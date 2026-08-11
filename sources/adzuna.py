import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_adzuna_config() -> Dict[str, Any]:
    """Loads Adzuna API credentials and configuration from env or config/sources.json."""
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    country = os.getenv("ADZUNA_COUNTRY", "in")
    enabled = True

    config_path = os.path.join("config", "sources.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "adzuna" in data and isinstance(data["adzuna"], dict):
                    cfg = data["adzuna"]
                    if not app_id:
                        app_id = cfg.get("app_id", "")
                    if not app_key:
                        app_key = cfg.get("app_key", "")
                    country = cfg.get("country", country)
                    enabled = cfg.get("enabled", enabled)
        except Exception as e:
            logger.warning(f"Failed to load Adzuna config from {config_path}: {e}")

    return {
        "app_id": app_id,
        "app_key": app_key,
        "country": country,
        "enabled": enabled
    }

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from Adzuna public job search API.
    API: GET https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id=...&app_key=...
    """
    config = load_adzuna_config()
    app_id = config.get("app_id")
    app_key = config.get("app_key")
    country = config.get("country", "in")
    enabled = config.get("enabled", True)

    if search_config and "adzuna_app_id" in search_config:
        app_id = search_config["adzuna_app_id"]
        app_key = search_config.get("adzuna_app_key", "")
        if app_id and app_key:
            enabled = True

    if not enabled or not app_id or not app_key:
        logger.info("Adzuna API app_id or app_key unconfigured. Skipping Adzuna job discovery.")
        return []

    what_query = "software engineer intern"
    if search_config and search_config.get("query"):
        what_query = search_config["query"]

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": what_query,
        "content-type": "application/json"
    }

    normalized_jobs = []

    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])

            for item in results:
                job_id = str(item.get("id", ""))
                title = item.get("title", "")
                
                comp_obj = item.get("company", {})
                company_name = comp_obj.get("display_name", "Unknown Company") if isinstance(comp_obj, dict) else "Unknown Company"
                
                loc_obj = item.get("location", {})
                location = loc_obj.get("display_name", "Remote") if isinstance(loc_obj, dict) else "Remote"
                
                contract_time = item.get("contract_time") or item.get("contract_type")
                redirect_url = item.get("redirect_url", "")
                description = item.get("description", "")
                created_at = item.get("created", "")[:10] if item.get("created") else None

                norm_job = create_normalized_job(
                    source="adzuna",
                    source_job_id=job_id,
                    company=company_name,
                    title=title,
                    location=location,
                    employment_type=contract_time,
                    description=description,
                    application_url=redirect_url,
                    job_url=redirect_url,
                    apply_url=redirect_url,
                    posted_date=created_at
                )
                normalized_jobs.append(norm_job)
        else:
            logger.debug(f"Adzuna search returned HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error fetching Adzuna jobs: {e}")

    return normalized_jobs
