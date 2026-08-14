import os
import sys
import json
import logging
import tempfile
import shutil

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_resume_v1_6")

# Add workspace to path
sys.path.insert(0, os.path.abspath("."))

import database
import app as flask_app
import resume
import resume_optimizer
import ai
from sources.base import create_normalized_job

def run_e2e_resume_validation():
    print("=" * 80)
    print("[AUDIT] V1.6 ATS-OPTIMIZED RESUME GENERATION & TAILORING PRODUCTION AUDIT")
    print("=" * 80)

    temp_dir = tempfile.mkdtemp(prefix="resume_v1_6_audit_")
    test_db = os.path.join(temp_dir, "test_jobs.db")
    database.init_db(test_db)
    
    orig_db = database.DB_PATH
    database.DB_PATH = test_db
    flask_app.app.testing = True
    client = flask_app.app.test_client()

    try:
        # 1. Candidate Setup
        master_profile = {
            "name": "Alex Mercer",
            "email": "alex.mercer@cs.university.edu",
            "phone": "+1 555-0199",
            "links": {
                "linkedin": "https://linkedin.com/in/alexmercer-dev",
                "github": "https://github.com/alexmercer"
            },
            "skills": [
                "Python", "SQL", "Flask", "FastAPI", "PyTorch", "Git", "Docker",
                "PostgreSQL", "JavaScript", "Linux", "REST APIs"
            ],
            "education": [
                {
                    "degree": "B.S. in Computer Science",
                    "institution": "Stanford University",
                    "graduation_year": 2026,
                    "cgpa": "3.92/4.00"
                }
            ],
            "experience": [
                {
                    "company": "ScaleAI Labs",
                    "role": "Software Engineering Intern",
                    "start_date": "2025-06",
                    "end_date": "2025-08",
                    "bullets": [
                        "Optimized distributed data pipeline backend in Python and PostgreSQL, reducing query latency by 32%.",
                        "Designed REST API microservices handling 1200+ concurrent requests."
                    ]
                }
            ],
            "projects": [
                {
                    "name": "Neural Semantic Search Engine",
                    "description": "High-throughput vector search engine built with PyTorch and Flask.",
                    "technologies": ["Python", "PyTorch", "Flask", "Docker"],
                    "bullets": [
                        "Indexed 500k+ unstructured documents with sub-50ms retrieval latency."
                    ]
                }
            ],
            "certifications": ["AWS Certified Cloud Practitioner"]
        }
        database.save_candidate("Alex Mercer", "alex.mercer@cs.university.edu", "+1 555-0199", master_profile, db_path=test_db)
        print("[PASS] [1/5] Master Candidate Profile Saved into SQLite (Factual Source of Truth).")

        # 2. Define 5 Target Jobs across Discovery Types
        target_jobs = [
            {
                "source": "first_party",
                "source_job_id": "google-101",
                "company": "Google",
                "title": "Software Engineer, Early Career",
                "location": "Bengaluru, Karnataka, India",
                "description": """
                Minimum qualifications:
                - Bachelor's degree in Computer Science or related technical field.
                - Experience programming in Python, C++, or Java.
                - Experience with Data Structures, Algorithms, and SQL.
                Preferred qualifications:
                - Experience with Machine Learning, PyTorch, or TensorFlow.
                - Familiarity with distributed systems and Linux.
                """
            },
            {
                "source": "first_party",
                "source_job_id": "amazon-202",
                "company": "Amazon",
                "title": "Software Development Engineer I",
                "location": "Hyderabad, Telangana, India",
                "description": """
                Basic Qualifications:
                - BS in Computer Science or equivalent.
                - 1+ years of non-internship professional software development experience or new graduate.
                - Proficiency in Python, PostgreSQL, and REST APIs.
                Preferred Qualifications:
                - Experience building scalable cloud services with AWS, Docker, and Kubernetes.
                """
            },
            {
                "source": "first_party",
                "source_job_id": "microsoft-303",
                "company": "Microsoft",
                "title": "Software Engineer II - Cloud & AI",
                "location": "Hyderabad, Telangana, India",
                "description": """
                Qualifications:
                - Required: Bachelor's degree in CS, proficiency with Python, SQL, and Docker.
                - Preferred: Knowledge of Azure, C#, CI/CD pipelines, and PyTorch.
                """
            },
            {
                "source": "workday",
                "source_job_id": "salesforce-404",
                "company": "Salesforce",
                "title": "Associate Software Engineer",
                "location": "Bengaluru, India",
                "description": """
                Requirements:
                - Strong foundation in Python, JavaScript, and database query design (Postgres/SQL).
                - Knowledge of Git version control and RESTful API architecture.
                Bonus:
                - Experience with React, Flask, and cloud containers (Docker).
                """
            },
            {
                "source": "adzuna",
                "source_job_id": "adzuna-505",
                "company": "Databricks",
                "title": "Software Engineer Intern",
                "location": "Bengaluru, Karnataka, India",
                "description": """
                Requirements:
                - Currently pursuing a Bachelor's or Master's degree in Computer Science.
                - Strong coding skills in Python or Scala.
                - Familiarity with Linux environments and Git.
                Preferred:
                - Interest in distributed data systems, SQL, and PyTorch.
                """
            }
        ]

        print(f"\n[INFO] [2/5] Running ATS Optimization & Tailoring on {len(target_jobs)} Target Jobs:")

        audit_results = []

        for idx, j_spec in enumerate(target_jobs, 1):
            norm_job = create_normalized_job(
                source=j_spec["source"],
                source_job_id=j_spec["source_job_id"],
                company=j_spec["company"],
                title=j_spec["title"],
                location=j_spec["location"],
                employment_type="full-time",
                description=j_spec["description"],
                application_url=f"https://careers.example.com/{j_spec['source_job_id']}"
            )
            job_id = database.save_job(norm_job, db_path=test_db)
            database.update_job_status(job_id, "selected", db_path=test_db)

            # Run Full Pipeline
            result = resume_optimizer.tailor_resume_pipeline(
                candidate_profile=master_profile,
                job_dict=norm_job,
                max_iterations=2
            )

            res_json = result["resume_json"]
            match_score = result["match_score"]
            match_details = result["match_details"]
            reqs = result["requirements"]
            matrix = result["match_matrix"]

            # Validate Factual Integrity
            is_valid, violations, sanitized = resume_optimizer.validate_factual_integrity(res_json, master_profile)
            assert is_valid, f"Factual integrity violation in job {j_spec['company']}: {violations}"
            assert len(violations) == 0, f"Violations found: {violations}"

            # Render LaTeX & Validate ATS Format
            latex_code = resume.render_latex(sanitized)
            ats_valid, ats_issues = resume_optimizer.validate_ats_format(latex_code)
            assert ats_valid, f"ATS format issues for {j_spec['company']}: {ats_issues}"

            # Save File & DB
            sanitized_comp = resume.sanitize_filename(j_spec["company"])
            sanitized_title = resume.sanitize_filename(j_spec["title"])
            tex_path = os.path.join(temp_dir, f"{sanitized_comp}_{sanitized_title}_{job_id}.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_code)

            database.update_job_resume(
                job_id=job_id,
                resume_json=sanitized,
                tex_path=tex_path,
                status="selected",
                resume_score=match_score,
                resume_match_details=match_details,
                db_path=test_db
            )

            # Test details endpoint via Flask client
            resp = client.get(f"/jobs/{job_id}/resume-details")
            assert resp.status_code == 200, f"Failed GET /jobs/{job_id}/resume-details"
            det_json = resp.get_json()
            assert det_json["status"] == "success"
            assert det_json["resume_score"] == match_score

            audit_results.append({
                "company": j_spec["company"],
                "title": j_spec["title"],
                "source": j_spec["source"],
                "seniority": reqs["seniority"],
                "match_score": match_score,
                "sub_scores": match_details["sub_scores"],
                "matched_required": matrix["matched_required"],
                "unsupported_required": matrix["unsupported_required"],
                "matched_preferred": matrix["matched_preferred"],
                "unsupported_preferred": matrix["unsupported_preferred"],
                "violations_count": len(violations)
            })

            print(f"  [{idx}/{len(target_jobs)}] {j_spec['company']} ({j_spec['title']}):")
            print(f"      * Seniority: {reqs['seniority']}")
            print(f"      * Match Score: {match_score}% (Req: {match_details['sub_scores']['required_skills']}%, Keyword: {match_details['sub_scores']['keyword_coverage']}%)")
            print(f"      * Matched Required: {matrix['matched_required']}")
            print(f"      * Unsupported Required: {matrix['unsupported_required']}")
            print(f"      * Unsupported Preferred: {matrix['unsupported_preferred']}")
            print(f"      * Factual Integrity Violations: 0 (Strictly Validated)")

        print("\n[PASS] [3/5] All 5 Target Jobs Tailored & ATS-Validated with Zero Factual Violations.")

        # 3. Verify Master Resume Immutability
        cand_verify = database.get_candidate(db_path=test_db)
        assert cand_verify["profile"]["skills"] == master_profile["skills"]
        assert cand_verify["profile"]["name"] == master_profile["name"]
        print("[PASS] [4/5] Master Candidate Profile Strictly Preserved (0 mutations).")

        # 4. Verify SQLite Database State
        all_jobs = database.get_all_jobs(db_path=test_db)
        assert len(all_jobs) == 5
        for j in all_jobs:
            assert j["resume_score"] is not None
            assert j["resume_match_details"] is not None
            assert j["resume_tex_path"] is not None
            assert os.path.exists(j["resume_tex_path"])
        print("[PASS] [5/5] SQLite Database & Resume Associations Fully Verified.")

        print("\n" + "=" * 80)
        print("[COMPLETE] V1.6 PRODUCTION AUDIT COMPLETE -- 100% PASS RATE")
        print("=" * 80)

    finally:
        database.DB_PATH = orig_db
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    run_e2e_resume_validation()
