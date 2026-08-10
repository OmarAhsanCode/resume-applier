import re
from typing import Dict, Any, Optional

def normalize_url(url: str) -> str:
    """Normalizes application URLs by stripping query parameters and trailing slashes."""
    if not url:
        return ""
    # Strip trailing whitespace and slashes
    cleaned = url.strip().rstrip('/')
    # Remove tracking query params if needed, or return lowercase standard scheme
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

def create_normalized_job(
    source: str,
    source_job_id: Optional[str],
    company: str,
    title: str,
    location: str,
    employment_type: str,
    description: str,
    application_url: str,
    posted_date: Optional[str] = None
) -> Dict[str, Any]:
    """Factory helper returning a dictionary conforming to the normalized job schema."""
    u_id = build_unique_id(source, source_job_id, application_url)
    return {
        "source": source.lower().strip(),
        "source_job_id": str(source_job_id).strip() if source_job_id else None,
        "unique_id": u_id,
        "company": company.strip() if company else "Unknown Company",
        "title": title.strip() if title else "Software Engineer",
        "location": location.strip() if location else "Remote",
        "employment_type": employment_type.strip() if employment_type else "Full-time",
        "description": description.strip() if description else "",
        "application_url": normalize_url(application_url),
        "posted_date": posted_date
    }
