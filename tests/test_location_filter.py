import unittest
from jobs import is_hard_filtered

class TestLocationFilter(unittest.TestCase):

    def test_1_user_selects_hyderabad_job_hyderabad(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = {"title": "Software Engineer", "location": "Hyderabad", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, f"Should keep job in preferred city. Reason: {reason}")

    def test_2_user_selects_hyderabad_job_mumbai_onsite(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = {"title": "Software Engineer", "location": "Mumbai, Maharashtra - Onsite", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertTrue(filtered, "Should reject job in known incompatible onsite location")

    def test_3_user_selects_hyderabad_remote_job_remote(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad", "Remote"]}
        job = {"title": "Software Engineer", "location": "Remote", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, f"Should keep remote job if remote is selected. Reason: {reason}")

    def test_4_user_selects_hyderabad_only_job_remote(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = {"title": "Software Engineer", "location": "Remote", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertTrue(filtered, "Should reject remote job if remote is NOT selected")

    def test_5_user_selects_hyderabad_bangalore_job_bengaluru(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad", "Bangalore"]}
        job = {"title": "Software Engineer", "location": "Bengaluru", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, f"Should keep Bengaluru job if Bangalore is preferred. Reason: {reason}")

    def test_6_user_selects_hyderabad_bangalore_job_pune_onsite(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad", "Bangalore"]}
        job = {"title": "Software Engineer", "location": "Pune - On-Site", "description": ""}
        filtered, reason = is_hard_filtered(job, prefs, {})
        self.assertTrue(filtered, "Should reject Pune job if not in preferred cities")

    def test_7_user_selects_hyderabad_job_location_unknown(self):
        # empty / unknown / not specified should be kept
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job1 = {"title": "Software Engineer", "location": "", "description": ""}
        filtered1, _ = is_hard_filtered(job1, prefs, {})
        self.assertFalse(filtered1, "Should keep empty location job")

        job2 = {"title": "Software Engineer", "location": "Not Specified", "description": ""}
        filtered2, _ = is_hard_filtered(job2, prefs, {})
        self.assertFalse(filtered2, "Should keep 'Not Specified' location job")

        job3 = {"title": "Software Engineer", "location": "unknown", "description": ""}
        filtered3, _ = is_hard_filtered(job3, prefs, {})
        self.assertFalse(filtered3, "Should keep 'unknown' location job")

    def test_8_user_selects_no_locations_job_mumbai_onsite(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": []}
        job = {"title": "Software Engineer", "location": "Mumbai - Onsite", "description": ""}
        filtered, _ = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, "Should not apply filter if preferences are empty")

    def test_9_hybrid_hyderabad_with_hyderabad_selected(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = {"title": "Software Engineer", "location": "Hybrid - Hyderabad", "description": ""}
        filtered, _ = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, "Should keep hybrid job in preferred city")

    def test_10_hybrid_mumbai_with_hyderabad_selected(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Hyderabad"]}
        job = {"title": "Software Engineer", "location": "Hybrid, Mumbai", "description": ""}
        filtered, _ = is_hard_filtered(job, prefs, {})
        self.assertTrue(filtered, "Should reject hybrid job in incompatible city")

    def test_11_location_matching_is_case_insensitive(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["hyderabad"]}
        job = {"title": "Software Engineer", "location": "HYDERABAD", "description": ""}
        filtered, _ = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, "Case-insensitive match should keep job")

    def test_12_bangalore_bengaluru_alias_works(self):
        prefs = {"preferred_roles": ["Software Engineer"], "locations": ["Bangalore"]}
        job = {"title": "Software Engineer", "location": "Bengaluru, Karnataka", "description": ""}
        filtered, _ = is_hard_filtered(job, prefs, {})
        self.assertFalse(filtered, "Bangalore/Bengaluru alias should match and keep job")

        # reverse alias check
        prefs2 = {"preferred_roles": ["Software Engineer"], "locations": ["bengaluru"]}
        job2 = {"title": "Software Engineer", "location": "Bangalore, India", "description": ""}
        filtered2, _ = is_hard_filtered(job2, prefs2, {})
        self.assertFalse(filtered2, "Bengaluru/Bangalore alias should match and keep job")

if __name__ == '__main__':
    unittest.main()
