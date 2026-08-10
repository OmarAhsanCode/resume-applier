import unittest
import ai

class TestAI(unittest.TestCase):
    def test_parse_resume_mock(self):
        sample_cv_text = """
        John Alex Smith
        john.smith@example.com | +1 555-0199 | linkedin.com/in/johnsmith
        
        EDUCATION
        B.Tech in Computer Science, State University, 2026. CGPA: 8.8/10
        
        EXPERIENCE
        Software Engineer Intern at Acme Corp (2025-05 to 2025-08)
        - Developed Python scripts and REST APIs using Flask.
        - Wrote SQL queries and automated reporting.
        
        SKILLS
        Python, Java, SQL, Flask, Git, Machine Learning
        """
        profile = ai.parse_resume(sample_cv_text)
        self.assertIsNotNone(profile)
        self.assertIn("name", profile)
        self.assertEqual(profile["email"], "john.smith@example.com")
        self.assertTrue(any("Python" in s for s in profile["skills"]))

    def test_analyze_job(self):
        cand_profile = {
            "name": "Jane Doe",
            "skills": ["Python", "SQL", "Flask"],
            "experience": [{"role": "Python Developer"}]
        }
        job_dict = {
            "company": "DataCorp",
            "title": "Junior Python Developer",
            "description": "Looking for a Junior Python Developer skilled in Python, SQL, and Git."
        }
        analysis = ai.analyze_job(cand_profile, job_dict)
        self.assertIn("score", analysis)
        self.assertIn("recommendation", analysis)
        self.assertTrue(analysis["score"] >= 50)

    def test_tailor_resume(self):
        cand_profile = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python", "SQL", "Flask"],
            "education": [{"degree": "BS CS", "institution": "Tech Uni", "graduation_year": 2026}]
        }
        job_dict = {"company": "DataCorp", "title": "Python Engineer", "description": "Python job"}
        analysis = {"score": 88, "recommendation": "strong_match"}
        settings = {"section_order": ["summary", "education", "experience", "projects", "skills"]}
        
        tailored = ai.tailor_resume(cand_profile, job_dict, analysis, settings)
        self.assertIsNotNone(tailored)
        self.assertEqual(tailored["header"]["name"], "Jane Doe")
        self.assertIn("summary", tailored)

if __name__ == "__main__":
    unittest.main()
