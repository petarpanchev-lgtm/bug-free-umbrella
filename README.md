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
- `app.py` — the Streamlit UI (all 6 tools)
- `kullamagi_setups.py` — the setup-specific screener/calculator logic, with book citations in the docstrings
- `kullamagi_score.py` — shared helpers (`fetch_data`, `market_regime`) plus the original blended 0-100 fit score (superseded by the dedicated tools above, kept for reference)
- `screener.py` — ticker universe fetchers (S&P 500 / Nasdaq-100 via Wikipedia, with an offline fallback list) + batch price download
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

## Using the Screeners

1. Pick a universe: **S&P 500** or **Nasdaq-100** (fetched live from
   Wikipedia each run, with an offline fallback list if that fetch fails),
   or **Custom list** (paste tickers or upload a CSV with a `Ticker`/`Symbol`
   column).
2. Adjust the setup-specific sliders if you want (defaults match the book's
   own numbers where the book gives one — e.g. EP gap ≥10%, Parabolic Short
   A+ ≥300% over 3-5 days).
3. Set a **max tickers to scan** safety cap and click **Fetch universe & run**.
   Tickers download in batches with a progress bar. Only tickers meeting
   **all** of that setup's conditions are shown, with a CSV download button.
4. The Breakout and EP screeners show the market-environment banner (SPY
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

## Using the Calculators

1. Type in a ticker, set your account size and risk % (book: 0.5% typical,
   1% max), and any setup-specific check thresholds.
2. Click **Calculate**. You'll get the entry, stop, risk per share, position
   size (shares, $ value, % of account), and 1R/2R/3R targets.
3. Warnings appear inline if a condition fails — e.g. the Breakout stop is
   wider than 1x ADTR (book says skip the trade), or a gap/volume/A+ check
   doesn't clear your threshold.
4. The EP and Parabolic Short calculators try to pull real 5-minute intraday
   bars for the exact entry/stop the book describes; if that data isn't
   available, they fall back to today's daily open/low or high and say so.

## Disclaimer
Educational tool only, not financial advice. Not affiliated with or endorsed
by Kristjan Kullamagi / Qullamaggie.
