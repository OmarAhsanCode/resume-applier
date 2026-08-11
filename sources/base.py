import re
from typing import Dict, Any, Optional, Tuple, List

def normalize_url(url: str) -> str:
    """Normalizes application URLs by stripping query parameters and trailing slashes."""
    if not url:
        return ""
    # Remove query parameters first
    cleaned = url.split('?')[0]
    # Strip trailing whitespace and slashes
    cleaned = cleaned.strip().rstrip('/')
    return cleaned

def build_unique_id(source: str, source_job_id: Optional[str], application_url: str) -> str:
    """
    Constructs stable unique_id according to PROJECT_SPEC.md:
    Preferred: source:source_job_id
    Fallback: source:normalized_application_url
    """
    source_clean = source.lower().strip()
    if source_job_id and str(source_job_id).strip():
        return f"{source_clean}:{str(source_job_id).strip()}"
    norm_url = normalize_url(application_url)
    return f"{source_clean}:{norm_url}"

def normalize_salary(salary_text: Optional[str], description: str = "") -> Tuple[Optional[int], str]:
    """
    Deterministically parses and normalizes salary/stipend information:
    - Normalizes INR formats to monthly INR amount and formatted string ('₹50,000/month', '₹6 LPA').
    - Preserves foreign currency strings ('$30/hour', '$5,000/month') without arbitrary conversion.
    - Returns (monthly_inr_amount, display_string). Returns (None, "Not disclosed") if absent.
    """
    text = (salary_text or "") + " " + (description or "")
    if not text.strip():
        return None, "Not disclosed"

    text_lower = text.lower()

    # 1. Foreign Currencies: $30/hour, $5,000/month, €40/hour, $100k/year
    m_foreign = re.search(r"(\$|€|£)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(/\s*hour|/\s*hr|/\s*month|/\s*pm|/\s*year|/\s*yr)?", text_lower)
    if m_foreign:
        symbol = m_foreign.group(1)
        val = m_foreign.group(2)
        k_suffix = m_foreign.group(3) or ""
        unit = m_foreign.group(4) or ""
        unit_str = unit.replace(" ", "")
        if "hour" in unit_str or "hr" in unit_str:
            display = f"{symbol}{val}/hour"
        elif "year" in unit_str or "yr" in unit_str:
            display = f"{symbol}{val}{k_suffix}/year"
        else:
            display = f"{symbol}{val}{k_suffix}/month"
        return None, display

    # 2. INR Monthly Formats: e.g. ₹50,000/month, 50k/month, 50k/pm
    m_inr_month = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(?:/\s*month|per\s*month|/\s*pm|\s*pm\b)", text_lower)
    if m_inr_month:
        val = float(m_inr_month.group(1).replace(",", ""))
        if m_inr_month.group(2) == "k":
            val *= 1000
        monthly = int(val)
        return monthly, f"₹{monthly:,}/month"

    # 2. INR LPA / Annual Formats: e.g. ₹6 LPA, 6 Lakhs per annum, 6lpa
    m_lpa = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?\s*(?:per\s*annum|\s*pa\b)?|lac\b)", text_lower)
    if m_lpa:
        lakhs = float(m_lpa.group(1))
        annual = lakhs * 100000
        monthly = int(annual / 12)
        return monthly, f"₹{lakhs:.1f}".rstrip('0').rstrip('.') + " LPA"

    # 3. INR Raw Annual: e.g. ₹6,00,000/year, ₹800000 per annum
    m_inr_yr = re.search(r"(?:₹|rs\.?|inr)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:/\s*year|per\s*annum|/\s*yr|\s*pa\b)", text_lower)
    if m_inr_yr:
        annual = float(m_inr_yr.group(1).replace(",", ""))
        monthly = int(annual / 12)
        return monthly, f"₹{monthly:,}/month"

    # 4. Foreign Currencies: $30/hour, $5,000/month, €40/hour, $100k/year
    m_foreign = re.search(r"(\$|€|£)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(/\s*hour|/\s*hr|/\s*month|/\s*pm|/\s*year|/\s*yr)?", text_lower)
    if m_foreign:
        symbol = m_foreign.group(1)
        val = m_foreign.group(2)
        k_suffix = m_foreign.group(3) or ""
        unit = m_foreign.group(4) or ""
        unit_str = unit.replace(" ", "")
        if "hour" in unit_str or "hr" in unit_str:
            display = f"{symbol}{val}/hour"
        elif "year" in unit_str or "yr" in unit_str:
            display = f"{symbol}{val}{k_suffix}/year"
        else:
            display = f"{symbol}{val}{k_suffix}/month"
        return None, display

    if salary_text and salary_text.strip():
        return None, salary_text.strip()

    return None, "Not disclosed"

