"""
export_universe.py

Refreshes nasdaq_nyse_common_stock.csv -- the bundled list of every
INDIVIDUAL COMMON STOCK (ETFs excluded) listed on NASDAQ, NYSE, NYSE
American, and NYSE Arca, sourced from Nasdaq Trader's public symbol
directory.

This file is used three ways elsewhere in this project:
  1. screener.py's get_common_stocks_from_csv() reads it as a fast, local,
     network-free universe source (for the app's "Common Stocks (bundled
     list)" manual-scan option).
  2. daily_screen.py falls back to it if the live NASDAQ+NYSE fetch fails
     that day (better fallback than the small S&P 500 + Nasdaq-100 list).
  3. You can select it directly for a manual scan in the app.

It needs real, unrestricted internet access (blocked from a chat-agent
sandbox), so it's meant to run via its own GitHub Actions workflow --
see .github/workflows/update_common_stock_list.yml -- on a weekly
schedule, or triggered manually anytime from the Actions tab.

Usage:
    python export_universe.py

Writes:
    nasdaq_nyse_common_stock.csv  (columns: Symbol, Security Name, Exchange, ETF)
"""

import os
import re

import pandas as pd

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nasdaq_nyse_common_stock.csv")

VALID_TICKER = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")

# otherlisted.txt's "Exchange" column uses single-letter codes for the
# NYSE-family exchanges it covers.
_EXCHANGE_CODE_MAP = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}


def _clean_ticker(raw):
    """Same validation used in screener.py's get_all_us_tickers -- strict
    regex, no internal whitespace, normalize share classes (BRK.B -> BRK-B).

    Checks pd.isna(raw) BEFORE stringifying, rather than comparing the
    stringified value to "NAN" -- there's a real ticker, NAN (Nuveen New
    York Quality Municipal Income Fund), that a naive string comparison
    would wrongly reject as if it were a missing value."""
    if pd.isna(raw):
        return None
    try:
        t = str(raw).strip().upper()
    except Exception:
        return None
    if not t or "FILE CREATION TIME" in t:
        return None
    if " " in t:
        return None
    t = t.replace(".", "-")
    if not VALID_TICKER.match(t):
        return None
    return t


def fetch_nasdaq_listed():
    df = pd.read_csv("https://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt", sep="|")
    if "Test Issue" in df.columns:
        df = df[df["Test Issue"] == "N"]
    if "ETF" in df.columns:
        df = df[df["ETF"] == "N"]  # individual common stocks only, no ETFs

    rows = []
    for _, r in df.iterrows():
        t = _clean_ticker(r.get("Symbol"))
        if not t:
            continue
        rows.append({
            "Symbol": t,
            "Security Name": str(r.get("Security Name", "")).strip(),
            "Exchange": "NASDAQ",
            "ETF": "N",
        })
    return rows


def fetch_other_listed():
    df = pd.read_csv("https://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt", sep="|")
    if "Test Issue" in df.columns:
        df = df[df["Test Issue"] == "N"]
    if "ETF" in df.columns:
        df = df[df["ETF"] == "N"]  # individual common stocks only, no ETFs
    sym_col = "ACT Symbol" if "ACT Symbol" in df.columns else "NASDAQ Symbol"

    rows = []
    for _, r in df.iterrows():
        t = _clean_ticker(r.get(sym_col))
        if not t:
            continue
        exch_code = str(r.get("Exchange", "")).strip()
        rows.append({
            "Symbol": t,
            "Security Name": str(r.get("Security Name", "")).strip(),
            "Exchange": _EXCHANGE_CODE_MAP.get(exch_code, exch_code or "Unknown"),
            "ETF": "N",
        })
    return rows


def main():
    print("Fetching NASDAQ-listed securities...")
    nasdaq_rows = fetch_nasdaq_listed()
    print(f"  {len(nasdaq_rows)} individual common stocks after filtering ETFs/test issues.")

    print("Fetching NYSE-group-listed securities (otherlisted.txt)...")
    other_rows = fetch_other_listed()
    print(f"  {len(other_rows)} individual common stocks after filtering ETFs/test issues.")

    all_rows = nasdaq_rows + other_rows
    df = (
        pd.DataFrame(all_rows, columns=["Symbol", "Security Name", "Exchange", "ETF"])
        .drop_duplicates(subset="Symbol")
        .sort_values("Symbol")
        .reset_index(drop=True)
    )

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(df)} unique individual common stocks to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
