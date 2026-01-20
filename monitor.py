import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
import requests

STATE_FILE = os.environ.get("STATE_FILE", "/app/roofz_listings.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 120))

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    from playwright.sync_api import sync_playwright
    
    listings = {}
    api_data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        def handle_response(response):
            url = response.url
            if "api" in url and "propert" in url.lower():
                log(f"API Response: {url[:80]}")
                try:
                    data = response.json()
                    if "data" in data:
                        api_data.append(data)
                        log(f"Got {len(data.get('data', []))} items from API")
                except:
                    pass
        
        page.on("response", handle_response)
        
        log("Loading page...")
        page.goto("https://roofz.eu/availability", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        
        html = page.content()
        
        # Find ALL UUIDs in the page
        all_uuids = set(re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', html))
        log(f"Total UUIDs found: {len(all_uuids)}")
        
        # Look for property-related content
        property_patterns = [
            r'"id":"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"',  # JSON id
            r'property[^>]*([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',  # property class/attr
            r'data-id="([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"',  # data-id
        ]
        
        for pattern in property_patterns:
            matches = set(re.findall(pattern, html))
            if matches:
                log(f"Pattern '{pattern[:30]}...' found {len(matches)} matches")
        
        # Check for __NUXT__ data
        nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(.+?);</script>', html, re.DOTALL)
        if nuxt_match:
            nuxt_data = nuxt_match.group(1)
            nuxt_uuids = set(re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', nuxt_data))
            log(f"UUIDs in __NUXT__: {len(nuxt_uuids)}")
            # Log a sample
            if nuxt_uuids:
                sample = list(nuxt_uuids)[:3]
                log(f"Sample UUIDs: {sample}")
        
        browser.close()
    
    # Use API data if available
    for data in api_data:
        for item in data.get("data", []):
            lid = item.get("id")
            if lid:
                listings[lid] = {"id": lid}
    
    # Use NUXT UUIDs as fallback (filter to reasonable count)
    if not listings and nuxt_match:
        nuxt_data = nuxt_match.group(1)
        # Look for IDs that appear near "available" or "property" context
        context_uuids = set(re.findall(r'"id":"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"', nuxt_data))
        log(f"Context UUIDs: {len(context_uuids)}")
        listings = {lid: {"id": lid} for lid in context_uuids}
    
    return listings


def send_email(new_listings):
    body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid in new_listings:
        body += f"* https://roofz.eu/listing/{lid}\n\n"
    body += "View all: https://roofz.eu/availability"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": "Roofz Monitor <onboarding@resend.dev>",
            "to": os.environ["EMAIL_TO"],
            "subject": f"Roofz: {len(new_listings)} New Listing(s)!",
            "text": body,
        },
    )
    if resp.status_code == 200:
        log("Email sent!")
    else:
        log(f"Email failed: {resp.text}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    state_path = Path(STATE_FILE)

    log(f"Found {len(current_ids)} listings")

    previous_ids = set()
    if state_path.exists():
        previous_ids = set(json.loads(state_path.read_text()))

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids and len(new_ids) <= 5:
        log(f"NEW LISTINGS: {len(new_ids)}")
        send_email(new_ids)
    elif new_ids and len(new_ids) > 5:
        log(f"Skipping alert - {len(new_ids)} 'new' (likely restart)")
    elif not previous_ids:
        log(f"First run - tracking {len(current_ids)} listings")
    else:
        log("No new listings")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (every {CHECK_INTERVAL}s)")
    errors = 0
    
    while True:
        try:
            check_for_new()
            errors = 0
        except Exception as e:
            errors += 1
            log(f"Error: {e}")
            if errors >= 3:
                wait = min(errors * 120, 600)
                log(f"Backing off {wait}s...")
                time.sleep(wait)
        
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
