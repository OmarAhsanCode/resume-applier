# Personal Job Automation System — Production Ready

A personal, single-user job-search automation and ATS resume tailoring system built with **Python**, **Flask**, **SQLite**, **Requests / BeautifulSoup**, **Playwright**, **Hosted Open-Source AI**, **LaTeX (`pdflatex`)**, and **Google Sheets API**.

---

## Key Features

1. **One-Time Master CV Upload**: Extract structured candidate profile factual data from PDF.
2. **Multi-Source Job Discovery**: Discovers job postings across direct ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday), first-party career pages, and Playwright Chromium headless fallback.
3. **Company Watchlist Management**: Dynamic watchlist with priority scoring and real-time endpoint verification.
4. **Stable ID Deduplication**: Deduplicates using stable source IDs (`source:source_job_id` or `source:normalized_url`) stored in persistent SQLite database (`data/jobs.db`).
5. **Conservative Hard Filtering**: Retains high-recall opportunities. Hard-filters only obvious profession/experience mismatches (never hard-filters missing skills).
6. **Deterministic Ranking**: Scores jobs from 0–100 using weighted rules (Role 35%, Location 25%, Experience 20%, Employment Type 10%, Skill Overlap 10%, Dream Company Bonus +5 to +10 pts).
7. **Hosted Multi-Provider AI Router**: Automatically evaluates jobs and tailors resumes with primary, secondary, and tertiary fallback.
8. **LaTeX Resume Tailoring & ATS Scoring**: Customizes bullet points with strict factual integrity rules, LaTeX macro security escaping, ATS keyword matching, and compiling to single-page PDF resumes or Overleaf export.
9. **Google Sheets Sync**: Syncs application dashboard to Google Sheets with custom Overleaf LaTeX compiler links.
10. **Production Hardened**: Built-in Gunicorn WSGI server, SQLite WAL mode, rate limiting, request correlation IDs, security headers, online database backup, and Docker containerization.

---

## Quick Start (Docker Deployment)

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env and supply your SECRET_KEY, AI_API_KEY, and optional Google credentials
```

### 2. Build and Start Container
```bash
docker compose up -d --build
```

### 3. Check Health
```bash
curl http://localhost:8000/health
# {"status": "ok", "app_env": "production"}
```
Access the dashboard at `http://localhost:8000`.

---

## Local Development Setup

### 1. Prerequisites
- Python 3.10+
- `pdflatex` (TeX Live / MacTeX / MiKTeX)
- Playwright Chromium (`playwright install chromium`)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Start Development Server
```bash
python app.py
```
Open `http://localhost:5000`.

---

## Running Tests

Run the complete 311+ test suite:
```bash
python -m unittest discover tests
```

Run the production smoke test:
```bash
python scripts/production_smoke_test.py
```

Run database online backup:
```bash
python scripts/backup_db.py backups/
```

---

## Operations & Production Architecture

See:
- [docs/OPERATIONS.md](docs/OPERATIONS.md) - Operations runbook, backup/restore procedures, secret rotation, incident response.
- [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) - Comprehensive security, data integrity, and deployment checklist.
- [PRODUCTION_AUDIT.md](PRODUCTION_AUDIT.md) - Complete architectural audit and risk assessment.
