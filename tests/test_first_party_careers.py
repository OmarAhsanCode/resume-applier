"""
tests/test_first_party_careers.py - Comprehensive test suite for V1.5.1 Generic Dynamic First-Party Career Discovery.

Covers all 25 scenarios:
1. Eightfold/PCSX JSON extraction
2. Generic nested positions extraction
3. Generic jobs/results/items extraction
4. Amazon search.json regression
5. PCSX query parameter construction
6. PCSX location parameter construction
7. PCSX pagination
8. total_positions -> jobs_available
9. jobs_retrieved tracking
10. HTTP 200 + empty jobs does NOT verify a source
11. Browser XHR JSON interception
12. Browser discovery uses domcontentloaded (not networkidle)
13. Browser-discovered API direct standalone retrieval
14. reCAPTCHA script does NOT trigger access_restricted
15. Actual Cloudflare challenge DOES trigger access_restricted
16. Actual CAPTCHA challenge DOES trigger access_restricted
17. Stop checker cancels browser/API discovery
18. Existing ATS discovery remains unchanged
19. Existing Amazon first-party discovery remains unchanged
20. First-party jobs enter existing normalization
21. First-party jobs receive targeted discovery_lane
22. Cross-source deduplication still works
23. last_shown_at rotation still works
24. Applied/rejected jobs remain excluded
25. Mocked Microsoft-style payload regression test
"""

import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

import database
import jobs
import company_manager
import company_discovery
import sources
import sources.first_party_careers as fp_mod
from sources.first_party_careers import (
    extract_jobs_from_json_payload,
    extract_jobs_from_json_ld,
    extract_jobs_from_html,
    probe_first_party_api_or_search,
    discover_first_party_with_browser,
    discover_jobs_from_first_party,
    check_page_for_challenges,
    AccessRestrictedError
)


