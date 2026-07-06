"""
Kullamagi Breakout Fit Score - Streamlit web app

Public-facing web UI around the scoring logic in kullamagi_score.py, plus
a screener (screener.py) that scans a universe of tickers and surfaces only
the ones clearing a score threshold. Deploy on Streamlit Community Cloud
(see README.md in this folder).
"""

import re

import streamlit as st
import pandas as pd

from kullamagi_score import score_breakout_fit, fetch_data
from screener import get_sp500_tickers, get_nasdaq100_tickers, run_screener

st.set_page_config(
    page_title="Kullamagi Breakout Score",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Kullamagi Breakout Fit Score")
st.caption(
    "An unofficial scoring tool modeled on Kristjan Kullamagi's (Qullamaggie) "
    "publicly documented Breakout / Episodic Pivot / Parabolic Short setups."
)

with st.expander("How this works", expanded=False):
    st.markdown(
        """
This tool pulls daily price/volume history for a ticker and scores it 0-100
against Kullamagi's **Breakout** setup criteria:

| Category | Points | Checks |
|---|---|---|
| Trend template | 25 | Price vs 10/20/50-day MAs, MA stacking, proximity to 52-week high |
| Prior momentum / RS | 20 | 1/3/6-month returns, 3-month return vs. SPY |
| ADR% / volatility | 15 | Whether ADR% falls in the ~4-12% sweet spot |
| Base / consolidation quality | 20 | Range contraction, higher lows, distance to base high |
| Volume / liquidity | 10 | Dollar volume, recent volume vs 50-day average, dry-up into the base |
| Price floor | 10 | Price at or above $5 |

**Rating scale:** 85-100 A+ (prime candidate) &nbsp;|&nbsp; 70-84 B (watchlist)
&nbsp;|&nbsp; 50-69 C (developing) &nbsp;|&nbsp; below 50 D (not a fit)

It also flags possible **Episodic Pivot** (large gap-up), **Parabolic Short**
(overextended, multi-day vertical move) conditions, and a **market
environment** check (SPY's 10-day MA vs. 20-day MA) — Kullamagi's own rule
for whether the current market favors Breakout/EP setups at all.

This is an independent, educational tool — not affiliated with or endorsed by
Kristjan Kullamagi, and not financial advice.
        """
    )

tab_single, tab_screener = st.tabs(["🔍 Single Ticker", "📋 Screener"])


def render_market_environment(me):
    if not me or me.get("trend") == "unknown":
        return
    if me["trend"] == "uptrend":
        st.success(
            f"Market environment: **favorable** (SPY 10-day MA {me['sma10']} "
            f"is above its 20-day MA {me['sma20']}) — Kullamagi's own filter "
            "for taking Breakout/EP setups."
        )
    else:
        st.error(
            f"Market environment: **unfavorable** (SPY 10-day MA {me['sma10']} "
            f"is below its 20-day MA {me['sma20']}) — Kullamagi's rule says "
            "stand aside on Breakout/EP setups here. His largest-ever drawdown "
            "came from ignoring this exact filter. Parabolic Short setups "
            "aren't affected by it."
        )


# ---------------------------------------------------------------------------
# Tab 1: Single ticker
# ---------------------------------------------------------------------------
with tab_single:
    ticker = st.text_input("Enter a stock ticker", placeholder="e.g. NVDA").strip().upper()
    go = st.button("Score it", type="primary", use_container_width=True)

    if go and not ticker:
        st.warning("Enter a ticker symbol first.")

    if go and ticker:
        with st.spinner(f"Fetching data for {ticker}..."):
            try:
                df = fetch_data(ticker)
            except Exception as e:
                st.error(f"Error fetching data for {ticker}: {e}")
                df = None

            spy_df = None
            if df is not None:
                try:
                    spy_df = fetch_data("SPY")
                except Exception:
                    spy_df = None

        if df is None:
            st.error(f"No data found for '{ticker}'. Check the symbol and try again.")
        else:
            result = score_breakout_fit(df, spy_df)

            if result["rating"] == "INSUFFICIENT DATA":
                st.error("Not enough trading history for this ticker (need ~60+ days).")
            else:
                score = result["score"]
                rating = result["rating"]

                color = "#1a9850" if score >= 85 else "#66bd63" if score >= 70 else "#fdae61" if score >= 50 else "#d73027"

                st.markdown(
                    f"""
                    <div style="text-align:center; padding: 1.2rem; border-radius: 12px;
                                background-color:{color}22; border: 2px solid {color};">
                        <div style="font-size:0.9rem; color:#666;">{ticker}</div>
                        <div style="font-size:3rem; font-weight:800; color:{color};">{score}/100</div>
                        <div style="font-size:1.1rem; font-weight:600;">{rating}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                render_market_environment(result.get("market_environment"))

                st.subheader("Score breakdown")
                rows = []
                for name, d in result["breakdown"].items():
                    rows.append({"Category": name.replace("_", " ").title(),
                                 "Points": d["points"], "Out of": d["out_of"]})
                bdf = pd.DataFrame(rows)
                st.dataframe(bdf, hide_index=True, use_container_width=True)
                for _, r in bdf.iterrows():
                    st.progress(r["Points"] / r["Out of"], text=f"{r['Category']}: {r['Points']}/{r['Out of']}")

                st.subheader("Key metrics")
                det = result["details"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Last close", f"${det.get('last_close', '—')}")
                c2.metric("ADR% (20d)", f"{det.get('adr_pct', '—')}%")
                m = det.get("momentum", {})
                c3.metric("6-month return", f"{m.get('return_6m_pct', '—')}%")

                c4, c5 = st.columns(2)
                c4.metric("1-month return", f"{m.get('return_1m_pct', '—')}%")
                c5.metric("3-month return", f"{m.get('return_3m_pct', '—')}%")
                if m.get("relative_strength_vs_spy"):
                    st.caption(m["relative_strength_vs_spy"])

                cq = det.get("consolidation")
                if cq:
                    st.markdown(
                        f"**Base contraction ratio:** {cq['contraction_ratio']:.2f} (lower = tighter)  \n"
                        f"**Higher-low frequency (last 10d):** {cq['higher_low_frac']*100:.0f}%  \n"
                        f"**Distance to base high:** {cq['dist_to_base_high_pct']:.1f}%"
                    )

                if result["flags"]:
                    st.subheader("Flags")
                    for f in result["flags"]:
                        st.warning(f)

                st.caption(
                    "Educational tool only. Not financial advice. Not affiliated with "
                    "Kristjan Kullamagi / Qullamaggie."
                )

# ---------------------------------------------------------------------------
# Tab 2: Screener
# ---------------------------------------------------------------------------
with tab_screener:
    st.subheader("Scan a universe of tickers for A+ setups")
    st.caption(
        "Scores every ticker in the chosen universe and shows only the ones "
        "clearing your score threshold (default 90+)."
    )

    universe_choice = st.radio(
        "Universe", ["S&P 500", "Nasdaq-100", "Custom list"], horizontal=True
    )

    custom_tickers = None
    if universe_choice == "Custom list":
        custom_input = st.text_area(
            "Paste tickers (comma, space, or newline separated)",
            height=100,
            placeholder="AAPL, MSFT, NVDA ...",
        )
        uploaded = st.file_uploader("...or upload a CSV with a Ticker/Symbol column", type=["csv"])
        if uploaded is not None:
            try:
                cdf = pd.read_csv(uploaded)
                col = next(
                    (c for c in cdf.columns if str(c).strip().lower() in ("ticker", "tickers", "symbol", "symbols")),
                    cdf.columns[0],
                )
                custom_tickers = cdf[col].astype(str).tolist()
            except Exception as e:
                st.error(f"Couldn't read that CSV: {e}")
        elif custom_input.strip():
            custom_tickers = [t for t in re.split(r"[,\s]+", custom_input.strip()) if t]

    col1, col2 = st.columns(2)
    threshold = col1.slider("Minimum score to show", 0, 100, 90, 1)
    max_tickers = col2.number_input(
        "Max tickers to scan (safety cap)",
        min_value=10, max_value=500, value=150, step=10,
        help="Larger scans take longer and use more data-provider calls; "
             "free hosting (e.g. Streamlit Community Cloud) can time out on "
             "very long runs. Increase gradually.",
    )

    run = st.button("Run screener", type="primary", use_container_width=True)

    if run:
        if universe_choice == "S&P 500":
            with st.spinner("Fetching S&P 500 constituent list..."):
                tickers = get_sp500_tickers()
        elif universe_choice == "Nasdaq-100":
            with st.spinner("Fetching Nasdaq-100 constituent list..."):
                tickers = get_nasdaq100_tickers()
        else:
            tickers = custom_tickers or []

        if not tickers:
            st.warning("No tickers to scan. Paste a list or upload a CSV in the Custom list option.")
        else:
            tickers = tickers[: int(max_tickers)]
            st.info(f"Scanning {len(tickers)} tickers — this can take a couple of minutes.")

            progress_bar = st.progress(0.0)
            status = st.empty()

            def _cb(done, total):
                progress_bar.progress(done / total)
                status.text(f"{done}/{total} tickers fetched...")

            with st.spinner("Scoring..."):
                hits, errors, market_env = run_screener(
                    tickers, threshold=threshold, progress_cb=_cb
                )

            progress_bar.empty()
            status.empty()

            render_market_environment(market_env)

            if not hits:
                st.warning(f"No tickers scored {threshold}+ out of {len(tickers)} scanned.")
            else:
                st.success(f"{len(hits)} of {len(tickers)} tickers scored {threshold}+.")
                res_df = pd.DataFrame(hits)
                st.dataframe(res_df, hide_index=True, use_container_width=True)
                csv = res_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download results as CSV", csv,
                    "kullamagi_screener_results.csv", "text/csv",
                )

            if errors:
                with st.expander(f"{len(errors)} tickers skipped (no data / insufficient history)"):
                    st.write(", ".join(errors))

            st.caption(
                "Educational tool only. Not financial advice. Not affiliated with "
                "Kristjan Kullamagi / Qullamaggie."
            )

st.divider()
st.caption(
    "Built from publicly documented Qullamaggie criteria (qullamaggie.com FAQ, "
    "\"3 timeless setups\", and his interview in Schwager & Coyle's Market "
    "Wizards: The Next Generation). Data via Yahoo Finance (yfinance)."
)
