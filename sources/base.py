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

CANONICAL_EMPLOYMENT_MAP = {
    "internship": "Internship",
    "entry_level": "Entry Level",
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract",
    "temporary": "Temporary",
    "unknown": "Unknown"
}

def format_employment_type_display(emp_type: Optional[str]) -> str:
    """Returns canonical display string for employment type."""
    if not emp_type:
        return "Unknown"
    clean = str(emp_type).lower().strip()
    return CANONICAL_EMPLOYMENT_MAP.get(clean, clean.replace("_", " ").title())

def _parse_salary_from_text(text: str) -> Tuple[Optional[int], Optional[str]]:
    """Helper to parse INR or foreign currency salary patterns from text string."""
    if not text or not text.strip():
        return None, None

    text_lower = text.lower()

    # 1a. Foreign Currency Ranges: e.g. $115,000 - $162,000 USD, $100k - $150k/year, $30 - $50/hour
    m_foreign_range = re.search(r"(\$|€|£)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(?:-|—|to)\s*(?:(\$|€|£)\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(usd|eur|gbp)?\s*(/\s*hour|/\s*hr|/\s*month|/\s*pm|/\s*year|/\s*yr)?", text_lower)
    if m_foreign_range:
        symbol = m_foreign_range.group(1)
        v1 = m_foreign_range.group(2)
        k1 = m_foreign_range.group(3) or ""
        v2 = m_foreign_range.group(5)
        k2 = m_foreign_range.group(6) or ""
        unit = m_foreign_range.group(8) or ""
        unit_str = unit.replace(" ", "")
        if "hour" in unit_str or "hr" in unit_str:
            display = f"{symbol}{v1}{k1} - {symbol}{v2}{k2}/hour"
        elif "month" in unit_str or "pm" in unit_str:
            display = f"{symbol}{v1}{k1} - {symbol}{v2}{k2}/month"
        else:
            display = f"{symbol}{v1}{k1} - {symbol}{v2}{k2}/year"
        return None, display

    # 1b. Foreign Currencies: $30/hour, $5,000/month, €40/hour, $100k/year
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

    # 3. INR Stipend Formats: e.g. ₹30,000 stipend, 15k stipend, stipend of ₹25,000, stipend: ₹20,000
    m_stipend = re.search(r"(?:stipend|stipend\s+of|stipend:?)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?", text_lower)
    if not m_stipend:
        m_stipend = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?\s*(?:stipend)", text_lower)
    if m_stipend:
        val = float(m_stipend.group(1).replace(",", ""))
        if m_stipend.group(2) == "k":
            val *= 1000
        monthly = int(val)
        return monthly, f"₹{monthly:,}/month"

    # 4. INR LPA / Annual Formats: e.g. ₹6 LPA, 6 Lakhs per annum, 6lpa
    m_lpa = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?\s*(?:per\s*annum|\s*pa\b)?|lac\b)", text_lower)
    if m_lpa:
        lakhs = float(m_lpa.group(1))
        annual = lakhs * 100000
        monthly = int(annual / 12)
        return monthly, f"₹{lakhs:.1f}".rstrip('0').rstrip('.') + " LPA"

    # 5. INR Raw Annual: e.g. ₹6,00,000/year, ₹800000 per annum
    m_inr_yr = re.search(r"(?:₹|rs\.?|inr)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:/\s*year|per\s*annum|/\s*yr|\s*pa\b)", text_lower)
    if m_inr_yr:
        annual = float(m_inr_yr.group(1).replace(",", ""))
        monthly = int(annual / 12)
        return monthly, f"₹{monthly:,}/month"

    return None, None

