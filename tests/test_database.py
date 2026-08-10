import os
import unittest
import tempfile
import database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        database.init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_candidate_crud(self):
        profile = {
            "name": "Jane Doe",
            "skills": ["Python", "SQL"],
            "education": [{"degree": "BS CS", "year": 2025}]
        }
        database.save_candidate("Jane Doe", "jane@example.com", "+123456", profile, db_path=self.db_path)
        retrieved = database.get_candidate(db_path=self.db_path)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["name"], "Jane Doe")
        self.assertEqual(retrieved["profile"]["skills"], ["Python", "SQL"])

    def test_preferences_crud(self):
        prefs = {
            "preferred_roles": ["Software Engineer"],
            "locations": ["Remote"],
            "jobs_per_run": 25
        }
        database.save_preferences(prefs, db_path=self.db_path)
        retrieved = database.get_preferences(db_path=self.db_path)
        self.assertEqual(retrieved["jobs_per_run"], 25)
        self.assertEqual(retrieved["preferred_roles"], ["Software Engineer"])

    def test_job_deduplication_and_crud(self):
        job_data = {
            "source": "greenhouse",
            "source_job_id": "101",
            "unique_id": "greenhouse:101",
            "company": "Tech Corp",
            "title": "Backend Engineer",
            "description": "Python developer role",
            "application_url": "https://example.com/apply/101"
        }
        self.assertFalse(database.job_exists("greenhouse:101", db_path=self.db_path))
        job_id = database.save_job(job_data, db_path=self.db_path)
        self.assertTrue(database.job_exists("greenhouse:101", db_path=self.db_path))
        
        # Test update job status
        database.update_job_status(job_id, "applied", db_path=self.db_path)
        job = database.get_job_by_id(job_id, db_path=self.db_path)
        self.assertEqual(job["status"], "applied")
        self.assertIsNotNone(job["applied_at"])

    def test_runs_crud(self):
        run_id = database.create_run(50, db_path=self.db_path)
        database.update_run_progress(run_id, discovered_count=100, duplicate_count=20, status="completed", db_path=self.db_path)
        run = database.get_run(run_id, db_path=self.db_path)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["discovered_count"], 100)

if __name__ == "__main__":
    unittest.main()
