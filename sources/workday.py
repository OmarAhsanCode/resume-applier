import os
import json
import logging
import requests
from typing import List, Dict, Any
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

def load_workday_config() -> List[Dict[str, Any]]:
    """Loads active, verified Workday target configurations from config/sources.json filtered by watchlist."""
    try:
        import company_manager
        companies = company_manager.load_companies()
        
        # Active, verified Workday company names (case-insensitive)
        active_workday_comps = {
            c["company"].strip().lower() for c in companies
            if c.get("source") == "workday"
            and c.get("enabled", True)
            and c.get("verification_status") in ("verified", "verified_api", "verified_html", "verified_browser")
        }
        
        watchlist_companies = {c["company"].strip().lower() for c in companies if c.get("source") == "workday"}
    except Exception as e:
        logger.debug(f"Error loading companies in load_workday_config: {e}")
        active_workday_comps = set()
        watchlist_companies = set()

    config_path = os.path.join("config", "sources.json")
    targets = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "workday" in data and isinstance(data["workday"], list):
                    targets = data["workday"]
        except Exception as e:
            logger.warning(f"Failed to load Workday config from {config_path}: {e}")
            
    if not targets:
        targets = [
            {"company": "Adobe", "host": "adobe.wd5.myworkdayjobs.com", "tenant": "external_careers"},
            {"company": "NVIDIA", "host": "nvidia.wd5.myworkdayjobs.com", "tenant": "NVIDIAExternalCareerSite"}
        ]
        
    filtered_targets = []
    for t in targets:
        comp_name = t.get("company", "").strip().lower()
        if comp_name in watchlist_companies:
            if comp_name in active_workday_comps:
                filtered_targets.append(t)
        else:
            # Keep targets that aren't in companies.json watchlist (like default fallbacks)
            filtered_targets.append(t)
            
    return filtered_targets

def discover_jobs(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from Workday public CXS API endpoints with pagination and query-aware search.
    Endpoint: POST https://{host}/wday/cxs/{company_tenant}/jobs
    """
    targets = load_workday_config()
    if search_config and search_config.get("workday_targets"):
        targets = search_config["workday_targets"]

    page_size = int(os.getenv("WORKDAY_PAGE_SIZE", 20))
    max_pages = int(os.getenv("WORKDAY_MAX_PAGES", 5))
    max_jobs = int(os.getenv("WORKDAY_MAX_JOBS", 100))

    preferred_roles = search_config.get("preferred_roles", []) if search_config else []
    if not preferred_roles:
        preferred_roles = [""]

    normalized_jobs = []
    seen_job_urls = set()

    for target in targets:
        company = target.get("company", "Workday Employer")
        host = target.get("host")
        tenant = target.get("tenant")

        if not host or not tenant:
            continue

        company_slug = target.get("company_slug") or company.lower().replace(" ", "")
        
        path = target.get("path")
        if path:
            api_url = f"https://{host}{path}"
        elif target.get("tenant_path"):
            api_url = f"https://{host}/wday/cxs/{target['tenant_path']}/jobs"
        else:
            api_url = f"https://{host}/wday/cxs/{company_slug}/{tenant}/jobs"
            
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        for query in preferred_roles:
            offset = 0
            page_count = 0
            
            while page_count < max_pages:
                payload = {
                    "appliedFacets": {},
                    "limit": page_size,
                    "offset": offset,
                    "searchText": query
                }
                
                try:
                    resp = requests.post(api_url, json=payload, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        postings = data.get("jobPostings", [])
                        total_available = data.get("total", len(postings))
                        
                        if not postings:
                            break
                            
                        for item in postings:
                            if len(normalized_jobs) >= max_jobs:
                                break
                                
                            title = item.get("title", "")
                            ext_path = item.get("externalPath", "")
                            job_id = ext_path.strip("/").split("_")[-1] if ext_path else item.get("bulletFields", [""])[0]
                            location = item.get("locationsText") or "Remote"
                            posted_date = item.get("postedOn")
                            
                            job_page_url = f"https://{host}{ext_path}" if ext_path else f"https://{host}"
                            apply_page_url = f"{job_page_url}/apply"
                            
                            if job_page_url in seen_job_urls:
                                continue
                            seen_job_urls.add(job_page_url)

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
                            # Set count metadata
                            norm_job["jobs_available"] = total_available
                            norm_job["jobs_retrieved"] = len(postings)
                            normalized_jobs.append(norm_job)
                            
                        offset += len(postings)
                        page_count += 1
                        
                        if offset >= total_available or len(postings) < page_size:
                            break
                    else:
                        logger.debug(f"Workday tenant {company} ({host}) returned HTTP {resp.status_code}")
                        break
                except Exception as e:
                    logger.warning(f"Error fetching Workday jobs for {company} (query='{query}', page={page_count}): {e}")
                    break

            if len(normalized_jobs) >= max_jobs:
                break

    return normalized_jobs
