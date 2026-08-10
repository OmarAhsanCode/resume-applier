import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

# Default target Greenhouse board tokens if none provided in search_config
DEFAULT_GREENHOUSE_BOARDS = ["stripe", "figma", "github", "discord", "gitlab", "datadog", "canonical", "doordash"]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Fetches job listings from Greenhouse public Job Board APIs.
    """
    boards = DEFAULT_GREENHOUSE_BOARDS
    if search_config and search_config.get("companies"):
        boards = [c.lower().replace(" ", "") for c in search_config["companies"]]
    
    # Check if custom greenboard tokens specified in search_config
    if search_config and search_config.get("greenhouse_boards"):
        boards = search_config["greenhouse_boards"]

    normalized_jobs = []
    
    for board in boards:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                company_name = board.capitalize()
                jobs_list = data.get("jobs", [])
                
                for item in jobs_list:
                    job_id = str(item.get("id", ""))
                    title = item.get("title", "")
                    location_obj = item.get("location", {})
                    location = location_obj.get("name", "Remote") if isinstance(location_obj, dict) else str(location_obj)
                    app_url = item.get("absolute_url", f"https://boards.greenhouse.io/{board}/jobs/{job_id}")
                    
                    # Content/description parsing
                    content = item.get("content", "")
                    # Strip basic HTML tags if HTML description returned
                    if content and ("<" in content and ">" in content):
                        try:
                            from bs4 import BeautifulSoup
                            content = BeautifulSoup(content, "html.parser").get_text(separator="\n")
                        except Exception:
                            pass
                            
                    posted_date = item.get("updated_at", "")[:10] if item.get("updated_at") else None

                    norm_job = create_normalized_job(
                        source="greenhouse",
                        source_job_id=job_id,
                        company=company_name,
                        title=title,
                        location=location,
                        employment_type="Full-time",
                        description=content,
                        application_url=app_url,
                        posted_date=posted_date
                    )
                    normalized_jobs.append(norm_job)
            else:
                logger.debug(f"Greenhouse board {board} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching Greenhouse board {board}: {e}")
            
    return normalized_jobs
