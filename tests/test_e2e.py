import os
import unittest
import tempfile
import database
import ai
import jobs
import resume

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        database.init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_full_e2e_workflow(self):
        # 1. Candidate Setup
        sample_cv = """
        Alex Johnson
        alex.johnson@example.com | +1 555-0199
        
        Education:
        B.Tech Computer Science, State University, 2026. CGPA: 8.9/10
        
        Skills:
        Python, Java, SQL, Flask, Git, Machine Learning, Docker
        
        Experience:
        Software Engineering Intern at Cloud Systems (2025-05 to 2025-08)
        - Developed Python microservices using Flask and PostgreSQL.
        - Wrote automated test scripts in pytest.
        """
        profile = ai.parse_resume(sample_cv)
        database.save_candidate("Alex Johnson", "alex.johnson@example.com", "+1 555-0199", profile, db_path=self.db_path)

        retrieved_cand = database.get_candidate(db_path=self.db_path)
        self.assertIsNotNone(retrieved_cand)
        self.assertEqual(retrieved_cand["name"], "Alex Johnson")

        # 2. Search Preferences Setup
        prefs = {
            "preferred_roles": ["Software Engineer", "Python Developer", "AI Engineer"],
            "locations": ["Remote", "Hyderabad"],
            "work_modes": ["remote", "hybrid"],
            "experience_levels": ["entry_level", "internship"],
            "jobs_per_run": 5,
            "dream_companies": ["Google", "Microsoft"]
        }
        database.save_preferences(prefs, db_path=self.db_path)

        # 3. Simulate Pipeline Run 1
        res1 = jobs.run_job_search_pipeline(requested_jobs=5, db_path=self.db_path)
        self.assertIn(res1["status"], ["completed", "partial"])
        self.assertTrue(res1["discovered_count"] > 0)
        self.assertTrue(res1["selected_count"] > 0)

        first_selected_jobs = database.get_all_jobs(status_filter="selected", db_path=self.db_path)
        self.assertTrue(len(first_selected_jobs) > 0)
        
        top_job = first_selected_jobs[0]
        self.assertIsNotNone(top_job["final_score"])
        self.assertIsNotNone(top_job["resume_tex_path"])

        # Mark top job as Applied
        database.update_job_status(top_job["id"], "applied", db_path=self.db_path)
        updated_job = database.get_job_by_id(top_job["id"], db_path=self.db_path)
        self.assertEqual(updated_job["status"], "applied")

        # 4. Simulate Pipeline Run 2 (Deduplication Check)
        res2 = jobs.run_job_search_pipeline(requested_jobs=5, db_path=self.db_path)
        self.assertIn(res2["status"], ["completed", "partial"])
        self.assertTrue(res2["duplicate_count"] > 0) # Previously seen jobs must be deduplicated!

if __name__ == "__main__":
    unittest.main()
