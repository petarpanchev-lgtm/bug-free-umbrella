"""
kullamagi_setups.py

Screeners and trade-planning calculators for Kristjan Kullamagi's (Qullamaggie)
three setups -- Breakout ("Momentum Burst"), Episodic Pivot (EP), and
Parabolic Short -- built ONLY from what he states in his own words in his
interview in Jack Schwager & George F. Coyle's "Market Wizards: The Next
Generation" (Chapter 1). No thresholds from his blog, FAQ, or third-party
scanner write-ups are used here -- every number below is a direct or
lightly-operationalized version of a specific line from that interview.
Anywhere the book only gives a qualitative description (e.g. "neglected
stock"), that is called out explicitly as an approximation.

Book citations used (paraphrased close to verbatim):

Breakout / "Momentum Burst":
  - "[Bonde] found that when stocks make explosive moves, most of the move
    is over in three to five days. That's the holding period."
  - "...look for a stock in an uptrend that then goes into a sideways
    consolidation, preferably on reduced volume... buy the stock when it
    breaks out of the consolidation and hold it for three to five days."
  - "One way to identify [leading stocks] is to scan for the 1% or 2% stocks
    with the largest upmoves in the past one, three, and six months."
  - "I usually look for shorter consolidations -- about one to three weeks."
  - "The stop would be at the low of the day. There is an added condition
    that the stop should be no wider than the average daily true range
    (ADTR)... If the low is more than the ADTR below the current price,
    then I wouldn't take the trade."
  - "I will take a partial profit during the first three to five days and
    move the stop up to break even... then use a close below either a
    10-day or 20-day moving average as a trailing stop."
  - Market filter: "I use the 10-day and 20-day moving averages. When they
    are both moving up, the market is in an uptrend... When the 10-day
    crosses below the 20-day, that's a sign of caution" -- applies to
    Breakout and EP, NOT Parabolic Short ("For the parabolic short trade,
    it doesn't matter what kind of market you are in").

Episodic Pivot (EP):
  - "I look for stocks up at least 10% on high volume."
  - "...suddenly, it has 10 times its average daily volume."
  - "The best episodic pivot trade is a neglected stock... going sideways
    for a long time -- months, even years."
  - "If the opening volume is large enough, I will buy on a move above the
    high of the first 5-minute bar. Sometimes, I need to wait longer... and
    I will buy on a move above the first 1-hour price bar."
  - "Where is your protective stop on the trade? The low of the day."

Parabolic Short:
  - "In an A+ setup, the stock is up three or four days in a row with a
    total gain of at least 300%... I never go short on day one... I rarely
    short on day two. I usually wait for that third or fourth day."
    (Schwager's Take separately notes the entry can land on "day three,
    four, or five.")
  - "The short trigger could be breaking the opening range lows or...
    breaking below a 5-minute candle bar."
  - "Would your stop be at the high of the day? Yes, most of the time."
  - Market-agnostic: "For the parabolic short trade, it doesn't matter what
    kind of market you are in."

Risk/position sizing (applies to all three; not setup-specific in the book):
  - "Typically, I will risk 0.5% or less of my account size per trade, but
    I may risk up to a maximum of 1% on some trades."
"""

import numpy as np
import pandas as pd

