import os
import threading
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import database
import resume
import ai
import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs("data", exist_ok=True)

# Initialize database tables
database.init_db()

# In-memory background thread state for runs
_active_run_lock = threading.Lock()
_active_run_thread = None
_latest_progress = {"status": "idle", "stage": "Ready", "details": "No active run."}

# ---------------------------------------------------------------------------
# Dashboard & Setup Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    candidate = database.get_candidate()
    preferences = database.get_preferences()
    resume_settings = database.get_resume_settings()
    latest_run = database.get_latest_run()
    
    return render_template(
        "index.html",
        candidate=candidate,
        preferences=preferences,
        resume_settings=resume_settings,
        latest_run=latest_run,
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
            return redirect(url_for("preferences"))
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
            
            pref_data = {
                "preferred_roles": roles,
                "locations": locations,
                "work_modes": work_modes,
                "experience_levels": exp_levels,
                "jobs_per_run": jobs_per_run,
                "dream_companies": dream_companies
            }
            database.save_preferences(pref_data)
            flash("Job search preferences saved!", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Error saving preferences: {e}", "error")

    preferences = database.get_preferences() or {
        "preferred_roles": ["Software Engineer", "AI/ML Engineer", "Python Developer"],
        "locations": ["Remote", "Hyderabad", "Bangalore"],
        "work_modes": ["remote", "hybrid"],
        "experience_levels": ["entry_level", "internship"],
        "jobs_per_run": 50,
        "dream_companies": ["Google", "Microsoft", "NVIDIA", "Amazon"]
    }
    return render_template("preferences.html", preferences=preferences)

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
    global _active_run_thread, _latest_progress
    
    candidate = database.get_candidate()
    if not candidate:
        return jsonify({"status": "error", "message": "Candidate profile not set up. Upload master CV first."}), 400

    requested_jobs = int(request.form.get("jobs_count", 50))

    with _active_run_lock:
        if _active_run_thread and _active_run_thread.is_alive():
            return jsonify({"status": "error", "message": "A job search run is already in progress."}), 409

        _latest_progress = {"status": "running", "stage": "Starting", "details": "Initiating job search pipeline..."}

        def _worker_callback(progress_info):
            global _latest_progress
            _latest_progress = {
                "status": "running",
                "stage": progress_info.get("stage"),
                "details": progress_info.get("details"),
                "extra": progress_info.get("extra")
            }

        def _run_target():
            global _latest_progress
            res = jobs.run_job_search_pipeline(
                requested_jobs=requested_jobs,
                progress_callback=_worker_callback
            )
            _latest_progress = {
                "status": res.get("status", "completed"),
                "stage": "Finished",
                "details": f"Completed run. {res.get('selected_count', 0)} jobs selected.",
                "result": res
            }

        _active_run_thread = threading.Thread(target=_run_target, daemon=True)
        _active_run_thread.start()

    return jsonify({"status": "started", "message": f"Job search started for {requested_jobs} jobs."})

@app.route("/run/status")
def run_status():
    latest_run = database.get_latest_run()
    return jsonify({
        "progress": _latest_progress,
        "latest_run": latest_run
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
    return render_template("results.html", jobs=all_jobs, current_filter=status_filter)

@app.route("/jobs/<int:job_id>/applied", methods=["POST"])
def mark_applied(job_id):
    database.update_job_status(job_id, "applied")
    return jsonify({"status": "success", "message": "Job marked as Applied."})

@app.route("/jobs/<int:job_id>/rejected", methods=["POST"])
def mark_rejected(job_id):
    database.update_job_status(job_id, "rejected")
    return jsonify({"status": "success", "message": "Job marked as Rejected."})

@app.route("/jobs/<int:job_id>/overleaf")
def open_in_overleaf(job_id):
    from flask import render_template_string
    job = database.get_job_by_id(job_id)
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("results"))
        
    tex_code = ""
    tex_path = job.get("resume_tex_path")
    if tex_path and os.path.exists(tex_path):
        try:
            with open(tex_path, "r", encoding="utf-8") as f:
                tex_code = f.read()
        except Exception as e:
            logger.error(f"Error reading tex file: {e}")
            
    if not tex_code and job.get("resume_json"):
        try:
            tex_code = resume.render_latex(job["resume_json"])
        except Exception as e:
            logger.error(f"Error rendering latex from json: {e}")
            
    if not tex_code:
        flash("Resume source code not available.", "error")
        return redirect(url_for("results"))
        
    template = """<!DOCTYPE html>
<html>
<head>
    <title>Redirecting to Overleaf...</title>
</head>
<body>
    <p>Opening your tailored resume in Overleaf, please wait...</p>
    <form id="overleafForm" action="https://www.overleaf.com/docs" method="POST">
        <input type="hidden" name="snip" value="{{ tex_code }}">
    </form>
    <script>
        document.getElementById('overleafForm').submit();
    </script>
</body>
</html>"""
    return render_template_string(template, tex_code=tex_code)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
