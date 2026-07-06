#!/usr/bin/env python3
"""
kullamagi_score.py

A stock "fit score" calculator modeled on the publicly documented trading
rules of Kristjan Kullamagi (Qullamaggie) - a momentum swing trader known
for three setups: Breakouts, Episodic Pivots (EP), and Parabolic Shorts.

This is an independent, unofficial heuristic tool. It is NOT affiliated
with or endorsed by Kristjan Kullamagi. It translates his publicly shared
rules (ADR%, moving-average trend structure, prior momentum, base quality,
volume, risk sizing) into a 0-100 score so you can quickly triage a ticker
against his Breakout methodology, with flags for possible EP / Parabolic
Short conditions.

Requirements:
    pip install yfinance pandas numpy

Usage:
    python kullamagi_score.py AAPL
    python kullamagi_score.py          (will prompt for a ticker)

Notes:
    - Needs internet access to pull price data from Yahoo Finance via
      yfinance. Run it on your own machine, not inside a sandboxed
      environment with restricted network access.
    - This is educational, not investment advice. See the accompanying
      "Kullamagi Trading Playbook" document for the full rule set and
      caveats.
"""

import sys
import math

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("Missing dependency. Run: pip install numpy pandas yfinance")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Core indicator + scoring logic (pure pandas/numpy, no network calls here so
# it can be unit-tested with synthetic data).
# ---------------------------------------------------------------------------

def compute_adr_pct(df, window=20):
    """Qullamaggie's own ADR% formula: avg of (High/Low) over `window`
    sessions, expressed as a percentage. Source: qullamaggie.com FAQ.
    """
    hl_ratio = df["High"] / df["Low"]
    adr = 100.0 * (hl_ratio.rolling(window=window).mean() - 1.0)
    return adr


def pct_change_over(df, periods):
    close = df["Close"]
    if len(close) <= periods:
        return np.nan
    return 100.0 * (close.iloc[-1] / close.iloc[-1 - periods] - 1.0)


def relative_strength_vs_spy(stock_df, spy_df, periods=63):
    """3-month (63 trading day) return comparison vs SPY."""
    stock_ret = pct_change_over(stock_df, periods)
    spy_ret = pct_change_over(spy_df, periods) if spy_df is not None else np.nan
    if np.isnan(stock_ret) or spy_df is None or np.isnan(spy_ret):
        return stock_ret, spy_ret, np.nan
    return stock_ret, spy_ret, stock_ret - spy_ret


def consolidation_quality(df, lookback=40, recent=10):
    """
    Rough proxy for 'orderly pullback / tight base' quality:
    - range contraction: recent N-day high-low range vs the prior window
    - higher-lows check over the recent window
    - proximity of current close to the recent base high (breakout trigger)
    Returns a dict of raw metrics (0-1 normalized where noted).
    """
    if len(df) < lookback + recent:
        return None

    recent_df = df.iloc[-recent:]
    prior_df = df.iloc[-(lookback):-recent]

    recent_range = (recent_df["High"].max() - recent_df["Low"].min())
    prior_range = (prior_df["High"].max() - prior_df["Low"].min())

    contraction_ratio = np.nan
    if prior_range > 0:
        contraction_ratio = recent_range / prior_range  # <1 = contracting (good)

    lows = recent_df["Low"].values
    higher_low_frac = 0.0
    if len(lows) >= 3:
        ups = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i - 1] * 0.985)
        higher_low_frac = ups / (len(lows) - 1)

    base_high = recent_df["High"].max()
    last_close = df["Close"].iloc[-1]
    dist_to_base_high_pct = 100.0 * (base_high - last_close) / base_high if base_high else np.nan

    return {
        "contraction_ratio": contraction_ratio,
        "higher_low_frac": higher_low_frac,
        "dist_to_base_high_pct": dist_to_base_high_pct,
    }


