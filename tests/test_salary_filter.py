import unittest
from sources.base import normalize_salary
from jobs import is_hard_filtered

class TestSalaryFilter(unittest.TestCase):

    def test_salary_normalization_inr(self):
        # Monthly INR
        m1, t1 = normalize_salary("₹50,000/month")
        self.assertEqual(m1, 50000)
        self.assertIn("50,000", t1)

        # 50k/pm
        m2, t2 = normalize_salary("50k/pm")
        self.assertEqual(m2, 50000)

        # 6 LPA
        m3, t3 = normalize_salary("₹6 LPA")
        self.assertEqual(m3, 50000)
        self.assertIn("LPA", t3)

    def test_salary_normalization_foreign_currency(self):
        # Foreign currency preservation
        m1, t1 = normalize_salary("$30/hour")
        self.assertIsNone(m1)
        self.assertEqual(t1, "$30/hour")

        m2, t2 = normalize_salary("$5,000/month")
        self.assertIsNone(m2)
        self.assertEqual(t2, "$5,000/month")

    def test_salary_normalization_undisclosed(self):
        m1, t1 = normalize_salary(None, "No salary listed in description")
        self.assertIsNone(m1)
        self.assertEqual(t1, "Not disclosed")

    def test_salary_hard_filtering(self):
        prefs_min_30k = {
            "preferred_roles": ["Software Engineer"],
            "minimum_salary": 30000,
            "include_undisclosed_salary": True
        }

        # 1. Job below minimum (₹20k < ₹30k) -> REJECTED
        job_low = {
            "title": "Software Engineer Intern",
            "salary": "₹20,000/month",
            "description": "Python dev position paying ₹20,000/month"
        }
        filtered, reason = is_hard_filtered(job_low, prefs_min_30k, {})
        self.assertTrue(filtered)
        self.assertIn("below minimum threshold", reason)

        # 2. Job at/above minimum (₹50k >= ₹30k) -> ACCEPTED
        job_high = {
            "title": "Software Engineer Intern",
            "salary": "₹50,000/month",
            "description": "Python position paying ₹50,000/month"
        }
        filtered2, _ = is_hard_filtered(job_high, prefs_min_30k, {})
        self.assertFalse(filtered2)

        # 3. Foreign currency position ($30/hour) -> ACCEPTED (not rejected by INR min)
        job_usd = {
            "title": "Software Engineer Intern",
            "salary": "$30/hour",
            "description": "Remote US position paying $30/hour"
        }
        filtered3, _ = is_hard_filtered(job_usd, prefs_min_30k, {})
        self.assertFalse(filtered3)

        # 4. Undisclosed salary when include_undisclosed = True -> ACCEPTED
        job_unknown = {
            "title": "Software Engineer Intern",
            "salary": None,
            "description": "Engineering intern position."
        }
        filtered4, _ = is_hard_filtered(job_unknown, prefs_min_30k, {})
        self.assertFalse(filtered4)

        # 5. Undisclosed salary when include_undisclosed = False -> REJECTED
        prefs_strict = {
            "preferred_roles": ["Software Engineer"],
            "minimum_salary": 30000,
            "include_undisclosed_salary": False
        }
        filtered5, reason5 = is_hard_filtered(job_unknown, prefs_strict, {})
        self.assertTrue(filtered5)
        self.assertIn("not disclosed", reason5)

if __name__ == '__main__':
    unittest.main()
