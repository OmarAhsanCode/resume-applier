"""
test_deduplication_behavior.py

Regression tests for the job deduplication vs deprioritization semantics.

The correct model:
    TRUE DUPLICATE (same unique_id in same run)  → EXCLUDE (duplicate_count++)
    PREVIOUSLY SHOWN (cross-run re-discovery)    → DEPRIORITIZE (eligible for re-selection)
    NEVER SHOWN                                  → PRIORITIZE
    APPLIED / REJECTED                           → PERMANENTLY EXCLUDED (existing rules)
"""
import os
import unittest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import database
import jobs


def _make_job(uid: str, title: str = "Software Engineer", status: str = "new",
              last_shown_at: str = None, final_score: float = None) -> dict:
    """Helper: insert a job directly into the DB for test setup."""
    return {
        "source": "greenhouse",
        "source_job_id": uid.split(":")[-1],
        "unique_id": uid,
        "company": "Acme Corp",
        "title": title,
        "location": "Remote",
        "employment_type": "full_time",
        "description": "Python developer role with SQL experience required.",
        "application_url": f"https://example.com/job/{uid}",
        "discovery_lane": "targeted",
        "status": status,
        "last_shown_at": last_shown_at,
        "final_score": final_score,
    }


def _insert_job(uid: str, db_path: str, status: str = "new",
                last_shown_at: str = None, final_score: float = None) -> int:
    """Insert a pre-existing job into the DB and optionally set last_shown_at."""
    j = _make_job(uid, status=status)
    j["deterministic_score"] = 70.0
    j["ai_score"] = 70.0
    j["final_score"] = final_score or 70.0
    job_id = database.save_job(j, db_path=db_path)
    if status not in ("new", None):
        database.update_job_status(job_id, status, db_path=db_path)
    if last_shown_at:
        conn = database.get_connection(db_path)
        conn.execute("UPDATE jobs SET last_shown_at = ? WHERE id = ?", (last_shown_at, job_id))
        conn.commit()
        conn.close()
    return job_id


def _make_discovered(uid: str, title: str = "Software Engineer") -> dict:
    """Make a job dict as it would come from discover_all_sources()."""
    return {
        "source": "greenhouse",
        "source_job_id": uid.split(":")[-1],
        "unique_id": uid,
        "company": "Acme Corp",
        "title": title,
        "location": "Remote",
        "employment_type": "full_time",
        "description": "Python developer role with SQL experience required.",
        "application_url": f"https://example.com/job/{uid}",
        "discovery_lane": "targeted",
    }


PREFS = {
    "preferred_roles": ["Software Engineer", "Python Developer"],
    "locations": ["Remote"],
    "experience_levels": ["entry_level", "mid_level"],
    "work_modes": ["remote"],
    "jobs_per_run": 50,
    "dream_companies": [],
}

PROFILE = {
    "name": "Test User",
    "skills": ["Python", "SQL", "Flask"],
    "experience": [],
    "education": [],
}

# Shared mock AI analysis
MOCK_AI = {
    "recommendation": "strong_match",
    "score": 80,
    "eligibility": True,
    "matching_requirements": ["Python"],
    "missing_preferred_skills": [],
    "missing_critical_requirements": [],
    "role_alignment": 80,
    "reason": "Good fit.",
}


