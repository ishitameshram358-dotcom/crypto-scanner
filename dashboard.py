"""
==========================================================================
 CRYPTO SIGNAL DASHBOARD
==========================================================================
Plain-English explanation:

This turns Steps 1, 2, and 3 (which you've already tested in the
terminal) into a clean webpage. It uses ONLY public, read-only market
data — no exchange account, no API key, no real money involved.

Run with:
    streamlit run dashboard.py

It will open in your browser automatically. To get a real shareable
link (not just on your own computer), this can be deployed for free on
Streamlit Community Cloud — same process as the stock dashboard we
built earlier.
==========================================================================
"""

import streamlit as st
from datetime import datetime

from step1_btc_regime import determine_btc_regime
from step2_market_scanner import APPROVED_COINS
from step3_entry_signals import generate_entry_signal


# --------------------------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------------------------

st.set_page_config(
    page_title="Crypto Signal Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Crypto Signal Dashboard")
st.caption(
    "Read-only market analysis — no exchange account or API key connected. "
    "This does NOT place trades. It only displays information for a human to review."
)

# Big, impossible-to-miss reminder banner
st.warning(
    "⚠️ **This is a decision-support tool, not financial advice, and not a "
    "prediction system.** Always verify signals yourself before acting on them. "
    "Nothing here executes real trades."
)


# --------------------------------------------------------------------
# REFRESH CONTROL
# --------------------------------------------------------------------

col_refresh, col_time = st.columns([1, 4])
with col_refresh:
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

with col_time:
    st.caption(f"Last checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")


# --------------------------------------------------------------------
# CACHED DATA FETCHING (keeps the dashboard fast, avoids hammering
# the exchange with requests every time the page redraws)
# --------------------------------------------------------------------

@st.cache_data(ttl=300)  # refresh at most every 5 minutes automatically
def load_btc_regime():
    return determine_btc_regime()


@st.cache_data(ttl=300)
def load_all_signals(btc_regime):
    results = []
    for symbol in APPROVED_COINS:
        try:
            signal = generate_entry_signal(symbol, btc_regime)
            results.append(signal)
        except Exception as e:
            results.append({"symbol": symbol, "direction": "ERROR", "reason": str(e)})
    return results


# --------------------------------------------------------------------
# SECTION 1: BTC MARKET REGIME
# --------------------------------------------------------------------

st.subheader("🟠 BTC Market Regime")

with st.spinner("Checking Bitcoin's trend across timeframes..."):
    btc_report = load_btc_regime()

regime = btc_report["final_btc_regime"]
regime_colors = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡", "MIXED": "🟠"}

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Final Regime", f"{regime_colors.get(regime, '⚪')} {regime}")
col2.metric("1D", btc_report["timeframe_breakdown"].get("1D", "N/A"))
col3.metric("4H", btc_report["timeframe_breakdown"].get("4H", "N/A"))
col4.metric("1H", btc_report["timeframe_breakdown"].get("1H", "N/A"))
col5.metric("15M", btc_report["timeframe_breakdown"].get("15M", "N/A"))

st.markdown("---")


# --------------------------------------------------------------------
# SECTION 2: SIGNAL CARDS FOR EACH COIN
# --------------------------------------------------------------------

st.subheader("📈 Coin Signals")
st.caption("Grade, direction, and trade levels for each approved coin (meme coins excluded by default)")

with st.spinner("Analyzing all approved coins..."):
    signals = load_all_signals(regime)

direction_colors = {
    "LONG": "🟢",
    "SHORT": "🔴",
    "WAIT": "🟡",
    "NO_TRADE": "⚪",
    "ERROR": "❌",
}

for signal in signals:
    direction = signal.get("direction", "ERROR")
    icon = direction_colors.get(direction, "⚪")

    with st.container(border=True):
        header_col, grade_col = st.columns([3, 1])
        header_col.markdown(f"### {icon} {signal['symbol']} — {direction}")
        if "grade" in signal:
            grade_col.markdown(f"**Grade: {signal['grade']}**")

        if direction in ("LONG", "SHORT"):
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Entry", signal["entry"])
            m2.metric("Stop Loss", signal["stop_loss"])
            m3.metric("TP1", signal["tp1"])
            m4.metric("TP2", signal["tp2"])
            m5.metric("TP3", signal["tp3"])
            m6.metric("R:R", f"1:{signal['rr_ratio']}")

        st.caption(f"**Reasoning:** {signal.get('reason', 'N/A')}")

        with st.expander("More details"):
            st.write(f"- 4H Trend: {signal.get('coin_trend_4h', 'N/A')}")
            st.write(f"- BTC Alignment: {signal.get('btc_alignment', 'N/A')}")

st.markdown("---")
st.caption(
    "Data source: Binance public market data (via ccxt). "
    "Signals are rule-based on the logic in step1/2/3 — not predictions, "
    "not financial advice. Past patterns do not guarantee future results."
)
