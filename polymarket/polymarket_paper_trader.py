#!/usr/bin/env python3
"""
================================================================================
POLYMARKET ALL-MARKET PAPER TRADING ENGINE
================================================================================
Scans live prediction markets across categories on Polymarket.
Now uses BTC bias filter for crypto bets (not random cheap contract accumulation).
Non-crypto categories use asymmetric price filter only (honest about having no model).
================================================================================
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timezone

from polymarket_client import (
    PolymarketClient, evaluate_btc_bias, check_market_resolved,
    CLOB_API_URL, get_now_utc8_str
)

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polymarket_paper_ledger.json")

DEFAULT_STARTING_BALANCE = 100.00
BET_SIZE_USD = 5.00
MAX_CONCURRENT_POSITIONS = 8
STALE_HOURS = 48

CATEGORIES = [
    ("CRYPTO", "crypto"),
    ("POLITICS", "politics"),
    ("WEATHER", "weather"),
    ("GLOBAL", "pop-culture")
]


class PolymarketPaperTrader:
    def __init__(self, starting_balance: float = DEFAULT_STARTING_BALANCE):
        self.starting_balance = starting_balance
        self.client = PolymarketClient()
        self.state = self._load_ledger()

    def _load_ledger(self) -> dict:
        if os.path.exists(LEDGER_FILE):
            try:
                with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "virtual_wallet": self.starting_balance,
            "starting_capital": self.starting_balance,
            "realized_pnl": 0.0,
            "wins": 0, "losses": 0,
            "open_positions": [],
            "closed_trades": []
        }

    def _save_ledger(self):
        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _get_win_rate(self) -> float:
        total = self.state['wins'] + self.state['losses']
        return (self.state['wins'] / total * 100.0) if total > 0 else 0.0

    def _evaluate_positions(self):
        """Update prices, check resolution, apply time-decay exit."""
        remaining = []
        now = datetime.now(timezone.utc)

        for pos in self.state['open_positions']:
            token_id = pos.get('token_id', '')
            market_id = pos.get('market_id', '')

            # Update midpoint
            mid = self.client.get_market_midpoint(token_id)
            if mid is not None:
                pos['current_price'] = mid

            # Check actual resolution via API
            if market_id:
                resolution = check_market_resolved(market_id)
                if resolution and resolution.get('resolved'):
                    winner = resolution.get('winner', '')
                    if winner and winner.upper() == pos['outcome'].upper():
                        payout = pos['shares'] * 1.00
                        profit = payout - pos['cost']
                        self.state['virtual_wallet'] += payout
                        self.state['realized_pnl'] += profit
                        self.state['wins'] += 1
                        self.state['closed_trades'].append({**pos, "status": "WIN", "pnl": profit})
                        print(f" 🏆 [WIN] {pos['question']} | +${profit:.2f}")
                        continue
                    elif winner:
                        loss = -pos['cost']
                        self.state['realized_pnl'] += loss
                        self.state['losses'] += 1
                        self.state['closed_trades'].append({**pos, "status": "LOSS", "pnl": loss})
                        print(f" 🔴 [LOSS] {pos['question']} | -${pos['cost']:.2f}")
                        continue

            # Time-decay exit
            opened_at = pos.get('opened_at', '')
            if opened_at:
                try:
                    open_time = datetime.strptime(opened_at, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                    hours_held = (now - open_time).total_seconds() / 3600
                    if hours_held >= STALE_HOURS and pos['current_price'] < pos['entry_price']:
                        sell_value = pos['shares'] * pos['current_price']
                        pnl = sell_value - pos['cost']
                        self.state['virtual_wallet'] += sell_value
                        self.state['realized_pnl'] += pnl
                        if pnl >= 0:
                            self.state['wins'] += 1
                        else:
                            self.state['losses'] += 1
                        self.state['closed_trades'].append({**pos, "status": "TIME_EXIT", "pnl": pnl})
                        print(f" ⏰ [TIME EXIT] {pos['question']} | {hours_held:.0f}h | ${pnl:+.2f}")
                        continue
                except Exception:
                    pass

            remaining.append(pos)

        self.state['open_positions'] = remaining
        self._save_ledger()

    def scan_and_trade(self):
        print("=" * 100)
        print(" POLYMARKET PAPER TRADING ENGINE")
        print(f" {get_now_utc8_str()}")
        print(f" Wallet: ${self.state['virtual_wallet']:,.2f} | WR: {self._get_win_rate():.1f}%")
        print("=" * 100)

        # Update positions first
        self._evaluate_positions()

        # Get BTC bias for crypto filtering
        btc = evaluate_btc_bias()
        btc_price = btc['price'] if btc else None

        open_tokens = {p['token_id'] for p in self.state['open_positions']}
        new_trades = 0

        for cat_name, tag in CATEGORIES:
            events = self.client.get_events(tag_slug=tag, limit=35)
            if not events:
                # Fallback to query
                events = self.client.get_events(query=tag, limit=20)
            if not events:
                continue

            for event in events:
                title = event.get('title', '')
                for m in event.get('markets', []):
                    parsed = PolymarketClient.parse_market(m)
                    if not parsed:
                        continue
                    outcomes, prices, clob_tokens = parsed
                    q = m.get('question', title)
                    market_id = m.get('id', '')

                    for idx, (outcome, price) in enumerate(zip(outcomes, prices)):
                        # Asymmetric price filter
                        if price < 0.05 or price > 0.35:
                            continue

                        token_id = clob_tokens[idx] if idx < len(clob_tokens) else f"{market_id}_{outcome}"
                        if token_id in open_tokens:
                            continue

                        # For crypto: require BTC model alignment
                        is_crypto = (tag == "crypto")
                        should_trade = False
                        direction = None

                        if is_crypto and btc:
                            direction = PolymarketClient.detect_direction(q, outcome, btc_price)
                            if direction == 'BULL' and btc['bias'] == 'BULLISH' and btc['signal_strength'] >= 3:
                                should_trade = True
                            elif direction == 'BEAR' and btc['bias'] == 'BEARISH' and btc['signal_strength'] >= 3:
                                should_trade = True
                            # ponytail: non-BTC crypto contracts with no threshold → skip
                            # (honest about having no model for them)
                        elif not is_crypto:
                            # Non-crypto: asymmetric filter only, no pretend model
                            # ponytail: this is still random accumulation for non-crypto,
                            # but at least we're honest about it. Add model when one exists.
                            should_trade = True
                            direction = "UNMODELED"

                        if not should_trade:
                            continue

                        if len(self.state['open_positions']) >= MAX_CONCURRENT_POSITIONS:
                            break
                        if self.state['virtual_wallet'] < BET_SIZE_USD:
                            break

                        shares = BET_SIZE_USD / price
                        payout_mult = 1.0 / price
                        self.state['virtual_wallet'] -= BET_SIZE_USD

                        new_pos = {
                            "category": cat_name,
                            "event": title[:45],
                            "question": q[:60],
                            "outcome": outcome,
                            "token_id": token_id,
                            "market_id": market_id,
                            "entry_price": price,
                            "current_price": price,
                            "cost": BET_SIZE_USD,
                            "shares": shares,
                            "payout_if_yes": shares * 1.00,
                            "payout_multiplier": payout_mult,
                            "direction": direction,
                            "opened_at": get_now_utc8_str()
                        }
                        self.state['open_positions'].append(new_pos)
                        open_tokens.add(token_id)
                        new_trades += 1
                        print(f" 🚀 [{cat_name}] {q[:45]} | {outcome} @ ${price:.3f} ({payout_mult:.1f}x) | {direction or '?'}")

                if len(self.state['open_positions']) >= MAX_CONCURRENT_POSITIONS:
                    break

        self._save_ledger()
        self._display_summary()

    def _display_summary(self):
        print("\n" + "=" * 100)
        print(" OPEN PAPER POSITIONS:")
        print("=" * 100)
        if not self.state['open_positions']:
            print("   (none)")
        else:
            for p in self.state['open_positions']:
                u_pnl = (p['current_price'] - p['entry_price']) * p['shares']
                icon = "🟢" if u_pnl >= 0 else "🔴"
                cat = p.get('category', '?')
                print(f" {cat:>8} | {p['question'][:45]} | {p['outcome']} @ ${p['entry_price']:.3f} → ${p['current_price']:.3f} | {icon} ${u_pnl:+.2f}")

        total_target = sum(p['payout_if_yes'] for p in self.state['open_positions'])
        print("=" * 100)
        print(f" Cash: ${self.state['virtual_wallet']:,.2f} | Target Payouts: ${total_target:,.2f}")
        print(f" PnL: ${self.state['realized_pnl']:+,.2f} | WR: {self._get_win_rate():.1f}% ({self.state['wins']}W/{self.state['losses']}L)")
        print("=" * 100)


if __name__ == '__main__':
    trader = PolymarketPaperTrader(starting_balance=100.00)
    trader.scan_and_trade()