from kullamagi_score import fetch_data, market_regime  # reuse, don't duplicate


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def compute_adtr(df, window=20):
    """Average Daily TRUE Range in price units (not %), over `window` days.
    True range = max(high-low, |high-prev_close|, |low-prev_close|).
    This is the exact metric Kullamagi cites for his stop-distance rule.
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()


def _pct_change_over(df, periods):
    close = df["Close"]
    if len(close) <= periods:
        return np.nan
    return 100.0 * (close.iloc[-1] / close.iloc[-1 - periods] - 1.0)


def consecutive_up_run(df, max_run=8):
    """
    Length of the run of consecutive up-days ending at the last bar, and the
    cumulative % gain from the close just before the run started to the
    last close. Used for the Parabolic Short setup ("up three or four days
    in a row").
    """
    close = df["Close"]
    if len(close) < 2:
        return 0, np.nan
    run = 0
    for i in range(len(close) - 1, 0, -1):
        if close.iloc[i] > close.iloc[i - 1]:
            run += 1
            if run >= max_run:
                break
        else:
            break
    if run == 0:
        return 0, np.nan
    start_idx = len(close) - 1 - run
    if start_idx < 0:
        return run, np.nan
    cum_gain = 100.0 * (close.iloc[-1] / close.iloc[start_idx] - 1.0)
    return run, cum_gain


def fetch_intraday_5m(ticker):
    """
    Fetch the most recent session's 5-minute bars (needed for the EP and
    Parabolic Short calculators' exact entry/stop rules -- the first
    5-minute bar's high/low, and the running day high/low). Returns None if
    unavailable (outside market hours, data-provider limits, etc.); callers
    must fall back to a daily-bar approximation and say so.
    """
    import yfinance as yf
    try:
        df = yf.download(ticker, period="5d", interval="5m", auto_adjust=False, progress=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(how="all")
    if df.empty:
        return None
    last_date = df.index[-1].date()
    today_bars = df[df.index.date == last_date]
    return today_bars if not today_bars.empty else None


# ---------------------------------------------------------------------------
# 1. Breakout ("Momentum Burst") screener
# ---------------------------------------------------------------------------

def screen_breakouts(price_data, top_pct=2.0, consolidation_days=10, near_trigger_pct=5.0):
    """
    Flags tickers matching Kullamagi's Breakout / Momentum Burst setup,
    using only book-stated conditions:
      1) Leading stock: return over 1, 3, or 6 months ranks in the top
         `top_pct` percent of the SCANNED BATCH (book: "scan for the 1% or
         2% stocks with the largest upmoves in the past one, three, and six
         months").
      2) A recent consolidation of about `consolidation_days` trading days
         (book: "shorter consolidations -- about one to three weeks", so
         default 10 days ~ 2 weeks), following an uptrend, ideally on
         reduced volume, with price holding above its 10- and/or 20-day MA
         ("surfing" the moving average).
      3) The stop (the consolidation low, standing in for "the low of the
         day" until you're actually in the trade) must not be wider than 1x
         ADTR (book's explicit rule -- otherwise "I wouldn't take the
         trade").

    Returns (hits, errors) -- hits is a list of dicts for tickers meeting
    ALL three conditions, sorted by 1-month return descending.
    """
    tickers = list(price_data.keys())
    rows = {}
    for t, df in price_data.items():
        if df is None or df.empty or len(df) < 130:
            continue
        rows[t] = {
            "ret_1m": _pct_change_over(df, 22),
            "ret_3m": _pct_change_over(df, 67),
            "ret_6m": _pct_change_over(df, 126),
        }

    if not rows:
        return [], list(price_data.keys())

    ret1 = [r["ret_1m"] for r in rows.values() if not np.isnan(r["ret_1m"])]
    ret3 = [r["ret_3m"] for r in rows.values() if not np.isnan(r["ret_3m"])]
    ret6 = [r["ret_6m"] for r in rows.values() if not np.isnan(r["ret_6m"])]

    thresh_1m = np.percentile(ret1, 100 - top_pct) if ret1 else np.inf
    thresh_3m = np.percentile(ret3, 100 - top_pct) if ret3 else np.inf
    thresh_6m = np.percentile(ret6, 100 - top_pct) if ret6 else np.inf

    hits, errors = [], []
    for t in tickers:
        df = price_data.get(t)
        if t not in rows:
            errors.append(t)
            continue

        r = rows[t]
        leading_windows = []
        if not np.isnan(r["ret_1m"]) and r["ret_1m"] >= thresh_1m:
            leading_windows.append("1m")
        if not np.isnan(r["ret_3m"]) and r["ret_3m"] >= thresh_3m:
            leading_windows.append("3m")
        if not np.isnan(r["ret_6m"]) and r["ret_6m"] >= thresh_6m:
            leading_windows.append("6m")

        if not leading_windows:
            continue  # not a "leading stock" -- book requires this first

        close = df["Close"]
        last_close = close.iloc[-1]
        ema10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        surfing_10 = last_close >= ema10
        surfing_20 = last_close >= ema20
        if not (surfing_10 or surfing_20):
            continue  # not "surfing" its moving average

        window = df.iloc[-consolidation_days:]
        prior = df.iloc[-(consolidation_days * 3):-consolidation_days] if len(df) >= consolidation_days * 4 else None
        base_high = window["High"].max()
        base_low = window["Low"].min()
        contraction_ratio = np.nan
        if prior is not None and len(prior) > 0:
            prior_range = prior["High"].max() - prior["Low"].min()
            recent_range = base_high - base_low
            if prior_range > 0:
                contraction_ratio = recent_range / prior_range
        if not np.isnan(contraction_ratio) and contraction_ratio > 1.0:
            continue  # not actually contracting -- not a tight consolidation

        adtr = compute_adtr(df).iloc[-1]
        stop_distance = last_close - base_low
        adtr_ok = (not np.isnan(adtr)) and stop_distance <= adtr

        if not adtr_ok:
            continue  # book: skip the trade if stop is wider than 1x ADTR

        dist_to_trigger_pct = 100.0 * (base_high - last_close) / base_high if base_high else np.nan
        near_trigger = (not np.isnan(dist_to_trigger_pct)) and dist_to_trigger_pct <= near_trigger_pct
        already_triggered = last_close >= base_high

        hits.append({
            "Ticker": t,
            "Last Close": round(float(last_close), 2),
            "Leading (windows)": "/".join(leading_windows),
            "1m %": None if np.isnan(r["ret_1m"]) else round(r["ret_1m"], 1),
            "3m %": None if np.isnan(r["ret_3m"]) else round(r["ret_3m"], 1),
            "6m %": None if np.isnan(r["ret_6m"]) else round(r["ret_6m"], 1),
            "Base High (trigger)": round(float(base_high), 2),
            "Base Low (stop)": round(float(base_low), 2),
            "ADTR ($)": round(float(adtr), 2) if not np.isnan(adtr) else None,
            "Contraction Ratio": None if np.isnan(contraction_ratio) else round(contraction_ratio, 2),
            "Status": "Already triggered" if already_triggered else (
                f"Within {near_trigger_pct:.0f}% of trigger" if near_trigger else "Building base"
            ),
        })

    hits.sort(key=lambda r: (r["1m %"] if r["1m %"] is not None else -999), reverse=True)
    return hits, errors


# ---------------------------------------------------------------------------
# 2. Episodic Pivot screener
# ---------------------------------------------------------------------------

def screen_episodic_pivots(price_data, min_gap_pct=10.0, min_volume_multiple=3.0,
                            dormancy_days=126, dormancy_range_pct=40.0):
    """
    Flags tickers matching Kullamagi's Episodic Pivot setup, using only
    book-stated conditions:
      1) Gap up of at least `min_gap_pct` at the open (book: "I look for
         stocks up at least 10% on high volume").
      2) Volume well above average. Book figure is "10 times its average
         daily volume" for the OPENING surge specifically; this screener
         compares the full day's volume to the 50-day average as a coarser
         daily-bar proxy, so the default threshold (`min_volume_multiple`)
         is set lower than 10x on purpose -- raise it toward 10x if you
         want to approximate his literal bar more strictly.
      3) "Neglected" stock: book says the best EPs come from a stock that
         was flat/range-bound for "months, even years" beforehand. This is
         approximated as: the stock's trading range over the
         `dormancy_days` (default ~6 months) before the gap stayed within
         `dormancy_range_pct` of its midpoint. This is NOT a strict
         requirement in the book ("not necessarily") -- shown as an info
         column, not a hard filter.

    A real news catalyst is REQUIRED per Kullamagi but cannot be verified
    from price data alone -- always confirm one manually before trading
    anything this screener surfaces.

    Returns (hits, errors).
    """
    hits, errors = [], []
    for t, df in price_data.items():
        if df is None or df.empty or len(df) < 55:
            errors.append(t)
            continue

        prior_close = df["Close"].iloc[-2]
        today = df.iloc[-1]
        if prior_close == 0 or np.isnan(prior_close):
            errors.append(t)
            continue

        gap_pct = 100.0 * (today["Open"] - prior_close) / prior_close
        if gap_pct < min_gap_pct:
            continue

        avg_vol_50 = df["Volume"].iloc[-51:-1].mean()
        vol_multiple = (today["Volume"] / avg_vol_50) if avg_vol_50 else np.nan
        if np.isnan(vol_multiple) or vol_multiple < min_volume_multiple:
            continue

        dormant = None
        if len(df) >= dormancy_days + 2:
            window = df["Close"].iloc[-(dormancy_days + 1):-1]
            mid = window.median()
            rng_pct = 100.0 * (window.max() - window.min()) / mid if mid else np.nan
            dormant = (not np.isnan(rng_pct)) and rng_pct <= dormancy_range_pct

        hits.append({
            "Ticker": t,
            "Gap %": round(float(gap_pct), 1),
            "Volume vs 50d Avg": round(float(vol_multiple), 1),
            "Was Dormant (~6mo)": "Yes" if dormant else ("No" if dormant is not None else "n/a"),
            "Today's Open": round(float(today["Open"]), 2),
            "Today's Low (stop)": round(float(today["Low"]), 2),
            "Note": "Confirm a genuine catalyst (earnings/FDA/contract/etc.) manually -- not screenable from price data.",
        })

    hits.sort(key=lambda r: r["Volume vs 50d Avg"], reverse=True)
    return hits, errors


# ---------------------------------------------------------------------------
# 3. Parabolic Short screener
# ---------------------------------------------------------------------------

def screen_parabolic_shorts(price_data, min_run_days=3, max_run_days=5, min_gain_pct=300.0):
    """
    Flags tickers matching Kullamagi's Parabolic Short "A+" setup, using
    only the book's own definition:
      "In an A+ setup, the stock is up three or four days in a row with a
      total gain of at least 300%." He never shorts day one, rarely day
      two, and typically waits for day three, four, or (per Schwager's
      summary) sometimes five.

    Finds the run of consecutive up days ending at the most recent bar and
    flags it if the run length is within [min_run_days, max_run_days] and
    the cumulative gain over that run is >= min_gain_pct.

    The actual entry still requires an intraday sign of weakness (a break
    of the opening range low, or a break below a 5-minute candle) -- this
    is a candidate list, not a trigger signal.

    Returns (hits, errors).
    """
    hits, errors = [], []
    for t, df in price_data.items():
        if df is None or df.empty or len(df) < max_run_days + 2:
            errors.append(t)
            continue

        run, cum_gain = consecutive_up_run(df, max_run=max_run_days + 2)
        if run < min_run_days or run > max_run_days:
            continue
        if np.isnan(cum_gain) or cum_gain < min_gain_pct:
            continue

        last_close = df["Close"].iloc[-1]
        today_high = df["High"].iloc[-1]

        hits.append({
            "Ticker": t,
            "Consecutive Up Days": run,
            "Cumulative Gain %": round(float(cum_gain), 1),
            "Last Close": round(float(last_close), 2),
            "Today's High (stop)": round(float(today_high), 2),
            "A+ Setup": "Yes" if (run in (3, 4, 5) and cum_gain >= min_gain_pct) else "Borderline",
            "Note": "Wait for an intraday sign of weakness (break of opening range low, "
                    "or break below a 5-minute candle) before entering -- do not short strength blindly.",
        })

    hits.sort(key=lambda r: r["Cumulative Gain %"], reverse=True)
    return hits, errors


# ---------------------------------------------------------------------------
# Calculators (single ticker, manual entry)
# ---------------------------------------------------------------------------

def _position_size(account_size, risk_pct, risk_per_share):
    if risk_per_share is None or risk_per_share <= 0:
        return 0, 0.0, 0.0
    risk_dollars = account_size * (risk_pct / 100.0)
    shares = int(risk_dollars // risk_per_share)
    position_value = shares * 0.0  # filled in by caller with entry price
    return shares, risk_dollars, position_value


def calc_breakout_trade(df, account_size, risk_pct=0.5, consolidation_days=10):
    """
    Kullamagi Breakout trade planner (book rules only):
      - Entry: the high of the recent consolidation (stand-in for "breaking
        out of the consolidation"; the book's intraday variants are the
        high of the first 5-, 30-, or 60-minute bar).
      - Stop: the consolidation low (stand-in for "the low of the day" --
        once you're actually in the trade, use that day's real low).
      - Must-not-exceed-1x-ADTR stop rule: if the distance from entry to
        stop is wider than 1x ADTR, the book says skip the trade.
      - Risk: 0.5% typical, up to 1% max.
      - Targets: 1R/2R/3R, with the book's rule to sell 1/3-1/2 in the
        first 3-5 days (or at 2-3R) and trail the remainder with a close
        below the 10- or 20-day moving average.
    """
    close = df["Close"]
    last_close = close.iloc[-1]
    window = df.iloc[-consolidation_days:]
    entry = float(window["High"].max())
    stop = float(window["Low"].min())
    adtr = compute_adtr(df).iloc[-1]
    risk_per_share = entry - stop
    valid = (not np.isnan(adtr)) and risk_per_share <= adtr

    shares = int((account_size * risk_pct / 100.0) // risk_per_share) if risk_per_share > 0 else 0
    position_value = shares * entry
    ema10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]

    return {
        "setup": "Breakout / Momentum Burst",
        "last_close": round(float(last_close), 2),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "risk_per_share": round(risk_per_share, 2),
        "adtr": round(float(adtr), 2) if not np.isnan(adtr) else None,
        "stop_within_adtr": bool(valid),
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct_of_account": round(100 * position_value / account_size, 1) if account_size else None,
        "risk_dollars": round(account_size * risk_pct / 100.0, 2),
        "targets": {
            "1R": round(entry + risk_per_share, 2),
            "2R": round(entry + 2 * risk_per_share, 2),
            "3R": round(entry + 3 * risk_per_share, 2),
        },
        "ema10": round(float(ema10), 2),
        "ema20": round(float(ema20), 2),
        "note": ("Book rule: sell 1/3-1/2 of the position in the first 3-5 days or at "
                 "2-3R, move stop to breakeven, then trail the rest with a close below "
                 "the 10- or 20-day MA."),
    }


def calc_episodic_pivot_trade(daily_df, intraday_df, account_size, risk_pct=0.5,
                               min_gap_pct=10.0, min_volume_multiple=3.0):
    """
    Kullamagi Episodic Pivot trade planner (book rules only):
      - Entry: "buy on a move above the high of the first 5-minute bar" if
        opening volume already confirms; otherwise "the first 1-hour price
        bar." Uses real intraday data if available; otherwise falls back
        to today's open as a rough stand-in (clearly flagged).
      - Stop: "the low of the day." Uses the running intraday low if
        available; otherwise today's daily low as a rough stand-in.
      - Checks: gap >= 10% at the open; volume well above average (book
        says ~10x average daily volume for the opening surge -- this daily
        approximation compares full-day volume to the 50-day average, so
        the default threshold is set lower than 10x on purpose).
    """
    prior_close = daily_df["Close"].iloc[-2]
    today = daily_df.iloc[-1]
    gap_pct = 100.0 * (today["Open"] - prior_close) / prior_close if prior_close else np.nan
    avg_vol_50 = daily_df["Volume"].iloc[-51:-1].mean()
    vol_multiple = (today["Volume"] / avg_vol_50) if avg_vol_50 else np.nan

    used_intraday = intraday_df is not None and not intraday_df.empty
    if used_intraday:
        entry = float(intraday_df["High"].iloc[0])
        stop = float(intraday_df["Low"].min())
    else:
        entry = float(today["Open"])
        stop = float(today["Low"])

    risk_per_share = entry - stop
    shares = int((account_size * risk_pct / 100.0) // risk_per_share) if risk_per_share > 0 else 0
    position_value = shares * entry

    return {
        "setup": "Episodic Pivot",
        "gap_pct": round(float(gap_pct), 1) if not np.isnan(gap_pct) else None,
        "gap_ok": (not np.isnan(gap_pct)) and gap_pct >= min_gap_pct,
        "volume_multiple": round(float(vol_multiple), 1) if not np.isnan(vol_multiple) else None,
        "volume_ok": (not np.isnan(vol_multiple)) and vol_multiple >= min_volume_multiple,
        "used_intraday_data": used_intraday,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "risk_per_share": round(risk_per_share, 2) if risk_per_share else None,
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct_of_account": round(100 * position_value / account_size, 1) if account_size else None,
        "risk_dollars": round(account_size * risk_pct / 100.0, 2),
        "targets": {
            "1R": round(entry + risk_per_share, 2) if risk_per_share else None,
            "2R": round(entry + 2 * risk_per_share, 2) if risk_per_share else None,
            "3R": round(entry + 3 * risk_per_share, 2) if risk_per_share else None,
        },
        "note": ("Verify a genuine catalyst (earnings beat, FDA approval, major "
                 "contract, etc.) manually -- the book requires it but it isn't "
                 "screenable from price data.") + (
            "" if used_intraday else
            " No intraday data available -- entry/stop use today's open/low as a "
            "rough stand-in; confirm the real opening-range high/low before trading."
        ),
    }


def calc_parabolic_short_trade(daily_df, intraday_df, account_size, risk_pct=0.5,
                                min_run_days=3, max_run_days=5, min_gain_pct=300.0):
    """
    Kullamagi Parabolic Short trade planner (book rules only):
      - Entry (short trigger): "breaking the opening range lows or...
        breaking below a 5-minute candle bar." Uses real intraday data if
        available (first 5-minute bar's low); otherwise falls back to
        today's daily low as a rough stand-in (clearly flagged).
      - Stop: "the high of the day." Uses the running intraday high if
        available; otherwise today's daily high.
      - Context checks: run length of consecutive up days (book: "three or
        four days in a row," never day one, rarely day two) and cumulative
        gain over that run (book: "a total gain of at least 300%").
    """
    run, cum_gain = consecutive_up_run(daily_df, max_run=max_run_days + 2)

    used_intraday = intraday_df is not None and not intraday_df.empty
    if used_intraday:
        entry = float(intraday_df["Low"].iloc[0])
        stop = float(intraday_df["High"].max())
    else:
        entry = float(daily_df["Low"].iloc[-1])
        stop = float(daily_df["High"].iloc[-1])

    risk_per_share = stop - entry  # short: risk is stop above entry
    shares = int((account_size * risk_pct / 100.0) // risk_per_share) if risk_per_share > 0 else 0
    position_value = shares * entry

    return {
        "setup": "Parabolic Short",
        "consecutive_up_days": run,
        "cumulative_gain_pct": None if np.isnan(cum_gain) else round(float(cum_gain), 1),
        "a_plus_setup": bool(run in (3, 4, 5) and (not np.isnan(cum_gain)) and cum_gain >= min_gain_pct),
        "used_intraday_data": used_intraday,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "risk_per_share": round(risk_per_share, 2) if risk_per_share else None,
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct_of_account": round(100 * position_value / account_size, 1) if account_size else None,
        "risk_dollars": round(account_size * risk_pct / 100.0, 2),
        "targets": {
            "1R": round(entry - risk_per_share, 2) if risk_per_share else None,
            "2R": round(entry - 2 * risk_per_share, 2) if risk_per_share else None,
            "3R": round(entry - 3 * risk_per_share, 2) if risk_per_share else None,
        },
        "note": ("Never short day 1 of a rally, rarely day 2 -- book waits for day "
                 "3, 4, or sometimes 5. Market direction doesn't matter for this "
                 "setup.") + (
            "" if used_intraday else
            " No intraday data available -- entry/stop use today's daily low/high "
            "as a rough stand-in; confirm the real opening-range low and a 5-minute "
            "candle break before shorting."
        ),
    }
