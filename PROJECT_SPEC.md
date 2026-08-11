# Personal Job Automation System --- V1

## Ultra-Detailed Project Specification

**Project type:** Personal automation / portfolio project\
**Primary goal:** Find new, relevant jobs on demand, rank them against a
persistent candidate profile, generate a tailored LaTeX resume for each
selected job, generate Overleaf redirect links for the resumes, and organize the results
in Google Sheets.

------------------------------------------------------------------------

# 1. Project Overview

This project is a personal job-search automation system.

The user should **not** have to enter their personal details every time
the application runs.

Instead, the system has a one-time setup process:

1.  Upload a master CV/resume.
2.  Use AI to parse the CV.
3.  Convert the CV into a structured candidate profile.
4.  Let the user review and correct the extracted information.
5.  Save the verified profile in SQLite.
6.  Enter job-search preferences once.
7.  Save those preferences in SQLite.

After setup, the normal workflow is intentionally simple:

> Open application → choose how many jobs to find → click **Find Jobs**.

The application then:

1.  Loads the saved candidate profile.
2.  Loads the saved job preferences.
3.  Discovers jobs from permitted/public job sources.
4.  Normalizes the different source formats.
5.  Uses stable source job IDs for deduplication.
6.  Removes jobs already stored in the database.
7.  Performs conservative deterministic filtering.
8.  Performs deterministic ranking.
9.  Uses a hosted open-source AI model for deeper job/candidate
    evaluation.
10. Selects the best requested number of jobs.
11. Uses AI to tailor the resume content for each selected job.
12. Inserts the structured resume content into a fixed LaTeX template.
13. Generates Overleaf redirect links for the generated LaTeX code.
14. Adds the job, score, reasoning, application link, and Overleaf resume link to Google Sheets.
15. Shows a completion summary and any errors.

The system is deliberately **not** intended to be a SaaS product,
multi-user application, or autonomous application-submission bot.

------------------------------------------------------------------------

# 2. Core Design Philosophy

The project follows five principles.

## 2.1 Deterministic first, AI second

Use normal code wherever the problem can be solved reliably with normal
code.

Examples:

-   database storage
-   job ID deduplication
-   URL normalization
-   hard filtering
-   scoring
-   sorting
-   PDF generation
-   Google Drive upload
-   Google Sheets updates

Use AI where semantic judgment is genuinely useful:

-   parsing the master CV
-   understanding job descriptions
-   distinguishing important vs. optional requirements
-   evaluating ambiguous candidate/job fit
-   tailoring resume wording

The system should never use an LLM simply because an LLM can do
something.

------------------------------------------------------------------------

## 2.2 Recall is more important than precision

The system must avoid silently removing a potentially excellent
opportunity.

For example:

Candidate:

-   Python
-   Java
-   SQL
-   Machine Learning

Job:

-   Python
-   Java
-   SQL
-   Azure
-   C++

The system should **not** reject the job merely because Azure and C++
are missing.

Instead:

> Strong candidate match, but missing some preferred skills.

This is especially important for high-value companies and competitive
roles.

It is better to show the user some extra jobs than to hide one job they
would have loved.

------------------------------------------------------------------------

## 2.3 The master CV is the factual source of truth

The AI must never invent:

-   work experience
-   degrees
-   grades
-   certifications
-   projects
-   technologies
-   job titles
-   achievements
-   responsibilities
-   employment dates

The structured profile extracted from the master CV becomes the factual
source of truth.

AI may rewrite or reorder existing information for relevance, but it
must not fabricate qualifications.

------------------------------------------------------------------------

## 2.4 Job history is persistent

The application should never start from zero.

Every discovered job is stored in SQLite.

This allows the system to know:

-   whether a job has been seen before
-   whether the user applied
-   whether the user rejected it
-   whether it was saved
-   when it was first discovered
-   when it was last observed

The database therefore becomes a permanent personal job-search history.

------------------------------------------------------------------------

## 2.5 Keep V1 deliberately small

V1 should not include:

-   automatic application submission
-   LinkedIn scraping
-   Indeed scraping
-   multi-user accounts
-   authentication
-   vector databases
-   embeddings
-   LangChain
-   LangGraph
-   agents
-   PostgreSQL
-   Redis
-   Celery
-   Docker as a requirement
-   complex resume editors
-   automated interview tracking
-   email automation
-   cover-letter generation
-   salary prediction

These can be considered later only if a real need appears.

------------------------------------------------------------------------

# 3. Final Technology Stack

## Frontend

-   HTML
-   CSS
-   Jinja templates
-   Vanilla JavaScript

No React.

The UI is intentionally basic.

It should look like a functional internal tool rather than a polished
SaaS product.

------------------------------------------------------------------------

## Backend

-   Python
-   Flask

Flask is appropriate because the application is small, single-user, and
primarily a collection of forms, buttons, APIs, and background
processing.

------------------------------------------------------------------------

## Database

-   SQLite
-   Python's built-in `sqlite3`

No ORM.

No SQLAlchemy.

No Alembic.

The database is small enough that direct SQL is preferable for
simplicity.

------------------------------------------------------------------------

## Job discovery

Primary sources:

-   public ATS job-posting APIs
-   permitted public job feeds
-   direct public career pages when necessary

Initial ATS integrations:

-   Greenhouse
-   Lever
-   Ashby

