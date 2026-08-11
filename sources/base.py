import re
from typing import Dict, Any, Optional, Tuple

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

def create_normalized_job(
    source: str,
    source_job_id: Optional[str],
    company: str,
    title: str,
    location: str,
    employment_type: Optional[str],
    description: str,
    application_url: str,
    posted_date: Optional[str] = None
) -> Dict[str, Any]:
    """Factory helper returning a dictionary conforming to the normalized job schema."""
    u_id = build_unique_id(source, source_job_id, application_url)
    norm_emp_type = normalize_employment_type(employment_type)
    return {
        "source": source.lower().strip(),
        "source_job_id": str(source_job_id).strip() if source_job_id else None,
        "unique_id": u_id,
        "company": company.strip() if company else "Unknown Company",
        "title": title.strip() if title else "Software Engineer",
        "location": location.strip() if location else "Remote",
        "employment_type": norm_emp_type,
        "description": description.strip() if description else "",
        "application_url": normalize_url(application_url),
        "posted_date": posted_date
    }