def normalize_employment_type(emp_type: Optional[str]) -> str:
    """
    Normalizes employment type strings from ATS adapters into standard canonical forms:
    - 'full_time'
    - 'internship'
    - 'part_time'
    - 'contract'
    - 'temporary'
    - 'unknown'
    """
    if not emp_type or not str(emp_type).strip():
        return "unknown"
    clean = str(emp_type).lower().strip().replace("_", "").replace("-", "").replace(" ", "")
    if "fulltime" in clean:
        return "full_time"
    if "intern" in clean or "coop" in clean:
        return "internship"
    if "parttime" in clean:
        return "part_time"
    if "contract" in clean:
        return "contract"
    if "temp" in clean:
        return "temporary"
    return "unknown"

def detect_work_mode(location_text: str, description_text: str = "") -> str:
    """Detects work mode: 'remote', 'hybrid', 'onsite', or 'unknown'."""
    text = (location_text or "") + " " + (description_text or "")
    text_lower = text.lower()
    if "remote" in text_lower or "work from home" in text_lower or "wfh" in text_lower:
        return "remote"
    if "hybrid" in text_lower:
        return "hybrid"
    if "onsite" in text_lower or "on-site" in text_lower or "in-office" in text_lower or "in office" in text_lower:
        return "onsite"
    return "unknown"

def expand_query_title(target_title: str) -> List[str]:
    """Returns deterministic title synonyms for query expansion without AI."""
    if not target_title:
        return []
    clean = target_title.strip()
    clean_lower = clean.lower()

    SYNONYM_MAP = {
        "software engineer intern": [
            "Software Engineer Intern", "Software Engineering Intern",
            "Software Developer Intern", "Software Development Intern",
            "SWE Intern", "SDE Intern", "Developer Intern"
        ],
        "ai/ml engineer intern": [
            "AI Engineer Intern", "ML Engineer Intern",
            "Machine Learning Intern", "Artificial Intelligence Intern",
            "Machine Learning Engineering Intern", "Applied AI Intern",
            "Generative AI Intern", "GenAI Intern"
        ],
        "backend engineer": [
            "Backend Engineer", "Back End Engineer", "Backend Developer", "Server Engineer"
        ],
        "frontend engineer": [
            "Frontend Engineer", "Front End Engineer", "Frontend Developer", "UI Engineer"
        ],
        "full stack engineer": [
            "Full Stack Engineer", "Fullstack Engineer", "Full Stack Developer"
        ]
    }

    for key, synonyms in SYNONYM_MAP.items():
        if key in clean_lower or clean_lower in key:
            # Return list preserving exact clean title first
            res = [clean] + [s for s in synonyms if s.lower() != clean_lower]
            return list(dict.fromkeys(res))

    return [clean]

def classify_role_family(title: str, description: str = "") -> str:
    """Classifies job into lightweight role families deterministically."""
    text = f"{title or ''} {description or ''}".lower()
    if re.search(r"\b(machine learning|ml|ml engineer|scikit|xgboost)\b", text):
        return "machine_learning"
    if re.search(r"\b(ai|artificial intelligence|llm|genai|generative ai|langchain|nlp)\b", text):
        return "artificial_intelligence"
    if re.search(r"\b(backend|back-end|back end|server|api|django|fastapi)\b", text):
        return "backend"
    if re.search(r"\b(frontend|front-end|front end|react|vue|ui|ux)\b", text):
        return "frontend"
    if re.search(r"\b(full stack|fullstack|full-stack)\b", text):
        return "full_stack"
    if re.search(r"\bpython\b", text):
        return "python"
    if any(k in text for k in ["data engineer", "etl", "spark", "data pipeline"]):
        return "data_engineering"
    if any(k in text for k in ["data scientist", "data science", "analytics"]):
        return "data_science"
    if any(k in text for k in ["devops", "site reliability", "sre", "ci/cd"]):
        return "devops"
    if any(k in text for k in ["cloud", "aws", "gcp", "azure"]):
        return "cloud"
    return "software_engineering"

def classify_experience_evidence(title: str, description: str = "", emp_type: str = "") -> str:
    """Classifies experience evidence: explicit_internship, explicit_entry_level, explicit_new_grad, inferred_entry_level, unknown."""
    t_lower = (title or "").lower()
    d_lower = (description or "").lower()
    e_lower = (emp_type or "").lower()

    if "intern" in t_lower or "internship" in t_lower or "co-op" in t_lower or "coop" in t_lower or "intern" in e_lower:
        return "explicit_internship"
    if "new grad" in t_lower or "new graduate" in t_lower or "university graduate" in t_lower or "fresh graduate" in d_lower[:300]:
        return "explicit_new_grad"
    if "entry level" in t_lower or "entry-level" in t_lower or "junior" in t_lower or "jr" in t_lower:
        return "explicit_entry_level"
    if any(k in d_lower[:400] for k in ["0-2 years", "0-1 year", "freshers", "fresher", "associate"]):
        return "inferred_entry_level"
    return "unknown"

