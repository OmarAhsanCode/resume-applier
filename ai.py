import os
import re
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Environment configuration for OpenAI-compatible AI API
AI_API_KEY = os.getenv("AI_API_KEY", "mock_key")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "llama-3.3-70b-versatile")

import time
import random

class AIProvider:
    def __init__(self, name: str, api_key: str, base_url: str, model_name: str):
        self.name = name
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name
        self.rate_limit_reset_time = 0.0
        self.disabled_until = 0.0

    def is_available(self) -> bool:
        if not self.api_key or self.api_key == "mock_key":
            return False
        now = time.time()
        if now < self.rate_limit_reset_time or now < self.disabled_until:
            return False
        return True

    def mark_rate_limited(self, cooldown_seconds: float = 60.0):
        self.rate_limit_reset_time = time.time() + cooldown_seconds
        logger.warning(f"AI Router: Provider '{self.name}' marked rate-limited for {cooldown_seconds:.1f}s.")

    def mark_auth_disabled(self, cooldown_seconds: float = 300.0):
        self.disabled_until = time.time() + cooldown_seconds
        logger.error(f"AI Router: Provider '{self.name}' auth error (401/403). Disabled for {cooldown_seconds:.1f}s.")

    def call_chat_completion(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1200) -> Optional[str]:
        if not self.is_available():
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }

        try:
            url = f"{self.base_url}/chat/completions"
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # Retry without response_format if model or gateway rejects json_object mode (400 Bad Request)
            if response.status_code == 400 and "response_format" in payload:
                payload_no_rf = dict(payload)
                del payload_no_rf["response_format"]
                retry_resp = requests.post(url, headers=headers, json=payload_no_rf, timeout=30)
                if retry_resp.status_code == 200:
                    response = retry_resp

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
                try:
                    cooldown = float(retry_after) if retry_after else 60.0
                except ValueError:
                    cooldown = 60.0
                self.mark_rate_limited(cooldown)
                return None
            elif response.status_code in (401, 403):
                self.mark_auth_disabled()
                return None
            elif response.status_code in (408, 500, 502, 503, 504):
                self.mark_rate_limited(60.0)
                return None

            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content")
                if content is not None:
                    return str(content)
            return None
        except Exception as e:
            logger.warning(f"AI Router: Provider '{self.name}' call failed: {e}")
            return None

class AIRouter:
    def __init__(self):
        self.providers = []
        self._init_providers()

    def _init_providers(self):
        p_key = os.getenv("GROQ_API_KEY") or os.getenv("AI_API_KEY", "mock_key")
        p_url = os.getenv("GROQ_BASE_URL") or os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
        p_model = os.getenv("GROQ_MODEL_NAME") or os.getenv("AI_MODEL_NAME", "llama-3.3-70b-versatile")
        primary = AIProvider("PrimaryGroq", p_key, p_url, p_model)

        s_key = os.getenv("SECOND_AI_API_KEY", "mock_key")
        s_url = os.getenv("SECOND_AI_BASE_URL", "https://api.groq.com/openai/v1")
        s_model = os.getenv("SECOND_AI_MODEL_NAME", "llama-3.3-70b-versatile")
        secondary = AIProvider("SecondaryFallback", s_key, s_url, s_model)

        t_key = os.getenv("THIRD_AI_API_KEY", "mock_key")
        t_url = os.getenv("THIRD_AI_BASE_URL", "https://openrouter.ai/api/v1")
        t_model = os.getenv("THIRD_AI_MODEL_NAME", "meta-llama/llama-3.3-70b-instruct")
        third = AIProvider("ThirdFallback", t_key, t_url, t_model)

        self.providers = [primary, secondary, third]

    @property
    def primary(self) -> AIProvider:
        return self.providers[0]

    @primary.setter
    def primary(self, val: AIProvider):
        self.providers[0] = val

    @property
    def secondary(self) -> AIProvider:
        return self.providers[1]

    @secondary.setter
    def secondary(self, val: AIProvider):
        self.providers[1] = val

    @property
    def third(self) -> AIProvider:
        return self.providers[2]

    @third.setter
    def third(self, val: AIProvider):
        self.providers[2] = val

    def get_available_providers(self) -> list:
        return [p for p in self.providers if p.is_available()]

    def call_ai(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1200) -> Optional[str]:
        available = self.get_available_providers()
        if not available:
            logger.warning("AI Router: All configured providers failed or unavailable.")
            return None

        for idx, provider in enumerate(self.providers):
            if not provider.is_available():
                logger.info(f"AI Router: Provider '{provider.name}' is unavailable/cooling down. Skipping.")
                continue

            if idx > 0:
                logger.info(f"AI Router: Falling back to Provider '{provider.name}'...")

            res = provider.call_chat_completion(prompt, system_prompt, max_tokens)
            if res:
                logger.info(f"AI Router: Provider '{provider.name}' succeeded.")
                return res

        logger.warning("AI Router: All configured providers failed or unavailable.")
        return None

