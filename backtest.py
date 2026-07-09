"""
backtest.py

Single-ticker historical backtest for Kullamagi's Breakout / "Momentum
Burst" setup -- the one setup whose entry and stop are derivable purely
from DAILY bars (no dependence on intraday 5-minute data), which makes it
the only one of the three setups that can be backtested accurately over
many years of history. EP and Parabolic Short both key off real intraday
bars for their exact entry (first 5-minute bar high / opening range low)
per the book, and Yahoo Finance only retains ~60 days of 5-minute history,
so a multi-year backtest of those two isn't attempted here.

IMPORTANT BOOK-FIDELITY CAVEAT -- the "leading stock" approximation:
The live screener (screen_breakouts in kullamagi_setups.py) defines
"leading stock" as ranking in the top 1-2% of 1/3/6-month returns WITHIN
THE SPECIFIC BATCH OF TICKERS SCANNED THAT DAY -- a cross-sectional,
batch-relative rule. A single-ticker backtest has no batch to rank
against at each historical date (reconstructing the actual top 1-2% of
the whole market on every past trading day would mean re-running the
full multi-thousand-ticker screener for every single day of history,
which isn't practical here). Instead, this backtest substitutes a fixed
ABSOLUTE return threshold for each of the 1/3/6-month windows -- a stock
must clear at least one of them, matching the live screener's "OR" logic
across windows, but the specific thresholds are a rough proxy for
"roughly top 1-2% of the market," not a reconstruction of the actual
historical rank. Treat backtest results as illustrative of what the
MECHANICAL rest of the setup (consolidation + ADTR-capped stop + book's
own exit rules) would have done on a stock that was clearly a strong
momentum name, not as a literal replay of the live screener.

Trade simulation, once a setup is validated as of some day's close:
  1. Entry trigger: the first day, within a lookahead window, whose HIGH
     reaches the consolidation high (the breakout level). If that day's
     OPEN already gapped above the trigger, entry is at the open (you
     can't get filled at a level price already gapped past); otherwise
     entry is at the trigger level itself.
  2. Stop: the consolidation low (already validated to be within 1x ADTR
     of the trigger price, per the book's rule -- setups failing that
     check are skipped, same as the live screener).
  3. Partial exit (book: "take a partial profit during the first three to
     five days"): operationalized as the earlier of (a) the first close,
     from day 2 through day `partial_max_days` after entry, at or above a
     2R target, or (b) the close of day `partial_max_days` itself if 2R is
     never reached. If the stop is hit first, the WHOLE position exits at
     the stop -- no partial ever occurs.
  4. Remainder: after a partial, book says move the stop to breakeven,
     then trail with "a close below either the 10-day or 20-day moving
     average." Simulated here as: exit the remaining half at breakeven if
     price falls back to it first, otherwise at the first close below
     either EMA.
  5. R-multiple accounting: each trade's result is a blended R -- 50% at
     the partial's R-multiple, 50% at the remainder's R-multiple (or 100%
     at -1R-equivalent if stopped out before any partial).

This is ONE reasonable, clearly-labeled operationalization of qualitative
book language ("during the first three to five days," "most of the time")
-- not the only valid one. Adjust the parameters below to explore others.
"""

import numpy as np
import pandas as pd

from kullamagi_setups import compute_adtr


def _pct_change_at(close, idx, periods):
    if idx - periods < 0:
        return np.nan
    prev = close.iloc[idx - periods]
    if prev == 0 or pd.isna(prev):
        return np.nan
    return 100.0 * (close.iloc[idx] / prev - 1.0)


