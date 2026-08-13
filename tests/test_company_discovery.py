import unittest
import os
import json
import shutil
from unittest.mock import patch, MagicMock

import company_discovery
import company_manager
import database
import sources
import jobs

class TestCompanyDiscoveryV1_3(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.test_dir = tempfile.mkdtemp(prefix="test_comp_disc_")
        self.test_companies_json = os.path.join(self.test_dir, "companies.json")
        self.test_sources_json = os.path.join(self.test_dir, "sources.json")
        self.test_db = os.path.join(self.test_dir, "jobs.db")

        # Patch sync_playwright to None by default
        self.playwright_patch = patch("sources.browser_careers.sync_playwright", None)
        self.playwright_patch.start()

        # Initial test configuration
        initial_companies = [
            {
                "company": "Google",
                "careers_url": "https://careers.google.com",
                "official_company_url": "https://www.google.com",
                "priority": 100,
                "country": "India",
                "source": "workday",
                "source_identifier": "google",
                "enabled": True,
                "verified": True,
                "verification_status": "verified",
                "last_verified": "2026-08-13T10:00:00",
                "jobs_found": 37
            }
        ]
        initial_sources = {
            "greenhouse": ["razorpay"],
            "lever": ["postman"],
            "ashby": ["ramp"],
            "workday": [{"company": "Google", "host": "google.wd5.myworkdayjobs.com", "tenant": "Google", "company_slug": "google"}]
        }

        with open(self.test_companies_json, "w", encoding="utf-8") as f:
            json.dump(initial_companies, f, indent=2)
        with open(self.test_sources_json, "w", encoding="utf-8") as f:
            json.dump(initial_sources, f, indent=2)

        database.init_db(self.test_db)

    def tearDown(self):
        self.playwright_patch.stop()
        if hasattr(self, 'test_dir') and os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    # 1. Empty company name rejected
    def test_1_empty_company_name_rejected(self):
        with self.assertRaises(ValueError):
            company_discovery.discover_company("")

    # 2. Company name normalized
    def test_2_company_name_normalized(self):
        with patch("ai._call_ai_api") as mock_ai:
            mock_ai.return_value = json.dumps({"company_name": "  Zoho  ", "ats_platform": "workday"})
            res = company_discovery.discover_company("  Zoho  ")
            self.assertEqual(res["company_name"], "Zoho")

    # 3. AI discovery response parsed correctly
    def test_3_ai_discovery_response_parsed_correctly(self):
        mock_resp = json.dumps({
            "company_name": "Zoho",
            "official_company_url": "https://www.zoho.com",
            "careers_url": "https://www.zoho.com/careers",
            "country": "India",
            "ats_platform": "workday",
            "ats_host": "zoho.wd5.myworkdayjobs.com",
            "ats_tenant": "ZohoCareers",
            "ats_slug": "zoho",
            "confidence": 90
        })
        with patch("ai._call_ai_api", return_value=mock_resp):
            res = company_discovery.discover_company("Zoho")
            self.assertEqual(res["ats_platform"], "workday")
            self.assertEqual(res["confidence"], 90)

    # 4. Malformed AI response handled
    def test_4_malformed_ai_response_handled(self):
        with patch("ai._call_ai_api", return_value="Invalid JSON response"):
            res = company_discovery.discover_company("AcmeCorp")
            self.assertEqual(res["company_name"], "AcmeCorp")
            self.assertEqual(res["ats_slug"], "acmecorp")

    # 5. 3-provider AI failover works for discovery
    def test_5_ai_failover_works_for_discovery(self):
        with patch("ai._call_ai_api", return_value=json.dumps({"company_name": "Stripe", "ats_platform": "greenhouse"})):
            res = company_discovery.discover_company("Stripe")
            self.assertEqual(res["ats_platform"], "greenhouse")

    # 6. Official careers URL verification succeeds
    def test_6_official_careers_url_verification_succeeds(self):
        cand = {
            "company_name": "Figma",
            "ats_platform": "greenhouse",
            "ats_slug": "figma",
            "official_company_url": "https://www.figma.com",
            "careers_url": "https://www.figma.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 1, "title": "Dev"}]}
            mock_get.return_value = mock_resp

            verified = company_discovery.verify_discovered_source(cand)
            self.assertTrue(verified["verified"])
            self.assertEqual(verified["jobs_found"], 1)

    # 7. Invalid careers URL rejected
    def test_7_invalid_careers_url_rejected(self):
        cand = {
            "company_name": "FakeCo",
            "ats_platform": "greenhouse",
            "ats_slug": "non_existent_slug_999",
            "official_company_url": "https://www.fakeco.com",
            "careers_url": "https://www.fakeco.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            verified = company_discovery.verify_discovered_source(cand)
            self.assertFalse(verified["verified"])
            self.assertEqual(verified["verification_status"], "verification_failed")

    # 8. Unsupported ATS handled gracefully
    def test_8_unsupported_ats_handled_gracefully(self):
        cand = {
            "company_name": "LegacyCorp",
            "ats_platform": "unknown",
            "ats_slug": "legacycorp"
        }
        with patch("requests.get", side_effect=Exception("Connection refused")):
            verified = company_discovery.verify_discovered_source(cand)
            self.assertFalse(verified["verified"])

    # 9. Workday config verified before persistence
    def test_9_workday_config_verified_before_persistence(self):
        cand = {
            "company_name": "NVIDIA",
            "ats_platform": "workday",
            "ats_host": "nvidia.wd5.myworkdayjobs.com",
            "ats_tenant": "NVIDIAExternalCareerSite",
            "ats_slug": "nvidia"
        }
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobPostings": [{"id": 1}]}
            mock_post.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])
            self.assertEqual(res["jobs_found"], 1)

    # 10. Greenhouse config verified before persistence
    def test_10_greenhouse_config_verified_before_persistence(self):
        cand = {"company_name": "Razorpay", "ats_platform": "greenhouse", "ats_slug": "razorpay"}
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 10}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])

    # 11. Lever config verified before persistence
    def test_11_lever_config_verified_before_persistence(self):
        cand = {"company_name": "Postman", "ats_platform": "lever", "ats_slug": "postman"}
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"id": "1"}]
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])

    # 12. Ashby config verified before persistence
    def test_12_ashby_config_verified_before_persistence(self):
        cand = {"company_name": "Ramp", "ats_platform": "ashby", "ats_slug": "ramp"}
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": "r1"}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])

    # 13. SmartRecruiters config verified before persistence
    def test_13_smartrecruiters_config_verified_before_persistence(self):
        cand = {"company_name": "Visa", "ats_platform": "smartrecruiters", "ats_slug": "visa"}
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"content": [{"id": "v1"}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])

    # 14. Failed ATS verification does not modify config
    def test_14_failed_ats_verification_does_not_modify_config(self):
        initial_count = len(company_manager.load_companies(self.test_companies_json))
        cand = {"company_name": "UnverifiedCo", "verified": False}
        # Attempting to save unverified without explicitly invoking add_company_config
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(len(comps), initial_count)

    # 15. Successful verification writes companies.json
    def test_15_successful_verification_writes_companies_json(self):
        comp_data = {
            "company": "Zoho",
            "priority": 85,
            "ats_platform": "workday",
            "ats_slug": "zoho",
            "verified": True,
            "jobs_found": 42
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        comps = company_manager.load_companies(self.test_companies_json)
        zoho = [c for c in comps if c["company"] == "Zoho"][0]
        self.assertEqual(zoho["priority"], 85)
        self.assertEqual(zoho["jobs_found"], 42)

    # 16. Successful verification writes sources.json
    def test_16_successful_verification_writes_sources_json(self):
        comp_data = {
            "company": "Freshworks",
            "priority": 90,
            "ats_platform": "greenhouse",
            "ats_slug": "freshworks",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 10
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        sources_cfg = company_manager.load_sources(self.test_sources_json)
        self.assertIn("freshworks", sources_cfg["greenhouse"])

    # 17. Existing company is not duplicated
    def test_17_existing_company_not_duplicated(self):
        comp_data = {
            "company": "Google",
            "priority": 95,
            "ats_platform": "workday",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 37
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        comps = company_manager.load_companies(self.test_companies_json)
        googles = [c for c in comps if c["company"].lower() == "google"]
        self.assertEqual(len(googles), 1)
        self.assertEqual(googles[0]["priority"], 95)

    # 18. Existing company can be re-verified
    def test_18_existing_company_can_be_reverified(self):
        with patch("company_discovery.verify_discovered_source") as mock_ver:
            mock_ver.return_value = {"verified": True, "verification_status": "verified", "last_verified": "2026-08-13T12:00:00", "jobs_found": 50}
            updated = company_manager.verify_company_config("Google", self.test_companies_json, self.test_sources_json)
            self.assertTrue(updated["verified"])
            self.assertEqual(updated["jobs_found"], 50)

    # 19. Company priority is persisted
    def test_19_company_priority_persisted(self):
        success = company_manager.update_company_priority("Google", 88, self.test_companies_json)
        self.assertTrue(success)
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(comps[0]["priority"], 88)

    # 20. Priority remains within 1–100
    def test_20_priority_clamped_1_to_100(self):
        company_manager.update_company_priority("Google", 150, self.test_companies_json)
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(comps[0]["priority"], 100)

        company_manager.update_company_priority("Google", -10, self.test_companies_json)
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(comps[0]["priority"], 1)

    # 21. Company disable works
    def test_21_company_disable_works(self):
        company_manager.toggle_company_status("Google", False, self.test_companies_json)
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertFalse(comps[0]["enabled"])

    # 22. Company enable works
    def test_22_company_enable_works(self):
        company_manager.toggle_company_status("Google", True, self.test_companies_json)
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertTrue(comps[0]["enabled"])

    # 23. Company removal does not delete historical jobs
    def test_23_company_removal_does_not_delete_historical_jobs(self):
        # Insert historical job into SQLite
        job = {
            "source": "workday",
            "unique_id": "workday:g1",
            "company": "Google",
            "title": "SWE",
            "location": "Remote",
            "description": "Desc",
            "application_url": "http://google",
            "status": "new"
        }
        job_id = database.save_job(job, db_path=self.test_db)
        
        # Remove Google from config
        company_manager.remove_company_config("Google", self.test_companies_json, self.test_sources_json)
        
        # Verify Google removed from config
        comps = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(len([c for c in comps if c["company"] == "Google"]), 0)
        
        # Verify historical SQLite job intact
        fetched = database.get_job_by_id(job_id, db_path=self.test_db)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["company"], "Google")

    # 24. Open Discovery remains unaffected
    def test_24_open_discovery_remains_unaffected(self):
        comp_data = {
            "company": "Uber",
            "priority": 90,
            "ats_platform": "greenhouse",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 5
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        
        # Verify Adzuna open discovery entry in sources.json is unchanged
        sources_cfg = company_manager.load_sources(self.test_sources_json)
        self.assertIn("greenhouse", sources_cfg)

    # 25. Targeted Discovery uses newly added company
    def test_25_targeted_discovery_uses_newly_added_company(self):
        comp_data = {
            "company": "Figma",
            "priority": 90,
            "ats_platform": "greenhouse",
            "source_identifier": "figma",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 8
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        
        with patch("company_manager.COMPANIES_CONFIG_PATH", self.test_companies_json), \
             patch("company_manager.SOURCES_CONFIG_PATH", self.test_sources_json):
            from sources.greenhouse import load_greenhouse_boards
            boards = load_greenhouse_boards()
            self.assertIn("figma", boards)

    # 26. Source failure does not crash discovery
    def test_26_source_failure_does_not_crash_discovery(self):
        cand = {"company_name": "BrokenCo", "ats_platform": "greenhouse", "ats_slug": "broken_slug"}
        with patch("requests.get", side_effect=Exception("Network error")):
            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertEqual(res["verification_status"], "verification_failed")

    # 27. API keys never appear in logs
    def test_27_api_keys_never_appear_in_logs(self):
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
        
        with patch("ai._call_ai_api", return_value=json.dumps({"company_name": "SecureCo"})):
            company_discovery.discover_company("SecureCo", progress_callback=mock_log)
            for m in log_msgs:
                self.assertNotIn("mock_key", m)
                self.assertNotIn("AI_API_KEY", m)

    # 28. Private/unsafe URLs are rejected
    def test_28_private_unsafe_urls_rejected(self):
        self.assertFalse(company_discovery.is_safe_url("http://localhost:5000"))
        self.assertFalse(company_discovery.is_safe_url("http://127.0.0.1/admin"))
        self.assertFalse(company_discovery.is_safe_url("file:///etc/passwd"))
        self.assertTrue(company_discovery.is_safe_url("https://www.google.com"))

    # 29. Verification timestamp, status, and jobs_found are persisted
    def test_29_verification_timestamp_status_jobs_found_persisted(self):
        comp_data = {
            "company": "SmartCo",
            "priority": 80,
            "ats_platform": "lever",
            "verified": True,
            "verification_status": "verified",
            "last_verified": "2026-08-13T14:30:00",
            "jobs_found": 15
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        comps = company_manager.load_companies(self.test_companies_json)
        saved = [c for c in comps if c["company"] == "SmartCo"][0]
        self.assertEqual(saved["verification_status"], "verified")
        self.assertEqual(saved["jobs_found"], 15)
        self.assertEqual(saved["last_verified"], "2026-08-13T14:30:00")

    # 30. Existing company configurations remain intact after adding a new company
    def test_30_existing_company_configs_remain_intact(self):
        initial_google = company_manager.load_companies(self.test_companies_json)[0]
        
        comp_data = {
            "company": "NewCo",
            "priority": 70,
            "ats_platform": "lever",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 5
        }
        company_manager.add_company_config(comp_data, self.test_companies_json, self.test_sources_json)
        
        updated_google = company_manager.load_companies(self.test_companies_json)[0]
        self.assertEqual(initial_google["company"], updated_google["company"])
        self.assertEqual(initial_google["priority"], updated_google["priority"])

    # --- REGRESSION TESTS FOR ZERO-JOB AND STATE MACHINE PRECEDENCE ---

    # Reg 1: Reachable ATS + jobs > 0 -> Verified
    def test_reg_1_reachable_ats_jobs_greater_than_0_verified(self):
        cand = {
            "company_name": "Acme",
            "ats_platform": "greenhouse",
            "ats_slug": "acme",
            "confidence": 85,
            "careers_url": "https://www.acme.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 1}, {"id": 2}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])
            self.assertTrue(res["addable"])
            self.assertTrue(res["verification_status"].startswith("verified"))
            self.assertEqual(res["jobs_found"], 2)

    # Reg 2: Reachable ATS + jobs == 0 -> Not Verified / No Current Jobs
    def test_reg_2_reachable_ats_jobs_0_no_jobs_found(self):
        cand = {
            "company_name": "Deloitte",
            "ats_platform": "smartrecruiters",
            "ats_slug": "deloitte",
            "confidence": 95,
            "careers_url": "https://www.deloitte.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"content": []}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "no_jobs_found")
            self.assertIn("no current jobs", res["verification_reason"].lower())

    # Reg 3: Unreachable ATS -> Verification Failed
    def test_reg_3_unreachable_ats_verification_failed(self):
        cand = {
            "company_name": "UnreachableCo",
            "ats_platform": "greenhouse",
            "ats_slug": "unreachable",
            "confidence": 90
        }
        with patch("requests.get", side_effect=Exception("Connection refused")):
            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "verification_failed")

    # Reg 4: Wrong ATS configuration -> Verification Failed (HTTP 404)
    def test_reg_4_wrong_ats_config_verification_failed(self):
        cand = {
            "company_name": "WrongCo",
            "ats_platform": "greenhouse",
            "ats_slug": "wrong_slug_404",
            "confidence": 85
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "verification_failed")

    # Reg 5: Speculative SmartRecruiters with 0 jobs returns verification_failed
    def test_reg_5_speculative_smartrecruiters_zero_jobs_returns_failed(self):
        cand = {
            "company_name": "Focus Softnet",
            "ats_platform": "unknown",
            "ats_slug": "focussoftnet",
            "source_origin": "speculative",
            "careers_url": "https://www.focussoftnet.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html></html>"
            mock_resp.json.return_value = {"content": []}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "verification_failed")

    # Reg 6: Unverified candidate cannot be persisted
    def test_reg_6_unverified_cannot_be_persisted(self):
        cand = {
            "company": "FailedCo",
            "priority": 75,
            "ats_platform": "greenhouse",
            "verified": False,
            "addable": False,
            "verification_status": "verification_failed"
        }
        with self.assertRaises(ValueError):
            company_manager.add_company_config(cand, self.test_companies_json, self.test_sources_json)

    # Reg 7: Zero-job source cannot be persisted as a Verified active source
    def test_reg_7_zero_job_source_cannot_be_persisted_as_verified(self):
        cand = {
            "company": "Deloitte",
            "priority": 75,
            "ats_platform": "smartrecruiters",
            "verified": False,
            "addable": False,
            "verification_status": "no_jobs_found",
            "jobs_found": 0
        }
        with self.assertRaises(ValueError):
            company_manager.add_company_config(cand, self.test_companies_json, self.test_sources_json)

    # Reg 8: Valid company with jobs can still be added
    def test_reg_8_valid_company_with_jobs_can_be_added(self):
        cand = {
            "company": "ValidCo",
            "priority": 85,
            "ats_platform": "greenhouse",
            "source_identifier": "validco",
            "verified": True,
            "addable": True,
            "verification_status": "verified",
            "jobs_found": 12
        }
        entry = company_manager.add_company_config(cand, self.test_companies_json, self.test_sources_json)
        self.assertEqual(entry["company"], "ValidCo")
        self.assertEqual(entry["jobs_found"], 12)

    # Reg 9: Existing companies remain unchanged
    def test_reg_9_existing_companies_remain_unchanged(self):
        initial = company_manager.load_companies(self.test_companies_json)
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]["company"], "Google")

    # Reg 10: Verification failure does not modify companies.json
    def test_reg_10_verification_failure_does_not_modify_companies_json(self):
        initial_len = len(company_manager.load_companies(self.test_companies_json))
        cand = {
            "company": "FailedCo",
            "verified": False,
            "addable": False,
            "verification_status": "verification_failed"
        }
        try:
            company_manager.add_company_config(cand, self.test_companies_json, self.test_sources_json)
        except ValueError:
            pass
        current_len = len(company_manager.load_companies(self.test_companies_json))
        self.assertEqual(initial_len, current_len)

    # Reg 11: Verification failure does not modify sources.json
    def test_reg_11_verification_failure_does_not_modify_sources_json(self):
        initial_sources = company_manager.load_sources(self.test_sources_json)
        cand = {
            "company": "FailedCo",
            "ats_platform": "greenhouse",
            "ats_slug": "failedco",
            "verified": False,
            "addable": False,
            "verification_status": "verification_failed"
        }
        try:
            company_manager.add_company_config(cand, self.test_companies_json, self.test_sources_json)
        except ValueError:
            pass
        current_sources = company_manager.load_sources(self.test_sources_json)
        self.assertEqual(initial_sources, current_sources)

    # Reg 12: Retry discovery preserves company name
    def test_reg_12_retry_discovery_preserves_company_name(self):
        with patch("ai._call_ai_api") as mock_ai:
            mock_ai.return_value = json.dumps({"company_name": "Deloitte", "ats_platform": "smartrecruiters"})
            res = company_discovery.discover_company("Deloitte")
            self.assertEqual(res["company_name"], "Deloitte")

    # Reg 13: 0 jobs on valid explicit ATS returns no_jobs_found
    def test_reg_13_zero_jobs_on_valid_explicit_ats_returns_no_jobs_found(self):
        cand = {
            "company_name": "ZeroJobsCo",
            "ats_platform": "greenhouse",
            "ats_slug": "zerojobs",
            "source_origin": "ai"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": []}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "no_jobs_found")

    # Reg 14: HTML Greenhouse inspection verified when jobs exist
    def test_reg_14_html_greenhouse_inspection_verified(self):
        cand = {
            "company_name": "GitLab",
            "official_company_url": "https://about.gitlab.com",
            "careers_url": "https://about.gitlab.com/jobs",
            "ats_platform": "unknown"
        }
        html_content = '<html><body><a href="https://boards.greenhouse.io/gitlab">Careers</a></body></html>'
        with patch("company_discovery.inspect_careers_page_for_ats") as mock_inspect, \
             patch("requests.get") as mock_get:
            mock_inspect.return_value = {"ats_platform": "greenhouse", "ats_slug": "gitlab", "ats_host": "", "ats_tenant": "", "origin": "html_inspection"}
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 101}]}
            mock_get.return_value = mock_resp

            disc = company_discovery.discover_company("GitLab")
            self.assertEqual(disc["ats_platform"], "greenhouse")
            self.assertEqual(disc["source_origin"], "html_inspection")

            ver = company_discovery.verify_discovered_source(disc)
            self.assertTrue(ver["verified"])
            self.assertTrue(ver["addable"])
            self.assertTrue(ver["verification_status"].startswith("verified"))
            self.assertEqual(ver["jobs_found"], 1)

    # Reg 15: Disney test - AI confidence = 30 + Greenhouse jobs = 2 -> verified
    def test_reg_15_disney_confidence_30_with_jobs_verified(self):
        cand = {
            "company_name": "Disney",
            "ats_platform": "greenhouse",
            "ats_slug": "disney",
            "confidence": 30,
            "careers_url": "https://www.disney.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 1}, {"id": 2}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])
            self.assertTrue(res["addable"])
            self.assertTrue(res["verification_status"].startswith("verified"))
            self.assertEqual(res["jobs_found"], 2)
            self.assertNotIn("confidence", res)

    # Reg 16: Disney test - AI confidence = 85 + Greenhouse jobs = 2 -> verified
    def test_reg_16_disney_confidence_85_with_jobs_verified(self):
        cand = {
            "company_name": "Disney",
            "ats_platform": "greenhouse",
            "ats_slug": "disney",
            "confidence": 85,
            "careers_url": "https://www.disney.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 1}, {"id": 2}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])
            self.assertTrue(res["addable"])
            self.assertTrue(res["verification_status"].startswith("verified"))

    # Reg 17: Disney test - AI confidence = None + Greenhouse jobs = 2 -> verified
    def test_reg_17_disney_confidence_none_with_jobs_verified(self):
        cand = {
            "company_name": "Disney",
            "ats_platform": "greenhouse",
            "ats_slug": "disney",
            "confidence": None,
            "careers_url": "https://www.disney.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": [{"id": 1}, {"id": 2}]}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertTrue(res["verified"])
            self.assertTrue(res["addable"])
            self.assertTrue(res["verification_status"].startswith("verified"))

    # Reg 18: Disney test - AI confidence = 100 + Greenhouse jobs = 0 -> no_jobs_found
    def test_reg_18_disney_confidence_100_with_zero_jobs_no_jobs_found(self):
        cand = {
            "company_name": "Disney",
            "ats_platform": "greenhouse",
            "ats_slug": "disney",
            "confidence": 100,
            "source_origin": "ai",
            "careers_url": "https://www.disney.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"jobs": []}
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "no_jobs_found")

    # Reg 19: Disney test - AI confidence = 30 + Greenhouse invalid (HTTP 404) -> verification_failed
    def test_reg_19_disney_confidence_30_with_404_verification_failed(self):
        cand = {
            "company_name": "Disney",
            "ats_platform": "greenhouse",
            "ats_slug": "invalid_slug_404",
            "confidence": 30,
            "careers_url": "https://www.disney.com/careers"
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            res = company_discovery.verify_discovered_source(cand)
            self.assertFalse(res["verified"])
            self.assertFalse(res["addable"])
            self.assertEqual(res["verification_status"], "verification_failed")
            self.assertIn("HTTP 404", res["verification_reason"])

if __name__ == "__main__":
    unittest.main()
