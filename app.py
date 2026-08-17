import os
import threading
import logging
import uuid
import time
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()  # Must be first - loads .env before any module-level os.getenv() calls
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, g
import config
import database
import resume
import ai
import jobs
import company_manager
import company_discovery

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app_config = config.get_config()

app = Flask(__name__)
app.secret_key = app_config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = app_config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = app_config.MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = app_config.SESSION_COOKIE_HTTPONLY
app.config["SESSION_COOKIE_SAMESITE"] = app_config.SESSION_COOKIE_SAMESITE
app.config["SESSION_COOKIE_SECURE"] = app_config.SESSION_COOKIE_SECURE

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs(app_config.GENERATED_RESUMES_DIR, exist_ok=True)

# Initialize database tables
database.init_db()

# Rate limiting data structure
_rate_limit_lock = threading.Lock()
_rate_limit_records = defaultdict(list)

def is_rate_limited(client_ip: str, limit: int = 30, window_sec: int = 60) -> bool:
    if not app_config.RATE_LIMIT_ENABLED:
        return False
    now = time.time()
    with _rate_limit_lock:
        timestamps = _rate_limit_records[client_ip]
        # Keep only timestamps within window
        _rate_limit_records[client_ip] = [ts for ts in timestamps if now - ts < window_sec]
        if len(_rate_limit_records[client_ip]) >= limit:
            return True
        _rate_limit_records[client_ip].append(now)
        return False

# Request Correlation ID and Security Headers Middleware
@app.before_request
def handle_before_request():
    req_id = request.headers.get("X-Request-ID")
    if req_id and len(req_id) <= 64:
        g.request_id = req_id.strip()
    else:
        g.request_id = str(uuid.uuid4())

@app.after_request
def handle_after_request(response):
    req_id = getattr(g, "request_id", None)
    if req_id:
        response.headers["X-Request-ID"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Standard Error Handlers
@app.errorhandler(400)
def handle_bad_request(e):
    if request.path.startswith("/jobs/") or request.path.startswith("/companies/") or request.path.startswith("/run"):
        return jsonify({
            "success": False,
            "error": {
                "code": "BAD_REQUEST",
                "message": "Invalid request parameters or payload.",
                "request_id": getattr(g, "request_id", None)
            }
        }), 400
    return render_template("base.html"), 400

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith("/jobs/") or request.path.startswith("/companies/") or request.path.startswith("/run"):
        return jsonify({
            "success": False,
            "error": {
                "code": "RESOURCE_NOT_FOUND",
                "message": "The requested resource could not be found.",
                "request_id": getattr(g, "request_id", None)
            }
        }), 404
    return render_template("base.html"), 404

@app.errorhandler(413)
def handle_payload_too_large(e):
    return jsonify({
        "success": False,
        "error": {
            "code": "PAYLOAD_TOO_LARGE",
            "message": "Request payload exceeds maximum allowed size.",
            "request_id": getattr(g, "request_id", None)
        }
    }), 413

@app.errorhandler(429)
def handle_rate_limited(e):
    return jsonify({
        "success": False,
        "error": {
            "code": "RATE_LIMITED",
            "message": "Too many requests. Please slow down and try again later.",
            "request_id": getattr(g, "request_id", None)
        }
    }), 429

@app.errorhandler(500)
def handle_internal_error(e):
    logger.error(f"Internal server error on request {getattr(g, 'request_id', 'unknown')}: {e}")
    if request.path.startswith("/jobs/") or request.path.startswith("/companies/") or request.path.startswith("/run"):
        return jsonify({
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please check application logs.",
                "request_id": getattr(g, "request_id", None)
            }
        }), 500
    return render_template("base.html"), 500

# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health_liveness():
    """Lightweight liveness probe."""
    return jsonify({"status": "ok", "app_env": app_config.APP_ENV})

