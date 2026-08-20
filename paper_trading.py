"""
==========================================================================
 PAPER TRADING ENGINE (Fake Money Only)
==========================================================================
Plain-English explanation:

This is a SIMULATION. No real exchange account, no real money, ever.

It keeps track of a pretend account balance (starting at a fake $10,000)
saved in a file called "paper_trades.json" in this same folder. Every
time the dashboard checks the market:

  1. If there's a valid new signal (LONG/SHORT) for a coin, and we don't
     already have a fake position open on that coin, it automatically
     "opens" one - calculating position size using a real risk-management
     rule (risking only 1% of the fake balance per trade, matching your
     friend's spec).

  2. For coins we already have a fake position open on, it checks the
     current price: did it hit the stop loss (fake loss) or take-profit
     target (fake win)? If so, it closes the position and records the
     result.

  3. Everything is saved to the trade journal so you can see, over time,
     whether this strategy WOULD have made or lost fake money - before
     anyone considers using real money.

IMPORTANT HONEST LIMITATION:
This checks prices only whenever the dashboard is refreshed/loaded - it
does not watch the market every single second in between. So it's an
approximation, not a perfectly precise simulation of exact execution
timing. Good enough for learning whether a strategy has promise; not a
substitute for a proper backtesting engine over historical data.
==========================================================================
"""

import json
import os
from datetime import datetime

from step1_btc_regime import fetch_candles

# --------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------

JOURNAL_FILE = "paper_trades.json"
STARTING_BALANCE = 10_000.0   # fake starting money, in USDT
RISK_PER_TRADE_PERCENT = 1.0   # risk 1% of current fake balance per trade


# --------------------------------------------------------------------
# STEP A: Load / save the journal file
# --------------------------------------------------------------------

def load_journal() -> dict:
    """
    Loads the paper trading state from disk. If it doesn't exist yet
    (first time running), creates a fresh one with the starting balance.
    """
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "r") as f:
            return json.load(f)

    return {
        "balance": STARTING_BALANCE,
        "open_positions": [],   # currently active fake trades
        "closed_trades": [],    # completed fake trades (the "journal")
    }


def save_journal(journal: dict):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal, f, indent=2)


# --------------------------------------------------------------------
# STEP B: Open a new fake position from a valid signal
# --------------------------------------------------------------------

def open_position(journal: dict, signal: dict):
    """
    Calculates a sensible fake position size (risking only 1% of the
    current fake balance) and adds it to open_positions.
    """
    symbol = signal["symbol"]

    # Don't open a duplicate position if one is already open on this coin
    already_open = any(p["symbol"] == symbol for p in journal["open_positions"])
    if already_open:
        return

    entry = signal["entry"]
    stop_loss = signal["stop_loss"]
    take_profit = signal["tp2"]   # using TP2 as the target we track to close, matching Step 3's R:R calc
    direction = signal["direction"]

    risk_amount = journal["balance"] * (RISK_PER_TRADE_PERCENT / 100)
    stop_distance = abs(entry - stop_loss)

    if stop_distance == 0:
        return  # avoid divide-by-zero, shouldn't normally happen

    position_size = risk_amount / stop_distance   # how many "coins" this fake trade uses

    position = {
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "position_size": position_size,
        "risk_amount": risk_amount,
        "opened_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    journal["open_positions"].append(position)


# --------------------------------------------------------------------
# STEP C: Check open positions against the current price
# --------------------------------------------------------------------

def check_open_positions(journal: dict):
    """
    For every open fake position, fetches the current price and checks
    whether it has hit the stop loss (fake loss) or take profit
    (fake win). Closes and records the result if so.
    """
    still_open = []

    for position in journal["open_positions"]:
        symbol = position["symbol"]

        try:
            df = fetch_candles(symbol, "15m", limit=2)
            current_price = df["close"].iloc[-1]
        except Exception:
            # If we can't fetch a price right now, just leave it open and try again next time
            still_open.append(position)
            continue

        direction = position["direction"]
        hit_stop = False
        hit_target = False

        if direction == "LONG":
            hit_stop = current_price <= position["stop_loss"]
            hit_target = current_price >= position["take_profit"]
        else:  # SHORT
            hit_stop = current_price >= position["stop_loss"]
            hit_target = current_price <= position["take_profit"]

        if hit_stop or hit_target:
            result = "WIN" if hit_target else "LOSS"
            exit_price = position["take_profit"] if hit_target else position["stop_loss"]

            if direction == "LONG":
                pnl = (exit_price - position["entry"]) * position["position_size"]
            else:
                pnl = (position["entry"] - exit_price) * position["position_size"]

            journal["balance"] += pnl

            closed_trade = {
                **position,
                "exit_price": exit_price,
                "result": result,
                "pnl": round(pnl, 2),
                "closed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            }
            journal["closed_trades"].append(closed_trade)
        else:
            still_open.append(position)

    journal["open_positions"] = still_open


# --------------------------------------------------------------------
# STEP D: Run a full paper-trading cycle (used by the dashboard)
# --------------------------------------------------------------------

def run_paper_trading_cycle(signals: list) -> dict:
    """
    The main function the dashboard calls. Loads the journal, checks
    existing positions, opens any new valid signals, saves, returns
    the updated state.
    """
    journal = load_journal()

    check_open_positions(journal)

    for signal in signals:
        if signal.get("direction") in ("LONG", "SHORT"):
            open_position(journal, signal)

    save_journal(journal)
    return journal


# --------------------------------------------------------------------
# STEP E: Calculate performance stats for display
# --------------------------------------------------------------------

def calculate_performance(journal: dict) -> dict:
    closed = journal["closed_trades"]
    total = len(closed)
    wins = len([t for t in closed if t["result"] == "WIN"])
    losses = total - wins

    win_rate = (wins / total * 100) if total > 0 else 0
    total_pnl = journal["balance"] - STARTING_BALANCE

    return {
        "starting_balance": STARTING_BALANCE,
        "current_balance": round(journal["balance"], 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "open_positions_count": len(journal["open_positions"]),
    }


# --------------------------------------------------------------------
# RUN IT STANDALONE (for testing outside the dashboard)
# --------------------------------------------------------------------

if __name__ == "__main__":
    from step1_btc_regime import determine_btc_regime
    from step2_market_scanner import APPROVED_COINS
    from step3_entry_signals import generate_entry_signal

    print("Running one paper-trading cycle...\n")

    btc_report = determine_btc_regime()
    regime = btc_report["final_btc_regime"]

    signals = []
    for symbol in APPROVED_COINS:
        try:
            signals.append(generate_entry_signal(symbol, regime))
        except Exception as e:
            print(f"{symbol}: error - {e}")

    journal = run_paper_trading_cycle(signals)
    stats = calculate_performance(journal)

    print("=" * 50)
    print("PAPER TRADING STATUS")
    print("=" * 50)
    print(f"Starting balance: ${stats['starting_balance']:,.2f}")
    print(f"Current balance:  ${stats['current_balance']:,.2f}")
    print(f"Total P&L:        ${stats['total_pnl']:,.2f}")
    print(f"Open positions:   {stats['open_positions_count']}")
    print(f"Closed trades:    {stats['total_trades']}")
    print(f"Win rate:         {stats['win_rate']}% ({stats['wins']}W / {stats['losses']}L)")
    print("=" * 50)
