import logging
from typing import List, Dict, Any
from sources import greenhouse, lever, ashby, workday, smartrecruiters, taleo, icims, adzuna

logger = logging.getLogger(__name__)

# Lightweight Source Registry
SOURCES = [
    {"name": "greenhouse", "module": greenhouse, "enabled": True},
    {"name": "lever", "module": lever, "enabled": True},
    {"name": "ashby", "module": ashby, "enabled": True},
    {"name": "workday", "module": workday, "enabled": True},
    {"name": "smartrecruiters", "module": smartrecruiters, "enabled": True},
    {"name": "taleo", "module": taleo, "enabled": False},
    {"name": "icims", "module": icims, "enabled": False},
    {"name": "adzuna", "module": adzuna, "enabled": True}
]

def discover_all_sources(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from all enabled registered job sources using the unified Source Registry.
    Error isolation ensured per source.
    """
    all_jobs = []
    
    for source_entry in SOURCES:
        s_name = source_entry["name"]
        s_mod = source_entry["module"]
        
        # Check if explicitly enabled/disabled in search_config or registry default
        is_enabled = source_entry.get("enabled", True)
        if search_config and f"enable_{s_name}" in search_config:
            is_enabled = bool(search_config[f"enable_{s_name}"])
            
        if not is_enabled:
            logger.info(f"Source '{s_name}' is disabled by default. Skipping.")
            continue

        try:
            jobs = s_mod.discover_jobs(search_config)
            all_jobs.extend(jobs)
            logger.info(f"Discovered {len(jobs)} jobs from {s_name.capitalize()}.")
        except Exception as e:
            logger.error(f"Error in {s_name.capitalize()} job discovery: {e}")

    return all_jobs