class TestFirstPartyCareers(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_fp_")
        self.db_path = os.path.join(self.test_dir, "test_jobs.db")
        self.companies_path = os.path.join(self.test_dir, "companies.json")
        self.sources_path = os.path.join(self.test_dir, "sources.json")
        database.init_db(self.db_path)

        self.mock_companies = [
            {
                "company": "Amazon India",
                "careers_url": "https://www.amazon.jobs/",
                "category": "Global Tech",
                "priority": 100,
                "country": "India",
                "source": "first_party",
                "source_type": "first_party",
                "source_identifier": "amazon",
                "enabled": True,
                "verified": True,
                "verification_status": "verified_first_party",
                "jobs_found": 15,
                "last_verified": "2026-08-14 10:00:00"
            },
            {
                "company": "Microsoft India",
                "careers_url": "https://careers.microsoft.com",
                "category": "Global Tech",
                "priority": 100,
                "country": "India",
                "source": "first_party",
                "source_type": "first_party",
                "source_identifier": "microsoft",
                "enabled": True,
                "verified": True,
                "verification_status": "verified_first_party",
                "jobs_found": 20,
                "last_verified": "2026-08-14 10:00:00"
            }
        ]

        with open(self.companies_path, "w", encoding="utf-8") as f:
            json.dump(self.mock_companies, f, indent=2)

        with open(self.sources_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

    def tearDown(self):
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    # 1. Eightfold/PCSX JSON extraction
    def test_01_pcsx_json_extraction(self):
        payload = {
            "status": 200,
            "data": {
                "total_positions": 116,
                "positions": [
                    {
                        "id": 1970393556955275,
                        "displayJobId": "200046596",
                        "name": "Software Engineer II",
                        "locations": ["India, Karnataka, Bangalore", "India, Telangana, Hyderabad"],
                        "employmentType": "Full-Time",
                        "description": "Develop high-scale cloud platforms.",
                        "positionUrl": "https://apply.careers.microsoft.com/careers/job/1970393556955275"
                    }
                ]
            }
        }
        jobs_list, total = extract_jobs_from_json_payload(payload, "Microsoft India", "https://apply.careers.microsoft.com")
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(total, 116)
        job = jobs_list[0]
        self.assertEqual(job["title"], "Software Engineer II")
        self.assertEqual(job["source_job_id"], "200046596")
        self.assertIn("Bangalore", job["location"])
        self.assertEqual(job["employment_type"], "full_time")
        self.assertEqual(job["application_url"], "https://apply.careers.microsoft.com/careers/job/1970393556955275")
        self.assertEqual(job["discovery_lane"], "targeted")

    # 2. Generic nested positions extraction
    def test_02_generic_nested_positions_extraction(self):
        payload = {
            "response": {
                "body": {
                    "openings": [
                        {
                            "jobTitle": "Backend Engineer",
                            "requisitionId": "REQ-101",
                            "city": "Austin",
                            "state": "TX",
                            "country": "USA",
                            "url": "/jobs/req-101"
                        }
                    ],
                    "totalCount": 42
                }
            }
        }
        jobs_list, total = extract_jobs_from_json_payload(payload, "AcmeCorp", "https://careers.acme.com")
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(total, 42)
        self.assertEqual(jobs_list[0]["title"], "Backend Engineer")
        self.assertEqual(jobs_list[0]["source_job_id"], "REQ-101")
        self.assertIn("Austin", jobs_list[0]["location"])
        self.assertEqual(jobs_list[0]["application_url"], "https://careers.acme.com/jobs/req-101")

    # 3. Generic jobs/results/items extraction
    def test_03_generic_results_items_extraction(self):
        payload = {
            "results": [
                {
                    "title": "Data Scientist",
                    "id": "DS-202",
                    "location": "Remote",
                    "link": "https://company.com/ds-202"
                }
            ],
            "hits": 1
        }
        jobs_list, total = extract_jobs_from_json_payload(payload, "DataCorp", "https://company.com")
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(total, 1)
        self.assertEqual(jobs_list[0]["title"], "Data Scientist")
        self.assertEqual(jobs_list[0]["source_job_id"], "DS-202")

    # 4. Amazon search.json regression
    def test_04_amazon_search_json_regression(self):
        payload = {
            "hits": 500,
            "jobs": [
                {
                    "title": "Software Development Engineer I",
                    "id_icims": "2841459",
                    "job_path": "/en/jobs/2841459/sde-i",
                    "location": "Hyderabad, IND",
                    "country_code": "IND",
                    "job_schedule_type": "Full-Time",
                    "description_short": "Amazon SDE role in Hyderabad."
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = payload
        with patch("requests.get", return_value=mock_resp):
            jobs_list, total = probe_first_party_api_or_search("https://www.amazon.jobs/", "Amazon India")
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(total, 500)
            self.assertEqual(jobs_list[0]["title"], "Software Development Engineer I")
            self.assertEqual(jobs_list[0]["source_job_id"], "2841459")
            self.assertEqual(jobs_list[0]["application_url"], "https://www.amazon.jobs/en/jobs/2841459/sde-i")

    # 5. PCSX query parameter construction
    def test_05_pcsx_query_parameter_construction(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {
            "status": 200,
            "data": {
                "total_positions": 5,
                "positions": [{"name": "AI Engineer", "id": 1, "locations": ["Remote"]}]
            }
        }
        with patch("requests.get", return_value=mock_resp) as mock_get:
            search_cfg = {"preferred_roles": ["AI Engineer"], "locations": ["Bangalore"]}
            jobs_list, total = probe_first_party_api_or_search("https://careers.microsoft.com", "Microsoft", search_config=search_cfg)
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(total, 5)
            # Verify query and location parameters were passed
            called_params = mock_get.call_args[1]["params"]
            self.assertEqual(called_params.get("query"), "AI Engineer")
            self.assertEqual(called_params.get("location"), "Bangalore")

    # 6. PCSX location parameter construction
    def test_06_pcsx_location_parameter_construction(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {
            "status": 200,
            "data": {
                "total_positions": 10,
                "positions": [{"name": "SWE", "id": 2, "locations": ["Hyderabad"]}]
            }
        }
        with patch("requests.get", return_value=mock_resp) as mock_get:
            search_cfg = {"preferred_roles": ["SWE"], "locations": ["Hyderabad"]}
            probe_first_party_api_or_search("https://apply.careers.microsoft.com", "Microsoft", search_config=search_cfg)
            called_params = mock_get.call_args[1]["params"]
            self.assertEqual(called_params.get("location"), "Hyderabad")

    # 7. PCSX pagination
    def test_07_pcsx_pagination(self):
        page1_payload = {
            "status": 200,
            "data": {
                "total_positions": 30,
                "positions": [{"name": f"Job {i}", "id": i, "locations": ["Remote"]} for i in range(20)]
            }
        }
        page2_payload = {
            "status": 200,
            "data": {
                "total_positions": 30,
                "positions": [{"name": f"Job {i}", "id": i, "locations": ["Remote"]} for i in range(20, 30)]
            }
        }
        mock_r1 = MagicMock(status_code=200, headers={"Content-Type": "application/json"})
        mock_r1.json.return_value = page1_payload
        mock_r2 = MagicMock(status_code=200, headers={"Content-Type": "application/json"})
        mock_r2.json.return_value = page2_payload

        with patch("requests.get", side_effect=[mock_r1, mock_r2]):
            jobs_list, total = probe_first_party_api_or_search("https://careers.microsoft.com", "Microsoft")
            self.assertEqual(len(jobs_list), 30)
            self.assertEqual(total, 30)

    # 8. total_positions -> jobs_available
    def test_08_total_positions_mapped_to_jobs_available(self):
        payload = {
            "status": 200,
            "data": {
                "total_positions": 250,
                "positions": [{"name": "Lead Architect", "id": 99, "locations": ["Bangalore"]}]
            }
        }
        _, total = extract_jobs_from_json_payload(payload, "Test", "https://test.com")
        self.assertEqual(total, 250)

    # 9. jobs_retrieved tracking
    def test_09_jobs_retrieved_tracking(self):
        mock_resp = MagicMock(status_code=200, headers={"Content-Type": "application/json"})
        mock_resp.json.return_value = {
            "status": 200,
            "data": {
                "total_positions": 116,
                "positions": [{"name": "Dev", "id": 1, "locations": ["India"]}]
            }
        }
        with patch("requests.get", return_value=mock_resp):
            jobs_list, total = probe_first_party_api_or_search("https://careers.microsoft.com", "Microsoft")
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(total, 116)

    # 10. HTTP 200 + empty jobs does NOT verify a source
    def test_10_empty_jobs_does_not_verify(self):
        mock_resp = MagicMock(status_code=200, headers={"Content-Type": "application/json"})
        mock_resp.json.return_value = {"status": 200, "data": {"total_positions": 0, "positions": []}}
        with patch("requests.get", return_value=mock_resp):
            jobs_list, total = probe_first_party_api_or_search("https://careers.empty.com", "EmptyCorp")
            self.assertEqual(len(jobs_list), 0)
            self.assertIsNone(total)

    # 11. Browser XHR JSON interception
    def test_11_browser_xhr_json_interception(self):
        mock_page = MagicMock()
        mock_page.title.return_value = "Careers"
        mock_page.content.return_value = "<html><body>No DOM jobs</body></html>"
        mock_page.url = "https://careers.microsoft.com"
        mock_page.query_selector.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        mock_playwright = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p

        # Simulate network response event callback triggering on page.on("response", ...)
        captured_cb = []
        def capture_on(event, cb):
            if event == "response":
                captured_cb.append(cb)
        mock_page.on.side_effect = capture_on

        def fake_goto(url, **kwargs):
            # Trigger response listener with mock XHR response
            fake_res = MagicMock()
            fake_res.request.resource_type = "xhr"
            fake_res.request.method = "GET"
            fake_res.url = "https://apply.careers.microsoft.com/api/pcsx/search"
            fake_res.headers = {"content-type": "application/json"}
            fake_res.json.return_value = {
                "data": {
                    "total_positions": 50,
                    "positions": [{"name": "Cloud Engineer", "id": 88, "locations": ["Bangalore"]}]
                }
            }
            for cb in captured_cb:
                cb(fake_res)
        mock_page.goto.side_effect = fake_goto

        with patch("sources.browser_careers.sync_playwright", mock_playwright):
            jobs_list, total = discover_first_party_with_browser({"company": "Microsoft", "careers_url": "https://careers.microsoft.com"})
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(total, 50)
            self.assertEqual(jobs_list[0]["title"], "Cloud Engineer")

    # 12. Browser discovery uses domcontentloaded (not networkidle)
    def test_12_browser_discovery_uses_domcontentloaded(self):
        mock_page = MagicMock()
        mock_page.title.return_value = "Careers"
        mock_page.content.return_value = "<html><body></body></html>"
        mock_page.url = "https://careers.com"
        mock_page.query_selector.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        mock_playwright = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p

        with patch("sources.browser_careers.sync_playwright", mock_playwright):
            discover_first_party_with_browser({"company": "Test", "careers_url": "https://careers.com"})
            # Verify wait_until was domcontentloaded
            called_wait = mock_page.goto.call_args[1].get("wait_until")
            self.assertEqual(called_wait, "domcontentloaded")

    # 13. Browser-discovered API can be called directly
    def test_13_browser_discovered_api_direct_retrieval(self):
        mock_resp = MagicMock(status_code=200, headers={"Content-Type": "application/json"})
        mock_resp.json.return_value = {
            "status": 200,
            "data": {
                "total_positions": 20,
                "positions": [{"name": "Site Reliability Engineer", "id": 77, "locations": ["Hyderabad"]}]
            }
        }
        with patch("requests.get", return_value=mock_resp):
            jobs_list, total = probe_first_party_api_or_search("https://apply.careers.microsoft.com", "Microsoft")
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(jobs_list[0]["title"], "Site Reliability Engineer")

    # 14. reCAPTCHA script does NOT trigger access_restricted
    def test_14_recaptcha_script_does_not_trigger_access_restricted(self):
        html = """
        <html>
        <head>
            <title>Careers at Microsoft</title>
            <script src="https://www.recaptcha.net/recaptcha/api.js?render=6LfwboYU"></script>
        </head>
        <body>
            <h1>Welcome to Microsoft Careers</h1>
        </body>
        </html>
        """
        # Should not raise AccessRestrictedError
        try:
            check_page_for_challenges("Careers at Microsoft", html)
        except AccessRestrictedError:
            self.fail("check_page_for_challenges raised AccessRestrictedError on benign reCAPTCHA script tag!")

    # 15. Actual Cloudflare challenge DOES trigger access_restricted
    def test_15_cloudflare_challenge_triggers_access_restricted(self):
        html = '<html><head><title>Just a moment...</title></head><body><div id="challenge-running">Please verify you are a human.</div></body></html>'
        with self.assertRaises(AccessRestrictedError):
            check_page_for_challenges("Just a moment...", html)

    # 16. Actual CAPTCHA challenge DOES trigger access_restricted
    def test_16_captcha_challenge_triggers_access_restricted(self):
        html = '<html><head><title>Security Check</title></head><body><p>Please complete the security check to access this page.</p></body></html>'
        with self.assertRaises(AccessRestrictedError):
            check_page_for_challenges("Security Check", html)

    # 17. Stop checker cancels browser/API discovery
    def test_17_stop_checker_cancels_discovery(self):
        stop_called = False
        def should_stop():
            nonlocal stop_called
            stop_called = True
            return True

        jobs_list = discover_jobs_from_first_party(
            {"company": "Test", "careers_url": "https://test.com"},
            stop_checker=should_stop
        )
        self.assertTrue(stop_called)
        self.assertEqual(len(jobs_list), 0)

    # 18. Existing ATS discovery remains unchanged
    def test_18_existing_ats_discovery_unchanged(self):
        gh_entry = [s for s in sources.SOURCES if s["name"] == "greenhouse"]
        self.assertEqual(len(gh_entry), 1)
        self.assertTrue(gh_entry[0]["enabled"])

    # 19. Existing Amazon first-party discovery remains unchanged
    def test_19_amazon_first_party_unchanged(self):
        json_data = {"jobs": [{"title": "AWS Support Engineer", "id_icims": "9911", "job_path": "/en/jobs/9911"}]}
        mock_resp = MagicMock(status_code=200, headers={"Content-Type": "application/json"}, text=json.dumps(json_data))
        mock_resp.json.return_value = json_data
        with patch("requests.get", return_value=mock_resp):
            jobs_list = discover_jobs_from_first_party({"company": "Amazon", "careers_url": "https://www.amazon.jobs/"})
            self.assertEqual(len(jobs_list), 1)
            self.assertEqual(jobs_list[0]["title"], "AWS Support Engineer")

    # 20. First-party jobs enter existing normalization
    def test_20_first_party_normalization_fields(self):
        payload = {"positions": [{"name": "Full Stack Engineer", "id": "123", "locations": ["Bangalore"]}]}
        jobs_list, _ = extract_jobs_from_json_payload(payload, "TestCo", "https://testco.com")
        job = jobs_list[0]
        self.assertIn("source", job)
        self.assertIn("title", job)
        self.assertIn("company", job)
        self.assertIn("location", job)
        self.assertIn("employment_type", job)
        self.assertIn("description", job)
        self.assertIn("application_url", job)
        self.assertEqual(job["source"], "first_party")

    # 21. First-party jobs receive targeted discovery_lane
    def test_21_first_party_targeted_lane(self):
        payload = {"jobs": [{"title": "Frontend Engineer", "id": "FE-1", "url": "/job/1"}]}
        jobs_list, _ = extract_jobs_from_json_payload(payload, "TestCo", "https://testco.com")
        self.assertEqual(jobs_list[0]["discovery_lane"], "targeted")

    # 22. Cross-source deduplication still works
    def test_22_cross_source_deduplication(self):
        fp_job = {
            "source": "first_party",
            "source_job_id": "999",
            "unique_id": "first_party:999:https://www.amazon.jobs/en/jobs/999",
            "company": "Amazon India",
            "title": "Software Development Engineer",
            "location": "Hyderabad",
            "employment_type": "Full-time",
            "description": "Software engineer role",
            "application_url": "https://www.amazon.jobs/en/jobs/999"
        }
        id1 = database.save_job(fp_job, self.db_path)
        adzuna_job = {
            "source": "adzuna",
            "source_job_id": "adzuna-777",
            "unique_id": "first_party:999:https://www.amazon.jobs/en/jobs/999",
            "company": "Amazon India",
            "title": "Software Development Engineer",
            "location": "Hyderabad",
            "employment_type": "Full-time",
            "description": "Software engineer role",
            "application_url": "https://www.amazon.jobs/en/jobs/999"
        }
        id2 = database.save_job(adzuna_job, self.db_path)
        self.assertEqual(id1, id2)

    # 23. last_shown_at rotation still works
    def test_23_last_shown_at_rotation_intact(self):
        j1 = {"source": "first_party", "source_job_id": "1", "unique_id": "fp:1", "company": "Amazon", "title": "SDE 1", "description": "SDE 1", "location": "India", "application_url": "https://amazon.jobs/1"}
        j2 = {"source": "first_party", "source_job_id": "2", "unique_id": "fp:2", "company": "Microsoft", "title": "SWE 1", "description": "SWE 1", "location": "India", "application_url": "https://microsoft.jobs/2"}
        id1 = database.save_job(j1, self.db_path)
        id2 = database.save_job(j2, self.db_path)

        database.mark_jobs_shown([id1], self.db_path)
        eligible = database.get_eligible_candidate_jobs(db_path=self.db_path)
        self.assertEqual(eligible[0]["id"], id2)
        self.assertIsNone(eligible[0]["last_shown_at"])
        self.assertEqual(eligible[1]["id"], id1)
        self.assertIsNotNone(eligible[1]["last_shown_at"])

    # 24. Applied/rejected jobs remain excluded
    def test_24_applied_rejected_jobs_excluded(self):
        job = {
            "source": "first_party", "source_job_id": "1001", "unique_id": "first_party:1001",
            "company": "Microsoft India", "title": "SWE", "location": "Bangalore",
            "employment_type": "Full-time", "description": "SWE", "application_url": "https://microsoft.com/jobs/1001"
        }
        job_id = database.save_job(job, self.db_path)
        database.update_job_status(job_id, "applied", self.db_path)
        eligible = database.get_eligible_candidate_jobs(db_path=self.db_path)
        self.assertNotIn(job_id, [j["id"] for j in eligible])

    # 25. Mocked Microsoft-style payload regression test
    def test_25_mocked_microsoft_payload_regression(self):
        payload = {
            "status": 200,
            "data": {
                "total_positions": 116,
                "positions": [
                    {
                        "id": 1970393556955275,
                        "displayJobId": "200046596",
                        "name": "Software Engineer II",
                        "locations": [
                            "India, Karnataka, Bangalore"
                        ],
                        "positionUrl": "https://apply.careers.microsoft.com/careers/job/1970393556955275"
                    }
                ]
            }
        }
        jobs_list, total = extract_jobs_from_json_payload(payload, "Microsoft India", "https://apply.careers.microsoft.com")
        self.assertEqual(total, 116)
        self.assertEqual(len(jobs_list), 1)
        job = jobs_list[0]
        self.assertEqual(job["title"], "Software Engineer II")
        self.assertIn("Bangalore", job["location"])
        self.assertEqual(job["source"], "first_party")
        self.assertEqual(job["discovery_lane"], "targeted")

    # 26. Google/WIZ AF_initData payload containing valid job tuples is parsed
    def test_26_google_af_init_data_payload_extraction(self):
        html = """
        <html><body>
        <script>
        AF_initDataCallback({
            key: 'ds:1',
            hash: '2',
            data: [
                [
                    [
                        "143775524936655558",
                        "Senior Software Engineer, Control Plane Network",
                        "https://www.google.com/about/careers/applications/signin?jobId=143775524936655558",
                        [null, "<ul><li>Write code.</li></ul>"],
                        [null, "<h3>Qualifications:</h3><p>5 years exp</p>"],
                        "projects/123",
                        null,
                        "Google",
                        "en-US",
                        [["Bengaluru, Karnataka, India", ["3, Old Madras Rd"]]],
                        [null, "<p>Build cloud systems.</p>"]
                    ]
                ],
                null,
                165,
                20
            ],
            sideChannel: {}
        });
        </script>
        </body></html>
        """
        jobs_list, total = fp_mod.extract_jobs_from_af_init_data(html, "Google India", "https://www.google.com/about/careers/applications/jobs/results/")
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(total, 165)
        job = jobs_list[0]
        self.assertEqual(job["title"], "Senior Software Engineer, Control Plane Network")
        self.assertEqual(job["source_job_id"], "143775524936655558")
        self.assertEqual(job["company"], "Google")
        self.assertIn("Bengaluru", job["location"])
        self.assertEqual(job["source"], "first_party")
        self.assertEqual(job["discovery_lane"], "targeted")

    # 27. Google/WIZ AF_initData total count extracted correctly
    def test_27_google_af_init_data_total_count_extraction(self):
        html = """
        <script>
        AF_initDataCallback({
            key: 'ds:1',
            data: [
                [["101", "AI Scientist", "https://google.com/job/101", null, null, null, null, "DeepMind", null, [["London, UK"]]]],
                null,
                240,
                20
            ],
            sideChannel: {}
        });
        </script>
        """
        jobs_list, total = fp_mod.extract_jobs_from_af_init_data(html, "Google DeepMind", "https://google.com")
        self.assertEqual(total, 240)
        self.assertEqual(len(jobs_list), 1)

    # 28. Malformed AF_initData does not crash
    def test_28_malformed_af_init_data_resilience(self):
        html = "<script>AF_initDataCallback({key: 'ds:1', data: invalid_json_syntax, sideChannel: {}})</script>"
        jobs_list, total = fp_mod.extract_jobs_from_af_init_data(html, "Google", "https://google.com")
        self.assertEqual(len(jobs_list), 0)
        self.assertIsNone(total)

    # 29. Non-job AF_initData arrays are ignored
    def test_29_non_job_af_init_data_ignored(self):
        html = """
        <script>
        AF_initDataCallback({
            key: 'ds:0',
            data: [
                [["config_key_1", "config_val_1"], ["config_key_2", "config_val_2"]],
                "metadata"
            ],
            sideChannel: {}
        });
        </script>
        """
        jobs_list, total = fp_mod.extract_jobs_from_af_init_data(html, "Google", "https://google.com")
        self.assertEqual(len(jobs_list), 0)

    # 30. Google-style page=1 and page=2 pagination returns distinct jobs
    def test_30_google_pagination_distinct_jobs(self):
        p1_html = """
        <script>
        AF_initDataCallback({
            key: 'ds:1',
            data: [
                [["101", "Job Page 1", "https://google.com/101", null, null, null, null, "Google", null, [["India"]]]],
                null, 40, 20
            ],
            sideChannel: {}
        });
        </script>
        """
        p2_html = """
        <script>
        AF_initDataCallback({
            key: 'ds:1',
            data: [
                [["102", "Job Page 2", "https://google.com/102", null, null, null, null, "Google", null, [["India"]]]],
                null, 40, 20
            ],
            sideChannel: {}
        });
        </script>
        """
        mock_r1 = MagicMock(status_code=200, text=p1_html)
        mock_r2 = MagicMock(status_code=200, text=p2_html)

        with patch("requests.get", side_effect=[mock_r1, mock_r2]):
            jobs_list, total = fp_mod.probe_first_party_api_or_search(
                "https://www.google.com/about/careers/applications/jobs/results/",
                "Google India"
            )
            self.assertEqual(len(jobs_list), 2)
            self.assertEqual(total, 40)
            self.assertEqual(jobs_list[0]["source_job_id"], "101")
            self.assertEqual(jobs_list[1]["source_job_id"], "102")

    # 31. Navigation links are not extracted as jobs
    def test_31_navigation_links_not_extracted(self):
        html = """
        <div>
            <a href="/about/careers/applications/jobs/results">Jobs</a>
            <a href="/about/careers/applications/jobs/recommendations">Recommended jobs</a>
            <a href="/about/careers/applications/jobs/saved">Saved jobs</a>
            <a href="/about/careers/applications/jobs/alerts">Job alerts</a>
        </div>
        """
        jobs_list = extract_jobs_from_html(html, "https://www.google.com/about/careers/applications/jobs/results/", "Google")
        self.assertEqual(len(jobs_list), 0)

    # 32. EEO, legal, and PDF links excluded
    def test_32_eeo_legal_pdf_links_excluded(self):
        html = """
        <div>
            <a href="/about/careers/applications/eeo">Google's EEO Policy</a>
            <a href="https://careers.google.com/jobs/dist/legal/EEOC_KnowYourRights_10_20.pdf">Know your rights: workplace discrimination is illegal</a>
        </div>
        """
        jobs_list = extract_jobs_from_html(html, "https://www.google.com/about/careers/applications/jobs/results/", "Google")
        self.assertEqual(len(jobs_list), 0)

    # 33. Real DOM job links are still extracted
    def test_33_real_dom_job_links_still_extracted(self):
        html = """
        <div class="job-card">
            <a href="/jobs/12345-backend-engineer">Backend Software Engineer</a>
            <span>Location: Bangalore, India</span>
            <p>Build distributed backend systems at scale.</p>
        </div>
        """
        jobs_list = extract_jobs_from_html(html, "https://careers.example.com", "ExampleCo")
        self.assertEqual(len(jobs_list), 1)
        self.assertEqual(jobs_list[0]["title"], "Backend Software Engineer")
        self.assertIn("Bangalore", jobs_list[0]["location"])

    # 34. Google verification becomes verified_first_party when jobs_available > 0
    def test_34_google_verification_status(self):
        html = """
        <script>
        AF_initDataCallback({
            key: 'ds:1',
            data: [
                [["555", "Cloud Engineer", "https://google.com/555", null, null, null, null, "Google", null, [["Hyderabad, India"]]]],
                null, 165, 20
            ],
            sideChannel: {}
        });
        </script>
        """
        cand_info = {
            "company_name": "Google India",
            "careers_url": "https://www.google.com/about/careers/applications/jobs/results/",
            "ats_platform": "unknown"
        }
        mock_resp = MagicMock(status_code=200, text=html)
        with patch("requests.get", return_value=mock_resp):
            res = company_discovery.verify_discovered_source(cand_info)
            self.assertTrue(res["verified"])
            self.assertEqual(res["verification_status"], "verified_first_party")
            self.assertEqual(res["jobs_available"], 165)


if __name__ == "__main__":
    unittest.main()

