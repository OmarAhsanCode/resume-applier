import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_taleo_config() -> List[Dict[str, str]]:
    """Loads Taleo target configuration from config/sources.json or default fallback."""
    config_path = os.path.join("config", "sources.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "taleo" in data and isinstance(data["taleo"], list):
                    return data["taleo"]
        except Exception as e:
            logger.warning(f"Failed to load Taleo config from {config_path}: {e}")
            
    return [
        {"company": "Oracle", "career_url": "https://oracle.taleo.net/careersection/2/jobsearch.ftl"}
    ]

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from Taleo public career section endpoints.
    """
    targets = load_taleo_config()
    if search_config and search_config.get("taleo_targets"):
        targets = search_config["taleo_targets"]

    normalized_jobs = []

    for target in targets:
        company = target.get("company", "Taleo Employer")
        career_url = target.get("career_url")

        if not career_url:
            continue

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(career_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # Attempt to extract job postings if RSS/JSON/HTML structured data exists
                content = resp.text
                if "<rss" in content.lower() or "<?xml" in content.lower():
                    try:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(content)
                        items = root.findall(".//item")
                        for item in items:
                            title_elem = item.find("title")
                            link_elem = item.find("link")
                            desc_elem = item.find("description")
                            
                            title = title_elem.text if title_elem is not None and title_elem.text else "Job Position"
                            link = link_elem.text if link_elem is not None and link_elem.text else career_url
                            desc = desc_elem.text if desc_elem is not None and desc_elem.text else title
                            job_id = link.split("job=")[-1] if "job=" in link else None

                            norm_job = create_normalized_job(
                                source="taleo",
                                source_job_id=job_id,
                                company=company,
                                title=title,
                                location="Remote",
                                employment_type="full_time",
                                description=desc,
                                application_url=link,
                                job_url=link,
                                apply_url=link
                            )
                            normalized_jobs.append(norm_job)
                    except Exception:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(content, "html.parser")
                        items = soup.find_all("item")
                        for item in items:
                            title = item.find("title").text if item.find("title") else "Job Position"
                            link = item.find("link").text if item.find("link") else career_url
                            desc = item.find("description").text if item.find("description") else title
                            job_id = link.split("job=")[-1] if "job=" in link else None

                            norm_job = create_normalized_job(
                                source="taleo",
                                source_job_id=job_id,
                                company=company,
                                title=title,
                                location="Remote",
                                employment_type="full_time",
                                description=desc,
                                application_url=link,
                                job_url=link,
                                apply_url=link
                            )
                            normalized_jobs.append(norm_job)
                    except Exception as ex:
                        logger.debug(f"Error parsing Taleo RSS feed for {company}: {ex}")
            else:
                logger.debug(f"Taleo career URL for {company} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching Taleo jobs for {company}: {e}")

    return normalized_jobs
