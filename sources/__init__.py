import logging
from typing import List, Dict, Any
from sources import greenhouse, lever, ashby

logger = logging.getLogger(__name__)

def discover_all_sources(search_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Discovers jobs from all supported job sources (Greenhouse, Lever, Ashby)
    and returns a combined list of normalized job dictionaries.
    """
    all_jobs = []
    
    # 1. Greenhouse
    try:
        gh_jobs = greenhouse.discover_jobs(search_config)
        all_jobs.extend(gh_jobs)
        logger.info(f"Discovered {len(gh_jobs)} jobs from Greenhouse.")
    except Exception as e:
        logger.error(f"Error in Greenhouse job discovery: {e}")
        
    # 2. Lever
    try:
        lv_jobs = lever.discover_jobs(search_config)
        all_jobs.extend(lv_jobs)
        logger.info(f"Discovered {len(lv_jobs)} jobs from Lever.")
    except Exception as e:
        logger.error(f"Error in Lever job discovery: {e}")

    # 3. Ashby
    try:
        ash_jobs = ashby.discover_jobs(search_config)
        all_jobs.extend(ash_jobs)
        logger.info(f"Discovered {len(ash_jobs)} jobs from Ashby.")
    except Exception as e:
        logger.error(f"Error in Ashby job discovery: {e}")

    return all_jobs
