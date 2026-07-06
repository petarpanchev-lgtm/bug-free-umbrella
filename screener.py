"""
screener.py

Scans a universe of tickers and scores each against the Kullamagi Breakout
fit model (kullamagi_score.py), returning only tickers that clear a score
threshold (e.g. 90+). Built for the Streamlit screener tab (app.py) but
usable standalone.

Universe sources:
  - S&P 500 / Nasdaq-100: fetched live from Wikipedia via pandas.read_html,
    with a small bundled fallback list used only if the live fetch fails
    (e.g. no internet, or Wikipedia's page structure changes). The fallback
    lists are NOT guaranteed to be current -- they exist purely so the
    screener still works if the live fetch breaks.
  - Custom: any list of tickers you provide (pasted or uploaded as CSV).

Data is pulled in batches via yfinance's multi-ticker download, which is
much faster and more reliable than one ticker per request.
"""

import re
import time

import pandas as pd
import yfinance as yf

from kullamagi_score import score_breakout_fit, fetch_data, market_regime


# ---------------------------------------------------------------------------
# Ticker universes
# ---------------------------------------------------------------------------

# Small fallback lists used only if the live Wikipedia fetch fails. Not
# exhaustive or guaranteed current -- just enough to keep the screener
# usable if the live fetch breaks.
_SP500_FALLBACK = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "BRK-B", "AVGO", "TSLA",
    "JPM", "LLY", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ", "NFLX", "MRK",
    "ABBV", "CRM", "BAC", "ORCL", "CVX", "KO", "AMD", "PEP", "ADBE", "WMT", "TMO",
    "MCD", "CSCO", "ACN", "LIN", "ABT", "WFC", "DHR", "IBM", "GE", "CAT", "QCOM",
    "TXN", "INTU", "VZ", "AMGN", "NOW", "PM", "ISRG", "SPGI", "UNP", "NEE", "RTX",
    "LOW", "AMAT", "HON", "BKNG", "BA", "T", "SYK", "PFE", "GS", "ELV", "DE", "PLD",
    "BLK", "SCHW", "MDT", "TJX", "LMT", "GILD", "ADP", "VRTX", "MU", "SBUX", "MMC",
    "C", "CB", "REGN", "PANW", "ETN", "BSX", "ADI", "ANET", "MO", "SO", "FI", "ZTS",
    "APH", "CME", "DUK", "PGR", "CDNS", "ICE", "MDLZ", "SLB", "KLAC", "SNPS", "WM",
    "TDG", "CI", "EOG", "CVS", "SHW", "HCA", "EQIX", "AON", "ITW", "MCK",
]

_NASDAQ100_FALLBACK = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "AVGO", "TSLA", "COST",
    "NFLX", "ADBE", "AMD", "PEP", "CSCO", "TMUS", "INTU", "QCOM", "AMAT", "TXN",
    "ISRG", "BKNG", "HON", "VRTX", "REGN", "PANW", "ADI", "MU", "GILD", "SBUX",
    "LRCX", "MDLZ", "KLAC", "SNPS", "CDNS", "MAR", "PYPL", "ORLY", "CTAS", "ABNB",
    "MELI", "ASML", "CRWD", "FTNT", "ADP", "NXPI", "MRVL", "PCAR", "CSX", "MNST",
]


def _read_wikipedia_tickers(url, symbol_col_candidates):
    """Try to fetch a ticker table from Wikipedia. Returns a list of ticker
    strings, or None if the fetch/parse fails for any reason (no internet,
    page structure changed, etc.)."""
    try:
        tables = pd.read_html(url)
    except Exception:
        return None
    for t in tables:
        cols = [str(c) for c in t.columns]
        for cand in symbol_col_candidates:
            if cand in cols:
                syms = t[cand].astype(str).str.strip().tolist()
                # Yahoo Finance uses '-' instead of '.' for share classes (e.g. BRK.B -> BRK-B)
                syms = [s.replace(".", "-") for s in syms if s and s.lower() != "nan"]
                if len(syms) >= 20:
                    return syms
    return None


def get_sp500_tickers():
    syms = _read_wikipedia_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        ["Symbol"],
    )
    return syms if syms else list(_SP500_FALLBACK)


def get_nasdaq100_tickers():
    syms = _read_wikipedia_tickers(
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        ["Ticker", "Symbol"],
    )
    return syms if syms else list(_NASDAQ100_FALLBACK)


