import os
import sys
import json
import requests
import dotenv

sys.path.insert(0, ".")
dotenv.load_dotenv()

import sources.adzuna
import sources.base

def run_integrity_audit():
    print("=== STARTING V1.1.3 ADZUNA DATA INTEGRITY AUDIT ===")
    
    cfg = sources.adzuna.load_adzuna_config()
    print("\n--- ADZUNA ADAPTER CONFIGURATION ---")
    print(f"Country: {cfg.get('country')}")
    print(f"Enabled: {cfg.get('enabled')}")
    print(f"App ID Present: {bool(cfg.get('app_id'))}")
    print(f"App Key Present: {bool(cfg.get('app_key'))}")

    country = cfg.get("country", "in")
    app_id = cfg.get("app_id")
    app_key = cfg.get("app_key")

    if not app_id or not app_key:
        print("ERROR: Adzuna credentials not configured.")
        return

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": "software engineer intern",
        "content-type": "application/json"
    }

    print(f"\n--- QUERY PARAMETERS SENT TO ADZUNA ---")
    print(f"URL Endpoint: {url}")
    print(f"Page: 1")
    print(f"Results Per Page: 20")
    print(f"Search Query ('what'): 'software engineer intern'")
    print(f"Country: '{country}'")

    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        print(f"ERROR: Adzuna HTTP {resp.status_code}: {resp.text}")
        return

    data = resp.json()
    raw_results = data.get("results", [])
    print(f"\nRaw Results Returned by Adzuna: {len(raw_results)}")

    print("\n--- RAW API ITEM INSPECTION & ONE-TO-ONE MAPPING CHECK ---")
    normalized_jobs = []
    
    source_ids = []
    urls = []
    company_url_pairs = []
    title_url_pairs = []

    for idx, item in enumerate(raw_results, 1):
        raw_id = str(item.get("id", ""))
        raw_title = item.get("title", "")
        raw_company_obj = item.get("company", {})
        raw_company = raw_company_obj.get("display_name", "Unknown Company") if isinstance(raw_company_obj, dict) else "Unknown Company"
        raw_location_obj = item.get("location", {})
        raw_location = raw_location_obj.get("display_name", "Remote") if isinstance(raw_location_obj, dict) else "Remote"
        raw_redirect_url = item.get("redirect_url", "")
        raw_created = item.get("created", "")
        raw_contract_type = item.get("contract_type", "")
        raw_contract_time = item.get("contract_time", "")
        raw_salary_min = item.get("salary_min")
        raw_salary_max = item.get("salary_max")
        raw_category = item.get("category", {}).get("label") if isinstance(item.get("category"), dict) else None

        # Normalized job created using sources.adzuna adapter logic
        contract_time_val = raw_contract_time or raw_contract_type
        created_at_date = raw_created[:10] if raw_created else None
        
        # Canonical URL selection: Prefer raw redirect_url if available, else construct from raw_id
        if raw_redirect_url and raw_redirect_url.strip():
            canonical_url = sources.base.normalize_url(raw_redirect_url)
        else:
            canonical_url = f"https://www.adzuna.in/details/{raw_id}"

        norm_job = sources.base.create_normalized_job(
            source="adzuna",
            source_job_id=raw_id,
            company=raw_company,
            title=raw_title,
            location=raw_location,
            employment_type=contract_time_val,
            description=item.get("description", ""),
            application_url=canonical_url,
            job_url=canonical_url,
            apply_url=canonical_url,
            posted_date=created_at_date
        )

        normalized_jobs.append(norm_job)

        source_ids.append(norm_job["source_job_id"])
        urls.append(norm_job["job_url"])
        company_url_pairs.append((norm_job["company"], norm_job["job_url"]))
        title_url_pairs.append((norm_job["title"], norm_job["job_url"]))

        print(f"{idx:2d}. ID: {norm_job['source_job_id']} | Company: '{norm_job['company']}' | Title: '{norm_job['title']}' | URL: {norm_job['job_url']}")

    # Integrity Analysis
    unique_source_ids = set(source_ids)
    unique_urls = set(urls)
    dup_ids_count = len(source_ids) - len(unique_source_ids)
    dup_urls_count = len(urls) - len(unique_urls)

    # Detect conflicting company/url or title/url pairs
    url_to_companies = {}
    url_to_titles = {}
    for comp, u in company_url_pairs:
        url_to_companies.setdefault(u, set()).add(comp)
    for tit, u in title_url_pairs:
        url_to_titles.setdefault(u, set()).add(tit)

    conflicting_company_urls = {u: comps for u, comps in url_to_companies.items() if len(comps) > 1}
    conflicting_title_urls = {u: tits for u, tits in url_to_titles.items() if len(tits) > 1}

    print("\n=== INTEGRITY METRICS REPORT ===")
    print(f"Total returned: {len(normalized_jobs)}")
    print(f"Unique source IDs: {len(unique_source_ids)}")
    print(f"Unique URLs: {len(unique_urls)}")
    print(f"Duplicate IDs: {dup_ids_count}")
    print(f"Duplicate URLs: {dup_urls_count}")
    print(f"Conflicting company/URL pairs: {len(conflicting_company_urls)}")
    print(f"Conflicting title/URL pairs: {len(conflicting_title_urls)}")

    if conflicting_company_urls:
        print("\nWARNING: Conflicting company/URL pairs detected:")
        for u, comps in conflicting_company_urls.items():
            print(f"  URL: {u} -> Companies: {comps}")

    if conflicting_title_urls:
        print("\nWARNING: Conflicting title/URL pairs detected:")
        for u, tits in conflicting_title_urls.items():
            print(f"  URL: {u} -> Titles: {tits}")

if __name__ == "__main__":
    run_integrity_audit()