@app.route("/health/ready", methods=["GET"])
def health_readiness():
    """Readiness probe checking database availability and configuration."""
    db_ok = False
    try:
        conn = database.get_connection()
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        db_ok = True
    except Exception as e:
        logger.warning(f"Health readiness db check failed: {e}")

    pdflatex_found = bool(resume.shutil.which(os.getenv("PDFLATEX_PATH", "pdflatex")))

    all_ready = db_ok
    status_code = 200 if all_ready else 503
    return jsonify({
        "status": "ready" if all_ready else "unready",
        "database": "ok" if db_ok else "error",
        "pdflatex_available": pdflatex_found,
        "app_env": app_config.APP_ENV
    }), status_code

# In-memory background thread state for runs
_active_run_lock = threading.Lock()
_active_run_thread = None
_active_stop_requested = False
_active_run_id = None
_latest_progress = {"status": "idle", "stage": "Ready", "details": "No active run.", "logs": []}

# In-memory async company discovery state
_discovery_tasks_lock = threading.Lock()
_discovery_tasks = {}

def add_log_entry(msg: str):
    from datetime import datetime
    time_str = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{time_str}] {msg}"
    logs = _latest_progress.setdefault("logs", [])
    logs.append(log_line)
    # Keep last 200 logs
    if len(logs) > 200:
        _latest_progress["logs"] = logs[-200:]

# ---------------------------------------------------------------------------
# Dashboard & Setup Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    candidate = database.get_candidate()
    preferences = database.get_preferences()
    resume_settings = database.get_resume_settings()
    latest_run = database.get_latest_run()
    companies = company_manager.load_companies()
    
    return render_template(
        "index.html",
        candidate=candidate,
        preferences=preferences,
        resume_settings=resume_settings,
        latest_run=latest_run,
        companies=companies,
        current_progress=_latest_progress
    )

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        if "master_cv" not in request.files:
            flash("No file part selected.", "error")
            return redirect(request.url)
            
        file = request.files["master_cv"]
        if file.filename == "":
            flash("No selected PDF file.", "error")
            return redirect(request.url)
            
        if file and file.filename.lower().endswith(".pdf"):
            filename = resume.sanitize_filename(file.filename) + ".pdf"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            
            try:
                cv_text = resume.extract_text_from_pdf(save_path)
                parsed_profile = ai.parse_resume(cv_text)
                
                # Save candidate profile
                database.save_candidate(
                    name=parsed_profile.get("name", "Candidate Name"),
                    email=parsed_profile.get("email", ""),
                    phone=parsed_profile.get("phone", ""),
                    profile=parsed_profile,
                    master_resume_path=save_path
                )
                flash("Master CV uploaded and parsed successfully! Please review your profile below.", "success")
                return redirect(url_for("profile"))
            except Exception as e:
                logger.error(f"Error parsing uploaded CV: {e}")
                flash(f"Failed to parse CV: {e}", "error")
                return redirect(request.url)
        else:
            flash("Only PDF files are supported.", "error")
            return redirect(request.url)

    candidate = database.get_candidate()
    return render_template("setup.html", candidate=candidate)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            
            skills_raw = request.form.get("skills", "")
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
            
            # Additional details from form
            linkedin = request.form.get("linkedin", "").strip()
            github = request.form.get("github", "").strip()
            
            existing = database.get_candidate()
            current_profile = existing["profile"] if existing else {}
            
            current_profile["name"] = name
            current_profile["email"] = email
            current_profile["phone"] = phone
            current_profile["skills"] = skills
            if "links" not in current_profile or not isinstance(current_profile["links"], dict):
                current_profile["links"] = {}
            current_profile["links"]["linkedin"] = linkedin
            current_profile["links"]["github"] = github
            
            database.save_candidate(
                name=name,
                email=email,
                phone=phone,
                profile=current_profile,
                master_resume_path=existing.get("master_resume_path") if existing else None
            )
            flash("Candidate profile saved successfully!", "success")
            return redirect(url_for("preferences_route"))
        except Exception as e:
            flash(f"Error saving profile: {e}", "error")

    candidate = database.get_candidate()
    return render_template("profile_review.html", candidate=candidate)

