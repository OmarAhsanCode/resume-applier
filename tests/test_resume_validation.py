import unittest
import ai
import resume

class TestResumeValidation(unittest.TestCase):
    def setUp(self):
        self.cand_profile = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555-0199",
            "skills": ["Python", "SQL", "Flask", "PyTorch", "Git"],
            "education": [{"degree": "BS Computer Science", "institution": "State Uni", "graduation_year": 2026}],
            "experience": [{
                "company": "Tech Corp",
                "role": "Software Engineering Intern",
                "start_date": "2025-06",
                "end_date": "2025-08",
                "bullets": ["Optimized backend SQL queries, improving response times by 25%."]
            }],
            "projects": [{
                "name": "AI Search Engine",
                "description": "Built vector search tool using Python and PyTorch.",
                "technologies": ["Python", "PyTorch"],
                "bullets": ["Processed over 500+ document queries."]
            }]
        }

    def test_1_skills_validation_rejects_hallucinated_skills(self):
        tailored_with_fake_skills = {
            "header": {"name": "Jane Doe"},
            "skills": {
                "languages": ["Python", "SQL", "Rust", "Golang"], # Rust & Golang are hallucinated
                "frameworks": ["Flask", "Spring Boot"] # Spring Boot is hallucinated
            }
        }
        validated = ai.validate_tailored_resume(tailored_with_fake_skills, self.cand_profile)
        languages = validated["skills"]["languages"]
        frameworks = validated["skills"]["frameworks"]
        
        self.assertIn("Python", languages)
        self.assertIn("SQL", languages)
        self.assertNotIn("Rust", languages)
        self.assertNotIn("Golang", languages)
        self.assertNotIn("Spring Boot", frameworks)

    def test_2_projects_and_experience_validation_rejects_unknown_entries(self):
        tailored_with_fake_entries = {
            "header": {"name": "Jane Doe"},
            "experience": [
                {"company": "Tech Corp", "role": "Intern", "bullets": ["Valid experience"]},
                {"company": "NASA", "role": "Senior Engineer", "bullets": ["Fabricated company"]}
            ],
            "projects": [
                {"name": "AI Search Engine", "bullets": ["Valid project"]},
                {"name": "Secret Quantum Computer", "bullets": ["Fabricated project"]}
            ]
        }
        validated = ai.validate_tailored_resume(tailored_with_fake_entries, self.cand_profile)
        exp_companies = [e["company"] for e in validated["experience"]]
        proj_names = [p["name"] for p in validated["projects"]]
        
        self.assertIn("Tech Corp", exp_companies)
        self.assertNotIn("NASA", exp_companies)
        self.assertIn("AI Search Engine", proj_names)
        self.assertNotIn("Secret Quantum Computer", proj_names)

    def test_3_unsupported_metrics_rejected(self):
        tailored_with_fake_metrics = {
            "header": {"name": "Jane Doe"},
            "experience": [{
                "company": "Tech Corp",
                "bullets": [
                    "Optimized backend SQL queries, improving response times by 25%.", # Valid (25%)
                    "Increased company revenue by $10M and 99% growth." # Fabricated metrics ($10M, 99%)
                ]
            }],
            "projects": [{
                "name": "AI Search Engine",
                "bullets": ["Processed over 500+ document queries."] # Valid (500+)
            }]
        }
        validated = ai.validate_tailored_resume(tailored_with_fake_metrics, self.cand_profile)
        bullets = validated["experience"][0]["bullets"]
        
        # The bullet with fake metric 99% should be rejected/dropped
        self.assertEqual(len(bullets), 1)
        self.assertIn("25%", bullets[0])

    def test_4_summary_sanitization_removes_fluff_and_unsupported_seniority(self):
        tailored_with_fluff = {
            "header": {"name": "Jane Doe"},
            "summary": "Highly motivated and passionate seasoned expert AI engineer with world-class skills."
        }
        validated = ai.validate_tailored_resume(tailored_with_fluff, self.cand_profile)
        summary = validated["summary"]
        
        self.assertNotIn("highly motivated", summary.lower())
        self.assertNotIn("seasoned expert", summary.lower())
        self.assertNotIn("world-class", summary.lower())
        self.assertIn("Python", summary)

    def test_5_generated_latex_remains_valid(self):
        tailored = ai.validate_tailored_resume({
            "header": {"name": "Jane Doe"},
            "summary": "Computer Science candidate with hands-on technical experience in Python, SQL.",
            "skills": {"languages": ["Python", "SQL"], "frameworks": ["Flask"], "tools": ["Git"]}
        }, self.cand_profile)
        
        latex_code = resume.render_latex(tailored)
        self.assertIn(r"\begin{document}", latex_code)
        self.assertIn(r"\end{document}", latex_code)
        self.assertIn("Jane Doe", latex_code)
        self.assertIn("Python", latex_code)

if __name__ == "__main__":
    unittest.main()
