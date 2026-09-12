# Casio Bhawar Store — Deep Discount Watcher

Watches `casiostore.bhawar.com/collections/watches` for watches discounted
70% or more, and pushes a phone notification the moment a new one appears.

## How it works

1. Pulls every product in the collection via Shopify's public JSON feed
   (no login needed — prices are visible to everyone).
2. Computes the real discount percentage itself from `price` vs.
   `compare_at_price`, rather than relying on the site's own "% off" tag
   (so it won't miss anything the site's own filter might).
3. The first time a specific variant+price crosses the threshold, it sends
   a push notification via [ntfy](https://ntfy.sh) and remembers it in
   `seen_deals.json` so you don't get repeat alerts for the same deal.

## Requirements

- Python 3.9+ — no external packages, standard library only
- The [ntfy](https://ntfy.sh) app on your phone (free, no signup)

## Running locally

Create a `.env` file next to `watch_alert.py` (already gitignored, never
commit it):

```
NTFY_TOPIC=pick-something-long-and-random
```

ntfy topics are public — anyone who guesses your topic name can see your
alerts, so make it long and random rather than something guessable like
`casio-deals`. Subscribe to that same topic name in the ntfy app, then run:

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
   secret** → add `NTFY_TOPIC` with your chosen topic name.
3. Repo → **Settings → Actions → General → Workflow permissions** → select
   **Read and write permissions** → Save. (Lets the workflow commit updated
   `seen_deals.json` after each run.)
4. Repo → **Actions** tab → select "Casio deal check" → **Run workflow** to
   test it manually. Check the log for `Checked N products`.
5. From then on it runs automatically every 15 minutes, for free.

## Configuration

Edit the constants near the top of `watch_alert.py`:

| Variable                 | Default | Meaning                                  |
|---------------------------|---------|-------------------------------------------|
| `DISCOUNT_THRESHOLD`      | `70`    | Minimum % off to trigger an alert         |
| `CHECK_INTERVAL_SECONDS`  | `300`   | Poll interval in local loop mode          |

The GitHub Actions cron schedule lives in
`.github/workflows/deal-check.yml` (`*/15 * * * *`).

## A few notes

- This store's `robots.txt` requests no automated crawling. This script is
  meant for personal, low-frequency use (one request every 15+ minutes) —
  not for scraping the whole catalog rapidly or redistributing data.
- Your ntfy topic is effectively a private channel — don't commit it into
  a public README or code file; keep it in `.env` / GitHub secrets.
- `seen_deals.json` is intentionally tracked in git (not ignored) so state
  survives between GitHub Actions runs.