Potential future sources:

-   SmartRecruiters
-   Workday
-   other public ATS systems
-   public company career pages

Do not build a separate scraper for every company unless a source
genuinely requires it.

------------------------------------------------------------------------

## HTTP

Use Python HTTP requests for API calls and simple pages.

A minimal choice is:

-   `requests`

Do not introduce an async HTTP architecture unless it becomes necessary.

------------------------------------------------------------------------

## HTML parsing

-   BeautifulSoup

Use it for ordinary static HTML.

------------------------------------------------------------------------

## Browser automation

-   Playwright

Use Playwright only when a job source genuinely requires
JavaScript-rendered content.

Do not make Playwright the default for every source.

------------------------------------------------------------------------

## AI

Use a **hosted free/open-source model API**.

The model does not run locally because the user's laptop is not suitable
for local LLM inference.

Candidate model families may include:

-   Qwen
-   Llama
-   Gemma
-   Mistral

The exact provider is intentionally abstracted behind a small Python AI
module so the provider can be replaced later.

The application should not depend deeply on provider-specific behavior.

------------------------------------------------------------------------

## Resume generation

-   LaTeX
-   `pdflatex`

The AI generates structured resume content.

The AI does **not** control the visual layout.

The fixed LaTeX template controls:

-   typography
-   spacing
-   margins
-   section order
-   styling
-   hyperlinks
-   page structure

------------------------------------------------------------------------

## Google integrations

-   Google Drive API
-   Google Sheets API

Google Drive stores generated resumes.

Google Sheets acts as the application/job dashboard.

------------------------------------------------------------------------

# 4. High-Level Architecture

``` text
                         USER
                          |
                          v
              +-----------------------+
              | Flask + Jinja UI      |
              | HTML/CSS/JS           |
              +-----------+-----------+
                          |
                          v
              +-----------------------+
              | Flask Backend         |
              +-----------+-----------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
      SQLite         Job Discovery      AI API
          |               |                |
          |        +------+------+         |
          |        |      |      |         |
          |     Green-  Lever  Ashby       |
          |     house                       |
          |               |                |
          +---------------+----------------+
                          |
                          v
                Job Normalization
                          |
                          v
                 ID Deduplication
                          |
                          v
                Conservative Filter
                          |
                          v
              Deterministic Ranking
                          |
                          v
                  AI Evaluation
                          |
                          v
                     Top N Jobs
                          |
                          v
                AI Resume Tailoring
                          |
                          v
                   Resume JSON
                          |
                          v
                  LaTeX Template
                          |
                          v
                      pdflatex
                          |
                    +-----+-----+
                    |           |
                    v           v
               Google Drive  Google Sheets
```

------------------------------------------------------------------------

# 5. User Experience

The application has two phases.

## Phase A --- One-Time Setup

### Step A1 --- Upload Master CV

The user uploads their current master CV.

Supported initial format:

-   PDF

Potential future support:

-   DOCX
-   TXT

The system extracts text from the PDF.

If extraction fails, show an error instead of silently producing an
incomplete profile.

------------------------------------------------------------------------

### Step A2 --- AI CV Parsing

The extracted CV text is sent to the hosted AI model.

The model returns structured candidate data.

Example:

``` json
{
  "name": "Candidate Name",
  "email": "candidate@example.com",
  "phone": "+91...",
  "links": {
    "linkedin": "...",
    "github": "..."
  },
  "education": [
    {
      "degree": "B.Tech Computer Science",
      "institution": "Example University",
      "graduation_year": 2027,
      "cgpa": "8.3"
    }
  ],
  "experience": [
    {
      "company": "Example Company",
      "role": "Python Developer Intern",
      "start_date": "2026-06",
      "end_date": null,
      "bullets": [
        "..."
      ]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "description": "...",
      "technologies": [
        "Python",
        "Flask"
      ],
      "bullets": [
        "..."
      ]
    }
  ],
  "skills": [
    "Python",
    "Java",
    "SQL"
  ],
  "certifications": [
    "..."
  ],
  "achievements": [
    "..."
  ]
}
```

------------------------------------------------------------------------

### Step A3 --- Profile Review

The user sees the extracted information.

The user can:

-   edit fields
-   add missing information
-   remove incorrect information
-   correct AI extraction errors

Only after clicking:

> **Save Profile**

does the information become the stored candidate profile.

The reviewed profile becomes the factual source of truth.

------------------------------------------------------------------------

### Step A4 --- Job Preferences

The user enters preferences once.

Fields:

-   preferred roles
-   preferred locations
-   work mode
-   experience level
-   number of jobs per run
-   dream/preferred companies

Example:

``` text
Preferred roles:
AI/ML Engineer
Software Engineer
Python Developer

Locations:
Hyderabad
Bangalore
Remote

Work mode:
Remote
Hybrid
On-site

Experience:
Internship
Entry Level

Jobs per run:
50

Dream companies:
Google
Microsoft
NVIDIA
Amazon
```

These preferences are saved to SQLite.

------------------------------------------------------------------------

# 6. Normal Daily Workflow

The normal interface should require almost no input.

Example:

``` text
PERSONAL JOB AUTOMATOR

Profile: ✓ Loaded
Master Resume: ✓ Loaded
Preferences: ✓ Loaded

Jobs to find: [ 50 ]

[ FIND JOBS ]

Last Run:
50 jobs found
47 resumes generated
3 errors
```

