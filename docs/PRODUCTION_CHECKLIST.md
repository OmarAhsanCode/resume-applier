# Production Checklist (PRODUCTION_CHECKLIST.md)

## 1. Security & Hardening
- [x] No plaintext secrets or real API keys committed to git repository
- [x] `.env.example` provided with documentation and placeholder values
- [x] Production startup validates `SECRET_KEY` is not empty or default
- [x] Session cookies configured (`HttpOnly`, `SameSite=Lax`, `Secure` when HTTPS enabled)
- [x] Request correlation ID (`X-Request-ID`) middleware active
- [x] Standard security headers enabled (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`)
- [x] Path traversal protections verified on resume download and view endpoints
- [x] LaTeX injection protections active (macro stripping and special character escaping)
- [x] Subprocess execution safe (`shell=False`, argument array, `-no-shell-escape`, timeout bounds)
- [x] In-memory rate limiting enabled on expensive routes (`/run`, `/jobs/<id>/generate-resume`, `/companies/verify-all`)
- [x] Request payload bounds enforced (`MAX_CONTENT_LENGTH = 16MB`)
- [x] Sanitized JSON error responses hiding stack traces

## 2. Database & Data Integrity
- [x] SQLite configured with WAL mode (`PRAGMA journal_mode=WAL;`)
- [x] Busy timeout configured (`PRAGMA busy_timeout=5000;`) to avoid write contention locks
- [x] Foreign key constraints enforced
- [x] Non-blocking online database backup script (`scripts/backup_db.py`)
- [x] Persistent volume mounts for database (`/app/data`) and resumes (`/app/generated/resumes`)

## 3. AI Reliability & Cost Control
- [x] Multi-provider AI Router with Primary, Secondary, and Tertiary fallback
- [x] Provider rate limit detection (HTTP 429) and cooldown backoff
- [x] Auth error handling (HTTP 401/403) and circuit breaker disablement
- [x] Configurable resume optimizer iteration limits (`RESUME_MAX_ITERATIONS`)
- [x] Deterministic mock resume fallback if all AI providers fail

## 4. Document Engine (LaTeX & PDF)
- [x] TeX Live installed in Docker image (`texlive-latex-base`, `texlive-latex-extra`, `texlive-fonts-recommended`)
- [x] pdflatex command discovery and execution with timeout
- [x] Automatic cleanup of auxiliary build artifacts (`.aux`, `.log`, `.out`, `.fls`)
- [x] Safe filename generation stripping illegal filesystem characters

## 5. Playwright & Web Discovery
- [x] Playwright Chromium browser installed in Docker image
- [x] Headless browser execution with graceful exception handling
- [x] Strict detection and non-evasion of Cloudflare CAPTCHA challenges (`ACCESS_RESTRICTED`)

## 6. Docker & Containerization
- [x] Non-root container user (`appuser`, UID 1000)
- [x] Lightweight `python:3.11-slim` base image
- [x] Production WSGI Gunicorn configuration (`--workers 1 --threads 4`)
- [x] Container healthcheck configured against `/health`
- [x] Multi-directory volume persistence in `docker-compose.yml`

## 7. Testing & Verification
- [x] 100% pass on all existing 301 regression tests
- [x] 100% pass on new 10 production readiness tests (311 tests total)
- [x] Production smoke test script (`scripts/production_smoke_test.py`) passing