def get_all_us_tickers():
    """
    Broad universe (~6,000-8,000 tickers): every common stock listed on
    NASDAQ, NYSE, NYSE American, and NYSE Arca, pulled from Nasdaq Trader's
    public symbol directory (nasdaqtrader.com/symboldirectory). This is the
    only realistic way to scan 3,000+ tickers in one run -- the S&P 500 and
    Nasdaq-100 lists top out at ~500 and ~100 respectively.

    Includes ETFs (no reliable free field distinguishes common stock from ETF
    across both files), and Test Issues are filtered out. If the live fetch
    fails (no internet, file moved), returns None -- the caller should fall
    back to S&P 500 + Nasdaq-100 combined, or a custom list.
    """
    try:
        nasdaq = pd.read_csv(
            "https://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt", sep="|"
        )
        other = pd.read_csv(
            "https://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt", sep="|"
        )
    except Exception:
        return None

    tickers = []
    try:
        if "Test Issue" in nasdaq.columns:
            nasdaq = nasdaq[nasdaq["Test Issue"] == "N"]
        if "Symbol" in nasdaq.columns:
            tickers += [str(x) for x in nasdaq["Symbol"].dropna().tolist()]
    except Exception:
        pass

    try:
        if "Test Issue" in other.columns:
            other = other[other["Test Issue"] == "N"]
        sym_col = "ACT Symbol" if "ACT Symbol" in other.columns else "NASDAQ Symbol"
        if sym_col in other.columns:
            tickers += [str(x) for x in other[sym_col].dropna().tolist()]
    except Exception:
        pass

    # Drop footer rows (e.g. "File Creation Time...") and anything that
    # doesn't look like a real ticker, and normalize share classes the way
    # Yahoo Finance expects (BRK.B -> BRK-B). Explicitly cast + validate
    # every entry with a strict regex -- the live Nasdaq Trader file has
    # occasionally shown malformed/footer rows that don't match the
    # documented column layout, so don't trust it to always be clean.
    valid_ticker = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")
    cleaned = []
    for raw in tickers:
        try:
            t = str(raw).strip().upper()
        except Exception:
            continue
        if not t or t == "NAN" or "FILE CREATION TIME" in t:
            continue
        if " " in t:
            continue
        t = t.replace(".", "-")
        if not valid_ticker.match(t):
            continue
        cleaned.append(t)

    cleaned = list(dict.fromkeys(cleaned))
    return cleaned if len(cleaned) > 1000 else None


# ---------------------------------------------------------------------------
# Batch data fetch
# ---------------------------------------------------------------------------

def _download_chunk(chunk, period, max_retries=2, base_backoff=5.0):
    """
    Download one chunk via yfinance, retrying with exponential backoff if the
    whole chunk comes back empty/errored -- which is the usual shape of a
    Yahoo Finance rate limit (YFRateLimitError), not just a bad ticker.
    Individual delisted/bad tickers inside an otherwise-successful chunk are
    NOT retried here; they just come back with no data for that symbol,
    which the caller already handles as a per-ticker miss.
    """
    for attempt in range(max_retries + 1):
        try:
            data = yf.download(
                tickers=chunk, period=period, interval="1d",
                group_by="ticker", auto_adjust=False, threads=True,
                progress=False,
            )
        except Exception:
            data = None

        if data is not None and not data.empty:
            return data

        if attempt < max_retries:
            time.sleep(base_backoff * (attempt + 1))  # 5s, then 10s, ...

    return None


def batch_download(tickers, period="18mo", chunk_size=40, pause=1.5, progress_cb=None):
    """
    Download daily OHLCV for many tickers in chunks (faster + more reliable
    than one ticker per request). Returns {ticker: DataFrame or None}.
    progress_cb(done, total), if given, is called after each chunk.

    Defaults are deliberately conservative (smaller chunks, longer pause)
    to reduce Yahoo Finance rate-limit errors (YFRateLimitError) that show
    up when scanning large universes (thousands of tickers) -- a failed
    chunk is retried with backoff before being given up on.
    """
    results = {}
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    done = 0
    for chunk in chunks:
        data = _download_chunk(chunk, period)

        for t in chunk:
            df = None
            if data is not None and not data.empty:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t] if t in data.columns.get_level_values(0) else None
                    else:
                        sub = data  # single-ticker chunk: flat columns
                    if sub is not None:
                        sub = sub.dropna(how="all")
                        if not sub.empty:
                            df = sub
                except Exception:
                    df = None
            results[t] = df

        done += len(chunk)
        if progress_cb:
            progress_cb(done, len(tickers))
        time.sleep(pause)  # be polite to the data endpoint between chunks

    return results


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------

def run_screener(tickers, threshold=90, period="18mo", chunk_size=60, progress_cb=None):
    """
    Score every ticker in `tickers` and return:
      (hits, errors, market_env)
    - hits: list of result dicts for tickers scoring >= threshold, sorted
      by score descending.
    - errors: list of tickers that had no usable data.
    - market_env: the market_regime() reading computed once against SPY.
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))

    spy_df = None
    try:
        spy_df = fetch_data("SPY", period=period)
    except Exception:
        spy_df = None

    market_env = market_regime(spy_df)

    price_data = batch_download(tickers, period=period, chunk_size=chunk_size, progress_cb=progress_cb)

    hits = []
    errors = []
    for t in tickers:
        df = price_data.get(t)
        if df is None or df.empty:
            errors.append(t)
            continue
        try:
            res = score_breakout_fit(df, spy_df)
        except Exception:
            errors.append(t)
            continue

        if res["rating"] == "INSUFFICIENT DATA":
            errors.append(t)
            continue

        if res["score"] >= threshold:
            det = res["details"]
            m = det.get("momentum", {})
            hits.append({
                "Ticker": t,
                "Score": res["score"],
                "Rating": res["rating"],
                "Last Close": det.get("last_close"),
                "ADR %": det.get("adr_pct"),
                "1m %": m.get("return_1m_pct"),
                "3m %": m.get("return_3m_pct"),
                "6m %": m.get("return_6m_pct"),
                "Flags": " | ".join(res["flags"]) if res["flags"] else "",
            })

    hits.sort(key=lambda r: r["Score"], reverse=True)
    return hits, errors, market_env