def volume_profile(df, recent=10, baseline=50):
    if len(df) < baseline:
        return None
    dollar_vol = (df["Close"] * df["Volume"])
    recent_avg = dollar_vol.iloc[-recent:].mean()
    baseline_avg = dollar_vol.iloc[-baseline:-recent].mean() if len(df) >= baseline + recent else dollar_vol.iloc[:-recent].mean()
    last_day_vol = df["Volume"].iloc[-1]
    avg_vol_50 = df["Volume"].iloc[-baseline:].mean()
    return {
        "avg_dollar_vol_recent": recent_avg,
        "avg_dollar_vol_baseline": baseline_avg,
        "last_day_vol_vs_50d_avg": (last_day_vol / avg_vol_50) if avg_vol_50 else np.nan,
    }


def score_breakout_fit(df, spy_df=None):
    """
    Compute a 0-100 'Kullamagi Breakout fit score' plus a category breakdown
    and qualitative flags (possible EP / possible parabolic-short-extended).

    df: DataFrame with columns Open, High, Low, Close, Volume, indexed by date,
        ascending by date, daily bars, at least ~260 rows recommended.
    """
    result = {
        "score": 0,
        "max_score": 100,
        "breakdown": {},
        "flags": [],
        "rating": "",
        "details": {},
    }

    if df is None or len(df) < 60:
        result["rating"] = "INSUFFICIENT DATA"
        result["details"]["note"] = "Need at least ~60 trading days of history."
        return result

    close = df["Close"]
    last_close = close.iloc[-1]

    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean() if len(df) >= 150 else pd.Series([np.nan] * len(df))
    sma200 = close.rolling(200).mean() if len(df) >= 200 else pd.Series([np.nan] * len(df))

    high_252 = df["High"].iloc[-252:].max() if len(df) >= 20 else df["High"].max()
    low_252 = df["Low"].iloc[-252:].min() if len(df) >= 20 else df["Low"].min()

    adr_series = compute_adr_pct(df, 20)
    adr_pct = adr_series.iloc[-1] if not adr_series.empty else np.nan

    # ---------------- 1. Trend template (25 pts) ----------------
    trend_pts = 0
    trend_detail = {}
    c_gt_10 = last_close > ema10.iloc[-1]
    c_gt_20 = last_close > ema20.iloc[-1]
    c_gt_50 = last_close > sma50.iloc[-1] if not math.isnan(sma50.iloc[-1]) else False
    stacked_short = ema10.iloc[-1] > ema20.iloc[-1] > (sma50.iloc[-1] if not math.isnan(sma50.iloc[-1]) else -np.inf)

    trend_pts += 3 if c_gt_10 else 0
    trend_pts += 3 if c_gt_20 else 0
    trend_pts += 4 if c_gt_50 else 0
    trend_pts += 5 if stacked_short else 0

    if not math.isnan(sma150.iloc[-1] if len(df) >= 150 else np.nan):
        c_gt_150 = last_close > sma150.iloc[-1]
        trend_pts += 3 if c_gt_150 else 0
        trend_detail["close_gt_150sma"] = bool(c_gt_150)
        if len(df) >= 200 and not math.isnan(sma200.iloc[-1]):
            stacked_long = sma50.iloc[-1] > sma150.iloc[-1] > sma200.iloc[-1]
            trend_pts += 4 if stacked_long else 0
            trend_detail["long_ma_stacked_50_150_200"] = bool(stacked_long)

    within_25pct_of_high = (high_252 > 0) and ((high_252 - last_close) / high_252 <= 0.25)
    trend_pts += 3 if within_25pct_of_high else 0

    trend_pts = min(trend_pts, 25)
    result["breakdown"]["trend_template"] = {"points": trend_pts, "out_of": 25}
    trend_detail.update({
        "close_gt_10ema": bool(c_gt_10),
        "close_gt_20ema": bool(c_gt_20),
        "close_gt_50sma": bool(c_gt_50),
        "10_20_50_stacked": bool(stacked_short),
        "within_25pct_of_52wk_high": bool(within_25pct_of_high),
    })
    result["details"]["trend"] = trend_detail

    # ---------------- 2. Prior momentum / RS (20 pts) ----------------
    mom_pts = 0
    ret_1m = pct_change_over(df, 22)
    ret_3m = pct_change_over(df, 67)
    ret_6m = pct_change_over(df, 126)

    mom_pts += 5 if (not np.isnan(ret_1m) and ret_1m >= 25) else (3 if (not np.isnan(ret_1m) and ret_1m >= 10) else 0)
    mom_pts += 5 if (not np.isnan(ret_3m) and ret_3m >= 50) else (3 if (not np.isnan(ret_3m) and ret_3m >= 20) else 0)
    mom_pts += 5 if (not np.isnan(ret_6m) and ret_6m >= 100) else (3 if (not np.isnan(ret_6m) and ret_6m >= 40) else 0)

    rs_line = ""
    if spy_df is not None:
        s_ret, spy_ret, excess = relative_strength_vs_spy(df, spy_df, 63)
        if not np.isnan(excess):
            mom_pts += 5 if excess > 0 else 0
            rs_line = f"Stock 3m: {s_ret:.1f}%  SPY 3m: {spy_ret:.1f}%  Excess: {excess:.1f}%"
    mom_pts = min(mom_pts, 20)
    result["breakdown"]["prior_momentum_rs"] = {"points": mom_pts, "out_of": 20}
    result["details"]["momentum"] = {
        "return_1m_pct": None if np.isnan(ret_1m) else round(ret_1m, 1),
        "return_3m_pct": None if np.isnan(ret_3m) else round(ret_3m, 1),
        "return_6m_pct": None if np.isnan(ret_6m) else round(ret_6m, 1),
        "relative_strength_vs_spy": rs_line or "n/a (no SPY data)",
    }

    # ---------------- 3. ADR / volatility (15 pts) ----------------
    adr_pts = 0
    if not np.isnan(adr_pct):
        if 4 <= adr_pct <= 12:
            adr_pts = 15
        elif 2.5 <= adr_pct < 4 or 12 < adr_pct <= 18:
            adr_pts = 8
        else:
            adr_pts = 3
    result["breakdown"]["adr_volatility"] = {"points": adr_pts, "out_of": 15}
    result["details"]["adr_pct"] = None if np.isnan(adr_pct) else round(adr_pct, 2)

    # ---------------- 4. Base / consolidation quality (20 pts) --------
    base_pts = 0
    cq = consolidation_quality(df)
    if cq:
        if not np.isnan(cq["contraction_ratio"]):
            if cq["contraction_ratio"] <= 0.7:
                base_pts += 8
            elif cq["contraction_ratio"] <= 1.0:
                base_pts += 5
        base_pts += round(7 * cq["higher_low_frac"])
        if not np.isnan(cq["dist_to_base_high_pct"]):
            if cq["dist_to_base_high_pct"] <= 5:
                base_pts += 5
            elif cq["dist_to_base_high_pct"] <= 10:
                base_pts += 3
    base_pts = min(base_pts, 20)
    result["breakdown"]["base_quality"] = {"points": base_pts, "out_of": 20}
    result["details"]["consolidation"] = cq

    # ---------------- 5. Volume / liquidity (10 pts) -------------------
    vol_pts = 0
    vp = volume_profile(df)
    if vp:
        if vp["avg_dollar_vol_recent"] and vp["avg_dollar_vol_recent"] >= 500_000:
            vol_pts += 4
        if not np.isnan(vp["last_day_vol_vs_50d_avg"]):
            if vp["last_day_vol_vs_50d_avg"] >= 1.5:
                vol_pts += 4
            elif vp["last_day_vol_vs_50d_avg"] >= 1.0:
                vol_pts += 2
        if vp["avg_dollar_vol_baseline"] and vp["avg_dollar_vol_recent"] < vp["avg_dollar_vol_baseline"]:
            vol_pts += 2  # volume dry-up into the base is a good sign
    vol_pts = min(vol_pts, 10)
    result["breakdown"]["volume_liquidity"] = {"points": vol_pts, "out_of": 10}
    result["details"]["volume"] = vp

    # ---------------- 6. Price floor (10 pts) ---------------------------
    price_pts = 10 if last_close >= 5 else (4 if last_close >= 2 else 0)
    result["breakdown"]["price_floor"] = {"points": price_pts, "out_of": 10}
    result["details"]["last_close"] = round(float(last_close), 2)

    total = trend_pts + mom_pts + adr_pts + base_pts + vol_pts + price_pts
    result["score"] = total

    if total >= 85:
        result["rating"] = "A+ Prime Breakout Candidate"
    elif total >= 70:
        result["rating"] = "B - Strong, watchlist for trigger"
    elif total >= 50:
        result["rating"] = "C - Developing, needs more base/RS"
    else:
        result["rating"] = "D - Not a current fit"

    # ---------------- Qualitative flags: EP / Parabolic short ----------
    if len(df) >= 2:
        prev_close = close.iloc[-2]
        gap_pct = 100.0 * (df["Open"].iloc[-1] - prev_close) / prev_close if prev_close else 0
        if gap_pct >= 10:
            result["flags"].append(
                f"Possible Episodic Pivot: gapped up {gap_pct:.1f}% at the open. "
                "Check for an earnings/news catalyst and first-15-min volume vs. average."
            )

    if len(df) >= 6:
        last6 = close.iloc[-6:]
        up_days = sum(1 for i in range(1, len(last6)) if last6.iloc[i] > last6.iloc[i - 1])
        move_5d = 100.0 * (close.iloc[-1] / close.iloc[-6] - 1.0)
        if up_days >= 4 and move_5d >= 50:
            result["flags"].append(
                f"Possible Parabolic Short setup: {up_days}/5 up days, +{move_5d:.1f}% "
                "over 5 sessions. Extended stocks like this are what Kullamagi looks to "
                "fade, not chase long."
            )

    return result


