# PRODUCTION AUDIT

## 1. Executive Summary & Production Readiness Overview
This audit was performed in accordance with **PROJECT_SPEC.md**, **AGENTS.md**, and the **PRODUCTION START** specifications.
The application is a single-user, personal job discovery, ranking, AI-tailoring, and LaTeX/PDF generation system with Google Sheets synchronization.
All baseline 301 unit and integration tests are currently **passing (100% OK)**.

The current architecture consists of:
- **Web App**: Flask 3.x, Jinja2, Vanilla HTML/CSS/JS.
- **Database**: SQLite3 (`data/jobs.db`).
- **Discovery Sources**: Direct ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday), first-party web discovery heuristics, and Playwright Chromium headless fallback.
- **AI Integration**: Multi-provider OpenAI-compatible AI Router (Primary, Secondary, Tertiary providers) with automatic fallback and deterministic mocks.
- **Document Engine**: LaTeX compilation via `pdflatex` with security flags (`-no-shell-escape`, nonstopmode) and text escaping.
- **Integrations**: Google Sheets OAuth2/token synchronization.

---

## 2. Architecture & Runtime Dependencies
- **Python**: 3.10+ / 3.11+
- **Core Python Packages**:
  - `Flask>=3.0.0`
  - `requests>=2.31.0`
  - `beautifulsoup4>=4.12.0`
  - `pypdf>=4.0.0`
  - `google-api-python-client>=2.100.0`
  - `google-auth-httplib2>=0.2.0`
  - `google-auth-oauthlib>=1.2.0`
  - `python-dotenv>=1.0.0`
  - `playwright>=1.40.0`
  - *(To add)*: `gunicorn>=21.2.0`
- **System Binary Dependencies**:
  - `pdflatex` (TeX Live on Linux / Mac / Windows)
  - `chromium` (via Playwright) + Linux shared libraries (`libnss3`, `libatk-bridge2.0-0`, etc.)

---

## 3. External Services & Network Dependencies
1. **Hosted Open-Source AI Model Providers** (Groq, Together, OpenRouter, etc.):
   - Endpoint: `/chat/completions` (JSON mode supported).
   - Timeouts: 30s per call, 60s/300s cooldown tracking on rate limits (429) or auth errors (401/403).
2. **ATS & Career APIs**:
   - Greenhouse (`boards-api.greenhouse.io`), Lever (`api.lever.co`), Ashby (`api.ashbyhq.com`), SmartRecruiters (`api.smartrecruiters.com`), Workday (`wd3.myworkdayjobs.com`), Adzuna API.
   - Timeouts: Explicit 4s to 10s timeouts with safe retry policies.
3. **Google APIs**:
   - Google Sheets API v4 (OAuth2 client flow / token refresh).

---

## 4. Persistent Data & Filesystem Assets
1. **SQLite Database**: `data/jobs.db` (stores candidate profile, preferences, resume settings, discovery history, score breakdown, run logs).
2. **Uploaded Files**: `uploads/` (master CV pdfs).
3. **Generated Documents**: `generated/resumes/*.tex`, `generated/resumes/*.pdf`.
4. **Configuration Watchlists**: `config/companies.json`, `config/sources.json`.
5. **Credentials**: `credentials.json`, `token.json` (OAuth tokens).

---

## 5. Security & Risk Audit

| Category | Finding | Current State | Production Fix Required |
| :--- | :--- | :--- | :--- |
| **Secrets & Keys** | Secret Key & API keys | `.env.example` has placeholder keys; `.gitignore` ignores `.env`, `credentials.json`, `token.json`, `*.db`. | Enforce startup validation that fails if `SECRET_KEY` is default in `APP_ENV=production`. |
| **Path Traversal** | `/jobs/<id>/download-resume` & `/jobs/<id>/view-resume` | Safe checks: checks `os.path.abspath(tex_path).startswith(resumes_dir)`. Filenames are sanitized via `resume.sanitize_filename()`. | Ensure strict canonical check and proper headers (`Content-Disposition` quoting, MIME types). |
| **LaTeX Injection** | `resume.render_latex()` | `latex_escape()` escapes `\`, `&`, `%`, `$`, `#`, `_`, `{`, `}`, `^`, `~`. | Ensure dangerous macros (`\input`, `\write18`, `\openin`, `\openout`) cannot be injected even if escaping is bypassed. Maintain `-no-shell-escape`. |
| **Subprocess Execution** | `resume.compile_pdf()` | Uses `subprocess.run(list, shell=False, timeout=30)` with `-no-shell-escape` and `-halt-on-error`. | Safe. Add bounds on pdflatex stdout/stderr capture and isolated temp directory cleaning. |
| **Request Limits** | Flask `MAX_CONTENT_LENGTH` | Currently not set on Flask app. Large POST could exhaust memory. | Add `app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024` (16MB) and input bounds on text fields. |
| **Security Headers** | HTTP headers | Currently default Flask headers. | Add `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, and tailored CSP. |
| **Sessions & Cookies** | Flask session | Default cookies. | Configure `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, and `SESSION_COOKIE_SECURE` in production. |
| **Error Handling** | Unhandled exceptions | Standard Flask 500 HTML in debug/unhandled modes. | Add custom 400, 404, 429, 500 JSON/HTML error handlers that never expose stack traces or credentials. |
| **Observability** | Request correlation | No Correlation ID. | Add `X-Request-ID` middleware that generates or forwards UUID per request. |
| **Health Checks** | Container liveness/readiness | None existed. | Add `GET /health` (liveness) and `GET /health/ready` (readiness). |
| **Concurrency / Workers** | Background Threads | In-memory `_active_run_lock`, `_discovery_tasks`, `_verify_all_lock` are process-local. | Document single-worker Gunicorn architecture (`-w 1 --threads 4`) for background task safety. Enable SQLite WAL mode and busy timeout. |

