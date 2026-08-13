import os
import re
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

DB_PATH = os.getenv("DATABASE_PATH", "data/jobs.db")

def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Connects to SQLite database and returns a connection with Row factory."""
    target_path = db_path or DB_PATH
    dir_name = os.path.dirname(target_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = None) -> None:
    """Initializes all database tables according to PROJECT_SPEC.md."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Candidate table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidate (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        profile_json TEXT NOT NULL,
        master_resume_path TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Preferences table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        preferences_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Resume settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS resume_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        template TEXT NOT NULL,
        section_order TEXT NOT NULL,
        resume_length INTEGER DEFAULT 1,
        instructions TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # Jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        source TEXT NOT NULL,
        source_job_id TEXT,
        unique_id TEXT NOT NULL UNIQUE,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        employment_type TEXT,
        description TEXT NOT NULL,
        application_url TEXT NOT NULL,
        posted_date TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        deterministic_score REAL,
        ai_score REAL,
        final_score REAL,
        ai_analysis TEXT,
        resume_json TEXT,
        resume_tex_path TEXT,
        applied_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Migration: Add run_id and discovery_lane columns if table was created previously without them
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN run_id INTEGER;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN discovery_lane TEXT DEFAULT 'targeted';")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN raw_employment_type TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN salary_evidence TEXT DEFAULT 'unknown';")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN salary_text TEXT DEFAULT 'Not disclosed';")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN normalized_salary TEXT DEFAULT 'Not disclosed';")
    except sqlite3.OperationalError:
        pass

    # Migration: Track when a job was last surfaced/shown to the user in results
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN last_shown_at TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass

    # Runs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        requested_jobs INTEGER NOT NULL,
        discovered_count INTEGER DEFAULT 0,
        duplicate_count INTEGER DEFAULT 0,
        invalid_count INTEGER DEFAULT 0,
        filtered_count INTEGER DEFAULT 0,
        analyzed_count INTEGER DEFAULT 0,
        selected_count INTEGER DEFAULT 0,
        resume_success_count INTEGER DEFAULT 0,
        resume_error_count INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'running',
        error TEXT
    );
    """)

    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# Candidate Helper Functions
# ---------------------------------------------------------------------------

def save_candidate(name: str, email: str, phone: str, profile: Dict[str, Any], master_resume_path: str = None, db_path: str = None) -> None:
    """Saves or updates the single candidate profile record."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    profile_json = json.dumps(profile, ensure_ascii=False)
    
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO candidate (id, name, email, phone, profile_json, master_resume_path, created_at, updated_at)
    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name=excluded.name,
        email=excluded.email,
        phone=excluded.phone,
        profile_json=excluded.profile_json,
        master_resume_path=COALESCE(excluded.master_resume_path, candidate.master_resume_path),
        updated_at=excluded.updated_at;
    """, (name, email, phone, profile_json, master_resume_path, now, now))
    conn.commit()
    conn.close()

def get_candidate(db_path: str = None) -> Optional[Dict[str, Any]]:
    """Retrieves the stored candidate profile if set."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM candidate WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["profile"] = json.loads(data["profile_json"])
    return data

# ---------------------------------------------------------------------------
# Preferences Helper Functions
# ---------------------------------------------------------------------------

