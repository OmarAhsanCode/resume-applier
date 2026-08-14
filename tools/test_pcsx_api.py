import requests
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

url = "https://apply.careers.microsoft.com/api/pcsx/search"
params = {
    "domain": "microsoft.com",
    "query": "Software Engineer",
    "location": "India",
    "start": 0,
    "num": 20
}

r = requests.get(url, headers=headers, params=params, timeout=10)
print(f"Status Code: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type')}")

if r.status_code == 200:
    data = r.json().get("data", {})
    total = data.get("total_positions") or data.get("count") or data.get("total")
    positions = data.get("positions", [])
    print(f"Total positions in search: {total}")
    print(f"Retrieved positions on page: {len(positions)}")
    
    for idx, pos in enumerate(positions[:5], 1):
        pid = pos.get("id")
        job_id = pos.get("displayJobId")
        title = pos.get("name")
        locations = pos.get("locations", [])
        posted = pos.get("posted_ts")
        url_link = f"https://apply.careers.microsoft.com/careers/job/{pid}"
        print(f"\n[{idx}] {title}")
        print(f"    Job ID: {job_id} (Internal ID: {pid})")
        print(f"    Locations: {locations}")
        print(f"    Posted: {posted}")
        print(f"    Application URL: {url_link}")
        
    if positions:
        print("\nFull JSON Keys for position object:")
        print(list(positions[0].keys()))
