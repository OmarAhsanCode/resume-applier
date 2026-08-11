import logging
from typing import List, Dict, Any
from sources import greenhouse, lever, ashby, workday, smartrecruiters, taleo, icims, adzuna

logger = logging.getLogger(__name__)

# Lightweight Source Registry
SOURCES = [
    {"name": "greenhouse", "module": greenhouse},
    {"name": "lever", "module": lever},
    {"name": "ashby", "module": ashby},
    {"name": "workday", "module": workday},
    {"name": "smartrecruiters", "module": smartrecruiters},
    {"name": "taleo", "module": taleo},
    {"name": "icims", "module": icims},
    {"name": "adzuna", "module": adzuna}
]

def discover_all_sources(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from all registered job sources using the unified Source Registry.
    Error isolation ensured per source.
    """
    all_jobs = []
    
    for source_entry in SOURCES:
        s_name = source_entry["name"]
        s_mod = source_entry["module"]
        try:
            jobs = s_mod.discover_jobs(search_config)
            all_jobs.extend(jobs)
            logger.info(f"Discovered {len(jobs)} jobs from {s_name.capitalize()}.")
        except Exception as e:
            logger.error(f"Error in {s_name.capitalize()} job discovery: {e}")

    return all_jobs
