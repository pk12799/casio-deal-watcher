#!/usr/bin/env python3
"""
Casio Bhawar Store - Deep Discount Watcher
-------------------------------------------
Polls the public Shopify product feed for the /collections/watches
collection, computes the real discount (price vs compare_at_price) for
every variant, and pushes a phone notification via ntfy.sh the first
time a deal crosses DISCOUNT_THRESHOLD percent.

No third-party packages required - stdlib only, so it runs anywhere
Python 3 is installed (laptop, Raspberry Pi, GitHub Actions, etc).

Usage:
    python3 watch_alert.py           # run forever, checking on an interval
    python3 watch_alert.py --once    # check a single time and exit (for cron / GitHub Actions)
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ---------------- Config ----------------
COLLECTION_URL = "https://casiostore.bhawar.com/collections/watches/products.json"
DISCOUNT_THRESHOLD = 50          # percent - change if you want a different cutoff
CHECK_INTERVAL_SECONDS = 300     # 5 minutes, used only in loop mode

# Reads from the NTFY_TOPIC environment variable if set (used on GitHub Actions,
# where it comes from a repo secret). Falls back to the hardcoded value below
# for local runs - edit that fallback to your own random topic name.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "casio-deals-CHANGE-ME")
STATE_FILE = Path(__file__).with_name("seen_deals.json")
USER_AGENT = "Mozilla/5.0 (compatible; PersonalDealBot/1.0)"
REQUEST_TIMEOUT = 15
# -----------------------------------------


def fetch_products():
    """Pull every product in the collection via Shopify's public JSON feed."""
    products = []
    page = 1
    while True:
        url = f"{COLLECTION_URL}?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            print(f"HTTP error on page {page}: {e}")
            break
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def find_deep_discounts(products, threshold):
    """Return every variant whose real discount % is >= threshold."""
    deals = []
    for product in products:
        title = product.get("title", "Unknown")
        handle = product.get("handle", "")
        for variant in product.get("variants", []):
            try:
                price = float(variant.get("price") or 0)
                compare_at = float(variant.get("compare_at_price") or 0)
            except (TypeError, ValueError):
                continue

            if compare_at <= 0 or price <= 0 or price >= compare_at:
                continue

            discount_pct = (compare_at - price) / compare_at * 100
            if discount_pct >= threshold:
                deals.append({
                    "id": variant.get("id"),
                    "title": title,
                    "variant_title": variant.get("title"),
                    "price": price,
                    "compare_at": compare_at,
                    "discount_pct": round(discount_pct, 1),
                    "url": f"https://casiostore.bhawar.com/products/{handle}?variant={variant.get('id')}",
                })
    return deals


def load_seen():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(seen, indent=2))


def notify(deal):
    message = (
        f"{deal['title']} ({deal['variant_title']})\n"
        f"{deal['discount_pct']}% off - Rs.{deal['price']:.0f} (was Rs.{deal['compare_at']:.0f})\n"
        f"{deal['url']}"
    )
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": f"Casio deal: {deal['discount_pct']}% off",
            "Priority": "high",
            "Tags": "watch,moneybag",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Notified: {deal['title']} - {deal['discount_pct']}% off")
    except Exception as e:
        print(f"Failed to send notification: {e}")


def run_once():
    seen = load_seen()
    products = fetch_products()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Checked {len(products)} products")

    deals = find_deep_discounts(products, DISCOUNT_THRESHOLD)
    new_deals = 0
    for deal in deals:
        key = f"{deal['id']}:{deal['price']}"
        if key not in seen:
            notify(deal)
            seen[key] = deal
            new_deals += 1

    if new_deals:
        save_seen(seen)
    else:
        print("No new deals above threshold.")
    return new_deals


def main_loop():
    print(f"Watching casiostore.bhawar.com for >= {DISCOUNT_THRESHOLD}% discounts...")
    print(f"Checking every {CHECK_INTERVAL_SECONDS // 60} minute(s). Ctrl+C to stop.")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Unexpected error: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Casio Bhawar Store discount watcher")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        main_loop()
