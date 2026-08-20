"""
==========================================================================
 PART 3: ENTRY SIGNAL LOGIC
==========================================================================
Plain-English explanation:

Steps 1 and 2 answered "is this coin healthy and well-graded?" This step
answers the actual trading question: "Should we go LONG (bet price goes
up), SHORT (bet price goes down), or WAIT (do nothing)? And if we trade,
at what price, with what safety net, and what target?"

Key terms used below:
  ENTRY       = the price where you'd open the trade
  STOP LOSS   = a safety price. If hit, you exit to limit your loss.
  TAKE PROFIT = your target price(s) to lock in gains (we calculate 3:
                TP1, TP2, TP3 — closer, medium, and further targets)
  R:R         = Risk:Reward ratio. If you're risking $10 (distance to
                stop loss) to potentially make $20 (distance to TP2),
                that's an R:R of 1:2. The spec requires AT LEAST 1:2
                before a signal counts as valid — otherwise the
                potential reward doesn't justify the risk.
  ATR         = Average True Range. A standard way to measure "how much
                does this coin typically move in a given period?" We
                use this to set a SENSIBLE stop-loss distance — not
                too tight (gets stopped out by normal wiggle) and not
                too wide (risks too much).

HOW DIRECTION IS DECIDED (plain English):
  - LONG only if: this coin's own trend is BULLISH, AND it's not
    fighting against BTC's overall regime (per spec Parts 11-13)
  - SHORT only if: this coin's own trend is BEARISH, AND it's not
    fighting against BTC's overall regime
  - Otherwise: WAIT (no clear, low-conflict direction right now)

This mirrors your friend's core philosophy (Part 30 / 39 of the spec):
the system should be willing to say "NO TRADE" rather than force one.
==========================================================================
"""

import pandas as pd
from datetime import datetime

from step1_btc_regime import fetch_candles, determine_btc_regime
from step2_market_scanner import grade_coin, APPROVED_COINS


# --------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------

ATR_PERIOD = 14           # standard ATR calculation window
STOP_LOSS_ATR_MULTIPLE = 1.5   # stop loss = 1.5x the ATR away from entry

# Take-profit targets, expressed as multiples of the risk distance
# (the distance between entry and stop loss). This is what creates
# the R:R ratios.
TP1_R_MULTIPLE = 1.5   # TP1 = 1.5x the risk distance (R:R of 1:1.5)
TP2_R_MULTIPLE = 2.0   # TP2 = 2x the risk distance   (R:R of 1:2)
TP3_R_MULTIPLE = 3.0   # TP3 = 3x the risk distance   (R:R of 1:3)

MINIMUM_RR = 2.0   # per the spec: R:R must be >= 1:2 to be a valid signal


# --------------------------------------------------------------------
# STEP A: Calculate ATR (a standard volatility measure)
# --------------------------------------------------------------------