---

## 6. Detailed Issue Categorization

### P0 (Must Fix Before Production Deployment)
1. **Centralized Configuration System**: Create `config.py` supporting `DevelopmentConfig`, `TestingConfig`, `ProductionConfig`, validating required secrets and environment variables.
2. **Missing Production WSGI Entrypoint & Server**: Add `gunicorn` to `requirements.txt` and prepare production WSGI entrypoint (`app:app` or `wsgi.py`).
3. **SQLite WAL & Busy Timeout**: Configure `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` on database connections to prevent database locked errors under concurrent web requests and background thread writes.
4. **Flask Request Limits & Error Masking**: Set `MAX_CONTENT_LENGTH`, add JSON error handlers that hide tracebacks, and configure security headers + secure cookie flags.
5. **Production Health & Readiness Endpoints**: Add lightweight `/health` and `/health/ready` endpoints.
6. **Dockerization & Assets**: Create production `Dockerfile` with non-root user, TeX Live (`pdflatex`), Playwright Chromium, `.dockerignore`, and `docker-compose.yml` with persistent volumes (`data/`, `generated/resumes/`, `uploads/`, `config/`).

### P1 (Important Hardening & Reliability)
1. **Correlation IDs**: Inject `X-Request-ID` into request context, logs, and error responses.
2. **Configurable Cost Limits**: Enforce `RESUME_MAX_ITERATIONS` in `resume_optimizer.py` and `ai.py`.
3. **Rate Limiting Protection**: Implement lightweight in-memory rate limiter on expensive endpoints (`/run`, `/jobs/<id>/generate-resume`, `/companies/verify-all`).
4. **Safe Database Backup Script**: Create `scripts/backup_db.py` to perform online SQLite backups (`sqlite3.Connection.backup`) to timestamped archives.
5. **Production Smoke Test**: Create `scripts/production_smoke_test.py` to verify health, database, routes, PDF compilation, and downloads.

### P2 (Documentation & Operations)
1. **Operations Runbook**: Create `docs/OPERATIONS.md` covering backup, restore, secret rotation, updates, and troubleshooting.
2. **Production Checklist**: Create `docs/PRODUCTION_CHECKLIST.md`.
3. **Update README.md**: Complete instructions for local development, Docker deployment, environment variables, and limitations.

---

## 7. Recommended Deployment Architecture
```text
Internet
   ↓
Reverse Proxy / TLS Termination (Caddy / Nginx / Cloudflare)
   ↓ (HTTP)
Gunicorn (1 worker, 4 threads: gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 app:app)
   ↓
Flask Application (Security Headers, Request ID, Rate Limiter, Error Handlers)
   ├── SQLite Database (WAL mode, busy_timeout=5000ms) [/app/data]
   ├── Generated Resumes Volume [/app/generated/resumes]
   ├── Uploads Volume [/app/uploads]
   ├── External AI Providers (Groq / OpenRouter / Together)
   ├── External Career APIs (Greenhouse / Lever / Ashby / SmartRecruiters / Workday)
   ├── Local pdflatex (TeX Live, -no-shell-escape)
   └── Local Headless Chromium (Playwright)
```

---

## 8. Conclusion
The codebase is solid, cleanly modularized, and functionally comprehensive. Implementing the P0 and P1 security, configuration, Dockerization, and observability enhancements will achieve full production readiness without disturbing the existing 301 passing tests.
