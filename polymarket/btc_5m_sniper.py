#!/usr/bin/env python3
"""
================================================================================
⚡ POLYMARKET BTC 5-MINUTE UP/DOWN 24/7 CONTINUOUS SCALPER & SNIPER
================================================================================
Runs a continuous high-frequency loop (polls every 30 seconds):
1. Connects to live Binance Futures 1m/5m order flow (Taker Buy Vol, EMA 9/21, RSI).
2. Constantly searches for active rolling 5-minute Polymarket contracts:
   (https://polymarket.com/event/btc-updown-5m-...)
3. Automatically triggers high-conviction UP / DOWN bets.
4. Auto-settles won ($1.00 payout) and lost contracts on resolution.
5. Sends real-time Telegram alerts for entries and winning payouts.
================================================================================
"""
import os
import sys
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

POLY_DIR = os.path.dirname(os.path.abspath(__file__))
if POLY_DIR not in sys.path:
    sys.path.insert(0, POLY_DIR)

from polymarket_client import (
    PolymarketClient, GAMMA_API_URL, CLOB_API_URL, BINANCE_FUTURES_API,
    get_now_utc8_str
)

LEDGER_5M_FILE = os.path.join(POLY_DIR, "polymarket_5m_ledger.json")
BET_SIZE_USD = 5.00
STARTING_BALANCE = 100.00
LOOP_INTERVAL_SECONDS = 30  # Continuous 30-second polling for 5m contracts

TELEGRAM_ENABLED = os.getenv("TELEGRAM_NOTIFICATIONS", "false").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def send_telegram(msg: str):
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass


