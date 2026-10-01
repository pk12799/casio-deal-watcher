#!/usr/bin/env python3
"""
Casio Bhawar Store - Deep Discount Watcher
-------------------------------------------
Logs into the store as a customer, walks every page of the
/collections/watches collection, reads the *rendered* price vs. MRP for
each product card, and alerts you the first time a deal crosses
DISCOUNT_THRESHOLD percent - via a push notification (with the watch's
photo attached) and, optionally, email.

Why not the public products.json feed? Because this store applies its
discounts for logged-in customers only: logged out, every product (and
therefore the JSON feed) shows MRP with "(0% Off)", even when the product
page shows e.g. "70% Special Offer" to a signed-in shopper. So we scrape
the HTML with an authenticated session instead. Set SHOP_EMAIL and
SHOP_PASSWORD or you will see no deals at all.

A given deal (product + price) won't re-alert for SEEN_TTL_HOURS, after
which it "forgets" it and will alert again if the discount is still live -
so a recurring flash sale keeps notifying you each time it reappears
instead of going silent forever after the first hit.

No third-party packages required - stdlib only.

Usage:
    python3 watch_alert.py           # run forever, checking on an interval
    python3 watch_alert.py --once    # check a single time and exit (cron / GitHub Actions)
"""

import argparse
import html as html_module
import http.cookiejar
import json
import os
import re
import smtplib
import time
import urllib.parse
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, timedelta

# ---------------- Config ----------------
STORE = "https://casiostore.bhawar.com"
COLLECTION_URL = f"{STORE}/collections/watches/products.json"
COLLECTION_HTML_URL = f"{STORE}/collections/watches"
LOGIN_URL = f"{STORE}/account/login"
DISCOUNT_THRESHOLD = 50          # percent - change if you want a different cutoff
CHECK_INTERVAL_SECONDS = 300     # 5 minutes, used only in loop mode
SEEN_TTL_HOURS = 24              # a deal "forgotten" after this long can alert again
MAX_COLLECTION_PAGES = 40        # safety stop when walking the collection HTML

# Store login - the discounted prices are only rendered for logged-in
# customers, so without these the watcher only sees MRP (0% off).
SHOP_EMAIL = os.environ.get("SHOP_EMAIL")
SHOP_PASSWORD = os.environ.get("SHOP_PASSWORD")

# ntfy (push notifications) - reads NTFY_TOPIC from env / GitHub secret / .env
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "casio-deals-CHANGE-ME")


# Email (optional) - only used if SMTP_HOST and EMAIL_TO are both set.
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")
EMAIL_ENABLED = bool(SMTP_HOST and EMAIL_TO)

