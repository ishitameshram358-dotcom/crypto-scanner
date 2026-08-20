"""
==========================================================================
 PART 4: SIGNAL REASONING + SPOT/FUTURES SEPARATION
==========================================================================
Plain-English explanation:

Your friend's spec (Parts covering Spot vs Futures) says SPOT and FUTURES
must NEVER be mixed together in the output - they need their own
sections, because they behave differently:

  SPOT:    You're buying the actual coin. You can only go LONG (bet the
           price goes up) - there's no "shorting" in basic spot trading.
           No leverage, no liquidation risk, simpler.

  FUTURES: You're trading a contract that TRACKS the price, without
           owning the coin. You CAN go LONG or SHORT (bet up OR down).
           Can use leverage (multiplies gains AND losses), carries
           liquidation risk (can lose the whole position if price moves
           too far against you), and has extra costs like "funding
           rate."

This file also builds a plain-English explanation for every signal -
a list of CONFIRMATIONS (what supports this decision), a list of
NOT_FULFILLED (what's missing or working against it), and a REASONING
sentence that ties it together - matching what the spec's trade card
format asks for.
==========================================================================
"""

from step1_btc_regime import fetch_candles, calculate_trend
from step2_market_scanner import grade_coin
from step3_entry_signals import calculate_atr, MINIMUM_RR, STOP_LOSS_ATR_MULTIPLE, TP1_R_MULTIPLE, TP2_R_MULTIPLE, TP3_R_MULTIPLE


def build_confirmations(grade_info: dict, coin_trend: str, alignment: str, rr_ratio: float = None) -> tuple:
    """
    Builds two plain-English lists:
      CONFIRMATIONS  = things supporting this trade idea
      NOT_FULFILLED  = things missing or working against it
    This is what lets a human quickly see WHY the system decided what
    it decided, instead of just trusting a black-box grade.
    """
    confirmations = []
    not_fulfilled = []

    # --- Volume/liquidity ---
    if "Volume: sufficient" in " ".join(grade_info.get("reasons", [])):
        confirmations.append("24h trading volume is healthy (easy to enter/exit without moving the price much)")
    else:
        not_fulfilled.append("24h trading volume is below the healthy threshold (could mean unreliable price moves)")

    # --- Spread ---
    if "Spread: tight" in " ".join(grade_info.get("reasons", [])):
        confirmations.append("Bid/ask spread is tight (cheap to trade right now)")
    else:
        not_fulfilled.append("Bid/ask spread is wider than ideal (trading right now costs more than usual)")

    # --- Trend ---
    if coin_trend in ("BULLISH", "BEARISH"):
        confirmations.append(f"This coin has a clear 4H trend ({coin_trend}), not just random noise")
    else:
        not_fulfilled.append("This coin's 4H trend is NEUTRAL - no clear direction to trade with confidence")

    # --- BTC alignment ---
    if alignment == "SUPPORTIVE":
        confirmations.append("BTC's overall market regime supports this direction (not fighting the broader market)")
    elif alignment == "CONFLICTING":
        not_fulfilled.append("BTC's overall market regime CONFLICTS with this direction - higher risk of reversal")
    else:
        not_fulfilled.append("BTC alignment is unclear - this trade doesn't have strong broader market support")

    # --- R:R ---
    if rr_ratio is not None:
        if rr_ratio >= MINIMUM_RR:
            confirmations.append(f"Risk:Reward of 1:{rr_ratio} meets the required minimum of 1:{MINIMUM_RR}")
        else:
            not_fulfilled.append(f"Risk:Reward of 1:{rr_ratio} is BELOW the required minimum of 1:{MINIMUM_RR}")

    return confirmations, not_fulfilled