def robust_json_loads(raw: str) -> Any:
    if not raw or not isinstance(raw, str):
        raise ValueError("Empty or non-string response from AI model")
    
    s = raw.strip()
    if not s:
        raise ValueError("Empty response from AI model after stripping whitespace")

    # 1. Strip reasoning/thinking blocks (<think>...</think> or <thought>...</thought>)
    s = re.sub(r"<(think|thought)>.*?</\1>", "", s, flags=re.DOTALL | re.IGNORECASE).strip()

    # 2. Extract content inside markdown code blocks ```json ... ``` or ``` ... ```
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    if not code_block_match:
        code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    
    if code_block_match:
        candidate_inside = code_block_match.group(1).strip()
        if "{" in candidate_inside and "}" in candidate_inside:
            s = candidate_inside

    # 3. Locate the outermost '{' ... '}' JSON object
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and start <= end:
        s = s[start:end+1]
    else:
        raise ValueError(f"No valid JSON object {{}} found in response: '{raw[:80]}...'")

    # 4. Standard json.loads
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 5. Normalization heuristics for common LLM JSON syntax errors:
    # A. Remove trailing commas before closing braces/brackets
    cleaned = re.sub(r",\s*([\}\]])", r"\1", s)
    
    # B. Fix unescaped newlines/tabs inside string literals
    def fix_string_literal(match):
        val = match.group(0)
        return val.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    cleaned = re.sub(r'"(?:[^"\\]|\\.)*"', fix_string_literal, cleaned, flags=re.DOTALL)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as err:
        try:
            cleaned_strict = re.sub(r"[\x00-\x1F\x7F]", "", cleaned)
            return json.loads(cleaned_strict)
        except Exception:
            raise ValueError(f"Failed to parse JSON: {err}. Snippet: '{cleaned[:100]}...'")

_router = AIRouter()

def _call_ai_api(prompt: str, system_prompt: str = None, max_tokens: int = 1500) -> Optional[str]:
    """Sends a chat completion request via multi-provider AI router."""
    global AI_API_KEY
    if AI_API_KEY != _router.primary.api_key:
        _router.primary.api_key = AI_API_KEY
        if AI_API_KEY != "mock_key":
            _router.primary.rate_limit_reset_time = 0.0

    res = _router.call_ai(prompt, system_prompt, max_tokens=max_tokens)
    if not res and AI_API_KEY != "mock_key":
        # Fallback to direct call with retries if router providers fail but key is configured for tests
        headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": AI_MODEL_NAME, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens, "response_format": {"type": "json_object"}}
        try:
            url = f"{AI_BASE_URL}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
    return res

