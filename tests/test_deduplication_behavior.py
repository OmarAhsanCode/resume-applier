"""
test_deduplication_behavior.py

Regression test suite for cross-run job deduplication, rotation, and last_shown_at semantics.

Enforces:
1. A job stored in SQLite is NOT permanently excluded.
2. last_shown_at is set ONLY when a job is actually surfaced/selected for the user.
3. Never-shown jobs (last_shown_at IS NULL) have highest selection priority.
4. Previously-shown jobs are used only as fallback when never-shown jobs are insufficient.
5. Recently-shown jobs do NOT immediately recycle into the next run (stale first).
6. Applied and rejected jobs remain permanently excluded.
7. Within-run duplicates increment duplicate_count and are excluded.
8. Cross-run re-discovery is NOT counted as a duplicate.
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
    # Test 1: Run 1 has 20 eligible new jobs -> Request 10 -> Select 10.
    # Run 2 requests 10 -> Must return remaining 10 never-shown jobs.
    # ------------------------------------------------------------------ #
    def test_scenario_1_disjoint_selection_across_runs(self):
        """Run 1 has 20 new jobs, requests 10. Run 2 requests 10 -> returns remaining 10 never-shown jobs."""
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 21)]
        res1 = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res1["selected_count"], 10)
        selected_run1 = {j["unique_id"] for j in database.get_all_jobs(status_filter="selected", db_path=self.db_path)}
        self.assertEqual(len(selected_run1), 10)

        # Run 2 with same discovered jobs
        res2 = self._run_pipeline(discovered, requested=10)
        self.assertEqual(res2["selected_count"], 10)

        conn = database.get_connection(self.db_path)
        all_selected_rows = conn.execute("SELECT unique_id FROM jobs WHERE status = 'selected'").fetchall()
        conn.close()

        # In total, all 20 jobs must have been selected across the 2 runs
        selected_all = {r["unique_id"] for r in all_selected_rows}
        self.assertEqual(len(selected_all), 20)

    # ------------------------------------------------------------------ #
    # Test 2: Run 1 has 20 eligible jobs -> Request 5 -> Only 5 marked shown.
    # Run 2 requests 5 -> Must select from remaining 15 never-shown jobs.
    # ------------------------------------------------------------------ #
    def test_scenario_2_only_surfaced_jobs_marked_shown(self):
        """Run 1 requests 5 -> 5 marked shown. Run 2 requests 5 -> selects from remaining 15 never-shown jobs."""
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 21)]
        res1 = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res1["selected_count"], 5)

        run1_selected = {j["unique_id"] for j in database.get_all_jobs(status_filter="selected", db_path=self.db_path)}
        self.assertEqual(len(run1_selected), 5)

        res2 = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res2["selected_count"], 5)

        # Check jobs selected in Run 2 (most recently updated last_shown_at)
        conn = database.get_connection(self.db_path)
        rows = conn.execute("SELECT unique_id FROM jobs WHERE status = 'selected' ORDER BY last_shown_at DESC LIMIT 5").fetchall()
        conn.close()
        run2_selected = {r["unique_id"] for r in rows}

        self.assertTrue(run2_selected.isdisjoint(run1_selected), f"Run 2 selected {run2_selected} which overlaps Run 1 {run1_selected}")

    # ------------------------------------------------------------------ #
    # Test 3: Run 1 selects 5 -> Run 2 has no new jobs.
    # Previously shown jobs used only according to stale/recycle policy.
    # ------------------------------------------------------------------ #
    def test_scenario_3_recycle_previously_shown_when_unseen_depleted(self):
        """Run 1 selects 5. Run 2 has no new jobs and all 5 shown. Recycles oldest shown first."""
        base_time = datetime.now() - timedelta(days=2)
        for i in range(1, 6):
            shown_at = (base_time + timedelta(hours=i)).isoformat()
            _insert_job(f"gh:{i}", self.db_path, status="selected", last_shown_at=shown_at)

        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 6)]
        res = self._run_pipeline(discovered, requested=2)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["selected_count"], 2)

        # Must recycle oldest shown jobs (gh:1 and gh:2)
        conn = database.get_connection(self.db_path)
        rows = conn.execute("SELECT unique_id FROM jobs ORDER BY last_shown_at DESC LIMIT 2").fetchall()
        conn.close()
        recently_updated = {r["unique_id"] for r in rows}
        self.assertEqual(recently_updated, {"gh:1", "gh:2"})

    # ------------------------------------------------------------------ #
    # Test 4: Applied/rejected jobs are never returned.
    # ------------------------------------------------------------------ #
    def test_scenario_4_applied_and_rejected_permanently_excluded(self):
        """Applied and rejected jobs are never returned in results."""
        _insert_job("gh:applied", self.db_path, status="applied")
        _insert_job("gh:rejected", self.db_path, status="rejected")
        _insert_job("gh:eligible", self.db_path, status="new")

        discovered = [_make_discovered("gh:applied"), _make_discovered("gh:rejected"), _make_discovered("gh:eligible")]
        res = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res["status"], "completed")

        selected = database.get_all_jobs(status_filter="selected", db_path=self.db_path)
        selected_ids = {j["unique_id"] for j in selected}
        self.assertNotIn("gh:applied", selected_ids)
        self.assertNotIn("gh:rejected", selected_ids)
        self.assertIn("gh:eligible", selected_ids)

    # ------------------------------------------------------------------ #
    # Test 5: Same job twice in one discovery run increments duplicate_count.
    # ------------------------------------------------------------------ #
    def test_scenario_5_within_run_duplicate_count(self):
        """Same job twice in one discovery run increments duplicate_count and is excluded."""
        discovered = [_make_discovered("gh:1"), _make_discovered("gh:1")]
        res = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res["discovered_count"], 2)
        self.assertEqual(res["duplicate_count"], 1)

    # ------------------------------------------------------------------ #
    # Test 6: A job discovered again in a later run is not counted as duplicate.
    # ------------------------------------------------------------------ #
    def test_scenario_6_cross_run_rediscovery_not_duplicate(self):
        """A job discovered again in a later run is not counted as a duplicate."""
        discovered = [_make_discovered("gh:1")]
        res1 = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res1["duplicate_count"], 0)

        res2 = self._run_pipeline(discovered, requested=5)
        self.assertEqual(res2["duplicate_count"], 0)

    # ------------------------------------------------------------------ #
    # Test 7: Verify last_shown_at is updated ONLY for jobs surfaced to user.
    # ------------------------------------------------------------------ #
    def test_scenario_7_last_shown_at_updated_only_for_surfaced_jobs(self):
        """10 jobs discovered, requested 3. Only the 3 selected jobs get last_shown_at set."""
        discovered = [_make_discovered(f"gh:{i}") for i in range(1, 11)]
        res = self._run_pipeline(discovered, requested=3)
        self.assertEqual(res["selected_count"], 3)

        conn = database.get_connection(self.db_path)
        rows = conn.execute("SELECT unique_id, last_shown_at FROM jobs").fetchall()
        conn.close()

        shown_jobs = [r["unique_id"] for r in rows if r["last_shown_at"] is not None]
        unshown_jobs = [r["unique_id"] for r in rows if r["last_shown_at"] is None]

        self.assertEqual(len(shown_jobs), 3)
        self.assertEqual(len(unshown_jobs), 7)


if __name__ == "__main__":
    unittest.main()
