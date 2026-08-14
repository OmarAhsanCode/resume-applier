import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from sources import greenhouse, lever, ashby, workday, smartrecruiters, taleo, icims, adzuna, first_party_careers
from sources.base import generate_open_discovery_queries

logger = logging.getLogger(__name__)

# Lightweight Source Registry
SOURCES = [
    {"name": "greenhouse", "module": greenhouse, "enabled": True, "lane": "targeted"},
    {"name": "lever", "module": lever, "enabled": True, "lane": "targeted"},
    {"name": "ashby", "module": ashby, "enabled": True, "lane": "targeted"},
    {"name": "workday", "module": workday, "enabled": True, "lane": "targeted"},
    {"name": "smartrecruiters", "module": smartrecruiters, "enabled": True, "lane": "targeted"},
    {"name": "first_party", "module": first_party_careers, "enabled": True, "lane": "targeted"},
    {"name": "taleo", "module": taleo, "enabled": False, "lane": "targeted"},
    {"name": "icims", "module": icims, "enabled": False, "lane": "targeted"},
    {"name": "adzuna", "module": adzuna, "enabled": True, "lane": "open"}
]

def discover_targeted_sources(search_config: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Discovers jobs from targeted ATS platforms (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Taleo, iCIMS).
    Returns (targeted_jobs, targeted_source_counts). Error isolation ensured per source.
    """
    targeted_jobs = []
    source_counts = {}

    try:
        import company_manager
        company_priority_map = {
            c["company"].strip().lower(): c.get("priority", 50)
            for c in company_manager.load_companies()
            if c.get("enabled", True)
        }
    except Exception:
        company_priority_map = {}

    for source_entry in SOURCES:
        if source_entry.get("lane") != "targeted":
            continue

        s_name = source_entry["name"]
        s_mod = source_entry["module"]
        
        is_enabled = source_entry.get("enabled", True)
        if search_config and f"enable_{s_name}" in search_config:
            is_enabled = bool(search_config[f"enable_{s_name}"])
            
        if not is_enabled:
            logger.info(f"Source '{s_name}' is disabled by default. Skipping.")
            continue

        try:
            jobs = s_mod.discover_jobs(search_config)
            # Ensure discovery_lane is tagged as targeted and attach company_priority
            for j in jobs:
                j["discovery_lane"] = "targeted"
                comp_clean = (j.get("company") or "").strip().lower()
                if comp_clean in company_priority_map:
                    j["company_priority"] = company_priority_map[comp_clean]
            targeted_jobs.extend(jobs)
            source_counts[s_name] = len(jobs)
            logger.info(f"Discovered {len(jobs)} jobs from {s_name.capitalize()}.")
        except Exception as e:
            logger.error(f"Error in {s_name.capitalize()} targeted discovery: {e}")
            source_counts[s_name] = 0

    return targeted_jobs, source_counts

def discover_open_sources(
    search_config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, str, Dict], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Discovers jobs from Open Discovery providers (Adzuna) using balanced query generation.
    Returns (open_jobs, open_metrics). Error isolation ensured against targeted discovery.
    """
    adzuna_cfg = adzuna.load_adzuna_config()
    if search_config and "adzuna_app_id" in search_config and search_config["adzuna_app_id"]:
        max_queries = search_config.get("max_queries", adzuna_cfg["max_queries"])
        max_pages = search_config.get("max_pages_per_query", adzuna_cfg["max_pages_per_query"])
        results_per_page = search_config.get("results_per_page", adzuna_cfg["results_per_page"])
    else:
        max_queries = adzuna_cfg["max_queries"]
        max_pages = adzuna_cfg["max_pages_per_query"]
        results_per_page = adzuna_cfg["results_per_page"]

    def log_progress(details: str, extra: Dict = None):
        logger.info(f"[OPEN DISCOVERY] {details}")
        if progress_callback:
            progress_callback("Open Discovery", f"[OPEN DISCOVERY] {details}", extra or {})

    log_progress("Generating queries...")

    # Generate balanced queries
    queries = generate_open_discovery_queries(search_config or {}, max_queries=max_queries)
    if not queries:
        queries = [{"query": "software engineer intern", "role": "Software Engineer Intern", "location": ""}]

    raw_open_jobs = []
    queries_run_count = 0

    for idx, q_info in enumerate(queries, 1):
        if stop_checker and stop_checker():
            log_progress("Open Discovery stop requested. Halting query loop.")
            break

        q_str = q_info["query"]
        log_progress(f"Query {idx}/{len(queries)}: \"{q_str}\"", {"query_idx": idx, "query_total": len(queries), "query": q_str})
        queries_run_count += 1

        for page in range(1, max_pages + 1):
            if stop_checker and stop_checker():
                break

            try:
                page_jobs = adzuna.fetch_single_query(
                    query=q_str,
                    page=page,
                    results_per_page=results_per_page,
                    search_config=search_config
                )
                for j in page_jobs:
                    j["discovery_lane"] = "open"
                raw_open_jobs.extend(page_jobs)
                log_progress(f"Adzuna returned {len(page_jobs)} jobs for query \"{q_str}\" (page {page}).")
            except Exception as e:
                logger.error(f"[OPEN DISCOVERY] Error fetching Adzuna query '{q_str}' page {page}: {e}")

    log_progress(f"Deduplicating open-discovery results...")
    
    # Pre-deduplication summary
    seen_unique_ids = set()
    unique_open_jobs = []
    for j in raw_open_jobs:
        u_id = j["unique_id"]
        if u_id not in seen_unique_ids:
            seen_unique_ids.add(u_id)
            unique_open_jobs.append(j)

    log_progress(f"{len(raw_open_jobs)} raw Adzuna jobs -> {len(unique_open_jobs)} unique open jobs.")

    open_metrics = {
        "queries_run": queries_run_count,
        "raw_count": len(raw_open_jobs),
        "unique_count": len(unique_open_jobs)
    }

    return unique_open_jobs, open_metrics

def discover_all_sources(
    search_config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, str, Dict], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None,
    return_summary: bool = False
) -> Any:
    """
    Unified discovery dispatcher routing jobs according to discovery_mode:
    - 'targeted': Targeted ATS sources only.
    - 'targeted_and_open': Merges Targeted ATS sources + Adzuna Open Discovery.
    - 'open_only': Adzuna Open Discovery only.
    If return_summary is True, returns (merged_jobs, summary).
    Otherwise returns merged_jobs list.
    """
    search_config = search_config or {}
    mode = search_config.get("discovery_mode", "targeted_and_open")

    targeted_jobs = []
    targeted_counts = {}
    open_jobs = []
    open_metrics = {"queries_run": 0, "raw_count": 0, "unique_count": 0}

    # 1. Targeted Discovery Lane
    if mode in ["targeted", "targeted_and_open"]:
        if progress_callback:
            progress_callback("Discovery", "Discovering jobs from targeted ATS platforms...", {})
        try:
            targeted_jobs, targeted_counts = discover_targeted_sources(search_config)
        except Exception as e:
            logger.error(f"Targeted discovery encountered error, continuing with open jobs: {e}")
            targeted_jobs, targeted_counts = [], {}

    if stop_checker and stop_checker():
        summary = {
            "mode": mode,
            "targeted_counts": targeted_counts,
            "open_metrics": open_metrics,
            "total_discovered": len(targeted_jobs)
        }
        res_jobs = targeted_jobs + open_jobs
        return (res_jobs, summary) if return_summary else res_jobs

    # 2. Open Discovery Lane
    if mode in ["open_only", "targeted_and_open"]:
        try:
            open_jobs, open_metrics = discover_open_sources(search_config, progress_callback, stop_checker)
        except Exception as e:
            logger.error(f"Open Discovery encountered error, continuing with targeted jobs: {e}")

    # 3. Merge Discovery Lanes BEFORE deduplication, filtering, and scoring
    merged_jobs = targeted_jobs + open_jobs
    
    summary = {
        "mode": mode,
        "targeted_counts": targeted_counts,
        "open_metrics": open_metrics,
        "total_discovered": len(merged_jobs),
        "targeted_count": len(targeted_jobs),
        "open_count": len(open_jobs)
    }

    if progress_callback:
        progress_callback(
            "Discovery",
            f"[PIPELINE] Merging targeted + open discovery... Total raw jobs: {len(merged_jobs)} (Targeted: {len(targeted_jobs)}, Open: {len(open_jobs)})",
            summary
        )

    return (merged_jobs, summary) if return_summary else merged_jobs
