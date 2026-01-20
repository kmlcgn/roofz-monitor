import requests
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime

PAGE_URL = "https://roofz.eu/availability"
STATE_FILE = "/tmp/roofz_listings.json"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 30))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    resp = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    
    # Extract listing IDs from the HTML (they appear as /listing/UUID links)
    listing_ids = set(re.findall(r'/listing/([a-f0-9-]{36})', html))
    
    # Try to extract listing details from __NUXT__ state
    listings = {}
    for lid in listing_ids:
        listings[lid] = {"id": lid}
    
    # Try to get more details from the page
    # Match title patterns near listing IDs
    for lid in listing_ids:
        # Look for title in nearby content
        title_match = re.search(rf'title["\s:]+([^"<>]+)["\s<].*?{lid}|{lid}.*?title["\s:]+([^"<>]+)', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            listings[lid]["title"] = title_match.group(1) or title_match.group(2)
    
    return listings


def send_email(new_listings):
    body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid, info in new_listings.items():
        title = info.get("title", "New Property")
        body += f"* {title}\n"
        body += f"  https://roofz.eu/listing/{lid}\n\n"
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
        log(f"Email sent for {len(new_listings)} new listing(s)")
    else:
        log(f"Email failed: {resp.text}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    state_path = Path(STATE_FILE)

    log(f"Found {len(current_ids)} listings on page")

    previous_ids = set()
    if state_path.exists():
        previous_ids = set(json.loads(state_path.read_text()))

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids:
        log(f"NEW LISTINGS: {len(new_ids)}")
        new_listings = {lid: current[lid] for lid in new_ids}
        send_email(new_listings)
    elif not previous_ids:
        log(f"First run - now tracking {len(current_ids)} listings")
    else:
        log(f"No new listings")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (checking every {CHECK_INTERVAL}s)")
    log(f"Scraping: {PAGE_URL}")
    while True:
        try:
            check_for_new()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
