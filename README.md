# Casio Bhawar Store — Deep Discount Watcher

Watches `casiostore.bhawar.com` for deeply discounted, **in-stock** Casio
watches and alerts you the moment one appears — with a photo, via push
notification and (optionally) email.

## How it works

1. Sweeps the public Shopify JSON feeds for `/collections/all` **plus**
   `watches`, `edifice-watches`, `g-shock`, `casio-vintage`, `casio` and
   `new-launch`, de-duplicating by product handle (~1,360 unique products).

   > Why not just `/collections/watches`? Because that collection only
   > exposes ~407 products. Plenty of discounted models — MTP-VT01G-9B at
   > 50% off, for example — simply aren't tagged into it, so watching that
   > one collection silently missed them.

2. Computes the real discount percentage itself from `price` vs.
   `compare_at_price`, rather than relying on the site's own "% off" tag.
   (The collection *pages* render `MRP ₹ … (0% Off)` on every card because
   the theme shows the product-level price range, not the variant sale
   price — the JSON feed is the accurate source.)
3. Skips any variant marked `"available": false` — sold-out watches are
   filtered out so you're only pinged about deals you can actually buy.
4. The first time a specific variant+price crosses the threshold, it sends
   a push notification (with the watch's photo attached) via
   [ntfy](https://ntfy.sh), and an email if you've configured SMTP.
   Deals are processed highest-discount-first.
5. Remembers each alerted deal in `seen_deals.json` for **24 hours**
   (`SEEN_TTL_HOURS`) so you don't get repeat alerts for the same still-live
   deal — but if it's still discounted after 24h, or the discount reappears
   later, you'll be notified again rather than it going silent forever.

## Checking what's on sale right now

```bash
python3 watch_alert.py --dry-run
```

Lists every current in-stock deal without sending notifications or touching
`seen_deals.json`. Useful for sanity-checking the threshold before you let
it loose.

## Requirements

- Python 3.9+ — no external packages, standard library only
- The [ntfy](https://ntfy.sh) app on your phone (free, no signup)
- (Optional) a customer account on the store — `SHOP_EMAIL` / `SHOP_PASSWORD`
  make requests with a logged-in session. Not required; the public feed
  already carries the sale prices.
- (Optional) an SMTP account for email alerts — e.g. a Gmail address with
  an [app password](https://myaccount.google.com/apppasswords)

## Running locally

Create a `.env` file next to `watch_alert.py` (already gitignored, never
commit it):

```
NTFY_TOPIC=pick-something-long-and-random

# Optional - browse with a logged-in session (not needed for prices)
SHOP_EMAIL=you@example.com
SHOP_PASSWORD=your_store_password

# Optional - only add these if you also want email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your_16_char_app_password
EMAIL_TO=you@gmail.com
```

ntfy topics are public — anyone who guesses your topic name can see your
alerts, so make it long and random. Subscribe to that topic in the ntfy
app, then run:

```bash
python3 watch_alert.py            # loops forever, checks every 5 min
python3 watch_alert.py --once     # single check, useful for cron
```

Keep it running in the background with `nohup python3 watch_alert.py &`,
a `screen`/`tmux` session, or a systemd user service / Task Scheduler entry.

## Running for free on GitHub Actions (no laptop needed)

1. Push this folder to a new **public** GitHub repo (public = unlimited
   free Actions minutes; a private repo works too but gets 2,000 free
   minutes/month, so widen the cron interval to ~30 min to stay under that).
2. Repo → **Settings → Secrets and variables → Actions → New repository
   secret** → add `NTFY_TOPIC`, `SHOP_EMAIL` and `SHOP_PASSWORD`. Add the five
   `SMTP_*` / `EMAIL_TO` secrets too if you want email alerts (leave them
   unset to skip email entirely).
3. Repo → **Settings → Actions → General → Workflow permissions** → select
   **Read and write permissions** → Save. (Lets the workflow commit updated
   `seen_deals.json` after each run.)
4. Repo → **Actions** tab → select "Casio deal check" → **Run workflow** to
   test it manually. Check the log for `Checked N unique products`.
5. From then on it runs automatically every 15 minutes, for free.

## Email setup notes (optional)

- **Gmail**: turn on 2-Step Verification, then create an
  [app password](https://myaccount.google.com/apppasswords) — use that as
  `SMTP_PASS`, not your normal password. `SMTP_HOST=smtp.gmail.com`,
  `SMTP_PORT=587`.
- Any other provider's SMTP works too — just fill in its host/port/creds.
- If `SMTP_HOST` and `EMAIL_TO` aren't set, email is skipped automatically
  and only the ntfy push notification is sent.

## Configuration

Edit the constants near the top of `watch_alert.py`:

| Variable                 | Default | Meaning                                          |
|---------------------------|---------|---------------------------------------------------|
| `DISCOUNT_THRESHOLD`      | `70`    | Minimum % off to trigger an alert                 |
| `CHECK_INTERVAL_SECONDS`  | `300`   | Poll interval in local loop mode                  |
| `SEEN_TTL_HOURS`          | `24`    | How long a deal is "remembered" before re-alerting |

The GitHub Actions cron schedule lives in
`.github/workflows/deal-check.yml` (`*/15 * * * *`).

## A few notes

- This store's `robots.txt` requests no automated crawling. This script is
  meant for personal, low-frequency use (one request every 15+ minutes) —
  not for scraping the whole catalog rapidly or redistributing data.
- Your ntfy topic and any SMTP credentials are secrets — keep them in
  `.env` / GitHub secrets, never commit them.
- `seen_deals.json` is intentionally tracked in git (not ignored) so state
  survives between GitHub Actions runs; expired entries are pruned from it
  automatically on each run.
