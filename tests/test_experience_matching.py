import unittest
import jobs

class TestExperienceMatching(unittest.TestCase):
    def setUp(self):
        self.cand_profile = {"skills": ["Python", "SQL", "Flask"]}

    def test_1_senior_rejected_for_internship_and_entry(self):
        pref = {
            "preferred_roles": ["AI/ML Engineer Intern", "Software Engineer"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "Senior AI Engineer",
            "company": "GitLab",
            "description": "Senior role with 8+ years experience."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertTrue(filtered)
        self.assertIn("Senior", reason)

    def test_2_internship_accepted_for_internship_and_entry(self):
        pref = {
            "preferred_roles": ["AI/ML Engineer Intern"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "AI Engineer Intern",
            "company": "Tech Corp",
            "description": "Internship working with Python."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)

    def test_3_unknown_experience_level_retained(self):
        pref = {
            "preferred_roles": ["Software Engineer"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "Software Engineer",
            "company": "Acme Inc",
            "employment_type": "unknown",
            "description": "General software developer role."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)
        
        score = jobs.calculate_deterministic_score(self.cand_profile, pref, job)
        self.assertTrue(score > 0)

    def test_4_internship_accepted_for_internship_only(self):
        pref = {
            "preferred_roles": ["Software Engineer Intern"],
            "experience_levels": ["Internship"]
        }
        job = {
            "title": "Software Engineer Intern",
            "company": "OpenAI",
            "employment_type": "internship",
            "description": "Summer internship."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)

    def test_5_entry_level_accepted(self):
        pref = {
            "preferred_roles": ["Software Engineer"],
            "experience_levels": ["Entry Level"]
        }
        job = {
            "title": "Junior Software Engineer",
            "company": "Startup Co",
            "employment_type": "full_time",
            "description": "Entry level junior role."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)

    def test_6_staff_engineer_rejected_for_entry_level_only(self):
        pref = {
            "preferred_roles": ["Software Engineer"],
            "experience_levels": ["Entry Level"]
        }
        job = {
            "title": "Staff Software Engineer",
            "company": "Big Tech",
            "description": "Staff level position."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertTrue(filtered)

    def test_7_role_similarity_high_but_eligibility_false(self):
        pref = {
            "preferred_roles": ["AI/ML Engineer Intern"],
            "experience_levels": ["Internship"]
        }
        job = {
            "title": "Senior AI Engineer",
            "company": "AI Corp",
            "description": "Looking for AI Engineer."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertTrue(filtered)

    def test_8_fulltime_non_entry_rejected_when_internship_and_entry_requested(self):
        # Exact failure case from live test: Notion / Ramp Software Engineer - FullTime
        pref = {
            "preferred_roles": ["Software Engineer Intern", "AI/ML Engineer Intern"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "Software Engineer",
            "company": "Notion",
            "employment_type": "full_time",
            "description": "Building product features."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertTrue(filtered)
        self.assertIn("Explicit full-time", reason)

    def test_9_fulltime_with_entry_title_accepted_when_entry_requested(self):
        pref = {
            "preferred_roles": ["Software Engineer Intern", "AI/ML Engineer Intern"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "Junior Software Engineer",
            "company": "Ramp",
            "employment_type": "full_time",
            "description": "Entry level engineering role."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)

    def test_10_unknown_employment_type_not_rejected(self):
        pref = {
            "preferred_roles": ["Software Engineer Intern", "AI/ML Engineer Intern"],
            "experience_levels": ["Internship", "Entry Level"]
        }
        job = {
            "title": "Software Engineer",
            "company": "Greenhouse Comp",
            "employment_type": "unknown",
            "description": "No employment metadata provided."
        }
        filtered, reason = jobs.is_hard_filtered(job, pref, self.cand_profile)
        self.assertFalse(filtered)

if __name__ == "__main__":
    unittest.main()