The user clicks:

> **FIND JOBS**

Everything else happens automatically.

------------------------------------------------------------------------

# 7. Candidate Data Model

Because there is only one user, there is no need for a user-account
system.

## Table: `candidate`

Suggested columns:

``` sql
CREATE TABLE candidate (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    profile_json TEXT NOT NULL,
    master_resume_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Why store most data as JSON?

The candidate profile contains nested structures such as:

-   education
-   experiences
-   projects
-   certifications
-   skills

For a single-user personal project, JSON stored in SQLite is simpler
than creating many normalized tables.

The application can load:

``` python
profile = json.loads(row["profile_json"])
```

and work with a normal Python dictionary.

------------------------------------------------------------------------

# 8. Job Preferences Data Model

## Table: `preferences`

``` sql
CREATE TABLE preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    preferences_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Example JSON:

``` json
{
  "preferred_roles": [
    "AI/ML Engineer",
    "Software Engineer",
    "Python Developer"
  ],
  "locations": [
    "Hyderabad",
    "Bangalore",
    "Remote"
  ],
  "work_modes": [
    "remote",
    "hybrid"
  ],
  "experience_levels": [
    "internship",
    "entry_level"
  ],
  "jobs_per_run": 50,
  "dream_companies": [
    "Google",
    "Microsoft",
    "NVIDIA",
    "Amazon"
  ]
}
```

------------------------------------------------------------------------

# 9. Resume Settings Data Model

## Table: `resume_settings`

``` sql
CREATE TABLE resume_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    template TEXT NOT NULL,
    section_order TEXT NOT NULL,
    resume_length INTEGER DEFAULT 1,
    instructions TEXT,
    updated_at TEXT NOT NULL
);
```

Example:

``` json
{
  "template": "ats",
  "section_order": [
    "education",
    "experience",
    "projects",
    "skills",
    "certifications"
  ],
  "resume_length": 1
}
```

The section order can be stored as JSON text.

------------------------------------------------------------------------

# 10. Job Data Model

This is the most important table.

## Table: `jobs`

``` sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

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
    resume_pdf_path TEXT,

    drive_url TEXT,

    applied_at TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

------------------------------------------------------------------------

# 11. Job Identity

The key field is:

``` text
unique_id
```

The preferred format is:

``` text
source:source_job_id
```

Examples:

``` text
greenhouse:123456
lever:abc123
ashby:987654
```

This field must be unique.

SQLite should enforce this with:

``` sql
UNIQUE(unique_id)
```

------------------------------------------------------------------------

# 12. If a Source Does Not Provide a Job ID

Use:

``` text
source:normalized_application_url
```

Example:

``` text
lever:https://jobs.lever.co/company/abc123
```

Do not implement complicated fuzzy identity logic in V1.

The first fallback should be the normalized URL.

------------------------------------------------------------------------

# 13. Job Status

Use a small status vocabulary:

``` text
new
selected
applied
rejected
saved
```

Meaning:

### `new`

The job exists in the database but has not been selected for the current
workflow.

### `selected`

The job was selected as one of the final recommendations.

### `applied`

The user manually applied.

### `rejected`

The user explicitly decided not to apply.

### `saved`

The user wants to keep the job for later.

Do not create a `seen` status.

Existence in the database already tells us whether a job has been seen.

------------------------------------------------------------------------

# 14. Run Data Model

## Table: `runs`

``` sql
CREATE TABLE runs (
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
```

Possible statuses:

``` text
running
completed
failed
partial
```

------------------------------------------------------------------------

# 15. Why Run History Exists

The run table is mainly for debugging and visibility.

Example:

``` text
Run #8

Started: 2026-08-11 10:00
Completed: 2026-08-11 10:05

Requested: 50
Discovered: 742
Duplicates: 183
Invalid: 41
Filtered: 210
AI analyzed: 100
Selected: 50
Resume success: 48
Resume errors: 2

Status: partial
```

This makes failures understandable without digging through logs.

------------------------------------------------------------------------

# 16. Database Initialization

V1 should have a simple initialization function.

Conceptually:

``` text
database.py
    |
    +-- get_connection()
    |
    +-- init_db()
    |
    +-- save_candidate()
    |
    +-- get_candidate()
    |
    +-- save_preferences()
    |
    +-- get_preferences()
    |
    +-- save_job()
    |
    +-- job_exists()
    |
    +-- get_new_jobs()
    |
    +-- update_job_status()
    |
    +-- create_run()
    |
    +-- update_run()
```

No migration framework.

If the schema changes during early development, manually delete/recreate
the local SQLite database while the project is still in V1 development.

------------------------------------------------------------------------

# 17. Job Source Architecture

Each source should return the same normalized structure.

Example:

``` python
{
    "source": "greenhouse",
    "source_job_id": "123456",
    "unique_id": "greenhouse:123456",
    "company": "Example Company",
    "title": "Software Engineer Intern",
    "location": "Hyderabad, India",
    "employment_type": "Internship",
    "description": "...",
    "application_url": "...",
    "posted_date": "2026-08-10"
}
```

The rest of the application should not care whether the job came from:

-   Greenhouse
-   Lever
-   Ashby
-   a career page

This is important for maintainability.

------------------------------------------------------------------------

# 18. Source Modules

Initial structure:

``` text
sources/
    greenhouse.py
    lever.py
    ashby.py
```

Each source module should have a small interface such as:

``` python
def discover_jobs(search_config):
    ...
    return normalized_jobs
```

Do not let source-specific data structures leak into the rest of the
application.

------------------------------------------------------------------------

# 19. Job Discovery Strategy

The system should not try to scrape every company individually.

The discovery strategy is:

1.  Query public ATS job sources.
2.  Discover relevant job postings.
3.  Normalize the results.
4.  Store new jobs.
5.  Optionally supplement gaps with permitted public career-page
    sources.
6.  Stop once enough valid candidate jobs have been collected or
    discovery sources are exhausted.

The system should target jobs rather than blindly targeting companies.

------------------------------------------------------------------------

# 20. Target Number

If the user requests:

``` text
50 jobs
```

the system should attempt to return the top 50 qualifying jobs.

It should not blindly scrape exactly 50 postings.

There may be:

-   duplicates
-   expired jobs
-   irrelevant jobs
-   invalid pages
-   jobs already seen

Therefore the discovery pool must be larger than the final output.

------------------------------------------------------------------------

# 21. Discovery Stopping Conditions

The process stops when one of these happens:

## Condition A --- Target reached

Example:

``` text
50 final qualifying jobs
```

Stop.

## Condition B --- Sources exhausted

Example:

``` text
Only 37 qualifying new jobs exist
```

Stop and report:

> Found 37 matching new jobs.

## Condition C --- Safety limit reached

A configurable V1 safety ceiling should prevent infinite discovery.

Example:

``` text
Maximum candidate jobs examined: 1000
```

If the target has not been reached:

> Discovery limit reached. 43 qualifying jobs were found.

------------------------------------------------------------------------

# 22. Deduplication Workflow

For every discovered job:

``` text
Generate unique_id
        |
        v
Does unique_id exist in SQLite?
        |
     +--+--+
     |     |
    YES    NO
     |     |
   skip   save
```

No AI.

No embeddings.

No fuzzy matching.

No semantic similarity.

This is intentionally simple.

------------------------------------------------------------------------

# 23. Historical Job Handling

Suppose the same job is discovered tomorrow.

The system should:

-   detect the existing `unique_id`
-   update `last_seen`
-   not create a new record
-   not include it as a new job

Example:

``` text
Job:
greenhouse:123456

first_seen:
2026-08-10

last_seen:
2026-08-11

status:
applied
```

The job remains in the database forever unless manually deleted.

------------------------------------------------------------------------

# 24. Conservative Hard Filtering

Hard filtering should remove only obvious mismatches.

Examples:

### Reject

``` text
Candidate wants internships.
Job requires 7+ years of experience.
```

### Reject

``` text
Job is for a completely unrelated profession.
```

### Reject

``` text
Job is explicitly restricted to a location the candidate cannot work in.
```

### Reject

``` text
Job posting is invalid/expired and no longer accepts applications.
```

------------------------------------------------------------------------

# 25. Do NOT Hard Filter Missing Skills

Example:

Candidate:

``` text
Python
Java
SQL
Machine Learning
```

Job:

``` text
Python
Java
SQL
Azure
C++
```

Do not reject.

Instead:

``` text
Matching:
Python
Java
SQL

Missing:
Azure
C++
```

The job proceeds to ranking and AI analysis.

------------------------------------------------------------------------

# 26. Deterministic Ranking

Before using AI, score jobs using simple rules.

Suggested V1 weights:

``` text
Role alignment       35%
Location alignment   25%
Experience alignment 20%
Employment type      10%
Skill overlap        10%
```

Total:

``` text
100%
```

The deterministic score is between:

``` text
0–100
```

------------------------------------------------------------------------

# 27. Dream Company Preference

Dream companies should influence ranking, but should not override
eligibility.

Example:

``` text
Google
Microsoft
NVIDIA
Amazon
Meta
```

can receive a modest opportunity boost.

However:

``` text
Google
Senior Engineer
8 years experience
```

should still be rejected if it clearly violates the candidate's
eligibility.

Dream-company preference is a ranking factor, not a permission to ignore
hard requirements.

------------------------------------------------------------------------

# 28. AI Deep Analysis

Do not send every discovered job to the AI.

Example pipeline:

``` text
700 discovered
      |
      v
deduplicate
      |
      v
500 new
      |
      v
hard filter
      |
      v
300
      |
      v
deterministic ranking
      |
      v
top 100
      |
      v
AI analysis
```

The exact numbers are not fixed.

The principle is:

> Cheap deterministic processing first; expensive semantic processing
> second.

------------------------------------------------------------------------

# 29. AI Job Analysis Output

The AI should return structured JSON.

Example:

``` json
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
  "reason": "The role closely matches the candidate's Python and machine-learning background."
}
```

Allowed recommendation values:

``` text
strong_match
good_match
consider
stretch
reject
```

The AI should be instructed to avoid rejecting a candidate solely
because a preferred skill is missing.

------------------------------------------------------------------------

# 30. Final Job Score

For V1:

``` text
final_score =
    deterministic_score * 0.60
    +
    ai_score * 0.40
