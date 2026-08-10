import unittest
from sources.base import create_normalized_job, build_unique_id, normalize_url

class TestJobSources(unittest.TestCase):
    def test_normalize_url(self):
        url = "https://jobs.lever.co/company/abc12345/  "
        normalized = normalize_url(url)
        self.assertEqual(normalized, "https://jobs.lever.co/company/abc12345")

    def test_unique_id_generation(self):
        # Preferred: source:source_job_id
        uid1 = build_unique_id("Greenhouse", "123456", "https://boards.greenhouse.io/company/jobs/123456")
        self.assertEqual(uid1, "greenhouse:123456")

        # Fallback: source:normalized_url when job_id is missing
        uid2 = build_unique_id("Lever", None, "https://jobs.lever.co/company/abc12345/")
        self.assertEqual(uid2, "lever:https://jobs.lever.co/company/abc12345")

    def test_create_normalized_job(self):
        job = create_normalized_job(
            source="Ashby",
            source_job_id="987654",
            company="Tech Corp",
            title="Senior Python Developer",
            location="Remote",
            employment_type="Full-time",
            description="Python & Flask job",
            application_url="https://jobs.ashbyhq.com/company/987654"
        )
        self.assertEqual(job["source"], "ashby")
        self.assertEqual(job["unique_id"], "ashby:987654")
        self.assertEqual(job["company"], "Tech Corp")
        self.assertEqual(job["title"], "Senior Python Developer")

if __name__ == "__main__":
    unittest.main()
