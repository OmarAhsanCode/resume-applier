import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_icims_config() -> List[Dict[str, str]]:
    """Loads iCIMS target configuration from config/sources.json or default fallback."""
    config_path = os.path.join("config", "sources.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "icims" in data and isinstance(data["icims"], list):
                    return data["icims"]
        except Exception as e:
            logger.warning(f"Failed to load iCIMS config from {config_path}: {e}")
            
    return [
        {"company": "Microsoft", "portal_url": "https://careers.microsoft.com"}
    ]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from iCIMS public career portals.
    """
    targets = load_icims_config()
    if search_config and search_config.get("icims_targets"):
        targets = search_config["icims_targets"]

    normalized_jobs = []

    for target in targets:
        company = target.get("company", "iCIMS Employer")
        portal_url = target.get("portal_url")

        if not portal_url:
            continue

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(f"{portal_url.rstrip('/')}/jobs/search?in_iframe=1", headers=headers, timeout=10)
            if resp.status_code == 200:
                content = resp.text
                if "job" in content.lower():
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(content, "html.parser")
                        job_links = soup.find_all("a", href=True)
                        for a in job_links:
                            href = a["href"]
                            title = a.get_text(strip=True)
                            if "/jobs/" in href and len(title) > 3:
                                job_id = href.split("/jobs/")[1].split("/")[0] if "/jobs/" in href else None
                                full_url = href if href.startswith("http") else f"{portal_url.rstrip('/')}{href}"
                                norm_job = create_normalized_job(
                                    source="icims",
                                    source_job_id=job_id,
                                    company=company,
                                    title=title,
                                    location="Remote",
                                    employment_type="full_time",
                                    description=title,
                                    application_url=full_url,
                                    job_url=full_url,
                                    apply_url=full_url
                                )
                                normalized_jobs.append(norm_job)
                    except Exception as ex:
                        logger.debug(f"Error parsing iCIMS HTML for {company}: {ex}")
            else:
                logger.debug(f"iCIMS portal for {company} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching iCIMS jobs for {company}: {e}")

    return normalized_jobs