```

This keeps deterministic ranking dominant.

The AI adds semantic judgment without becoming the entire ranking
system.

------------------------------------------------------------------------

# 31. Selecting the Final Jobs

After AI analysis:

``` text
Sort by final_score descending
```

Take:

``` text
top N
```

where:

``` text
N = user requested jobs
```

For example:

``` text
requested_jobs = 50
```

→ select top 50.

------------------------------------------------------------------------

# 32. Resume Tailoring Architecture

The master resume should not be regenerated as raw LaTeX by the AI.

Instead:

``` text
Master Profile
+
Job Description
+
AI Job Analysis
+
Resume Preferences
        |
        v
      AI
        |
        v
Structured Resume JSON
        |
        v
LaTeX Template
        |
        v
pdflatex
        |
        v
PDF
```

------------------------------------------------------------------------

# 33. Resume JSON

Example:

``` json
{
  "header": {
    "name": "Candidate Name",
    "email": "candidate@example.com",
    "phone": "+91...",
    "links": {
      "linkedin": "...",
      "github": "..."
    }
  },
  "summary": "...",
  "education": [
    {
      "degree": "B.Tech Computer Science",
      "institution": "Example University",
      "year": "2027"
    }
  ],
  "experience": [
    {
      "company": "Example Company",
      "role": "Python Developer Intern",
      "bullets": [
        "...",
        "..."
      ]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "bullets": [
        "...",
        "..."
      ]
    }
  ],
  "skills": {
    "languages": [],
    "frameworks": [],
    "tools": []
  }
}
```

------------------------------------------------------------------------

# 34. Resume Tailoring Rules

The AI may:

-   reorder existing projects
-   prioritize relevant skills
-   rewrite existing bullets
-   emphasize relevant technologies
-   tailor the professional summary
-   use terminology from the job description when truthful
-   remove low-relevance content if necessary
-   preserve factual information

The AI may not:

-   invent skills
-   invent experience
-   invent metrics
-   invent employers
-   invent projects
-   invent certifications
-   claim proficiency in a technology that is not supported by the
    master profile
-   fabricate achievements

------------------------------------------------------------------------

# 35. LaTeX Generation

The project contains a fixed template:

``` text
latex/
    resume_template.tex
```

Python replaces placeholders with generated content.

Example:

``` latex
\section{Experience}

\resumeSubheading
  {{{company}}}
  {{{location}}}
  { {{role}} }
  { {{dates}} }

\resumeItemListStart
  \resumeItem{{{bullet_1}}}
  \resumeItem{{{bullet_2}}}
\resumeItemListEnd
```

The AI does not control layout.

------------------------------------------------------------------------

# 36. LaTeX Escaping

All AI-generated text must be escaped before being inserted into LaTeX.

Characters requiring special handling include:

``` text
&
%
$
#
_
{
}
\
```

The application should have a dedicated function:

``` text
latex_escape(text)
```

This prevents valid resume content such as:

``` text
C++
100%
A&B
```

from breaking compilation.

------------------------------------------------------------------------

# 37. PDF Generation

For every selected job:

``` text
Generate .tex
     |
     v
Run pdflatex
     |
     v
Check exit code
     |
     v
PDF created?
```

If compilation fails:

1.  Log the error.
2.  Mark the resume generation as failed.
3.  Continue processing other jobs.
4.  Report the failure at the end.

One bad resume must not terminate the entire run.

------------------------------------------------------------------------

# 38. PDF Validation

Basic validation should check:

-   PDF exists
-   file size is greater than zero
-   LaTeX exited successfully
-   PDF contains text
-   expected sections are present
-   page count is within configured limit

Optional V1 check:

-   one-page resume requirement

Use a lightweight PDF parsing library only if needed.

------------------------------------------------------------------------

# 39. Resume File Naming

Use deterministic filenames.

Example:

``` text
Microsoft_AI_Intern.pdf
Google_Software_Engineer_Intern.pdf
NVIDIA_Machine_Learning_Intern.pdf
```

Sanitize:

-   `/`
-   `\`
-   `:`
-   `*`
-   `?`
-   quotes
-   `<`
-   `>`
-   `|`
-   excessively long titles

Prevent filename collisions by including the job ID when necessary.

Example:

``` text
Microsoft_AI_Intern_greenhouse_123456.pdf
```

------------------------------------------------------------------------

# 40. Overleaf Redirect Workflow

For every successful LaTeX resume generation:

``` text
LaTeX Source Code
 |
 v
Saved to Local File / DB
 |
 v
