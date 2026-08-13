"""
company_manager.py - Persistent watchlist manager for config/companies.json and config/sources.json.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import company_discovery

logger = logging.getLogger(__name__)

COMPANIES_CONFIG_PATH = os.path.join("config", "companies.json")
SOURCES_CONFIG_PATH = os.path.join("config", "sources.json")

def load_companies(config_path: str = COMPANIES_CONFIG_PATH) -> List[Dict[str, Any]]:
    """Loads companies list from config/companies.json."""
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                migrated = False
                for item in data:
                    # Check if unverified: last_verified is N/A/None/missing, or verification_status is unverified
                    is_unverified = (
                        item.get("last_verified") == "N/A"
                        or "last_verified" not in item
                        or item.get("last_verified") is None
                        or item.get("verification_status") == "unverified"
                    )
                    if is_unverified:
                        if item.get("verification_status") != "unverified":
                            item["verification_status"] = "unverified"
                            migrated = True
                        if item.get("verified") is not False:
                            item["verified"] = False
                            migrated = True
                        if item.get("jobs_found") is not None:
                            item["jobs_found"] = None
                            migrated = True
                        if "jobs_available" not in item or item.get("jobs_available") is not None:
                            item["jobs_available"] = None
                            migrated = True
                        if "jobs_retrieved" not in item or item.get("jobs_retrieved") is not None:
                            item["jobs_retrieved"] = None
                            migrated = True
                        if item.get("last_verified") is not None:
                            item["last_verified"] = None
                            migrated = True
                    else:
                        # Ensure fields exist for verified items
                        if "jobs_available" not in item:
                            item["jobs_available"] = item.get("jobs_found")
                            migrated = True
                        if "jobs_retrieved" not in item:
                            item["jobs_retrieved"] = item.get("jobs_found")
                            migrated = True
                        if "verification_status" not in item:
                            item["verification_status"] = "verified" if item.get("verified") else "verification_failed"
                            migrated = True
                
                if migrated:
                    try:
                        os.makedirs(os.path.dirname(config_path), exist_ok=True)
                        with open(config_path, "w", encoding="utf-8") as wf:
                            json.dump(data, wf, indent=2, ensure_ascii=False)
                        logger.info(f"Migrated and saved companies watchlist configuration to {config_path}")
                    except Exception as e:
                        logger.error(f"Error saving migrated companies config: {e}")
                return data
    except Exception as e:
        logger.error(f"Error loading companies from {config_path}: {e}")
    return []

def save_companies(companies: List[Dict[str, Any]], config_path: str = COMPANIES_CONFIG_PATH) -> None:
    """Saves companies list to config/companies.json."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(companies)} companies to {config_path}")

def load_sources(config_path: str = SOURCES_CONFIG_PATH) -> Dict[str, Any]:
    """Loads sources config from config/sources.json."""
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading sources from {config_path}: {e}")
    return {}

