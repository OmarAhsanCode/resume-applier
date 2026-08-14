#!/usr/bin/env python3
"""
Diagnostic tool for inspecting first-party career sites.
Non-destructive; does not modify any application state or production files.
"""

import sys
import os
import re
import json
import argparse
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sources.first_party_careers as fp

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

def diagnose_url(target_url: str, search_query: str = "Software Engineer"):
    print("=" * 80)
    print(f"FIRST-PARTY CAREER SITE DIAGNOSTIC: {target_url}")
    print(f"Sample Search Query: '{search_query}'")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # PART A: HTTP HTML Inspection
    # -------------------------------------------------------------------------
    print("\n--- [PART A: STATIC HTTP / HTML INSPECTION] ---")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    resp = None
    access_restricted = False
    restriction_reason = None
    html_content = ""
    status_code = None
    final_url = target_url
    content_type = "unknown"

    try:
        resp = requests.get(target_url, headers=headers, timeout=15, allow_redirects=True)
        status_code = resp.status_code
        final_url = resp.url
        content_type = resp.headers.get("Content-Type", "")
        html_content = resp.text

        print(f"HTTP Status: {status_code}")
        print(f"Final URL: {final_url}")
        print(f"Content-Type: {content_type}")
        print(f"HTML Size: {len(html_content):,} bytes")

        if status_code in (403, 429):
            access_restricted = True
            restriction_reason = f"HTTP {status_code} Access Denied / Rate Limited"

        # Check for challenge signatures
        soup = BeautifulSoup(html_content, "html.parser")
        title_text = soup.title.string.strip() if soup.title and soup.title.string else ""
        print(f"Page Title: '{title_text}'")

        try:
            fp.check_page_for_challenges(title_text, html_content)
        except fp.AccessRestrictedError as e:
            access_restricted = True
            restriction_reason = str(e)

    except Exception as e:
        print(f"HTTP Request failed: {e}")
        restriction_reason = str(e)

    print(f"Access Restricted Detected: {access_restricted} ({restriction_reason or 'None'})")

    # JSON-LD extraction
    json_ld_jobs = []
    if html_content:
        json_ld_jobs = fp.extract_jobs_from_json_ld(html_content, final_url, "DiagnosticTarget")
    print(f"JobPosting JSON-LD Objects Found: {len(json_ld_jobs)}")

    # DOM Cards & Links extraction
    dom_jobs = []
    if html_content:
        dom_jobs = fp.extract_jobs_from_html(html_content, final_url, "DiagnosticTarget")
    print(f"Recognizable DOM Job Cards / Links Found: {len(dom_jobs)}")

    # -------------------------------------------------------------------------
    # PART B: JavaScript / API Clues in HTML & Scripts
    # -------------------------------------------------------------------------
    print("\n--- [PART B: JAVASCRIPT / API CLUES IN STATIC SOURCE] ---")
    likely_patterns = [
        r'https?://[^\s"\'<>]*(?:api|job|search|posting|career|graphql)[^\s"\'<>]*',
        r'/(?:api|jobs|job|search|search-api|postings|positions|opportunities|graphql|jobs\.json|search\.json)[^\s"\'<>]*',
        r'window\.__[A-Z0-9_]+__\s*=\s*\{.*?\}',
        r'endpoint["\']?\s*:\s*["\']([^"\']+)["\']',
        r'apiUrl["\']?\s*:\s*["\']([^"\']+)["\']',
        r'searchUrl["\']?\s*:\s*["\']([^"\']+)["\']',
    ]

    discovered_clues = set()
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        # Inline and external script tags
        scripts = soup.find_all("script")
        print(f"Total <script> tags found: {len(scripts)}")
        
        script_srcs = [s.get("src") for s in scripts if s.get("src")]
        print(f"External script sources: {len(script_srcs)}")

        # Search main HTML & inline scripts
        for pat in likely_patterns:
            matches = re.findall(pat, html_content, re.IGNORECASE)
            for m in matches[:10]:
                if isinstance(m, str) and len(m) < 150 and any(w in m.lower() for w in ["api", "search", "job", "career", "graphql", "json"]):
                    discovered_clues.add(m.strip())

    print(f"Discovered potential API / endpoint string clues ({len(discovered_clues)}):")
    for clue in sorted(discovered_clues)[:15]:
        print(f"  • {clue}")

    # -------------------------------------------------------------------------
    # PART C: Playwright Network Inspection
    # -------------------------------------------------------------------------
    print("\n--- [PART C: PLAYWRIGHT DYNAMIC NETWORK & DOM INSPECTION] ---")
    recorded_network_requests = []
    job_payloads = []
    browser_dom_jobs = []

    if sync_playwright is None:
        print("Playwright is not installed. Skipping dynamic network inspection.")
    elif access_restricted:
        print("Page classified as access_restricted. Skipping browser launch per safety rules.")
    else:
        print("Launching headless Chromium to observe dynamic XHR/fetch traffic...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=headers["User-Agent"],
                    viewport={"width": 1440, "height": 900}
                )
                page = context.new_page()

                def handle_response(response):
                    try:
                        req = response.request
                        res_url = response.url
                        res_type = req.resource_type
                        if res_type in ("xhr", "fetch") or any(kw in res_url.lower() for kw in ["api", "search", "job", "graphql", "query"]):
                            status = response.status
                            ct = response.headers.get("content-type", "")
                            
                            entry = {
                                "url": res_url,
                                "method": req.method,
                                "status": status,
                                "type": res_type,
                                "content_type": ct,
                                "post_data": req.post_data,
                            }
                            
                            # Inspect JSON bodies
                            if "json" in ct or "javascript" in ct or "graphql" in res_url or "api" in res_url:
                                try:
                                    body_text = response.text()
                                    entry["body_preview"] = body_text[:300]
                                    entry["body_length"] = len(body_text)
                                    
                                    # Check if body contains job data
                                    if any(w in body_text.lower() for w in ["jobposting", "jobid", "job_id", "jobtitle", "job_title", "positiontitle", "totalcount", "jobpostings", "operationname"]):
                                        try:
                                            parsed = response.json()
                                            entry["is_job_payload"] = True
                                            entry["parsed_sample"] = parsed
                                            job_payloads.append((res_url, req.method, status, parsed))
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            
                            recorded_network_requests.append(entry)
                    except Exception:
                        pass

                page.on("response", handle_response)

                print(f"Navigating to {target_url}...")
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                except Exception as e:
                    print(f"Navigation warning: {e}")
                
                # Wait 5 seconds for background API calls and rendering
                page.wait_for_timeout(5000)

                # Check security challenges in browser
                b_title = page.title()
                b_content = page.content()
                print(f"Browser Page Title: '{b_title}'")
                print(f"Browser Final URL: '{page.url}'")
                print(f"Browser DOM HTML Size: {len(b_content):,} bytes")

                # Check for challenge in browser
                try:
                    fp.check_page_for_challenges(b_title, b_content)
                except fp.AccessRestrictedError as e:
                    print(f"Browser Security Challenge Detected: {e}")

                # Extract jobs from rendered browser DOM
                b_json_ld = fp.extract_jobs_from_json_ld(b_content, page.url, "DiagnosticTarget")
                b_dom = fp.extract_jobs_from_html(b_content, page.url, "DiagnosticTarget")
                print(f"Browser Rendered JSON-LD jobs: {len(b_json_ld)}")
                print(f"Browser Rendered DOM job cards: {len(b_dom)}")
                browser_dom_jobs = b_json_ld + b_dom

                # Look for search input or search button
                search_input = page.query_selector(
                    "input[type='text'], input[type='search'], "
                    "input[placeholder*='search' i], input[placeholder*='job' i], "
                    "input[placeholder*='title' i], input[id*='search' i], input[class*='search' i]"
                )
                if search_input:
                    print(f"Found search input. Typing query '{search_query}' to observe search XHR...")
                    try:
                        search_input.click()
                        search_input.fill(search_query)
                        search_input.press("Enter")
                        page.wait_for_timeout(5000)
                        print(f"Post-search browser URL: {page.url}")
                        
                        # Re-extract DOM jobs after search interaction
                        post_content = page.content()
                        post_dom = fp.extract_jobs_from_html(post_content, page.url, "DiagnosticTarget")
                        print(f"Post-search Browser DOM job cards: {len(post_dom)}")
                        if post_dom and not browser_dom_jobs:
                            browser_dom_jobs = post_dom
                    except Exception as ex:
                        print(f"Search input interaction error: {ex}")

                browser.close()
        except Exception as e:
            print(f"Playwright error during inspection: {e}")

    print(f"\nTotal XHR/Fetch Requests Captured: {len(recorded_network_requests)}")
    print(f"Job Data JSON Payloads Captured: {len(job_payloads)}")

    for idx, (j_url, j_meth, j_stat, j_data) in enumerate(job_payloads, 1):
        print(f"\n--- [CANDIDATE JOB ENDPOINT #{idx}] ---")
        print(f"URL: {j_url}")
        print(f"Method: {j_meth} | Status: {j_stat}")
        
        # Analyze structure
        if isinstance(j_data, dict):
            keys = list(j_data.keys())
            print(f"Top-level Keys: {keys}")
            
            # Find list of jobs
            for k in keys:
                v = j_data[k]
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    print(f"  Key '{k}' contains a list of {len(v)} objects.")
                    sample_item = v[0]
                    print(f"  Sample Item Keys: {list(sample_item.keys())[:12]}")
                    # Sample job title/id
                    t = sample_item.get("title") or sample_item.get("jobTitle") or sample_item.get("postingTitle") or sample_item.get("name")
                    i = sample_item.get("id") or sample_item.get("jobId") or sample_item.get("id_icims")
                    l = sample_item.get("location") or sample_item.get("locations") or sample_item.get("city") or sample_item.get("primaryLocation")
                    print(f"  Extracted Sample: Title='{t}', ID='{i}', Location='{l}'")
                elif isinstance(v, dict):
                    # Check nested subkeys (e.g. data -> jobs or operation)
                    for sk, sv in v.items():
                        if isinstance(sv, list) and len(sv) > 0 and isinstance(sv[0], dict):
                            print(f"  Nested Key '{k}.{sk}' contains {len(sv)} objects.")
                            print(f"  Sample Keys: {list(sv[0].keys())[:12]}")
        elif isinstance(j_data, list):
            print(f"Top-level is List of {len(j_data)} items.")
            if len(j_data) > 0 and isinstance(j_data[0], dict):
                print(f"Sample Item Keys: {list(j_data[0].keys())[:12]}")

    # -------------------------------------------------------------------------
    # PART D: Candidate Endpoint Verification via Standalone HTTP
    # -------------------------------------------------------------------------
    print("\n--- [PART D: STANDALONE HTTP ENDPOINT VERIFICATION] ---")
    for idx, (j_url, j_meth, j_stat, j_data) in enumerate(job_payloads, 1):
        print(f"\nTesting Endpoint #{idx} via standalone requests.get/post...")
        try:
            parsed = urlparse(j_url)
            base_endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            print(f"Endpoint Base: {base_endpoint}")
            
            if j_meth.upper() == "GET":
                test_r = requests.get(j_url, headers=headers, timeout=10)
            else:
                test_r = requests.post(j_url, headers=headers, json={}, timeout=10)
                
            print(f"Standalone Response Code: {test_r.status_code}")
            print(f"Standalone Content-Type: {test_r.headers.get('Content-Type')}")
            print(f"Standalone Response Size: {len(test_r.text):,} bytes")
            if test_r.status_code == 200:
                print("✓ Successfully queried standalone without browser!")
            else:
                print(f"✗ Failed standalone query (status {test_r.status_code})")
        except Exception as e:
            print(f"Error testing standalone endpoint: {e}")

    return {
        "url": target_url,
        "status_code": status_code,
        "access_restricted": access_restricted,
        "static_json_ld_count": len(json_ld_jobs),
        "static_dom_jobs_count": len(dom_jobs),
        "browser_dom_jobs_count": len(browser_dom_jobs),
        "job_payloads_count": len(job_payloads),
        "job_payloads": job_payloads,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose first-party career site")
    parser.add_argument("url", help="Careers portal URL to inspect")
    parser.add_argument("--query", default="Software Engineer", help="Sample search query")
    args = parser.parse_args()

    diagnose_url(args.url, args.query)
