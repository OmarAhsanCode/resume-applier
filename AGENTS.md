# AGENTS.md

## Project: Personal Job Automation System

You are the coding agent responsible for implementing and maintaining this project.

The complete product and technical specification is located in:

`PROJECT_SPEC.md`

**`PROJECT_SPEC.md` is the source of truth for what the application should do.**

This file defines **how you should work** while implementing it.

---

# 1. Project Context

This is a **personal, single-user job-search automation application**.

The goal is to:

1. Parse the user's master CV once.
2. Store a verified structured candidate profile.
3. Store the user's job-search preferences.
4. Discover new jobs from permitted/public job sources.
5. Deduplicate jobs using stable source IDs.
6. Conservatively filter and deterministically rank jobs.
7. Use a hosted open-source AI model for deeper semantic job analysis.
8. Select the best jobs.
9. Tailor the user's resume for each selected job.
10. Generate LaTeX source files through a fixed template.
11. Generate Overleaf redirect links for the generated LaTeX code.
12. Store job/application information and Overleaf links in Google Sheets.

The application is **not a SaaS product**.

It is not intended to support multiple users.

It is not intended to automatically submit job applications.

---

# 2. Source of Truth

Before making architectural or implementation decisions:

1. Read `PROJECT_SPEC.md`.
2. Read this `AGENTS.md`.
3. Inspect the existing repository.
4. Follow the architecture already established in the specification.

Do not contradict the specification unless there is a concrete technical reason.

If you believe the specification contains a problem:

1. Explain the problem.
2. Explain the simplest alternative.
3. Ask for approval before changing the architecture.

Do not silently redesign the project.

---

# 3. Core Technology Stack

Use the following stack.

## Backend

- Python
- Flask

## Frontend

- Jinja2
- HTML
- CSS
- Vanilla JavaScript

## Database

- SQLite
- Python's built-in `sqlite3`

## HTTP

- `requests`

## HTML parsing

- BeautifulSoup

## Browser automation

- Playwright only when a source genuinely requires JavaScript rendering

## AI

- Hosted open-source model API

## Resume

- LaTeX
- `pdflatex`

## Google

- Google Sheets API

---

# 4. Technologies Explicitly Not Wanted

Do **not** introduce these unless the user explicitly asks for them:

- React
- Vue
- Angular
- FastAPI
- Django
- SQLAlchemy
- Alembic
- PostgreSQL
- MongoDB
- Firebase
- Supabase
- Redis
- Celery
- LangChain
- LangGraph
- CrewAI
- AutoGen
- vector databases
- embeddings
- microservices
- Kubernetes
- Docker as a requirement
- authentication systems
- multi-user architecture

Do not add a framework merely because it is popular or technically capable of solving the problem.

---

# 5. Simplicity Rule

This is one of the most important project requirements.

**Prefer the simplest implementation that correctly satisfies the specification.**

For example:

If SQLite + `sqlite3` solves the problem, do not introduce an ORM.

If a Python function solves the problem, do not create a class hierarchy.

If a normal HTTP request works, do not introduce a browser automation layer.

If deterministic logic works, do not use an LLM.

If a simple Flask route works, do not create an additional API framework.

Avoid premature abstraction.

---

# 6. Single-User Architecture

This is a personal application.

Do not design for:

- thousands of users
- concurrent users
- distributed deployments
- horizontal scaling
- tenant isolation
- enterprise authentication

Optimize for:

- simplicity
- reliability
- maintainability
- low cost
- easy debugging

---

# 7. AI Usage Philosophy

AI should be used only where semantic reasoning is genuinely useful.

Use AI for:

### 1. Master CV parsing

Convert CV text into structured candidate information.

### 2. Job analysis

Understand:

- required qualifications
- preferred qualifications
- skills
- responsibilities
- location requirements
- experience requirements
- candidate/job fit

### 3. Ambiguous job matching

AI may evaluate whether a candidate is a strong, reasonable, or weak fit.

### 4. Resume tailoring

AI may rewrite and prioritize existing candidate information for a particular job.

---

# 8. Do NOT Use AI For