def backtest_breakout(
    df,
    min_ret_1m=25.0,
    min_ret_3m=40.0,
    min_ret_6m=75.0,
    consolidation_days=10,
    trigger_lookahead_days=20,
    partial_r_target=2.0,
    partial_max_days=5,
):
    """
    Replays Kullamagi's Breakout setup over a single ticker's full daily
    history and simulates every occurrence mechanically (see module
    docstring for the exact rules and their book-fidelity caveats).

    df: daily OHLCV DataFrame, ascending by date, with a DatetimeIndex.
    min_ret_1m/3m/6m: absolute % return thresholds standing in for the live
        screener's batch-relative "top 1-2%" leading-stock rule (a stock
        qualifies if it clears ANY ONE of the three, same OR logic as the
        live screener).
    consolidation_days: length of the base window (book: "about one to
        three weeks" -- default 10 trading days ~ 2 weeks).
    trigger_lookahead_days: how many days after a setup is validated to
        keep waiting for an actual breakout above the base high before
        giving up on that occurrence (setups don't stay valid forever).
    partial_r_target: the R-multiple used as the partial-profit trigger
        (book: "sell 1/3-1/2... at 2-3R" -- default 2R, the earlier/more
        conservative end).
    partial_max_days: latest day (relative to entry) the partial exit is
        forced to occur if 2R hasn't been reached yet (book: "during the
        first three to five days" -- default 5).

    Returns (trades, note):
      trades: list of dicts, one per simulated occurrence (see fields in
        the code below).
      note: a string explaining why no backtest could run (insufficient
        history), or None if it ran normally (an empty trades list with
        note=None just means no occurrences were found).
    """
    if df is None or len(df) < 150:
        return [], "Not enough history (need at least ~150 trading days -- roughly 6-7 months)."

    df = df.sort_index()
    close, high, low, open_ = df["Close"], df["High"], df["Low"], df["Open"]
    n = len(df)

    adtr = compute_adtr(df)
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()

    trades = []
    i = 130  # first index with enough lookback for the 6-month return window
    while i < n - 1:
        ret_1m = _pct_change_at(close, i, 22)
        ret_3m = _pct_change_at(close, i, 67)
        ret_6m = _pct_change_at(close, i, 126)
        leading = (
            (not np.isnan(ret_1m) and ret_1m >= min_ret_1m)
            or (not np.isnan(ret_3m) and ret_3m >= min_ret_3m)
            or (not np.isnan(ret_6m) and ret_6m >= min_ret_6m)
        )
        if not leading:
            i += 1
            continue

        if not (close.iloc[i] >= ema10.iloc[i] or close.iloc[i] >= ema20.iloc[i]):
            i += 1
            continue

        win_start = i - consolidation_days + 1
        if win_start < 0:
            i += 1
            continue
        base_high = float(high.iloc[win_start : i + 1].max())
        base_low = float(low.iloc[win_start : i + 1].min())

        prior_start = win_start - consolidation_days * 3
        if prior_start >= 0:
            prior_high = float(high.iloc[prior_start:win_start].max())
            prior_low = float(low.iloc[prior_start:win_start].min())
            prior_range = prior_high - prior_low
            recent_range = base_high - base_low
            if prior_range > 0 and (recent_range / prior_range) > 1.0:
                i += 1
                continue  # not actually contracting

        cur_adtr = adtr.iloc[i]
        stop = base_low
        risk_per_share = base_high - stop
        if pd.isna(cur_adtr) or risk_per_share <= 0 or risk_per_share > cur_adtr:
            i += 1
            continue

        # Setup validated as of day i. Look forward for the actual
        # breakout trigger (high reaching the base high), abandoning if
        # the base breaks down (a new low under the stop) first.
        trigger_idx = None
        for j in range(i + 1, min(i + 1 + trigger_lookahead_days, n)):
            if low.iloc[j] < stop:
                break
            if high.iloc[j] >= base_high:
                trigger_idx = j
                break
        if trigger_idx is None:
            i += 1
            continue

        entry_price = float(open_.iloc[trigger_idx]) if open_.iloc[trigger_idx] > base_high else base_high
        r_per_share = entry_price - stop
        if r_per_share <= 0:
            i = trigger_idx + 1
            continue

        target_2r = entry_price + partial_r_target * r_per_share

        stopped_out_idx = None
        partial_exit_idx = None
        for k in range(trigger_idx, min(trigger_idx + partial_max_days + 1, n)):
            if low.iloc[k] <= stop:
                stopped_out_idx = k
                break
            if k > trigger_idx and close.iloc[k] >= target_2r:
                partial_exit_idx = k
                break
        if stopped_out_idx is None and partial_exit_idx is None:
            partial_exit_idx = min(trigger_idx + partial_max_days, n - 1)

        if stopped_out_idx is not None:
            r_multiple = (stop - entry_price) / r_per_share  # == -1.0 by construction
            trades.append({
                "setup_date": df.index[i],
                "entry_date": df.index[trigger_idx],
                "entry": round(entry_price, 2),
                "stop": round(stop, 2),
                "partial_exit_date": None,
                "partial_exit": None,
                "remainder_exit_date": df.index[stopped_out_idx],
                "remainder_exit": round(stop, 2),
                "outcome": "Stopped out (full position, before any partial)",
                "r_multiple": round(r_multiple, 2),
                "holding_days": stopped_out_idx - trigger_idx,
                "still_open": False,
            })
            i = stopped_out_idx + 1
            continue

        partial_exit_price = float(close.iloc[partial_exit_idx])
        partial_r = (partial_exit_price - entry_price) / r_per_share
        breakeven_stop = entry_price

        remainder_exit_idx = None
        remainder_exit_price = None
        for m in range(partial_exit_idx + 1, n):
            if low.iloc[m] <= breakeven_stop:
                remainder_exit_idx, remainder_exit_price = m, breakeven_stop
                break
            if close.iloc[m] < ema10.iloc[m] or close.iloc[m] < ema20.iloc[m]:
                remainder_exit_idx, remainder_exit_price = m, float(close.iloc[m])
                break

        still_open = remainder_exit_idx is None
        if still_open:
            remainder_exit_idx = n - 1
            remainder_exit_price = float(close.iloc[-1])

        remainder_r = (remainder_exit_price - entry_price) / r_per_share
        blended_r = 0.5 * partial_r + 0.5 * remainder_r

        trades.append({
            "setup_date": df.index[i],
            "entry_date": df.index[trigger_idx],
            "entry": round(entry_price, 2),
            "stop": round(stop, 2),
            "partial_exit_date": df.index[partial_exit_idx],
            "partial_exit": round(partial_exit_price, 2),
            "remainder_exit_date": df.index[remainder_exit_idx] if not still_open else None,
            "remainder_exit": round(remainder_exit_price, 2),
            "outcome": "Still open (ran out of history)" if still_open else "Closed",
            "r_multiple": round(blended_r, 2),
            "holding_days": remainder_exit_idx - trigger_idx,
            "still_open": still_open,
        })

        i = (n if still_open else remainder_exit_idx) + 1

    return trades, None


def summarize_trades(trades):
    """Aggregate stats over CLOSED trades only (an open trade's R-multiple
    is unrealized, so it's shown separately, not blended into the stats)."""
    closed = [t for t in trades if not t.get("still_open")]
    open_trades = [t for t in trades if t.get("still_open")]

    if not closed:
        return {
            "total_trades": 0,
            "open_trades": len(open_trades),
            "win_rate_pct": None,
            "avg_r": None,
            "total_r": None,
            "best_r": None,
            "worst_r": None,
            "avg_holding_days": None,
        }

    rs = [t["r_multiple"] for t in closed]
    wins = [r for r in rs if r > 0]
    return {
        "total_trades": len(closed),
        "open_trades": len(open_trades),
        "win_rate_pct": round(100.0 * len(wins) / len(closed), 1),
        "avg_r": round(sum(rs) / len(rs), 2),
        "total_r": round(sum(rs), 2),
        "best_r": round(max(rs), 2),
        "worst_r": round(min(rs), 2),
        "avg_holding_days": round(sum(t["holding_days"] for t in closed) / len(closed), 1),
    }
