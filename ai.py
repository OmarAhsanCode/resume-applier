import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Environment configuration for OpenAI-compatible AI API
AI_API_KEY = os.getenv("AI_API_KEY", "mock_key")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "llama-3.3-70b-versatile")

def _call_ai_api(prompt: str, system_prompt: str = None) -> Optional[str]:
    """Sends a chat completion request to an OpenAI-compatible API endpoint with automatic retries for rate limits."""
    if not AI_API_KEY or AI_API_KEY == "mock_key":
        logger.info("AI_API_KEY is not set or set to mock_key. Utilizing mock fallback.")
        return None

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": AI_MODEL_NAME,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    import time
    retries = 3
    for attempt in range(retries):
        delay = 6 * (attempt + 1)
        try:
            url = f"{AI_BASE_URL}/chat/completions"
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            if response.status_code == 429:
                logger.warning(f"Rate limit hit (429). Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"API error: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"Error calling AI API at {AI_BASE_URL} after {retries} attempts: {e}")
                if AI_API_KEY != "mock_key":
                    raise
                return None

def parse_resume(cv_text: str) -> Dict[str, Any]:
    """
    Parses raw Master CV text into a structured candidate profile JSON object.
    Factual accuracy rule: Return null/empty if missing, never fabricate data.
    """
    system_prompt = (
        "You are an expert ATS resume parser. Your task is to convert CV text into structured JSON. "
        "CRITICAL RULE: Never fabricate or hallucinate any facts. If a field or detail is not present "
        "in the CV text, return null or empty list. Extract exact dates, names, metrics, and technologies."
    )
    
    prompt = f"""
Extract the candidate profile from the following CV text into JSON format:

CV TEXT:
{cv_text}

OUTPUT JSON SCHEMA:
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "+1234567890",
  "links": {{
    "linkedin": "url or null",
    "github": "url or null",
    "portfolio": "url or null"
  }},
  "education": [
    {{
      "degree": "Degree title",
      "institution": "University/College name",
      "graduation_year": 2026,
      "cgpa": "GPA or null"
    }}
  ],
  "experience": [
    {{
      "company": "Company Name",
      "role": "Role Title",
      "start_date": "YYYY-MM or string",
      "end_date": "YYYY-MM, Present, or null",
      "bullets": ["Bullet point 1", "Bullet point 2"]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "description": "Brief summary",
      "technologies": ["Python", "Flask"],
      "bullets": ["Bullet point 1"]
    }}
  ],
  "skills": ["Skill 1", "Skill 2"],
  "certifications": ["Cert 1"],
  "achievements": ["Achievement 1"]
}}
"""
    raw_response = _call_ai_api(prompt, system_prompt)
    if raw_response:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "name" in parsed:
                return _clean_candidate_profile(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse AI CV output: {e}.")
            if AI_API_KEY != "mock_key":
                raise RuntimeError(f"Failed to parse AI CV output: {e}")

    if AI_API_KEY != "mock_key":
        raise RuntimeError("AI CV parsing failed or timed out.")

    # Deterministic Mock Fallback for offline/unconfigured API
    return _mock_parse_resume(cv_text)

def _clean_candidate_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures profile fields adhere to expected types and defaults."""
    return {
        "name": profile.get("name") or "Candidate Name",
        "email": profile.get("email") or "",
        "phone": profile.get("phone") or "",
        "links": profile.get("links") if isinstance(profile.get("links"), dict) else {"linkedin": None, "github": None, "portfolio": None},
        "education": profile.get("education") if isinstance(profile.get("education"), list) else [],
        "experience": profile.get("experience") if isinstance(profile.get("experience"), list) else [],
        "projects": profile.get("projects") if isinstance(profile.get("projects"), list) else [],
        "skills": profile.get("skills") if isinstance(profile.get("skills"), list) else [],
        "certifications": profile.get("certifications") if isinstance(profile.get("certifications"), list) else [],
        "achievements": profile.get("achievements") if isinstance(profile.get("achievements"), list) else []
    }

def _mock_parse_resume(cv_text: str) -> Dict[str, Any]:
    """Deterministic basic extractor for CV text fallback."""
    lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
    name = lines[0] if lines else "Candidate Name"
    
    email = None
    phone = None
    skills = []
    
    for line in lines:
        if "@" in line and not email:
            words = line.split()
            for w in words:
                if "@" in w:
                    email = w.strip("(),;")
        if any(char.isdigit() for char in line) and any(kw in line.lower() for kw in ["phone", "+", "mobile", "tel"]):
            phone = line
            
    # Sample default skills if present in text
    known_skills = ["Python", "Java", "C++", "SQL", "Flask", "Django", "React", "Machine Learning", "Git", "Linux", "Docker", "AWS", "PyTorch", "TensorFlow"]
    for ks in known_skills:
        if ks.lower() in cv_text.lower():
            skills.append(ks)
            
    return {
        "name": name,
        "email": email or "candidate@example.com",
        "phone": phone or "+1 555-0199",
        "links": {"linkedin": "https://linkedin.com/in/candidate", "github": "https://github.com/candidate", "portfolio": None},
        "education": [
            {
                "degree": "B.Tech in Computer Science & Engineering",
                "institution": "State University",
                "graduation_year": 2026,
                "cgpa": "8.5/10"
            }
        ],
        "experience": [
            {
                "company": "Tech Solutions Inc.",
                "role": "Software Engineering Intern",
                "start_date": "2025-06",
                "end_date": "2025-08",
                "bullets": [
                    "Developed REST APIs using Python and Flask serving 10k+ active users.",
                    "Optimized SQL database queries, improving endpoint response time by 25%."
                ]
            }
        ],
        "projects": [
            {
                "name": "Automated Resume Applier",
                "description": "Full-stack Python Flask application for job discovery and tailoring.",
                "technologies": ["Python", "Flask", "SQLite"],
                "bullets": [
                    "Built job discovery engine integrating public ATS sources (Greenhouse, Lever, Ashby).",
                    "Integrated automated LaTeX compilation to produce single-page PDF resumes."
                ]
            }
        ],
        "skills": skills or ["Python", "SQL", "Flask", "Machine Learning", "Git"],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "achievements": ["1st place in University Hackathon 2025"]
    }

def analyze_job(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates semantic match between stored candidate profile and discovered job posting.
    Returns structured analysis dict with AI score (0-100), recommendation, matching/missing skills.
    """
    system_prompt = (
        "You are an expert AI recruiter evaluating candidate-job fit. "
        "Analyze the job description against candidate profile. "
        "Do NOT reject a candidate solely because a preferred skill is missing if core qualifications match. "
        "Output structured JSON matching the requested schema."
    )
    
    prompt = f"""
Evaluate the candidate fit for this job posting:

CANDIDATE PROFILE:
{json.dumps(candidate_profile, indent=2)}

JOB DETAILS:
Company: {job_dict.get('company')}
Title: {job_dict.get('title')}
Location: {job_dict.get('location')}
Employment Type: {job_dict.get('employment_type')}
Description:
{job_dict.get('description', '')[:3000]}

OUTPUT JSON SCHEMA:
{{
  "recommendation": "strong_match | good_match | consider | stretch | reject",
  "score": 85,
  "eligibility": true,
  "matching_requirements": ["Python", "SQL"],
  "missing_preferred_skills": ["Azure"],
  "missing_critical_requirements": [],
  "role_alignment": 90,
  "reason": "Detailed summary of candidate suitability and key matching strengths."
}}
"""
    raw_response = _call_ai_api(prompt, system_prompt)
    if raw_response:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "score" in parsed:
                return _clean_job_analysis(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse AI job analysis JSON: {e}")
            if AI_API_KEY != "mock_key":
                raise RuntimeError(f"Failed to parse AI job analysis JSON: {e}")

    if AI_API_KEY != "mock_key":
        raise RuntimeError("AI job analysis failed or timed out.")

    # Fallback deterministic analysis
    return _mock_analyze_job(candidate_profile, job_dict)

def _clean_job_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Validates and cleans AI job analysis payload."""
    score = float(analysis.get("score", 70))
    score = max(0.0, min(100.0, score))
    rec = analysis.get("recommendation", "consider")
    if rec not in ["strong_match", "good_match", "consider", "stretch", "reject"]:
        rec = "consider"
        
    return {
        "recommendation": rec,
        "score": score,
        "eligibility": bool(analysis.get("eligibility", True)),
        "matching_requirements": analysis.get("matching_requirements", []),
        "missing_preferred_skills": analysis.get("missing_preferred_skills", []),
        "missing_critical_requirements": analysis.get("missing_critical_requirements", []),
        "role_alignment": float(analysis.get("role_alignment", 75)),
        "reason": analysis.get("reason", "Reasonable match based on candidate profile and skills.")
    }

def _mock_analyze_job(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic candidate-job match evaluation fallback."""
    cand_skills = set(s.lower() for s in candidate_profile.get("skills", []))
    desc = (job_dict.get("description", "") + " " + job_dict.get("title", "")).lower()
    
    matching = []
    missing = []
    
    common_tech = ["python", "java", "c++", "sql", "flask", "django", "react", "machine learning", "git", "linux", "docker", "aws", "pytorch", "tensorflow", "azure"]
    for tech in common_tech:
        if tech in desc:
            if tech in cand_skills or any(tech in cs.lower() for cs in candidate_profile.get("skills", [])):
                matching.append(tech.title())
            else:
                missing.append(tech.title())
                
    overlap_ratio = len(matching) / (len(matching) + len(missing)) if (matching or missing) else 0.7
    score = min(98.0, max(50.0, 60.0 + overlap_ratio * 38.0))
    
    rec = "strong_match" if score >= 85 else ("good_match" if score >= 75 else "consider")
    return {
        "recommendation": rec,
        "score": round(score, 1),
        "eligibility": True,
        "matching_requirements": matching or ["Python", "Software Engineering"],
        "missing_preferred_skills": missing[:3],
        "missing_critical_requirements": [],
        "role_alignment": round(score, 1),
        "reason": f"Matches key candidate skills ({', '.join(matching[:3]) if matching else 'core development'})."
    }

def tailor_resume(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any], ai_analysis: Dict[str, Any], resume_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tailors candidate profile content into structured Resume JSON targeted specifically for the job posting.
    Factual truthfulness rule: Can reorder, rephrase, or emphasize, but NEVER fabricate skills, projects, or dates.
    """
    system_prompt = (
        "You are an expert ATS resume tailoring engine. Your goal is to customize bullet points, summary, "
        "and skill groupings from the candidate profile to align with the job description. "
        "STRICT TRUTHFULNESS RULE: You must NEVER invent new projects, companies, dates, degrees, metrics, "
        "or unsupported technical skills. Rephrase existing bullets truthfully using job terminology."
    )
    
    links_json = json.dumps(candidate_profile.get('links', {}))
    prompt = f"""
Tailor the candidate resume for this job:

CANDIDATE PROFILE:
{json.dumps(candidate_profile, indent=2)}

JOB DETAILS:
Company: {job_dict.get('company')}
Title: {job_dict.get('title')}
Description:
{job_dict.get('description', '')[:3000]}

MATCH ANALYSIS:
{json.dumps(ai_analysis, indent=2)}

RESUME SETTINGS:
Section Order: {json.dumps(resume_settings.get('section_order', []))}

OUTPUT JSON SCHEMA:
{{
  "header": {{
    "name": "{candidate_profile.get('name')}",
    "email": "{candidate_profile.get('email')}",
    "phone": "{candidate_profile.get('phone')}",
    "links": {links_json}
  }},
  "summary": "Targeted 2-line professional summary highlighting candidate background relative to this role.",
  "education": [
    {{
      "degree": "Degree",
      "institution": "University",
      "year": "2026",
      "details": "GPA / Details"
    }}
  ],
  "experience": [
    {{
      "company": "Company",
      "role": "Role",
      "dates": "June 2025 - Aug 2025",
      "bullets": ["Tailored bullet 1", "Tailored bullet 2"]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "technologies": "Python, SQL",
      "bullets": ["Tailored project bullet 1"]
    }}
  ],
  "skills": {{
    "languages": ["Python", "SQL"],
    "frameworks": ["Flask", "PyTorch"],
    "tools": ["Git", "Linux"]
  }},
  "certifications": ["Cert 1"]
}}
"""
    raw_response = _call_ai_api(prompt, system_prompt)
    if raw_response:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "header" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Failed to parse AI resume tailoring JSON: {e}")
            if AI_API_KEY != "mock_key":
                raise RuntimeError(f"Failed to parse AI resume tailoring JSON: {e}")

    if AI_API_KEY != "mock_key":
        raise RuntimeError("AI resume tailoring failed or timed out.")

    # Fallback mock tailored resume
    return _mock_tailor_resume(candidate_profile, job_dict, ai_analysis, resume_settings)

def _mock_tailor_resume(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any], ai_analysis: Dict[str, Any], resume_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic resume content tailoring fallback."""
    title = job_dict.get("title", "Software Engineer")
    company = job_dict.get("company", "Company")
    
    summary = f"Motivated candidate with strong foundation in {', '.join(candidate_profile.get('skills', ['software development'])[:3])}, targeting the {title} role at {company}."
    
    education = []
    for ed in candidate_profile.get("education", []):
        education.append({
            "degree": ed.get("degree", "Degree"),
            "institution": ed.get("institution", "University"),
            "year": str(ed.get("graduation_year", "")),
            "details": ed.get("cgpa", "")
        })
        
    experience = []
    for exp in candidate_profile.get("experience", []):
        dates = f"{exp.get('start_date', '')} - {exp.get('end_date') or 'Present'}"
        experience.append({
            "company": exp.get("company", "Company"),
            "role": exp.get("role", "Role"),
            "dates": dates,
            "bullets": exp.get("bullets", ["Contributed to software engineering projects."])
        })
        
    projects = []
    for proj in candidate_profile.get("projects", []):
        techs = ", ".join(proj.get("technologies", []))
        projects.append({
            "name": proj.get("name", "Project"),
            "technologies": techs,
            "bullets": proj.get("bullets", [proj.get("description", "Built application solution.")])
        })
        
    all_skills = candidate_profile.get("skills", [])
    skills_dict = {
        "languages": [s for s in all_skills if s.lower() in ["python", "java", "c++", "sql", "javascript", "typescript", "html", "css"]],
        "frameworks": [s for s in all_skills if s.lower() in ["flask", "django", "react", "pytorch", "tensorflow", "fastapi"]],
        "tools": [s for s in all_skills if s.lower() not in ["python", "java", "c++", "sql", "javascript", "typescript", "html", "css", "flask", "django", "react", "pytorch", "tensorflow", "fastapi"]]
    }
    
    return {
        "header": {
            "name": candidate_profile.get("name", "Candidate Name"),
            "email": candidate_profile.get("email", ""),
            "phone": candidate_profile.get("phone", ""),
            "links": candidate_profile.get("links", {})
        },
        "summary": summary,
        "education": education or [{"degree": "B.Tech Computer Science", "institution": "University", "year": "2026", "details": ""}],
        "experience": experience,
        "projects": projects,
        "skills": skills_dict,
        "certifications": candidate_profile.get("certifications", [])
    }