Generate Local Flask Redirect Link (http://localhost:5000/jobs/<id>/overleaf)
 |
 v
Save link in jobs table as resume URL
```

When clicked, the link opens a Flask route that auto-submits a POST request to Overleaf's API with the LaTeX content.

------------------------------------------------------------------------

# 41. Google Sheets Workflow

The system maintains one primary spreadsheet.

Suggested columns:

``` text
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

Example:

  -------------------------------------------------------------------------------------
        Rank Company     Position        Score Location    Resume   Apply    Status
  ---------- ----------- ---------- ---------- ----------- -------- -------- ----------
           1 Microsoft   AI Intern          94 Hyderabad   PDF      Apply    Selected

           2 Google      SWE Intern         92 Bangalore   PDF      Apply    Selected

           3 NVIDIA      ML Intern          90 Bangalore   PDF      Apply    Selected
  -------------------------------------------------------------------------------------

The application URL should point directly to the official application
page.

The resume URL should point to the local Flask `/jobs/<id>/overleaf` route which auto-redirects to Overleaf.

------------------------------------------------------------------------

# 42. Application Submission

V1 does **not** automatically submit applications.

The system ends at:

> Here is the job + tailored resume + official application link.

The user clicks Apply manually.

This avoids dealing with:

-   login requirements
-   CAPTCHAs
-   custom forms
-   legal declarations
-   authorization questions
-   company-specific application questions
-   accidental false answers

The user remains responsible for final submission.

------------------------------------------------------------------------

# 43. Updating Application Status

After manually applying, the user can click:

``` text
[ Mark Applied ]
```

The backend updates:

``` text
status = applied
applied_at = current timestamp
```

The Google Sheet is updated too.

------------------------------------------------------------------------

# 44. Next-Day Workflow

Suppose Day 1 produces:

``` text
50 selected
30 applied
10 saved
10 ignored
```

Day 2 discovers 700 jobs.

For every job:

``` text
unique_id exists?
```

If yes:

``` text
skip
```

If no:

``` text
save
```

Therefore the next run naturally prioritizes new jobs.

No AI duplicate detection is required.

------------------------------------------------------------------------

# 45. Existing Job Status Logic

V1 behavior:

### Previously applied

Do not show again.

### Previously rejected

Do not show again.

### Previously saved

Do not automatically show as a new job, but keep it accessible.

### Previously selected but no action taken

Treat as already seen and do not include as a new job.

This keeps the daily list genuinely fresh.

------------------------------------------------------------------------

# 46. Run Progress

The frontend should show progress.

Example:

``` text
Finding jobs...

Source: Greenhouse
Discovered: 184

Source: Lever
Discovered: 96

Source: Ashby
Discovered: 72

Checking history...
Previously seen: 83

Filtering...
Valid candidates: 142

Ranking...
Top candidates: 100

AI analysis...
43 / 100

Generating resumes...
18 / 50
```

The user should always know that the application is still working.

------------------------------------------------------------------------

# 47. Background Processing

The job run may take several minutes.

The Flask request should not remain blocked for the entire operation.

For V1, a simple Python background thread is sufficient.

Conceptually:

``` text
POST /run
    |
    +--> start background task
    |
    +--> return immediately
```

Frontend periodically requests:

``` text
GET /run/status
```

and updates the UI.

No Celery, Redis, or distributed queue is necessary for a single-user
project.

------------------------------------------------------------------------

# 48. Error Handling

Every external operation can fail.

Potential failures:

-   ATS API unavailable
-   career page unavailable
-   malformed job response
-   AI rate limit
-   AI timeout
-   invalid AI JSON
-   LaTeX compilation failure
-   Google authentication failure
-   Google Drive upload failure
-   Google Sheets update failure

The system should isolate failures.

Example:

``` text
Job A
  ↓
AI failure
  ↓
log error
  ↓
continue

Job B
  ↓
success
```

At the end:

``` text
Run completed with 3 errors.

Successful jobs: 47
Failed jobs: 3

[VIEW ERRORS]
```

------------------------------------------------------------------------

# 49. AI Failure Recovery

If an AI API call fails:

1.  Retry a small number of times.
2.  Respect rate limits.
3.  If it still fails, log the job.
4.  Continue processing other jobs.
5.  Do not restart the entire run.

A failed AI call should never erase successful work.

------------------------------------------------------------------------

# 50. AI JSON Validation

Never blindly trust the model output.

After receiving JSON:

1.  Parse JSON.
2.  Verify required fields.
3.  Verify field types.
4.  Reject malformed output.
5.  Retry or skip.

Example:

``` text
AI response
    |
    v
JSON parse
    |
  valid?
  /    \
yes     no
 |       |
continue retry
```

------------------------------------------------------------------------

# 51. Security

Even though this is a local personal application:

-   never hard-code Google credentials
-   never hard-code AI API keys
-   use environment variables
-   add `.env` to `.gitignore`
-   do not commit OAuth tokens
-   do not commit the personal master CV
-   do not commit generated resumes
-   do not commit `jobs.db` if it contains personal information

Suggested `.gitignore`:

``` text
.env
*.db
credentials.json
token.json
generated/
uploads/
__pycache__/
*.pyc
```

------------------------------------------------------------------------

# 52. Suggested Project Structure

Keep it simple.

``` text
job-automator/
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
├── .gitignore
└── README.md
```

Do not split files further until there is a real reason.

------------------------------------------------------------------------

# 53. Flask Routes

Minimal V1 routes:

``` text
GET  /
```

Dashboard.

``` text
GET  /setup
POST /setup
```

Initial master CV and preferences setup.

``` text
GET  /profile
POST /profile
```

Review/edit stored candidate profile.

``` text
GET  /resume-settings
POST /resume-settings
```

Resume configuration.

``` text
POST /run
```

Start a job-search run.

``` text
GET /run/status
```

Return current run progress.

``` text
GET /results
```

Show the latest selected jobs.

``` text
POST /jobs/<id>/applied
```

Mark a job as applied.

``` text
POST /jobs/<id>/rejected
```

Mark a job as rejected.

``` text
POST /jobs/<id>/saved
```

Mark a job as saved.

------------------------------------------------------------------------

# 54. Frontend Design

The frontend is deliberately minimal.

## Dashboard

``` text
PERSONAL JOB AUTOMATOR

Profile:
✓ Loaded

Master Resume:
✓ Loaded

Preferences:
✓ Loaded

Jobs:
[ 50 ]

[ FIND JOBS ]

Last Run:
Aug 10, 2026
50 jobs found
48 resumes generated
2 errors
```

------------------------------------------------------------------------

## Setup

``` text
MASTER CV

[ Choose PDF ]

[ PARSE CV ]
```

After parsing:

``` text
EXTRACTED PROFILE

Name: ...
Email: ...
Education: ...
Experience: ...
Skills: ...
Projects: ...

[ EDIT ]

[ SAVE PROFILE ]
```

Then:

``` text
JOB PREFERENCES

Preferred Roles:
[ ... ]

Locations:
[ ... ]

Work Mode:
[ ... ]

Experience:
[ ... ]

Jobs Per Run:
[ 50 ]

Dream Companies:
[ ... ]

[ SAVE PREFERENCES ]
```

------------------------------------------------------------------------

## Results

Simple table.

``` text
Rank | Company | Role | Score | Resume | Apply | Status
```

No fancy cards or animations are required.

------------------------------------------------------------------------

# 55. JavaScript Responsibilities

Keep JavaScript small.

Use it for:

-   starting runs
-   polling progress
-   updating progress text
-   showing success/error popups
-   confirming status changes
-   basic form behavior
-   opening links

Do not build a large frontend application.

------------------------------------------------------------------------

# 56. Suggested AI Module Design

`ai.py` should hide the AI provider.

Possible functions:

``` python
parse_resume(text)
analyze_job(candidate, job)
tailor_resume(candidate, job, analysis, settings)
```

The rest of the application should not know how the API works.

For example:

``` python
profile = ai.parse_resume(cv_text)
analysis = ai.analyze_job(profile, job)
resume = ai.tailor_resume(profile, job, analysis, settings)
```

If the AI provider changes, only `ai.py` should need significant
modification.

------------------------------------------------------------------------

# 57. AI Prompt Design Principles

Prompts should:

-   explicitly request JSON
-   define the schema
-   tell the model not to invent information
-   distinguish required vs preferred skills
-   emphasize factual accuracy
-   give clear scoring criteria
-   avoid vague instructions

The AI should be treated as a structured reasoning component, not an
autonomous agent.

------------------------------------------------------------------------

# 58. Master Resume Parsing Rules

The parser should extract information only from the uploaded CV.

If information is missing:

``` json
{
  "phone": null
}
```

rather than guessing.

If a value is ambiguous:

``` json
{
  "cgpa": null
}
```

and let the user correct it.

------------------------------------------------------------------------

# 59. Job Description Parsing Rules

The AI should distinguish:

### Hard/critical requirements

Examples:

-   degree requirement
-   graduation requirement
-   legal work authorization
-   explicit years of experience
-   location restrictions

### Core skills

Examples:

-   Python
-   Java
-   SQL
-   machine learning

### Preferred skills

Examples:

-   Azure
-   Docker
-   AWS
-   Kubernetes

### Nice-to-have

Examples:

-   open-source contributions
-   specific domain knowledge

Missing preferred/nice-to-have skills should not automatically
disqualify the candidate.

------------------------------------------------------------------------

# 60. What the System Should NOT Do

The system should not:

-   fabricate experience
-   apply automatically
-   bypass CAPTCHAs
-   bypass login restrictions
-   scrape private data
-   impersonate the user
-   submit false application information
-   aggressively hammer websites
-   repeatedly request the same job source unnecessarily

The project should use publicly available/permitted job data.

------------------------------------------------------------------------

# 61. V1 Success Criteria

V1 is successful if the following works end-to-end:

### Setup

-   Upload master CV.
-   AI parses it.
-   User reviews it.
-   Profile is stored.
-   Preferences are stored.

### Job discovery

-   Find jobs from at least three supported source types.
-   Normalize them.
-   Assign stable IDs.
-   Prevent duplicate database records.

### Ranking

-   Remove only obvious mismatches.
-   Rank remaining jobs deterministically.
-   AI analyzes the strongest candidates.
-   Produce a final ranked list.

### Resume

-   Generate tailored resume content.
-   Insert into LaTeX.
-   Compile successfully.
-   Produce a valid PDF.

### Storage

-   Upload PDF to Google Drive.
-   Add job and resume links to Google Sheets.

### Repeatability

-   Run again tomorrow.
-   Previously stored job IDs are excluded.
-   New jobs are returned.

### Reliability

-   One broken job does not kill the run.
-   One failed AI call does not kill the run.
-   One failed PDF does not kill the run.
-   Final run summary reports successes and failures.

------------------------------------------------------------------------

# 62. Example Complete Run

User has:

``` text
Jobs requested = 50
```

System starts:

``` text
Run #12 started.
```

### Discovery

``` text
Greenhouse: 310
Lever: 210
Ashby: 160

Total discovered: 680
```

### Deduplication

``` text
Previously seen: 173
New jobs: 507
```

### Validation

``` text
Invalid/expired: 38
Remaining: 469
```

### Hard filtering

``` text
Obvious mismatches: 142
Remaining: 327
```

### Deterministic ranking

``` text
Top candidates: 100
```

### AI evaluation

``` text
100 analyzed
```

### Final selection

``` text
Top 50 selected
```

### Resume generation

``` text
50 resume jobs
48 PDFs successfully generated
2 failed
```

### Google Drive

``` text
48 PDFs uploaded
```

### Google Sheets

``` text
50 jobs recorded
48 resume links available
```

Final UI:

``` text
RUN COMPLETE

Requested: 50
Selected: 50
Resumes: 48
Errors: 2

[ VIEW RESULTS ]
```

------------------------------------------------------------------------

# 63. Future Improvements --- Explicitly Not V1

Only add these after V1 is stable.

## Possible V2

-   more ATS sources
-   better URL normalization
-   repost detection
-   fuzzy duplicate detection
-   embeddings
-   more resume templates
-   cover letters
-   automatic job alerts
-   application deadline tracking

## Possible V3

-   application form assistance
-   browser-assisted application filling
-   interview tracking
-   email integration
-   application analytics
-   personal job-search statistics

None of these should affect the V1 architecture.

------------------------------------------------------------------------

# 64. Final V1 Architecture

The final system is intentionally simple:

``` text
                    MASTER CV
                        |
                        v
                   AI PARSER
                        |
                        v
               VERIFIED PROFILE
                        |
                        +------------------+
                        |                  |
                        v                  v
                JOB PREFERENCES      RESUME SETTINGS
                        |                  |
                        +---------+--------+
                                  |
                                  v
                         [ FIND JOBS ]
                                  |
                                  v
                         JOB DISCOVERY
                                  |
                         +--------+--------+
                         |        |        |
                         v        v        v
                    Greenhouse Lever    Ashby
                         |        |        |
                         +--------+--------+
                                  |
                                  v
                           NORMALIZE JOBS
                                  |
                                  v
                         STABLE JOB ID
                                  |
                                  v
                         SQLITE HISTORY
                                  |
                                  v
                       CONSERVATIVE FILTER
                                  |
                                  v
                    DETERMINISTIC RANKING
                                  |
                                  v
                         TOP CANDIDATES
                                  |
                                  v
                         HOSTED OPEN-SOURCE AI
                                  |
                                  v
                        FINAL TOP 50 JOBS
                                  |
                                  v
                         AI RESUME TAILORING
                                  |
                                  v
                            RESUME JSON
                                  |
                                  v
                           LATEX TEMPLATE
                                  |
                                  v
                             PDF OUTPUT
                                  |
                         +--------+--------+
                         |                 |
                         v                 v
                    GOOGLE DRIVE      GOOGLE SHEETS
```

------------------------------------------------------------------------

# 65. The Most Important Architectural Rule

The entire project can be summarized as:

> **Use the master CV as the factual source of truth, use deterministic
> code for data management and filtering, use AI only for semantic
> interpretation and rewriting, and use LaTeX/code for deterministic
> document generation.**

That keeps the system:

-   cheap
-   understandable
-   debuggable
-   resistant to hallucinations
-   easy to modify
-   suitable for a low-powered laptop
-   appropriate for a single-user personal project

------------------------------------------------------------------------

# 66. V1 Build Order

Do not build everything simultaneously.

Build in this order:

### Phase 1 --- Foundation

1.  Flask application
2.  SQLite database
3.  Database initialization
4.  Basic Jinja UI
5.  Setup page

### Phase 2 --- Master CV

6.  PDF upload
7.  PDF text extraction
8.  AI CV parser
9.  Profile review page
10. Save verified profile

### Phase 3 --- Preferences

11. Preferences form
12. Save preferences
13. Dashboard showing saved configuration

### Phase 4 --- First Job Source

14. Greenhouse integration
15. Normalize jobs
16. Generate unique IDs
17. Store jobs in SQLite
18. Test duplicate detection

### Phase 5 --- Additional Sources

19. Lever integration
20. Ashby integration
21. Common job schema
22. Error handling

### Phase 6 --- Filtering and Ranking

23. Hard filters
24. Deterministic scoring
25. Sorting
26. Candidate pool selection

### Phase 7 --- AI Job Analysis

27. Hosted model integration
28. Structured JSON output
29. JSON validation
30. Retry handling
31. AI score integration

### Phase 8 --- Resume Generation

32. Resume JSON schema
33. Resume tailoring prompt
34. LaTeX template
35. LaTeX escaping
36. PDF generation
37. PDF validation

### Phase 9 --- Google

38. Google authentication
39. Drive upload
40. Sheets creation/update
41. Store links

### Phase 10 --- Final Workflow

42. Background run
43. Progress polling
44. Result page
45. Error reporting
46. Mark Applied/Saved/Rejected
47. Full end-to-end testing

Only after this should additional features be considered.

------------------------------------------------------------------------

# 67. Definition of Done for V1

V1 is complete when you can do this:

``` text
1. Open localhost.
2. Upload your master CV once.
3. Review extracted profile.
4. Save it.
5. Set job preferences once.
6. Click "Find 50 Jobs".
7. Wait.
8. Receive 50 ranked new job opportunities.
9. Receive tailored PDF resumes.
10. Find those PDFs in Google Drive.
11. Find every job and link in Google Sheets.
12. Click the official application link.
13. Apply manually.
14. Mark the job as Applied.
15. Run the application again tomorrow.
16. Receive a fresh set without previously stored jobs.
```

If those 16 steps work reliably, **V1 is finished.**
