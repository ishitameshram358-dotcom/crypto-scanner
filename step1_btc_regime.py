"""
==========================================================================
 PART 1: BTC MARKET REGIME DETECTOR
==========================================================================
Plain-English explanation:

Before analyzing ANY other coin, this system needs to answer one question:
"Is Bitcoin currently trending up, down, sideways, or unclear?"

Why does this matter? Because most altcoins (ETH, SOL, BNB, XRP, etc.)
tend to move in the SAME direction as Bitcoin most of the time. So if
Bitcoin is falling hard, buying an altcoin "LONG" (betting it goes up)
is generally riskier — even if that altcoin looks good on its own chart.

This script looks at Bitcoin's price on 4 different time windows:
  - 1D  (daily candles)   = the big-picture trend
  - 4H  (4-hour candles)  = the medium-term trend
  - 1H  (1-hour candles)  = the short-term trend
  - 15M (15-min candles)  = the very short-term trend

It then combines all 4 into ONE final answer:
  BULLISH  = market is trending up
  BEARISH  = market is trending down
  NEUTRAL  = market is flat / sideways
  MIXED    = timeframes disagree with each other (be extra careful here)

HOW "trend" is measured here (plain English):
We use something called an EMA (Exponential Moving Average) — think of
it as a smoothed-out average price line that reacts a bit faster to
recent price changes than a simple average would.

If the CURRENT price is above its own 50-period and 200-period EMA,
and the 50 EMA is above the 200 EMA, that's a classic "uptrend" signal
that traders have used for decades. The reverse (price below both EMAs,
50 below 200) is a classic "downtrend" signal.
==========================================================================
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime


# --------------------------------------------------------------------
# CONFIGURATION - these are the "knobs" you can adjust later.
# Nothing magic here, just settings the rest of the code reads.
# --------------------------------------------------------------------

EXCHANGE_NAME = "kucoin"         # where we pull public price data from
SYMBOL = "BTC/USDT"                # the asset we're checking the "regime" of

TIMEFRAMES = {
    "1D": "1d",
    "4H": "4h",
    "1H": "1h",
    "15M": "15m",
}

EMA_FAST = 50     # "medium-term" moving average
EMA_SLOW = 200     # "long-term" moving average, classic trend-defining line

CANDLES_TO_FETCH = 300   # how much history to pull (needs to be > EMA_SLOW)


# --------------------------------------------------------------------
# STEP 1: Connect to the exchange and fetch price history
# --------------------------------------------------------------------

def fetch_candles(symbol: str, timeframe: str, limit: int = CANDLES_TO_FETCH) -> pd.DataFrame:
    """
    Downloads historical price candles (OHLCV = Open, High, Low, Close, Volume)
    for a given symbol and timeframe. This uses PUBLIC data only —
    no account, no API key, no money involved at all.
    """
    exchange = getattr(ccxt, EXCHANGE_NAME)()
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


# --------------------------------------------------------------------
# STEP 2: Calculate the trend on ONE timeframe
# --------------------------------------------------------------------

def calculate_trend(df: pd.DataFrame) -> str:
    """
    Given price history for ONE timeframe, decide: BULLISH, BEARISH,
    or NEUTRAL for that timeframe alone.

    Plain-English logic:
      - Calculate the 50-period and 200-period EMA (trend-following lines)
      - If current price > both EMAs AND 50 EMA > 200 EMA  -> BULLISH
      - If current price < both EMAs AND 50 EMA < 200 EMA  -> BEARISH
      - Anything else (mixed signals)                       -> NEUTRAL
    """
    if len(df) < EMA_SLOW:
        # Not enough historical data to calculate a reliable 200 EMA
        return "UNAVAILABLE"

    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    last_close = df["close"].iloc[-1]
    last_ema_fast = df["ema_fast"].iloc[-1]
    last_ema_slow = df["ema_slow"].iloc[-1]

    if last_close > last_ema_fast and last_close > last_ema_slow and last_ema_fast > last_ema_slow:
        return "BULLISH"
    elif last_close < last_ema_fast and last_close < last_ema_slow and last_ema_fast < last_ema_slow:
        return "BEARISH"
    else:
        return "NEUTRAL"


# --------------------------------------------------------------------
# STEP 3: Combine all 4 timeframes into ONE final regime
# --------------------------------------------------------------------

def determine_btc_regime() -> dict:
    """
    Pulls all 4 timeframes for BTC/USDT, calculates the trend on each,
    then combines them into a single final regime.

    Combination logic (plain English):
      - If 1D and 4H (the two most important, slower timeframes) AGREE
        with each other (both bullish or both bearish) -> that's the regime
      - If 1D and 4H DISAGREE with each other -> MIXED
        (this means the big picture is genuinely unclear right now,
        and per your spec, that should make the system MORE cautious,
        not less)
      - If either timeframe has insufficient data -> UNAVAILABLE
    """
    results = {}

    for label, tf_code in TIMEFRAMES.items():
        try:
            df = fetch_candles(SYMBOL, tf_code)
            trend = calculate_trend(df)
            results[label] = trend
        except Exception as e:
            results[label] = f"ERROR: {e}"

    # The two most important timeframes for the OVERALL regime
    daily_trend = results.get("1D")
    h4_trend = results.get("4H")

    if daily_trend == "UNAVAILABLE" or h4_trend == "UNAVAILABLE":
        final_regime = "UNAVAILABLE"
    elif daily_trend == h4_trend:
        final_regime = daily_trend   # they agree -> use that as final answer
    elif "BULLISH" in (daily_trend, h4_trend) and "BEARISH" in (daily_trend, h4_trend):
        final_regime = "MIXED"        # direct disagreement -> be cautious
    else:
        final_regime = "NEUTRAL"      # one is neutral, other has a lean -> call it neutral for safety

    return {
        "asset": SYMBOL,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "timeframe_breakdown": results,
        "final_btc_regime": final_regime,
    }


# --------------------------------------------------------------------
# RUN IT
# --------------------------------------------------------------------

if __name__ == "__main__":
    print("Checking BTC market regime across 1D / 4H / 1H / 15M...\n")

    regime = determine_btc_regime()

    print("=" * 50)
    print("BTC MARKET REGIME REPORT")
    print("=" * 50)
    print(f"Asset:      {regime['asset']}")
    print(f"Checked at: {regime['timestamp']}")
    print("-" * 50)
    print("Breakdown by timeframe:")
    for tf, trend in regime["timeframe_breakdown"].items():
        print(f"  {tf:>4}: {trend}")
    print("-" * 50)
    print(f"FINAL BTC REGIME: {regime['final_btc_regime']}")
    print("=" * 50)