def extract_salary_with_evidence(salary_text: Optional[str], description: str = "") -> Tuple[Optional[int], str, str]:
    """
    Pipeline: source salary text -> job description fallback -> normalize_salary().
    Returns (monthly_inr_amount, display_string, salary_evidence).
    Evidence: 'source_salary_text', 'description', 'unknown'.
    """
    # 1. Try structured salary_text first
    if salary_text and salary_text.strip() and salary_text.strip().lower() != "not disclosed":
        m_inr, disp = _parse_salary_from_text(salary_text)
        if disp:
            return m_inr, disp, "source_salary_text"
        return None, salary_text.strip(), "source_salary_text"

    # 2. Try description fallback
    if description and description.strip():
        m_inr, disp = _parse_salary_from_text(description)
        if disp:
            return m_inr, disp, "description"

    return None, "Not disclosed", "unknown"

def normalize_salary(salary_text: Optional[str], description: str = "") -> Tuple[Optional[int], str]:
    """
    Deterministically parses and normalizes salary/stipend information.
    Returns (monthly_inr_amount, display_string). Returns (None, "Not disclosed") if absent.
    """
    monthly, disp, _ = extract_salary_with_evidence(salary_text, description)
    return monthly, disp

def normalize_employment_type(emp_type: Optional[str], title: str = "", description: str = "") -> str:
    """
    Normalizes employment type strings into canonical forms using an evidence hierarchy:
    1. Strong Title Evidence (overrides misleading source metadata)
    2. Source Employment Metadata
    3. Experience / Description Evidence
    Returns canonical string: 'internship', 'entry_level', 'full_time', 'part_time', 'contract', 'temporary', 'unknown'
    """
    t_lower = (title or "").lower()
    d_lower = (description or "").lower()

    # 1. Title Evidence (Highest Priority)
    # A. Internship / Trainee
    if re.search(r"\b(intern|internship|co-op|coop|trainee)\b", t_lower):
        return "internship"

    # B. New Grad
    if re.search(r"\b(new\s+grad|new\s+graduate|university\s+graduate)\b", t_lower):
        return "entry_level"

    # C. Junior Engineer
    if re.search(r"\b(junior|jr)\b", t_lower):
        return "entry_level"

    # D. Explicit Engineering Associate Titles vs Non-Engineering Associate Titles
    if re.search(r"\b(associate\s+software\s+engineer|associate\s+engineer|associate\s+developer|associate\s+sde|associate\s+swe)\b", t_lower):
        return "entry_level"

    # Senior Associate should be senior / full_time
    if re.search(r"\bsenior\s+associate\b", t_lower):
        return "full_time"

    # Non-engineering associate titles (Associate Director, Associate Manager, Associate General Counsel, Associate Vice President)
    is_non_eng_associate = bool(re.search(r"\b(associate\s+director|associate\s+manager|associate\s+general\s+counsel|associate\s+vice\s+president|associate\s+partner)\b", t_lower))

    # E. Senior / Principal / Director Titles
    if re.search(r"\b(senior|sr|lead|principal|staff|director|head|vp)\b", t_lower):
        return "full_time"

    # 2. Source Employment Metadata
    if emp_type and str(emp_type).strip():
        clean_raw = str(emp_type).lower().strip()
        clean = clean_raw.replace("_", "").replace("-", "").replace(" ", "")
        if "intern" in clean or "coop" in clean:
            return "internship"
        if "fulltime" in clean or "permanent" in clean:
            return "full_time"
        if "parttime" in clean:
            return "part_time"
        if "contract" in clean:
            return "contract"
        if "temp" in clean:
            return "temporary"

    # 3. Description Evidence Fallback
    if re.search(r"\b(internship|co-op|coop)\b", d_lower[:400]):
        return "internship"
    if not is_non_eng_associate and ("fresh graduate" in d_lower[:300] or "freshers" in d_lower[:300]):
        return "entry_level"

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

