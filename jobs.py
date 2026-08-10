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

def is_hard_filtered(job: Dict[str, Any], preferences: Dict[str, Any], candidate_profile: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Evaluates whether a job should be HARD FILTERED (rejected immediately).
    RECALL IS MORE IMPORTANT THAN PRECISION.
    Hard-filter ONLY obvious mismatches:
    - Wrong profession / completely unrelated role
    - Excessive incompatible experience requirement
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

    # Rule 1: Obvious profession mismatch
    # If candidate wants software/tech roles, reject non-tech/unrelated professions
    unrelated_keywords = ["registered nurse", "cashier", "truck driver", "store manager", "customer service representative", "medical assistant", "dental hygienist"]
    if any(ukw in title for ukw in unrelated_keywords):
        return True, f"Role profession mismatch: '{title}'"

    # Rule 2: Extreme experience gap
    # If candidate is looking for internship/entry level, filter out 8+ years executive/VP positions
    if any(lvl in pref_exp_levels for lvl in ["internship", "entry_level", "entry level", "junior"]):
        high_exp_patterns = [r"\b8\+\s*years", r"\b10\+\s*years", r"\b15\+\s*years", r"vp of", r"vice president", r"chief tech", r"director of"]
        for pat in high_exp_patterns:
            if re.search(pat, title) or re.search(pat, description[:500]):
                return True, f"Extreme experience requirement mismatch: '{title}'"

    # Rule 3: Impossible location mismatch
    # If user specifies restricted locations and job requires onsite work in incompatible region
    if pref_locations:
        is_remote_job = "remote" in location or "remote" in title or "work from home" in description[:300]
        location_matched = is_remote_job or any(pl in location for pl in pref_locations if pl != "remote")
        # If strict onsite location specified that contradicts all user choices
        if not location_matched and "onsite" in location and not any(loc in location for loc in ["india", "us", "usa", "anywhere"]):
            pass # Keep conservative: log but pass unless clearly impossible

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
    - Dream company bonus: +5-10 pts (capped at 100)
    """
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()
    emp_type = (job.get("employment_type") or "").lower()
    company = (job.get("company") or "").lower()

    # 1. Role Alignment (35 pts)
    pref_roles = [r.lower() for r in preferences.get("preferred_roles", [])]
    role_score = 0.0
    if pref_roles:
        for r in pref_roles:
            if r in title:
                role_score = 35.0
                break
            elif any(word in title for word in r.split() if len(word) > 3):
                role_score = max(role_score, 25.0)
        if role_score == 0.0:
            role_score = 15.0 # Baseline for passing hard filter
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
    exp_score = 15.0
    if any(e in title or e in description[:500] for e in pref_exp):
        exp_score = 20.0

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

    # Dream Company Bonus (+5 to +10 pts)
    dream_companies = [c.lower() for c in preferences.get("dream_companies", [])]
    if any(dc in company for dc in dream_companies if dc):
        total_score += 8.0

    return min(100.0, round(total_score, 1))

# ---------------------------------------------------------------------------
# 3. Main End-to-End Pipeline Runner
# ---------------------------------------------------------------------------

def run_job_search_pipeline(
    requested_jobs: int = 50,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    db_path: str = None
) -> Dict[str, Any]:
    """
    Executes complete job discovery, deduplication, filtering, deterministic ranking,
    AI evaluation, resume tailoring, LaTeX rendering, PDF compilation, and Drive/Sheets sync.
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
            update_kwargs.update(extra)
        database.update_run_progress(run_id, **update_kwargs, db_path=db_path)
        if progress_callback:
            progress_callback({"run_id": run_id, "stage": stage, "details": details, "extra": extra})

    try:
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

        # Step 2: Job Discovery across sources
        report_progress("Discovery", "Discovering jobs from Greenhouse, Lever, Ashby...")
        discovered_jobs = sources.discover_all_sources(preferences)
        discovered_count = len(discovered_jobs)
        report_progress("Discovery", f"Discovered {discovered_count} job postings.", {"discovered_count": discovered_count})

        # Step 3: Deduplication & Hard Filtering
        report_progress("Deduplication & Filtering", "Checking job history and deduplicating...")
        duplicate_count = 0
        filtered_count = 0
        valid_candidate_jobs = []

        for job in discovered_jobs:
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

        # Step 4: Sort by deterministic score and pick top pool for AI analysis
        valid_candidate_jobs.sort(key=lambda j: j["deterministic_score"], reverse=True)
        ai_pool_size = min(len(valid_candidate_jobs), max(requested_jobs * 2, 50))
        ai_candidate_pool = valid_candidate_jobs[:ai_pool_size]

        # Step 5: AI Job Deep Analysis
        report_progress("AI Analysis", f"Evaluating top {len(ai_candidate_pool)} jobs with AI model...")
        analyzed_count = 0
        scored_jobs = []

        for idx, job in enumerate(ai_candidate_pool, 1):
            report_progress("AI Analysis", f"Analyzing job {idx}/{len(ai_candidate_pool)}: {job['title']} at {job['company']}")
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

        report_progress("AI Analysis", f"AI Analysis completed for {analyzed_count} jobs.", {"analyzed_count": analyzed_count})

        # Step 6: Select Top N jobs
        scored_jobs.sort(key=lambda j: j["final_score"], reverse=True)
        selected_jobs = scored_jobs[:requested_jobs]
        selected_count = len(selected_jobs)

        for s_job in selected_jobs:
            database.update_job_status(s_job["id"], "selected", db_path=db_path)

        report_progress("Selection", f"Selected top {selected_count} jobs.", {"selected_count": selected_count})

        # Step 7: Resume Tailoring, LaTeX Rendering & PDF Compilation
        report_progress("Resume Generation", f"Tailoring resumes for top {selected_count} jobs...")
        resume_success_count = 0
        resume_error_count = 0
        google_service.initialize_google_drive()

        for idx, s_job in enumerate(selected_jobs, 1):
            report_progress("Resume Generation", f"Generating resume {idx}/{selected_count} for {s_job['company']}...")
            try:
                tailored_res = ai.tailor_resume(profile, s_job, s_job["ai_analysis"], resume_settings)
                latex_code = resume.render_latex(tailored_res)

                sanitized_comp = resume.sanitize_filename(s_job["company"])
                sanitized_title = resume.sanitize_filename(s_job["title"])
                file_basename = f"{sanitized_comp}_{sanitized_title}_{s_job['id']}"

                os.makedirs("generated/resumes", exist_ok=True)
                tex_path = os.path.abspath(f"generated/resumes/{file_basename}.tex")
                
                with open(tex_path, "w", encoding="utf-8") as f:
                    f.write(latex_code)

                # PDF Compilation attempt
                pdf_ok, pdf_path, pdf_log = resume.compile_pdf(tex_path, "generated/resumes")
                drive_url = None

                if pdf_ok and pdf_path:
                    resume_success_count += 1
                    # Upload to Google Drive if configured
                    drive_url = google_service.upload_pdf_to_drive(pdf_path, s_job["company"])
                else:
                    resume_error_count += 1
                    logger.warning(f"Resume PDF compilation notice for job #{s_job['id']}: {pdf_log}")

                database.update_job_resume(
                    job_id=s_job["id"],
                    resume_json=tailored_res,
                    tex_path=tex_path,
                    pdf_path=pdf_path if pdf_ok else None,
                    drive_url=drive_url,
                    status="selected",
                    db_path=db_path
                )
            except Exception as e:
                resume_error_count += 1
                logger.error(f"Error tailoring resume for job #{s_job['id']}: {e}")

        # Step 8: Sync Google Sheet
        report_progress("Google Sheets", "Syncing final selected job dashboard to Google Sheets...")
        try:
            google_service.sync_jobs_to_sheet(selected_jobs)
        except Exception as e:
            logger.warning(f"Google Sheets sync warning: {e}")

        final_run_status = "completed" if resume_error_count == 0 else "partial"
        report_progress(
            "Complete",
            f"Run completed. Selected: {selected_count}, Resumes Created: {resume_success_count}, Errors: {resume_error_count}",
            {
                "status": final_run_status,
                "resume_success_count": resume_success_count,
                "resume_error_count": resume_error_count
            }
        )

        return {
            "status": final_run_status,
            "run_id": run_id,
            "discovered_count": discovered_count,
            "duplicate_count": duplicate_count,
            "filtered_count": filtered_count,
            "analyzed_count": analyzed_count,
            "selected_count": selected_count,
            "resume_success_count": resume_success_count,
            "resume_error_count": resume_error_count
        }

    except Exception as e:
        logger.error(f"Fatal failure in pipeline run #{run_id}: {e}", exc_info=True)
        database.update_run_progress(run_id, status="failed", error=str(e), db_path=db_path)
        return {"status": "failed", "error": str(e)}