@app.route("/preferences", methods=["GET", "POST"])
def preferences_route():
    if request.method == "POST":
        try:
            roles = [r.strip() for r in request.form.get("preferred_roles", "").split("\n") if r.strip()]
            locations = [l.strip() for l in request.form.get("locations", "").split("\n") if l.strip()]
            work_modes = request.form.getlist("work_modes")
            exp_levels = request.form.getlist("experience_levels")
            jobs_per_run = int(request.form.get("jobs_per_run", 50))
            dream_companies = [c.strip() for c in request.form.get("dream_companies", "").split("\n") if c.strip()]
            
            min_sal_raw = request.form.get("minimum_salary", "").strip()
            min_salary = int(min_sal_raw) if min_sal_raw.isdigit() else None
            include_undisclosed = request.form.get("include_undisclosed_salary") in ["true", "on", "1"] or "include_undisclosed_salary" in request.form
            discovery_mode = request.form.get("discovery_mode", "targeted_and_open")

            pref_data = {
                "preferred_roles": roles,
                "locations": locations,
                "work_modes": work_modes,
                "experience_levels": exp_levels,
                "jobs_per_run": jobs_per_run,
                "dream_companies": dream_companies,
                "minimum_salary": min_salary,
                "include_undisclosed_salary": include_undisclosed,
                "discovery_mode": discovery_mode
            }
            database.save_preferences(pref_data)
            flash("Job preferences updated successfully!", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Error saving preferences: {e}", "error")

    prefs = database.get_preferences()
    return render_template("preferences.html", preferences=prefs)

@app.route("/resume-settings", methods=["GET", "POST"])
def resume_settings_route():
    if request.method == "POST":
        try:
            template = request.form.get("template", "ats")
            order_raw = request.form.get("section_order", "summary, education, experience, projects, skills, certifications")
            section_order = [s.strip() for s in order_raw.split(",") if s.strip()]
            resume_length = int(request.form.get("resume_length", 1))
            instructions = request.form.get("instructions", "")
            
            database.save_resume_settings(template, section_order, resume_length, instructions)
            flash("Resume settings saved!", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Error saving resume settings: {e}", "error")

    settings = database.get_resume_settings()
    return render_template("resume_settings.html", settings=settings)

# ---------------------------------------------------------------------------
# Background Run & Progress Polling Routes
# ---------------------------------------------------------------------------

@app.route("/run", methods=["POST"])
def trigger_run():
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip, limit=10, window_sec=60):
        return jsonify({"status": "error", "message": "Rate limit exceeded for run trigger. Please wait before triggering a new run."}), 429

    global _active_run_thread, _active_stop_requested, _active_run_id, _latest_progress
    
    candidate = database.get_candidate()
    if not candidate:
        return jsonify({"status": "error", "message": "Candidate profile not set up. Upload master CV first."}), 400

    requested_jobs = int(request.form.get("jobs_count", 50))

    with _active_run_lock:
        if _active_run_thread and _active_run_thread.is_alive():
            return jsonify({"status": "error", "message": "A job search run is already in progress."}), 409

        _active_stop_requested = False
        _latest_progress = {
            "status": "running",
            "stage": "Starting",
            "details": "Initiating job search pipeline...",
            "logs": []
        }
        add_log_entry("Initiating job search pipeline...")

        def _worker_callback(progress_info):
            global _latest_progress
            stg = progress_info.get("stage", "Running")
            det = progress_info.get("details", "")
            _latest_progress["status"] = "running"
            _latest_progress["stage"] = stg
            _latest_progress["details"] = det
            if "extra" in progress_info and progress_info["extra"]:
                _latest_progress["extra"] = progress_info["extra"]
            if det:
                add_log_entry(f"[{stg}] {det}")

        def check_stop():
            return _active_stop_requested

        def _run_target():
            global _latest_progress, _active_run_id
            res = jobs.run_job_search_pipeline(
                requested_jobs=requested_jobs,
                progress_callback=_worker_callback,
                stop_checker=check_stop
            )
            _active_run_id = res.get("run_id")
            final_st = res.get("status", "completed")
            _latest_progress["status"] = final_st
            _latest_progress["stage"] = "Finished" if final_st == "completed" else ("Stopped" if final_st == "stopped" else "Failed")
            _latest_progress["details"] = res.get("message", f"Run {final_st}.")
            _latest_progress["result"] = res
            add_log_entry(f"Pipeline run {final_st}: {res.get('message', '')}")

        _active_run_thread = threading.Thread(target=_run_target, daemon=True)
        _active_run_thread.start()

    return jsonify({"status": "started", "message": f"Job search started for {requested_jobs} jobs."})

@app.route("/run/stop", methods=["POST"])
def stop_run():
    global _active_stop_requested
    with _active_run_lock:
        if not (_active_run_thread and _active_run_thread.is_alive()):
            return jsonify({"status": "error", "message": "No active run to stop."}), 400
        _active_stop_requested = True
        add_log_entry("Stop requested by user. Performing cooperative cancellation...")
    return jsonify({"status": "success", "message": "Stop requested. Pipeline will stop at next safe checkpoint."})

@app.route("/database/clear", methods=["POST"])
def clear_database():
    global _latest_progress
    with _active_run_lock:
        if _active_run_thread and _active_run_thread.is_alive():
            return jsonify({"status": "error", "message": "Stop the current run before clearing the database."}), 409
        database.clear_jobs_and_runs()
        _latest_progress = {"status": "idle", "stage": "Ready", "details": "Database cleared.", "logs": ["Database cleared."]}
    return jsonify({"status": "success", "message": "Jobs and run history cleared successfully."})

@app.route("/run/status")
def run_status():
    latest_run = database.get_latest_run()
    is_active = bool(_active_run_thread and _active_run_thread.is_alive())
    return jsonify({
        "active": is_active,
        "run_id": _active_run_id or (latest_run["id"] if latest_run else None),
        "status": _latest_progress.get("status", "idle"),
        "progress": _latest_progress,
        "latest_run": latest_run,
        "logs": _latest_progress.get("logs", [])
    })

# ---------------------------------------------------------------------------
# Results & Application Status Updating Routes
# ---------------------------------------------------------------------------

@app.route("/results")
def results():
    status_filter = request.args.get("status")
    if not status_filter:
        # Show only processed/selected jobs, excluding raw 'new' ones
        all_jobs = database.get_all_jobs(limit=100)
        all_jobs = [j for j in all_jobs if j.get("status") != 'new']
    else:
        all_jobs = database.get_all_jobs(status_filter=status_filter, limit=100)

    sheets_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_url = f"https://docs.google.com/spreadsheets/d/{sheets_id}" if sheets_id else None

    return render_template(
        "results.html",
        jobs=all_jobs,
        current_filter=status_filter,
        google_sheets_url=google_sheets_url
    )

import google_service

@app.route("/jobs/<int:job_id>/applied", methods=["POST"])
def mark_applied(job_id):
    database.update_job_status(job_id, "applied")
    job = database.get_job_by_id(job_id)
    if job:
        google_service.update_job_status_in_sheet(job)
    return jsonify({"status": "success", "message": "Job marked as Applied."})

@app.route("/jobs/<int:job_id>/rejected", methods=["POST"])
def mark_rejected(job_id):
    database.update_job_status(job_id, "rejected")
    job = database.get_job_by_id(job_id)
    if job:
        google_service.update_job_status_in_sheet(job)
    return jsonify({"status": "success", "message": "Job marked as Rejected."})

@app.route("/jobs/<int:job_id>/generate-resume", methods=["POST"])
def generate_resume_endpoint(job_id):
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip, limit=20, window_sec=60):
        return jsonify({"status": "error", "message": "Resume generation is temporarily rate-limited. Please try again later."}), 429

    job = database.get_job_by_id(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404

    cand_record = database.get_candidate()
    if not cand_record or not cand_record.get("profile"):
        return jsonify({"status": "error", "message": "Candidate profile not configured. Please complete setup."}), 400

    profile = cand_record["profile"]
    settings = database.get_resume_settings()
    ai_analysis = job.get("ai_analysis") or {}

    try:
        import resume_optimizer

        # Analyze requirements and match matrix
        requirements = resume_optimizer.analyze_job_requirements(job)
        match_matrix = resume_optimizer.match_candidate_to_job(profile, requirements)

        try:
            tailored_res = ai.tailor_resume(
                profile,
                job,
                {
                    "matching_requirements": match_matrix["all_matched_skills"],
                    "missing_preferred_skills": match_matrix["all_unsupported_skills"],
                    "requirements_breakdown": requirements
                },
                settings
            )
        except Exception as tail_err:
            logger.warning(f"AI resume tailoring failed: {tail_err}. Falling back to deterministic resume mock.")
            mock_res = ai._mock_tailor_resume(profile, job, ai_analysis, settings)
            tailored_res = ai.validate_tailored_resume(mock_res, profile)

        # Factual Integrity Validation
        _, _, tailored_res = resume_optimizer.validate_factual_integrity(tailored_res, profile)

        # Compute Match Score & Details
        match_data = resume_optimizer.calculate_resume_match_score(tailored_res, requirements, profile)
        match_score = match_data.get("overall_score", 85.0)

        latex_code = resume.render_latex(tailored_res)

        sanitized_comp = resume.sanitize_filename(job.get("company", "Company"))
        sanitized_title = resume.sanitize_filename(job.get("title", "Role"))
        file_basename = f"{sanitized_comp}_{sanitized_title}_{job['id']}"
        os.makedirs("generated/resumes", exist_ok=True)
        tex_path = os.path.abspath(f"generated/resumes/{file_basename}.tex")
        
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_code)

        # Compile PDF
        pdf_ok = False
        pdf_path = None
        try:
            pdf_ok, pdf_path, pdf_log = resume.compile_pdf(tex_path)
            if not pdf_ok:
                logger.info(f"PDF compilation skipped or unconfigured: {pdf_log}")
        except Exception as pdf_err:
            logger.info(f"PDF compilation error: {pdf_err}")

        database.update_job_resume(
            job_id=job['id'],
            resume_json=tailored_res,
            tex_path=tex_path,
            status=job.get("status", "selected"),
            resume_score=match_score,
            resume_match_details=match_data
        )

        base_url = os.getenv("LOCAL_BASE_URL", "http://localhost:5000")
        view_url = f"{base_url}/jobs/{job['id']}/view-resume"

        try:
            google_service.update_job_resume_url_in_sheet(job, view_url)
        except Exception as e:
            logger.warning(f"Failed to update Resume URL in Google Sheets: {e}")

        return jsonify({
            "status": "success",
            "message": "Resume created successfully.",
            "match_score": match_score,
            "match_details": match_data,
            "pdf_available": bool(pdf_ok and pdf_path and os.path.exists(pdf_path)),
            "download_pdf_url": f"/jobs/{job['id']}/download-resume?format=pdf",
            "download_tex_url": f"/jobs/{job['id']}/download-resume?format=tex",
            "view_url": f"/jobs/{job['id']}/view-resume",
            "download_url": f"/jobs/{job['id']}/download-resume"
        })
    except Exception as e:
        logger.error(f"Error generating resume for job #{job_id}: {e}")
        err_msg = str(e)
        if "rate" in err_msg.lower() or "429" in err_msg:
            return jsonify({"status": "error", "message": "Resume generation is temporarily rate-limited. Please try again later."}), 429
        return jsonify({"status": "error", "message": "Resume generation failed. Please try again."}), 500

