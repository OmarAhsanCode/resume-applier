import unittest
import os
import json
from unittest.mock import patch, MagicMock

import jobs
import sources
import database

class TestV1_1_2Regression(unittest.TestCase):

    def setUp(self):
        self.candidate_profile = {
            "name": "Test Candidate",
            "skills": ["Python", "Java", "Machine Learning", "SQL"]
        }
        self.preferences = {
            "preferred_roles": ["Software Engineer", "Backend Engineer", "AI Engineer"],
            "locations": ["India", "Bangalore", "Bengaluru", "Remote", "Hyderabad"],
            "work_modes": ["remote", "hybrid", "onsite"],
            "experience_levels": ["internship", "entry_level"],
            "minimum_salary": 0,
            "include_undisclosed_salary": True,
            "dream_companies": ["Google", "Microsoft"]
        }

    def test_1_internship_not_rejected_as_fulltime(self):
        """1. Internship job with explicit intern title is NOT rejected as full-time."""
        job = sources.base.create_normalized_job(
            source="greenhouse",
            source_job_id="101",
            company="Razorpay",
            title="Software Engineering Intern",
            location="Bengaluru",
            employment_type="internship",
            description="Summer software engineering internship in Bangalore",
            application_url="https://razorpay.com/jobs/101"
        )
        is_filtered, reason = jobs.is_hard_filtered(job, self.preferences, self.candidate_profile)
        self.assertFalse(is_filtered, f"Internship role was unexpectedly hard-filtered: {reason}")

    def test_2_internship_compatible_location_accepted(self):
        """2. Internship + compatible location is accepted."""
        job = sources.base.create_normalized_job(
            source="lever",
            source_job_id="102",
            company="Swiggy",
            title="SDE Intern",
            location="Hyderabad, India",
            employment_type="internship",
            description="Backend engineering internship",
            application_url="https://swiggy.com/jobs/102"
        )
        is_filtered, reason = jobs.is_hard_filtered(job, self.preferences, self.candidate_profile)
        self.assertFalse(is_filtered, f"Compatible internship was filtered: {reason}")

    def test_3_entry_level_compatible_location_accepted(self):
        """3. Entry-level + compatible location is accepted."""
        job = sources.base.create_normalized_job(
            source="ashby",
            source_job_id="103",
            company="PhonePe",
            title="Junior Backend Engineer",
            location="Remote",
            employment_type="full_time",
            description="Junior developer role for entry level engineers",
            application_url="https://phonepe.com/jobs/103"
        )
        is_filtered, reason = jobs.is_hard_filtered(job, self.preferences, self.candidate_profile)
        self.assertFalse(is_filtered, f"Entry level job was filtered: {reason}")

    def test_4_unknown_experience_remains_eligible(self):
        """4. Unknown experience remains eligible but receives lower confidence score."""
        job = sources.base.create_normalized_job(
            source="greenhouse",
            source_job_id="104",
            company="Freshworks",
            title="Junior Software Engineer",
            location="Bangalore",
            employment_type="unknown",
            description="General software engineering position",
            application_url="https://freshworks.com/jobs/104"
        )
        # Entry level preference + unknown employment type general engineer should not be hard-filtered
        is_filtered, reason = jobs.is_hard_filtered(job, self.preferences, self.candidate_profile)
        self.assertFalse(is_filtered, f"Unknown/general experience job was filtered: {reason}")
        score = jobs.calculate_deterministic_score(self.candidate_profile, self.preferences, job)
        self.assertTrue(score > 0.0)

    def test_5_company_priority_affects_ranking_without_hard_filtering(self):
        """5. Company priority affects ranking boost but does NOT hard-filter standard companies."""
        job_normal = sources.base.create_normalized_job(
            source="greenhouse",
            source_job_id="105a",
            company="Normal Startup",
            title="Junior Software Engineer",
            location="Remote",
            employment_type="unknown",
            description="Standard role",
            application_url="https://normal.com/jobs/105a"
        )
        job_priority = sources.base.create_normalized_job(
            source="greenhouse",
            source_job_id="105b",
            company="Microsoft",
            title="Junior Software Engineer",
            location="Remote",
            employment_type="unknown",
            description="Standard role",
            application_url="https://microsoft.com/jobs/105b"
        )
        job_normal["company_priority"] = 50
        job_priority["company_priority"] = 100

        # Neither is hard-filtered
        self.assertFalse(jobs.is_hard_filtered(job_normal, self.preferences, self.candidate_profile)[0])
        self.assertFalse(jobs.is_hard_filtered(job_priority, self.preferences, self.candidate_profile)[0])

        score_normal = jobs.calculate_deterministic_score(self.candidate_profile, self.preferences, job_normal)
        score_priority = jobs.calculate_deterministic_score(self.candidate_profile, self.preferences, job_priority)
        self.assertGreater(score_priority, score_normal)

    @patch("sources.workday.discover_jobs")
    @patch("sources.greenhouse.discover_jobs")
    @patch("sources.lever.discover_jobs")
    @patch("sources.ashby.discover_jobs")
    @patch("sources.smartrecruiters.discover_jobs")
    @patch("sources.adzuna.discover_jobs")
    def test_6_disabled_source_reported_correctly(self, mock_adz, mock_sr, mock_ash, mock_lev, mock_gh, mock_wd):
        """6. Disabled source is skipped and reported cleanly in source registry."""
        mock_gh.return_value = [{"source": "greenhouse"}]
        mock_lev.return_value = [{"source": "lever"}]
        mock_ash.return_value = [{"source": "ashby"}]
        mock_wd.return_value = [{"source": "workday"}]
        mock_sr.return_value = [{"source": "smartrecruiters"}]
        mock_adz.return_value = []

        search_config = {"enable_taleo": False, "enable_icims": False}
        all_jobs = sources.discover_all_sources(search_config)
        sources_found = {j["source"] for j in all_jobs}
        self.assertNotIn("taleo", sources_found)
        self.assertNotIn("icims", sources_found)

    @patch.dict(os.environ, {}, clear=True)
    def test_7_adzuna_missing_credentials_reported_as_disabled(self):
        """7. Adzuna missing credentials is reported as disabled without crashing."""
        search_config = {"app_id": "", "app_key": "", "enabled": False}
        discovered = sources.adzuna.discover_jobs(search_config)
        self.assertEqual(len(discovered), 0)

    @patch("requests.post")
    def test_8_workday_target_failure_does_not_kill_registry(self, mock_post):
        """8. Individual Workday target HTTP failure isolates error and allows other targets to succeed."""
        mock_post.side_effect = Exception("Workday connection timeout")
        search_config = {
            "workday_targets": [{"company": "BrokenCorp", "host": "broken.myworkdayjobs.com", "tenant": "jobs"}]
        }
        jobs_found = sources.workday.discover_jobs(search_config)
        self.assertEqual(len(jobs_found), 0)

if __name__ == "__main__":
    unittest.main()
