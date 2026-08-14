import requests
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

url = "https://apply.careers.microsoft.com/careers"
r = requests.get(url, headers=headers, timeout=15)
print(f"URL: {r.url}")
print(f"Status: {r.status_code}")
print(f"Length: {len(r.text)}")

# Find all JSON / state variables
soup = BeautifulSoup(r.text, "html.parser")
scripts = soup.find_all("script")
print(f"Script tags: {len(scripts)}")

for idx, s in enumerate(scripts):
    txt = s.string or ""
    if "api" in txt.lower() or "job" in txt.lower() or "domain" in txt.lower():
        if len(txt) > 500:
            print(f"Script #{idx} (len {len(txt)}): preview -> {txt[:200]}")
            # Look for JSON configs
            json_matches = re.findall(r'window\.[a-zA-Z0-9_]+\s*=\s*(\{.*?\});', txt)
            for jm in json_matches:
                print(f"  Found window config object: {jm[:100]}...")

# Find all relative API links
api_links = set(re.findall(r'["\'](/api/[^"\']+)["\']', r.text))
print(f"\nAll /api/ strings in HTML ({len(api_links)}):")
for a in sorted(api_links):
    print(f"  - {a}")

# Let's test standard Eightfold API search endpoints for Microsoft
# e.g., /api/apply/v2/jobs?domain=microsoft.com or /api/pcs/jobs or /api/jobs
eightfold_test_urls = [
    "https://apply.careers.microsoft.com/api/apply/v2/jobs?domain=microsoft.com",
    "https://apply.careers.microsoft.com/api/apply/v2/jobs?domain=microsoft.com&query=Software%20Engineer",
    "https://apply.careers.microsoft.com/api/pcs/jobs?domain=microsoft.com",
    "https://apply.careers.microsoft.com/api/application/v2/location/options?domain=microsoft.com",
    "https://careers.microsoft.com/api/jobs/search?query=Software%20Engineer",
    "https://jobs.careers.microsoft.com/api/jobs/search?query=Software%20Engineer",
]

print("\n--- Testing Candidate Eightfold / Microsoft Endpoints ---")
for eu in eightfold_test_urls:
    try:
        er = requests.get(eu, headers=headers, timeout=10)
        print(f"Testing {eu} -> Status: {er.status_code}, Content-Type: {er.headers.get('Content-Type')}, Size: {len(er.text)}")
        if er.status_code == 200:
            try:
                ej = er.json()
                print(f"  ✓ JSON Keys: {list(ej.keys()) if isinstance(ej, dict) else 'List of ' + str(len(ej))}")
                if isinstance(ej, dict):
                    for k, v in ej.items():
                        if isinstance(v, list):
                            print(f"    Key '{k}' has {len(v)} items. Sample: {str(v[0])[:150] if v else 'empty'}")
                        elif isinstance(v, dict):
                            print(f"    Key '{k}' (dict): keys={list(v.keys())}")
                        elif isinstance(v, (int, str)):
                            print(f"    Key '{k}' = {v}")
            except Exception as e:
                print(f"  Response text snippet: {er.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")
