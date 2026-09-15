#!/usr/bin/env python3
"""
================================================================================
🌐 POLYMARKET UNIVERSAL 24/7 OMNI-MARKET AUTOPILOT TRADING ENGINE
================================================================================
Autonomous prediction and trading across ALL Polymarket sectors:
- 🏛️ Politics & Fed Macro (Fed Rates, Elections, Ceasefires, Treaties)
- ⚾ Sports & Esports (MLB, Champions League, Tennis, LoL, CS2)
- ⚡ Pop Culture, Tech & AI (GTA VI, AI Models, Tweet Brackets)
- 🌦️ Weather & Climate (City Daily Highs)
- 🪙 Crypto & DeFi (BTC, ETH, SOL, Altcoins)
- 💼 Business & Global Events

Features:
- Multi-Category Quant Predictor (Probability Normalization & Moneyline Value)
- Diversified Portfolio Risk Management (Max 10 concurrent open positions)
- Automatic Real-Time Settlement ($1.00/share payouts via Gamma API)
- 48h Time-Decay Trailing Stop-Loss
- Real-Time Telegram Alerts
- UTC+8 Timestamps throughout
================================================================================
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

POLY_DIR = os.path.dirname(os.path.abspath(__file__))
if POLY_DIR not in sys.path:
    sys.path.insert(0, POLY_DIR)

from polymarket_client import (
    PolymarketClient, UniversalPredictor, evaluate_btc_bias, check_market_resolved,
    POLYMARKET_CATEGORIES, GAMMA_API_URL, CLOB_API_URL, get_now_utc8_str
)

LEDGER_FILE = os.path.join(POLY_DIR, "polymarket_autopilot_ledger.json")

TELEGRAM_ENABLED = os.getenv("TELEGRAM_NOTIFICATIONS", "false").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

DEFAULT_VIRTUAL_CAPITAL = 100.00
BET_SIZE_USD = 5.00
SCAN_INTERVAL_SECONDS = 300  # 5-minute evaluation loop across all sectors
MAX_TOTAL_POSITIONS = 10     # Max 10 positions across all categories
MAX_PER_CATEGORY = 3         # Max 3 positions per category for diversification
STALE_HOURS = 48


def send_telegram(msg: str):
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass


class PolymarketOmniAutopilot:
    def __init__(self):
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
            "virtual_wallet": DEFAULT_VIRTUAL_CAPITAL,
            "starting_capital": DEFAULT_VIRTUAL_CAPITAL,
            "realized_pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "open_positions": [],
            "closed_trades": []
        }

    def _save_ledger(self):
        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _update_positions(self):
        """Update live CLOB mark prices, check Gamma API resolution, and apply time-decay exits."""
        remaining = []
        now_dt = datetime.now(timezone.utc)

        for p in self.state['open_positions']:
            token_id = p.get('token_id', '')
            market_id = p.get('market_id', '')

            # 1. Update midpoint
            mid = self.client.get_market_midpoint(token_id)
            if mid is not None:
                p['current_price'] = mid

            # 2. Check resolution via Gamma API
            resolved = False
            if market_id:
                resolution = check_market_resolved(market_id)
                if resolution and resolution.get('resolved'):
                    winner = resolution.get('winner', '')
                    if winner and winner.upper() == p['outcome'].upper():
                        payout = p['shares'] * 1.00
                        profit = payout - p['cost']
                        self.state['virtual_wallet'] += payout
                        self.state['realized_pnl'] += profit
                        self.state['wins'] += 1
                        self.state['closed_trades'].append({
                            **p, "status": "WIN", "pnl": profit,
                            "closed_at": get_now_utc8_str()
                        })
                        print(f" 🏆 [RESOLVED WIN] {p['question']} | Profit: +${profit:.2f} USDC!")
                        send_telegram(f"🏆 *POLYMARKET WIN*\n\n• Sector: `{p.get('category','Global')}`\n• Event: `{p['question']}`\n• Pick: *{p['outcome']}*\n• Payout: `+${profit:.2f} USDC`\n• Wallet: `${self.state['virtual_wallet']:.2f}`")
                        resolved = True
                    elif winner:
                        loss = -p['cost']
                        self.state['realized_pnl'] += loss
                        self.state['losses'] += 1
                        self.state['closed_trades'].append({
                            **p, "status": "LOSS", "pnl": loss,
                            "closed_at": get_now_utc8_str()
                        })
                        print(f" 🔴 [RESOLVED LOSS] {p['question']} | Loss: -${p['cost']:.2f}")
                        resolved = True

            if resolved:
                continue

            # 3. Time-decay exit: if held > STALE_HOURS and mark < entry, cut loss
            opened_at = p.get('opened_at_utc', '')
            if opened_at:
                try:
                    open_dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                    hours_held = (now_dt - open_dt).total_seconds() / 3600
                    if hours_held >= STALE_HOURS and p['current_price'] < p['entry_price']:
                        sell_value = p['shares'] * p['current_price']
                        pnl = sell_value - p['cost']
                        self.state['virtual_wallet'] += sell_value
                        self.state['realized_pnl'] += pnl
                        if pnl >= 0:
                            self.state['wins'] += 1
                        else:
                            self.state['losses'] += 1
                        self.state['closed_trades'].append({
                            **p, "status": "TIME_EXIT", "pnl": pnl,
                            "closed_at": get_now_utc8_str()
                        })
                        print(f" ⏰ [TIME EXIT] {p['question']} | Held {hours_held:.0f}h | PnL: ${pnl:+.2f}")
                        continue
                except Exception:
                    pass

            remaining.append(p)

        self.state['open_positions'] = remaining
        self._save_ledger()

    def run_cycle(self):
        print("\n" + "=" * 115)
        print(" 🌐 POLYMARKET UNIVERSAL OMNI-AUTOPILOT TRADING CYCLE")
        print(f" Timestamp: {get_now_utc8_str()}")
        print("=" * 115)

        # 1. Evaluate BTC technicals for crypto contracts
        btc_eval = evaluate_btc_bias()
        if btc_eval and btc_eval.get('price', 0) > 0:
            print(f" 📊 BTC Spot Reference: ${btc_eval['price']:,.2f} | 15m RSI: {btc_eval['rsi']:.1f} | Bias: {btc_eval['bias']} ({btc_eval['signal_strength']}/4 signals)")
            print("-" * 115)

        # 2. Update existing open positions
        self._update_positions()

        # 3. Check overall portfolio capacity
        if len(self.state['open_positions']) >= MAX_TOTAL_POSITIONS:
            print(f" ℹ️ Maximum portfolio capacity reached ({MAX_TOTAL_POSITIONS}/{MAX_TOTAL_POSITIONS} active positions). Monitoring positions.")
            self._print_dashboard()
            return

        if self.state['virtual_wallet'] < BET_SIZE_USD:
            print(f" ⚠️ Low virtual wallet cash (${self.state['virtual_wallet']:.2f}). Waiting for positions to settle.")
            self._print_dashboard()
            return

        open_tokens = {p['token_id'] for p in self.state['open_positions']}
        category_counts = {}
        for p in self.state['open_positions']:
            cat = p.get('tag', 'other')
            category_counts[cat] = category_counts.get(cat, 0) + 1

        new_bets_entered = 0

        # 4. Scan and predict across ALL Polymarket sectors
        for tag_slug, meta in POLYMARKET_CATEGORIES.items():
            if category_counts.get(tag_slug, 0) >= MAX_PER_CATEGORY:
                continue

            events = self.client.get_events(tag_slug=tag_slug, limit=25)
            if not events:
                events = self.client.get_events(query=tag_slug, limit=20)

            for ev in (events or []):
                title = ev.get('title', '')
                vol = float(ev.get('volume24hr') or ev.get('volume') or 0.0)

                for m in (ev.get('markets', []) or []):
                    parsed = PolymarketClient.parse_market(m)
                    if not parsed:
                        continue
                    outcomes, prices, tokens = parsed
                    question = m.get('question', title)
                    market_id = m.get('id', '')

                    for idx, (outcome, price) in enumerate(zip(outcomes, prices)):
                        if price < 0.08 or price > 0.38:
                            continue  # Strict asymmetric sweet-spot ($0.08 - $0.38 / 2.6x to 12.5x payout)

                        token_id = tokens[idx] if idx < len(tokens) else f"{market_id}_{outcome}"
                        if token_id in open_tokens:
                            continue

                        # Run Universal Prediction Model
                        pred = {}
                        if tag_slug == "crypto":
                            pred = UniversalPredictor.evaluate_crypto_contract(question, outcome, price, btc_eval)
                        elif tag_slug in ["politics", "business"]:
                            pred = UniversalPredictor.evaluate_macro_politics(question, outcome, price, outcomes, prices)
                        elif tag_slug == "sports":
                            pred = UniversalPredictor.evaluate_sports_esports(question, outcome, price, outcomes, prices)
                        else:
                            pred = UniversalPredictor.evaluate_bracket_market(question, outcome, price, outcomes, prices)

                        # High Conviction Entry Filter
                        if pred.get('is_recommended', False) and pred.get('conviction', 0) >= 2:
                            if len(self.state['open_positions']) >= MAX_TOTAL_POSITIONS:
                                break
                            if category_counts.get(tag_slug, 0) >= MAX_PER_CATEGORY:
                                break
                            if self.state['virtual_wallet'] < BET_SIZE_USD:
                                break

                            shares = BET_SIZE_USD / price
                            payout_if_yes = shares * 1.00
                            payout_mult = 1.0 / price
                            self.state['virtual_wallet'] -= BET_SIZE_USD

                            new_pos = {
                                "category": meta['name'],
                                "tag": tag_slug,
                                "icon": meta['icon'],
                                "event": title[:45],
                                "question": question[:60],
                                "outcome": outcome,
                                "token_id": token_id,
                                "market_id": market_id,
                                "entry_price": price,
                                "current_price": price,
                                "cost": BET_SIZE_USD,
                                "shares": shares,
                                "payout_if_yes": payout_if_yes,
                                "payout_multiplier": payout_mult,
                                "conviction": pred['conviction'],
                                "model_type": pred['model_type'],
                                "opened_at": get_now_utc8_str(),
                                "opened_at_utc": datetime.now(timezone.utc).isoformat()
                            }
                            self.state['open_positions'].append(new_pos)
                            open_tokens.add(token_id)
                            category_counts[tag_slug] = category_counts.get(tag_slug, 0) + 1
                            new_bets_entered += 1

                            print(f" 🚀 [{meta['icon']} {meta['name']}] {question[:45]}")
                            print(f"    ➔ Bet ${BET_SIZE_USD:.2f} on {outcome} @ ${price:.3f} (Payout: ${payout_if_yes:.2f} / {payout_mult:.1f}x | Model: {pred['model_type']})")
                            send_telegram(f"🌐 *POLYMARKET BET ENTERED*\n\n• Sector: `{meta['name']}`\n• Event: `{question}`\n• Pick: *{outcome}* @ `${price:.3f}`\n• Stake: `${BET_SIZE_USD:.2f}` ➔ Target Payout: `${payout_if_yes:.2f}` ({payout_mult:.1f}x)\n• Model: `{pred['model_type']}`")

                    if len(self.state['open_positions']) >= MAX_TOTAL_POSITIONS:
                        break
                if len(self.state['open_positions']) >= MAX_TOTAL_POSITIONS:
                    break

        self._save_ledger()
        self._print_dashboard()

    def _print_dashboard(self):
        total = self.state['wins'] + self.state['losses']
        wr = (self.state['wins'] / total * 100.0) if total > 0 else 0.0

        print("-" * 115)
        print(" 📋 ACTIVE MULTI-SECTOR OPEN POSITIONS:")
        if not self.state['open_positions']:
            print("   (No active open positions)")
        else:
            print(f" {'Sector':<18} | {'Contract Question':<45} | {'Pick':<8} | {'Entry':<8} | {'Mark':<8} | {'Target Payout'}")
            print("-" * 115)
            for p in self.state['open_positions']:
                u_pnl = (p['current_price'] - p['entry_price']) * p['shares']
                icon = "🟢" if u_pnl >= 0 else "🔴"
                cat_display = f"{p.get('icon','🌐')} {p.get('category','Global')[:14]}"
                payout_str = f"${p['payout_if_yes']:.2f} ({p.get('payout_multiplier', 0.0):.1f}x)"
                print(f" {cat_display:<18} | {p['question'][:43]:<45} | {p['outcome'][:8]:<8} | ${p['entry_price']:<7.3f} | ${p['current_price']:<7.3f} | {icon} {payout_str}")

        total_target_payout = sum(p['payout_if_yes'] for p in self.state['open_positions'])
        print("=" * 115)
        print(f" 💰 Free Virtual Wallet: ${self.state['virtual_wallet']:,.2f} USDC | Target Payouts: ${total_target_payout:,.2f} USDC")
        print(f" 📊 Realized PnL: ${self.state['realized_pnl']:+,.2f} USDC | Win Rate: {wr:.1f}% ({self.state['wins']}W / {self.state['losses']}L)")
        print("=" * 115)


def main():
    bot = PolymarketOmniAutopilot()
    print("=" * 115)
    print(" 🌐 STARTING 24/7 POLYMARKET OMNI-AUTOPILOT PREDICTION & TRADING DAEMON")
    print(f" • Scope: Sports • Politics/Fed • Pop Culture/AI • Weather • Crypto • Business")
    print(f" • Polling Interval: Every {SCAN_INTERVAL_SECONDS} seconds")
    print(" • Press Ctrl+C to stop.")
    print("=" * 115)

    while True:
        try:
            bot.run_cycle()
        except KeyboardInterrupt:
            print("\n [!] Stopping Omni-Autopilot daemon gracefully...")
            break
        except Exception as e:
            print(f"[!] Autopilot exception: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
