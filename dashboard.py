"""
==========================================================================
 CRYPTO SIGNAL DASHBOARD (v2 - full SPOT/FUTURES + reasoning + journal)
==========================================================================
Run with:
    streamlit run dashboard.py

Still 100% read-only public market data. No exchange account, no API
key, no real money. The Paper Trading section below simulates trades
with FAKE money only, saved locally in paper_trades.json.
==========================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from step1_btc_regime import determine_btc_regime, fetch_candles
from step2_market_scanner import APPROVED_COINS
from signals import generate_market_signal
from paper_trading import run_paper_trading_cycle, calculate_performance


st.set_page_config(page_title="Crypto Signal Dashboard", page_icon="📊", layout="wide")

st.title("📊 Crypto Signal Dashboard")
st.caption(
    "Read-only market analysis — no exchange account or API key connected. "
    "This does NOT place real trades."
)
st.warning(
    "⚠️ **Decision-support tool, not financial advice, and not a prediction system.** "
    "The Paper Trading section below uses simulated FAKE money only."
)

col_refresh, col_time = st.columns([1, 4])
with col_refresh:
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()
with col_time:
    st.caption(f"Last checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")


# --------------------------------------------------------------------
# CACHED DATA
# --------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_btc_regime():
    return determine_btc_regime()

@st.cache_data(ttl=300)
def load_market_signals(btc_regime, market_type):
    results = []
    for symbol in APPROVED_COINS:
        try:
            results.append(generate_market_signal(symbol, btc_regime, market_type))
        except Exception as e:
            results.append({"symbol": symbol, "market_type": market_type, "direction": "ERROR", "reasoning": str(e)})
    return results

@st.cache_data(ttl=300)
def load_price_history(symbol):
    df = fetch_candles(symbol, "4h", limit=100)
    return df


# --------------------------------------------------------------------
# SECTION: BTC MARKET REGIME
# --------------------------------------------------------------------

st.subheader("🟠 BTC Market Regime")
btc_report = load_btc_regime()
regime = btc_report["final_btc_regime"]
regime_colors = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡", "MIXED": "🟠"}

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Final Regime", f"{regime_colors.get(regime, '⚪')} {regime}")
c2.metric("1D", btc_report["timeframe_breakdown"].get("1D", "N/A"))
c3.metric("4H", btc_report["timeframe_breakdown"].get("4H", "N/A"))
c4.metric("1H", btc_report["timeframe_breakdown"].get("1H", "N/A"))
c5.metric("15M", btc_report["timeframe_breakdown"].get("15M", "N/A"))

st.markdown("---")


# --------------------------------------------------------------------
# SHARED: render one signal card (reused for both SPOT and FUTURES)
# --------------------------------------------------------------------

direction_colors = {"LONG": "🟢", "SHORT": "🔴", "WAIT": "🟡", "NO_TRADE": "⚪", "ERROR": "❌"}

def render_signal_card(signal: dict):
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

            if signal["market_type"] == "FUTURES":
                f1, f2, f3 = st.columns(3)
                f1.caption(f"Leverage: {signal.get('leverage', 'N/A')}")
                f2.caption(f"Funding: {signal.get('funding_status', 'N/A')}")
                f3.caption(f"Open Interest: {signal.get('open_interest_status', 'N/A')}")

        # ---- Reasoning / Confirmations / Not Fulfilled (the "why") ----
        st.markdown(f"**Reasoning:** {signal.get('reasoning', 'N/A')}")

        conf_col, missing_col = st.columns(2)
        with conf_col:
            st.markdown("**✅ Confirmations**")
            for c in signal.get("confirmations", []):
                st.caption(f"• {c}")
        with missing_col:
            st.markdown("**❌ Not Fulfilled**")
            for n in signal.get("not_fulfilled", []):
                st.caption(f"• {n}")

        # ---- Price chart ----
        with st.expander("📈 Price chart (4H, last ~16 days)"):
            try:
                df = load_price_history(signal["symbol"])
                st.line_chart(df["close"])
            except Exception as e:
                st.caption(f"Chart unavailable: {e}")


# --------------------------------------------------------------------
# SECTION A: SPOT SIGNALS
# --------------------------------------------------------------------

st.subheader("💰 Spot Signals")
st.caption("Buy-only market (no shorting, no leverage, no liquidation risk)")

spot_signals = load_market_signals(regime, "SPOT")
for s in spot_signals:
    render_signal_card(s)

st.markdown("---")


# --------------------------------------------------------------------
# SECTION B: FUTURES SIGNALS
# --------------------------------------------------------------------

st.subheader("🚨 Futures Signals")
st.caption("Perpetual futures — LONG or SHORT, with leverage/funding context")

futures_signals = load_market_signals(regime, "FUTURES")
for s in futures_signals:
    render_signal_card(s)

st.markdown("---")


# --------------------------------------------------------------------
# SECTION C: PAPER TRADING PERFORMANCE (fake money simulation)
# --------------------------------------------------------------------

st.subheader("📒 Paper Trading Journal (Simulated — Fake Money Only)")
st.caption(
    "This automatically tracks hypothetical trades based on the Futures signals above, "
    "using fake starting money, so you can see over time whether this strategy would "
    "have been profitable — with zero real risk."
)

journal = run_paper_trading_cycle(futures_signals)
stats = calculate_performance(journal)

p1, p2, p3, p4, p5 = st.columns(5)
p1.metric("Fake Balance", f"${stats['current_balance']:,.2f}", delta=f"${stats['total_pnl']:,.2f}")
p2.metric("Total Trades", stats["total_trades"])
p3.metric("Win Rate", f"{stats['win_rate']}%")
p4.metric("Wins / Losses", f"{stats['wins']}W / {stats['losses']}L")
p5.metric("Open Positions", stats["open_positions_count"])

if journal["closed_trades"]:
    with st.expander("📄 View closed trade history"):
        df_trades = pd.DataFrame(journal["closed_trades"])
        st.dataframe(df_trades, use_container_width=True)

if journal["open_positions"]:
    with st.expander("⏳ View currently open paper positions"):
        df_open = pd.DataFrame(journal["open_positions"])
        st.dataframe(df_open, use_container_width=True)

st.markdown("---")
st.caption(
    "Data source: Binance public market data (via ccxt). Signals are rule-based, "
    "not predictions. Funding rate / Open Interest are marked UNAVAILABLE because "
    "they are not yet connected — never invented per the spec's data-honesty rule."
)