class BTC5mSniper:
    def __init__(self):
        self.client = PolymarketClient()
        self.state = self._load_ledger()

    def _load_ledger(self) -> dict:
        if os.path.exists(LEDGER_5M_FILE):
            try:
                with open(LEDGER_5M_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "virtual_wallet": STARTING_BALANCE,
            "starting_capital": STARTING_BALANCE,
            "realized_pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "open_positions": [],
            "closed_trades": []
        }

    def _save_ledger(self):
        with open(LEDGER_5M_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def get_live_5m_markets(self) -> list:
        """Find the active rolling 5-minute BTC Up/Down Polymarket event closing in the next 5-30 mins."""
        try:
            params = {
                "series_slug": "btc-up-or-down-5m",
                "active": "true",
                "closed": "false",
                "limit": 50
            }
            res = requests.get(f"{GAMMA_API_URL}/events", params=params, timeout=5).json()
            if not res or not isinstance(res, list):
                res = requests.get(f"{GAMMA_API_URL}/events?tag_slug=5M&active=true&closed=false&limit=50", timeout=5).json()

            now_dt = datetime.now(timezone.utc)
            valid_markets = []

            for ev in (res if isinstance(res, list) else []):
                slug = ev.get('slug', '') or ''
                series_slug = ev.get('seriesSlug', '') or ''

                is_btc = ('btc' in slug.lower() or 'btc-up-or-down-5m' in series_slug or 'bitcoin' in ev.get('title','').lower())
                if not is_btc:
                    continue

                for m in (ev.get('markets', []) or []):
                    if not m.get('active', True) or m.get('closed', False):
                        continue

                    end_iso = m.get('endDate', '')
                    if not end_iso:
                        continue

                    try:
                        end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
                        time_left_sec = (end_dt - now_dt).total_seconds()

                        # Only pick contracts closing in the next 0 to 30 minutes (current/upcoming 5m windows)
                        if time_left_sec < 0 or time_left_sec > 1800:
                            continue
                    except Exception:
                        continue

                    raw_out = m.get('outcomes', '["Up","Down"]')
                    outcomes = json.loads(raw_out) if isinstance(raw_out, str) else (raw_out or ["Up", "Down"])
                    
                    raw_p = m.get('outcomePrices')
                    if raw_p:
                        prices = [float(p) for p in (json.loads(raw_p) if isinstance(raw_p, str) else raw_p)]
                    else:
                        prices = [0.50, 0.50]

                    raw_tok = m.get('clobTokenIds')
                    tokens = json.loads(raw_tok) if isinstance(raw_tok, str) else (raw_tok or [])

                    valid_markets.append({
                        "event_title": ev.get('title'),
                        "question": m.get('question'),
                        "slug": m.get('slug', slug),
                        "market_id": m.get('id'),
                        "condition_id": m.get('conditionId'),
                        "outcomes": outcomes,
                        "prices": prices,
                        "clob_tokens": tokens,
                        "end_date": end_iso,
                        "time_left_sec": time_left_sec,
                        "start_time": m.get('eventStartTime', m.get('startDate', ''))
                    })

            # Sort by earliest closing time (immediate next 5-minute candle first)
            valid_markets = sorted(valid_markets, key=lambda x: x['time_left_sec'])
            return valid_markets
        except Exception as e:
            return []

    def evaluate_1m_5m_micro_momentum(self) -> dict:
        """Analyze high-frequency 1m & 5m BTC candle velocity, taker volume, and RSI."""
        try:
            r1m = requests.get(
                f"{BINANCE_FUTURES_API}/fapi/v1/klines",
                params={"symbol": "BTCUSDT", "interval": "1m", "limit": 60},
                timeout=4
            ).json()
            df = pd.DataFrame(r1m, columns=['ot', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 'trades', 'tb_b', 'tb_q', 'i'])
            for col in ['o', 'h', 'l', 'c', 'v', 'tb_b']:
                df[col] = df[col].astype(float)

            c = df['c'].values
            v = df['v'].values
            tb = df['tb_b'].values
            curr_p = c[-1]

            ema9 = pd.Series(c).ewm(span=9).mean().iloc[-1]
            ema21 = pd.Series(c).ewm(span=21).mean().iloc[-1]

            recent_buy_vol = tb[-5:].sum()
            recent_tot_vol = v[-5:].sum()
            buy_ratio = (recent_buy_vol / (recent_tot_vol + 1e-9)) * 100.0

            diff = pd.Series(c).diff()
            gain = diff.where(diff > 0, 0.0).rolling(14).mean()
            loss = (-diff.where(diff < 0, 0.0)).rolling(14).mean()
            rsi1m = (100.0 - (100.0 / (1.0 + gain / (loss + 1e-9)))).iloc[-1]

            five_min_open = df['o'].iloc[-5]
            pct_change_5m = ((curr_p - five_min_open) / five_min_open) * 100.0

            score_up = 0
            score_down = 0

            if curr_p > ema9 >= ema21:
                score_up += 2
            elif curr_p < ema9 <= ema21:
                score_down += 2

            if buy_ratio > 54.0:
                score_up += 2
            elif buy_ratio < 46.0:
                score_down += 2

            if rsi1m > 52.0:
                score_up += 1
            elif rsi1m < 48.0:
                score_down += 1

            if pct_change_5m > 0.04:
                score_up += 1
            elif pct_change_5m < -0.04:
                score_down += 1

            prediction = "UP" if score_up > score_down and score_up >= 3 else ("DOWN" if score_down > score_up and score_down >= 3 else "NEUTRAL")
            conviction = max(score_up, score_down)

            return {
                "price": curr_p,
                "ema9": ema9,
                "ema21": ema21,
                "buy_ratio": buy_ratio,
                "rsi1m": rsi1m,
                "pct_change_5m": pct_change_5m,
                "prediction": prediction,
                "conviction": conviction,
                "score_up": score_up,
                "score_down": score_down
            }
        except Exception as e:
            return {"price": 0.0, "prediction": "NEUTRAL", "conviction": 0}

    def update_5m_positions(self):
        """Check resolution of open 5m contracts."""
        remaining = []
        now_dt = datetime.now(timezone.utc)

        for pos in self.state['open_positions']:
            market_id = pos.get('market_id')
            token_id = pos.get('token_id')

            mid = self.client.get_market_midpoint(token_id)
            if mid is not None:
                pos['current_price'] = mid

            resolved = False
            try:
                res = requests.get(f"{GAMMA_API_URL}/markets/{market_id}", timeout=4).json()
                if res.get('closed') or res.get('resolved'):
                    outcomes = json.loads(res.get('outcomes', '["Up","Down"]')) if isinstance(res.get('outcomes'), str) else res.get('outcomes')
                    prices = [float(p) for p in (json.loads(res.get('outcomePrices', '["0.5","0.5"]')) if isinstance(res.get('outcomePrices'), str) else res.get('outcomePrices'))]
                    
                    winner = None
                    for out, p in zip(outcomes, prices):
                        if p >= 0.95:
                            winner = out
                            break

                    if winner and winner.upper() == pos['outcome'].upper():
                        payout = pos['shares'] * 1.00
                        profit = payout - pos['cost']
                        self.state['virtual_wallet'] += payout
                        self.state['realized_pnl'] += profit
                        self.state['wins'] += 1
                        self.state['closed_trades'].append({**pos, "status": "WIN", "pnl": profit, "settled_at": now_dt.isoformat()})
                        print(f" 🏆 [5M RESOLVED WIN] {pos['question']} | Profit: +${profit:.2f} USDC!")
                        send_telegram(f"🏆 *5M POLYMARKET WIN*\n\n• Market: `{pos['question']}`\n• Outcome: `{pos['outcome']}`\n• Payout: `+${profit:.2f} USDC`\n• Wallet: `${self.state['virtual_wallet']:.2f}`")
                        resolved = True
                    elif winner:
                        loss = -pos['cost']
                        self.state['realized_pnl'] += loss
                        self.state['losses'] += 1
                        self.state['closed_trades'].append({**pos, "status": "LOSS", "pnl": loss, "settled_at": now_dt.isoformat()})
                        print(f" 🔴 [5M RESOLVED LOSS] {pos['question']} | Loss: -${pos['cost']:.2f}")
                        resolved = True
            except Exception:
                pass

            if not resolved:
                remaining.append(pos)

        self.state['open_positions'] = remaining
        self._save_ledger()

    def run_sniper_cycle(self):
        print("\n" + "=" * 105)
        print(" ⚡ POLYMARKET BTC 5-MINUTE SCALPER & SNIPER CYCLE")
        print(f" Timestamp: {get_now_utc8_str()}")
        print("=" * 105)

        micro = self.evaluate_1m_5m_micro_momentum()
        print(f" 📊 BTC Spot: ${micro['price']:,.2f} | 1m RSI: {micro.get('rsi1m',50):.1f} | Taker Buy: {micro.get('buy_ratio',50):.1f}% | 5m Delta: {micro.get('pct_change_5m',0):+.2f}%")
        print(f" 🎯 5M Signal: {micro['prediction']} (Conviction: {micro['conviction']}/6 | Up: {micro.get('score_up',0)} vs Down: {micro.get('score_down',0)})")
        print("-" * 105)

        self.update_5m_positions()

        markets = self.get_live_5m_markets()
        if not markets:
            print(" [ℹ️] Scanning for next rolling 5-minute contract on Polymarket...")
            self._print_summary()
            return

        open_tokens = {p['token_id'] for p in self.state['open_positions']}

        for m in markets:
            outcomes = m['outcomes']
            prices = m['prices']
            clob_tokens = m['clob_tokens']

            up_idx = next((i for i, o in enumerate(outcomes) if o.lower() == 'up'), 0)
            down_idx = next((i for i, o in enumerate(outcomes) if o.lower() == 'down'), 1)

            up_price = prices[up_idx] if up_idx < len(prices) else 0.50
            down_price = prices[down_idx] if down_idx < len(prices) else 0.50

            up_token = clob_tokens[up_idx] if up_idx < len(clob_tokens) else f"{m['market_id']}_Up"
            down_token = clob_tokens[down_idx] if down_idx < len(clob_tokens) else f"{m['market_id']}_Down"

            target_outcome = None
            target_price = 0.50
            target_token = None

            if micro['prediction'] == "UP" and micro['conviction'] >= 3:
                target_outcome = "Up"
                target_price = up_price
                target_token = up_token
            elif micro['prediction'] == "DOWN" and micro['conviction'] >= 3:
                target_outcome = "Down"
                target_price = down_price
                target_token = down_token

            if target_outcome and target_token not in open_tokens:
                if len(self.state['open_positions']) >= 3:
                    continue
                if self.state['virtual_wallet'] < BET_SIZE_USD:
                    continue

                shares = BET_SIZE_USD / target_price
                payout_mult = 1.0 / target_price
                self.state['virtual_wallet'] -= BET_SIZE_USD

                new_pos = {
                    "question": m['question'],
                    "slug": m['slug'],
                    "market_id": m['market_id'],
                    "token_id": target_token,
                    "outcome": target_outcome,
                    "entry_price": target_price,
                    "current_price": target_price,
                    "cost": BET_SIZE_USD,
                    "shares": shares,
                    "payout_if_win": shares * 1.00,
                    "payout_multiplier": payout_mult,
                    "micro_signal": micro['prediction'],
                    "conviction": micro['conviction'],
                    "entered_at": get_now_utc8_str()
                }
                self.state['open_positions'].append(new_pos)
                open_tokens.add(target_token)
                print(f" 🚀 [5M BET PLACED] {m['question']}")
                print(f"    ➔ Bet ${BET_SIZE_USD:.2f} on {target_outcome.upper()} @ ${target_price:.3f} (Target Payout: ${new_pos['payout_if_win']:.2f} / {payout_mult:.2f}x)")
                send_telegram(f"⚡ *BTC 5M BET PLACED*\n\n• Market: `{m['question']}`\n• Pick: *{target_outcome.upper()}* @ `${target_price:.3f}`\n• Stake: `${BET_SIZE_USD:.2f}` ➔ Target: `${new_pos['payout_if_win']:.2f}`\n• Conviction: `{micro['conviction']}/6`")

        self._save_ledger()
        self._print_summary()

    def _print_summary(self):
        total = self.state['wins'] + self.state['losses']
        wr = (self.state['wins'] / total * 100.0) if total > 0 else 0.0
        print("-" * 105)
        print(" 📋 ACTIVE 5-MINUTE POSITIONS:")
        if not self.state['open_positions']:
            print("   (No active open 5m positions)")
        else:
            for p in self.state['open_positions']:
                u_pnl = (p['current_price'] - p['entry_price']) * p['shares']
                icon = "🟢" if u_pnl >= 0 else "🔴"
                print(f"   • {p['question']} | {p['outcome']} @ ${p['entry_price']:.3f} | Mark: ${p['current_price']:.3f} | {icon} uPnL: ${u_pnl:+.2f}")
        print("-" * 105)
        print(f" 💰 Virtual Wallet: ${self.state['virtual_wallet']:,.2f} USDC | Realized PnL: ${self.state['realized_pnl']:+,.2f} USDC | Win Rate: {wr:.1f}% ({self.state['wins']}W / {self.state['losses']}L)")
        print("=" * 105)


def main():
    sniper = BTC5mSniper()
    print("=" * 105)
    print(" ⚡ STARTING 24/7 CONTINUOUS BTC 5-MINUTE UP/DOWN SCALPER DAEMON")
    print(f" • Polling Frequency: Every {LOOP_INTERVAL_SECONDS} seconds")
    print(f" • Micro-Strategy: 1m/5m Taker Flow Aggression + EMA 9/21 Momentum")
    print(" • Press Ctrl+C to stop.")
    print("=" * 105)

    while True:
        try:
            sniper.run_sniper_cycle()
        except KeyboardInterrupt:
            print("\n [!] Stopping BTC 5M Scalper daemon gracefully...")
            break
        except Exception as e:
            print(f"[!] Scalper exception: {e}")
        time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