STATE_FILE = Path(__file__).with_name("seen_deals.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
REQUEST_TIMEOUT = 40
# -----------------------------------------


def load_local_env():
    """
    Tiny, dependency-free .env loader for local runs. If a .env file sits
    next to this script, load KEY=VALUE lines into os.environ (without
    overwriting variables already set in the real environment). Ignored
    on GitHub Actions, where secrets arrive as real env vars.
    """
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def make_session():
    """A urllib opener that keeps cookies, so we stay logged in."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept", "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def get_text(opener, url, data=None, referer=None):
    headers = {"Referer": referer} if referer else {}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "ignore"), resp.geturl()


def login(opener):
    """
    Log into the Shopify storefront as a customer. The store only renders the
    real sale prices (e.g. 70% Special Offer) for logged-in customers - logged
    out, every product shows MRP with "(0% Off)", which is why the public
    products.json feed never reports a discount.

    Returns True if the session looks authenticated.
    """
    if not (SHOP_EMAIL and SHOP_PASSWORD):
        print("SHOP_EMAIL / SHOP_PASSWORD not set - running logged out "
              "(you will only see MRP, not the member sale prices).")
        return False

    try:
        get_text(opener, LOGIN_URL)  # pick up session + CSRF cookies
        _, final_url = get_text(
            opener,
            LOGIN_URL,
            data={
                "form_type": "customer_login",
                "utf8": "✓",
                "customer[email]": SHOP_EMAIL,
                "customer[password]": SHOP_PASSWORD,
                "return_url": "/account",
            },
            referer=LOGIN_URL,
        )
        account_html, account_url = get_text(opener, f"{STORE}/account")
    except Exception as e:
        print(f"Login failed: {e}")
        return False

    logged_in = "/account/login" not in account_url and (
        "logout" in account_html.lower() or "order history" in account_html.lower()
    )
    print("Logged in as a customer." if logged_in
          else f"Login did not take (landed on {final_url}). Check SHOP_EMAIL/SHOP_PASSWORD.")
    return logged_in


def fetch_product_catalogue(opener):
    """
    Handle -> {title, image_url, variant_id} from the public JSON feed.
    Used only for metadata (photo, variant id); prices come from the
    logged-in HTML pages.
    """
    catalogue = {}
    page = 1
    while page <= MAX_COLLECTION_PAGES:
        url = f"{COLLECTION_URL}?limit=250&page={page}"
        try:
            raw, _ = get_text(opener, url)
            batch = json.loads(raw).get("products", [])
        except Exception as e:
            print(f"Error fetching product feed page {page}: {e}")
            break
        if not batch:
            break
        for product in batch:
            images = product.get("images") or []
            variants = product.get("variants") or []
            catalogue[product.get("handle", "")] = {
                "title": product.get("title", "Unknown"),
                "image_url": images[0]["src"] if images and images[0].get("src") else None,
                "variant_id": variants[0].get("id") if variants else None,
            }
        if len(batch) < 250:
            break
        page += 1
    return catalogue


PRICE_RE = re.compile(r"(?:MRP\s*)?(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)")
SALE_RE = re.compile(
    r'price-item[^"]*price-item--sale[^"]*"[^>]*>\s*((?:MRP\s*)?(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)',
    re.I,
)
REGULAR_RE = re.compile(
    r'<s[^>]*price-item--regular[^>]*>\s*((?:MRP\s*)?(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)',
    re.I,
)
PLAIN_REGULAR_RE = re.compile(
    r'<span[^>]*price-item--regular[^>]*>\s*((?:MRP\s*)?(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)',
    re.I,
)
HANDLE_RE = re.compile(r"/products/([a-z0-9][a-z0-9\-]*)")


def _to_amount(text):
    if not text:
        return 0.0
    m = PRICE_RE.search(html_module.unescape(text).replace("\xa0", " "))
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0


def parse_collection_page(html):
    """
    Pull (handle, price, compare_at) out of every product card on a rendered
    collection page. Cards look like:
        <s class="price-item price-item--regular">MRP ₹ 5,995</s>
        <span class="price-item price-item--sale ...">₹ 1,799</span>
    """
    results = []
    chunks = html.split("card__content")
    for chunk in chunks[1:]:
        handle_match = HANDLE_RE.search(chunk)
        if not handle_match:
            continue
        handle = handle_match.group(1)
        price_block = chunk[:20000]

        sale = _to_amount(SALE_RE.search(price_block).group(1)) if SALE_RE.search(price_block) else 0.0
        regular_match = REGULAR_RE.search(price_block) or PLAIN_REGULAR_RE.search(price_block)
        regular = _to_amount(regular_match.group(1)) if regular_match else 0.0

        if not sale and regular:
            sale = regular
        if not sale:
            continue
        results.append({"handle": handle, "price": sale, "compare_at": max(regular, sale)})
    return results


def fetch_live_prices(opener):
    """Walk every page of the watches collection and read the rendered prices."""
    prices = {}
    page = 1
    while page <= MAX_COLLECTION_PAGES:
        url = f"{COLLECTION_HTML_URL}?page={page}"
        try:
            html, _ = get_text(opener, url)
        except Exception as e:
            print(f"Error fetching collection page {page}: {e}")
            break

        cards = parse_collection_page(html)
        if not cards:
            break

        new_on_page = 0
        for card in cards:
            if card["handle"] not in prices:
                prices[card["handle"]] = card
                new_on_page += 1
        if new_on_page == 0:          # pagination wrapped around / repeated page
            break
        page += 1
    print(f"Scraped prices for {len(prices)} products across {page - 1} collection page(s)")
    return prices


def fetch_deals(opener, threshold):
    """Every product whose live (logged-in) price is >= threshold percent off."""
    catalogue = fetch_product_catalogue(opener)
    prices = fetch_live_prices(opener)

    deals = []
    for handle, card in prices.items():
        price, compare_at = card["price"], card["compare_at"]
        if price <= 0 or compare_at <= 0 or price >= compare_at:
            continue
        discount_pct = (compare_at - price) / compare_at * 100
        if discount_pct < threshold:
            continue

        meta = catalogue.get(handle, {})
        variant_id = meta.get("variant_id")
        url = f"{STORE}/products/{handle}"
        if variant_id:
            url += f"?variant={variant_id}"
        deals.append({
            "id": variant_id or handle,
            "title": meta.get("title") or handle.replace("-", " ").title(),
            "price": price,
            "compare_at": compare_at,
            "discount_pct": round(discount_pct, 1),
            "url": url,
            "image_url": meta.get("image_url"),
        })
    return deals


def load_seen():
    """Load seen deals, dropping any entry older than SEEN_TTL_HOURS so it
    can alert again if the discount is still (or newly) live."""
    if not STATE_FILE.exists():
        return {}
    try:
        raw = json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}

    cutoff = datetime.now() - timedelta(hours=SEEN_TTL_HOURS)
    fresh = {}
    for key, entry in raw.items():
        seen_at_str = entry.get("seen_at") if isinstance(entry, dict) else None
        try:
            seen_at = datetime.fromisoformat(seen_at_str) if seen_at_str else None
        except ValueError:
            seen_at = None
        if seen_at is None or seen_at < cutoff:
            continue  # expired (or malformed/legacy entry) - treat as forgotten
        fresh[key] = entry
    return fresh


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(seen, indent=2))


def send_ntfy(deal):
    message = (
        f"{deal['title']} \n"
        f"{deal['discount_pct']}% off - Rs.{deal['price']:.0f} (was Rs.{deal['compare_at']:.0f})\n"
        f"{deal['url']}"
    )
    headers = {
        "Title": f"Casio deal: {deal['discount_pct']}% off",
        "Priority": "high",
        "Tags": "watch,moneybag",
        "Click": deal["url"],
    }
    if deal.get("image_url"):
        headers["Attach"] = deal["image_url"]  # ntfy fetches this URL and shows it as a photo

    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to send ntfy notification: {e}")


def send_email(deal):
    if not EMAIL_ENABLED:
        return
    subject = f"Casio deal: {deal['discount_pct']}% off {deal['title']}"
    image_html = (
        f'<p><img src="{deal["image_url"]}" alt="watch photo" style="max-width:400px;"></p>'
        if deal.get("image_url") else ""
    )
    html = f"""
    <html><body>
      <h2>{deal['title']}</h2>
      {image_html}
      <p><b>{deal['discount_pct']}% off</b> — Rs.{deal['price']:.0f}
         <s>Rs.{deal['compare_at']:.0f}</s></p>
      <p><a href="{deal['url']}">View watch on the store</a></p>
    </body></html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER or EMAIL_TO
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=REQUEST_TIMEOUT) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(msg["From"], [EMAIL_TO], msg.as_string())
    except Exception as e:
        print(f"Failed to send email: {e}")


def notify_deal(deal):
    send_ntfy(deal)
    send_email(deal)
    print(f"Notified: {deal['title']} - {deal['discount_pct']}% off")


def run_once():
    seen = load_seen()
    opener = make_session()
    login(opener)

    deals = fetch_deals(opener, DISCOUNT_THRESHOLD)
    print(f"[{datetime.now().isoformat(timespec='seconds')}] "
          f"{len(deals)} product(s) at >= {DISCOUNT_THRESHOLD}% off")

    new_deals = 0
    for deal in deals:
        key = f"{deal['id']}:{deal['price']}"
        if key not in seen:
            notify_deal(deal)
            seen[key] = {**deal, "seen_at": datetime.now().isoformat()}
            new_deals += 1

    if new_deals == 0:
        print("No new deals above threshold.")

    save_seen(seen)  # always save, so expired entries actually get pruned from disk
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
    load_local_env()

    parser = argparse.ArgumentParser(description="Casio Bhawar Store discount watcher")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        main_loop()
