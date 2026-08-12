import os
import sys
import json
import logging
from typing import Dict, Any, List

sys.path.insert(0, ".")

import database
import sources
import jobs

# Configure quiet logging
logging.basicConfig(level=logging.WARNING)

def run_audit():
    print("=== STARTING V1.1.1 REAL-WORLD DISCOVERY SOURCE AUDIT ===")
    
    # 1. Load preferences and candidate profile from DB
    conn = database.get_connection()
    
    cand_row = conn.execute("SELECT profile_json FROM candidate WHERE id=1").fetchone()
    candidate_profile = json.loads(cand_row["profile_json"]) if cand_row else {}
    
    pref_row = conn.execute("SELECT preferences_json FROM preferences WHERE id=1").fetchone()
    preferences = json.loads(pref_row["preferences_json"]) if pref_row else {
        "preferred_roles": ["Software Engineer", "Backend Engineer", "Full Stack Engineer", "Python Engineer", "AI/ML Engineer"],
        "locations": ["India", "Bangalore", "Bengaluru", "Remote", "Hyderabad"],
        "work_modes": ["remote", "hybrid", "onsite"],
        "experience_levels": ["internship", "entry_level"]
    }
    
    # Fetch existing unique_ids for deduplication
    db_rows = conn.execute("SELECT unique_id FROM jobs").fetchall()
    existing_ids = {r["unique_id"] for r in db_rows}
    conn.close()
    
    print("\n--- CANDIDATE PREFERENCES USED FOR AUDIT ---")
    print(json.dumps(preferences, indent=2))
    
    # Load sources config directly from config/sources.json
    sources_config_path = os.path.join("config", "sources.json")
    if os.path.exists(sources_config_path):
        with open(sources_config_path, "r", encoding="utf-8") as f:
            sources_config = json.load(f)
    else:
        sources_config = {}
    
    # Sources list to audit
    source_modules = [
        ("greenhouse", sources.greenhouse),
        ("lever", sources.lever),
        ("ashby", sources.ashby),
        ("workday", sources.workday),
        ("smartrecruiters", sources.smartrecruiters),
        ("taleo", sources.taleo),
        ("icims", sources.icims),
        ("adzuna", sources.adzuna)
    ]
    
    seen_in_run = set()
    audit_results = {}
    sample_jobs = {}

    for source_name, module in source_modules:
        status = "SUCCESS"
        status_detail = ""
        raw_count = 0
        normalized_jobs = []
        
        # Determine configuration status
        if source_name == "adzuna":
            adz_cfg = sources_config.get("adzuna", {})
            has_keys = bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY")) or (adz_cfg.get("app_id") and adz_cfg.get("app_key"))
            if not adz_cfg.get("enabled") and not has_keys:
                status = "DISABLED"
                status_detail = "credentials not configured"
        
        try:
            if status != "DISABLED":
                # Discover jobs directly from adapter
                if source_name == "greenhouse":
                    raw_jobs = module.discover_jobs({"greenhouse_targets": sources_config.get("greenhouse", [])})
                elif source_name == "lever":
                    raw_jobs = module.discover_jobs({"lever_targets": sources_config.get("lever", [])})
                elif source_name == "ashby":
                    raw_jobs = module.discover_jobs({"ashby_targets": sources_config.get("ashby", [])})
                elif source_name == "workday":
                    raw_jobs = module.discover_jobs({"workday_targets": sources_config.get("workday", [])})
                elif source_name == "smartrecruiters":
                    raw_jobs = module.discover_jobs({"smartrecruiters_targets": sources_config.get("smartrecruiters", [])})
                elif source_name == "taleo":
                    t_list = sources_config.get("taleo", [])
                    if isinstance(t_list, dict):
                        t_list = t_list.get("targets", [])
                    raw_jobs = module.discover_jobs({"taleo_targets": t_list})
                elif source_name == "icims":
                    i_list = sources_config.get("icims", [])
                    if isinstance(i_list, dict):
                        i_list = i_list.get("targets", [])
                    raw_jobs = module.discover_jobs({"icims_targets": i_list})
                elif source_name == "adzuna":
                    raw_jobs = module.discover_jobs(sources_config.get("adzuna", {}))
                else:
                    raw_jobs = []

                raw_count = len(raw_jobs)
                normalized_jobs = raw_jobs
                
                if raw_count == 0:
                    if status == "SUCCESS":
                        status = "ZERO_JOBS"
                        status_detail = "source returned zero jobs"
        except Exception as e:
            status = "ERROR"
            status_detail = str(e)
            raw_count = 0
            normalized_jobs = []

        # Pipeline tracking
        dup_count = 0
        filter_breakdown = {
            "negative_title": 0,
            "profession_mismatch": 0,
            "senior_experience": 0,
            "extreme_experience": 0,
            "employment_type_mismatch": 0,
            "location_mismatch": 0,
            "salary_mismatch": 0,
            "other_filter": 0
        }
        filtered_count = 0
        eligible_jobs = []
        india_jobs_count = 0
        intern_jobs_count = 0

        for job in normalized_jobs:
            uid = job.get("unique_id")
            
            # Check India relevance
            loc_str = (job.get("location") or "").lower()
            title_str = (job.get("title") or "").lower()
            
            is_india = any(kw in loc_str or kw in title_str for kw in [
                "india", "bangalore", "bengaluru", "mumbai", "delhi", "noida", 
                "gurgaon", "gurugram", "hyderabad", "pune", "chennai", "kolkata", 
                "remote-india", "india remote"
            ])
            if is_india:
                india_jobs_count += 1

            # Check Internship / Early Career relevance
            is_intern = jobs.has_pattern(title_str, jobs.INTERN_PATTERNS) or \
                        jobs.has_pattern(title_str, jobs.ENTRY_PATTERNS) or \
                        any(kw in (job.get("employment_type") or "").lower() for kw in ["intern", "internship", "entry"])
            if is_intern:
                intern_jobs_count += 1

            # Deduplication
            if uid in existing_ids or uid in seen_in_run:
                dup_count += 1
                continue
            seen_in_run.add(uid)

            # Hard filtering evaluation
            is_filtered, reason = jobs.is_hard_filtered(job, preferences, candidate_profile)
            if is_filtered:
                filtered_count += 1
                r_lower = reason.lower()
                if "negative title" in r_lower or "unrelated" in r_lower:
                    filter_breakdown["negative_title"] += 1
                elif "profession" in r_lower:
                    filter_breakdown["profession_mismatch"] += 1
                elif "senior" in r_lower:
                    filter_breakdown["senior_experience"] += 1
                elif "extreme" in r_lower:
                    filter_breakdown["extreme_experience"] += 1
                elif "employment type" in r_lower or "full-time" in r_lower:
                    filter_breakdown["employment_type_mismatch"] += 1
                elif "location" in r_lower:
                    filter_breakdown["location_mismatch"] += 1
                elif "salary" in r_lower:
                    filter_breakdown["salary_mismatch"] += 1
                else:
                    filter_breakdown["other_filter"] += 1
            else:
                eligible_jobs.append(job)

        audit_results[source_name] = {
            "status": status if status != "SUCCESS" else ("SUCCESS" if len(eligible_jobs) > 0 else "ALL_FILTERED"),
            "status_detail": status_detail,
            "raw": raw_count,
            "normalized": len(normalized_jobs),
            "duplicates": dup_count,
            "filtered": filtered_count,
            "filter_breakdown": filter_breakdown,
            "eligible": len(eligible_jobs),
            "india_relevant": india_jobs_count,
            "internship_relevant": intern_jobs_count
        }

        # Store sample representative jobs (up to 5)
        sample_pool = eligible_jobs if eligible_jobs else normalized_jobs
        sample_jobs[source_name] = []
        for j in sample_pool[:5]:
            sample_jobs[source_name].append({
                "company": j.get("company"),
                "title": j.get("title"),
                "location": j.get("location"),
                "employment_type": j.get("employment_type"),
                "work_mode": j.get("work_mode") or "not_specified",
                "salary": j.get("salary_text") or "not_specified",
                "source": j.get("source"),
                "job_url": j.get("job_url") or j.get("application_url")
            })

    # Output clean JSON
    print("\n--- DETAILED AUDIT RESULTS JSON ---")
    print(json.dumps({"summary": audit_results, "samples": sample_jobs}, indent=2))

if __name__ == "__main__":
    run_audit()
