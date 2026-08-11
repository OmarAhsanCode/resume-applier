import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_workday_config() -> List[Dict[str, str]]:
    """Loads Workday target configuration from config/sources.json or default fallback."""
    config_path = os.path.join("config", "sources.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "workday" in data and isinstance(data["workday"], list):
                    return data["workday"]
        except Exception as e:
            logger.warning(f"Failed to load Workday config from {config_path}: {e}")
            
    return [
        {"company": "Adobe", "host": "adobe.wd5.myworkdayjobs.com", "tenant": "external_careers"},
        {"company": "NVIDIA", "host": "nvidia.wd5.myworkdayjobs.com", "tenant": "NVIDIAExternalCareerSite"}
    ]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from Workday public CXS API endpoints.
    Endpoint: POST https://{host}/wday/cxs/{company_tenant}/jobs
    """
    targets = load_workday_config()
    if search_config and search_config.get("workday_targets"):
        targets = search_config["workday_targets"]

    normalized_jobs = []

    for target in targets:
        company = target.get("company", "Workday Employer")
        host = target.get("host")
        tenant = target.get("tenant")

        if not host or not tenant:
            continue

        api_url = f"https://{host}/wday/cxs/{tenant}/jobs"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": ""
        }

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                postings = data.get("jobPostings", [])

                for item in postings:
                    title = item.get("title", "")
                    ext_path = item.get("externalPath", "")
                    job_id = ext_path.strip("/").split("_")[-1] if ext_path else item.get("bulletFields", [""])[0]
                    location = item.get("locationsText") or "Remote"
                    posted_date = item.get("postedOn")
                    
                    job_page_url = f"https://{host}{ext_path}" if ext_path else f"https://{host}"
                    apply_page_url = f"{job_page_url}/apply"

                    norm_job = create_normalized_job(
                        source="workday",
                        source_job_id=job_id,
                        company=company,
                        title=title,
                        location=location,
                        employment_type=item.get("timeType"),
                        description=title,
                        application_url=job_page_url,
                        job_url=job_page_url,
                        apply_url=apply_page_url,
                        posted_date=posted_date
                    )
                    normalized_jobs.append(norm_job)
            else:
                logger.debug(f"Workday tenant {company} ({host}) returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching Workday jobs for {company}: {e}")

    return normalized_jobs
