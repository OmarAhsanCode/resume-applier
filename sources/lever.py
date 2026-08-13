import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

DEFAULT_LEVER_COMPANIES = ["palantir", "netflix", "spotify", "postman", "scaleai", "chime"]

def load_lever_companies() -> List[str]:
    """Loads active Lever targets from config files."""
    try:
        import company_manager
        sources_cfg = company_manager.load_sources()
        companies = company_manager.load_companies()
        
        valid_statuses = ("verified", "verified_api", "verified_html", "verified_browser")
        active_slugs = {
            c.get("source_identifier", "").lower() for c in companies
            if c.get("source") == "lever"
            and c.get("enabled", True)
            and c.get("verification_status") in valid_statuses
        }
        
        watchlist_slugs = {
            c.get("source_identifier", "").lower() for c in companies
            if c.get("source") == "lever"
        }
        
        configured = sources_cfg.get("lever", [])
        if configured and isinstance(configured, list):
            res = []
            for c in configured:
                slug = str(c).lower()
                if slug in watchlist_slugs:
                    if slug in active_slugs:
                        res.append(slug)
                else:
                    res.append(slug)
            return res
    except Exception as e:
        logger.debug(f"Error loading dynamic lever targets: {e}")
    return DEFAULT_LEVER_COMPANIES

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Fetches job listings from Lever public postings API.
    """
    companies = load_lever_companies()
    if search_config and search_config.get("companies"):
        companies = [c.lower().replace(" ", "") for c in search_config["companies"]]
        
    if search_config and search_config.get("lever_companies"):
        companies = search_config["lever_companies"]

    normalized_jobs = []
    
    for comp in companies:
        url = f"https://api.lever.co/v0/postings/{comp}?mode=json"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        job_id = str(item.get("id", ""))
                        title = item.get("text", "")
                        categories = item.get("categories", {})
                        location = categories.get("location", "Remote") if isinstance(categories, dict) else "Remote"
                        emp_type = categories.get("commitment") if isinstance(categories, dict) else None
                        
                        app_url = item.get("hostedUrl", f"https://jobs.lever.co/{comp}/{job_id}")
                        
                        description_plain = item.get("descriptionPlain", "")
                        if not description_plain and item.get("description"):
                            content = item.get("description", "")
                            try:
                                from bs4 import BeautifulSoup
                                description_plain = BeautifulSoup(content, "html.parser").get_text(separator="\n")
                            except Exception:
                                description_plain = content
                                
                        created_at = item.get("createdAt")
                        posted_date = None
                        if created_at:
                            try:
                                import datetime
                                posted_date = datetime.datetime.fromtimestamp(created_at / 1000.0).strftime('%Y-%m-%d')
                            except Exception:
                                pass

                        norm_job = create_normalized_job(
                            source="lever",
                            source_job_id=job_id,
                            company=comp.capitalize(),
                            title=title,
                            location=location,
                            employment_type=emp_type,
                            description=description_plain,
                            application_url=app_url,
                            posted_date=posted_date
                        )
                        normalized_jobs.append(norm_job)
            else:
                logger.debug(f"Lever company {comp} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching Lever postings for {comp}: {e}")
            
    return normalized_jobs
