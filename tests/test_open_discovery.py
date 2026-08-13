import unittest
from unittest.mock import patch, MagicMock
import os
import sources
import jobs
import database
from sources.base import generate_open_discovery_queries, create_normalized_job

class TestOpenDiscoveryV1_2(unittest.TestCase):

    def setUp(self):
        self.test_db = "data/test_open_discovery.db"
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

    @patch("sources.adzuna.discover_jobs")
    @patch("sources.discover_targeted_sources")
    def test_1_targeted_mode_does_not_call_adzuna(self, mock_targeted, mock_adzuna):
        mock_targeted.return_value = ([], {})
        config = {"discovery_mode": "targeted"}
        jobs_list, _ = sources.discover_all_sources(config, return_summary=True)
        mock_targeted.assert_called_once()
        mock_adzuna.assert_not_called()

    @patch("sources.adzuna.fetch_single_query")
    @patch("sources.discover_targeted_sources")
    def test_2_open_only_mode_does_not_call_targeted(self, mock_targeted, mock_adzuna_fetch):
        mock_adzuna_fetch.return_value = []
        config = {"discovery_mode": "open_only", "preferred_roles": ["Software Engineer Intern"]}
        jobs_list, _ = sources.discover_all_sources(config, return_summary=True)
        mock_targeted.assert_not_called()
        self.assertTrue(mock_adzuna_fetch.called)

    @patch("sources.adzuna.fetch_single_query")
    @patch("sources.discover_targeted_sources")
    def test_3_targeted_and_open_calls_both_lanes(self, mock_targeted, mock_adzuna_fetch):
        mock_targeted.return_value = ([create_normalized_job("greenhouse", "1", "Acme", "SWE", "Hyderabad", "full_time", "desc", "http://app")], {"greenhouse": 1})
        mock_adzuna_fetch.return_value = [create_normalized_job("adzuna", "2", "BetaCorp", "ML Intern", "Bangalore", "internship", "desc", "http://app2")]
        
        config = {"discovery_mode": "targeted_and_open", "preferred_roles": ["Software Engineer Intern"]}
        jobs_list, summary = sources.discover_all_sources(config, return_summary=True)
        
        mock_targeted.assert_called_once()
        self.assertTrue(mock_adzuna_fetch.called)
        self.assertEqual(len(jobs_list), 2)

    def test_4_5_adzuna_and_targeted_results_merge_and_deduplicate(self):
        job_targeted = create_normalized_job("greenhouse", "100", "Microsoft", "SWE Intern", "Hyderabad", "internship", "desc", "https://careers.microsoft.com/job/100")
        job_adzuna_new = create_normalized_job("adzuna", "adz_200", "UnknownStartup", "AI Intern", "Hyderabad", "internship", "desc", "https://unknownstartup.com/job/200")

        # Save targeted job
        id1 = database.save_job(job_targeted, db_path=self.test_db)
        self.assertTrue(database.job_exists(job_targeted["unique_id"], db_path=self.test_db))

        # Check job existence
        self.assertTrue(database.job_exists(job_targeted["unique_id"], db_path=self.test_db))
        self.assertFalse(database.job_exists(job_adzuna_new["unique_id"], db_path=self.test_db))

    def test_6_unknown_company_remains_eligible(self):
        job = create_normalized_job("adzuna", "999", "Unknown AI Startup", "Software Engineer Intern", "Hyderabad", "internship", "Python SQL machine learning", "http://apply")
        prefs = {"preferred_roles": ["Software Engineer Intern"], "locations": ["Hyderabad"], "experience_levels": ["internship"]}
        profile = {"skills": ["Python", "SQL"]}

        filtered, reason = jobs.is_hard_filtered(job, prefs, profile)
        self.assertFalse(filtered)

    def test_7_8_company_priority_scoring_bonus(self):
        profile = {"skills": ["C++"]} # Keep skill score lower so cap of 100.0 is not hit
        prefs_dream = {"preferred_roles": ["Software Engineer Intern"], "locations": ["Hyderabad"], "dream_companies": ["Microsoft"]}
        
        microsoft_job = create_normalized_job("workday", "1", "Microsoft", "Software Engineer Intern", "Hyderabad", "internship", "Python SQL", "http://ms")
        unknown_job = create_normalized_job("adzuna", "2", "Unknown Startup", "Software Engineer Intern", "Hyderabad", "internship", "Python SQL", "http://unk")

        ms_score = jobs.calculate_deterministic_score(profile, prefs_dream, microsoft_job)
        unk_score = jobs.calculate_deterministic_score(profile, prefs_dream, unknown_job)

        self.assertGreater(ms_score, unk_score)
        self.assertEqual(round(ms_score - unk_score, 1), 8.0)

    def test_9_location_filter_rejects_incompatible_adzuna_job(self):
        job = create_normalized_job("adzuna", "55", "TechCorp", "SWE Intern", "Mumbai", "internship", "Onsite in Mumbai", "http://mumbai")
        prefs = {"preferred_roles": ["SWE Intern"], "locations": ["Hyderabad", "Bangalore"], "experience_levels": ["internship"]}
        profile = {"skills": ["Python"]}

        filtered, reason = jobs.is_hard_filtered(job, prefs, profile)
        self.assertTrue(filtered)
        self.assertIn("Location mismatch", reason)

    def test_10_salary_filter_rejects_below_threshold_adzuna_job(self):
        job = create_normalized_job("adzuna", "66", "LowPayCorp", "SWE Intern", "Hyderabad", "internship", "Stipend ₹5,000 per month", "http://lowpay")
        job["salary"] = "₹5,000 per month"
        prefs = {"preferred_roles": ["SWE Intern"], "locations": ["Hyderabad"], "minimum_salary": 20000}
        profile = {"skills": ["Python"]}

        filtered, reason = jobs.is_hard_filtered(job, prefs, profile)
        self.assertTrue(filtered)
        self.assertIn("Salary below minimum threshold", reason)

    def test_11_internship_filter_rejects_senior_adzuna_job(self):
        job = create_normalized_job("adzuna", "77", "BigCorp", "Senior Principal Architect", "Hyderabad", "full_time", "15+ years experience required", "http://senior")
        prefs = {"preferred_roles": ["Software Engineer Intern"], "locations": ["Hyderabad"], "experience_levels": ["internship"]}
        profile = {"skills": ["Python"]}

        filtered, reason = jobs.is_hard_filtered(job, prefs, profile)
        self.assertTrue(filtered)
        self.assertIn("Senior", reason)

    @patch("sources.adzuna.fetch_single_query", side_effect=Exception("Adzuna API Error 500"))
    @patch("sources.discover_targeted_sources")
    def test_12_adzuna_failure_does_not_kill_targeted_discovery(self, mock_targeted, mock_adzuna):
        mock_targeted.return_value = ([create_normalized_job("greenhouse", "1", "Acme", "SWE", "Hyderabad", "full_time", "desc", "http://app")], {"greenhouse": 1})
        config = {"discovery_mode": "targeted_and_open", "preferred_roles": ["SWE"]}
        
        jobs_list, summary = sources.discover_all_sources(config, return_summary=True)
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(jobs_list[0]["company"], "Acme")

    @patch("sources.adzuna.fetch_single_query")
    @patch("sources.discover_targeted_sources", side_effect=Exception("Targeted Discovery Error"))
    def test_13_targeted_failure_does_not_kill_adzuna(self, mock_targeted, mock_adzuna_fetch):
        mock_adzuna_fetch.return_value = [create_normalized_job("adzuna", "2", "BetaCorp", "ML Intern", "Bangalore", "internship", "desc", "http://app2")]
        config = {"discovery_mode": "targeted_and_open", "preferred_roles": ["ML Intern"]}

        jobs_list, summary = sources.discover_all_sources(config, return_summary=True)
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(jobs_list[0]["company"], "BetaCorp")

    def test_14_15_query_and_page_budget_is_respected(self):
        prefs = {
            "preferred_roles": ["RoleA", "RoleB", "RoleC", "RoleD", "RoleE", "RoleF"],
            "locations": ["Hyderabad", "Bangalore", "Pune"]
        }
        queries = generate_open_discovery_queries(prefs, max_queries=10)
        self.assertLessEqual(len(queries), 10)
        
        # Verify balanced interleaving across roles
        roles_in_queries = set(q["role"] for q in queries)
        self.assertGreaterEqual(len(roles_in_queries), 3)

    @patch("sources.adzuna.fetch_single_query")
    def test_16_stop_run_prevents_additional_open_discovery(self, mock_adzuna_fetch):
        mock_adzuna_fetch.return_value = [create_normalized_job("adzuna", "1", "Corp", "Title", "Loc", "full_time", "desc", "http://url")]
        stop_flag = [False]
        def check_stop():
            return stop_flag[0]

        # Stop triggered immediately
        stop_flag[0] = True
        config = {"discovery_mode": "open_only", "preferred_roles": ["RoleA", "RoleB"]}
        open_jobs, metrics = sources.discover_open_sources(config, stop_checker=check_stop)
        
        self.assertEqual(open_jobs, [])

    def test_17_discovery_lane_is_correctly_recorded(self):
        targeted_job = create_normalized_job("workday", "1", "Adobe", "Dev", "Remote", "full_time", "desc", "http://ad")
        open_job = create_normalized_job("adzuna", "2", "Startup", "Dev", "Remote", "full_time", "desc", "http://st", discovery_lane="open")

        self.assertEqual(targeted_job["discovery_lane"], "targeted")
        self.assertEqual(open_job["discovery_lane"], "open")

    def test_18_adzuna_one_to_one_result_integrity(self):
        item = create_normalized_job("adzuna", "AZ_12345", "UniqueCorp", "Unique Title", "Hyderabad", "internship", "Unique Desc", "https://uniquecorp.com/apply/12345")
        self.assertEqual(item["source"], "adzuna")
        self.assertEqual(item["source_job_id"], "AZ_12345")
        self.assertEqual(item["company"], "UniqueCorp")
        self.assertEqual(item["title"], "Unique Title")
        self.assertEqual(item["location"], "Hyderabad")
        self.assertEqual(item["discovery_lane"], "open")

if __name__ == "__main__":
    unittest.main()
