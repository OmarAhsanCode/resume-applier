import os
import sys
import json
import logging

sys.path.insert(0, ".")

import database
import sources
import jobs

logging.basicConfig(level=logging.WARNING)

def investigate():
    print("=== PART 1: INVESTIGATING ZERO-ELIGIBLE ANOMALY ===")
    
    conn = database.get_connection()
    cand_row = conn.execute("SELECT profile_json FROM candidate WHERE id=1").fetchone()
    candidate_profile = json.loads(cand_row["profile_json"]) if cand_row else {}
    
    pref_row = conn.execute("SELECT preferences_json FROM preferences WHERE id=1").fetchone()
    preferences = json.loads(pref_row["preferences_json"]) if pref_row else {
        "preferred_roles": ["SDE Interm", "Software Engineer", "Ai Automation Engineer"],
        "locations": ["Remote", "Lucknow", "New York", "Hyderabad"],
        "work_modes": ["remote", "hybrid", "onsite"],
        "experience_levels": ["internship", "entry_level"]
    }
    conn.close()
    
    sources_config_path = os.path.join("config", "sources.json")
    with open(sources_config_path, "r", encoding="utf-8") as f:
        sources_config = json.load(f)

    sources_to_check = [
        ("greenhouse", sources.greenhouse, "greenhouse_targets"),
        ("lever", sources.lever, "lever_targets"),
        ("ashby", sources.ashby, "ashby_targets")
    ]

    rejection_breakdown = {}

    for source_name, module, target_key in sources_to_check:
        print(f"\n--- Analyzing {source_name.upper()} ---")
        raw_jobs = module.discover_jobs({target_key: sources_config.get(source_name, [])})
        
        intern_entry_jobs = []
        for job in raw_jobs:
            title_str = (job.get("title") or "").lower()
            emp_type_str = (job.get("employment_type") or "").lower()
            
            is_intern_entry = jobs.has_pattern(title_str, jobs.INTERN_PATTERNS) or \
                              jobs.has_pattern(title_str, jobs.ENTRY_PATTERNS) or \
                              any(kw in emp_type_str for kw in ["intern", "internship", "entry"])
            if is_intern_entry:
                intern_entry_jobs.append(job)

        print(f"Total raw jobs fetched: {len(raw_jobs)}")
        print(f"Total internship/entry-level jobs identified: {len(intern_entry_jobs)}")

        rejection_breakdown[source_name] = {
            "total_intern_entry": len(intern_entry_jobs),
            "location_mismatch": 0,
            "senior_experience": 0,
            "employment_type_mismatch": 0,
            "negative_title": 0,
            "profession_mismatch": 0,
            "salary_mismatch": 0,
            "eligible": 0,
            "reasons": []
        }

        for j in intern_entry_jobs:
            is_filtered, reason = jobs.is_hard_filtered(j, preferences, candidate_profile)
            r_lower = reason.lower()
            
            if not is_filtered:
                rejection_breakdown[source_name]["eligible"] += 1
            else:
                rejection_breakdown[source_name]["reasons"].append({
                    "company": j.get("company"),
                    "title": j.get("title"),
                    "location": j.get("location"),
                    "employment_type": j.get("employment_type"),
                    "reason": reason
                })
                
                if "location" in r_lower:
                    rejection_breakdown[source_name]["location_mismatch"] += 1
                elif "senior" in r_lower or "extreme" in r_lower:
                    rejection_breakdown[source_name]["senior_experience"] += 1
                elif "employment type" in r_lower or "full-time" in r_lower:
                    rejection_breakdown[source_name]["employment_type_mismatch"] += 1
                elif "negative title" in r_lower or "unrelated" in r_lower:
                    rejection_breakdown[source_name]["negative_title"] += 1
                elif "profession" in r_lower:
                    rejection_breakdown[source_name]["profession_mismatch"] += 1
                elif "salary" in r_lower:
                    rejection_breakdown[source_name]["salary_mismatch"] += 1

    print("\n=== REJECTION BREAKDOWN SUMMARY JSON ===")
    print(json.dumps(rejection_breakdown, indent=2))

if __name__ == "__main__":
    investigate()
