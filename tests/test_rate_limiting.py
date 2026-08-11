import unittest
from unittest.mock import MagicMock, patch
import tempfile
import ai
import database
import os
import shutil
from sources.base import create_normalized_job

class TestRateLimitingAndResilience(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.test_db)
        
        self.cand_profile = {
            "name": "Alex Smith",
            "email": "alex@example.com",
            "phone": "555-0100",
            "skills": ["Python", "Flask", "SQL"],
            "education": [{"degree": "BS CS", "institution": "Tech Uni", "graduation_year": 2026}],
            "experience": [{"company": "Acme", "role": "Dev", "start_date": "2025-01", "end_date": "2025-06", "bullets": ["Built API"]}]
        }
        database.save_candidate("Alex Smith", "alex@example.com", "555-0100", self.cand_profile, db_path=self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except OSError:
                pass
        if os.path.exists("generated/resumes"):
            shutil.rmtree("generated/resumes", ignore_errors=True)

    @patch("requests.post")
    def test_1_http_429_inspects_retry_after_header(self, mock_post):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "12.5"}

        mock_post.return_value = mock_resp_429
        
        provider = ai.AIProvider("TestProv", "test_key", "https://api.test.com/v1", "model_x")
        res = provider.call_chat_completion("test prompt")
        self.assertIsNone(res)
        self.assertFalse(provider.is_available())
        self.assertGreater(provider.rate_limit_reset_time, 0.0)

    @patch("requests.post")
    def test_2_http_429_exponential_backoff_when_header_missing(self, mock_post):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {}

        mock_post.return_value = mock_resp_429
        
        provider = ai.AIProvider("TestProv", "test_key", "https://api.test.com/v1", "model_x")
        res = provider.call_chat_completion("test prompt")
        self.assertIsNone(res)
        self.assertFalse(provider.is_available())

    @patch("requests.post")
    @patch("time.sleep")
    def test_3_max_retries_enforced_and_exception_handled(self, mock_sleep, mock_post):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {}

        mock_post.return_value = mock_resp_429

        original_key = ai.AI_API_KEY
        ai.AI_API_KEY = "real_test_key"
        try:
            with self.assertRaises(RuntimeError):
                ai.tailor_resume(self.cand_profile, {"company": "Acme", "title": "Dev"}, {}, {})
        finally:
            ai.AI_API_KEY = original_key

    def test_4_failed_resume_tailoring_leaves_job_intact(self):
        job_data = create_normalized_job(
            source="ashby",
            source_job_id="999",
            company="Tech Corp",
            title="Software Engineer Intern",
            location="Remote",
            employment_type="internship",
            description="Internship role.",
            application_url="https://example.com/job999"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        job = database.get_job_by_id(job_id, db_path=self.test_db)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "selected")
        self.assertIsNone(job.get("resume_tex_path"))

    def test_5_ondemand_resume_generation_in_app_route(self):
        import app as flask_app
        flask_app.app.testing = True
        client = flask_app.app.test_client()

        job_data = create_normalized_job(
            source="ashby",
            source_job_id="888",
            company="Figma",
            title="Software Engineer Intern",
            location="Remote",
            employment_type="internship",
            description="Internship role.",
            application_url="https://example.com/job888"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        with patch("database.get_candidate", return_value={"name": "Alex Smith", "profile": self.cand_profile}), \
             patch("database.get_job_by_id", return_value=database.get_job_by_id(job_id, db_path=self.test_db)), \
             patch("database.get_resume_settings", return_value={"section_order": ["summary", "skills"]}):
            resp = client.get(f"/jobs/{job_id}/view-resume")
            self.assertEqual(resp.status_code, 404)

if __name__ == "__main__":
    unittest.main()
