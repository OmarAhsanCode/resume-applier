import unittest
from unittest.mock import patch, MagicMock
import os
import sources
from sources.base import create_normalized_job, normalize_url, detect_work_mode

class TestDiscoveryV1_1Phase1(unittest.TestCase):

    def test_1_normalized_job_schema_extensions(self):
        job = create_normalized_job(
            source="workday",
            source_job_id="WD1001",
            company="Adobe",
            title="Senior Software Engineer - Remote",
            location="San Jose, CA",
            employment_type="full_time",
            description="Build scalable cloud systems. Remote eligible.",
            application_url="https://adobe.wd5.myworkdayjobs.com/jobs/1001",
            posted_date="2026-08-01",
            salary_text="$150,000/year",
            job_url="https://adobe.wd5.myworkdayjobs.com/jobs/1001",
            apply_url="https://adobe.wd5.myworkdayjobs.com/jobs/1001/apply"
        )
        
        self.assertEqual(job["source"], "workday")
        self.assertEqual(job["source_job_id"], "WD1001")
        self.assertEqual(job["unique_id"], "workday:WD1001")
        self.assertEqual(job["company"], "Adobe")
        self.assertEqual(job["work_mode"], "remote")
        self.assertEqual(job["salary_text"], "$150,000/year")
        self.assertIn("/apply", job["apply_url"])
        self.assertEqual(job["posted_at"], "2026-08-01")

    def test_2_source_registry_integrity(self):
        self.assertTrue(hasattr(sources, "SOURCES"))
        registered_names = [s["name"] for s in sources.SOURCES]
        self.assertIn("greenhouse", registered_names)
        self.assertIn("lever", registered_names)
        self.assertIn("ashby", registered_names)
        self.assertIn("workday", registered_names)
        self.assertIn("smartrecruiters", registered_names)
        self.assertIn("taleo", registered_names)

    @patch("requests.post")
    def test_3_workday_discovery_adapter(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Software Engineer Intern",
                    "externalPath": "/job/R12345",
                    "locationsText": "Bangalore, India",
                    "postedOn": "2026-08-10",
                    "timeType": "Full time"
                }
            ]
        }
        mock_post.return_value = mock_resp

        jobs = sources.workday.discover_jobs({"workday_targets": [{"company": "TestCorp", "host": "test.wd.com", "tenant": "jobs"}]})
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["source"], "workday")
        self.assertEqual(j["company"], "TestCorp")
        self.assertEqual(j["title"], "Software Engineer Intern")
        self.assertEqual(j["location"], "Bangalore, India")
        self.assertIn("/apply", j["apply_url"])

    @patch("requests.get")
    def test_4_smartrecruiters_discovery_adapter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [
                {
                    "id": "sr_9988",
                    "name": "Backend Intern",
                    "company": {"name": "Square"},
                    "location": {"city": "Hyderabad", "country": "India", "remote": True},
                    "typeOfEmployment": {"label": "Internship"},
                    "releasedDate": "2026-08-05T00:00:00Z"
                }
            ]
        }
        mock_get.return_value = mock_resp

        jobs = sources.smartrecruiters.discover_jobs({"smartrecruiters_companies": ["Square"]})
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["source"], "smartrecruiters")
        self.assertEqual(j["company"], "Square")
        self.assertEqual(j["title"], "Backend Intern")
        self.assertEqual(j["employment_type"], "internship")
        self.assertEqual(j["posted_at"], "2026-08-05")

    @patch("requests.get")
    def test_5_taleo_discovery_adapter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>AI Developer Intern</title>
                    <link>https://oracle.taleo.net/careersection/2/jobdetail.ftl?job=20000XYZ</link>
                    <description>AI Developer Internship role.</description>
                </item>
            </channel>
        </rss>"""
        mock_get.return_value = mock_resp

        jobs = sources.taleo.discover_jobs({"taleo_targets": [{"company": "Oracle", "career_url": "https://oracle.taleo.net/rss"}]})
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["source"], "taleo")
        self.assertEqual(j["company"], "Oracle")
        self.assertEqual(j["title"], "AI Developer Intern")
        self.assertEqual(j["source_job_id"], "20000XYZ")

    @patch("requests.get")
    def test_6_icims_discovery_adapter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<html><body><a href="/jobs/12345/view">Software Engineering Intern</a></body></html>"""
        mock_get.return_value = mock_resp

        jobs = sources.icims.discover_jobs({"icims_targets": [{"company": "Microsoft", "portal_url": "https://careers.microsoft.com"}]})
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["source"], "icims")
        self.assertEqual(j["company"], "Microsoft")
        self.assertEqual(j["title"], "Software Engineering Intern")
        self.assertEqual(j["source_job_id"], "12345")

    @patch("requests.get")
    def test_7_adzuna_discovery_adapter_configured(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "adz_5544",
                    "title": "Machine Learning Intern",
                    "company": {"display_name": "Flipkart"},
                    "location": {"display_name": "Bangalore, India"},
                    "contract_time": "full_time",
                    "description": "ML Intern role",
                    "redirect_url": "https://adzuna.in/job/5544",
                    "created": "2026-08-08T10:00:00Z"
                }
            ]
        }
        mock_get.return_value = mock_resp

        jobs = sources.adzuna.discover_jobs({"adzuna_app_id": "test_id", "adzuna_app_key": "test_key", "query": "machine learning intern"})
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["source"], "adzuna")
        self.assertEqual(j["company"], "Flipkart")
        self.assertEqual(j["title"], "Machine Learning Intern")
        self.assertEqual(j["posted_at"], "2026-08-08")

    def test_8_adzuna_unconfigured_skips_gracefully(self):
        jobs = sources.adzuna.discover_jobs({"adzuna_app_id": "", "adzuna_app_key": ""})
        self.assertEqual(jobs, [])

    def test_9_india_companies_seed_list_exists(self):
        config_path = os.path.join("config", "companies.json")
        self.assertTrue(os.path.exists(config_path))
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            companies = json.load(f)
        self.assertTrue(isinstance(companies, list))
        self.assertGreaterEqual(len(companies), 5)
        names = [c["company"] for c in companies]
        self.assertIn("Microsoft India", names)

    def test_10_query_expansion(self):
        from sources.base import expand_query_title
        synonyms = expand_query_title("Software Engineer Intern")
        self.assertIn("Software Engineer Intern", synonyms)
        self.assertIn("Software Developer Intern", synonyms)
        self.assertIn("SWE Intern", synonyms)

    def test_11_role_family_classification(self):
        from sources.base import classify_role_family
        self.assertEqual(classify_role_family("AI Engineering Intern"), "artificial_intelligence")
        self.assertEqual(classify_role_family("Backend Developer"), "backend")
        self.assertEqual(classify_role_family("React Frontend Developer"), "frontend")
        self.assertEqual(classify_role_family("ML Research Engineer"), "machine_learning")

    def test_12_evidence_classifiers(self):
        from sources.base import classify_experience_evidence, classify_location_evidence, classify_salary_evidence
        self.assertEqual(classify_experience_evidence("Software Engineering Intern"), "explicit_internship")
        self.assertEqual(classify_experience_evidence("Junior Software Engineer"), "explicit_entry_level")
        self.assertEqual(classify_location_evidence("Remote - US/India"), "explicit_remote")
        self.assertEqual(classify_location_evidence("Hybrid - Bangalore"), "explicit_hybrid_city")
        self.assertEqual(classify_salary_evidence("₹50,000/month stipend"), "explicit_inr")

    def test_13_negative_title_filtering(self):
        from sources.base import is_negative_title_match
        is_neg, reason = is_negative_title_match("Technical Recruiter")
        self.assertTrue(is_neg)
        self.assertIn("Negative title pattern match", reason)

        is_neg2, _ = is_negative_title_match("Software Engineering Intern")
        self.assertFalse(is_neg2)

    def test_14_source_quality_weights(self):
        from sources.base import calculate_source_quality
        self.assertEqual(calculate_source_quality("greenhouse"), 0.95)
        self.assertEqual(calculate_source_quality("workday"), 0.95)
        self.assertEqual(calculate_source_quality("adzuna"), 0.80)
        self.assertEqual(calculate_source_quality("career_page"), 1.00)

    def test_15_freshness_scoring(self):
        from sources.base import calculate_freshness_score
        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%Y-%m-%d")
        old_str = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        self.assertEqual(calculate_freshness_score(today_str), 100.0)
        self.assertEqual(calculate_freshness_score(old_str), 50.0)

if __name__ == "__main__":
    unittest.main()