def analyze_job(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes job description against candidate profile using AI router.
    Returns structured analysis dict with score, recommendation, key technologies, role summary, and key points.
    """
    system_prompt = (
        "You are an expert AI recruiter evaluating candidate-job fit. "
        "Analyze the job description against candidate profile. "
        "Output structured JSON matching the requested schema. "
        "CRITICAL RULE FOR KEY_POINTS: key_points MUST describe objective JOB FACTS (core responsibilities, tech stack, domain, team structure), NOT candidate-match evaluation commentary. "
        "Do NOT include candidate name, candidate evaluation, or match phrases like 'Omar demonstrates', 'Candidate has', or 'Strong match for candidate' in key_points."
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
{job_dict.get('description', '')[:2000]}

OUTPUT JSON SCHEMA:
{{
  "recommendation": "strong_match | good_match | consider | stretch | reject",
  "score": 85,
  "eligibility": true,
  "matching_requirements": ["Python", "SQL"],
  "missing_preferred_skills": ["Azure"],
  "missing_critical_requirements": [],
  "role_alignment": 90,
  "key_technologies": ["Python", "SQL", "LLMs"],
  "role_summary": "Build AI developer tools",
  "key_points": [
    "Build backend services for AI products",
    "Work with Python, AWS and Kubernetes",
    "Collaborate with distributed engineering teams"
  ],
  "extracted_salary": "₹50,000/month or null if not stated",
  "reason": "Detailed summary of candidate suitability and key matching strengths."
}}
"""
    raw_response = _call_ai_api(prompt, system_prompt)
    if raw_response:
        try:
            parsed = robust_json_loads(raw_response)
            if isinstance(parsed, dict) and "score" in parsed:
                return _clean_job_analysis(parsed, job_dict)
        except Exception as e:
            logger.warning(f"Failed to parse AI job analysis JSON: {e}")

    logger.warning("AI job analysis failed or timed out. Falling back to deterministic analysis.")
    return _mock_analyze_job(candidate_profile, job_dict)

def _clean_job_analysis(analysis: Dict[str, Any], job_dict: Dict[str, Any] = None) -> Dict[str, Any]:
    """Validates and cleans AI job analysis payload."""
    score = float(analysis.get("score", 70))
    score = max(0.0, min(100.0, score))
    rec = analysis.get("recommendation", "consider")
    if rec not in ["strong_match", "good_match", "consider", "stretch", "reject"]:
        rec = "consider"
        
    matching = analysis.get("matching_requirements", [])
    role_sum = analysis.get("role_summary", job_dict.get("title", "Software Engineering Role") if job_dict else "Software Engineering Role")
    techs = analysis.get("key_technologies", matching[:3])
    raw_kp = analysis.get("key_points", [])
    
    clean_kp = []
    if isinstance(raw_kp, list):
        for p in raw_kp:
            p_str = str(p).strip()
            if p_str and not re.search(r"\b(candidate|omar|applicant|resume|profile|demonstrates|fit|match|alignment|suitable)\b", p_str.lower()):
                clean_kp.append(p_str)

    if not clean_kp:
        clean_kp = [f"Focus: {role_sum}"]
        if techs:
            clean_kp.append(f"Technologies: {', '.join(techs[:3])}")
        if job_dict and job_dict.get("location"):
            clean_kp.append(f"Location: {job_dict.get('location')}")

    return {
        "recommendation": rec,
        "score": score,
        "eligibility": bool(analysis.get("eligibility", True)),
        "matching_requirements": matching,
        "missing_preferred_skills": analysis.get("missing_preferred_skills", []),
        "missing_critical_requirements": analysis.get("missing_critical_requirements", []),
        "role_alignment": float(analysis.get("role_alignment", 75)),
        "key_technologies": techs,
        "role_summary": role_sum,
        "key_points": clean_kp[:3],
        "extracted_salary": analysis.get("extracted_salary"),
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
    
    techs = matching[:3] or ["Python", "Software Engineering"]
    role_sum = f"{job_dict.get('title', 'Software Engineering Role')} at {job_dict.get('company', 'Company')}"
    key_pts = [
        f"Role: {job_dict.get('title', 'Developer')}",
        f"Technologies: {', '.join(techs)}",
        f"Location & Mode: {job_dict.get('location', 'Remote')} ({job_dict.get('work_mode', 'standard')})"
    ]

    return {
        "recommendation": rec,
        "score": round(score, 1),
        "eligibility": True,
        "matching_requirements": matching or ["Python", "Software Engineering"],
        "missing_preferred_skills": missing[:3],
        "missing_critical_requirements": [],
        "role_alignment": round(score, 1),
        "key_technologies": techs,
        "role_summary": role_sum,
        "key_points": key_pts,
        "extracted_salary": None,
        "reason": f"Matches key candidate skills ({', '.join(matching[:3]) if matching else 'core development'})."
    }

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
            parsed = robust_json_loads(raw_response)
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

FORBIDDEN_FLUFF = [
    "highly motivated", "passionate", "results-driven", "results driven",
    "seasoned expert", "seasoned professional", "dynamic professional",
    "experienced ai engineer", "expert engineer", "world-class", "rockstar"
]

def validate_tailored_resume(tailored_res: Dict[str, Any], candidate_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python Factuality Validation Layer:
    Validates AI-generated tailored resume JSON against stored candidate profile source of truth.
    Filters out hallucinated skills, fabricated projects, unknown experience entries, and invented metrics.
    """
    validated = dict(tailored_res)

    # 1. Header Enforcement
    validated["header"] = {
        "name": candidate_profile.get("name") or "Candidate Name",
        "email": candidate_profile.get("email") or "",
        "phone": candidate_profile.get("phone") or "",
        "links": candidate_profile.get("links") if isinstance(candidate_profile.get("links"), dict) else {}
    }

    # Build Master Candidate Skill Set
    cand_skills_raw = candidate_profile.get("skills", [])
    valid_skill_map = {s.lower().strip(): s for s in cand_skills_raw if isinstance(s, str)}
    
    # Also collect tech from candidate's projects
    for p in candidate_profile.get("projects", []):
        for tech in p.get("technologies", []):
            if isinstance(tech, str) and tech.strip():
                valid_skill_map[tech.lower().strip()] = tech.strip()

    # 2. Skills Validation
    skills = validated.get("skills")
    if isinstance(skills, dict):
        clean_skills = {}
        for category, skill_list in skills.items():
            if isinstance(skill_list, list):
                valid_cat_skills = []
                for sk in skill_list:
                    if isinstance(sk, str) and sk.lower().strip() in valid_skill_map:
                        valid_cat_skills.append(valid_skill_map[sk.lower().strip()])
                clean_skills[category] = valid_cat_skills
            else:
                clean_skills[category] = []
        if not any(clean_skills.values()):
            master_skills = list(cand_skills_raw)
            for p in candidate_profile.get("projects", []):
                for tech in p.get("technologies", []):
                    if tech not in master_skills:
                        master_skills.append(tech)
            languages_list = ["python", "java", "c++", "sql", "javascript", "typescript", "html", "css", "node.js", "r", "go", "bash"]
            frameworks_list = ["flask", "django", "react", "react 18", "streamlit", "pytorch", "tensorflow", "fastapi", "scikit-learn", "pandas", "xgboost", "selenium", "beautifulsoup4", "langchain", "tailwind css", "vite", "bootstrap", "jquery"]
            clean_skills = {
                "languages": [s for s in master_skills if s.lower() in languages_list],
                "frameworks": [s for s in master_skills if s.lower() in frameworks_list],
                "tools": [s for s in master_skills if s.lower() not in languages_list and s.lower() not in frameworks_list]
            }
        validated["skills"] = clean_skills
    elif isinstance(skills, list):
        valid_list = [valid_skill_map[sk.lower().strip()] for sk in skills if isinstance(sk, str) and sk.lower().strip() in valid_skill_map]
        validated["skills"] = valid_list or cand_skills_raw

    # 3. Experience Validation
    cand_exp = candidate_profile.get("experience", [])
    valid_exp_companies = {exp.get("company", "").lower().strip(): exp for exp in cand_exp if exp.get("company")}
    
    tailored_exp = validated.get("experience", [])
    clean_exp = []
    for item in tailored_exp:
        comp_name = item.get("company", "").lower().strip() if isinstance(item, dict) else ""
        if comp_name in valid_exp_companies:
            orig_exp = valid_exp_companies[comp_name]
            dates = f"{orig_exp.get('start_date', '')} - {orig_exp.get('end_date') or 'Present'}"
            item["dates"] = dates
            clean_exp.append(item)
    validated["experience"] = clean_exp or [
        {
            "company": exp.get("company", "Company"),
            "role": exp.get("role", "Role"),
            "dates": f"{exp.get('start_date', '')} - {exp.get('end_date') or 'Present'}",
            "bullets": exp.get("bullets", [])
        } for exp in cand_exp
    ]

    # 4. Projects Validation
    cand_proj = candidate_profile.get("projects", [])
    valid_proj_names = {p.get("name", "").lower().strip(): p for p in cand_proj if p.get("name")}
    
    tailored_proj = validated.get("projects", [])
    clean_proj = []
    for item in tailored_proj:
        p_name = item.get("name", "").lower().strip() if isinstance(item, dict) else ""
        if p_name in valid_proj_names:
            clean_proj.append(item)
    validated["projects"] = clean_proj or [
        {
            "name": p.get("name", "Project"),
            "technologies": ", ".join(p.get("technologies", [])),
            "bullets": p.get("bullets", [p.get("description", "")])
        } for p in cand_proj
    ]

    # 5. Metrics Verification
    master_text = json.dumps(candidate_profile)
    master_metrics = set(re.findall(r"\b\d+(?:%\b|\+\b|k\b|\.\d+)?", master_text.lower()))

    for sec in ["experience", "projects"]:
        for item in validated.get(sec, []):
            if isinstance(item, dict) and "bullets" in item and isinstance(item["bullets"], list):
                clean_bullets = []
                for bullet in item["bullets"]:
                    bullet_metrics = set(re.findall(r"\b\d+(?:%\b|\+\b|k\b|\.\d+)?", str(bullet).lower()))
                    unsupported = bullet_metrics - master_metrics
                    if unsupported:
                        logger.warning(f"Rejecting unsupported metrics in bullet: {unsupported}")
                        continue
                    clean_bullets.append(bullet)
                if not clean_bullets:
                    orig_match = valid_exp_companies.get(item.get("company", "").lower().strip()) if sec == "experience" else valid_proj_names.get(item.get("name", "").lower().strip())
                    clean_bullets = orig_match.get("bullets", []) if orig_match else ["Contributed to engineering solution."]
                item["bullets"] = clean_bullets

    # 6. Summary Sanitization
    summary = validated.get("summary", "")
    if summary and isinstance(summary, str):
        summary_lower = summary.lower()
        top_skills = ", ".join(cand_skills_raw[:3]) if cand_skills_raw else "software engineering"
        if any(fluff in summary_lower for fluff in FORBIDDEN_FLUFF) or len(summary.strip()) < 20:
            summary = f"Candidate with hands-on technical experience in {top_skills}, seeking a role aligned with candidate profile."
        validated["summary"] = summary

    return validated

def tailor_resume(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any], ai_analysis: Dict[str, Any], resume_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tailors candidate profile content into structured Resume JSON targeted specifically for the job posting.
    Factual truthfulness rule: Can reorder, rephrase, or emphasize, but NEVER fabricate skills, projects, or dates.
    """
    system_prompt = (
        "You are an expert ATS resume tailoring engine. Your goal is to customize bullet points, summary, "
        "and skill groupings from the candidate profile to align with the job description. "
        "STRICT TRUTHFULNESS RULE: You must NEVER invent new projects, companies, dates, degrees, metrics, "
        "or unsupported technical skills. Rephrase existing bullets truthfully using job terminology. "
        "Your output must be a single, valid JSON object only. Escape all backslashes and double quotes inside string values. "
        "Do NOT include raw newlines inside string values: escape them as \\n."
    )
    
    compact_cand = {
        "name": candidate_profile.get("name"),
        "email": candidate_profile.get("email"),
        "phone": candidate_profile.get("phone"),
        "skills": candidate_profile.get("skills", []),
        "education": candidate_profile.get("education", []),
        "experience": candidate_profile.get("experience", []),
        "projects": candidate_profile.get("projects", [])
    }
    cand_str = json.dumps(compact_cand, separators=(',', ':'))

    match_summary = {
        "matching_skills": ai_analysis.get("matching_requirements", []),
        "missing_skills": ai_analysis.get("missing_preferred_skills", [])
    }
    match_str = json.dumps(match_summary, separators=(',', ':'))

    links_json = json.dumps(candidate_profile.get('links', {}), separators=(',', ':'))
    desc_snippet = (job_dict.get('description', '') or '')[:1500]

    prompt = f"""
Tailor the candidate resume for this job. Ensure you produce a valid JSON object matching the schema below. Escape any quotes and newlines in string properties.

CANDIDATE:
{cand_str}

JOB:
Company: {job_dict.get('company')}
Title: {job_dict.get('title')}
Description: {desc_snippet}

MATCH:
{match_str}

OUTPUT JSON SCHEMA:
{{
  "header": {{"name": "{candidate_profile.get('name')}", "email": "{candidate_profile.get('email')}", "phone": "{candidate_profile.get('phone')}", "links": {links_json}}},
  "summary": "2-line targeted summary.",
  "education": [{{"degree": "Degree", "institution": "Institution", "year": "2026", "details": "GPA"}}],
  "experience": [{{"company": "Company", "role": "Role", "dates": "Dates", "bullets": ["Bullet 1"]}}],
  "projects": [{{"name": "Project Name", "technologies": "Python, SQL", "bullets": ["Bullet 1"]}}],
  "skills": {{"languages": ["Python"], "frameworks": ["Flask"], "tools": ["Git"]}},
  "certifications": []
}}
"""
    raw_response = _call_ai_api(prompt, system_prompt, max_tokens=4000)
    if raw_response:
        try:
            parsed = robust_json_loads(raw_response)
            if isinstance(parsed, dict) and "header" in parsed:
                return validate_tailored_resume(parsed, candidate_profile)
        except Exception as e:
            logger.warning(f"Failed to parse AI resume tailoring JSON: {e}. Raw response was: {raw_response}")
            if AI_API_KEY != "mock_key":
                raise RuntimeError(f"Failed to parse AI resume tailoring JSON: {e}. Raw response was: {raw_response}")

    if AI_API_KEY != "mock_key":
        raise RuntimeError("AI resume tailoring failed or timed out.")

    logger.warning("AI resume tailoring failed or timed out. Falling back to deterministic resume tailoring.")
    res = _mock_tailor_resume(candidate_profile, job_dict, ai_analysis, resume_settings)
    return validate_tailored_resume(res, candidate_profile)

def _mock_tailor_resume(candidate_profile: Dict[str, Any], job_dict: Dict[str, Any], ai_analysis: Dict[str, Any], resume_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic resume content tailoring fallback."""
    title = job_dict.get("title", "Software Engineer")
    company = job_dict.get("company", "Company")
    
    summary = f"Candidate with hands-on technical experience in {', '.join(candidate_profile.get('skills', ['software development'])[:3])}, targeting the {title} role at {company}."
    
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
        
    all_skills = list(candidate_profile.get("skills", []))
    for p in candidate_profile.get("projects", []):
        for tech in p.get("technologies", []):
            if tech not in all_skills:
                all_skills.append(tech)

    languages_list = ["python", "java", "c++", "sql", "javascript", "typescript", "html", "css", "node.js", "r", "go", "bash"]
    frameworks_list = ["flask", "django", "react", "react 18", "streamlit", "pytorch", "tensorflow", "fastapi", "scikit-learn", "pandas", "xgboost", "selenium", "beautifulsoup4", "langchain", "tailwind css", "vite", "bootstrap", "jquery"]

    skills_dict = {
        "languages": [s for s in all_skills if s.lower() in languages_list],
        "frameworks": [s for s in all_skills if s.lower() in frameworks_list],
        "tools": [s for s in all_skills if s.lower() not in languages_list and s.lower() not in frameworks_list]
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