def classify_location_evidence(location: str, description: str = "") -> str:
    """Classifies location evidence: explicit_remote, explicit_hybrid_city, explicit_city, unknown."""
    loc_lower = (location or "").lower()
    desc_lower = (description or "").lower()

    if "remote" in loc_lower or "wfh" in loc_lower or "work from home" in loc_lower:
        return "explicit_remote"
    if "hybrid" in loc_lower or "hybrid" in desc_lower[:300]:
        return "explicit_hybrid_city"
    if any(c in loc_lower for c in ["hyderabad", "bangalore", "bengaluru", "pune", "mumbai", "delhi", "noida", "gurgaon", "gurugram", "chennai", "kolkata", "san francisco", "london", "singapore"]):
        return "explicit_city"
    return "unknown"

def classify_salary_evidence(salary_text: Optional[str], description: str = "") -> str:
    """Classifies salary evidence: explicit_inr, explicit_foreign, stipend, unknown."""
    text = f"{salary_text or ''} {description or ''}".lower()
    if any(k in text for k in ["₹", "inr", "lpa", "lakhs", "rs."]):
        return "explicit_inr"
    if any(k in text for k in ["$", "€", "£", "usd", "eur", "gbp"]):
        return "explicit_foreign"
    if "stipend" in text:
        return "stipend"
    return "unknown"

def calculate_source_quality(source_name: str) -> float:
    """Returns source quality score multiplier (career page = 1.0, ATS = 0.95, aggregator = 0.80)."""
    s_clean = (source_name or "").lower().strip()
    if s_clean in ["company", "career_page", "direct"]:
        return 1.00
    if s_clean in ["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "taleo", "icims"]:
        return 0.95
    if s_clean in ["adzuna", "indeed", "linkedin"]:
        return 0.80
    return 0.60

def calculate_freshness_score(posted_date: Optional[str]) -> float:
    """Computes freshness score from 0.0 to 100.0 based on posted date."""
    if not posted_date:
        return 70.0  # Unknown freshness fallback
    try:
        from datetime import datetime
        dt = datetime.strptime(str(posted_date)[:10], "%Y-%m-%d")
        days = (datetime.now() - dt).days
        if days <= 3:
            return 100.0
        if days <= 7:
            return 90.0
        if days <= 14:
            return 80.0
        if days <= 30:
            return 70.0
        return 50.0
    except Exception:
        return 70.0

def is_negative_title_match(title: str, target_role_families: List[str] = None) -> Tuple[bool, str]:
    """Returns True if the title explicitly matches negative non-technical role patterns."""
    t_lower = (title or "").lower()
    NEGATIVE_PATTERNS = [
        r"\brecruiter\b", r"\bsales\b", r"\bmarketing\b", r"\bhuman\s+resources\b",
        r"\bhr\b", r"\bcustomer\s+support\b", r"\bbusiness\s+development\b",
        r"\baccount\s+manager\b", r"\bstore\s+manager\b", r"\bmedical\s+assistant\b"
    ]
    for pat in NEGATIVE_PATTERNS:
        if re.search(pat, t_lower):
            return True, f"Negative title pattern match: '{title}'"
    return False, ""

def create_normalized_job(
    source: str,
    source_job_id: Optional[str],
    company: str,
    title: str,
    location: str,
    employment_type: Optional[str],
    description: str,
    application_url: str,
    posted_date: Optional[str] = None,
    work_mode: Optional[str] = None,
    salary_text: Optional[str] = None,
    job_url: Optional[str] = None,
    apply_url: Optional[str] = None,
    posted_at: Optional[str] = None,
    updated_at: Optional[str] = None
) -> Dict[str, Any]:
    """Factory helper returning a dictionary conforming to the normalized job schema."""
    app_clean_url = normalize_url(apply_url or application_url)
    job_clean_url = normalize_url(job_url or application_url)
    u_id = build_unique_id(source, source_job_id, app_clean_url or job_clean_url)
    norm_emp_type = normalize_employment_type(employment_type)
    detected_wm = work_mode or detect_work_mode(location, description)
    p_at = posted_at or posted_date

    # V1.1 Classifiers & Quality Meta
    role_fam = classify_role_family(title, description)
    exp_ev = classify_experience_evidence(title, description, norm_emp_type)
    loc_ev = classify_location_evidence(location, description)
    sal_ev = classify_salary_evidence(salary_text, description)
    sq = calculate_source_quality(source)
    fs = calculate_freshness_score(p_at)

    return {
        "source": source.lower().strip(),
        "source_job_id": str(source_job_id).strip() if source_job_id else None,
        "unique_id": u_id,
        "company": company.strip() if company else "Unknown Company",
        "title": title.strip() if title else "Software Engineer",
        "location": location.strip() if location else "Remote",
        "work_mode": detected_wm,
        "employment_type": norm_emp_type,
        "description": description.strip() if description else "",
        "salary_text": salary_text,
        "application_url": app_clean_url,
        "job_url": job_clean_url,
        "apply_url": app_clean_url,
        "posted_date": p_at,
        "posted_at": p_at,
        "updated_at": updated_at,
        "role_family": role_fam,
        "experience_evidence": exp_ev,
        "location_evidence": loc_ev,
        "salary_evidence": sal_ev,
        "source_quality": sq,
        "freshness_score": fs
    }
