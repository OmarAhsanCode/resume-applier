import unittest
import os
import json
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

import company_manager
import company_discovery
import sources.workday
import sources.greenhouse
import sources.lever
import sources.ashby
import sources.smartrecruiters
from sources.browser_careers import discover_jobs_from_career_page, AccessRestrictedError

class TestWatchlistVerify(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for config test files
        self.test_dir = tempfile.mkdtemp()
        self.companies_path = os.path.join(self.test_dir, "companies.json")
        self.sources_path = os.path.join(self.test_dir, "sources.json")
        
        # Patch paths in company_manager and sync_playwright
        self.playwright_patch = patch("sources.browser_careers.sync_playwright", None)
        self.path_patches = [
            patch("company_manager.COMPANIES_CONFIG_PATH", self.companies_path),
            patch("company_manager.SOURCES_CONFIG_PATH", self.sources_path),
            self.playwright_patch
        ]
        for p in self.path_patches:
            p.start()

    def tearDown(self):
        for p in self.path_patches:
            p.stop()
        shutil.rmtree(self.test_dir)

    def write_companies(self, data):
        with open(self.companies_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def write_sources(self, data):
        with open(self.sources_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def test_preloaded_migration_unverified(self):
        # 1. Preloaded company with no verification metadata or legacy "N/A" -> unverified.
        companies_data = [
            {
                "company": "Razorpay",
                "careers_url": "https://razorpay.com/jobs",
                "source": "greenhouse",
                "source_identifier": "razorpay",
                "enabled": True,
                "verified": True,
                "verification_status": "verified",
                "jobs_found": 0,
                "last_verified": "N/A"
            },
            {
                "company": "GitLab",
                "careers_url": "https://gitlab.com/jobs",
                "source": "greenhouse",
                "source_identifier": "gitlab",
                "enabled": True,
                "verified": True,
                "verification_status": "verified",
                "jobs_found": 18,
                "last_verified": "2026-08-10 12:00:00" # Legacy valid verified info should be preserved
            }
        ]
        self.write_companies(companies_data)
        
        loaded = company_manager.load_companies(self.companies_path)
        
        # Razorpay should be migrated to unverified
        razorpay = next(c for c in loaded if c["company"] == "Razorpay")
        self.assertFalse(razorpay["verified"])
        self.assertEqual(razorpay["verification_status"], "unverified")
        self.assertIsNone(razorpay["jobs_found"])
        self.assertIsNone(razorpay["jobs_available"])
        self.assertIsNone(razorpay["jobs_retrieved"])
        self.assertIsNone(razorpay["last_verified"])
        
        # GitLab should be preserved
        gitlab = next(c for c in loaded if c["company"] == "GitLab")
        self.assertTrue(gitlab["verified"])
        self.assertEqual(gitlab["verification_status"], "verified")
        self.assertEqual(gitlab["jobs_found"], 18)
        self.assertEqual(gitlab["last_verified"], "2026-08-10 12:00:00")

    @patch("company_discovery.requests.get")
    def test_verify_button_greenhouse_success(self, mock_get):
        # Mock Greenhouse API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [{"id": 1, "title": "Software Engineer"}]
        }
        mock_get.return_value = mock_response

        companies_data = [
            {
                "company": "Razorpay",
                "careers_url": "https://razorpay.com/jobs",
                "source": "greenhouse",
                "source_identifier": "razorpay",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None,
                "last_verified": None
            }
        ]
        self.write_companies(companies_data)
        self.write_sources({"greenhouse": []})

        # Run verification
        updated = company_manager.verify_company_config("Razorpay", self.companies_path, self.sources_path)
        
        self.assertTrue(updated["verified"])
        self.assertEqual(updated["verification_status"], "verified_api")
        self.assertEqual(updated["jobs_found"], 1)
        self.assertIsNotNone(updated["last_verified"])
        
        # Check source.json updated
        with open(self.sources_path, "r") as f:
            sources_cfg = json.load(f)
            self.assertIn("razorpay", sources_cfg.get("greenhouse", []))

    @patch("company_discovery.requests.get")
    def test_verify_button_greenhouse_zero_jobs(self, mock_get):
        # Mock Greenhouse API response with 0 jobs
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobs": []}
        mock_get.return_value = mock_response

        companies_data = [
            {
                "company": "Razorpay",
                "careers_url": "https://razorpay.com/jobs",
                "source": "greenhouse",
                "source_identifier": "razorpay",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None,
                "last_verified": None
            }
        ]
        self.write_companies(companies_data)

        updated = company_manager.verify_company_config("Razorpay", self.companies_path, self.sources_path)
        
        self.assertFalse(updated["verified"])
        self.assertEqual(updated["verification_status"], "no_jobs_found")
        self.assertEqual(updated["jobs_found"], 0)

    @patch("company_discovery.requests.get")
    def test_verify_button_failed(self, mock_get):
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response

        companies_data = [
            {
                "company": "Razorpay",
                "careers_url": "https://razorpay.com/jobs",
                "source": "greenhouse",
                "source_identifier": "razorpay",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None,
                "last_verified": None
            }
        ]
        self.write_companies(companies_data)

        updated = company_manager.verify_company_config("Razorpay", self.companies_path, self.sources_path)
        
        self.assertFalse(updated["verified"])
        self.assertEqual(updated["verification_status"], "verification_failed")
        self.assertIsNone(updated["jobs_found"]) # Does not invent job count

    @patch("company_discovery.requests.post")
    def test_workday_cxs_total_field(self, mock_post):
        # Mock Workday response where first page is 2 jobs but total is 1500
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 1500,
            "jobPostings": [
                {"title": "Job 1", "externalPath": "/job1"},
                {"title": "Job 2", "externalPath": "/job2"}
            ]
        }
        mock_post.return_value = mock_response

        cand = {
            "company_name": "Salesforce",
            "ats_platform": "workday",
            "ats_host": "salesforce.myworkdayjobs.com",
            "ats_tenant": "external",
            "careers_url": "https://careers.salesforce.com"
        }
        
        res = company_discovery.verify_discovered_source(cand)
        
        self.assertTrue(res["verified"])
        self.assertEqual(res["jobs_found"], 2)
        self.assertEqual(res["jobs_available"], 1500)
        self.assertEqual(res["jobs_retrieved"], 2)

    @patch("sources.workday.requests.post")
    def test_workday_pagination(self, mock_post):
        # Mock Workday pagination requests (page 1 returns 2 jobs, total 3; page 2 returns 1 job)
        r1 = MagicMock()
        r1.status_code = 200
        r1.json.return_value = {
            "total": 3,
            "jobPostings": [
                {"title": "Job 1", "externalPath": "/job1"},
                {"title": "Job 2", "externalPath": "/job2"}
            ]
        }
        
        r2 = MagicMock()
        r2.status_code = 200
        r2.json.return_value = {
            "total": 3,
            "jobPostings": [
                {"title": "Job 3", "externalPath": "/job3"}
            ]
        }
        
        mock_post.side_effect = [r1, r2]

        with patch("sources.workday.load_workday_config") as mock_cfg:
            mock_cfg.return_value = [{"company": "Adobe", "host": "adobe.myworkdayjobs.com", "tenant": "external"}]
            
            # Run discover jobs with small page size
            with patch.dict(os.environ, {"WORKDAY_PAGE_SIZE": "2", "WORKDAY_MAX_PAGES": "5"}):
                jobs = sources.workday.discover_jobs({"preferred_roles": ["Engineer"]})
                
                self.assertEqual(len(jobs), 3)
                self.assertEqual(jobs[0]["title"], "Job 1")
                self.assertEqual(jobs[2]["title"], "Job 3")

    @patch("company_discovery.requests.get")
    @patch("sources.browser_careers.sync_playwright")
    def test_browser_fallback_playwright_mock(self, mock_playwright, mock_get):
        # Mock careers page reachable via requests
        r_page = MagicMock()
        r_page.status_code = 200
        r_page.text = "<html><body>Join our team!</body></html>"
        mock_get.return_value = r_page

        # Mock Playwright structure
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.title.return_value = "Careers Page"
        mock_page.content.return_value = "<html><body>Join our team!</body></html>"
        
        # Mock link elements returned by query_selector_all
        mock_link = MagicMock()
        mock_link.get_attribute.return_value = "/careers/job/12345"
        mock_link.inner_text.return_value = "Senior Software Engineer"
        mock_page.query_selector_all.return_value = [mock_link]
        
        # Mock page.evaluate to return absolute URL
        mock_page.evaluate.return_value = "https://careers.company.com/careers/job/12345"

        # Initialize watchlist where API call will fail (e.g. returns 403)
        companies_data = [
            {
                "company": "Walmart",
                "careers_url": "https://careers.walmart.com",
                "source": "workday",
                "source_identifier": "walmart",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None,
                "last_verified": None
            }
        ]
        self.write_companies(companies_data)

        # Mock the Workday API probe to fail with 403
        with patch("company_discovery.requests.post") as mock_post:
            r_post = MagicMock()
            r_post.status_code = 403
            r_post.text = "Forbidden (Cloudflare challenge)"
            mock_post.return_value = r_post

            # Verify Company Config which should trigger Browser Fallback
            updated = company_manager.verify_company_config("Walmart", self.companies_path, self.sources_path)
            
            self.assertTrue(updated["verified"])
            self.assertEqual(updated["verification_status"], "verified_browser")
            self.assertEqual(updated["jobs_found"], 1)
            self.assertEqual(updated["access_strategy"], "browser")

    @patch("company_discovery.requests.get")
    @patch("sources.browser_careers.sync_playwright")
    def test_browser_fallback_restricted_captcha(self, mock_playwright, mock_get):
        # Mock careers page reachable
        r_page = MagicMock()
        r_page.status_code = 200
        r_page.text = "<html><body>Challenge</body></html>"
        mock_get.return_value = r_page

        # Mock Playwright to return a Cloudflare/CAPTCHA title
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        
        # Set Cloudflare challenge page signatures
        mock_page.title.return_value = "Just a moment..."
        mock_page.content.return_value = "<html><body>Please verify you are a human. Cloudflare</body></html>"

        companies_data = [
            {
                "company": "Walmart",
                "careers_url": "https://careers.walmart.com",
                "source": "workday",
                "source_identifier": "walmart",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None,
                "last_verified": None
            }
        ]
        self.write_companies(companies_data)

        with patch("company_discovery.requests.post") as mock_post:
            r_post = MagicMock()
            r_post.status_code = 403
            r_post.text = "Forbidden"
            mock_post.return_value = r_post

            updated = company_manager.verify_company_config("Walmart", self.companies_path, self.sources_path)
            
            # Should map to access_restricted status and not verify
            self.assertFalse(updated["verified"])
            self.assertEqual(updated["verification_status"], "access_restricted")
            self.assertIsNone(updated["jobs_found"])

    def test_targeted_discovery_skips_unverified(self):
        companies_data = [
            {
                "company": "Razorpay",
                "source": "greenhouse",
                "source_identifier": "razorpay",
                "enabled": True,
                "verified": False,
                "verification_status": "unverified",
                "jobs_found": None
            },
            {
                "company": "Figma",
                "source": "greenhouse",
                "source_identifier": "figma",
                "enabled": True,
                "verified": True,
                "verification_status": "verified_api",
                "jobs_found": 15
            }
        ]
        self.write_companies(companies_data)
        
        # Greenhouse sources config in sources.json
        self.write_sources({"greenhouse": ["razorpay", "figma"]})
        
        # Load boards
        with patch("company_manager.load_companies") as mock_load:
            mock_load.return_value = companies_data
            boards = sources.greenhouse.load_greenhouse_boards()
            
            # Razorpay should be skipped (unverified), Figma should be active (verified)
            self.assertNotIn("razorpay", boards)
            self.assertIn("figma", boards)

    @patch("company_discovery.requests.post")
    @patch("company_discovery.test_careers_page_reachable")
    def test_adobe_workday_detection_success_on_connection_reset(self, mock_reachable, mock_post):
        # Mock careers page unreachable due to ConnectionResetError
        mock_reachable.return_value = (False, "verification_failed", "ConnectionResetError: An existing connection was forcibly closed by the remote host", "")
        
        # Mock Workday API to succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 45,
            "jobPostings": [{"title": "Job 1", "externalPath": "/job1"}]
        }
        mock_post.return_value = mock_response

        # Target candidate
        cand = {
            "company_name": "Adobe",
            "ats_platform": "workday",
            "ats_host": "adobe.wd5.myworkdayjobs.com",
            "ats_tenant": "external_experienced",
            "careers_url": "https://www.adobe.com/careers"
        }

        res = company_discovery.verify_discovered_source(cand)
        self.assertTrue(res["verified"])
        self.assertEqual(res["verification_status"], "verified_api")
        self.assertEqual(res["jobs_available"], 45)

    @patch("company_discovery.requests.post")
    @patch("company_discovery.test_careers_page_reachable")
    def test_salesforce_workday_detection_success_on_unavailable_page(self, mock_reachable, mock_post):
        # Mock careers page unreachable
        mock_reachable.return_value = (False, "verification_failed", "HTTP 500 returned from careers page.", "")
        
        # Mock Workday API to succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 120,
            "jobPostings": [{"title": "Job 1", "externalPath": "/job1"}]
        }
        mock_post.return_value = mock_response

        # Target candidate
        cand = {
            "company_name": "Salesforce",
            "ats_platform": "workday",
            "ats_host": "salesforce.wd12.myworkdayjobs.com",
            "ats_tenant": "External_Career_Site",
            "careers_url": "https://careers.salesforce.com"
        }

        res = company_discovery.verify_discovered_source(cand)
        self.assertTrue(res["verified"])
        self.assertEqual(res["verification_status"], "verified_api")
        self.assertEqual(res["jobs_available"], 120)

    @patch("company_discovery.requests.get")
    def test_speculative_smartrecruiters_zero_jobs_protection(self, mock_get):
        # Mock SmartRecruiters API response with 200 but 0 jobs
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"
        mock_response.json.return_value = {"content": []}
        mock_get.return_value = mock_response

        # Speculative candidate
        cand = {
            "company_name": "SpecCo",
            "ats_platform": "unknown",
            "ats_slug": "specco",
            "careers_url": "https://www.specco.com/careers"
        }
        with patch("sources.first_party_careers.discover_first_party_with_browser", return_value=([], None)):
            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertEqual(res["verification_status"], "verification_failed")

    @patch("company_discovery.requests.post")
    @patch("company_discovery.test_careers_page_reachable")
    def test_invalid_workday_endpoint_failed(self, mock_reachable, mock_post):
        mock_reachable.return_value = (False, "verification_failed", "HTTP 404 returned from careers page.", "")
        
        # Mock Workday API to fail
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response

        cand = {
            "company_name": "Walmart",
            "ats_platform": "workday",
            "ats_host": "walmart.myworkdayjobs.com",
            "ats_tenant": "external",
            "careers_url": "https://careers.walmart.com"
        }

        res = company_discovery.verify_discovered_source(cand)
        self.assertFalse(res["verified"])
        self.assertEqual(res["verification_status"], "verification_failed")

    @patch("company_discovery.test_careers_page_reachable")
    def test_security_challenge_restricted(self, mock_reachable):
        # Mock careers page showing security challenge
        mock_reachable.return_value = (False, "access_restricted", "Cloudflare CAPTCHA challenge page detected.", "")

        cand = {
            "company_name": "Walmart",
            "ats_platform": "workday",
            "ats_host": "walmart.myworkdayjobs.com",
            "ats_tenant": "external",
            "careers_url": "https://careers.walmart.com"
        }

        res = company_discovery.verify_discovered_source(cand)
        self.assertFalse(res["verified"])
        self.assertEqual(res["verification_status"], "access_restricted")

    def test_adobe_workday_jobs_available_790_preserved(self):
        companies_data = [
            {
                "company": "Adobe India",
                "careers_url": "https://www.adobe.com/careers.html",
                "source": "workday",
                "source_identifier": "adobe",
                "enabled": True,
                "verified": False,
                "verification_status": "no_jobs_found",
                "jobs_found": 0,
                "jobs_available": 790,
                "jobs_retrieved": 20,
                "last_verified": "2026-08-13 22:00:00",
                "ats_host": "adobe.wd5.myworkdayjobs.com",
                "ats_tenant": "external_experienced",
                "access_strategy": "api"
            }
        ]
        self.write_companies(companies_data)
        loaded = company_manager.load_companies(self.companies_path)
        adobe = next(c for c in loaded if c["company"] == "Adobe India")
        
        self.assertTrue(adobe["verified"])
        self.assertEqual(adobe["verification_status"], "verified_api")
        self.assertEqual(adobe["jobs_available"], 790)

    @patch("company_discovery.requests.post")
    def test_jobs_found_zero_cannot_override_positive_jobs_available(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 790,
            "jobPostings": [{"title": f"Job {i}", "externalPath": f"/job{i}"} for i in range(20)]
        }
        mock_post.return_value = mock_response

        cand = {
            "company_name": "Adobe India",
            "ats_platform": "workday",
            "ats_host": "adobe.wd5.myworkdayjobs.com",
            "ats_tenant": "external_experienced",
            "careers_url": "https://www.adobe.com/careers.html"
        }
        res = company_discovery.verify_discovered_source(cand)
        self.assertTrue(res["verified"])
        self.assertEqual(res["verification_status"], "verified_api")
        self.assertEqual(res["jobs_available"], 790)
        self.assertEqual(res["jobs_retrieved"], 20)

    def test_salesforce_nvidia_behavior_unchanged(self):
        companies_data = [
            {
                "company": "NVIDIA India",
                "source": "workday",
                "enabled": True,
                "verified": True,
                "verification_status": "verified_api",
                "jobs_found": 20,
                "jobs_available": 2000,
                "jobs_retrieved": 20,
                "last_verified": "2026-08-13 22:00:00"
            },
            {
                "company": "Salesforce India",
                "source": "workday",
                "enabled": True,
                "verified": True,
                "verification_status": "verified_api",
                "jobs_found": 20,
                "jobs_available": 1521,
                "jobs_retrieved": 20,
                "last_verified": "2026-08-13 22:00:00"
            }
        ]
        self.write_companies(companies_data)
        loaded = company_manager.load_companies(self.companies_path)
        nvidia = next(c for c in loaded if c["company"] == "NVIDIA India")
        salesforce = next(c for c in loaded if c["company"] == "Salesforce India")
        
        self.assertEqual(nvidia["jobs_available"], 2000)
        self.assertEqual(nvidia["verification_status"], "verified_api")
        self.assertEqual(salesforce["jobs_available"], 1521)
        self.assertEqual(salesforce["verification_status"], "verified_api")

if __name__ == "__main__":
    unittest.main()
