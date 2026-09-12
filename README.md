# Casio Bhawar Store — Deep Discount Watcher

Watches `casiostore.bhawar.com/collections/watches` for watches discounted
70% or more, and pushes a phone notification the moment a new one appears.
Since this store only reveals discounted prices to logged-in customers, the
script authenticates using **your own session cookie** and reads the page
the same way your browser would.

## How it works

1. Loads your session cookie and fetches each page of the watches collection.
2. Parses each product card for the regular price and the sale price shown
   to your logged-in account.
3. Computes the real discount percentage itself (doesn't rely on the site's
   own "% off" filter/tag).
4. The first time a specific product+price crosses the threshold, it sends
   a push notification via [ntfy](https://ntfy.sh) and remembers it in
   `seen_deals.json` so you don't get repeat alerts for the same deal.
5. If your session cookie expires, it sends you one alert telling you to
   refresh it, instead of silently going quiet.

## Requirements

- Python 3.9+
- `pip install -r requirements.txt` (requests, beautifulsoup4)
- The [ntfy](https://ntfy.sh) app on your phone (free, no signup)
- A logged-in account on casiostore.bhawar.com

## Getting your session cookie

1. Log into `casiostore.bhawar.com` in a normal browser tab.
2. Open Dev Tools → Network tab, then reload the watches collection page.
3. Click the first request in the list → **Headers** → find the `Cookie`
   request header → copy its entire value.
4. That whole string is your `CASIO_COOKIE` value. Treat it like a
   password — anyone with it can act as your logged-in session.

Session cookies eventually expire (typically after some weeks of
inactivity). When they do, the script alerts you and you just repeat the
steps above and update the secret/`.env` value.

## Running locally

```bash
pip install -r requirements.txt
```

Create a `.env` file next to `watch_alert.py` (already gitignored, never
commit it):

```
CASIO_COOKIE=paste_your_full_cookie_string_here
NTFY_TOPIC=pick-something-long-and-random
```

Subscribe to that same topic name in the ntfy app, then run:

```bash
python3 watch_alert.py            # loops forever, checks every 5 min
python3 watch_alert.py --once     # single check, useful for cron
python3 watch_alert.py --once --debug   # also dumps the raw page for tuning
```

Keep it running in the background with `nohup python3 watch_alert.py &`,
a `screen`/`tmux` session, or a systemd user service / Task Scheduler entry.

## Running for free on GitHub Actions (no laptop needed)

1. Push this folder to a new **public** GitHub repo (public = unlimited
   free Actions minutes; a private repo works too but gets 2,000 free
   minutes/month, so widen the cron interval to ~30 min to stay under that).
2. Repo → **Settings → Secrets and variables → Actions → New repository
   secret**. Add:
   - `CASIO_COOKIE` — your cookie string from above
   - `NTFY_TOPIC` — your chosen topic name
3. Repo → **Settings → Actions → General → Workflow permissions** → select
   **Read and write permissions** → Save. (Lets the workflow commit updated
   `seen_deals.json` after each run.)
4. Repo → **Actions** tab → select "Casio deal check" → **Run workflow** to
   test it manually. Check the log for `Found N discounted watches`.
5. From then on it runs automatically every 15 minutes.

## Configuration

Edit the constants near the top of `watch_alert.py`:

| Variable                 | Default | Meaning                                  |
|---------------------------|---------|-------------------------------------------|
| `DISCOUNT_THRESHOLD`      | `70`    | Minimum % off to trigger an alert         |
| `CHECK_INTERVAL_SECONDS`  | `300`   | Poll interval in local loop mode          |
| `MAX_PAGES`               | `20`    | Safety cap on collection pagination       |

The GitHub Actions cron schedule lives in
`.github/workflows/deal-check.yml` (`*/15 * * * *`).

## If parsing doesn't pick up prices

The site's theme markup wasn't inspected directly when this was written —
the parser targets Shopify's common "Dawn" theme price classes
(`price-item--regular` / `price-item--sale`). If a run finds 0 deals when
you know there should be some:

```bash
python3 watch_alert.py --once --debug
```

This saves the raw collection page HTML to `debug_page.html` so the CSS
selectors in `parse_products_from_html()` can be adjusted to match your
theme's actual markup.

## A few notes

- This store's `robots.txt` requests no automated crawling. This script is
  meant for personal, low-frequency use (one request every 15+ minutes) —
  not for scraping the whole catalog rapidly or redistributing data.
- Your cookie and ntfy topic are secrets — never commit a `.env` file or
  hardcode them into the script.
- `seen_deals.json` is intentionally tracked in git (not ignored) so state
  survives between GitHub Actions runs.