@app.route("/jobs/<int:job_id>/resume-details")
def resume_details(job_id):
    job = database.get_job_by_id(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    details = job.get("resume_match_details") or {}
    score = job.get("resume_score")
    return jsonify({
        "status": "success",
        "job_id": job_id,
        "company": job.get("company"),
        "title": job.get("title"),
        "resume_score": score,
        "match_details": details
    })

@app.route("/jobs/<int:job_id>/view-resume")
def view_resume(job_id):
    from flask import Response
    job = database.get_job_by_id(job_id)
    if not job:
        return "Job not found.", 404

    tex_path = job.get("resume_tex_path")
    if not tex_path or not os.path.exists(tex_path):
        return "Resume source file not found.", 404

    # Path traversal protection
    resumes_dir = os.path.abspath("generated/resumes")
    resolved_path = os.path.abspath(tex_path)
    if not resolved_path.startswith(resumes_dir):
        return "Access denied: Invalid path.", 403

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            tex_code = f.read()
        return Response(tex_code, mimetype="text/plain; charset=utf-8")
    except Exception as e:
        logger.error(f"Error reading tex file: {e}")
        return "Error reading resume file.", 500

@app.route("/jobs/<int:job_id>/download-resume")
def download_resume(job_id):
    from flask import send_file, request
    job = database.get_job_by_id(job_id)
    if not job:
        return "Job not found.", 404

    tex_path = job.get("resume_tex_path")
    if not tex_path or not os.path.exists(tex_path):
        return "Resume source file not found.", 404

    # Path traversal protection
    resumes_dir = os.path.abspath("generated/resumes")
    resolved_tex_path = os.path.abspath(tex_path)
    if not resolved_tex_path.startswith(resumes_dir):
        return "Access denied: Invalid path.", 403

    # Derive expected PDF path
    base_name = os.path.splitext(resolved_tex_path)[0]
    expected_pdf_path = f"{base_name}.pdf"
    has_pdf = os.path.exists(expected_pdf_path) and os.path.getsize(expected_pdf_path) > 0

    req_format = request.args.get("format", "").lower().strip()
    sanitized_comp = resume.sanitize_filename(job.get("company", "Company"))
    sanitized_title = resume.sanitize_filename(job.get("title", "Role"))

    # Explicit format=tex
    if req_format == "tex":
        download_name = f"{sanitized_comp}_{sanitized_title}_Resume.tex"
        return send_file(resolved_tex_path, as_attachment=True, download_name=download_name, mimetype="application/x-tex")

    # Explicit format=pdf
    if req_format == "pdf":
        if has_pdf:
            download_name = f"{sanitized_comp}_{sanitized_title}_Resume.pdf"
            return send_file(expected_pdf_path, as_attachment=True, download_name=download_name, mimetype="application/pdf")
        else:
            return "PDF resume not found or compilation was unavailable.", 404

    # Default (no format param): prefer PDF if available, fallback to TeX
    if has_pdf:
        download_name = f"{sanitized_comp}_{sanitized_title}_Resume.pdf"
        return send_file(expected_pdf_path, as_attachment=True, download_name=download_name, mimetype="application/pdf")
    else:
        download_name = f"{sanitized_comp}_{sanitized_title}_Resume.tex"
        return send_file(resolved_tex_path, as_attachment=True, download_name=download_name, mimetype="application/x-tex")

@app.route("/sync-sheets", methods=["POST"])
def sync_sheets():
    """Manually triggers Google Sheets synchronization for selected jobs."""
    try:
        import google_service
        selected_jobs = database.get_all_jobs(status_filter="selected", limit=100)
        if not selected_jobs:
            selected_jobs = database.get_all_jobs(limit=50)
            selected_jobs = [j for j in selected_jobs if j.get("status") != 'new']

        google_service.initialize_google_sheets()
        success = google_service.sync_jobs_to_sheet(selected_jobs)
        if success:
            return jsonify({"status": "success", "message": f"Successfully synced {len(selected_jobs)} jobs to Google Sheets."})
        else:
            return jsonify({"status": "warning", "message": "Google Sheets sync skipped or unconfigured. Check SPREADSHEET_ID in .env."}), 400
    except Exception as e:
        logger.error(f"Manual Google Sheets sync error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------------------------------------------------------------------
# Company Discovery & Watchlist Management Routes
# ---------------------------------------------------------------------------

@app.route("/companies", methods=["GET"])
def get_companies():
    """Returns all watchlist companies from config/companies.json."""
    return jsonify(company_manager.load_companies())

@app.route("/companies/discover", methods=["POST"])
def start_company_discovery():
    """Starts async discovery task for a company."""
    data = request.get_json(silent=True) or request.form
    company_name = (data.get("company_name") or data.get("company") or "").strip()
    if not company_name:
        return jsonify({"status": "error", "message": "Company name is required."}), 400

    task_id = str(uuid.uuid4())
    task_state = {
        "status": "in_progress",
        "company_name": company_name,
        "logs": [f"Searching for official company source: {company_name}"],
        "candidate": None,
        "error": None
    }

    with _discovery_tasks_lock:
        _discovery_tasks[task_id] = task_state

    def run_async_discovery():
        def task_progress(msg: str):
            with _discovery_tasks_lock:
                if task_id in _discovery_tasks:
                    _discovery_tasks[task_id]["logs"].append(msg)

        try:
            candidate = company_discovery.discover_company(company_name, progress_callback=task_progress)
            verified_result = company_discovery.verify_discovered_source(candidate, progress_callback=task_progress)
            with _discovery_tasks_lock:
                _discovery_tasks[task_id]["candidate"] = verified_result
                _discovery_tasks[task_id]["status"] = "completed"
        except Exception as e:
            logger.error(f"Async company discovery error: {e}")
            with _discovery_tasks_lock:
                _discovery_tasks[task_id]["status"] = "failed"
                _discovery_tasks[task_id]["error"] = str(e)
                _discovery_tasks[task_id]["logs"].append(f"Discovery error: {e}")

    thread = threading.Thread(target=run_async_discovery, daemon=True)
    thread.start()

    return jsonify({"status": "started", "task_id": task_id})

@app.route("/companies/discover/status/<task_id>", methods=["GET"])
def get_discovery_status(task_id: str):
    """Returns status and logs of an async company discovery task."""
    with _discovery_tasks_lock:
        task_state = _discovery_tasks.get(task_id)
        if not task_state:
            return jsonify({"status": "error", "message": "Task not found."}), 404
        return jsonify(task_state)

@app.route("/companies/add", methods=["POST"])
def add_company_route():
    """Adds verified company configuration to companies.json and sources.json."""
    data = request.get_json(silent=True) or request.form
    if not data:
        return jsonify({"status": "error", "message": "Invalid company payload."}), 400

    try:
        entry = company_manager.add_company_config(data)
        return jsonify({"status": "success", "company": entry})
    except Exception as e:
        logger.error(f"Error adding company: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/companies/priority", methods=["POST"])
def update_company_priority_route():
    """Updates company priority (1-100). Accepts JSON body {'company': 'Name', 'priority': 85}."""
    data = request.get_json(silent=True) or request.form
    comp_name = data.get("company")
    priority = data.get("priority")
    if not comp_name or priority is None:
        return jsonify({"status": "error", "message": "Company name and priority required."}), 400

    try:
        success = company_manager.update_company_priority(comp_name, priority)
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": f"Company '{comp_name}' not found."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/companies/toggle", methods=["POST"])
def toggle_company_route():
    """Toggles active/disabled state. Accepts JSON body {'company': 'Name', 'enabled': true/false}."""
    data = request.get_json(silent=True) or request.form
    comp_name = data.get("company")
    enabled = data.get("enabled")
    if not comp_name:
        return jsonify({"status": "error", "message": "Company name required."}), 400

    try:
        success = company_manager.toggle_company_status(comp_name, enabled)
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": f"Company '{comp_name}' not found."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/companies/verify", methods=["POST"])
def re_verify_company_route():
    """Re-runs ATS verification. Accepts JSON body {'company': 'Name'}."""
    data = request.get_json(silent=True) or request.form
    comp_name = data.get("company")
    if not comp_name:
        return jsonify({"status": "error", "message": "Company name required."}), 400

    try:
        updated = company_manager.verify_company_config(comp_name)
        return jsonify({"status": "success", "company": updated})
    except Exception as e:
        logger.error(f"Error re-verifying company: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

_verify_all_lock = threading.Lock()
_verify_all_state = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "current_company": "",
    "logs": []
}

