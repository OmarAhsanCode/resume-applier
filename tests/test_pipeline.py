import os
import unittest
import tempfile
import database
import jobs
import resume
import google_service
import sources

class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        database.init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_latex_escaping(self):
        raw_text = "Experienced in C++ & Python (100% test coverage) with $10k #achievements _under_ {pressure} \\ syntax"
        escaped = resume.latex_escape(raw_text)
        self.assertIn(r"C++", escaped)
        self.assertIn(r"\&", escaped)
        self.assertIn(r"\%", escaped)
        self.assertIn(r"\$", escaped)
        self.assertIn(r"\#", escaped)
        self.assertIn(r"\_", escaped)
        self.assertIn(r"\{", escaped)
        self.assertIn(r"\}", escaped)

    def test_conservative_filtering(self):
        pref = {
            "preferred_roles": ["Software Engineer", "AI Engineer"],
            "locations": ["Remote", "Hyderabad"],
            "experience_levels": ["internship", "entry_level"]
        }
        cand = {"skills": ["Python", "SQL"]}

        # Test valid job with missing skills (MUST NOT hard filter)
        job_valid = {
            "title": "Junior Software Engineer",
            "company": "Acme Tech",
            "location": "Remote",
            "description": "Looking for Python, SQL, C++, Azure, Docker."
        }
        filtered, reason = jobs.is_hard_filtered(job_valid, pref, cand)
        self.assertFalse(filtered)

        # Test obvious profession mismatch (MUST hard filter)
        job_unrelated = {
            "title": "Registered Nurse",
            "company": "City Hospital",
            "location": "Remote",
            "description": "Healthcare role."
        }
        filtered2, reason2 = jobs.is_hard_filtered(job_unrelated, pref, cand)
        self.assertTrue(filtered2)

    def test_deterministic_scoring(self):
        pref = {
            "preferred_roles": ["Software Engineer"],
            "locations": ["Remote"],
            "experience_levels": ["entry_level"],
            "dream_companies": ["Google"]
        }
        cand = {"skills": ["Python", "SQL"]}

        job_normal = {
            "company": "Normal Corp",
            "title": "Software Engineer",
            "location": "Remote",
            "employment_type": "Full-time",
            "description": "Python developer role."
        }
        score_normal = jobs.calculate_deterministic_score(cand, pref, job_normal)
        self.assertTrue(score_normal >= 70.0)

        job_dream = {
            "company": "Google LLC",
            "title": "Software Engineer",
            "location": "Remote",
            "employment_type": "Full-time",
            "description": "Python developer role."
        }
        score_dream = jobs.calculate_deterministic_score(cand, pref, job_dream)
        self.assertTrue(score_dream > score_normal)

    def test_google_service_fallback(self):
        # Without configured SPREADSHEET_ID, sync should return False without throwing
        # Patch the internal helper so real .env values don't interfere
        from unittest.mock import patch as _patch
        with _patch.object(google_service, '_spreadsheet_id', return_value=""):
            with _patch.object(google_service, 'ensure_sheets_service', return_value=False):
                sheet_ok = google_service.sync_jobs_to_sheet([])
                self.assertFalse(sheet_ok)

    def test_normalize_url_with_query_params(self):
        url = "https://jobs.lever.co/company/abc12345/?gh_jid=123&utm_source=feed"
        normalized = sources.base.normalize_url(url)
        self.assertEqual(normalized, "https://jobs.lever.co/company/abc12345")

if __name__ == "__main__":
    unittest.main()