Do not use AI for:

- database operations
- job ID generation
- deduplication
- URL normalization
- deterministic filtering
- basic ranking
- sorting
- file naming
- LaTeX compilation
- PDF generation
- Google Sheets operations
- application status updates

If normal code can perform the task reliably, use normal code.

---

# 9. Candidate Data Rules

The master CV is the factual source of truth.

Never invent:

- skills
- experience
- projects
- employers
- job titles
- certifications
- degrees
- grades
- achievements
- metrics
- dates
- technologies
- responsibilities

AI may:

- rewrite
- reorder
- shorten
- emphasize
- summarize

but only using information supported by the stored candidate profile.

If information is missing, return `null` or leave it empty.

Never guess.

---

# 10. Master CV Workflow

The master CV is uploaded during initial setup.

Workflow:

```text
Master CV
    ↓
Extract text
    ↓
AI parser
    ↓
Structured candidate profile
    ↓
User review
    ↓
User correction
    ↓
Save to SQLite
```

The user should **not** need to re-enter personal information every time the application runs.

After the initial setup, the stored profile is reused automatically.

---

# 11. Candidate Preferences

Candidate preferences are separate from factual candidate information.

The profile answers:

> Who is the candidate?

Preferences answer:

> What jobs does the candidate currently want?

Examples:

- preferred roles
- preferred locations
- work mode
- experience level
- jobs per run
- preferred/dream companies

Preferences can change without requiring the master CV to be parsed again.

---

# 12. Job Discovery

Initial sources:

- Greenhouse
- Lever
- Ashby

Additional sources may be added later.

Each source must return jobs using the same normalized internal structure.

The rest of the application should not depend on source-specific response formats.

---

# 13. Job Identity

The preferred job identifier is:

```text
source:source_job_id
```

Examples:

```text
greenhouse:123456
lever:abc123
ashby:987654
```

If the source does not provide a stable job ID, use:

```text
source:normalized_application_url
```

The `unique_id` must be unique in SQLite.

Do not use:

- embeddings
- semantic similarity
- LLM duplicate detection
- fuzzy matching

for V1.

---

# 14. Duplicate Handling

For every discovered job:

```text
Generate unique_id
        ↓
Check SQLite
        ↓
Already exists?
   /          \
 YES          NO
  |            |
Skip          Save
```

Previously seen jobs must not appear as new jobs.

The database is persistent.

Do not delete historical jobs merely because they are no longer visible in the source.

---

# 15. Job History

Store:

- first seen date
- last seen date
- current status
- scores
- analysis
- generated resume
- Drive URL
- application timestamp

This creates a permanent personal job-search history.

---

# 16. Job Status

Use only:

```text
new
selected
applied
rejected
saved
```

Do not create a `seen` status.

A job's existence in SQLite already means it has been seen.

---

# 17. Job Filtering Philosophy

**Recall is more important than precision.**

Do not aggressively eliminate jobs.

Hard-filter only obvious mismatches.

Examples of valid hard filters:

- clearly wrong profession
- clearly incompatible experience requirement
- explicitly impossible location requirement
- expired/invalid posting
- obvious eligibility mismatch

Do NOT reject a job simply because one or more preferred skills are missing.

Example:

Candidate:

```text
Python
Java
SQL
Machine Learning
```

Job:

```text
Python
Java
SQL
Azure
C++
```

This job should continue through the pipeline.

The missing skills can affect ranking.

---

# 18. Deterministic Ranking

Perform deterministic ranking before AI analysis.

Suggested V1 weights:

```text
Role alignment       35%
Location alignment   25%
Experience alignment 20%
Employment type      10%
Skill overlap        10%
```

Total:

```text
100%
```

The deterministic score should be between:

```text
0 and 100
```

Do not let an AI model perform this entire step.

---

# 19. AI Candidate Pool

Do not send every discovered job to the AI.

The intended pattern is:

```text
Many discovered jobs
        ↓
Deduplication
        ↓
Hard filtering
        ↓
Deterministic ranking
        ↓
Smaller candidate pool
        ↓
AI analysis
```

