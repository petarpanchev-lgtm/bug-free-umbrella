"""
daily_screen.py

Standalone daily scan (NOT a Streamlit app -- meant to run headless via
GitHub Actions, see .github/workflows/daily_screener.yml). Runs all 3
Kullamagi setup screeners -- Breakout, Episodic Pivot, Parabolic Short --
against the full NYSE + NASDAQ universe, using the exact same book-only
logic and default thresholds as the screener tabs in app.py.

Rather than re-writing the whole ticker list every day, this keeps a
running log in screener_history.xlsx (one sheet per setup) and only
records what CHANGED since the previous run:
  - First run ever for a setup: every current hit is logged with
    Status = "Initial".
  - Every run after that: only newly-flagged tickers ("Added") and
    tickers that no longer qualify ("Dropped") get a new row. Tickers
    that are still flagged and were already flagged yesterday get no
    row at all -- that's the point of tracking changes instead of state.

"Yesterday's" set of currently-flagged tickers is not stored separately;
it's reconstructed by replaying each sheet's own history top to bottom
(Initial/Added -> add to the set, Dropped -> remove from the set). This
keeps the workbook itself as the single source of truth, so there's
nothing else to keep in sync.

Usage:
    python daily_screen.py

Reads/writes:
    screener_history.xlsx  (created if it doesn't exist yet)
"""

import datetime as dt
import os
import sys

from openpyxl import Workbook, load_workbook

from screener import get_sp500_tickers, get_nasdaq100_tickers, get_all_us_tickers, batch_download
from kullamagi_setups import screen_breakouts, screen_episodic_pivots, screen_parabolic_shorts

HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener_history.xlsx")

SETUPS = ["Breakout", "EP", "Parabolic Short"]


def get_universe():
    """Full NYSE+NASDAQ universe, falling back to S&P 500 + Nasdaq-100
    combined if the live symbol-directory fetch fails for any reason."""
    tickers = get_all_us_tickers()
    if not tickers:
        print("Full universe fetch failed -- falling back to S&P 500 + Nasdaq-100 combined.", file=sys.stderr)
        tickers = list(dict.fromkeys(get_sp500_tickers() + get_nasdaq100_tickers()))
    return tickers


def reconstruct_current_state(ws):
    """Replay a history sheet's rows in date order to reconstruct the set
    of tickers considered 'currently hit' as of the last recorded run."""
    state = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        _, ticker, status = row[0], row[1], row[2]
        if ticker is None or status is None:
            continue
        if status in ("Initial", "Added"):
            state.add(ticker)
        elif status == "Dropped":
            state.discard(ticker)
    return state


def load_or_create_workbook():
    if os.path.exists(HISTORY_PATH):
        wb = load_workbook(HISTORY_PATH)
    else:
        wb = Workbook()
        wb.remove(wb.active)  # drop the default blank sheet
    for name in SETUPS:
        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            ws.append(["Date", "Ticker", "Status"])
    return wb


def update_sheet(wb, setup_name, today_hits, today_str):
    """Diff today's hits against the reconstructed prior state for this
    setup's sheet, and append only the rows that changed. Returns a small
    summary dict for the run log."""
    ws = wb[setup_name]
    previous_state = reconstruct_current_state(ws)
    today_set = set(today_hits)

    added = sorted(today_set - previous_state)
    dropped = sorted(previous_state - today_set)
    is_first_run = ws.max_row <= 1  # only the header row present so far

    if is_first_run:
        for t in sorted(today_set):
            ws.append([today_str, t, "Initial"])
        summary = {"mode": "initial", "count": len(today_set)}
    else:
        for t in added:
            ws.append([today_str, t, "Added"])
        for t in dropped:
            ws.append([today_str, t, "Dropped"])
        summary = {
            "mode": "diff",
            "added": len(added),
            "dropped": len(dropped),
            "unchanged": len(today_set & previous_state),
        }
    return summary


def main():
    today_str = dt.date.today().isoformat()
    print(f"=== Daily Kullamagi screener run: {today_str} ===")

    tickers = get_universe()
    print(f"Universe size: {len(tickers)} tickers")

    print("Downloading price data (shared across all 3 screeners)...")
    price_data = batch_download(tickers)
    print(f"Downloaded data for {sum(1 for v in price_data.values() if v is not None)} of {len(tickers)} tickers.")

    bo_hits, bo_errors = screen_breakouts(price_data)
    ep_hits, ep_errors = screen_episodic_pivots(price_data)
    ps_hits, ps_errors = screen_parabolic_shorts(price_data)

    print(f"Breakout: {len(bo_hits)} hits, {len(bo_errors)} skipped (no/insufficient data)")
    print(f"EP: {len(ep_hits)} hits, {len(ep_errors)} skipped (no/insufficient data)")
    print(f"Parabolic Short: {len(ps_hits)} hits, {len(ps_errors)} skipped (no/insufficient data)")

    wb = load_or_create_workbook()
    results = {
        "Breakout": update_sheet(wb, "Breakout", [h["Ticker"] for h in bo_hits], today_str),
        "EP": update_sheet(wb, "EP", [h["Ticker"] for h in ep_hits], today_str),
        "Parabolic Short": update_sheet(wb, "Parabolic Short", [h["Ticker"] for h in ps_hits], today_str),
    }

    wb.save(HISTORY_PATH)
    print(f"Saved {HISTORY_PATH}")

    for setup_name, s in results.items():
        if s["mode"] == "initial":
            print(f"[{setup_name}] First run recorded: {s['count']} initial hits.")
        else:
            print(f"[{setup_name}] {s['added']} added, {s['dropped']} dropped, "
                  f"{s['unchanged']} unchanged since last run.")


if __name__ == "__main__":
    main()
