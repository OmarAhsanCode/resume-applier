import os
import re
import logging
from typing import List, Dict, Any, Optional, Callable
from sources.base import create_normalized_job

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

class AccessRestrictedError(Exception):
    """Raised when a security challenge (CAPTCHA, Cloudflare, 403/429) is encountered."""
    pass

def check_page_for_challenges(page_title: str, page_content: str) -> None:
    """Checks the page title and content for Cloudflare, CAPTCHA, or blocking text."""
    title_lower = (page_title or "").lower()
    content_lower = (page_content or "").lower()
    
    challenge_indicators = [
        "cloudflare", "captcha", "ddos-guard", "sucuri", "security check",
        "robot check", "verify you are human", "access denied", "attention required",
        "one more step", "please verify you are a human"
    ]
    
    for indicator in challenge_indicators:
        if indicator in title_lower or indicator in content_lower:
            raise AccessRestrictedError(f"Security challenge or access restriction page detected (matched '{indicator}').")

def discover_jobs_from_career_page(
    company_config: Dict[str, Any],
    search_config: Dict[str, Any],
    progress_callback: Optional[Callable[[str], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None
) -> List[Dict[str, Any]]:
    """
    Generic browser discovery adapter that loads careers_url, optionally searches for
    preferred roles, and extracts active job listings using DOM heuristics.
    """
    def log_progress(msg: str):
        logger.info(f"[BROWSER DISCOVERY] {msg}")
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    careers_url = company_config.get("careers_url")
    company_name = company_config.get("company", "Generic Company")
    
    if not careers_url:
        log_progress("No careers_url provided. Skipping browser discovery.")
        return []

    # Configurable limits
    browser_timeout = int(os.getenv("BROWSER_DISCOVERY_TIMEOUT", 15000))
    max_pages = int(os.getenv("BROWSER_DISCOVERY_MAX_PAGES", 5))
    max_jobs = int(os.getenv("BROWSER_DISCOVERY_MAX_JOBS", 100))

    if sync_playwright is None:
        log_progress("Playwright package is not installed. Skipping browser discovery.")
        return []

    normalized_jobs = []
    
    # Preferred roles for query-aware search
    preferred_roles = search_config.get("preferred_roles", [])
    if not preferred_roles:
        preferred_roles = [""] # Run at least once without query

    log_progress(f"Starting browser discovery for {company_name} at {careers_url}...")

    try:
        with sync_playwright() as p:
            # Launch headless chromium
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            page.set_default_timeout(browser_timeout)

            # Load the main careers page
            try:
                response = page.goto(careers_url, wait_until="networkidle", timeout=browser_timeout)
                if response and response.status_code in (403, 429):
                    raise AccessRestrictedError(f"HTTP {response.status_code} Access Restricted.")
            except Exception as e:
                if "AccessRestrictedError" in str(type(e)):
                    raise
                # Connection or load error
                log_progress(f"Initial page load error: {e}")
                browser.close()
                return []

            # Check security challenges immediately
            title = page.title()
            content = page.content()
            check_page_for_challenges(title, content)

            # Loop through preferred roles to perform query-aware searches if search inputs exist
            search_queries = preferred_roles[:max_pages]
            for query in search_queries:
                if stop_checker and stop_checker():
                    log_progress("Stop requested. Halting browser discovery.")
                    break

                if len(normalized_jobs) >= max_jobs:
                    break

                if query:
                    log_progress(f"Searching careers page for role: '{query}'")
                    try:
                        # Attempt to locate search input
                        search_input = page.query_selector(
                            "input[type='text'], input[placeholder*='search' i], "
                            "input[placeholder*='job' i], input[placeholder*='role' i], "
                            "input[id*='search' i], input[class*='search' i]"
                        )
                        if search_input:
                            search_input.click()
                            search_input.fill("")
                            search_input.type(query)
                            search_input.press("Enter")
                            page.wait_for_timeout(3000) # Wait for page dynamic load
                            
                            # Check challenge again after search postback
                            check_page_for_challenges(page.title(), page.content())
                    except AccessRestrictedError:
                        raise
                    except Exception as e:
                        logger.debug(f"Search input interaction failed (proceeding with page source): {e}")

                # Heuristic Link Extraction: Find links that look like job postings
                links = page.query_selector_all("a")
                job_link_patterns = [
                    r"/jobs?/", r"/careers?/", r"/postings?/", r"/apply/",
                    r"/vacanc(y|ies)/", r"/showjob", r"/job\-detail"
                ]
                
                for link in links:
                    if len(normalized_jobs) >= max_jobs:
                        break

                    href = link.get_attribute("href")
                    if not href:
                        continue

                    # Resolve absolute URL
                    try:
                        job_url = page.evaluate(f"new URL('{href}', window.location.href).href")
                    except Exception:
                        continue

                    text = (link.inner_text() or "").strip()
                    # Skip empty, too short, or too long texts (job titles are usually 2 to 10 words)
                    word_count = len(text.split())
                    if word_count < 2 or word_count > 12:
                        continue

                    # Filter out noise links like "Search jobs", "Apply now", "Learn more"
                    noise_words = [
                        "search", "apply", "learn", "read", "view", "contact", "privacy", 
                        "cookie", "about", "team", "culture", "login", "register", "join",
                        "benefits", "student", "graduat", "internship", "work", "life",
                        "sign in", "sign up", "find jobs", "back to top"
                    ]
                    if any(nw in text.lower() for nw in noise_words) and not any(kw in text.lower() for kw in ["engineer", "developer", "analyst", "intern", "designer", "scientist"]):
                        continue

                    # Match URL pattern heuristic
                    is_job_url = any(re.search(pat, href, re.IGNORECASE) for pat in job_link_patterns)
                    if not is_job_url:
                        continue

                    # Avoid duplicate URLs in this discovery run
                    if any(j["application_url"] == job_url for j in normalized_jobs):
                        continue

                    # Heuristically detect location from surrounding text or parent elements
                    location = "Remote"
                    try:
                        parent = link.evaluate_handle("el => el.parentElement")
                        parent_text = parent.evaluate("el => el.innerText")
                        if parent_text:
                            # Search for location keyword or pattern in parent
                            # Simple regex match for common location signals
                            loc_match = re.search(r"(?:Location|City|Country|Region):\s*([a-zA-Z\s,]+)", parent_text, re.I)
                            if loc_match:
                                location = loc_match.group(1).strip()
                            else:
                                # Fallback check for location words in text
                                # If parent text contains Remote/WFH
                                if any(w in parent_text.lower() for w in ["remote", "work from home", "wfh", "anywhere"]):
                                    location = "Remote"
                    except Exception:
                        pass

                    # Extract job ID from URL
                    job_id = None
                    # e.g., matching trailing digit IDs
                    id_match = re.search(r"_(\d+)$|/(\d+)(?:/|$)|job/([a-zA-Z0-9\-]+)$", job_url)
                    if id_match:
                        job_id = next(g for g in id_match.groups() if g is not None)
                    else:
                        job_id = re.sub(r"[^a-zA-Z0-9]", "", text.lower())[:20]

                    norm_job = create_normalized_job(
                        source="browser_careers",
                        source_job_id=job_id,
                        company=company_name,
                        title=text,
                        location=location,
                        employment_type="Full-time", # Default heuristic
                        description=text,            # Heuristic description
                        application_url=job_url,
                        job_url=job_url,
                        apply_url=job_url
                    )
                    normalized_jobs.append(norm_job)

            browser.close()

    except AccessRestrictedError:
        raise
    except Exception as e:
        log_progress(f"Browser discovery error for {company_name}: {e}")

    log_progress(f"Browser discovery found {len(normalized_jobs)} jobs.")
    return normalized_jobs