def save_preferences(preferences: Dict[str, Any], db_path: str = None) -> None:
    """Saves or updates candidate job preferences."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    pref_json = json.dumps(preferences, ensure_ascii=False)
    
    conn.execute("""
    INSERT INTO preferences (id, preferences_json, updated_at)
    VALUES (1, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        preferences_json=excluded.preferences_json,
        updated_at=excluded.updated_at;
    """, (pref_json, now))
    conn.commit()
    conn.close()

def get_preferences(db_path: str = None) -> Optional[Dict[str, Any]]:
    """Retrieves stored job preferences."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return None
    data = json.loads(row["preferences_json"])
    if isinstance(data, dict):
        data.setdefault("discovery_mode", "targeted_and_open")
    return data

# ---------------------------------------------------------------------------
# Resume Settings Helper Functions
# ---------------------------------------------------------------------------

def save_resume_settings(template: str, section_order: List[str], resume_length: int = 1, instructions: str = "", db_path: str = None) -> None:
    """Saves or updates resume settings."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    order_json = json.dumps(section_order, ensure_ascii=False)
    
    conn.execute("""
    INSERT INTO resume_settings (id, template, section_order, resume_length, instructions, updated_at)
    VALUES (1, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        template=excluded.template,
        section_order=excluded.section_order,
        resume_length=excluded.resume_length,
        instructions=excluded.instructions,
        updated_at=excluded.updated_at;
    """, (template, order_json, resume_length, instructions, now))
    conn.commit()
    conn.close()

def get_resume_settings(db_path: str = None) -> Dict[str, Any]:
    """Retrieves stored resume settings or default fallback."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM resume_settings WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {
            "template": "ats",
            "section_order": ["summary", "education", "experience", "projects", "skills", "certifications"],
            "resume_length": 1,
            "instructions": ""
        }
    data = dict(row)
    data["section_order"] = json.loads(data["section_order"])
    return data

# ---------------------------------------------------------------------------
# Jobs Helper Functions
# ---------------------------------------------------------------------------

def job_exists(unique_id: str, db_path: str = None) -> bool:
    """Checks if a job unique_id already exists in database."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT id FROM jobs WHERE unique_id = ?", (unique_id,)).fetchone()
    conn.close()
    return row is not None

def update_job_last_seen(unique_id: str, db_path: str = None) -> None:
    """Updates last_seen timestamp for existing job."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    conn.execute("UPDATE jobs SET last_seen = ?, updated_at = ? WHERE unique_id = ?", (now, now, unique_id))
    conn.commit()
    conn.close()

def mark_jobs_shown(job_ids: List[int], db_path: str = None) -> None:
    """Records that a list of jobs were surfaced to the user (updates last_shown_at)."""
    if not job_ids:
        return
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    conn.executemany(
        "UPDATE jobs SET last_shown_at = ?, updated_at = ? WHERE id = ?",
        [(now, now, jid) for jid in job_ids]
    )
    conn.commit()
    conn.close()

def get_previously_shown_jobs(
    excluded_statuses: List[str] = None,
    limit: int = 500,
    db_path: str = None
) -> List[Dict[str, Any]]:
    """
    Returns previously discovered jobs that are eligible to be re-shown,
    ordered by least-recently-shown first (never-shown last — those are handled
    as new in the pipeline; this is the fallback pool when new jobs are scarce).

    Excluded statuses: applied, rejected, and any others that should never resurface.
    """
    if excluded_statuses is None:
        excluded_statuses = ["applied", "rejected"]
    placeholders = ",".join("?" for _ in excluded_statuses)
    conn = get_connection(db_path)
    rows = conn.execute(f"""
        SELECT * FROM jobs
        WHERE status NOT IN ({placeholders})
        ORDER BY
            CASE WHEN last_shown_at IS NULL THEN 1 ELSE 0 END ASC,
            last_shown_at ASC,
            CASE WHEN final_score IS NOT NULL THEN final_score ELSE 0 END DESC
        LIMIT ?
    """, (*excluded_statuses, limit)).fetchall()
    conn.close()
    return [_hydrate_job_record(dict(r)) for r in rows]

def save_job(job_data: Dict[str, Any], db_path: str = None) -> int:
    """Inserts a new job or updates an existing one if unique_id exists."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    
    unique_id = job_data["unique_id"]
    existing = conn.execute("SELECT id FROM jobs WHERE unique_id = ?", (unique_id,)).fetchone()
    
    if existing:
        job_id = existing["id"]
        conn.execute("""
        UPDATE jobs SET
            run_id = COALESCE(?, run_id),
            company = COALESCE(?, company),
            title = COALESCE(?, title),
            location = COALESCE(?, location),
            employment_type = COALESCE(?, employment_type),
            raw_employment_type = COALESCE(?, raw_employment_type),
            description = COALESCE(?, description),
            application_url = COALESCE(?, application_url),
            posted_date = COALESCE(?, posted_date),
            discovery_lane = COALESCE(?, discovery_lane),
            salary_evidence = COALESCE(?, salary_evidence),
            salary_text = COALESCE(?, salary_text),
            normalized_salary = COALESCE(?, normalized_salary),
            last_seen = ?,
            updated_at = ?
        WHERE unique_id = ?
        """, (
            job_data.get("run_id"),
            job_data.get("company"), job_data.get("title"), job_data.get("location"),
            job_data.get("employment_type"), job_data.get("raw_employment_type"),
            job_data.get("description"), job_data.get("application_url"),
            job_data.get("posted_date"), job_data.get("discovery_lane", "targeted"),
            job_data.get("salary_evidence", "unknown"),
            job_data.get("salary_text", "Not disclosed"),
            job_data.get("normalized_salary", "Not disclosed"),
            now, now, unique_id
        ))
        conn.commit()
        conn.close()
        return job_id

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO jobs (
        run_id, source, source_job_id, unique_id, company, title, location, employment_type,
        raw_employment_type, description, application_url, posted_date, discovery_lane,
        salary_evidence, salary_text, normalized_salary, first_seen, last_seen, status,
        deterministic_score, ai_score, final_score, ai_analysis, resume_json,
        resume_tex_path, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data.get("run_id"),
        job_data.get("source"),
        job_data.get("source_job_id"),
        unique_id,
        job_data.get("company"),
        job_data.get("title"),
        job_data.get("location"),
        job_data.get("employment_type"),
        job_data.get("raw_employment_type"),
        job_data.get("description"),
        job_data.get("application_url"),
        job_data.get("posted_date"),
        job_data.get("discovery_lane", "targeted"),
        job_data.get("salary_evidence", "unknown"),
        job_data.get("salary_text", "Not disclosed"),
        job_data.get("normalized_salary", "Not disclosed"),
        now, now,
        job_data.get("deterministic_score"),
        job_data.get("ai_score"),
        job_data.get("final_score"),
        json.dumps(job_data["ai_analysis"]) if isinstance(job_data.get("ai_analysis"), dict) else job_data.get("ai_analysis"),
        json.dumps(job_data["resume_json"]) if isinstance(job_data.get("resume_json"), dict) else job_data.get("resume_json"),
        job_data.get("resume_tex_path"),
        now, now
    ))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id

def delete_jobs_by_run_id(run_id: int, db_path: str = None) -> int:
    """Deletes ONLY jobs created/saved during a specific run_id."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE run_id = ?", (run_id,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

def clear_jobs_and_runs(db_path: str = None) -> None:
    """Clears all records from jobs and runs tables."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs;")
    cursor.execute("DELETE FROM runs;")
    conn.commit()
    conn.close()

def update_job_evaluation(job_id: int, deterministic_score: float = None, ai_score: float = None, final_score: float = None, ai_analysis: Dict = None, db_path: str = None) -> None:
    """Updates scores and AI analysis for a job."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    
    analysis_json = json.dumps(ai_analysis, ensure_ascii=False) if isinstance(ai_analysis, dict) else ai_analysis
    
    conn.execute("""
    UPDATE jobs SET
        deterministic_score = COALESCE(?, deterministic_score),
        ai_score = COALESCE(?, ai_score),
        final_score = COALESCE(?, final_score),
        ai_analysis = COALESCE(?, ai_analysis),
        updated_at = ?
    WHERE id = ?
    """, (deterministic_score, ai_score, final_score, analysis_json, now, job_id))
    conn.commit()
    conn.close()

def update_job_resume(job_id: int, resume_json: Dict = None, tex_path: str = None, status: str = None, db_path: str = None) -> None:
    """Updates resume data and generated paths for a job."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    
    res_json_str = json.dumps(resume_json, ensure_ascii=False) if isinstance(resume_json, dict) else resume_json
    
    conn.execute("""
    UPDATE jobs SET
        resume_json = COALESCE(?, resume_json),
        resume_tex_path = COALESCE(?, resume_tex_path),
        status = COALESCE(?, status),
        updated_at = ?
    WHERE id = ?
    """, (res_json_str, tex_path, status, now, job_id))
    conn.commit()
    conn.close()

def update_job_status(job_id: int, status: str, db_path: str = None) -> None:
    """Updates job status (new, selected, applied, rejected, saved)."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    applied_at = now if status == 'applied' else None
    
    if applied_at:
        conn.execute("UPDATE jobs SET status = ?, applied_at = ?, updated_at = ? WHERE id = ?", (status, applied_at, now, job_id))
    else:
        conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now, job_id))
    conn.commit()
    conn.close()

