"""
==========================================================================
 PART 2: MARKET SCANNER & COIN RANKING
==========================================================================
Plain-English explanation:

This script looks at a fixed list of "approved" coins (the ones your
friend's rules allow — meme coins are excluded by default, per Part 4 of
the spec) and grades each one from A+ (best) to AVOID (worst) based on:

  1. VOLUME    - how much real trading activity is happening right now.
                 Low volume = risky, prices can jump around unpredictably,
                 and it can be hard to buy/sell without a bad price.

  2. SPREAD    - the gap between the "buy price" and "sell price" at this
                 exact moment. A small gap = healthy market. A big gap =
                 expensive to trade, red flag.

  3. BTC ALIGNMENT - per the spec (Parts 11-13), Bitcoin's trend affects
                 how "safe" it is to bet on an altcoin. If BTC is falling
                 hard, betting on an altcoin going UP is riskier, even if
                 that altcoin's own chart looks fine.

This is a SIMPLIFIED first version. The full spec asks for many more
signals (order book depth, funding rate, open interest, news, etc.) —
those need either paid data sources or exchange API keys, and will be
added in later steps. For now, this covers the "is this coin healthy
enough to even consider trading" question.
==========================================================================
"""

import ccxt
import pandas as pd
from datetime import datetime

# Reuse the BTC regime logic we already built in Step 1
from step1_btc_regime import determine_btc_regime, fetch_candles, calculate_trend


# --------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------

EXCHANGE_NAME = "binance"

# The APPROVED coin list from the spec (Tier 1 + Tier 2).
# Meme coins are intentionally NOT in this list — per Part 4,
# ALLOW_MEME_COINS = FALSE by default, so we simply never scan them.
APPROVED_COINS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
]

# Minimum 24h trading volume (in USDT) for a coin to be considered
# "liquid enough." This is a simple, adjustable threshold — the spec
# calls for smarter relative-ranking eventually, but a fixed floor is
# a reasonable, honest starting point.
MIN_24H_VOLUME_USDT = 50_000_000   # 50 million USDT

# Maximum acceptable spread, as a percentage of price.
# Example: 0.05 means the buy/sell price gap shouldn't exceed 0.05%
MAX_SPREAD_PERCENT = 0.05


# --------------------------------------------------------------------
# STEP A: Get basic market health data for one coin
# --------------------------------------------------------------------

def get_market_health(symbol: str) -> dict:
    """
    Fetches current ticker data (price, volume, bid/ask) for one coin.
    This is all PUBLIC data - no account or API key needed.
    """
    exchange = getattr(ccxt, EXCHANGE_NAME)()
    ticker = exchange.fetch_ticker(symbol)

    bid = ticker.get("bid")
    ask = ticker.get("ask")
    last_price = ticker.get("last")
    volume_24h_base = ticker.get("baseVolume")   # volume in the coin itself (e.g. BTC)
    volume_24h_quote = ticker.get("quoteVolume")  # volume in USDT - easier to compare across coins

    spread_percent = None
    if bid and ask and bid > 0:
        spread_percent = ((ask - bid) / bid) * 100

    return {
        "symbol": symbol,
        "last_price": last_price,
        "volume_24h_usdt": volume_24h_quote,
        "spread_percent": spread_percent,
    }


# --------------------------------------------------------------------
# STEP B: Grade one coin based on its health + BTC alignment
# --------------------------------------------------------------------