def generate_open_discovery_queries(preferences: Dict[str, Any], max_queries: int = 10) -> List[Dict[str, str]]:
    """
    Generates a balanced, deduplicated set of search queries up to max_queries.
    Interleaves candidate queries across preferred roles and target locations.
    Returns list of dicts: [{"query": "...", "role": "...", "location": "..."}]
    """
    pref_roles = preferences.get("preferred_roles", ["Software Engineer Intern"]) if preferences else ["Software Engineer Intern"]
    pref_locations = preferences.get("locations", []) if preferences else []

    # Clean preferred locations (filter out generic flags)
    clean_locations = [l.strip() for l in pref_locations if l and l.strip().lower() not in ["remote", "hybrid", "onsite"]]

    # Build per-role candidate queries list
    per_role_queries = []

    for role in pref_roles:
        role_candidates = []
        synonyms = expand_query_title(role)
        primary_title = synonyms[0] if synonyms else role

        # First priority: Pair primary title with specific target locations
        for loc in clean_locations:
            role_candidates.append({"query": f"{primary_title} {loc}", "role": role, "location": loc})

        # Second priority: Primary title alone
        role_candidates.append({"query": primary_title, "role": role, "location": ""})

        # Third priority: Expanded title synonyms
        for syn in synonyms[1:]:
            role_candidates.append({"query": syn, "role": role, "location": ""})

        per_role_queries.append(role_candidates)

    # Balanced Interleaving across roles
    final_queries = []
    seen_query_strings = set()

    max_depth = max((len(q_list) for q_list in per_role_queries), default=0)

    for depth in range(max_depth):
        for role_q_list in per_role_queries:
            if depth < len(role_q_list):
                q_item = role_q_list[depth]
                q_str = q_item["query"].strip().lower()
                if q_str not in seen_query_strings:
                    seen_query_strings.add(q_str)
                    final_queries.append(q_item)
                    if len(final_queries) >= max_queries:
                        return final_queries

    return final_queries

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
    updated_at: Optional[str] = None,
    discovery_lane: Optional[str] = None
) -> Dict[str, Any]:
    """Factory helper returning a dictionary conforming to the normalized job schema."""
    app_clean_url = normalize_url(apply_url or application_url)
    job_clean_url = normalize_url(job_url or application_url)
    u_id = build_unique_id(source, source_job_id, app_clean_url or job_clean_url)
    clean_desc = description.strip() if description else ""
    clean_title = title.strip() if title else "Software Engineer"
    
    norm_emp_type = normalize_employment_type(employment_type, clean_title, clean_desc)
    detected_wm = work_mode or detect_work_mode(location, clean_desc)
    p_at = posted_at or posted_date

    # Discovery lane: default to 'open' if adzuna else 'targeted'
    lane = discovery_lane or ("open" if (source or "").lower().strip() == "adzuna" else "targeted")

    # Salary extraction with description fallback
    parsed_inr, disp_sal, sal_ev = extract_salary_with_evidence(salary_text, clean_desc)
    eff_salary_text = salary_text if (salary_text and salary_text.strip() and salary_text.strip().lower() != "not disclosed") else disp_sal

    # V1.1 Classifiers & Quality Meta
    role_fam = classify_role_family(clean_title, clean_desc)
    exp_ev = classify_experience_evidence(clean_title, clean_desc, norm_emp_type)
    loc_ev = classify_location_evidence(location, clean_desc)
    sq = calculate_source_quality(source)
    fs = calculate_freshness_score(p_at)

    return {
        "source": source.lower().strip(),
        "source_job_id": str(source_job_id).strip() if source_job_id else None,
        "unique_id": u_id,
        "company": company.strip() if company else "Unknown Company",
        "title": clean_title,
        "location": location.strip() if location else "Remote",
        "work_mode": detected_wm,
        "employment_type": norm_emp_type,
        "raw_employment_type": str(employment_type).strip() if employment_type else None,
        "description": clean_desc,
        "salary_text": eff_salary_text,
        "normalized_salary": disp_sal,
        "application_url": app_clean_url,
        "job_url": job_clean_url,
        "apply_url": app_clean_url,
        "posted_date": p_at,
        "posted_at": p_at,
        "updated_at": updated_at,
        "discovery_lane": lane,
        "role_family": role_fam,
        "experience_evidence": exp_ev,
        "location_evidence": loc_ev,
        "salary_evidence": sal_ev,
        "source_quality": sq,
        "freshness_score": fs
    }