This reduces:

- cost
- API usage
- latency
- unnecessary model calls

---

# 20. AI Job Analysis

The AI should return structured JSON.

Example:

```json
{
  "recommendation": "strong_match",
  "score": 92,
  "eligibility": true,
  "matching_requirements": [
    "Python",
    "SQL",
    "Machine Learning"
  ],
  "missing_preferred_skills": [
    "Azure"
  ],
  "missing_critical_requirements": [],
  "role_alignment": 95,
  "reason": "Strong alignment with the candidate's existing experience and skills."
}
```

The model must not invent candidate qualifications.

---

# 21. Final Ranking

Use both deterministic and AI scores.

V1:

```text
final_score =
    deterministic_score * 0.60
    +
    ai_score * 0.40
```

Sort descending.

Select the requested number of jobs.

Example:

```text
requested_jobs = 50
```

→ select top 50.

---

# 22. Resume Tailoring

Do NOT ask the AI to generate the entire LaTeX file.

Correct workflow:

```text
Candidate Profile
+
Job Description
+
AI Job Analysis
+
Resume Settings
        ↓
AI
        ↓
Structured Resume JSON
        ↓
Python
        ↓
Fixed LaTeX Template
        ↓
pdflatex
        ↓
PDF
```

The template controls the design.

AI controls the content.

---

# 23. Resume Tailoring Rules

AI may:

- rewrite existing bullets
- reorder projects
- prioritize relevant projects
- reorder skills
- tailor the summary
- emphasize relevant experience
- use job-description terminology when truthful
- remove low-relevance content if necessary

AI may not:

- invent experience
- invent projects
- invent metrics
- invent skills
- invent certifications
- invent employers
- invent dates
- claim unsupported expertise

---

# 24. LaTeX Rules

Use a fixed LaTeX template.

The AI should never control:

- margins
- font sizes
- spacing
- page layout
- section styling
- visual design

Python should populate the template.

Every inserted string must be escaped for LaTeX.

Characters such as:

```text
&
%
$
#
_
{
}
\
```

must be handled correctly.

---

# 25. PDF Generation

Generate:

```text
.tex
```

then compile with:

```text
pdflatex
```

Check the exit code.

If compilation fails:

1. Log the error.
2. Mark the resume as failed.
3. Continue processing other jobs.
4. Report the failure in the final run summary.

Never allow one bad resume to kill the entire run.

---

# 26. Overleaf Redirect

Successful LaTeX resumes should be accessible via a local Flask redirect route.

After generation:

- save the local Overleaf link
- associate it with the corresponding job
- expose it in the results page

---

# 27. Google Sheets

The spreadsheet should contain useful application information.

Suggested columns:

```text
Rank
Company
Position
Location
Employment Type
Deterministic Score
AI Score
Final Score
Matching Skills
Missing Skills
Why Match
Job URL
Resume URL
Status
Date Found
Date Applied
```

The Job URL must point to the official application page.

The Resume URL must point to the local Flask `/jobs/<id>/overleaf` route which auto-redirects to Overleaf.

---

# 28. Application Submission

Do NOT automatically submit applications in V1.

The application ends with:

```text
Job
+
Official application URL
+
Tailored resume
```

The user manually applies.

This avoids:

- authentication problems
- CAPTCHAs
- custom application forms
- legal declarations
- accidental false answers
- company-specific questions

---

# 29. Application Status

The user can manually update a job:

```text
Applied
Rejected
Saved
```

For example:

```text
POST /jobs/<id>/applied
```

should update the SQLite record.

The Google Sheet should also be updated.

---

# 30. Background Processing

A full run can take several minutes.

Do not keep the browser waiting on one long synchronous Flask request.

For V1, use a simple Python background thread/process.

Do NOT introduce:

- Celery
- Redis
- distributed queues

unless the project genuinely requires them later.

---

# 31. Progress Reporting

The frontend should display progress.

Example:

```text
Discovering jobs...
184 jobs discovered.

Checking job history...
83 duplicates.

Filtering...
142 candidates.

Ranking...
Top 100 selected for AI analysis.

AI analysis...
43 / 100

Generating resumes...
18 / 50
```