def save_sources(sources_dict: Dict[str, Any], config_path: str = SOURCES_CONFIG_PATH) -> None:
    """Saves sources config to config/sources.json."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(sources_dict, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved sources config to {config_path}")

def add_company_config(
    company_data: Dict[str, Any],
    companies_path: str = COMPANIES_CONFIG_PATH,
    sources_path: str = SOURCES_CONFIG_PATH
) -> Dict[str, Any]:
    """
    Persists verified company configuration to config/companies.json and config/sources.json.
    """
    comp_name = company_data.get("company") or company_data.get("company_name")
    if not comp_name:
        raise ValueError("Company name required.")

    # Enforcement: Do not persist unverified or zero-job candidates unless they are explicitly verified
    is_verified = bool(company_data.get("verified", False))
    is_addable = bool(company_data.get("addable", is_verified))
    ver_status = company_data.get("verification_status") or ("verified" if is_verified else "verification_failed")
    
    jobs_count = company_data.get("jobs_found")
    if jobs_count is not None:
        jobs_count = int(jobs_count)
    else:
        jobs_count = 0

    valid_verified_statuses = ("verified", "verified_api", "verified_html", "verified_browser")
    if not is_verified or not is_addable or ver_status not in valid_verified_statuses or jobs_count <= 0:
        reason = company_data.get("verification_reason") or "Company source is unverified or has no active jobs."
        raise ValueError(f"Cannot save company '{comp_name}': {reason}")

    priority = int(company_data.get("priority", 75))
    priority = max(1, min(100, priority))

    source_type = (company_data.get("ats_platform") or company_data.get("source") or "unknown").lower()
    slug = (company_data.get("ats_slug") or company_data.get("source_identifier") or comp_name).lower().replace(" ", "").replace("&", "")
    
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "company": comp_name,
        "careers_url": company_data.get("careers_url") or f"https://www.{slug}.com/careers",
        "official_company_url": company_data.get("official_company_url") or f"https://www.{slug}.com",
        "category": company_data.get("category") or "Targeted Watchlist",
        "priority": priority,
        "country": company_data.get("country") or "India",
        "source": source_type,
        "source_identifier": slug,
        "enabled": bool(company_data.get("enabled", True)),
        "verified": is_verified,
        "last_verified": company_data.get("last_verified") or now_iso,
        "verification_status": ver_status,
        "jobs_found": jobs_count,
        "jobs_available": company_data.get("jobs_available") if company_data.get("jobs_available") is not None else jobs_count,
        "jobs_retrieved": company_data.get("jobs_retrieved") if company_data.get("jobs_retrieved") is not None else jobs_count
    }

    # 1. Update config/companies.json
    companies = load_companies(companies_path)
    updated = False
    for idx, item in enumerate(companies):
        if item.get("company", "").strip().lower() == comp_name.strip().lower():
            companies[idx] = entry
            updated = True
            break

    if not updated:
        companies.append(entry)

    save_companies(companies, companies_path)

    # 2. Update config/sources.json if supported ATS
    sources_cfg = load_sources(sources_path)
    if source_type in ("greenhouse", "lever", "ashby", "smartrecruiters"):
        source_list = sources_cfg.setdefault(source_type, [])
        if isinstance(source_list, list) and slug not in [str(x).lower() for x in source_list]:
            source_list.append(slug)
    elif source_type == "workday":
        workday_list = sources_cfg.setdefault("workday", [])
        host = company_data.get("ats_host") or ""
        tenant = company_data.get("ats_tenant") or ""
        wd_entry = {
            "company": comp_name,
            "host": host,
            "tenant": tenant,
            "company_slug": slug
        }
        # Avoid duplicate workday targets
        exists = any(w.get("company_slug") == slug or w.get("company") == comp_name for w in workday_list if isinstance(w, dict))
        if not exists:
            workday_list.append(wd_entry)

    save_sources(sources_cfg, sources_path)
    return entry

def update_company_priority(
    company_name: str,
    priority: int,
    companies_path: str = COMPANIES_CONFIG_PATH
) -> bool:
    """Updates priority (1-100) for a company."""
    if not company_name:
        return False
    priority = max(1, min(100, int(priority)))
    companies = load_companies(companies_path)
    found = False
    for item in companies:
        if item.get("company", "").strip().lower() == company_name.strip().lower():
            item["priority"] = priority
            found = True
            break
    if found:
        save_companies(companies, companies_path)
    return found

def toggle_company_status(
    company_name: str,
    enabled: Optional[bool] = None,
    companies_path: str = COMPANIES_CONFIG_PATH
) -> bool:
    """Toggles active/disabled status for a company."""
    if not company_name:
        return False
    companies = load_companies(companies_path)
    found = False
    for item in companies:
        if item.get("company", "").strip().lower() == company_name.strip().lower():
            if enabled is None:
                item["enabled"] = not item.get("enabled", True)
            else:
                item["enabled"] = bool(enabled)
            found = True
            break
    if found:
        save_companies(companies, companies_path)
    return found

def remove_company_config(
    company_name: str,
    companies_path: str = COMPANIES_CONFIG_PATH,
    sources_path: str = SOURCES_CONFIG_PATH
) -> bool:
    """
    Removes/disables company from companies.json and sources.json.
    Does NOT touch historical SQLite database jobs!
    """
    if not company_name:
        return False

    comp_clean = company_name.strip().lower()
    companies = load_companies(companies_path)
    new_companies = [c for c in companies if c.get("company", "").strip().lower() != comp_clean]

    if len(new_companies) == len(companies):
        return False

    save_companies(new_companies, companies_path)

    # Clean from sources.json
    sources_cfg = load_sources(sources_path)
    slug = comp_clean.replace(" ", "").replace("&", "")
    for s_type, targets in sources_cfg.items():
        if isinstance(targets, list):
            sources_cfg[s_type] = [
                t for t in targets 
                if not (isinstance(t, str) and t.lower() == slug)
                and not (isinstance(t, dict) and (t.get("company_slug") == slug or t.get("company", "").lower() == comp_clean))
            ]
    save_sources(sources_cfg, sources_path)
    return True

def verify_company_config(
    company_name: str,
    companies_path: str = COMPANIES_CONFIG_PATH,
    sources_path: str = SOURCES_CONFIG_PATH
) -> Dict[str, Any]:
    """Re-runs live ATS verification for a stored company."""
    companies = load_companies(companies_path)
    target_comp = None
    for item in companies:
        if item.get("company", "").strip().lower() == company_name.strip().lower():
            target_comp = item
            break

    if not target_comp:
        raise ValueError(f"Company '{company_name}' not found in watchlist.")

    candidate_info = {
        "company_name": target_comp.get("company"),
        "ats_platform": target_comp.get("source"),
        "ats_slug": target_comp.get("source_identifier"),
        "official_company_url": target_comp.get("official_company_url"),
        "careers_url": target_comp.get("careers_url"),
        "ats_host": target_comp.get("ats_host"),
        "ats_tenant": target_comp.get("ats_tenant"),
        "access_strategy": target_comp.get("access_strategy")
    }

    # Re-verify
    verified_res = company_discovery.verify_discovered_source(candidate_info)
    
    # Save results
    target_comp["verified"] = verified_res.get("verified", False)
    target_comp["verification_status"] = verified_res.get("verification_status", "verification_failed")
    target_comp["last_verified"] = verified_res.get("last_verified")
    
    jobs_f = verified_res.get("jobs_found")
    target_comp["jobs_found"] = int(jobs_f) if jobs_f is not None else None
    
    jobs_av = verified_res.get("jobs_available")
    target_comp["jobs_available"] = int(jobs_av) if jobs_av is not None else None
    
    jobs_re = verified_res.get("jobs_retrieved")
    target_comp["jobs_retrieved"] = int(jobs_re) if jobs_re is not None else None
    
    if verified_res.get("ats_host"):
        target_comp["ats_host"] = verified_res["ats_host"]
    if verified_res.get("ats_tenant"):
        target_comp["ats_tenant"] = verified_res["ats_tenant"]
    if verified_res.get("access_strategy"):
        target_comp["access_strategy"] = verified_res["access_strategy"]

    # Also update sources.json if verified
    if verified_res.get("verified", False) and verified_res.get("verification_status") in ("verified", "verified_api", "verified_html", "verified_browser"):
        source_type = (verified_res.get("ats_platform") or target_comp.get("source") or "unknown").lower()
        slug = (verified_res.get("ats_slug") or target_comp.get("source_identifier") or company_name).lower().replace(" ", "").replace("&", "")
        
        sources_cfg = load_sources(sources_path)
        if source_type in ("greenhouse", "lever", "ashby", "smartrecruiters"):
            source_list = sources_cfg.setdefault(source_type, [])
            if isinstance(source_list, list) and slug not in [str(x).lower() for x in source_list]:
                source_list.append(slug)
        elif source_type == "workday":
            workday_list = sources_cfg.setdefault("workday", [])
            host = verified_res.get("ats_host") or target_comp.get("ats_host") or ""
            tenant = verified_res.get("ats_tenant") or target_comp.get("ats_tenant") or ""
            wd_entry = {
                "company": target_comp.get("company"),
                "host": host,
                "tenant": tenant,
                "company_slug": slug
            }
            # Avoid duplicate workday targets
            exists = any(w.get("company_slug") == slug or w.get("company") == target_comp.get("company") for w in workday_list if isinstance(w, dict))
            if not exists:
                workday_list.append(wd_entry)
        save_sources(sources_cfg, sources_path)

    save_companies(companies, companies_path)
    return target_comp