def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    """
    ATR = Average True Range.
    Plain English: on average, how much does the price move (high to low,
    accounting for gaps) over each recent candle? This gives us a
    sensible, data-driven distance for placing a stop loss — based on
    this coin's ACTUAL recent behavior, not a random guess.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()

    return atr.iloc[-1]


# --------------------------------------------------------------------
# STEP B: Build the actual trade signal for one coin
# --------------------------------------------------------------------

def generate_entry_signal(symbol: str, btc_regime: str) -> dict:
    """
    Combines everything: grades the coin (Step 2 logic), decides a
    direction, and if a direction makes sense, calculates entry,
    stop loss, take profits, and R:R.
    """
    # Reuse Step 2's grading (gives us trend + BTC alignment + grade)
    grade_info = grade_coin(symbol, btc_regime)

    coin_trend = grade_info.get("coin_trend_4h", "UNAVAILABLE")
    alignment = grade_info.get("btc_alignment", "UNCLEAR")
    grade = grade_info.get("grade", "AVOID")

    # ---- Decide direction (plain English rules from spec Parts 11-13) ----
    direction = "WAIT"
    if grade in ("AVOID",):
        direction = "NO_TRADE"
    elif coin_trend == "BULLISH" and alignment != "CONFLICTING":
        direction = "LONG"
    elif coin_trend == "BEARISH" and alignment != "CONFLICTING":
        direction = "SHORT"
    else:
        direction = "WAIT"

    signal = {
        "symbol": symbol,
        "grade": grade,
        "coin_trend_4h": coin_trend,
        "btc_alignment": alignment,
        "direction": direction,
    }

    if direction not in ("LONG", "SHORT"):
        # Nothing more to calculate - there's no trade to size up
        signal["reason"] = f"No valid direction (trend={coin_trend}, alignment={alignment}, grade={grade})"
        return signal

    # ---- Fetch fresh price data + calculate ATR for stop-loss sizing ----
    df = fetch_candles(symbol, "4h")
    atr = calculate_atr(df)
    current_price = df["close"].iloc[-1]

    stop_distance = atr * STOP_LOSS_ATR_MULTIPLE

    if direction == "LONG":
        entry = current_price
        stop_loss = entry - stop_distance
        tp1 = entry + (stop_distance * TP1_R_MULTIPLE)
        tp2 = entry + (stop_distance * TP2_R_MULTIPLE)
        tp3 = entry + (stop_distance * TP3_R_MULTIPLE)
    else:  # SHORT
        entry = current_price
        stop_loss = entry + stop_distance
        tp1 = entry - (stop_distance * TP1_R_MULTIPLE)
        tp2 = entry - (stop_distance * TP2_R_MULTIPLE)
        tp3 = entry - (stop_distance * TP3_R_MULTIPLE)

    # R:R is calculated using TP2 as the "standard" target
    risk = abs(entry - stop_loss)
    reward = abs(tp2 - entry)
    rr_ratio = reward / risk if risk > 0 else 0

    signal.update({
        "entry": round(entry, 4),
        "stop_loss": round(stop_loss, 4),
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "tp3": round(tp3, 4),
        "risk_distance": round(risk, 4),
        "rr_ratio": round(rr_ratio, 2),
    })

    # ---- Final validity check: does this meet the minimum R:R? ----
    if rr_ratio < MINIMUM_RR:
        signal["direction"] = "NO_TRADE"
        signal["reason"] = f"R:R of 1:{rr_ratio} is below the required minimum of 1:{MINIMUM_RR}"
    else:
        signal["reason"] = f"Valid {direction} setup: R:R of 1:{rr_ratio} meets the 1:{MINIMUM_RR} minimum"

    return signal


# --------------------------------------------------------------------
# RUN IT
# --------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating entry signals for all approved coins...\n")

    btc_report = determine_btc_regime()
    btc_regime = btc_report["final_btc_regime"]

    print("=" * 60)
    print("ENTRY SIGNAL REPORT")
    print("=" * 60)
    print(f"Checked at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"BTC Regime: {btc_regime}")
    print("=" * 60)

    for symbol in APPROVED_COINS:
        try:
            signal = generate_entry_signal(symbol, btc_regime)
        except Exception as e:
            print(f"\n{symbol}: ERROR - {e}")
            continue

        print(f"\n{symbol}")
        print("-" * 40)
        print(f"  Grade:        {signal['grade']}")
        print(f"  4H Trend:     {signal['coin_trend_4h']}")
        print(f"  BTC Aligned:  {signal['btc_alignment']}")
        print(f"  DIRECTION:    {signal['direction']}")

        if "entry" in signal:
            print(f"  Entry:        {signal['entry']}")
            print(f"  Stop Loss:    {signal['stop_loss']}")
            print(f"  TP1:          {signal['tp1']}")
            print(f"  TP2:          {signal['tp2']}")
            print(f"  TP3:          {signal['tp3']}")
            print(f"  R:R (to TP2): 1:{signal['rr_ratio']}")

        print(f"  Reason:       {signal['reason']}")

    print("\n" + "=" * 60)
