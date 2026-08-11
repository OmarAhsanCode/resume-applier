import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

DEFAULT_ASHBY_COMPANIES = ["ramp", "linear", "retool", "notion", "airtable", "openaipublic"]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Fetches job listings from Ashby public job board API.
    """
    companies = DEFAULT_ASHBY_COMPANIES
    if search_config and search_config.get("companies"):
        companies = [c.lower().replace(" ", "") for c in search_config["companies"]]
        
    if search_config and search_config.get("ashby_companies"):
        companies = search_config["ashby_companies"]

    normalized_jobs = []
    
    for comp in companies:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{comp}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                job_postings = data.get("jobs", [])
                
                for item in job_postings:
                    job_id = str(item.get("id", ""))
                    title = item.get("title", "")
                    location = item.get("locationName", "Remote")
                    emp_type = item.get("employmentType")
                    app_url = item.get("jobUrl", f"https://jobs.ashbyhq.com/{comp}/{job_id}")
                    
                    description = item.get("descriptionHtml", "") or item.get("descriptionPlain", "")
                    if description and "<" in description and ">" in description:
                        try:
                            from bs4 import BeautifulSoup
                            description = BeautifulSoup(description, "html.parser").get_text(separator="\n")
                        except Exception:
                            pass
                            
                    posted_date = item.get("publishedAt", "")[:10] if item.get("publishedAt") else None

                    norm_job = create_normalized_job(
                        source="ashby",
                        source_job_id=job_id,
                        company=comp.capitalize(),
                        title=title,
                        location=location,
                        employment_type=emp_type,
                        description=description,
                        application_url=app_url,
                        posted_date=posted_date
                    )
                    normalized_jobs.append(norm_job)
            else:
                logger.debug(f"Ashby board {comp} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching Ashby postings for {comp}: {e}")
            
    return normalized_jobs
