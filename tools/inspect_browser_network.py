import json
import time
from playwright.sync_api import sync_playwright

def inspect_network(url):
    print(f"Launching Playwright Network Inspector on: {url}")
    captured = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()

        def on_response(response):
            try:
                req = response.request
                r_url = response.url
                r_type = req.resource_type
                r_status = response.status
                ct = response.headers.get("content-type", "")
                
                # Check if xhr/fetch or relevant
                if r_type in ("xhr", "fetch") or any(kw in r_url.lower() for kw in ["api", "job", "search", "graphql", "query"]):
                    entry = {
                        "url": r_url,
                        "method": req.method,
                        "status": r_status,
                        "resource_type": r_type,
                        "content_type": ct,
                        "headers": req.headers,
                    }
                    if "json" in ct or "text" in ct:
                        try:
                            txt = response.text()
                            entry["body_preview"] = txt[:300]
                            entry["body_len"] = len(txt)
                            if any(k in txt.lower() for k in ["jobtitle", "job_title", "positiontitle", "jobid", "totalcount", "jobposting", "total_jobs"]):
                                entry["has_job_keywords"] = True
                                print(f"\n[JOB DATA DETECTED IN XHR] -> {req.method} {r_url} (Status: {r_status})")
                                print(f"  Preview: {txt[:250]}")
                        except Exception:
                            pass
                    captured.append(entry)
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Navigating to {url}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"Goto warning: {e}")

        page.wait_for_timeout(6000)

        print(f"Page Title: '{page.title()}'")
        print(f"Current URL: '{page.url}'")

        # Try to find search input and type query
        try:
            inputs = page.query_selector_all("input")
            print(f"Found {len(inputs)} input fields.")
            for inp in inputs:
                p_holder = inp.get_attribute("placeholder") or ""
                p_type = inp.get_attribute("type") or ""
                p_name = inp.get_attribute("name") or ""
                print(f"  Input: type='{p_type}', placeholder='{p_holder}', name='{p_name}'")
                if any(w in p_holder.lower() for w in ["search", "job", "title", "keyword", "role"]) or p_type == "search" or "search" in p_name.lower():
                    print(f"  -> Typing 'Software Engineer' into input...")
                    inp.click()
                    inp.fill("Software Engineer")
                    inp.press("Enter")
                    page.wait_for_timeout(6000)
                    break
        except Exception as e:
            print(f"Search input interaction error: {e}")

        # Check DOM job links
        links = page.query_selector_all("a")
        print(f"Found {len(links)} <a> links in rendered DOM.")
        job_links = []
        for l in links:
            href = l.get_attribute("href") or ""
            txt = l.inner_text() or ""
            if any(k in href.lower() for k in ["/job/", "/jobs/", "/position/", "/posting/"]) and len(txt.strip().split()) >= 2:
                job_links.append((txt.strip(), href))

        print(f"DOM Job Links matching heuristic: {len(job_links)}")
        for t, h in job_links[:5]:
            print(f"  - {t} -> {h}")

        browser.close()

    print(f"\nTotal Captured XHR/Fetch: {len(captured)}")
    print("Listing All Captured XHR/Fetch Requests:")
    for idx, c in enumerate(captured, 1):
        print(f"[{idx}] {c['method']} {c['url']} -> {c['status']} ({c['content_type']}) [{c.get('body_len', 0)} bytes]")

if __name__ == "__main__":
    inspect_network("https://apply.careers.microsoft.com/careers")