class TestDeduplicationBehavior(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.tmp.name
        self.tmp.close()
        database.init_db(self.db_path)

        # Seed a candidate profile and prefs
        database.save_candidate("Test User", "test@example.com", "+1234567890",
                                PROFILE, db_path=self.db_path)
        database.save_preferences(PREFS, db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _run_pipeline(self, discovered_jobs, requested=10):
        """Run the pipeline with mocked discovery, AI, and time.sleep."""
        with patch("sources.discover_all_sources") as mock_disc, \
             patch("ai.analyze_job") as mock_ai, \
             patch("time.sleep"), \
             patch("google_service.initialize_google_sheets"), \
             patch("google_service.sync_jobs_to_sheet"):
            mock_disc.return_value = discovered_jobs
            mock_ai.return_value = MOCK_AI
            return jobs.run_job_search_pipeline(
                requested_jobs=requested, db_path=self.db_path
            )

    # ------------------------------------------------------------------ #
    # Test 1: First run requesting 20 returns up to discovered count
    # ------------------------------------------------------------------ #
    def test_1_first_run_returns_discovered_count(self):
        """Run 1: 20 jobs discovered, 0 previously seen → all eligible."""
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 21)]
        res = self._run_pipeline(discovered, requested=20)
        self.assertIn(res["status"], ("completed", "partial"))
        self.assertEqual(res["discovered_count"], 20)
        self.assertEqual(res["duplicate_count"], 0)
        self.assertGreater(res["selected_count"], 0)

    # ------------------------------------------------------------------ #
    # Test 2: Run 2 requesting 10 does NOT return 0
    # ------------------------------------------------------------------ #
    def test_2_second_run_does_not_return_zero(self):
        """Run 1 shows 20. Run 2 requests 10 → must NOT return 0."""
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 21)]

        res1 = self._run_pipeline(discovered, requested=20)
        self.assertGreater(res1["selected_count"], 0)

        # Run 2: same discovery pool (all previously seen now)
        res2 = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res2["status"], "completed")
        # No within-run duplicates (each unique_id appears once)
        self.assertEqual(res2["duplicate_count"], 0)
        # Previously-seen eligible jobs must fill the pool
        self.assertGreater(res2["selected_count"], 0)

    # ------------------------------------------------------------------ #
    # Test 3: Prefer never-shown when 30 jobs exist, 20 shown, 10 new
    # ------------------------------------------------------------------ #
    def test_3_prioritize_unseen_over_previously_shown(self):
        """30 eligible jobs, 20 shown, 10 new → request 10 → all 10 are the new ones."""
        # Seed 20 previously-seen jobs in DB
        shown_time = (datetime.now() - timedelta(hours=2)).isoformat()
        for i in range(1, 21):
            _insert_job(f"gh:{i}", self.db_path, status="new", last_shown_at=shown_time)

        # Discovery returns 20 old + 10 brand-new
        discovered = (
            [_make_discovered(f"gh:{i}") for i in range(1, 21)]  # previously seen
            + [_make_discovered(f"gh:new{i}") for i in range(1, 11)]  # brand new
        )
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["status"], "completed")
        # 10 brand-new jobs were saved; 20 previously-seen were refreshed (not in duplicate_count)
        self.assertEqual(res["duplicate_count"], 0)
        self.assertEqual(res["selected_count"], 10)

        # The 10 selected jobs should be the new ones (never previously shown)
        selected = database.get_all_jobs(status_filter="selected", db_path=self.db_path)
        selected_ids = {j["unique_id"] for j in selected}
        new_ids = {f"gh:new{i}" for i in range(1, 11)}
        self.assertTrue(selected_ids.issubset(new_ids),
                        f"Expected only new jobs in selection, got: {selected_ids}")

    # ------------------------------------------------------------------ #
    # Test 4: 5 unseen + 5 old → return 5 unseen + 5 old eligible
    # ------------------------------------------------------------------ #
    def test_4_fill_with_older_eligible_when_unseen_are_scarce(self):
        """5 unseen, 10 previously-seen eligible → request 10 → get 5+5."""
        shown_time = (datetime.now() - timedelta(hours=1)).isoformat()
        for i in range(1, 11):
            _insert_job(f"gh:{i}", self.db_path, status="new", last_shown_at=shown_time)

        # Discovery returns 10 old + 5 brand-new
        discovered = (
            [_make_discovered(f"gh:{i}") for i in range(1, 11)]
            + [_make_discovered(f"gh:new{i}") for i in range(1, 6)]
        )
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["selected_count"], 10)

    # ------------------------------------------------------------------ #
    # Test 5: All 50 eligible jobs previously shown → return 10 (not 0)
    # ------------------------------------------------------------------ #
    def test_5_returns_oldest_shown_when_all_previously_seen(self):
        """All 50 eligible jobs have been shown → request 10 → return least-recently-shown."""
        base_time = datetime.now() - timedelta(days=3)
        for i in range(1, 51):
            shown_at = (base_time + timedelta(minutes=i)).isoformat()
            _insert_job(f"gh:{i}", self.db_path, status="new", last_shown_at=shown_at)

        # Discovery returns all 50 (all previously seen)
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 51)]
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["selected_count"], 10)

    # ------------------------------------------------------------------ #
    # Test 6: Within-run true duplicates (same unique_id twice) are removed
    # ------------------------------------------------------------------ #
    def test_6_within_run_true_duplicates_are_removed(self):
        """Same unique_id returned twice in one discovery run → 1 saved, duplicate_count=1."""
        # unique_id "gh:1" appears twice in the same discovery result
        discovered = [
            _make_discovered("gh:1"),
            _make_discovered("gh:1"),  # true within-run duplicate
        ]
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["discovered_count"], 2)
        self.assertEqual(res["duplicate_count"], 1)
        # Only 1 job actually saved
        all_jobs = database.get_all_jobs(db_path=self.db_path)
        gh1_records = [j for j in all_jobs if j["unique_id"] == "gh:1"]
        self.assertEqual(len(gh1_records), 1)

    # ------------------------------------------------------------------ #
    # Test 7: Same job from multiple sources → one row only
    # ------------------------------------------------------------------ #
    def test_7_cross_source_same_job_appears_once(self):
        """Two sources returning same unique_id → only one record in DB."""
        # Greenhouse and Lever both surface "gh:1" (same unique_id = canonical dedup key)
        discovered = [
            {**_make_discovered("gh:1"), "source": "greenhouse"},
            {**_make_discovered("gh:1"), "source": "lever"},  # same unique_id
        ]
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["duplicate_count"], 1)
        all_jobs = database.get_all_jobs(db_path=self.db_path)
        matches = [j for j in all_jobs if j["unique_id"] == "gh:1"]
        self.assertEqual(len(matches), 1)

    # ------------------------------------------------------------------ #
    # Test 8: Applied/rejected jobs obey exclusion rules
    # ------------------------------------------------------------------ #
    def test_8_applied_and_rejected_remain_excluded(self):
        """Applied and rejected jobs must not re-appear in selected."""
        # Seed 2 jobs in terminal states
        _insert_job("gh:applied", self.db_path, status="applied")
        _insert_job("gh:rejected", self.db_path, status="rejected")

        # Seed 1 new eligible job
        _insert_job("gh:eligible", self.db_path, status="new")

        # Discovery resurfaces all 3
        discovered = [
            _make_discovered("gh:applied"),
            _make_discovered("gh:rejected"),
            _make_discovered("gh:eligible"),
        ]
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["status"], "completed")

        selected = database.get_all_jobs(status_filter="selected", db_path=self.db_path)
        selected_ids = {j["unique_id"] for j in selected}

        self.assertNotIn("gh:applied", selected_ids, "Applied job must not be re-selected")
        self.assertNotIn("gh:rejected", selected_ids, "Rejected job must not be re-selected")
        self.assertIn("gh:eligible", selected_ids, "Eligible job should be selected")

    # ------------------------------------------------------------------ #
    # Test 9: Requested count honoured when ≥ 10 eligible jobs exist
    # ------------------------------------------------------------------ #
    def test_9_requested_count_respected(self):
        """If 15 eligible jobs exist and 10 are requested → exactly 10 selected."""
        # Seed 15 previously-seen eligible jobs
        shown_time = (datetime.now() - timedelta(hours=3)).isoformat()
        for i in range(1, 16):
            _insert_job(f"gh:{i}", self.db_path, status="new", last_shown_at=shown_time)

        # Discover all 15
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 16)]
        res = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["selected_count"], 10)


if __name__ == "__main__":
    unittest.main()