@app.route("/companies/verify-all", methods=["POST"])
def verify_all_route():
    """Starts async verification for all enabled companies in the watchlist."""
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip, limit=5, window_sec=60):
        return jsonify({"status": "error", "message": "Batch verification is temporarily rate-limited. Please wait before triggering again."}), 429

    global _verify_all_state
    
    with _verify_all_lock:
        if _verify_all_state["status"] == "in_progress":
            return jsonify({"status": "error", "message": "Verification is already in progress."}), 400
        
        _verify_all_state = {
            "status": "in_progress",
            "current": 0,
            "total": 0,
            "current_company": "",
            "logs": ["Starting batch verification of all enabled companies..."]
        }

    def run_async_verify_all():
        global _verify_all_state
        try:
            companies = company_manager.load_companies()
            enabled_companies = [c for c in companies if c.get("enabled", True)]
            total = len(enabled_companies)
            
            with _verify_all_lock:
                _verify_all_state["total"] = total
                
            if total == 0:
                with _verify_all_lock:
                    _verify_all_state["logs"].append("No enabled companies found in the watchlist.")
                    _verify_all_state["status"] = "completed"
                return

            for idx, comp in enumerate(enabled_companies):
                comp_name = comp.get("company", "Unknown")
                
                with _verify_all_lock:
                    _verify_all_state["current"] = idx + 1
                    _verify_all_state["current_company"] = comp_name
                    _verify_all_state["logs"].append(f"[{idx + 1}/{total}] {comp_name}...")
                
                try:
                    # Deterministic verification
                    updated = company_manager.verify_company_config(comp_name)
                    
                    status = updated.get("verification_status", "verification_failed")
                    source = (updated.get("source") or "source").capitalize()
                    
                    jobs_cnt = updated.get("jobs_available")
                    if jobs_cnt is None:
                        jobs_cnt = updated.get("jobs_found")
                        
                    if "verified" in status:
                        if jobs_cnt is not None:
                            log_msg = f"✓ {source} — {jobs_cnt} jobs"
                        else:
                            log_msg = f"✓ {source} — verified (jobs count unknown)"
                    elif status == "no_jobs_found":
                        log_msg = f"✓ {source} — 0 jobs"
                    elif status == "access_restricted":
                        log_msg = f"✗ Access Restricted (security challenge)"
                    else:
                        log_msg = f"✗ Verification failed"
                        
                except Exception as ex:
                    logger.error(f"Error verifying {comp_name} during batch run: {ex}")
                    log_msg = f"✗ Error: {ex}"
                
                with _verify_all_lock:
                    _verify_all_state["logs"].append(log_msg)
            
            with _verify_all_lock:
                _verify_all_state["logs"].append("Batch verification completed.")
                _verify_all_state["status"] = "completed"
                
        except Exception as e:
            logger.error(f"Async batch verification error: {e}")
            with _verify_all_lock:
                _verify_all_state["status"] = "failed"
                _verify_all_state["logs"].append(f"Fatal error during batch verification: {e}")

    thread = threading.Thread(target=run_async_verify_all, daemon=True)
    thread.start()
    
    return jsonify({"status": "started"})

@app.route("/companies/verify-all/status", methods=["GET"])
def get_verify_all_status():
    """Returns the current status of the batch verification task."""
    with _verify_all_lock:
        return jsonify(_verify_all_state)

@app.route("/companies/delete", methods=["POST"])
def delete_company_route():
    """Removes company from config files. Accepts JSON body {'company': 'Name'}."""
    data = request.get_json(silent=True) or request.form
    comp_name = data.get("company")
    if not comp_name:
        return jsonify({"status": "error", "message": "Company name required."}), 400

    try:
        success = company_manager.remove_company_config(comp_name)
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": f"Company '{comp_name}' not found."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = app_config.PORT
    debug_mode = app_config.DEBUG
    # use_reloader=False prevents watchdog from killing active background search threads mid-run
    app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