The frontend can poll:

```text
GET /run/status
```

---

# 32. Error Handling

External services can fail.

Potential failures include:

- ATS API errors
- invalid job responses
- blocked/unavailable pages
- AI rate limits
- AI timeouts
- malformed AI JSON
- LaTeX compilation failures
- Google API errors

The system must isolate failures.

One failed item must not kill the entire run.

---

# 33. AI Retry Strategy

If an AI request fails:

1. Retry a small number of times.
2. Respect rate limits.
3. If it continues failing, record the failure.
4. Continue with the next job.

Do not repeatedly retry indefinitely.

---

# 34. AI Output Validation

Never blindly trust model output.

After receiving AI output:

1. Parse JSON.
2. Validate required fields.
3. Validate field types.
4. Validate allowed enum values.
5. Reject malformed output.
6. Retry if appropriate.
7. Otherwise skip the affected job and continue.

---

# 35. Security

Never hard-code:

- AI API keys
- Google credentials
- OAuth tokens

Use environment variables and local credential files.

Do not commit:

```text
.env
*.db
credentials.json
token.json
uploads/
generated/
```

The master CV and generated resumes contain personal information and must not be committed to Git.

---

# 36. Project Structure

Prefer this initial structure:

```text
job-automator/
│
├── PROJECT_SPEC.md
├── AGENTS.md
│
├── app.py
├── database.py
├── jobs.py
├── ai.py
├── resume.py
├── google.py
│
├── sources/
│   ├── __init__.py
│   ├── greenhouse.py
│   ├── lever.py
│   └── ashby.py
│
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── setup.html
│   ├── profile_review.html
│   ├── resume_settings.html
│   └── results.html
│
├── static/
│   ├── style.css
│   └── script.js
│
├── latex/
│   └── resume_template.tex
│
├── uploads/
│
├── generated/
│   └── resumes/
│
├── data/
│   └── jobs.db
│
├── requirements.txt
├── .env
└── .gitignore
```

Do not split the project into more modules until the existing modules become genuinely difficult to manage.

---

# 37. Flask Routes

Keep routes simple.

Expected routes:

```text
GET  /
GET  /setup
POST /setup

GET  /profile
POST /profile

GET  /resume-settings
POST /resume-settings

POST /run
GET  /run/status

GET  /results

POST /jobs/<id>/applied
POST /jobs/<id>/rejected
POST /jobs/<id>/saved
```

Do not build a separate REST API framework.

---

# 38. Frontend Philosophy

The frontend is intentionally basic.

It needs:

- forms
- buttons
- progress
- tables
- links
- success messages
- error messages

Do not spend significant effort on:

- animations
- elaborate design systems
- responsive dashboards
- complex component architecture
- visual effects

The project should function like a simple internal tool.

---

# 39. Development Process

Do not implement the entire application in one giant pass.

Build incrementally.

Recommended phases:

```text
Phase 1
Project foundation

Phase 2
Master CV parsing

Phase 3
Job preferences

Phase 4
First job source

Phase 5
Additional job sources

Phase 6
Filtering and ranking

Phase 7
AI job analysis

Phase 8
Resume generation

Phase 9
Google Drive and Sheets

Phase 10
End-to-end workflow
```

After each phase:

1. Run the application.
2. Run relevant tests.
3. Check for errors.
4. Verify the feature manually.
5. Explain what changed.
6. Commit working code.
7. Only then move to the next phase.

---

# 40. Git Discipline

The project should use Git.

Make a commit after each meaningful working phase.

Example:

```text
feat: initialize Flask application
feat: add SQLite database
feat: add CV parser
feat: add profile review
feat: add Greenhouse discovery
feat: add job deduplication
feat: add job ranking
feat: add AI job analysis
feat: add LaTeX resume generation
feat: add Google Drive upload
feat: add Google Sheets integration
```

Do not create huge commits containing unrelated changes.

---

# 41. Dependency Discipline

Before adding a dependency, ask:

