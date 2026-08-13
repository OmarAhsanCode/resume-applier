import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import database
import sources
import ai
import resume
import google_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Conservative Hard Filtering
# ---------------------------------------------------------------------------

SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b", r"\blead\b",
    r"\bmanager\b", r"\bdirector\b", r"\bhead\b", r"\barchitect\b", r"\bdistinguished\b",
    r"\bvp\b", r"\bvice\s+president\b", r"\bchief\b"
]

INTERN_PATTERNS = [
    r"\bintern\b", r"\binternship\b", r"\bco-op\b", r"\bcoop\b",
    r"\bsummer intern\b", r"\bstudent intern\b", r"\bgraduate intern\b"
]

ENTRY_PATTERNS = [
    r"\bentry\s*-?\s*level\b", r"\bjunior\b", r"\bjr\.?\b", r"\bnew\s*-?\s*grad\b",
    r"\bgraduate\b", r"\bassociate\b", r"\bearly\s*-?\s*career\b"
]

def has_pattern(text: str, patterns: list) -> bool:
    text_lower = (text or "").lower()
    return any(re.search(pat, text_lower) for pat in patterns)

def extract_core_role(role_text: str) -> str:
    """Removes experience-level keywords to extract the core role string."""
    clean = (role_text or "").lower()
    for pat in SENIOR_PATTERNS + INTERN_PATTERNS + ENTRY_PATTERNS:
        clean = re.sub(pat, "", clean)
    return re.sub(r"\s+", " ", clean).strip()

