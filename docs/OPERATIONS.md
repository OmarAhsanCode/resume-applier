# Operations Runbook (OPERATIONS.md)

## 1. Overview
This runbook provides step-by-step procedures for managing, maintaining, backing up, restoring, and troubleshooting the personal job automation system in production.

---

## 2. Service Management (Docker & Gunicorn)

### Starting the Application
```bash
# Start all containers in background
docker compose up -d

# Inspect live status
docker compose ps
```

### Stopping & Restarting
```bash
# Gracefully stop
docker compose stop

# Restart
docker compose restart app

# View live container logs
docker compose logs -f app
```

---

## 3. Health & Readiness Monitoring

### Liveness Probe (`GET /health`)
```bash
curl -i http://localhost:8000/health
# Response: {"status": "ok", "app_env": "production"}
```

### Readiness Probe (`GET /health/ready`)
```bash
curl -i http://localhost:8000/health/ready
# Response: {"status": "ready", "database": "ok", "pdflatex_available": true, "app_env": "production"}
```

---

## 4. Database Backup & Disaster Recovery

### Creating an Online Backup
The application includes `scripts/backup_db.py` which uses SQLite's non-blocking online backup API.
```bash
# Inside container or host:
python scripts/backup_db.py backups/

# Or via docker exec:
docker compose exec app python scripts/backup_db.py /app/backups
```

### Restoring from Backup
1. Stop the application container:
   ```bash
   docker compose stop app
   ```
2. Replace `data/jobs.db` with the chosen backup file:
   ```bash
   cp backups/jobs_backup_YYYYMMDD_HHMMSS.db data/jobs.db
   ```
3. Remove any existing WAL journal files if present:
   ```bash
   rm -f data/jobs.db-wal data/jobs.db-shm
   ```
4. Start the application:
   ```bash
   docker compose start app
   ```

---

## 5. Secret Rotation Procedure

1. Generate a new cryptographic secret key:
   ```bash
   openssl rand -hex 32
   ```
2. Update `.env` with the new `SECRET_KEY` or rotate AI API keys (`AI_API_KEY`, `THIRD_AI_API_KEY`).
3. Recreate the container with updated environment variables:
   ```bash
   docker compose up -d --force-recreate
   ```

---

## 6. Incident Handling & Degradation Matrix

| Incident | Impact | Automated System Response | Operator Resolution |
| :--- | :--- | :--- | :--- |
| **Primary AI Outage (429/500/503)** | Resume tailoring / analysis fails on primary | Router applies 60s cooldown and automatically fails over to Secondary and Tertiary AI providers | Check provider balance or switch default provider in `.env` |
| **All AI Providers Unavailable** | Semantic AI matching unavailable | Router falls back to deterministic rule-based resume builder; run completes without crashing | Investigate provider connectivity |
| **External ATS / Workday 404 / 403** | Single company discovery failure | Pipeline isolates failure, logs warning, and continues with remaining companies | Re-verify company on Watchlist UI |
| **Cloudflare CAPTCHA Challenge** | Career page blocks automated scrapers | Marked as `[ACCESS_RESTRICTED]` without attempting unsafe bypass | Use direct API platform or add manual configuration |
| **LaTeX / pdflatex Missing or Crash** | PDF compilation error | Returns failure status, preserves raw `.tex` resume file, allows `.tex` download | Verify `texlive-latex-base` installation |
| **Google Sheets API Rate Limit** | Sheets sync failure | Sheets sync error logged; local SQLite records remain intact | Re-trigger manual sync from Results page |

---

## 7. Rollback Procedure
If a deployment fails:
```bash
# Rollback container image to previous tag:
docker compose down
docker pull <previous-image-tag>
docker compose up -d
```
