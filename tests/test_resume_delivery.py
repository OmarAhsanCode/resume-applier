import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import shutil
import database
import app as flask_app
import google_service
from sources.base import create_normalized_job

class TestResumeDelivery(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.test_db)
        
        # Override the database DB_PATH globally
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.test_db
        
        # Configure app testing client
        flask_app.app.testing = True
        self.client = flask_app.app.test_client()
        
        self.cand_profile = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555-0199",
            "skills": ["Python", "SQL", "Flask", "Git"],
            "education": [{"degree": "BS Computer Science", "institution": "State Uni", "graduation_year": 2026}],
            "experience": [{
                "company": "Tech Corp",
                "role": "Software Engineering Intern",
                "start_date": "2025-06",
                "end_date": "2025-08",
                "bullets": ["Optimized backend SQL queries."]
            }]
        }
        database.save_candidate("Jane Doe", "jane@example.com", "+1 555-0199", self.cand_profile, db_path=self.test_db)

    def tearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except OSError:
                pass
        if os.path.exists("generated/resumes"):
            shutil.rmtree("generated/resumes", ignore_errors=True)

    @patch("ai.tailor_resume")
    @patch("google_service.update_job_resume_url_in_sheet")
    def test_1_resume_generation_saves_tex_and_updates_db(self, mock_sheet_update, mock_tailor):
        mock_tailor.return_value = {
            "header": {"name": "Jane Doe", "email": "jane@example.com", "phone": "+1 555-0199", "links": {}},
            "summary": "CS student.",
            "education": [{"degree": "BS CS", "institution": "State Uni", "year": "2026", "details": ""}],
            "experience": [{"company": "Tech Corp", "role": "Dev", "dates": "2025", "bullets": ["Optimized SQL"]}],
            "projects": [],
            "skills": {"languages": ["Python", "SQL"], "frameworks": ["Flask"], "tools": ["Git"]}
        }
        
        job_data = create_normalized_job(
            source="greenhouse",
            source_job_id="112233",
            company="Google",
            title="Software Engineer",
            location="Remote",
            employment_type="full-time",
            description="Software Engineering role.",
            application_url="https://example.com/job112233"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        # POST to generate resume
        with patch("database.get_candidate", return_value={"name": "Jane Doe", "profile": self.cand_profile}):
            resp = self.client.post(f"/jobs/{job_id}/generate-resume")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["status"], "success")
            self.assertIn("/view-resume", data["view_url"])
            self.assertIn("/download-resume", data["download_url"])

            # Verify file exists
            job = database.get_job_by_id(job_id, db_path=self.test_db)
            tex_path = job.get("resume_tex_path")
            self.assertTrue(tex_path and os.path.exists(tex_path))
            
            # Verify database path is populated correctly
            self.assertIn("Google_Software_Engineer", tex_path)

    @patch("ai.tailor_resume")
    def test_2_view_route_returns_plain_text(self, mock_tailor):
        mock_tailor.return_value = {
            "header": {"name": "Jane Doe", "email": "jane@example.com", "phone": "+1 555-0199", "links": {}},
            "summary": "CS student.",
            "education": [{"degree": "BS CS", "institution": "State Uni", "year": "2026", "details": ""}],
            "experience": [],
            "projects": [],
            "skills": {"languages": ["Python", "SQL"], "frameworks": ["Flask"], "tools": ["Git"]}
        }
        
        job_data = create_normalized_job(
            source="lever",
            source_job_id="445566",
            company="Microsoft",
            title="DevOps Engineer",
            location="Remote",
            employment_type="full-time",
            description="DevOps role.",
            application_url="https://example.com/job445566"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        with patch("database.get_candidate", return_value={"name": "Jane Doe", "profile": self.cand_profile}):
            self.client.post(f"/jobs/{job_id}/generate-resume")

        # GET view-resume
        resp = self.client.get(f"/jobs/{job_id}/view-resume")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "text/plain")
        self.assertIn("Jane Doe", resp.get_data(as_text=True))
        self.assertIn(r"\begin{document}", resp.get_data(as_text=True))

    @patch("ai.tailor_resume")
    def test_3_download_route_returns_attachment(self, mock_tailor):
        mock_tailor.return_value = {
            "header": {"name": "Jane Doe", "email": "jane@example.com", "phone": "+1 555-0199", "links": {}},
            "summary": "CS student.",
            "education": [{"degree": "BS CS", "institution": "State Uni", "year": "2026", "details": ""}],
            "experience": [],
            "projects": [],
            "skills": {"languages": ["Python", "SQL"], "frameworks": ["Flask"], "tools": ["Git"]}
        }
        
        job_data = create_normalized_job(
            source="lever",
            source_job_id="445566",
            company="Microsoft",
            title="DevOps Engineer",
            location="Remote",
            employment_type="full-time",
            description="DevOps role.",
            application_url="https://example.com/job445566"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        with patch("database.get_candidate", return_value={"name": "Jane Doe", "profile": self.cand_profile}):
            self.client.post(f"/jobs/{job_id}/generate-resume")

        # GET download-resume
        resp = self.client.get(f"/jobs/{job_id}/download-resume")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-tex")
        self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
        self.assertIn("Microsoft_DevOps_Engineer_Resume.tex", resp.headers.get("Content-Disposition", ""))

    def test_4_missing_resume_returns_404(self):
        job_data = create_normalized_job(
            source="ashby",
            source_job_id="778899",
            company="Netflix",
            title="UI Engineer",
            location="Remote",
            employment_type="full-time",
            description="UI role.",
            application_url="https://example.com/job778899"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        
        # Test viewing missing resume
        resp_view = self.client.get(f"/jobs/{job_id}/view-resume")
        self.assertEqual(resp_view.status_code, 404)
        self.assertIn("Resume source file not found.", resp_view.get_data(as_text=True))

        # Test downloading missing resume
        resp_dl = self.client.get(f"/jobs/{job_id}/download-resume")
        self.assertEqual(resp_dl.status_code, 404)
        self.assertIn("Resume source file not found.", resp_dl.get_data(as_text=True))

    def test_5_path_traversal_protection(self):
        # Insert a job with a path traversal in resume_tex_path
        job_data = create_normalized_job(
            source="ashby",
            source_job_id="999888",
            company="TraverseCorp",
            title="Security Engineer",
            location="Remote",
            employment_type="full-time",
            description="Security role.",
            application_url="https://example.com/job999888"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        
        conn = database.get_connection(self.test_db)
        conn.execute("UPDATE jobs SET resume_tex_path = ? WHERE id = ?", ("generated/resumes/../../app.py", job_id))
        conn.commit()
        conn.close()

        # Test viewing
        resp_view = self.client.get(f"/jobs/{job_id}/view-resume")
        self.assertEqual(resp_view.status_code, 403)
        self.assertIn("Access denied: Invalid path.", resp_view.get_data(as_text=True))

        # Test downloading
        resp_dl = self.client.get(f"/jobs/{job_id}/download-resume")
        self.assertEqual(resp_dl.status_code, 403)
        self.assertIn("Access denied: Invalid path.", resp_dl.get_data(as_text=True))

    def test_6_google_sheets_updates_only_resume_url(self):
        job_data = create_normalized_job(
            source="ashby",
            source_job_id="111",
            company="SheetCorp",
            title="Automation Engineer",
            location="Remote",
            employment_type="full-time",
            description="Automation role.",
            application_url="https://example.com/job111"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)
        
        job = database.get_job_by_id(job_id, db_path=self.test_db)
        job_dict = dict(job)
        
        # Mock sheets client
        mock_sheets = MagicMock()
        google_service._sheets_service = mock_sheets
        google_service.GOOGLE_SHEETS_SPREADSHEET_ID = "test_spreadsheet_id"
        
        # Mock find_row to return row 5
        with patch("google_service._find_job_row_number", return_value=5):
            res = google_service.update_job_resume_url_in_sheet(job_dict, "http://localhost:5000/jobs/111/view-resume")
            self.assertTrue(res)
            
            # Check sheet update was called with the local resume url
            mock_sheets.spreadsheets().values().update.assert_called_once()
            args, kwargs = mock_sheets.spreadsheets().values().update.call_args
            self.assertEqual(kwargs.get("range"), "Sheet1!N5")
            self.assertEqual(kwargs.get("body").get("values")[0][0], "http://localhost:5000/jobs/111/view-resume")
            
            # Verify status remains "selected" in DB
            updated_job = database.get_job_by_id(job_id, db_path=self.test_db)
            self.assertEqual(updated_job["status"], "selected")

    def test_7_overleaf_route_is_removed(self):
        resp = self.client.get("/jobs/1/overleaf")
        self.assertEqual(resp.status_code, 404)

if __name__ == "__main__":
    unittest.main()