def grade_coin(symbol: str, btc_regime: str) -> dict:
    """
    Combines market health + BTC alignment into a single letter grade.

    Plain-English grading logic:
      - Start every coin at grade "B" (neutral baseline)
      - PROMOTE toward A/A+ if: volume is strong, spread is tight,
        and this coin's own trend AGREES with the BTC regime
      - DEMOTE toward C/AVOID if: volume is weak, spread is wide,
        or this coin's trend FIGHTS the BTC regime
    """
    health = get_market_health(symbol)

    # ---- Liquidity/Volume checks ----
    volume_ok = (health["volume_24h_usdt"] or 0) >= MIN_24H_VOLUME_USDT
    spread_ok = (health["spread_percent"] is not None) and (health["spread_percent"] <= MAX_SPREAD_PERCENT)

    # ---- This coin's own trend (reusing Step 1's trend logic on the 4H timeframe) ----
    try:
        df_4h = fetch_candles(symbol, "4h")
        coin_trend = calculate_trend(df_4h)
    except Exception:
        coin_trend = "UNAVAILABLE"

    # ---- Alignment with BTC (spec Parts 11-13) ----
    if symbol == "BTC/USDT":
        # BTC doesn't need to "align" with itself
        alignment = "N/A (this IS the BTC reference)"
    elif btc_regime in ("BULLISH", "NEUTRAL") and coin_trend in ("BULLISH", "NEUTRAL"):
        alignment = "SUPPORTIVE"
    elif btc_regime in ("BEARISH", "NEUTRAL") and coin_trend in ("BEARISH", "NEUTRAL"):
        alignment = "SUPPORTIVE"
    elif btc_regime == "BULLISH" and coin_trend == "BEARISH":
        alignment = "CONFLICTING"
    elif btc_regime == "BEARISH" and coin_trend == "BULLISH":
        alignment = "CONFLICTING"
    else:
        alignment = "UNCLEAR"

    # ---- Combine everything into a letter grade ----
    # Simple point system: start at 0, add/subtract points, then convert to a grade.
    score = 0
    reasons = []

    if volume_ok:
        score += 2
        reasons.append("Volume: sufficient (+2)")
    else:
        score -= 2
        reasons.append("Volume: too low (-2)")

    if spread_ok:
        score += 1
        reasons.append("Spread: tight/healthy (+1)")
    else:
        score -= 1
        reasons.append("Spread: too wide (-1)")

    if alignment == "SUPPORTIVE":
        score += 2
        reasons.append("BTC alignment: supportive (+2)")
    elif alignment == "CONFLICTING":
        score -= 2
        reasons.append("BTC alignment: conflicting (-2)")
    else:
        reasons.append("BTC alignment: neutral/unclear (0)")

    # Convert numeric score into the letter grades the spec asks for
    if score >= 4:
        grade = "A+"
    elif score >= 2:
        grade = "A"
    elif score >= 0:
        grade = "B"
    elif score >= -2:
        grade = "C"
    else:
        grade = "AVOID"

    return {
        "symbol": symbol,
        "price": health["last_price"],
        "volume_24h_usdt": health["volume_24h_usdt"],
        "spread_percent": health["spread_percent"],
        "coin_trend_4h": coin_trend,
        "btc_alignment": alignment,
        "score": score,
        "grade": grade,
        "reasons": reasons,
    }


# --------------------------------------------------------------------
# STEP C: Scan the whole approved list and rank everything
# --------------------------------------------------------------------

def run_market_scan() -> list:
    """
    Runs the full scan: get BTC regime first (everything else depends
    on it), then grade every approved coin, then sort best-to-worst.
    """
    btc_report = determine_btc_regime()
    btc_regime = btc_report["final_btc_regime"]

    graded_coins = []
    for symbol in APPROVED_COINS:
        try:
            result = grade_coin(symbol, btc_regime)
            graded_coins.append(result)
        except Exception as e:
            graded_coins.append({"symbol": symbol, "grade": "ERROR", "reasons": [str(e)]})

    # Sort so the best-graded coins appear first
    grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "AVOID": 4, "ERROR": 5}
    graded_coins.sort(key=lambda c: grade_order.get(c.get("grade", "ERROR"), 99))

    return btc_regime, graded_coins


# --------------------------------------------------------------------
# RUN IT
# --------------------------------------------------------------------

if __name__ == "__main__":
    print("Running market scan across approved coins...\n")

    btc_regime, ranked_coins = run_market_scan()

    print("=" * 60)
    print("MARKET SCAN REPORT")
    print("=" * 60)
    print(f"Checked at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"BTC Regime: {btc_regime}")
    print("-" * 60)
    print("ASSET RANKING:")
    print("-" * 60)

    for i, coin in enumerate(ranked_coins, start=1):
        print(f"{i}. {coin['symbol']:<10} — Grade: {coin.get('grade', 'ERROR')}")
        if "price" in coin:
            print(f"   Price: ${coin['price']:,}" if coin['price'] else "   Price: N/A")
            print(f"   24h Volume (USDT): {coin['volume_24h_usdt']:,.0f}" if coin['volume_24h_usdt'] else "   Volume: N/A")
            print(f"   Spread: {coin['spread_percent']:.4f}%" if coin['spread_percent'] is not None else "   Spread: N/A")
            print(f"   4H Trend: {coin['coin_trend_4h']}")
            print(f"   BTC Alignment: {coin['btc_alignment']}")
        print(f"   Reasons: {'; '.join(coin.get('reasons', []))}")
        print()

    print("=" * 60)