def _hydrate_job_record(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hydrates and re-normalizes a job dictionary loaded from SQLite:
    1. Re-evaluates employment type through canonical evidence hierarchy (base.py)
    2. Computes canonical employment_type_display string ('Internship', 'Full-time', etc.)
    3. Re-hydrates salary_text / normalized_salary from description if unpopulated or missing
    4. Sanitizes ai_analysis JSON to ensure key_points contains 2-3 objective job facts and removes candidate evaluation commentary
    """
    if not d or not isinstance(d, dict):
        return d

    import sources.base as base_mod

    raw_emp = d.get("raw_employment_type") or d.get("employment_type")
    title = d.get("title", "")
    desc = d.get("description", "")

    # 1. Employment Type Canonical Normalization
    norm_emp = base_mod.normalize_employment_type(raw_emp, title, desc)
    d["employment_type"] = norm_emp
    d["employment_type_display"] = base_mod.format_employment_type_display(norm_emp)

    # 2. Salary Re-hydration Fallback
    sal_text = d.get("salary_text")
    norm_sal = d.get("normalized_salary")
    if not sal_text or sal_text == "Not disclosed" or not norm_sal or norm_sal == "Not disclosed":
        m_inr, disp_sal, sal_ev = base_mod.extract_salary_with_evidence(sal_text, desc)
        if disp_sal and disp_sal != "Not disclosed":
            d["salary_text"] = disp_sal
            d["normalized_salary"] = disp_sal
            d["salary_evidence"] = sal_ev
        else:
            d["salary_text"] = "Not disclosed"
            d["normalized_salary"] = "Not disclosed"

    # 3. AI Analysis & Key Points Sanitization
    if d.get("ai_analysis"):
        if isinstance(d["ai_analysis"], str):
            try:
                d["ai_analysis"] = json.loads(d["ai_analysis"])
            except Exception:
                d["ai_analysis"] = {}
        if isinstance(d["ai_analysis"], dict):
            raw_kp = d["ai_analysis"].get("key_points", [])
            clean_kp = []
            if isinstance(raw_kp, list):
                for p in raw_kp:
                    p_str = str(p).strip()
                    if p_str and not re.search(r"\b(candidate|omar|applicant|resume|profile|demonstrates|fit|match|alignment|suitable)\b", p_str.lower()):
                        clean_kp.append(p_str)

            if not clean_kp:
                role_sum = d["ai_analysis"].get("role_summary") or title
                techs = d["ai_analysis"].get("key_technologies") or []
                clean_kp = [f"Focus: {role_sum}"]
                if techs:
                    clean_kp.append(f"Technologies: {', '.join(techs[:3])}")
                if d.get("location"):
                    clean_kp.append(f"Location: {d.get('location')}")

            d["ai_analysis"]["key_points"] = clean_kp[:3]

    if isinstance(d.get("resume_json"), str):
        try:
            d["resume_json"] = json.loads(d["resume_json"])
        except Exception:
            pass

    return d

def get_job_by_id(job_id: int, db_path: str = None) -> Optional[Dict[str, Any]]:
    """Fetches a single job by DB ID."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _hydrate_job_record(dict(row))

def delete_job_by_id(job_id: int, db_path: str = None) -> None:
    """Deletes a single job by DB ID."""
    conn = get_connection(db_path)
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

def get_all_jobs(status_filter: str = None, limit: int = 100, db_path: str = None) -> List[Dict[str, Any]]:
    """Returns jobs, optionally filtered by status, ordered by final_score descending or created_at descending."""
    conn = get_connection(db_path)
    if status_filter:
        rows = conn.execute("""
        SELECT * FROM jobs WHERE status = ? 
        ORDER BY CASE WHEN final_score IS NOT NULL THEN final_score ELSE 0 END DESC, id DESC 
        LIMIT ?
        """, (status_filter, limit)).fetchall()
    else:
        rows = conn.execute("""
        SELECT * FROM jobs 
        ORDER BY CASE WHEN final_score IS NOT NULL THEN final_score ELSE 0 END DESC, id DESC 
        LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append(_hydrate_job_record(dict(r)))
    return results

# ---------------------------------------------------------------------------
# Runs Helper Functions
# ---------------------------------------------------------------------------

def create_run(requested_jobs: int, db_path: str = None) -> int:
    """Creates a new run record and returns its ID."""
    conn = get_connection(db_path)
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO runs (started_at, requested_jobs, status)
    VALUES (?, ?, 'running')
    """, (now, requested_jobs))
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id

def update_run_progress(
    run_id: int,
    discovered_count: int = None,
    duplicate_count: int = None,
    invalid_count: int = None,
    filtered_count: int = None,
    analyzed_count: int = None,
    selected_count: int = None,
    resume_success_count: int = None,
    resume_error_count: int = None,
    status: str = None,
    error: str = None,
    db_path: str = None
) -> None:
    """Updates stats and status of an ongoing or completed run."""
    conn = get_connection(db_path)
    completed_at = datetime.now().isoformat() if status in ('completed', 'failed', 'partial') else None
    
    conn.execute("""
    UPDATE runs SET
        discovered_count = COALESCE(?, discovered_count),
        duplicate_count = COALESCE(?, duplicate_count),
        invalid_count = COALESCE(?, invalid_count),
        filtered_count = COALESCE(?, filtered_count),
        analyzed_count = COALESCE(?, analyzed_count),
        selected_count = COALESCE(?, selected_count),
        resume_success_count = COALESCE(?, resume_success_count),
        resume_error_count = COALESCE(?, resume_error_count),
        status = COALESCE(?, status),
        completed_at = COALESCE(?, completed_at),
        error = COALESCE(?, error)
    WHERE id = ?
    """, (
        discovered_count, duplicate_count, invalid_count, filtered_count,
        analyzed_count, selected_count, resume_success_count, resume_error_count,
        status, completed_at, error, run_id
    ))
    conn.commit()
    conn.close()

def get_run(run_id: int, db_path: str = None) -> Optional[Dict[str, Any]]:
    """Retrieves a specific run by ID."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_latest_run(db_path: str = None) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent run."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None
