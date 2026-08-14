"""
sources/first_party_careers.py - Generic first-party career portal discovery and extraction engine.

Discovers and extracts job listings directly from official company career websites
without relying on specific external ATS providers or hardcoded per-company scrapers.

Discovery & Extraction Hierarchy:
1. Generic first-party REST / API probes (Eightfold / PCSX, Amazon REST, Phenom, generic /api/jobs).
2. Schema.org JSON-LD structured data (<script type="application/ld+json"> where @type = JobPosting).
3. Generic HTML DOM job-card structures & semantic job link heuristics.
4. Headless browser (Playwright) dynamic DOM rendering with XHR/fetch JSON network interception.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

from sources.base import create_normalized_job, normalize_url

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class AccessRestrictedError(Exception):
    """Raised when an explicit security wall, CAPTCHA challenge, Cloudflare, or 403/429 block is encountered."""
    pass


def check_page_for_challenges(page_title: str, page_content: str) -> None:
    """
    Checks page title and HTML content for active blocking challenges.
    Distinguishes benign reCAPTCHA script imports from real blocking security screens.
    """
    title_lower = (page_title or "").lower()
    content_lower = (page_content or "").lower()

    # 1. High-confidence challenge indicators in Page Title
    title_challenge_markers = [
        "just a moment...", "attention required", "access denied", "security check",
        "robot check", "verify you are human", "ddos-guard", "cloudflare",
        "challenge validation", "human verification", "one more step"
    ]
    for marker in title_challenge_markers:
        if marker in title_lower:
            raise AccessRestrictedError(f"Security challenge or access restriction detected in page title (matched '{marker}').")

    # 2. High-confidence blocking challenge markers in Page Body
    body_challenge_markers = [
        "please verify you are a human",
        "verify you are a human to continue",
        "enable javascript and cookies to continue",
        "cf-browser-verification",
        "class=\"cf-error-overview\"",
        "id=\"challenge-running\"",
        "id=\"challenge-stage\"",
        "access to this page has been denied",
        "checking your browser before accessing",
        "unusual traffic from your computer network",
        "please complete the security check to access",
        "our systems have detected unusual traffic"
    ]
    for marker in body_challenge_markers:
        if marker in content_lower:
            raise AccessRestrictedError(f"Active security challenge screen detected (matched '{marker}').")


# ---------------------------------------------------------------------------
# 1. Generic JSON Job Payload Extraction
# ---------------------------------------------------------------------------

def _is_job_like_dict(d: Dict[str, Any]) -> bool:
    """Determines whether a dictionary represents a job posting."""
    if not isinstance(d, dict):
        return False
    keys = {k.lower() for k in d.keys()}
    has_title = bool({"title", "name", "jobtitle", "job_title", "postingtitle", "positiontitle", "role", "headline"} & keys)
    has_id = bool({"id", "jobid", "job_id", "displayjobid", "requisitionid", "atsjobid", "id_icims", "req_id", "code"} & keys)
    has_loc = bool({"location", "locations", "joblocation", "standardizedlocations", "city", "primarylocation", "country_code", "state"} & keys)
    has_url = bool({"url", "joburl", "job_url", "positionurl", "applicationurl", "applyurl", "job_path", "canonical_url", "link"} & keys)

    # Must have title and at least one other identifying field (id, location, or url)
    return has_title and (has_id or has_loc or has_url)


def _extract_field(d: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    """Extracts first matching field from dictionary by candidate names."""
    d_lower = {k.lower(): v for k, v in d.items()}
    for c in candidates:
        if c.lower() in d_lower:
            val = d_lower[c.lower()]
            if val is not None and val != "":
                return val
    return None


def extract_jobs_from_json_payload(
    payload: Any,
    company_name: str,
    source_url: str
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Recursively inspects arbitrary JSON structures to extract normalized job listings.
    Recognizes standard containers (jobs, positions, postings, results, items, data, etc.)
    and detects total available jobs if exposed.
    
    Returns:
        (List[normalized_jobs], total_available_count)
    """
    if not payload or not isinstance(payload, (dict, list)):
        return [], None

    jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    seen_ids = set()
    total_available: Optional[int] = None

    def find_total(d: Dict[str, Any]) -> Optional[int]:
        total_keys = [
            "total_positions", "total_jobs", "totalpositions", "totalcount",
            "total_count", "total", "hits", "count", "total_hits", "num_found"
        ]
        for k in total_keys:
            val = _extract_field(d, [k])
            if isinstance(val, int) and val >= 0:
                return val
            elif isinstance(val, str) and val.isdigit():
                return int(val)
        return None

    def normalize_single_job(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 1. Title
        title_val = _extract_field(item, ["title", "name", "jobTitle", "job_title", "postingTitle", "positionTitle", "role"])
        if not title_val or not isinstance(title_val, str) or not title_val.strip():
            return None
        title = title_val.strip()

        # 2. Job ID
        job_id_val = _extract_field(item, ["displayJobId", "jobId", "requisitionId", "atsJobId", "id_icims", "req_id", "job_id", "id", "code"])
        job_id = str(job_id_val).strip() if job_id_val is not None else None
        if not job_id:
            job_id = re.sub(r"[^a-zA-Z0-9]", "", title.lower())[:20]

        # 3. Application URL
        url_val = _extract_field(item, ["positionUrl", "applicationUrl", "jobUrl", "url", "applyUrl", "job_path", "canonical_url", "link"])
        if url_val and isinstance(url_val, str) and url_val.strip():
            raw_url = url_val.strip()
            full_url = urljoin(source_url, raw_url)
        elif job_id_val:
            # Construct standard application URL relative to source host
            parsed_src = urlparse(source_url)
            origin = f"{parsed_src.scheme}://{parsed_src.netloc}"
            full_url = f"{origin}/careers/job/{job_id_val}"
        else:
            full_url = source_url

        clean_url = normalize_url(full_url)
        dedup_key = (clean_url, str(job_id))
        if clean_url in seen_urls or str(job_id) in seen_ids:
            return None
        seen_urls.add(clean_url)
        seen_ids.add(str(job_id))

        # 4. Location
        loc_val = _extract_field(item, ["location", "locations", "jobLocation", "standardizedLocations", "primaryLocation", "city", "country_code"])
        location = "Remote"
        if isinstance(loc_val, list):
            loc_strs = [str(x).strip() for x in loc_val if x and str(x).strip()]
            if loc_strs:
                location = ", ".join(loc_strs[:3])
        elif isinstance(loc_val, dict):
            loc_parts = [
                str(loc_val.get("city") or loc_val.get("addressLocality") or "").strip(),
                str(loc_val.get("state") or loc_val.get("addressRegion") or "").strip(),
                str(loc_val.get("country") or loc_val.get("addressCountry") or "").strip()
            ]
            loc_str = ", ".join(p for p in loc_parts if p)
            if loc_str:
                location = loc_str
        elif isinstance(loc_val, str) and loc_val.strip():
            location = loc_val.strip()

        # 5. Employment Type
        emp_type_val = _extract_field(item, ["employmentType", "workLocationOption", "schedule_type", "job_schedule_type", "type", "employee_class"])
        employment_type = str(emp_type_val).strip() if emp_type_val and isinstance(emp_type_val, str) else "Full-time"

        # 6. Description / Summary
        desc_val = _extract_field(item, ["description", "summary", "jobDescription", "description_short", "basic_qualifications", "department"])
        description = title
        if isinstance(desc_val, str) and desc_val.strip():
            if "<" in desc_val and ">" in desc_val:
                desc_soup = BeautifulSoup(desc_val, "html.parser")
                description = desc_soup.get_text(separator=" ").strip()
            else:
                description = desc_val.strip()

        # 7. Posted Date
        posted_val = _extract_field(item, ["posted_date", "postedTs", "postedDate", "datePosted", "creationTs"])
        posted_date = str(posted_val).strip() if posted_val else None

        norm_job = create_normalized_job(
            source="first_party",
            source_job_id=job_id,
            company=company_name,
            title=title,
            location=location,
            employment_type=employment_type,
            description=description,
            application_url=clean_url,
            job_url=clean_url,
            apply_url=clean_url,
            posted_date=posted_date,
            discovery_lane="targeted"
        )
        return norm_job

    def traverse(obj: Any):
        nonlocal total_available
        if isinstance(obj, dict):
            if total_available is None:
                t = find_total(obj)
                if t is not None:
                    total_available = t

            # Check if this dictionary itself is a job item
            if _is_job_like_dict(obj):
                nj = normalize_single_job(obj)
                if nj:
                    jobs.append(nj)
                return

            # Traverse all child structures
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    traverse(v)

        elif isinstance(obj, list):
            for elem in obj:
                traverse(elem)

    traverse(payload)

    if total_available is None and jobs:
        total_available = len(jobs)

    return jobs, total_available


# ---------------------------------------------------------------------------
# 2. Schema.org JSON-LD Extractor
# ---------------------------------------------------------------------------

def extract_jobs_from_json_ld(
    html: str,
    base_url: str,
    company_name: str
) -> List[Dict[str, Any]]:
    """
    Parses <script type="application/ld+json"> blocks and extracts Schema.org JobPosting objects.
    """
    if not html:
        return []

    jobs = []
    seen_urls = set()
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    for s in scripts:
        raw_text = s.string or s.text
        if not raw_text or not raw_text.strip():
            continue
        try:
            parsed = json.loads(raw_text.strip())
            extracted_jobs, _ = extract_jobs_from_json_payload(parsed, company_name, base_url)
            for j in extracted_jobs:
                if j["application_url"] not in seen_urls:
                    seen_urls.add(j["application_url"])
                    jobs.append(j)
        except Exception:
            continue

    return jobs


# ---------------------------------------------------------------------------
# 3. HTML DOM Job-Card & Semantic Link Extractor
# ---------------------------------------------------------------------------

NOISE_WORDS = [
    "search", "search jobs", "apply", "apply now", "learn more", "read more",
    "view all", "contact", "privacy", "privacy policy", "cookies", "terms",
    "about", "team", "culture", "login", "sign in", "sign up", "register",
    "join our team", "benefits", "careers", "all jobs", "back to top", "home"
]

JOB_LINK_PATTERNS = [
    r"/jobs?/[a-zA-Z0-9_\-\.\/]+",
    r"/careers?/[a-zA-Z0-9_\-\.\/]+",
    r"/postings?/[a-zA-Z0-9_\-\.\/]+",
    r"/positions?/[a-zA-Z0-9_\-\.\/]+",
    r"/vacanc(?:y|ies)/[a-zA-Z0-9_\-\.\/]+",
    r"/showjob/[a-zA-Z0-9_\-\.\/]+",
    r"/job\-detail/[a-zA-Z0-9_\-\.\/]+",
    r"/apply/[a-zA-Z0-9_\-\.\/]+"
]

TECH_ROLE_KEYWORDS = [
    "engineer", "developer", "analyst", "intern", "designer", "scientist",
    "architect", "consultant", "specialist", "associate", "programmer", "manager"
]


# ---------------------------------------------------------------------------
# 3b. Google / WIZ AF_initDataCallback Positional Array Extraction
# ---------------------------------------------------------------------------

def extract_jobs_from_af_init_data(
    html: str,
    company_name: str,
    base_url: str
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Extracts structured jobs and total available count from Google/WIZ AF_initDataCallback payloads.
    
    Structure:
    AF_initDataCallback({
        key: 'ds:1', ...
        data: [
            [ [job_tuple_1], [job_tuple_2], ... ],
            cursor/state,
            total_count (int),
            page_size (int)
        ],
        sideChannel: {}
    });
    """
    if not html or not isinstance(html, str) or "AF_initDataCallback" not in html:
        return [], None

    jobs: List[Dict[str, Any]] = []
    total_available: Optional[int] = None
    seen_urls = set()

    # Match AF_initDataCallback blocks with data payload
    pattern = r"AF_initDataCallback\s*\(\s*\{.*?key:\s*['\"]([^'\"]+)['\"].*?data:\s*(.*?),\s*sideChannel:\s*\{.*?\}\s*\);"
    matches = list(re.finditer(pattern, html, re.DOTALL))
    if not matches:
        pattern_fallback = r"AF_initDataCallback\s*\(\s*\{.*?data:\s*(\[.*?\])\s*\}\s*\);"
        matches = list(re.finditer(pattern_fallback, html, re.DOTALL))

    for m in matches:
        raw_json = m.group(2) if len(m.groups()) >= 2 else m.group(1)
        try:
            payload = json.loads(raw_json)
        except Exception:
            continue

        if not isinstance(payload, list) or len(payload) == 0:
            continue

        # Look for the job array and total count
        job_array = None
        if isinstance(payload[0], list):
            # Job tuples must be lists with at least 4 elements or structural job signals
            sample = [
                item for item in payload[0]
                if isinstance(item, list) and len(item) >= 4 and isinstance(item[1], str) and len(item[1].strip().split()) >= 2
            ]
            if sample:
                job_array = payload[0]

        if len(payload) > 2 and isinstance(payload[2], int) and payload[2] > 0:
            total_available = payload[2]
        elif len(payload) > 1 and isinstance(payload[1], int) and payload[1] > 0:
            total_available = payload[1]

        if not job_array:
            continue

        for item in job_array:
            if not isinstance(item, list) or len(item) < 3:
                continue

            raw_id = item[0] if len(item) > 0 and item[0] is not None else None
            raw_title = item[1] if len(item) > 1 and item[1] is not None else None

            if not raw_title or not isinstance(raw_title, str) or len(raw_title.strip()) < 3:
                continue
            title = raw_title.strip()

            # Ensure title is not just a configuration key or noise word
            if title.lower() in NON_JOB_TITLES or any(nw == title.lower() for nw in NOISE_WORDS):
                continue
            if len(title.split()) < 2 and not any(kw in title.lower() for kw in TECH_ROLE_KEYWORDS):
                continue

            job_id = str(raw_id).strip() if raw_id is not None else re.sub(r"[^a-zA-Z0-9]", "", title.lower())[:20]

            # Application URL
            app_url = ""
            if len(item) > 2 and isinstance(item[2], str) and item[2].startswith("http") and "signin" not in item[2]:
                app_url = item[2]
            else:
                base_clean = base_url.split("?")[0].rstrip("/")
                app_url = f"{base_clean}/{job_id}"

            clean_url = normalize_url(app_url)
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            # Location extraction
            location = "Remote"
            if len(item) > 9 and isinstance(item[9], list) and item[9]:
                first_loc = item[9][0]
                if isinstance(first_loc, list) and first_loc and isinstance(first_loc[0], str):
                    location = first_loc[0].strip()
                elif isinstance(first_loc, str):
                    location = first_loc.strip()

            # Description / Qualifications / Responsibilities
            desc_parts = []
            if len(item) > 10 and isinstance(item[10], list) and len(item[10]) > 1 and isinstance(item[10][1], str):
                desc_parts.append(item[10][1])
            if len(item) > 4 and isinstance(item[4], list) and len(item[4]) > 1 and isinstance(item[4][1], str):
                desc_parts.append(item[4][1])
            if len(item) > 3 and isinstance(item[3], list) and len(item[3]) > 1 and isinstance(item[3][1], str):
                desc_parts.append(item[3][1])

            desc_raw = " ".join(desc_parts) if desc_parts else title
            desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
            desc_clean = " ".join(desc_clean.split())[:1500]

            extracted_comp = company_name
            if len(item) > 7 and isinstance(item[7], str) and item[7].strip():
                extracted_comp = item[7].strip()
            elif not extracted_comp:
                extracted_comp = "Google"

            norm_job = create_normalized_job(
                source="first_party",
                source_job_id=job_id,
                company=extracted_comp,
                title=title,
                location=location,
                employment_type="Full-time",
                description=desc_clean or title,
                application_url=clean_url,
                discovery_lane="targeted"
            )
            jobs.append(norm_job)

    if total_available is None and jobs:
        total_available = len(jobs)

    return jobs, total_available


# ---------------------------------------------------------------------------
# 3c. Generic HTML DOM Job-Card Extraction
# ---------------------------------------------------------------------------

NON_JOB_URL_SUBSTRINGS = {
    "/recommendations", "/saved", "/alerts", "/signin", "/signup", "/login",
    "/eeo", "/privacy", "/terms", "/legal", "/cookie", "/help", "/about",
    "/contact", ".pdf", "/jobs/dist/legal", "/jobs/results/jobs/"
}

NON_JOB_TITLES = {
    "jobs", "jobs jobs", "work_outline work_outline jobs jobs", "recommended jobs",
    "saved jobs", "job alerts", "job search", "search jobs", "view all jobs",
    "all jobs", "careers", "google's eeo policy", "eeo policy", "equal opportunity",
    "know your rights: workplace discrimination is illegal",
    "workplace discrimination is illegal", "privacy policy", "terms of service",
    "sign in", "log in", "my applications", "join our talent network"
}

def extract_jobs_from_html(
    html: str,
    base_url: str,
    company_name: str
) -> List[Dict[str, Any]]:
    """
    Extracts jobs from HTML by detecting job card containers and candidate job links.
    Filters out noise, navigation links, and generic non-job URLs.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict[str, Any]] = []
    seen_urls = set()

    # 1. Structured Job Card Containers
    card_selectors = [
        ".job-card", ".job-listing", ".job-item", ".job-row",
        ".career-item", ".posting-card", ".opening-card",
        "[data-job-id]", "[data-req-id]", ".search-result-item",
        "li.jobs-list-item", "article.job", ".jobs-table-row",
        ".job_listing", ".position-item", ".vacancies-item"
    ]
    card_elements = []
    for sel in card_selectors:
        matches = soup.select(sel)
        if matches and len(matches) < 200:
            card_elements.extend(matches)

    for card in card_elements:
        a_tag = card.find("a", href=True)
        if not a_tag:
            continue

        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        full_url = urljoin(base_url, href)
        clean_url = normalize_url(full_url)
        if clean_url in seen_urls:
            continue

        # Check non-job url patterns
        if any(bad in clean_url.lower() for bad in NON_JOB_URL_SUBSTRINGS):
            continue

        title = a_tag.get_text(separator=" ").strip()
        if not title or len(title) < 4:
            continue

        if title.lower() in NON_JOB_TITLES or any(nw == title.lower() for nw in NOISE_WORDS):
            continue

        card_text = card.get_text(separator=" ").strip()
        location = "Remote"
        loc_match = re.search(r"(?:Location|City|Office):\s*([^|\n,•]{2,40})", card_text, re.I)
        if loc_match:
            location = loc_match.group(1).strip()
        elif any(w in card_text.lower() for w in ["remote", "work from home", "wfh", "anywhere"]):
            location = "Remote"
        elif "india" in card_text.lower():
            location = "India"

        # Job ID
        id_match = re.search(r"/(?:jobs|job|posting|positions?|results)/(\d{4,12})(?:[\-_/]|\.html|\?|$)|/(\d{4,12})(?:[\-_/]|\.html|\?|$)|_(\d{4,12})|id=([a-zA-Z0-9_\-]+)", full_url, re.I)
        job_id = id_match.group(1) or id_match.group(2) or id_match.group(3) or id_match.group(4) if id_match else None
        if not job_id:
            job_id = re.sub(r"[^a-zA-Z0-9]", "", title.lower())[:20]

        seen_urls.add(clean_url)
        norm_job = create_normalized_job(
            source="first_party",
            source_job_id=job_id,
            company=company_name,
            title=title,
            location=location,
            employment_type="Full-time",
            description=card_text[:500] if len(card_text) > len(title) else title,
            application_url=clean_url,
            discovery_lane="targeted"
        )
        jobs.append(norm_job)

    # 2. Standalone job link scan if card detection yielded few/no jobs
    if len(jobs) < 3:
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            full_url = urljoin(base_url, href)
            clean_url = normalize_url(full_url)
            if clean_url in seen_urls:
                continue

            if any(bad in clean_url.lower() for bad in NON_JOB_URL_SUBSTRINGS):
                continue

            # Must match a known job link pattern
            is_job_pattern = any(re.search(pat, href, re.I) for pat in JOB_LINK_PATTERNS)
            if not is_job_pattern:
                continue

            text = a_tag.get_text(separator=" ").strip()
            words = text.split()
            if len(words) < 2 or len(words) > 16:
                continue

            text_lower = text.lower()
            if text_lower in NON_JOB_TITLES or any(nw == text_lower for nw in NOISE_WORDS):
                continue

            # If URL is just /jobs/results or /jobs/results/ without an ID, skip
            if re.search(r"/jobs/results/?$", href.lower()):
                continue

            seen_urls.add(clean_url)
            id_match = re.search(r"/(?:jobs|job|posting|positions?|results)/(\d{4,12})(?:[\-_/]|\.html|\?|$)|/(\d{4,12})(?:[\-_/]|\.html|\?|$)|_(\d{4,12})|/([a-zA-Z0-9_\-]{6,})(?:/|\.html|\?|$)", full_url, re.I)
            job_id = id_match.group(1) or id_match.group(2) or id_match.group(3) or id_match.group(4) if id_match else None
            if not job_id:
                job_id = re.sub(r"[^a-zA-Z0-9]", "", text.lower())[:20]

            norm_job = create_normalized_job(
                source="first_party",
                source_job_id=job_id,
                company=company_name,
                title=text,
                location="Remote",
                employment_type="Full-time",
                description=text,
                application_url=clean_url,
                discovery_lane="targeted"
            )
            jobs.append(norm_job)

    return jobs


# ---------------------------------------------------------------------------
# 4. Generic First-Party REST Probe Registry (Eightfold/PCSX, Amazon, REST)
# ---------------------------------------------------------------------------

def _derive_root_domain(netloc: str) -> str:
    """Derives root domain from netloc (e.g. apply.careers.microsoft.com -> microsoft.com)."""
    parts = netloc.split(":")[0].split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return netloc


def probe_first_party_api_or_search(
    careers_url: str,
    company_name: str,
    search_config: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Probes generic first-party career-platform REST search endpoints (Eightfold / PCSX,
    Amazon Jobs REST, generic /api/jobs) and returns extracted jobs and available count.
    
    Returns:
        (List[normalized_jobs], jobs_available)
    """
    if not careers_url:
        return [], None

    parsed_url = urlparse(careers_url)
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    domain = _derive_root_domain(parsed_url.netloc)

    search_cfg = search_config or {}
    pref_roles = search_cfg.get("preferred_roles", ["Software Engineer", "Intern"])
    pref_locs = search_cfg.get("locations", [])
    query_str = pref_roles[0] if pref_roles else "Software Engineer"
    loc_str = pref_locs[0] if pref_locs and pref_locs[0].lower() not in ["remote", "hybrid", "onsite"] else ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    max_jobs_to_retrieve = int(os.getenv("FIRST_PARTY_MAX_JOBS", 50))
    accumulated_jobs: List[Dict[str, Any]] = []
    total_available_reported: Optional[int] = None
    seen_urls = set()

    # Candidate Probe Families
    candidate_probes = []

    # 1. Google Careers & First-Party Query / WIZ Search Family
    if "google.com" in origin.lower() or "google" in company_name.lower() or "jobs/results" in careers_url:
        google_url = careers_url if "jobs/results" in careers_url else f"{origin}/about/careers/applications/jobs/results/"
        candidate_probes.append({
            "family": "google_wiz",
            "url": google_url,
            "params": {
                "q": query_str,
                "location": loc_str,
                "page": 1
            }
        })

    # 2. Amazon Jobs REST Search Family
    if "amazon.jobs" in origin.lower() or "amazon" in company_name.lower():
        candidate_probes.append({
            "family": "amazon",
            "url": f"{origin}/en/search.json",
            "params": {
                "base_query": query_str,
                "country": "IND" if "india" in loc_str.lower() or "india" in company_name.lower() else "",
                "offset": 0,
                "result_limit": 20
            }
        })
        candidate_probes.append({
            "family": "amazon",
            "url": f"{origin}/search.json",
            "params": {
                "base_query": query_str,
                "offset": 0,
                "result_limit": 20
            }
        })

    # 3. Eightfold / PCSX Platform Search Family
    if "google.com" not in origin.lower() and "amazon" not in origin.lower():
        pcsx_urls = [
            f"{origin}/api/pcsx/search",
            f"https://apply.careers.{domain}/api/pcsx/search" if domain else None,
            f"https://apply.{domain}/api/pcsx/search" if domain else None
        ]
        for u in pcsx_urls:
            if u and u not in [p["url"] for p in candidate_probes]:
                candidate_probes.append({
                    "family": "pcsx",
                    "url": u,
                    "params": {
                        "domain": domain or parsed_url.netloc,
                        "query": query_str,
                        "location": loc_str,
                        "start": 0,
                        "num": 20
                    }
                })

    # 4. Generic REST Platform Search Family
    generic_paths = [
        "/api/search/jobs",
        "/search/jobs/api",
        "/api/jobs",
        "/api/v1/jobs",
        "/api/v2/jobs",
        "/jobs/search",
        "/careers/api/jobs",
        "/jobs/api/search",
        "/search.json"
    ]
    for path in generic_paths:
        candidate_probes.append({
            "family": "generic",
            "url": f"{origin}{path}",
            "params": {
                "query": query_str,
                "location": loc_str,
                "limit": 20
            }
        })

    for probe in candidate_probes:
        ep_url = probe["url"]
        params = probe["params"]
        family = probe["family"]

        try:
            resp = requests.get(ep_url, headers=headers, params=params, timeout=6)
            if resp.status_code != 200:
                continue

            extracted = []
            total_cnt = None

            # Check if this is an AF_initDataCallback response (Google/WIZ style)
            if "AF_initDataCallback" in resp.text:
                extracted, total_cnt = extract_jobs_from_af_init_data(resp.text, company_name, ep_url)
            else:
                # Ensure response has JSON content
                ct = resp.headers.get("Content-Type", "").lower()
                if "json" not in ct and not resp.text.strip().startswith(("{", "[")):
                    continue

                try:
                    payload = resp.json()
                    extracted, total_cnt = extract_jobs_from_json_payload(payload, company_name, ep_url)
                except Exception:
                    continue

            if not extracted:
                # HTTP 200 with empty jobs does NOT verify the source
                continue

            # Found valid job payload!
            if total_cnt is not None:
                total_available_reported = total_cnt

            for j in extracted:
                if j["application_url"] not in seen_urls:
                    seen_urls.add(j["application_url"])
                    accumulated_jobs.append(j)

            # Handle pagination for multi-page retrieval up to max_jobs_to_retrieve
            if len(accumulated_jobs) < max_jobs_to_retrieve and total_cnt and total_cnt > len(accumulated_jobs):
                for page_idx in range(1, 4):
                    if len(accumulated_jobs) >= max_jobs_to_retrieve:
                        break
                    p_params = dict(params)
                    if family == "pcsx":
                        p_params["start"] = len(accumulated_jobs)
                    elif family == "amazon":
                        p_params["offset"] = len(accumulated_jobs)
                    elif family == "google_wiz":
                        p_params["page"] = page_idx + 1
                    else:
                        p_params["page"] = page_idx + 1
                        p_params["offset"] = len(accumulated_jobs)

                    try:
                        p_resp = requests.get(ep_url, headers=headers, params=p_params, timeout=6)
                        if p_resp.status_code == 200:
                            if isinstance(p_resp.text, str) and "AF_initDataCallback" in p_resp.text:
                                p_extracted, _ = extract_jobs_from_af_init_data(p_resp.text, company_name, ep_url)
                            else:
                                p_extracted, _ = extract_jobs_from_json_payload(p_resp.json(), company_name, ep_url)
                            for pj in p_extracted:
                                if pj["application_url"] not in seen_urls and len(accumulated_jobs) < max_jobs_to_retrieve:
                                    seen_urls.add(pj["application_url"])
                                    accumulated_jobs.append(pj)
                    except Exception:
                        pass

            if accumulated_jobs:
                break
        except Exception as e:
            logger.debug(f"[FIRST PARTY] Probe error for {ep_url}: {e}")

    avail_ret = total_available_reported if total_available_reported is not None else (len(accumulated_jobs) if accumulated_jobs else None)
    return accumulated_jobs, avail_ret


# ---------------------------------------------------------------------------
# 5. Playwright Headless Browser First-Party Discovery with XHR Interception
# ---------------------------------------------------------------------------

def discover_first_party_with_browser(
    company_config: Dict[str, Any],
    search_config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Loads official careers page in Playwright headless Chromium (using domcontentloaded),
    intercepts dynamic XHR/fetch JSON responses containing job payloads, interacts with search
    and location inputs if available, and extracts real job listings.
    
    Returns:
        (List[normalized_jobs], total_available_count)
    """
    import sources.browser_careers as bc_mod

    def log_progress(msg: str):
        logger.info(f"[FIRST PARTY BROWSER] {msg}")
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    careers_url = company_config.get("careers_url")
    company_name = company_config.get("company", "Generic Company")

    if not careers_url:
        return [], None

    playwright_runner = getattr(bc_mod, "sync_playwright", None) or sync_playwright

    if playwright_runner is None:
        log_progress("Playwright package is not installed. Skipping browser discovery.")
        return [], None

    browser_timeout = int(os.getenv("BROWSER_DISCOVERY_TIMEOUT", 15000))
    max_pages = int(os.getenv("BROWSER_DISCOVERY_MAX_PAGES", 3))
    max_jobs = int(os.getenv("BROWSER_DISCOVERY_MAX_JOBS", 100))

    search_cfg = search_config or {}
    pref_roles = search_cfg.get("preferred_roles", [])
    pref_locs = search_cfg.get("locations", [])
    search_queries = pref_roles[:max_pages] if pref_roles else [""]

    normalized_jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    total_available: Optional[int] = None
    discovered_api_candidates = []

    log_progress(f"Starting browser discovery for {company_name} at {careers_url}...")

    try:
        with playwright_runner() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            page.set_default_timeout(browser_timeout)

            # Response listener for XHR / fetch JSON interception
            def handle_network_response(response):
                nonlocal total_available
                try:
                    req = response.request
                    res_url = response.url if isinstance(response.url, str) else str(getattr(response, "url", ""))
                    r_type_val = getattr(req, "resource_type", "")
                    res_type = r_type_val() if callable(r_type_val) else str(r_type_val).lower()
                    r_meth_val = getattr(req, "method", "GET")
                    req_method = r_meth_val() if callable(r_meth_val) else str(r_meth_val)

                    if res_type in ("xhr", "fetch") or any(kw in res_url.lower() for kw in ["api", "search", "job", "graphql", "pcsx"]):
                        hdrs = response.headers() if callable(getattr(response, "headers", None)) else getattr(response, "headers", {})
                        ct = hdrs.get("content-type", "").lower() if isinstance(hdrs, dict) else ""
                        if "json" in ct or "text" in ct or not ct:
                            try:
                                payload = response.json() if callable(getattr(response, "json", None)) else json.loads(response.text())
                                extracted, total_cnt = extract_jobs_from_json_payload(payload, company_name, res_url)
                                if extracted:
                                    if total_cnt and total_available is None:
                                        total_available = total_cnt
                                    for ej in extracted:
                                        if ej["application_url"] not in seen_urls and len(normalized_jobs) < max_jobs:
                                            seen_urls.add(ej["application_url"])
                                            normalized_jobs.append(ej)
                                    discovered_api_candidates.append((res_url, req_method))
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", handle_network_response)

            # Navigate using domcontentloaded to prevent hanging on analytics/telemetry
            try:
                response = page.goto(careers_url, wait_until="domcontentloaded", timeout=browser_timeout)
                if response and response.status_code in (403, 429):
                    raise AccessRestrictedError(f"HTTP {response.status_code} Access Restricted.")
            except Exception as e:
                if "AccessRestrictedError" in str(type(e)):
                    raise
                logger.debug(f"[FIRST PARTY BROWSER] Goto warning: {e}")

            # Give page 3 seconds to initiate background XHRs
            page.wait_for_timeout(3000)

            # Immediate security challenge detection
            title_text = page.title() if callable(page.title) else str(page.title)
            content_text = page.content() if callable(page.content) else str(page.content)
            check_page_for_challenges(title_text, content_text)

            for query in search_queries:
                if stop_checker and stop_checker():
                    log_progress("Stop requested. Halting browser loop.")
                    break

                if len(normalized_jobs) >= max_jobs:
                    break

                # Search interaction if query provided
                if query:
                    log_progress(f"Searching career portal for '{query}'...")
                    try:
                        search_input = page.query_selector(
                            "input[type='text'], input[type='search'], "
                            "input[placeholder*='search' i], input[placeholder*='job' i], "
                            "input[placeholder*='role' i], input[placeholder*='title' i], "
                            "input[id*='search' i], input[class*='search' i], input[name*='q' i], "
                            "input[name*='search' i]"
                        )
                        if search_input:
                            search_input.click()
                            search_input.fill("")
                            search_input.type(query)

                            # Location input check
                            if pref_locs:
                                loc_input = page.query_selector(
                                    "input[placeholder*='location' i], input[placeholder*='city' i], "
                                    "input[id*='location' i], input[class*='location' i], input[name*='location' i]"
                                )
                                if loc_input:
                                    loc_target = pref_locs[0]
                                    if loc_target.lower() not in ["remote", "hybrid", "onsite"]:
                                        loc_input.click()
                                        loc_input.fill("")
                                        loc_input.type(loc_target)

                            search_input.press("Enter")
                            page.wait_for_timeout(3000)
                            t_curr = page.title() if callable(page.title) else str(page.title)
                            c_curr = page.content() if callable(page.content) else str(page.content)
                            check_page_for_challenges(t_curr, c_curr)
                    except AccessRestrictedError:
                        raise
                    except Exception as e:
                        logger.debug(f"[FIRST PARTY BROWSER] Search input interaction error: {e}")

                # Extract from current DOM content if XHR did not find enough jobs
                current_html = page.content() if callable(page.content) else str(page.content)
                current_url = page.url if isinstance(page.url, str) else careers_url

                # A. Google / WIZ AF_initData Extraction
                if "AF_initDataCallback" in current_html:
                    af_jobs, af_total = extract_jobs_from_af_init_data(current_html, company_name, current_url)
                    if af_jobs:
                        if af_total and total_available is None:
                            total_available = af_total
                        for j in af_jobs:
                            if j["application_url"] not in seen_urls and len(normalized_jobs) < max_jobs:
                                seen_urls.add(j["application_url"])
                                normalized_jobs.append(j)

                # B. JSON-LD Extraction
                if len(normalized_jobs) < 3:
                    json_ld_jobs = extract_jobs_from_json_ld(current_html, current_url, company_name)
                    for j in json_ld_jobs:
                        if j["application_url"] not in seen_urls and len(normalized_jobs) < max_jobs:
                            seen_urls.add(j["application_url"])
                            normalized_jobs.append(j)

                # C. HTML DOM Extraction
                if len(normalized_jobs) < 3:
                    html_jobs = extract_jobs_from_html(current_html, current_url, company_name)
                    for j in html_jobs:
                        if j["application_url"] not in seen_urls and len(normalized_jobs) < max_jobs:
                            seen_urls.add(j["application_url"])
                            normalized_jobs.append(j)

                # C. Standalone Link evaluation if DOM heuristic yielded 0
                if len(normalized_jobs) == 0:
                    try:
                        links = page.query_selector_all("a") or []
                        for link in links:
                            href = link.get_attribute("href") if hasattr(link, "get_attribute") else None
                            if not href or href.startswith("#") or href.startswith("javascript:"):
                                continue
                            try:
                                job_url = page.evaluate(f"new URL('{href}', window.location.href).href")
                            except Exception:
                                job_url = urljoin(current_url, href)
                            text = (link.inner_text() if hasattr(link, "inner_text") else "") or ""
                            if len(text.split()) >= 2 and any(kw in href.lower() for kw in ["/job", "/career", "/posting"]):
                                clean_u = normalize_url(job_url)
                                if clean_u not in seen_urls:
                                    seen_urls.add(clean_u)
                                    norm_job = create_normalized_job(
                                        source="first_party",
                                        source_job_id=re.sub(r"[^a-zA-Z0-9]", "", text.lower())[:20],
                                        company=company_name,
                                        title=text.strip(),
                                        location="Remote",
                                        employment_type="Full-time",
                                        description=text.strip(),
                                        application_url=clean_u,
                                        discovery_lane="targeted"
                                    )
                                    normalized_jobs.append(norm_job)
                    except Exception as e:
                        logger.debug(f"[FIRST PARTY BROWSER] Link fallback error: {e}")

            browser.close()

    except AccessRestrictedError:
        raise
    except Exception as e:
        log_progress(f"Browser discovery error: {e}")

    avail = total_available if total_available is not None else len(normalized_jobs)
    log_progress(f"First-party browser discovery retrieved {len(normalized_jobs)} jobs (available: {avail}).")
    return normalized_jobs, avail


# ---------------------------------------------------------------------------
# 6. Public Unified Entry Points
# ---------------------------------------------------------------------------

def discover_jobs_from_first_party(
    company_config: Dict[str, Any],
    search_config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None
) -> List[Dict[str, Any]]:
    """
    Executes first-party job discovery for a single company:
    1. Generic First-Party REST API probes (Eightfold/PCSX, Amazon REST, generic /api/jobs).
    2. Static HTTP fetch -> JSON-LD & DOM extraction.
    3. Headless browser (Playwright) dynamic fallback with XHR JSON interception.
    """
    def log_progress(msg: str):
        logger.info(f"[FIRST PARTY] {msg}")
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    careers_url = company_config.get("careers_url")
    company_name = company_config.get("company", "Generic Company")
    if not careers_url:
        return []

    log_progress(f"Discovering first-party jobs for {company_name}...")

    # Phase 1: Generic First-Party REST API Probing
    try:
        api_jobs, total_avail = probe_first_party_api_or_search(careers_url, company_name, search_config=search_config)
        if api_jobs:
            log_progress(f"Found {len(api_jobs)} jobs via first-party REST probe (total available: {total_avail or len(api_jobs)}).")
            return api_jobs
    except Exception as e:
        logger.debug(f"[FIRST PARTY] API probe error: {e}")

    # Phase 2: Static HTTP fetch -> JSON-LD & DOM extraction
    jobs = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(careers_url, headers=headers, timeout=8, allow_redirects=True)
        if resp.status_code in (403, 429):
            raise AccessRestrictedError(f"HTTP {resp.status_code} Access Restricted.")

        # Check challenges with refined challenge detector
        soup = BeautifulSoup(resp.text, "html.parser")
        title_text = soup.title.string.strip() if soup.title and soup.title.string else ""
        check_page_for_challenges(title_text, resp.text)

        if resp.status_code == 200 and resp.text:
            # Try AF_initDataCallback
            if "AF_initDataCallback" in resp.text:
                af_jobs, af_total = extract_jobs_from_af_init_data(resp.text, company_name, resp.url or careers_url)
                if af_jobs:
                    jobs.extend(af_jobs)

            # Try JSON-LD
            if len(jobs) < 3:
                ld_jobs = extract_jobs_from_json_ld(resp.text, resp.url or careers_url, company_name)
                jobs.extend(ld_jobs)

            # Try HTML job cards
            if len(jobs) < 3:
                dom_jobs = extract_jobs_from_html(resp.text, resp.url or careers_url, company_name)
                seen = {j["application_url"] for j in jobs}
                for dj in dom_jobs:
                    if dj["application_url"] not in seen:
                        seen.add(dj["application_url"])
                        jobs.append(dj)

        if jobs:
            log_progress(f"Found {len(jobs)} jobs via static first-party inspection.")
            return jobs

    except AccessRestrictedError:
        raise
    except Exception as e:
        logger.debug(f"[FIRST PARTY] Static fetch exception: {e}")

    # Phase 3: Headless Browser Fallback with XHR Interception
    if stop_checker and stop_checker():
        return jobs

    try:
        browser_jobs, total_avail = discover_first_party_with_browser(
            company_config,
            search_config,
            progress_callback=progress_callback,
            stop_checker=stop_checker
        )
        return browser_jobs
    except AccessRestrictedError:
        raise
    except Exception as e:
        logger.warning(f"[FIRST PARTY] Browser discovery failed for {company_name}: {e}")
        return []


def discover_jobs(
    search_config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    stop_checker: Optional[Callable[[], bool]] = None
) -> List[Dict[str, Any]]:
    """
    Standard sources registry interface for first_party source.
    Loads all enabled first_party companies from config/companies.json and retrieves jobs.
    """
    import company_manager

    all_jobs = []
    companies = company_manager.load_companies()
    first_party_companies = [
        c for c in companies
        if c.get("enabled", True)
        and (c.get("source") == "first_party" or c.get("source_type") == "first_party")
    ]

    for comp in first_party_companies:
        if stop_checker and stop_checker():
            break

        c_name = comp.get("company", "Company")
        priority = comp.get("priority", 100)
        try:
            comp_jobs = discover_jobs_from_first_party(
                comp,
                search_config=search_config,
                progress_callback=progress_callback,
                stop_checker=stop_checker
            )
            for j in comp_jobs:
                j["discovery_lane"] = "targeted"
                j["company_priority"] = priority
            all_jobs.extend(comp_jobs)
        except Exception as e:
            logger.error(f"[FIRST PARTY] Discovery failed for {c_name}: {e}")

    return all_jobs