1. Is it genuinely necessary?
2. Can Python's standard library solve it?
3. Can an existing dependency solve it?
4. Does it materially simplify the project?

If not, do not add it.

---

# 42. Scope Discipline

Do not add features that are not part of V1.

Explicitly out of scope:

- automatic job applications
- LinkedIn scraping
- Indeed scraping
- embeddings
- vector databases
- agents
- multi-user support
- authentication
- cover letters
- interview tracking
- email automation
- salary prediction
- application automation
- complicated resume editors
- SaaS deployment

If you identify a potentially useful feature, mention it separately rather than implementing it automatically.

---

# 43. When Requirements Are Ambiguous

Do not invent a complex interpretation.

If a requirement materially affects architecture or behavior:

1. Explain the ambiguity.
2. Give the simplest reasonable options.
3. Ask the user to choose.

If the missing detail is minor, use a simple reasonable default and document it.

---

# 44. Code Quality

Code should be:

- readable
- straightforward
- reasonably modular
- easy for a student developer to understand
- easy to debug

Avoid:

- clever abstractions
- unnecessary design patterns
- excessive inheritance
- unnecessary classes
- over-engineering
- premature optimization

Prefer explicit code over magic.

---

# 45. Testing

Every important feature should have a basic verification method.

At minimum, test:

### Database

- initialization
- candidate save/load
- preference save/load
- job insertion
- duplicate prevention
- status updates

### Job sources

- parsing
- normalization
- malformed response handling

### AI

- JSON parsing
- invalid response handling
- retry behavior

### Resume

- LaTeX escaping
- template generation
- PDF compilation
- failed compilation handling

### Google

- Drive upload
- Sheet update

### End-to-end

- first run
- second run
- duplicate jobs excluded
- failed job does not terminate the run

---

# 46. First Development Task

When starting work on this repository:

**Do not immediately implement the application.**

First:

1. Read `PROJECT_SPEC.md`.
2. Read `AGENTS.md`.
3. Inspect the repository.
4. Inspect the local development environment.
5. Check Python version.
6. Check whether Flask is installed.
7. Check whether `pdflatex` is available.
8. Check whether Git is available.
9. Check whether Playwright can be installed if needed.
10. Identify missing dependencies.

Then provide:

1. Environment assessment.
2. Specification assessment.
3. Potential implementation risks.
4. Proposed project structure.
5. Phase-by-phase implementation plan.
6. Exact Phase 1 deliverables.
7. Commands required to run Phase 1.

**Do not implement Phase 1 until the user explicitly approves the plan.**

---

# 47. Important Behavioral Rule

Do not optimize for showing how much code you can generate.

Optimize for getting the project to a working state with the least unnecessary complexity.

When in doubt:

> Choose the simpler solution.

When AI is not necessary:

> Use deterministic code.

When an abstraction is not necessary:

> Do not create it.

When a feature is not required:

> Do not build it.

When the specification is unclear:

> Ask before making a major architectural decision.

---

# 48. Definition of Success

The V1 application is successful when the user can:

1. Upload a master CV once.
2. Review the extracted profile.
3. Save the profile.
4. Set job preferences once.
5. Click `FIND JOBS`.
6. Receive a fresh list of relevant jobs.
7. Avoid previously seen jobs through stable ID deduplication.
8. Receive ranked jobs.
9. Receive tailored LaTeX-generated PDF resumes.
10. Open the resumes in Overleaf.
11. Find the job/application links in Google Sheets.
12. Apply manually.
13. Mark jobs as Applied/Saved/Rejected.
14. Run the system again later.
15. Receive new jobs without duplicates.
16. Complete the process even if individual jobs or services fail.

---

# Final Rule

**Do not make this project more complicated than it needs to be.**

The desired architecture is:

```text
Flask
  +
Jinja
  +
Vanilla JavaScript
  +
SQLite
  +
Public Job Sources
  +
Hosted Open-Source AI
  +
LaTeX
  +
Google Sheets
```

Keep it simple, deterministic where possible, AI-assisted where useful, and easy for the user to understand and maintain.