def generate_market_signal(symbol: str, btc_regime: str, market_type: str) -> dict:
    """
    Generates a full signal for ONE market type: "SPOT" or "FUTURES".

    KEY DIFFERENCE:
      - SPOT can only ever say LONG or WAIT (never SHORT - see explanation
        at the top of this file)
      - FUTURES can say LONG, SHORT, or WAIT, and includes extra fields
        (leverage, position size, funding status) that only make sense
        for futures contracts
    """
    grade_info = grade_coin(symbol, btc_regime)
    coin_trend = grade_info.get("coin_trend_4h", "UNAVAILABLE")
    alignment = grade_info.get("btc_alignment", "UNCLEAR")
    grade = grade_info.get("grade", "AVOID")

    # ---- Decide raw direction (same logic as Step 3) ----
    raw_direction = "WAIT"
    if grade == "AVOID":
        raw_direction = "NO_TRADE"
    elif coin_trend == "BULLISH" and alignment != "CONFLICTING":
        raw_direction = "LONG"
    elif coin_trend == "BEARISH" and alignment != "CONFLICTING":
        raw_direction = "SHORT"

    # ---- SPOT RESTRICTION: no shorting allowed ----
    direction = raw_direction
    if market_type == "SPOT" and raw_direction == "SHORT":
        direction = "WAIT"  # Spot can't short - so a SHORT idea just becomes "no action"

    signal = {
        "symbol": symbol,
        "market_type": market_type,
        "grade": grade,
        "coin_trend_4h": coin_trend,
        "btc_alignment": alignment,
        "direction": direction,
    }

    if direction not in ("LONG", "SHORT"):
        confirmations, not_fulfilled = build_confirmations(grade_info, coin_trend, alignment)
        signal["confirmations"] = confirmations
        signal["not_fulfilled"] = not_fulfilled
        signal["reasoning"] = (
            f"{symbol} on {market_type}: no valid trade right now. "
            f"4H trend is {coin_trend}, BTC alignment is {alignment}, grade is {grade}."
        )
        return signal

    # ---- Calculate entry/SL/TP (same math as Step 3) ----
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
    else:
        entry = current_price
        stop_loss = entry + stop_distance
        tp1 = entry - (stop_distance * TP1_R_MULTIPLE)
        tp2 = entry - (stop_distance * TP2_R_MULTIPLE)
        tp3 = entry - (stop_distance * TP3_R_MULTIPLE)

    risk = abs(entry - stop_loss)
    reward = abs(tp2 - entry)
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0

    confirmations, not_fulfilled = build_confirmations(grade_info, coin_trend, alignment, rr_ratio)

    if rr_ratio < MINIMUM_RR:
        direction = "NO_TRADE"
        signal["direction"] = direction
        signal["confirmations"] = confirmations
        signal["not_fulfilled"] = not_fulfilled
        signal["reasoning"] = (
            f"{symbol} on {market_type}: setup looked directionally valid, but the "
            f"Risk:Reward (1:{rr_ratio}) didn't meet the 1:{MINIMUM_RR} minimum, so no trade is issued."
        )
        return signal

    signal.update({
        "entry": round(entry, 4),
        "stop_loss": round(stop_loss, 4),
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "tp3": round(tp3, 4),
        "rr_ratio": rr_ratio,
        "confirmations": confirmations,
        "not_fulfilled": not_fulfilled,
        "reasoning": (
            f"{symbol} shows a {coin_trend} 4H trend with {alignment.lower()} BTC alignment "
            f"and a grade of {grade}. Entering {direction} at {round(entry, 4)} risks "
            f"{round(risk, 4)} to a stop at {round(stop_loss, 4)}, targeting {round(tp2, 4)} "
            f"for a 1:{rr_ratio} reward - above the required minimum."
        ),
    })

    # ---- FUTURES-only extra fields (spec requires these to be separate from SPOT) ----
    if market_type == "FUTURES":
        signal.update({
            "leverage": "1x (not auto-increased - see spec Part 8)",
            "funding_status": "UNAVAILABLE (not yet connected - see note below)",
            "open_interest_status": "UNAVAILABLE (not yet connected - see note below)",
            "liquidation_price": "UNAVAILABLE (requires account-specific margin data)",
        })

    return signal