def is_hard_filtered(job: Dict[str, Any], preferences: Dict[str, Any], candidate_profile: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Evaluates whether a job should be HARD FILTERED (rejected immediately).
    RECALL IS MORE IMPORTANT THAN PRECISION.
    Hard-filter ONLY obvious mismatches:
    - Wrong profession / completely unrelated role
    - Incompatible senior experience level when user requested internship/entry-level only
    - Explicit employment type mismatch (e.g. Full-time position when user requested Internship only)
    - Impossible location requirement
    Missing skills must NEVER trigger a hard filter.
    """
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    emp_type = (job.get("employment_type") or "").lower()

    pref_roles = [r.lower() for r in preferences.get("preferred_roles", [])]
    pref_locations = [l.lower() for l in preferences.get("locations", [])]
    pref_exp_levels = [e.lower() for e in preferences.get("experience_levels", [])]

    # Rule 1: Obvious profession mismatch & negative title filtering
    is_neg, neg_reason = sources.base.is_negative_title_match(job.get("title", ""))
    if is_neg:
        return True, neg_reason

    unrelated_keywords = ["registered nurse", "cashier", "truck driver", "store manager", "customer service representative", "medical assistant", "dental hygienist"]
    if any(ukw in title for ukw in unrelated_keywords):
        return True, f"Role profession mismatch: '{title}'"

    # Rule 2: Strict Experience Level & Seniority & Employment Type Matching
    wants_internship = any(lvl in pref_exp_levels for lvl in ["internship", "intern", "co-op"])
    wants_entry = any(lvl in pref_exp_levels for lvl in ["entry_level", "entry level", "junior", "new grad"])
    wants_mid = any(lvl in pref_exp_levels for lvl in ["mid_level", "mid level", "mid", "intermediate"])
    wants_senior = any(lvl in pref_exp_levels for lvl in ["senior", "senior_level", "senior level", "executive", "lead", "staff", "principal"])

    has_intern_title = has_pattern(title, INTERN_PATTERNS)
    has_entry_title = has_pattern(title, ENTRY_PATTERNS)
    has_senior_title = has_pattern(title, SENIOR_PATTERNS)

    # 2a. Senior title check: If user wants Internship or Entry Level and NOT Mid/Senior Level
    if (wants_internship or wants_entry) and not (wants_mid or wants_senior):
        if has_senior_title:
            return True, f"Senior experience mismatch: '{title}'"
        
        # High experience requirements in title/description (e.g. 8+ years)
        high_exp_patterns = [r"\b8\+\s*years", r"\b10\+\s*years", r"\b15\+\s*years"]
        for pat in high_exp_patterns:
            if re.search(pat, title) or re.search(pat, description[:500]):
                return True, f"Extreme experience requirement mismatch: '{title}'"

    # 2b. Explicit Employment Type Mismatch:
    is_explicit_fulltime = (emp_type == "full_time" or "full-time" in emp_type or "fulltime" in emp_type)

    if not (wants_mid or wants_senior):
        if wants_internship and not wants_entry:
            # User wants Internship ONLY: Explicit full-time role MUST be rejected unless title is an Intern role
            if is_explicit_fulltime and not has_intern_title:
                return True, f"Full-time employment type mismatch for internship-only preference: '{title}'"
        
        if wants_internship or wants_entry:
            # User wants Internship + Entry Level (or Entry Level only):
            # An explicit full-time role with NO intern title AND NO entry-level title is a standard regular/mid-level position!
            if is_explicit_fulltime and not has_intern_title and not has_entry_title:
                return True, f"Explicit full-time non-entry-level role mismatch: '{title}'"

    # Rule 3: Location mismatch (deterministic)
    if pref_locations:
        job_loc = (job.get("location") or "").lower().strip()
        job_title = (job.get("title") or "").lower().strip()
        
        # Determine if location is unknown
        is_unknown = not job_loc or job_loc in ["unknown", "not specified", "not-specified", "n/a", "none"]
        
        # Classify remote status
        remote_keywords = ["remote", "work from home", "wfh", "anywhere"]
        is_remote = any(re.search(r'\b' + re.escape(kw) + r'\b', job_loc) for kw in remote_keywords) or \
                    any(re.search(r'\b' + re.escape(kw) + r'\b', job_title) for kw in ["remote", "work from home", "wfh"])

        # Check if the location is purely a work-mode descriptor without a geographical place
        clean_geo = job_loc
        for term in ["hybrid", "onsite", "on-site", "office-based", "office based", "office", "remote", "wfh", "work from home", "anywhere", "-", ",", "/"]:
            clean_geo = clean_geo.replace(term, " ")
        clean_geo = clean_geo.strip()
        
        if not clean_geo and not is_remote:
            is_unknown = True
            
        if not is_unknown:
            
            wants_remote = "remote" in pref_locations
            pref_cities = [pl for pl in pref_locations if pl != "remote"]
            
            if is_remote:
                if not wants_remote:
                    return True, f"Location mismatch: Remote job but remote not preferred (location: '{job.get('location')}')"
            else:
                # Onsite/Hybrid job with known location: check if it matches target cities
                matched_city = False
                for city in pref_cities:
                    # Case-insensitive alias matching helper
                    pref_aliases = [city]
                    if city in ["bangalore", "bengaluru"]:
                        pref_aliases = ["bangalore", "bengaluru"]
                    
                    for alias in pref_aliases:
                        if re.search(r'\b' + re.escape(alias) + r'\b', job_loc):
                            matched_city = True
                            break
                    if matched_city:
                        break
                
                if not matched_city:
                    return True, f"Location mismatch: Job location '{job.get('location')}' does not match preferred cities: {', '.join(pref_cities)}"

    # Rule 4: Salary Hard Filter
    from sources.base import normalize_salary
    raw_salary = job.get("salary") or (job.get("ai_analysis") or {}).get("extracted_salary")
    monthly_inr, display_sal = normalize_salary(raw_salary, description[:1000])
    job["normalized_salary"] = display_sal
    job["monthly_salary_inr"] = monthly_inr

    min_salary = preferences.get("minimum_salary")
    include_undisclosed = preferences.get("include_undisclosed_salary", True)

    if min_salary and isinstance(min_salary, (int, float)) and min_salary > 0:
        if monthly_inr is not None:
            if monthly_inr < min_salary:
                return True, f"Salary below minimum threshold: ₹{monthly_inr:,}/month < ₹{min_salary:,}/month"
        elif display_sal == "Not disclosed":
            if not include_undisclosed:
                return True, f"Salary not disclosed (undisclosed compensation disabled)"

    return False, ""

# ---------------------------------------------------------------------------
# 2. Deterministic Ranking
# ---------------------------------------------------------------------------

def calculate_deterministic_score(candidate_profile: Dict[str, Any], preferences: Dict[str, Any], job: Dict[str, Any]) -> float:
    """
    Computes deterministic match score (0.0 to 100.0) based on weights:
    - Role alignment: 35%
    - Location alignment: 25%
    - Experience alignment: 20%
    - Employment type: 10%
    - Skill overlap: 10%
    - Dream company bonus: +8 pts (capped at 100)
    """
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    emp_type = (job.get("employment_type") or "").lower()
    company = (job.get("company") or "").lower()

    # 1. Role Alignment (35 pts) - Compare core roles separately from experience words
    pref_roles = [r.lower() for r in preferences.get("preferred_roles", [])]
    role_score = 0.0
    if pref_roles:
        job_core_role = extract_core_role(title)
        for r in pref_roles:
            pref_core_role = extract_core_role(r)
            if pref_core_role and pref_core_role in job_core_role:
                role_score = 35.0
                break
            elif any(word in job_core_role for word in pref_core_role.split() if len(word) > 3):
                role_score = max(role_score, 25.0)
        if role_score == 0.0:
            role_score = 15.0
    else:
        role_score = 25.0

    # 2. Location Alignment (25 pts)
    pref_locations = [l.lower() for l in preferences.get("locations", [])]
    location_score = 0.0
    if "remote" in location or "remote" in title or "work from home" in description[:400]:
        location_score = 25.0
    elif pref_locations:
        for pl in pref_locations:
            if pl in location:
                location_score = 25.0
                break
        if location_score == 0.0:
            location_score = 10.0
    else:
        location_score = 20.0

    # 3. Experience Alignment (20 pts)
    pref_exp = [e.lower() for e in preferences.get("experience_levels", [])]
    wants_intern = any(e in pref_exp for e in ["internship", "intern", "co-op"])
    wants_entry = any(e in pref_exp for e in ["entry_level", "entry level", "junior"])
    
    is_job_intern = has_pattern(title, INTERN_PATTERNS) or "internship" in emp_type
    is_job_entry = has_pattern(title, ENTRY_PATTERNS)

    if (wants_intern and is_job_intern) or (wants_entry and is_job_entry):
        exp_score = 20.0
    elif (wants_intern or wants_entry) and not is_job_intern and not is_job_entry:
        # Unknown / unlabelled experience level: keep but penalize slightly
        exp_score = 10.0
    else:
        exp_score = 15.0

    # 4. Employment Type (10 pts)
    pref_modes = [m.lower() for m in preferences.get("work_modes", [])]
    emp_score = 10.0
    if pref_modes and not any(m in emp_type or m in location for m in pref_modes):
        emp_score = 5.0

    # 5. Skill Overlap (10 pts)
    cand_skills = [s.lower() for s in candidate_profile.get("skills", [])]
    matched_skills = sum(1 for s in cand_skills if s in description)
    skill_score = min(10.0, (matched_skills / max(1, len(cand_skills))) * 10.0) if cand_skills else 5.0

    total_score = role_score + location_score + exp_score + emp_score + skill_score

    # Company Priority & Dream Company Ranking Boost (+3 to +8 pts, capped at 100)
    comp_clean = company.lower()
    dream_companies = [c.lower() for c in preferences.get("dream_companies", [])]
    company_priority = job.get("company_priority")
    if not company_priority:
        if any(dc in comp_clean for dc in dream_companies if dc):
            company_priority = 100
        else:
            company_priority = 50

    priority_bonus = 0.0
    if any(dc in comp_clean for dc in dream_companies if dc):
        priority_bonus = 8.0
    elif isinstance(company_priority, (int, float)) and company_priority > 50:
        priority_bonus = round(((company_priority - 50) / 50.0) * 5.0, 1)

    total_score += priority_bonus

    return min(100.0, round(total_score, 1))

# ---------------------------------------------------------------------------
# 3. Main End-to-End Pipeline Runner
# ---------------------------------------------------------------------------

def run_job_search_pipeline(
    requested_jobs: int = 50,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None,
    db_path: str = None
) -> Dict[str, Any]:
    """
    Executes complete job discovery, deduplication, filtering, deterministic ranking,
    AI evaluation, resume tailoring, LaTeX rendering, PDF compilation, and Drive/Sheets sync.
    Supports cooperative cancellation via stop_checker and run-scoped job cleanup.
    """
    db_path = db_path or database.DB_PATH
    database.init_db(db_path)
    resume.create_latex_template_file()

    # Create run record
    run_id = database.create_run(requested_jobs, db_path=db_path)

    def report_progress(stage: str, details: str = "", extra: Dict = None):
        logger.info(f"Run #{run_id} [{stage}]: {details}")
        update_kwargs = {"status": "running"}
        if extra:
            valid_db_keys = {"discovered_count", "duplicate_count", "invalid_count", "filtered_count", "analyzed_count", "selected_count", "resume_success_count", "resume_error_count", "status", "error"}
            db_extras = {k: v for k, v in extra.items() if k in valid_db_keys}
            update_kwargs.update(db_extras)
        database.update_run_progress(run_id, **update_kwargs, db_path=db_path)
        if progress_callback:
            progress_callback({"run_id": run_id, "stage": stage, "details": details, "extra": extra})

    def handle_stop():
        logger.info(f"Run #{run_id}: Stop requested by user. Cleaning up jobs from this run...")
        deleted_count = database.delete_jobs_by_run_id(run_id, db_path=db_path)
        msg = f"Run stopped. {deleted_count} jobs discovered during this run were removed."
        database.update_run_progress(run_id, status="stopped", error=msg, db_path=db_path)
        report_progress("Stopped", msg, {"status": "stopped", "deleted_count": deleted_count})
        return {
            "status": "stopped",
            "run_id": run_id,
            "message": msg,
            "deleted_count": deleted_count
        }

    try:
        if stop_checker and stop_checker():
            return handle_stop()

        # Step 1: Load Profile & Preferences
        report_progress("Initializing", "Loading candidate profile and preferences...")
        candidate = database.get_candidate(db_path=db_path)
        if not candidate:
            err = "No candidate profile found. Please complete setup first."
            database.update_run_progress(run_id, status="failed", error=err, db_path=db_path)
            return {"status": "failed", "error": err}

        profile = candidate["profile"]
        preferences = database.get_preferences(db_path=db_path) or {
            "preferred_roles": ["Software Engineer", "AI Engineer", "Python Developer"],
            "locations": ["Remote", "Hyderabad", "Bangalore"],
            "experience_levels": ["entry_level", "internship"],
            "jobs_per_run": requested_jobs
        }
        resume_settings = database.get_resume_settings(db_path=db_path)

        if stop_checker and stop_checker():
            return handle_stop()

        # Step 2: Job Discovery across sources (Targeted + Open Lanes)
        report_progress("Discovery", "Discovering jobs from registered sources...")
        discovery_res = sources.discover_all_sources(
            search_config=preferences,
            progress_callback=report_progress,
            stop_checker=stop_checker,
            return_summary=True
        )

        if isinstance(discovery_res, tuple) and len(discovery_res) == 2:
            discovered_jobs, discovery_summary = discovery_res
        else:
            discovered_jobs = discovery_res if isinstance(discovery_res, list) else []
            discovery_summary = {
                "mode": preferences.get("discovery_mode", "targeted_and_open"),
                "targeted_counts": {},
                "open_metrics": {}
            }

        discovered_count = len(discovered_jobs)

        source_counts = discovery_summary.get("targeted_counts", {})
        if discovery_summary.get("open_metrics", {}).get("unique_count", 0) > 0:
            source_counts["adzuna"] = discovery_summary["open_metrics"]["unique_count"]

        report_progress(
            "Discovery",
            f"Discovered {discovered_count} job postings across discovery lanes.",
            {"discovered_count": discovered_count, "source_counts": source_counts, "discovery_summary": discovery_summary}
        )

        if stop_checker and stop_checker():
            return handle_stop()

        # Step 3: Deduplication & Hard Filtering
        report_progress("Deduplication & Filtering", "Checking job history and deduplicating...")
        duplicate_count = 0
        filtered_count = 0
        valid_candidate_jobs = []

        for job in discovered_jobs:
            if stop_checker and stop_checker():
                return handle_stop()

            job["run_id"] = run_id
            u_id = job["unique_id"]
            if database.job_exists(u_id, db_path=db_path):
                database.update_job_last_seen(u_id, db_path=db_path)
                duplicate_count += 1
                continue

            # Hard filter check
            filtered, reason = is_hard_filtered(job, preferences, profile)
            if filtered:
                filtered_count += 1
                logger.debug(f"Filtered out job {job['title']} at {job['company']}: {reason}")
                continue

            # Compute deterministic score
            det_score = calculate_deterministic_score(profile, preferences, job)
            job["deterministic_score"] = det_score

            # Save valid new job to SQLite
            job_id = database.save_job(job, db_path=db_path)
            job["id"] = job_id
            valid_candidate_jobs.append(job)

        report_progress(
            "Filtering",
            f"Deduplicated {duplicate_count} jobs. Filtered {filtered_count} obvious mismatches. {len(valid_candidate_jobs)} new candidates remaining.",
            {"duplicate_count": duplicate_count, "filtered_count": filtered_count}
        )

        if not valid_candidate_jobs:
            msg = "No new matching jobs discovered."
            database.update_run_progress(run_id, status="completed", selected_count=0, db_path=db_path)
            return {
                "status": "completed",
                "run_id": run_id,
                "discovered_count": discovered_count,
                "duplicate_count": duplicate_count,
                "filtered_count": filtered_count,
                "analyzed_count": 0,
                "selected_count": 0,
                "resume_success_count": 0,
                "resume_error_count": 0,
                "message": msg
            }

        if stop_checker and stop_checker():
            return handle_stop()

        # Step 4: Sort by deterministic score and pick top pool for AI analysis
        valid_candidate_jobs.sort(key=lambda j: j["deterministic_score"], reverse=True)
        ai_pool_size = min(len(valid_candidate_jobs), max(requested_jobs * 2, 5))
        ai_candidate_pool = valid_candidate_jobs[:ai_pool_size]

        # Step 5: AI Job Deep Analysis
        report_progress("AI Analysis", f"Evaluating top {len(ai_candidate_pool)} jobs with AI model...")
        analyzed_count = 0
        scored_jobs = []

        for idx, job in enumerate(ai_candidate_pool, 1):
            if stop_checker and stop_checker():
                return handle_stop()

            report_progress("AI Analysis", f"Analyzing job {idx}/{len(ai_candidate_pool)}: {job['title']} at {job['company']}")
            try:
                analysis = ai.analyze_job(profile, job)
                ai_score = float(analysis.get("score", job["deterministic_score"]))

                # Final Score Formula: 60% Deterministic + 40% AI
                final_score = round((job["deterministic_score"] * 0.60) + (ai_score * 0.40), 1)

                job["ai_score"] = ai_score
                job["final_score"] = final_score
                job["ai_analysis"] = analysis
                database.update_job_evaluation(
                    job_id=job["id"],
                    deterministic_score=job["deterministic_score"],
                    ai_score=ai_score,
                    final_score=final_score,
                    ai_analysis=analysis,
                    db_path=db_path
                )
                scored_jobs.append(job)
                analyzed_count += 1
                import time
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error during AI analysis for job #{job['id']} ({job['title']}) at {job['company']}: {e}")

        report_progress("AI Analysis", f"AI Analysis completed for {analyzed_count} jobs.", {"analyzed_count": analyzed_count})

        if stop_checker and stop_checker():
            return handle_stop()

        # Step 6: Select Top N jobs
        scored_jobs.sort(key=lambda j: j["final_score"], reverse=True)
        selected_jobs = scored_jobs[:requested_jobs]
        selected_count = len(selected_jobs)

        for s_job in selected_jobs:
            database.update_job_status(s_job["id"], "selected", db_path=db_path)

        report_progress("Selection", f"Selected top {selected_count} jobs.", {"selected_count": selected_count})

        if stop_checker and stop_checker():
            return handle_stop()

        # Step 7: Sync Google Sheet
        report_progress("Google Sheets", "Syncing selected job dashboard to Google Sheets...")
        try:
            google_service.initialize_google_sheets()
            google_service.sync_jobs_to_sheet(selected_jobs)
        except Exception as e:
            logger.warning(f"Google Sheets sync warning: {e}")

        final_run_status = "completed"
        report_progress(
            "Complete",
            f"Run completed successfully. {selected_count} jobs selected and saved.",
            {
                "status": final_run_status,
                "selected_count": selected_count
            }
        )

        database.update_run_progress(
            run_id,
            discovered_count=discovered_count,
            duplicate_count=duplicate_count,
            invalid_count=0,
            filtered_count=filtered_count,
            analyzed_count=analyzed_count,
            selected_count=selected_count,
            resume_success_count=0,
            resume_error_count=0,
            status=final_run_status,
            db_path=db_path
        )

        return {
            "status": final_run_status,
            "run_id": run_id,
            "discovered_count": discovered_count,
            "duplicate_count": duplicate_count,
            "invalid_count": 0,
            "filtered_count": filtered_count,
            "analyzed_count": analyzed_count,
            "selected_count": selected_count,
            "resume_success_count": 0,
            "resume_error_count": 0
        }

    except Exception as e:
        logger.error(f"Fatal failure in pipeline run #{run_id}: {e}", exc_info=True)
        database.update_run_progress(run_id, status="failed", error=str(e), db_path=db_path)
        return {"status": "failed", "error": str(e)}
