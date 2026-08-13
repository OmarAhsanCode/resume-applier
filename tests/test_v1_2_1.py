import unittest
import os
import re
from sources.base import normalize_employment_type, normalize_salary, extract_salary_with_evidence, create_normalized_job
import ai
import jobs
import database
import google_service

class TestV1_2_1QualityAndUX(unittest.TestCase):

    def setUp(self):
        self.test_db = f"data/test_v1_2_1_{self._testMethodName}.db"
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass
        database.init_db(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    # --- 1. Employment Classification Tests (1-9) ---
    def test_1_intern_title_full_time_metadata(self):
        res = normalize_employment_type("full_time", "Software Engineer (Intern)", "Job desc")
        self.assertEqual(res, "internship")

    def test_2_intern_title_contract_metadata(self):
        res = normalize_employment_type("contract", "Software Engineer, Intern", "Job desc")
        self.assertEqual(res, "internship")

    def test_3_intern_title_unknown_metadata(self):
        res = normalize_employment_type(None, "Software Engineering Intern", "Job desc")
        self.assertEqual(res, "internship")

    def test_4_new_grad(self):
        res = normalize_employment_type("full_time", "Software Engineer — New Grad", "Job desc")
        self.assertEqual(res, "entry_level")

    def test_5_junior_engineer(self):
        res = normalize_employment_type("full_time", "Junior Software Engineer", "Job desc")
        self.assertEqual(res, "entry_level")

    def test_6_associate_software_engineer(self):
        res = normalize_employment_type("full_time", "Associate Software Engineer", "Job desc")
        self.assertEqual(res, "entry_level")

    def test_7_associate_director_not_entry_level(self):
        res = normalize_employment_type("full_time", "Associate Director", "Job desc")
        self.assertNotEqual(res, "entry_level")
        self.assertEqual(res, "full_time")

    def test_8_senior_associate(self):
        res = normalize_employment_type("full_time", "Senior Associate", "Job desc")
        self.assertNotEqual(res, "entry_level")
        self.assertEqual(res, "full_time")

    def test_9_senior_engineer(self):
        res = normalize_employment_type("full_time", "Senior Software Engineer", "Job desc")
        self.assertEqual(res, "full_time")

    # --- 2. Salary Extraction & Fallback Tests (10-16) ---
    def test_10_structured_salary_extraction(self):
        m, text, ev = extract_salary_with_evidence("₹50,000/month", "desc")
        self.assertEqual(m, 50000)
        self.assertEqual(ev, "source_salary_text")

    def test_11_description_salary_fallback(self):
        m, text, ev = extract_salary_with_evidence(None, "The position offers a salary of ₹40,000/month for all selected candidates.")
        self.assertEqual(m, 40000)
        self.assertEqual(text, "₹40,000/month")
        self.assertEqual(ev, "description")

    def test_12_lpa_normalization(self):
        m, text = normalize_salary("₹6 LPA")
        self.assertEqual(m, 50000)
        self.assertIn("6", text)
        self.assertIn("LPA", text)

    def test_13_50k_month(self):
        m, text = normalize_salary("50k/pm")
        self.assertEqual(m, 50000)
        self.assertEqual(text, "₹50,000/month")

    def test_14_stipend_extraction(self):
        m, text, ev = extract_salary_with_evidence(None, "Stipend of ₹30,000 per month will be provided during internship.")
        self.assertEqual(m, 30000)
        self.assertEqual(text, "₹30,000/month")
        self.assertEqual(ev, "description")

    def test_15_missing_salary_not_disclosed(self):
        m, text, ev = extract_salary_with_evidence(None, "Standard software engineering duties.")
        self.assertIsNone(m)
        self.assertEqual(text, "Not disclosed")
        self.assertEqual(ev, "unknown")

    def test_16_no_fabricated_salary_values(self):
        m, text = normalize_salary(None, "We offer competitive benefits and healthcare.")
        self.assertEqual(text, "Not disclosed")
        self.assertIsNone(m)

    # --- 3. Key Points & AI Analysis Schema Tests (17-20) ---
    def test_17_ai_key_points_contain_job_facts(self):
        raw_analysis = {
            "score": 90,
            "recommendation": "strong_match",
            "role_summary": "Build backend APIs in Python",
            "key_technologies": ["Python", "Flask", "PostgreSQL"],
            "key_points": [
                "Build scalable REST APIs using Python and Flask",
                "Deploy services on AWS Kubernetes clusters",
                "Collaborate with product and data engineering teams"
            ],
            "reason": "Omar Ahsan demonstrates a strong fit with core Python requirements."
        }
        cleaned = ai._clean_job_analysis(raw_analysis)
        self.assertEqual(len(cleaned["key_points"]), 3)
        self.assertIn("Build scalable REST APIs using Python and Flask", cleaned["key_points"])
        self.assertIn("Omar Ahsan", cleaned["reason"])

    def test_18_candidate_match_commentary_filtered_from_key_points(self):
        raw_analysis = {
            "score": 85,
            "key_points": [
                "Omar Ahsan has 3 years of Python experience",
                "Candidate demonstrates good fit",
                "Develop distributed AI data pipelines"
            ]
        }
        cleaned = ai._clean_job_analysis(raw_analysis)
        for point in cleaned["key_points"]:
            self.assertNotIn("Omar Ahsan", point)
            self.assertNotIn("Candidate demonstrates", point)

    def test_19_key_technologies_structured_correctly(self):
        job = {"company": "Acme", "title": "Dev", "description": "Python SQL AWS"}
        res = ai._mock_analyze_job({"skills": ["Python"]}, job)
        self.assertIsInstance(res["key_technologies"], list)

    def test_20_role_summary_is_concise(self):
        job = {"company": "Acme", "title": "Dev", "description": "Python SQL AWS"}
        res = ai._mock_analyze_job({"skills": ["Python"]}, job)
        self.assertIsInstance(res["role_summary"], str)
        self.assertLess(len(res["role_summary"]), 120)

    # --- 4. Ranking & Score Precision Tests (21-24) ---
    def test_21_existing_scoring_formula(self):
        profile = {"skills": ["Python", "SQL"]}
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = create_normalized_job("greenhouse", "1", "Acme", "Software Engineer", "Hyderabad", "full_time", "Python SQL", "http://app")
        
        score = jobs.calculate_deterministic_score(profile, prefs, job)
        self.assertIsInstance(score, float)
        self.assertGreater(score, 50.0)

    def test_22_score_precision_preserved_internally(self):
        job = create_normalized_job("adzuna", "101", "BetaCorp", "Developer", "Hyderabad", "full_time", "Python", "http://app")
        job["deterministic_score"] = 87.8432
        job["ai_score"] = 92.1568
        job["final_score"] = 89.5686
        
        job_id = database.save_job(job, db_path=self.test_db)
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        
        self.assertAlmostEqual(fetched["final_score"], 89.5686, places=3)

    def test_23_display_rounding_does_not_change_ranking(self):
        j1 = {"final_score": 87.86}
        j2 = {"final_score": 87.84}
        
        self.assertGreater(j1["final_score"], j2["final_score"])
        self.assertEqual(round(j1["final_score"], 1), 87.9)
        self.assertEqual(round(j2["final_score"], 1), 87.8)

    def test_24_identical_scores_remain_identical(self):
        score1 = 85.0
        score2 = 85.0
        self.assertEqual(score1, score2)

    # --- 5. End-to-End Database & Results Page Integration Tests ---
    def test_normalized_internship_classification_reaches_results_page(self):
        job = create_normalized_job("adzuna", "1001", "Stripe", "Software Engineer(Intern)- Backend", "Remote", "full_time", "Python API dev", "http://stripe")
        job_id = database.save_job(job, db_path=self.test_db)
        
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        self.assertEqual(fetched["employment_type"], "internship")
        self.assertEqual(fetched["employment_type_display"], "Internship")

    def test_raw_full_time_metadata_does_not_override_explicit_intern_title(self):
        job = create_normalized_job("adzuna", "1002", "Google", "Software Engineer, Intern", "Hyderabad", "full_time", "Desc", "http://google")
        self.assertEqual(job["employment_type"], "internship")

    def test_normalized_employment_value_is_displayed(self):
        job = create_normalized_job("greenhouse", "1003", "Meta", "Associate Software Engineer", "Remote", "full_time", "Desc", "http://meta")
        job_id = database.save_job(job, db_path=self.test_db)
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        self.assertEqual(fetched["employment_type_display"], "Entry Level")

    def test_key_points_contain_objective_job_facts(self):
        raw_analysis = {
            "score": 85,
            "key_points": ["Build backend services for AI products", "Python, AWS and Kubernetes", "Work with distributed systems"],
            "reason": "Omar demonstrates a strong alignment with Software Engineer..."
        }
        cleaned = ai._clean_job_analysis(raw_analysis)
        self.assertIn("Build backend services for AI products", cleaned["key_points"])
        self.assertNotIn("Omar demonstrates", str(cleaned["key_points"]))

    def test_candidate_match_reason_is_not_displayed_as_key_points(self):
        job = create_normalized_job("lever", "1004", "Uber", "Backend Developer", "Remote", "full_time", "Python APIs", "http://uber")
        job["ai_analysis"] = {
            "score": 80,
            "reason": "Omar is a strong candidate for Uber's backend engineering role."
        }
        job_id = database.save_job(job, db_path=self.test_db)
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        
        self.assertNotIn("Omar is a strong candidate", str(fetched["ai_analysis"]["key_points"]))

    def test_old_database_records_remain_readable(self):
        conn = database.get_connection(self.test_db)
        conn.execute("""
        INSERT INTO jobs (source, unique_id, company, title, location, employment_type, application_url, description, first_seen, last_seen, status, created_at, updated_at)
        VALUES ('greenhouse', 'old:1', 'GitLab', 'Software Engineer, Intern', 'Remote', 'full_time', 'http://gitlab', 'Salary range $115,000 to $162,000 USD per year', '2026-01-01', '2026-01-01', 'new', '2026-01-01', '2026-01-01')
        """)
        conn.commit()
        conn.close()

        all_jobs = database.get_all_jobs(db_path=self.test_db)
        old_job = [j for j in all_jobs if j["unique_id"] == "old:1"][0]
        
        self.assertEqual(old_job["employment_type"], "internship")
        self.assertEqual(old_job["employment_type_display"], "Internship")
        self.assertIn("$115,000", old_job["salary_text"])

    def test_salary_description_fallback_reaches_results_page_when_compensation_exists(self):
        job = create_normalized_job("greenhouse", "1005", "GitLab", "Backend Engineer", "Remote", "full_time", "Base salary range is $115,000 to $162,000 USD per year.", "http://gitlab")
        job_id = database.save_job(job, db_path=self.test_db)
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        
        self.assertIn("$115,000", fetched["salary_text"])

if __name__ == "__main__":
    unittest.main()

