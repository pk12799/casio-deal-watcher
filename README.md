# Casio Bhawar Store — Deep Discount Watcher

Watches `casiostore.bhawar.com/collections/watches` for watches discounted
70% or more, and alerts you the moment one appears — with a photo, via
push notification and (optionally) email.

## How it works

1. Pulls every product in the collection via Shopify's public JSON feed
   (no login needed — prices are visible to everyone).
2. Computes the real discount percentage itself from `price` vs.
   `compare_at_price`, rather than relying on the site's own "% off" tag.
3. The first time a specific variant+price crosses the threshold, it sends
   a push notification (with the watch's photo attached) via
   [ntfy](https://ntfy.sh), and an email if you've configured SMTP.
4. Remembers each alerted deal in `seen_deals.json` for **24 hours**
   (`SEEN_TTL_HOURS`) so you don't get repeat alerts for the same still-live
   deal — but if it's still discounted after 24h, or the discount reappears
   later, you'll be notified again rather than it going silent forever.

## Requirements

- Python 3.9+ — no external packages, standard library only
- The [ntfy](https://ntfy.sh) app on your phone (free, no signup)
- (Optional) an SMTP account for email alerts — e.g. a Gmail address with
  an [app password](https://myaccount.google.com/apppasswords)

## Running locally

Create a `.env` file next to `watch_alert.py` (already gitignored, never
commit it):

```
NTFY_TOPIC=pick-something-long-and-random

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
   secret** → add `NTFY_TOPIC`. Add the five `SMTP_*` / `EMAIL_TO` secrets
   too if you want email alerts (leave them unset to skip email entirely).
3. Repo → **Settings → Actions → General → Workflow permissions** → select
   **Read and write permissions** → Save. (Lets the workflow commit updated
   `seen_deals.json` after each run.)
4. Repo → **Actions** tab → select "Casio deal check" → **Run workflow** to
   test it manually. Check the log for `Checked N products`.
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
