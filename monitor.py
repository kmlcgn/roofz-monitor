import requests
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime

PAGE_URL = "https://roofz.eu/availability"
API_URL = "https://roofz.eu/api/properties"
STATE_FILE = "/tmp/roofz_listings.json"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 30))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://roofz.eu/availability",
    "Origin": "https://roofz.eu",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    session = requests.Session()
    
    # First visit the page to get cookies
    session.get(PAGE_URL, headers={
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }, timeout=30)
    
    # Now try the API with the session cookies
    params = {
        "filter[status]": "available",
        "sort": "-created_at",
        "page[number]": 1,
        "page[size]": 100,
    }
    
    resp = session.get(API_URL, headers=HEADERS, params=params, timeout=30)
    
    listings = {}
    
    # Check if we got JSON
    try:
        data = resp.json()
        for item in data.get("data", []):
            lid = item["id"]
            attrs = item.get("attributes", {})
            listings[lid] = {
                "title": attrs.get("title", ""),
                "price": attrs.get("price", 0),
                "city": attrs.get("city", ""),
                "bedrooms": attrs.get("bedrooms", 0),
                "surface": attrs.get("surface", 0),
            }
        log(f"API returned {len(listings)} listings")
    except:
        # API blocked, try parsing HTML for listing IDs
        log("API blocked, falling back to HTML parsing")
        html = session.get(PAGE_URL, headers=HEADERS, timeout=30).text
        
        # Look for listing UUIDs in href attributes
        listing_ids = set(re.findall(r'href="[^"]*?/listing/([a-f0-9-]{36})"', html))
        
        if not listing_ids:
            # Try __NUXT__ state
            nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(.+?);</script>', html, re.DOTALL)
            if nuxt_match:
                listing_ids = set(re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', nuxt_match.group(1)))
        
        for lid in listing_ids:
            listings[lid] = {"id": lid, "title": "New listing"}
        
        log(f"HTML parsing found {len(listings)} listings")
    
    return listings


def send_email(new_listings):
    body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid, info in new_listings.items():
        title = info.get("title") or "New Property"
        price = info.get("price", "")
        city = info.get("city", "")
        
        body += f"* {title}"
        if price:
            body += f" - EUR {price}/mo"
        body += "\n"
        if city:
            body += f"  {city}\n"
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
        log(f"Email sent!")
    else:
        log(f"Email failed: {resp.text}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    state_path = Path(STATE_FILE)

    if not current_ids:
        log("WARNING: No listings found - site may be blocking requests")
        return

    previous_ids = set()
    if state_path.exists():
        previous_ids = set(json.loads(state_path.read_text()))

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids:
        log(f"NEW LISTINGS: {len(new_ids)}")
        new_listings = {lid: current[lid] for lid in new_ids}
        send_email(new_listings)
    elif not previous_ids:
        log(f"First run - tracking {len(current_ids)} listings")
    else:
        log(f"No new listings (tracking {len(current_ids)})")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (every {CHECK_INTERVAL}s)")
    while True:
        try:
            check_for_new()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
