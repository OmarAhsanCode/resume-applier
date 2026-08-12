import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

import database
import jobs
import app as flask_app
from sources.base import create_normalized_job

class TestV1_2UIControlsAndResilience(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        database.init_db(self.db_path)

        flask_app.app.testing = True
        self.client = flask_app.app.test_client()

        # Seed candidate profile & preferences
        self.cand_profile = {
            "name": "Alex Smith",
            "email": "alex@example.com",
            "phone": "555-0100",
            "skills": ["Python", "SQL", "Flask"],
            "education": [{"degree": "BS CS", "institution": "State Uni", "graduation_year": 2026}],
            "experience": [{"company": "Acme Inc", "role": "Developer", "start_date": "2025-01", "end_date": "2025-06", "bullets": ["Built APIs"]}]
        }
        database.save_candidate("Alex Smith", "alex@example.com", "555-0100", self.cand_profile, db_path=self.db_path)
        database.save_preferences({
            "preferred_roles": ["Software Engineer"],
            "locations": ["Remote"],
            "experience_levels": ["entry_level"],
            "jobs_per_run": 10
        }, db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_1_run_cooperative_cancellation_checkpoint(self):
        """1. Verify that setting stop_checker causes the pipeline to stop gracefully."""
        stop_flag = True
        res = jobs.run_job_search_pipeline(requested_jobs=10, stop_checker=lambda: stop_flag, db_path=self.db_path)
        self.assertEqual(res["status"], "stopped")
        self.assertIn("stopped", res["message"].lower())

    def test_2_stopped_run_status_updated_in_db(self):
        """2. Verify that a cancelled run has its DB status set to 'stopped'."""
        stop_flag = True
        res = jobs.run_job_search_pipeline(requested_jobs=10, stop_checker=lambda: stop_flag, db_path=self.db_path)
        run_record = database.get_run(res["run_id"], db_path=self.db_path)
        self.assertEqual(run_record["status"], "stopped")

    def test_3_stopped_run_jobs_deleted(self):
        """3. Verify that stopping a run deletes ONLY jobs created during that run."""
        # Create Run 1
        run1_id = database.create_run(10, db_path=self.db_path)
        job1 = create_normalized_job(
            source="greenhouse", source_job_id="101", company="Acme", title="Software Engineer",
            location="Remote", employment_type="full_time", description="Python role", application_url="https://acme.com/job101"
        )
        job1["run_id"] = run1_id
        database.save_job(job1, db_path=self.db_path)

        # Create Run 2 (Stopped)
        run2_id = database.create_run(10, db_path=self.db_path)
        job2 = create_normalized_job(
            source="lever", source_job_id="102", company="Beta Corp", title="Backend Engineer",
            location="Remote", employment_type="full_time", description="Python role", application_url="https://beta.com/job102"
        )
        job2["run_id"] = run2_id
        database.save_job(job2, db_path=self.db_path)

        # Execute run-scoped cleanup on Run 2
        deleted = database.delete_jobs_by_run_id(run2_id, db_path=self.db_path)
        self.assertEqual(deleted, 1)

        # Check DB state
        all_jobs = database.get_all_jobs(db_path=self.db_path)
        self.assertEqual(len(all_jobs), 1)
        self.assertEqual(all_jobs[0]["company"], "Acme")

    def test_4_previous_run_jobs_preserved(self):
        """4. Verify that historical jobs from earlier runs are preserved when a new run is stopped."""
        # Run 1 completed job
        run1_id = database.create_run(5, db_path=self.db_path)
        job1 = create_normalized_job(
            source="ashby", source_job_id="201", company="Stripe", title="Software Engineer",
            location="Remote", employment_type="full_time", description="Role", application_url="https://stripe.com/201"
        )
        job1["run_id"] = run1_id
        database.save_job(job1, db_path=self.db_path)
        database.update_run_progress(run1_id, status="completed", db_path=self.db_path)

        # Run 2 stopped
        run2_id = database.create_run(5, db_path=self.db_path)
        job2 = create_normalized_job(
            source="ashby", source_job_id="202", company="Figma", title="Developer",
            location="Remote", employment_type="full_time", description="Role", application_url="https://figma.com/202"
        )
        job2["run_id"] = run2_id
        database.save_job(job2, db_path=self.db_path)
        database.delete_jobs_by_run_id(run2_id, db_path=self.db_path)

        surviving = database.get_all_jobs(db_path=self.db_path)
        self.assertEqual(len(surviving), 1)
        self.assertEqual(surviving[0]["company"], "Stripe")

    def test_5_clear_jobs_and_runs_removes_jobs(self):
        """5. Verify clear_jobs_and_runs() removes all jobs."""
        job1 = create_normalized_job(source="ashby", source_job_id="301", company="X", title="Eng", location="Remote", employment_type="full_time", description="D", application_url="https://x.com/301")
        database.save_job(job1, db_path=self.db_path)

        database.clear_jobs_and_runs(db_path=self.db_path)
        all_jobs = database.get_all_jobs(db_path=self.db_path)
        self.assertEqual(len(all_jobs), 0)

    def test_6_clear_jobs_and_runs_removes_runs(self):
        """6. Verify clear_jobs_and_runs() removes all runs."""
        database.create_run(5, db_path=self.db_path)
        database.clear_jobs_and_runs(db_path=self.db_path)
        latest = database.get_latest_run(db_path=self.db_path)
        self.assertIsNone(latest)

    def test_7_active_run_prevents_database_clearing(self):
        """7. Verify POST /database/clear returns 409 if a run is active."""
        with patch("app._active_run_thread") as mock_thread:
            mock_thread.is_alive.return_value = True
            resp = self.client.post("/database/clear")
            self.assertEqual(resp.status_code, 409)

    def test_8_run_status_endpoint_returns_payload(self):
        """8. Verify GET /run/status returns active, status, progress, and logs."""
        resp = self.client.get("/run/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("active", data)
        self.assertIn("status", data)
        self.assertIn("progress", data)
        self.assertIn("logs", data)

    def test_9_live_logs_returned_in_status(self):
        """9. Verify log messages are streamed in the logs list."""
        flask_app.add_log_entry("Test live log entry")
        resp = self.client.get("/run/status")
        data = resp.get_json()
        self.assertTrue(any("Test live log entry" in line for line in data["logs"]))

    def test_10_progress_dict_returned_in_status(self):
        """10. Verify progress dictionary is returned in status endpoint."""
        resp = self.client.get("/run/status")
        data = resp.get_json()
        self.assertIsInstance(data["progress"], dict)

    def test_11_completed_run_reports_completion(self):
        """11. Verify a completed run updates progress status to completed."""
        with patch("database.DB_PATH", self.db_path), \
             patch("sources.discover_all_sources", return_value=[]):
            res = jobs.run_job_search_pipeline(requested_jobs=5, db_path=self.db_path)
            self.assertEqual(res["status"], "completed")

    def test_12_stopped_run_reports_stopped(self):
        """12. Verify a stopped run reports 'stopped' status."""
        with patch("database.DB_PATH", self.db_path):
            res = jobs.run_job_search_pipeline(requested_jobs=5, stop_checker=lambda: True, db_path=self.db_path)
            self.assertEqual(res["status"], "stopped")

    def test_13_results_page_has_configured_google_sheet_url(self):
        """13. Verify results page constructs Google Sheet URL when env variable is present."""
        with patch.dict(os.environ, {"GOOGLE_SHEETS_SPREADSHEET_ID": "test_sheet_123"}):
            resp = self.client.get("/results")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"https://docs.google.com/spreadsheets/d/test_sheet_123", resp.data)

    def test_14_missing_spreadsheet_config_handled_gracefully(self):
        """14. Verify results page handles unconfigured Google Sheet gracefully without crashing."""
        with patch.dict(os.environ, {"GOOGLE_SHEETS_SPREADSHEET_ID": ""}):
            resp = self.client.get("/results")
            self.assertEqual(resp.status_code, 200)

if __name__ == "__main__":
    unittest.main()