# ---------------------------------------------------------------------------
# CLI / data-fetch layer (network-dependent; kept separate from scoring logic)
# ---------------------------------------------------------------------------

def fetch_data(ticker, period="18mo"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def print_report(ticker, result):
    print("=" * 60)
    print(f" Kullamagi Breakout Fit Score: {ticker.upper()}")
    print("=" * 60)
    print(f" Score: {result['score']} / {result['max_score']}   ->  {result['rating']}")
    print("-" * 60)
    for name, d in result["breakdown"].items():
        label = name.replace("_", " ").title()
        print(f"  {label:<28} {d['points']:>3} / {d['out_of']}")
    print("-" * 60)
    det = result["details"]
    if "last_close" in det:
        print(f"  Last close: ${det['last_close']}")
    if "adr_pct" in det and det["adr_pct"] is not None:
        print(f"  ADR% (20d): {det['adr_pct']}%")
    if "momentum" in det:
        m = det["momentum"]
        print(f"  Returns  1m: {m['return_1m_pct']}%   3m: {m['return_3m_pct']}%   6m: {m['return_6m_pct']}%")
        print(f"  {m['relative_strength_vs_spy']}")
    if "consolidation" in det and det["consolidation"]:
        c = det["consolidation"]
        print(f"  Base contraction ratio: {c['contraction_ratio']:.2f} (lower = tighter)")
        print(f"  Higher-low frequency (last 10d): {c['higher_low_frac']*100:.0f}%")
        print(f"  Distance to base high: {c['dist_to_base_high_pct']:.1f}%")
    if result["flags"]:
        print("-" * 60)
        print("  Flags:")
        for f in result["flags"]:
            print(f"   - {f}")
    print("=" * 60)
    print("Educational tool only. Not financial advice. Not affiliated with")
    print("Kristjan Kullamagi / Qullamaggie.")


def main():
    if len(sys.argv) > 1:
        ticker = sys.argv[1].strip().upper()
    else:
        ticker = input("Enter a stock ticker: ").strip().upper()

    if not ticker:
        print("No ticker entered.")
        return

    print(f"Fetching data for {ticker}...")
    try:
        df = fetch_data(ticker)
    except Exception as e:
        print(f"Error fetching data: {e}")
        print("Make sure you have internet access and 'yfinance' installed "
              "(pip install yfinance).")
        return

    if df is None:
        print(f"No data found for '{ticker}'. Check the symbol and try again.")
        return

    spy_df = None
    try:
        spy_df = fetch_data("SPY")
    except Exception:
        pass

    result = score_breakout_fit(df, spy_df)
    print_report(ticker, result)


if __name__ == "__main__":
    main()
