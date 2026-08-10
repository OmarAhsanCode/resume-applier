# Personal Job Automation System — V1

A personal, single-user job-search automation system built with **Python**, **Flask**, **SQLite**, **Requests / BeautifulSoup**, **Hosted Open-Source AI**, **LaTeX (`pdflatex`)**, and **Google Drive & Google Sheets APIs**.

---

## Key Features

1. **One-Time Master CV Upload**: Extract structured candidate profile factual data from PDF.
2. **Job Discovery**: Discovers job postings across permitted public ATS feeds (Greenhouse, Lever, Ashby).
3. **Stable ID Deduplication**: Deduplicates using stable source IDs (`source:source_job_id` or `source:normalized_url`) stored in local SQLite database (`data/jobs.db`).
4. **Conservative Hard Filtering**: Retains high-recall opportunities. Hard-filters only obvious profession/experience mismatches (never hard-filters missing skills).
5. **Deterministic Ranking**: Scores jobs from 0–100 using weighted rules (Role 35%, Location 25%, Experience 20%, Employment Type 10%, Skill Overlap 10%, Dream Company Bonus +5 to +10 pts).
6. **Hosted Open-Source AI Analysis**: Evaluates top candidate pool for semantic match recommendations. `final_score = deterministic_score * 0.60 + ai_score * 0.40`.
7. **LaTeX Resume Tailoring**: Customizes bullet points and summaries using candidate truthfulness rules, escaping special characters, and compiling to single-page PDF resumes.
8. **Google Integration**: Uploads PDFs to Google Drive and syncs application dashboard to Google Sheets.
9. **Dashboard & Results UI**: Simple Flask/Jinja2/Vanilla JS web app displaying run progress polling, status actions (Applied, Saved, Rejected), and direct official application links.

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Git
- `pdflatex` (optional, for PDF compilation; if missing, system generates `.tex` files and logs gracefully).

### 2. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and configure settings:
```bash
cp .env.example .env
```

Configured `.env` options:
- `AI_API_KEY`: API key for hosted open-source AI model (e.g. Groq, Together AI, OpenRouter, Gemini OpenAI compatibility layer).
- `AI_BASE_URL`: Base URL (default: `https://api.groq.com/openai/v1`).
- `AI_MODEL_NAME`: Model family (e.g. `llama-3.3-70b-versatile`, `qwen-2.5-72b`).
- `PDFLATEX_PATH`: Path to `pdflatex` binary if not on PATH.
- `GOOGLE_CREDENTIALS_FILE`: Path to `credentials.json`.
- `GOOGLE_DRIVE_FOLDER_ID`: Google Drive folder ID for generated resume PDFs.
- `GOOGLE_SHEETS_SPREADSHEET_ID`: Google Spreadsheet ID for application sync.

---

## How to Run

### Start the Flask Web Application
```bash
python app.py
```
Open your browser at `http://localhost:5000`.

### Workflow
1. Navigate to **Upload CV** (`/setup`) and upload your Master CV PDF.
2. Review and verify your candidate details on **Profile** (`/profile`).
3. Set your target roles, locations, and dream companies on **Preferences** (`/preferences`).
4. Click **FIND JOBS** on the **Dashboard** (`/`).
5. Track real-time progress as jobs are discovered, deduplicated, ranked, and tailored.
6. View ranked recommendations, generated resumes, and apply links on **Results** (`/results`).

---

## Running Tests

Run the complete test suite:
```bash
python -m unittest discover tests
```

Individual test modules:
- Database: `python -m unittest tests/test_database.py`
- AI Module: `python -m unittest tests/test_ai.py`
- Job Discovery: `python -m unittest tests/test_sources.py`
- Pipeline & Scoring: `python -m unittest tests/test_pipeline.py`
- End-to-End Workflow: `python -m unittest tests/test_e2e.py`
