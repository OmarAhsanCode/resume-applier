import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import shutil
import json
import database
import app as flask_app
import resume
import resume_optimizer
import ai
from sources.base import create_normalized_job

class TestResumeOptimizer(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db = self.temp_file.name
        self.temp_file.close()
        database.init_db(self.test_db)
        
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.test_db
        
        flask_app.app.testing = True
        self.client = flask_app.app.test_client()
        
        self.cand_profile = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555-0199",
            "links": {"linkedin": "https://linkedin.com/in/janedoe", "github": "https://github.com/janedoe"},
            "skills": ["Python", "SQL", "Flask", "PyTorch", "Git", "Docker", "PostgreSQL", "JavaScript"],
            "education": [{"degree": "B.S. in Computer Science", "institution": "State University", "graduation_year": 2026, "cgpa": "3.9/4.0"}],
            "experience": [{
                "company": "Tech Corp",
                "role": "Software Engineering Intern",
                "start_date": "2025-06",
                "end_date": "2025-08",
                "bullets": ["Optimized backend SQL queries, improving response times by 25%."]
            }],
            "projects": [{
                "name": "AI Search Engine",
                "description": "Built neural vector search engine using Python and PyTorch.",
                "technologies": ["Python", "PyTorch", "Flask"],
                "bullets": ["Processed over 500+ document queries with sub-second latency."]
            }],
            "certifications": ["AWS Certified Cloud Practitioner"]
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

    # -----------------------------------------------------------------------
    # Scenario 1: Structured JD Parsing & Categorization
    # -----------------------------------------------------------------------
    def test_01_jd_parsing_and_classification(self):
        job = {
            "title": "Senior Backend Engineer",
            "company": "Enterprise Cloud",
            "description": """
            Requirements:
            - 5+ years of experience with Python, C++, and PostgreSQL.
            - Deep knowledge of Docker, Kubernetes, and AWS.
            Preferred Qualifications:
            - Experience with PyTorch, Machine Learning, and Redis.
            """
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        self.assertEqual(reqs["seniority"], "Senior")
        self.assertIn("Python", reqs["required_skills"])
        self.assertIn("C++", reqs["required_skills"])
        self.assertIn("PostgreSQL", reqs["required_skills"])
        self.assertIn("Docker", reqs["required_skills"])
        self.assertIn("Kubernetes", reqs["required_skills"])
        self.assertIn("PyTorch", reqs["preferred_skills"])

    # -----------------------------------------------------------------------
    # Scenario 2: Required vs Preferred Qualification Classification
    # -----------------------------------------------------------------------
    def test_02_required_vs_preferred_classification(self):
        job = {
            "title": "Software Engineer, Early Career",
            "company": "Acme Corp",
            "description": """
            Minimum Qualifications:
            - Bachelor's degree in Computer Science.
            - Proficiency in Python, SQL, and Git.
            Bonus Points / Preferred:
            - Experience with React, Go, and GraphQL.
            """
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        self.assertEqual(reqs["seniority"], "Entry Level")
        self.assertIn("Python", reqs["required_skills"])
        self.assertIn("SQL", reqs["required_skills"])
        self.assertIn("Git", reqs["required_skills"])
        self.assertIn("React", reqs["preferred_skills"])
        self.assertIn("Golang", reqs["preferred_skills"])

    # -----------------------------------------------------------------------
    # Scenario 3: Exact Skill Matching
    # -----------------------------------------------------------------------
    def test_03_skill_matching_exact(self):
        job = {
            "title": "Flask Backend Developer",
            "description": "Requirements: Python, Flask, SQL, Docker."
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        matrix = resume_optimizer.match_candidate_to_job(self.cand_profile, reqs)
        self.assertIn("Python", matrix["matched_required"])
        self.assertIn("Flask", matrix["matched_required"])
        self.assertIn("SQL", matrix["matched_required"])
        self.assertIn("Docker", matrix["matched_required"])

    # -----------------------------------------------------------------------
    # Scenario 4: Technical Synonym & Alias Matching
    # -----------------------------------------------------------------------
    def test_04_alias_and_synonym_matching(self):
        # Candidate has "PostgreSQL", JD asks for "Postgres" or "psql"
        # Candidate has "PyTorch", JD asks for "torch"
        # Candidate has "JavaScript", JD asks for "JS"
        self.assertTrue(resume_optimizer.skills_are_equivalent("PostgreSQL", "Postgres"))
        self.assertTrue(resume_optimizer.skills_are_equivalent("Machine Learning", "ML"))
        self.assertTrue(resume_optimizer.skills_are_equivalent("React.js", "React"))
        self.assertTrue(resume_optimizer.skills_are_equivalent("K8s", "Kubernetes"))
        self.assertTrue(resume_optimizer.skills_are_equivalent("GCP", "Google Cloud Platform"))

    # -----------------------------------------------------------------------
    # Scenario 5: Unsupported Skill Detection
    # -----------------------------------------------------------------------
    def test_05_unsupported_skill_detection(self):
        job = {
            "title": "Rust / Solidity Blockchain Engineer",
            "description": "Requirements: Rust, Solidity, C++, Web3."
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        matrix = resume_optimizer.match_candidate_to_job(self.cand_profile, reqs)
        self.assertIn("Rust", matrix["unsupported_required"])
        self.assertIn("Solidity", matrix["unsupported_required"])

    # -----------------------------------------------------------------------
    # Scenario 6: Keyword Coverage Calculation
    # -----------------------------------------------------------------------
    def test_06_keyword_coverage_calculation(self):
        job = {
            "title": "Python Developer",
            "description": "Requirements: Python, SQL, Flask, Git."
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        tailored = ai._mock_tailor_resume(self.cand_profile, job, {}, {})
        score_data = resume_optimizer.calculate_resume_match_score(tailored, reqs, self.cand_profile)
        self.assertGreaterEqual(score_data["sub_scores"]["keyword_coverage"], 75.0)

    # -----------------------------------------------------------------------
    # Scenario 7: Bullet Tailoring with Action Verbs & Structure
    # -----------------------------------------------------------------------
    def test_07_bullet_tailoring_action_verbs(self):
        tailored = ai._mock_tailor_resume(self.cand_profile, {"title": "Software Engineer", "company": "Tech Corp"}, {}, {})
        exp_bullets = tailored["experience"][0]["bullets"]
        self.assertTrue(any(b.startswith("Optimized") or b.startswith("Contributed") for b in exp_bullets))

    # -----------------------------------------------------------------------
    # Scenario 8: Strict Factual Integrity — Rejects Fabricated Skills
    # -----------------------------------------------------------------------
    def test_08_no_fabricated_skills_enforced(self):
        fake_tailored = {
            "header": {"name": "Jane Doe"},
            "skills": {
                "languages": ["Python", "Rust", "Haskell", "COBOL"],
                "frameworks": ["Flask", "Angular", "Spring Boot"]
            }
        }
        is_valid, violations, sanitized = resume_optimizer.validate_factual_integrity(fake_tailored, self.cand_profile)
        self.assertFalse(is_valid)
        self.assertTrue(any("Fabricated skill" in v for v in violations))
        self.assertNotIn("Rust", sanitized["skills"]["languages"])
        self.assertNotIn("Haskell", sanitized["skills"]["languages"])
        self.assertNotIn("Spring Boot", sanitized["skills"]["frameworks"])

    # -----------------------------------------------------------------------
    # Scenario 9: Strict Factual Integrity — Rejects Fabricated Metrics
    # -----------------------------------------------------------------------
    def test_09_no_fabricated_metrics_enforced(self):
        fake_tailored = {
            "header": {"name": "Jane Doe"},
            "experience": [{
                "company": "Tech Corp",
                "role": "Software Engineering Intern",
                "bullets": [
                    "Optimized backend SQL queries, improving response times by 25%.", # Supported (25%)
                    "Grew enterprise sales revenue by $50M across 1000+ Fortune 500 clients." # Unsupported ($50M, 1000+)
                ]
            }]
        }
        is_valid, violations, sanitized = resume_optimizer.validate_factual_integrity(fake_tailored, self.cand_profile)
        self.assertFalse(is_valid)
        self.assertTrue(any("Fabricated numerical metric" in v for v in violations))
        # Fabricated bullet should be stripped
        bullets = sanitized["experience"][0]["bullets"]
        self.assertEqual(len(bullets), 1)
        self.assertIn("25%", bullets[0])

    # -----------------------------------------------------------------------
    # Scenario 10: Strict Factual Integrity — Rejects Fake Employers/Projects
    # -----------------------------------------------------------------------
    def test_10_no_fabricated_experience_or_projects(self):
        fake_tailored = {
            "header": {"name": "Jane Doe"},
            "experience": [
                {"company": "Tech Corp", "role": "Software Engineering Intern", "bullets": ["Valid bullet."]},
                {"company": "NASA Jet Propulsion Lab", "role": "Principal Scientist", "bullets": ["Fake rocket scientist."]}
            ],
            "projects": [
                {"name": "AI Search Engine", "bullets": ["Valid search."]},
                {"name": "Mars Rover Autonomous Driver", "bullets": ["Fake autonomous system."]}
            ]
        }
        is_valid, violations, sanitized = resume_optimizer.validate_factual_integrity(fake_tailored, self.cand_profile)
        self.assertFalse(is_valid)
        exp_companies = [e["company"] for e in sanitized["experience"]]
        proj_names = [p["name"] for p in sanitized["projects"]]
        self.assertIn("Tech Corp", exp_companies)
        self.assertNotIn("NASA Jet Propulsion Lab", exp_companies)
        self.assertIn("AI Search Engine", proj_names)
        self.assertNotIn("Mars Rover Autonomous Driver", proj_names)

    # -----------------------------------------------------------------------
    # Scenario 11: Dynamic Section Ordering
    # -----------------------------------------------------------------------
    def test_11_dynamic_section_ordering(self):
        entry_job = {"title": "Software Engineering Intern", "seniority": "Internship"}
        senior_job = {"title": "Staff Backend Engineer", "seniority": "Senior"}
        
        entry_order = resume_optimizer.determine_optimal_section_order(entry_job)
        senior_order = resume_optimizer.determine_optimal_section_order(senior_job)
        
        self.assertEqual(entry_order[2], "Projects")
        self.assertEqual(senior_order[2], "Experience")

    # -----------------------------------------------------------------------
    # Scenario 12: ATS Format Validation
    # -----------------------------------------------------------------------
    def test_12_ats_format_validation(self):
        valid_tailored = ai._mock_tailor_resume(self.cand_profile, {"title": "Developer", "company": "Co"}, {}, {})
        latex_code = resume.render_latex(valid_tailored)
        is_valid, issues = resume_optimizer.validate_ats_format(latex_code)
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    # -----------------------------------------------------------------------
    # Scenario 13: LaTeX Rendering and Escaping of Special Characters
    # -----------------------------------------------------------------------
    def test_13_latex_rendering_and_escaping(self):
        escaped = resume.latex_escape("C++ & Python with 100% test coverage & $50 bonus #1 _tag_ {bracket}")
        self.assertIn(r"\&", escaped)
        self.assertIn(r"\%", escaped)
        self.assertIn(r"\$", escaped)
        self.assertIn(r"\#", escaped)
        self.assertIn(r"\_", escaped)

    # -----------------------------------------------------------------------
    # Scenario 14: PDF Compilation Non-Crashing Handling
    # -----------------------------------------------------------------------
    def test_14_pdf_compilation_handling(self):
        # Even with nonexistent or broken file, compile_pdf returns False without unhandled crash
        success, pdf_path, err = resume.compile_pdf("nonexistent_resume_file.tex")
        self.assertFalse(success)

    # -----------------------------------------------------------------------
    # Scenario 15: Master Candidate Profile Immutability
    # -----------------------------------------------------------------------
    def test_15_generated_resume_master_integrity(self):
        cand_before = database.get_candidate(db_path=self.test_db)
        job = {"title": "Data Scientist", "company": "AI Labs", "description": "PyTorch, Python, SQL"}
        
        pipeline_res = resume_optimizer.tailor_resume_pipeline(self.cand_profile, job)
        cand_after = database.get_candidate(db_path=self.test_db)
        
        # Profile in database must not have mutated
        self.assertEqual(cand_before["profile"]["skills"], cand_after["profile"]["skills"])
        self.assertEqual(cand_before["profile"]["name"], cand_after["profile"]["name"])

    # -----------------------------------------------------------------------
    # Scenario 16: Job-Resume Database Association & Persistence
    # -----------------------------------------------------------------------
    def test_16_job_resume_database_association(self):
        job_data = create_normalized_job(
            source="greenhouse",
            source_job_id="991122",
            company="Stripe",
            title="Backend Engineer",
            location="Remote",
            employment_type="full-time",
            description="Python and SQL role.",
            application_url="https://stripe.com/jobs/991122"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        
        database.update_job_resume(
            job_id=job_id,
            resume_json={"summary": "Stripe tailored."},
            tex_path="generated/resumes/Stripe_Backend_Engineer_1.tex",
            status="selected",
            resume_score=94.5,
            resume_match_details={"sub_scores": {"keyword_coverage": 95.0}},
            db_path=self.test_db
        )
        
        loaded = database.get_job_by_id(job_id, db_path=self.test_db)
        self.assertEqual(loaded["resume_score"], 94.5)
        self.assertEqual(loaded["resume_match_details"]["sub_scores"]["keyword_coverage"], 95.0)

    # -----------------------------------------------------------------------
    # Scenario 17: Resume Scoring Engine Sub-scores
    # -----------------------------------------------------------------------
    def test_17_resume_scoring_engine_subscores(self):
        job = {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "description": "Requirements: Python, SQL, Flask. Preferred: Docker, Kubernetes."
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        tailored = ai._mock_tailor_resume(self.cand_profile, job, {}, {})
        score_data = resume_optimizer.calculate_resume_match_score(tailored, reqs, self.cand_profile)
        
        self.assertIn("overall_score", score_data)
        self.assertIn("sub_scores", score_data)
        subs = score_data["sub_scores"]
        self.assertIn("required_skills", subs)
        self.assertIn("preferred_skills", subs)
        self.assertIn("keyword_coverage", subs)
        self.assertIn("role_alignment", subs)
        self.assertIn("experience_relevance", subs)
        self.assertIn("project_relevance", subs)
        self.assertIn("ats_format", subs)
        self.assertIn("content_quality", subs)

    # -----------------------------------------------------------------------
    # Scenario 18: Missing vs Matched Skill Reporting
    # -----------------------------------------------------------------------
    def test_18_missing_keyword_reporting(self):
        job = {
            "title": "Full Stack Engineer",
            "description": "Requirements: Python, Ruby, C++. Preferred: Kubernetes, Rust."
        }
        reqs = resume_optimizer.analyze_job_requirements(job)
        matrix = resume_optimizer.match_candidate_to_job(self.cand_profile, reqs)
        
        self.assertIn("Python", matrix["matched_required"])
        self.assertIn("Ruby", matrix["unsupported_required"])
        self.assertIn("Rust", matrix["unsupported_preferred"])

    # -----------------------------------------------------------------------
    # Scenario 19: Iterative Refinement Loop
    # -----------------------------------------------------------------------
    def test_19_iterative_refinement_loop(self):
        job = {
            "title": "Backend Intern",
            "company": "Cloud Corp",
            "description": "Python, SQL, Flask, Git."
        }
        result = resume_optimizer.tailor_resume_pipeline(
            candidate_profile=self.cand_profile,
            job_dict=job,
            max_iterations=2
        )
        self.assertIn("resume_json", result)
        self.assertIn("match_score", result)
        self.assertGreaterEqual(result["match_score"], 80.0)

    # -----------------------------------------------------------------------
    # Scenario 20: Full Pipeline Preservation & Route Delivery
    # -----------------------------------------------------------------------
    def test_20_full_pipeline_preservation_and_delivery(self):
        job_data = create_normalized_job(
            source="lever",
            source_job_id="554433",
            company="Databricks",
            title="Software Engineer, Infrastructure",
            location="San Francisco, CA",
            employment_type="full-time",
            description="Python and distributed systems.",
            application_url="https://jobs.lever.co/databricks/554433"
        )
        job_id = database.save_job(job_data, db_path=self.test_db)
        database.update_job_status(job_id, "selected", db_path=self.test_db)

        with patch("database.get_candidate", return_value={"name": "Jane Doe", "profile": self.cand_profile}):
            # Generate Resume
            resp = self.client.post(f"/jobs/{job_id}/generate-resume")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["status"], "success")
            self.assertIn("match_score", data)
            self.assertIn("match_details", data)
            
            # Fetch Resume Match Details Endpoint
            details_resp = self.client.get(f"/jobs/{job_id}/resume-details")
            self.assertEqual(details_resp.status_code, 200)
            det_data = details_resp.get_json()
            self.assertEqual(det_data["company"], "Databricks")
            self.assertIsNotNone(det_data["resume_score"])

if __name__ == "__main__":
    unittest.main()
