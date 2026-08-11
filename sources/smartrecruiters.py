import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_smartrecruiters_config() -> List[str]:
    """Loads SmartRecruiters target configuration from config/sources.json or default fallback."""
    config_path = os.path.join("config", "sources.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "smartrecruiters" in data and isinstance(data["smartrecruiters"], list):
                    return data["smartrecruiters"]
        except Exception as e:
            logger.warning(f"Failed to load SmartRecruiters config from {config_path}: {e}")
            
    return ["Square", "Visa", "Bosch", "Ubisoft"]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from SmartRecruiters public postings REST API.
    API: GET https://api.smartrecruiters.com/v1/companies/{company}/postings
    """
    companies = load_smartrecruiters_config()
    if search_config and search_config.get("smartrecruiters_companies"):
        companies = search_config["smartrecruiters_companies"]

    normalized_jobs = []

    for comp in companies:
        url = f"https://api.smartrecruiters.com/v1/companies/{comp}/postings"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                postings = data.get("content", [])

                for item in postings:
                    job_id = str(item.get("id", ""))
                    title = item.get("name", "")
                    
                    # Company
                    comp_obj = item.get("company", {})
                    company_name = comp_obj.get("name", comp) if isinstance(comp_obj, dict) else comp
                    
                    # Location
                    loc_obj = item.get("location", {})
                    loc_parts = []
                    if isinstance(loc_obj, dict):
                        if loc_obj.get("city"):
                            loc_parts.append(loc_obj["city"])
                        if loc_obj.get("country"):
                            loc_parts.append(loc_obj["country"])
                        is_remote = loc_obj.get("remote", False)
                        if is_remote:
                            loc_parts.append("Remote")
                    location = ", ".join(loc_parts) if loc_parts else "Remote"
                    
                    # Employment type
                    emp_type_obj = item.get("typeOfEmployment", {})
                    emp_type = emp_type_obj.get("label") if isinstance(emp_type_obj, dict) else str(emp_type_obj)
                    
                    posted_date = item.get("releasedDate", "")[:10] if item.get("releasedDate") else None
                    job_page_url = f"https://jobs.smartrecruiters.com/{comp}/{job_id}"
                    apply_page_url = f"{job_page_url}/apply"

                    norm_job = create_normalized_job(
                        source="smartrecruiters",
                        source_job_id=job_id,
                        company=company_name,
                        title=title,
                        location=location,
                        employment_type=emp_type,
                        description=title,
                        application_url=job_page_url,
                        job_url=job_page_url,
                        apply_url=apply_page_url,
                        posted_date=posted_date
                    )
                    normalized_jobs.append(norm_job)
            else:
                logger.debug(f"SmartRecruiters company {comp} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching SmartRecruiters jobs for {comp}: {e}")

    return normalized_jobs
