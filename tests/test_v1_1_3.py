import unittest
from unittest.mock import patch, MagicMock

import sources.adzuna
import sources.base

class TestV1_1_3AdzunaDataIntegrity(unittest.TestCase):

    def setUp(self):
        self.sample_raw_results = [
            {
                "id": "5775777688",
                "title": "Software Engineering INTERN",
                "company": {"display_name": "Microsoft Corporation"},
                "location": {"display_name": "India"},
                "redirect_url": "https://www.adzuna.in/details/5775777688",
                "description": "Microsoft internship role",
                "created": "2026-07-01T10:00:00Z"
            },
            {
                "id": "5816813291",
                "title": "Software Engineering Intern",
                "company": {"display_name": "Red Hat"},
                "location": {"display_name": "Pune, Maharashtra"},
                "redirect_url": "https://www.adzuna.in/details/5816813291",
                "description": "Red Hat internship role",
                "created": "2026-07-15T10:00:00Z"
            },
            {
                "id": "5806704614",
                "title": "Software Engineer- Intern",
                "company": {"display_name": "Blueberry Digital Labs"},
                "location": {"display_name": "Hyderabad, Telangana"},
                "redirect_url": "https://www.adzuna.in/details/5806704614",
                "description": "Blueberry internship role",
                "created": "2026-07-19T10:00:00Z"
            }
        ]

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_1_each_raw_result_retains_own_id(self, mock_get, mock_cfg):
        """1. Verify that each raw result retains its own unique Adzuna ID."""
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": self.sample_raw_results}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["source_job_id"], "5775777688")
        self.assertEqual(jobs[1]["source_job_id"], "5816813291")
        self.assertEqual(jobs[2]["source_job_id"], "5806704614")

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_2_each_raw_result_retains_own_company(self, mock_get, mock_cfg):
        """2. Verify that each raw result retains its own company display name without cross-item leak."""
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": self.sample_raw_results}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        self.assertEqual(jobs[0]["company"], "Microsoft Corporation")
        self.assertEqual(jobs[1]["company"], "Red Hat")
        self.assertEqual(jobs[2]["company"], "Blueberry Digital Labs")

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_3_each_raw_result_retains_own_url(self, mock_get, mock_cfg):
        """3. Verify that each raw result retains its own canonical URL."""
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": self.sample_raw_results}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        self.assertEqual(jobs[0]["job_url"], "https://www.adzuna.in/details/5775777688")
        self.assertEqual(jobs[1]["job_url"], "https://www.adzuna.in/details/5816813291")
        self.assertEqual(jobs[2]["job_url"], "https://www.adzuna.in/details/5806704614")

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_4_no_state_leakage_between_results(self, mock_get, mock_cfg):
        """4. Verify that two different raw results cannot accidentally share a unique_id due to state leakage."""
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": self.sample_raw_results}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        uids = [j["unique_id"] for j in jobs]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(uids[0], "adzuna:5775777688")
        self.assertEqual(uids[1], "adzuna:5816813291")
        self.assertEqual(uids[2], "adzuna:5806704614")

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_5_duplicate_raw_results_handled_deterministically(self, mock_get, mock_cfg):
        """5. Verify that duplicate raw items produce identical unique_ids for deduplication."""
        duplicate_results = [self.sample_raw_results[0], self.sample_raw_results[0]]
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": duplicate_results}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["unique_id"], jobs[1]["unique_id"])

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_6_canonical_adzuna_urls_preserved(self, mock_get, mock_cfg):
        """6. Verify that canonical Adzuna URLs are normalized and preserved accurately."""
        raw_item = {
            "id": "99999",
            "title": "Software Engineer",
            "company": {"display_name": "Acme Corp"},
            "location": {"display_name": "Remote"},
            "redirect_url": "https://www.adzuna.in/details/99999?utm_source=test&ref=123",
            "description": "Test job"
        }
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [raw_item]}
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs()
        self.assertEqual(jobs[0]["job_url"], "https://www.adzuna.in/details/99999")
        self.assertEqual(jobs[0]["apply_url"], "https://www.adzuna.in/details/99999")

    @patch("sources.adzuna.load_adzuna_config")
    @patch("requests.get")
    def test_7_source_ids_stable_across_multiple_calls(self, mock_get, mock_cfg):
        """7. Verify that source IDs remain stable across multiple discovery executions."""
        mock_cfg.return_value = {"app_id": "test_id", "app_key": "test_key", "country": "in", "enabled": True}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": self.sample_raw_results}
        mock_get.return_value = mock_resp

        jobs_call1 = sources.adzuna.discover_jobs()
        jobs_call2 = sources.adzuna.discover_jobs()
        
        ids1 = [j["source_job_id"] for j in jobs_call1]
        ids2 = [j["source_job_id"] for j in jobs_call2]
        self.assertEqual(ids1, ids2)

if __name__ == "__main__":
    unittest.main()
