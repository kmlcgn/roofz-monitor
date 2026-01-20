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
        page = browser.new_page()
        
        def handle_response(response):
            if "/api/properties" in response.url:
                try:
                    data = response.json()
                    api_data.append(data)
                    log(f"Intercepted API: {len(data.get('data', []))} listings")
                except:
                    pass
        
        page.on("response", handle_response)
        
        page.goto("https://roofz.eu/availability", timeout=60000)
        page.wait_for_timeout(5000)
        
        # Get HTML before closing browser
        html = page.content()
        
        browser.close()
    
    # Use intercepted API data if available
    for data in api_data:
        for item in data.get("data", []):
            lid = item.get("id")
            if lid:
                listings[lid] = {"id": lid}
    
    # Fallback: parse HTML if no API data
    if not listings:
        log("No API data, parsing HTML")
        listing_ids = set(re.findall(r'/listing/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', html))
        listings = {lid: {"id": lid} for lid in listing_ids}
    
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
