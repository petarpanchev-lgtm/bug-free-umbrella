# Kullamagi Setup Tools — Web App

Six tools built ONLY from what Kristjan Kullamagi says in his own words in
Jack Schwager & George F. Coyle's *Market Wizards: The Next Generation*
(Chapter 1). No thresholds are pulled from his blog/FAQ or third-party
scanner write-ups — every number is a direct or clearly-labeled
operationalization of a specific line from that interview. See the
in-app "Book citations behind these tools" expander, or the docstrings in
`kullamagi_setups.py`, for the exact quotes behind every threshold.

**Screeners** (scan a universe, flag tickers matching ALL of that setup's book conditions):
- Breakout / Momentum Burst Screener
- Episodic Pivot (EP) Screener
- Parabolic Short Screener

**Calculators** (type in a ticker, get a trade plan):
- Breakout Trade Planner — entry, stop, position size, 1R/2R/3R targets
- Episodic Pivot Trade Planner
- Parabolic Short Trade Planner

See the main `Kullamagi_Trading_Playbook.docx` for the full narrative rule set.

Files in this folder:
- `app.py` — the Streamlit UI, laid out as a two-step workflow: **Step 1** (top row) picks a strategy and screens a universe for candidates; **Step 2** (bottom row) takes a ticker and calculates its entry/stop/position size. Also has a manual "run the daily screener now" trigger.
- `kullamagi_setups.py` — the setup-specific screener/calculator logic, with book citations in the docstrings
- `kullamagi_score.py` — shared helpers (`fetch_data`, `market_regime`) plus the original blended 0-100 fit score (superseded by the dedicated tools above, kept for reference)
- `screener.py` — ticker universe fetchers: S&P 500 / Nasdaq-100 (via Wikipedia, with offline fallbacks), "All NYSE and NASDAQ common stocks" (reads the local `nasdaq_nyse_common_stock.csv`, no network call), plus `get_all_us_tickers()` (live from the Nasdaq Trader symbol directory, used internally by the daily automated screener's fallback chain, not exposed as a manual option) — plus batch price download
- `nasdaq_nyse_common_stock.csv` — bundled snapshot of every individual common stock (ETFs excluded) on NASDAQ/NYSE/NYSE American/NYSE Arca; see "Keeping the common-stock list updated" below
- `export_universe.py` — refreshes `nasdaq_nyse_common_stock.csv` from Nasdaq Trader's live symbol directory
- `daily_screen.py` — standalone (non-Streamlit) script that runs all 3 screeners against the full universe once and logs changes to `screener_history.xlsx`; see "Daily Automated Screener" below
- `.github/workflows/daily_screener.yml` — the GitHub Actions workflow that runs `daily_screen.py` on a schedule
- `.github/workflows/update_common_stock_list.yml` — the GitHub Actions workflow that runs `export_universe.py` weekly to keep the bundled CSV current
- `requirements.txt` — dependencies

## Run it locally first (optional, to confirm it works)

```bash
pip install -r requirements.txt
streamlit run app.py
```

It'll open at `http://localhost:8501`.

## Deploy it publicly — Streamlit Community Cloud (free, recommended)

This is the easiest way to get a public URL you can share with anyone. No
server management, no credit card, free for public apps.

1. **Create a GitHub repo** (if you don't already have one for this).
   - Go to github.com → New repository → name it e.g. `kullamagi-tools` → Create.
   - Upload the files in this folder (`app.py`, `kullamagi_setups.py`,
     `kullamagi_score.py`, `screener.py`, `requirements.txt`) via the GitHub
     web UI ("Add file" → "Upload files"), or push them with git:
     ```bash
     cd kullamagi-web
     git init
     git add app.py kullamagi_setups.py kullamagi_score.py screener.py requirements.txt
     git commit -m "Kullamagi setup screeners + calculators"
     git branch -M main
     git remote add origin https://github.com/<your-username>/kullamagi-tools.git
     git push -u origin main
     ```

2. **Sign up / log in to Streamlit Community Cloud.**
   - Go to https://share.streamlit.io
   - Sign in with your GitHub account (this also authorizes Streamlit to
     read your repos).

3. **Deploy the app.**
   - Click "New app" (or "Create app").
   - Pick the repo, branch (`main`), and main file path (`app.py`).
   - Click "Deploy". First build takes 1-2 minutes.

4. **You'll get a public URL**, something like:
   `https://kullamagi-tools-<random>.streamlit.app`
   Share that link with anyone — it runs the same logic, live, against
   real Yahoo Finance data.

5. **Updating it later:** just push new commits to the GitHub repo — the
   Streamlit app redeploys automatically.

### Notes / limits
- Community Cloud apps "sleep" after a period of inactivity and take a few
  seconds to wake up on the next visit — normal for the free tier.
- Data comes from `yfinance` (Yahoo Finance), free and unauthenticated but
  can occasionally rate-limit heavy traffic — fine for personal/shared use.
- The calculators try to fetch real intraday 5-minute bars (for the EP and
  Parabolic Short entry/stop rules). This only works during/shortly after
  market hours and within Yahoo's intraday data window; outside that, the
  tools fall back to a daily-bar approximation and say so clearly.
- If you'd rather not use GitHub/Streamlit Cloud, the same `app.py` runs on
  any host that supports Python web apps (Render, Railway, Fly.io, etc.) —
  the command to run is `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

## Using the app: a two-step workflow

The page is laid out top to bottom as two steps, each its own row with its
own strategy selector — screen first, then calculate:

### Step 1 (top row) — Select a strategy and scan

1. Pick which setup to screen for: **Breakout / Momentum Burst**, **Episodic
   Pivot (EP)**, or **Parabolic Short**.
2. Pick a universe: **S&P 500** or **Nasdaq-100** (fetched live from
   Wikipedia each run, with an offline fallback list if that fetch fails),
   **All NYSE and NASDAQ common stocks (3963 tickers)** (reads
   `nasdaq_nyse_common_stock.csv` straight from the repo — no live fetch, so
   it's faster and immune to that site being briefly down, at the cost of
   being up to a week stale; the exact count drifts slightly as the weekly
   refresh runs — see "Keeping the common-stock list updated" below), or
   **Custom list** (paste tickers or upload a CSV with a `Ticker`/`Symbol`
   column).
3. Adjust the setup-specific sliders if you want (defaults match the book's
   own numbers where the book gives one — e.g. EP gap ≥10%, Parabolic Short
   A+ ≥300% over 3-5 days).
4. Set a **max tickers to scan** safety cap and click **Fetch universe & run**.
   Tickers download in batches with a progress bar. Only tickers meeting
   **all** of that setup's conditions are shown, with a CSV download button.
5. The Breakout and EP screeners show the market-environment banner (SPY
   10-day vs. 20-day MA) once at the top — book: only take those two setups
   in a favorable environment. Parabolic Short is market-agnostic per the
   book, so no banner there.

Important limitations, by design:
- The **EP screener** can't verify a genuine news catalyst from price data
  alone — it flags gap+volume(+dormancy) candidates only; always confirm a
  real catalyst manually.
- The **Parabolic Short screener** flags candidates by run-length + cumulative
  gain; the actual short trigger (break of the opening range low, or a break
  below a 5-minute candle) still needs to be confirmed intraday.
- Tickers with too little history, or that fail to download, are skipped and
  listed in a collapsed "skipped" section rather than breaking the whole scan.

### Step 2 (bottom row) — Calculate trade parameters

Once you've got a candidate ticker — from Step 1 above, or one you already
have in mind — drop down to the second row to work out the actual trade:

1. Pick the matching strategy, type in the ticker, set your account size and
   risk % (book: 0.5% typical, 1% max), and any setup-specific check
   thresholds.
2. Click **Calculate**. You'll get the entry, stop, risk per share, position
   size (shares, $ value, % of account), and 1R/2R/3R targets.
3. Warnings appear inline if a condition fails — e.g. the Breakout stop is
   wider than 1x ADTR (book says skip the trade), or a gap/volume/A+ check
   doesn't clear your threshold.
4. The EP and Parabolic Short calculators try to pull real 5-minute intraday
   bars for the exact entry/stop the book describes; if that data isn't
   available, they fall back to today's daily open/low or high and say so.

## Keeping the common-stock list updated

`nasdaq_nyse_common_stock.csv` is a snapshot -- every individual common
stock (ETFs excluded) listed on NASDAQ, NYSE, NYSE American, and NYSE Arca,
sourced from Nasdaq Trader's public symbol directory. Stock listings change
(new IPOs, delistings, ticker changes), so this file needs periodic
refreshing to stay accurate. Three things read it:

- The app's **All NYSE and NASDAQ common stocks** universe option (manual
  scans, Step 1).
- `daily_screen.py`'s fallback chain: it tries the live full-symbol-directory
  fetch first, falls back to this CSV if that fails, and only falls back
  further to the small S&P 500 + Nasdaq-100 combined list if the CSV itself
  is somehow missing or unreadable.

**Keeping it fresh** -- `.github/workflows/update_common_stock_list.yml` runs
`export_universe.py` automatically every Saturday at 12:00 UTC (markets
closed, quiet time) and commits the refreshed CSV back to the repo if
anything changed. No setup needed beyond having this workflow file pushed to
your repo -- same "just needs to exist under `.github/workflows/`" mechanism
as the daily screener.

**Running it manually**, e.g. right after a big batch of new listings: repo
-> **Actions** tab -> "Update Common Stock List" -> **Run workflow**. (It
doesn't have its own button in the app the way the daily screener does --
add one the same way if you want that, see `trigger_github_workflow()` in
`app.py` for the pattern.)

**Running it locally** (needs real internet access, so it won't work from a
sandboxed environment, but will from your own machine):
```bash
python export_universe.py
```
This overwrites `nasdaq_nyse_common_stock.csv` in place with a fresh pull.

## Daily Automated Screener (GitHub Actions)

`daily_screen.py` + `.github/workflows/daily_screener.yml` run all 3 screeners
against the full NYSE+NASDAQ universe once a day on GitHub's own servers --
the only part of this whole setup with guaranteed, unrestricted internet
access on a fixed schedule. Results are logged to `screener_history.xlsx` at
the repo root, one sheet per setup, tracking only what CHANGED (newly added
or dropped tickers) instead of rewriting the whole list every day.

Universe used: live full-symbol-directory fetch first, falling back to the
bundled `nasdaq_nyse_common_stock.csv` if that fails, falling back further to
S&P 500 + Nasdaq-100 combined only if the CSV itself is unavailable -- see
"Keeping the common-stock list updated" above.

### Enabling it
No separate "enable" step -- just make sure both of these are pushed to your
repo:
- `daily_screen.py`
- `.github/workflows/daily_screener.yml` (must be at exactly this path,
  including the `.github/workflows/` folder)

GitHub automatically picks up any workflow file under `.github/workflows/`.
It runs weekdays at 21:30 UTC (after the US market close whether it's EDT or
EST) -- edit the `cron:` line in the workflow file to change the time.

### Running it manually
Two ways to trigger a run without waiting for the schedule:

1. **From GitHub**: repo → **Actions** tab → "Daily Kullamagi Screener" →
   **Run workflow**.
2. **From the app itself**: expand "Manual trigger: run the daily screener
   now" near the top of the page and click **Run workflow now**. This calls
   GitHub's API directly, so you don't have to leave the app. To use this
   button, give the app a GitHub token first:

   a. Create a fine-grained personal access token at
      https://github.com/settings/personal-access-tokens/new
      - Under "Repository access", choose "Only select repositories" and
        pick this repo.
      - Under "Permissions" → "Repository permissions", set **Actions** to
        **Read and write**.
      - Generate the token and copy it (GitHub only shows it once).

   b. Add it to your Streamlit app's secrets: on share.streamlit.io, open
      your app → the "⋮" menu → **Settings** → **Secrets**, then add:
      ```toml
      GITHUB_TOKEN = "github_pat_..."
      GITHUB_REPO_OWNER = "your-github-username"
      GITHUB_REPO_NAME = "kullamagi-tools"
      ```
      (use your actual username/repo name; `GITHUB_BRANCH` is optional and
      defaults to `main`). Save -- the app restarts automatically with the
      secrets available.

   Never commit the token to the repo itself. Streamlit secrets are kept
   separate from your code for exactly this reason.

### Reading the results
Open `screener_history.xlsx` from the repo. Each sheet (`Breakout`, `EP`,
`Parabolic Short`) has six columns: `Date`, `Ticker`, `Status`, `Entry`,
`Stop Loss`, `Take Profit`. The first run for a setup logs every current hit
as `Initial`; every run after that only adds a row when a ticker newly
qualifies (`Added`) or stops qualifying (`Dropped`) -- tickers still flagged
from the day before get no new row, so the log stays short over time. To see
what's currently flagged as of any date, replay the rows top to bottom
(Initial/Added → in the set, Dropped → out of the set).

`Entry`, `Stop Loss`, and `Take Profit` come from that setup's own
trade-planner calculator (the same logic behind the app's Step 2
calculators) run automatically against every `Initial`/`Added` ticker --
`Take Profit` is the 2R target, matching the book's "sell 1/3-1/2 in the
first 3-5 days or at 2-3R" rule. `Dropped` rows leave these three columns
blank since the setup no longer applies. These numbers use a generic
$10,000/0.5%-risk placeholder purely to derive entry/stop/targets, which
don't actually depend on account size or risk % -- run the app's calculator
with your real numbers to get position size (shares/$ value). For EP and
Parabolic Short, the calculator tries to use that day's real 5-minute
intraday bars for the entry/stop, same as the app; if unavailable it falls
back to the daily bar approximation.

## Disclaimer
Educational tool only, not financial advice. Not affiliated with or endorsed
by Kristjan Kullamagi / Qullamaggie.
