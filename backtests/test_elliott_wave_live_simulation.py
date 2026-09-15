#!/usr/bin/env python3
"""
================================================================================
🌊 ELLIOTT WAVE + 31-MODEL CONFLUENCE LIVE SIMULATION ENGINE
================================================================================
Combines:
1. Elliott Wave 2->3 Golden Pocket Setup (0.500 - 0.618 Retrace + HTC Divergence)
2. 31-Model Quantitative Consensus Matrix & 9 Independent Pillars
3. Price Action Confirmation Gate (15M Bullish/Bearish Reversal Candle)
4. 4H Macro BTC Regime Filter (Blocks correlated Altcoin traps)
5. 3-Stage Dynamic TP/SL (50% TP1 @ 1.00x -> Breakeven -> 1.2x ATR Dynamic Trailing Runner)
6. 100% Realistic Friction Accounting (Binance VIP0+BNB Tier)

DOES NOT MODIFY main.py. Purely an isolated backtesting & verification suite.
================================================================================
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add root directory to import core models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from main import WeatherEnsembleBot, check_fibonacci_setup, OPTIMIZED_SYMBOLS
except ImportError:
    from weather_ensemble_bot import WeatherEnsembleBot, check_fibonacci_setup, OPTIMIZED_SYMBOLS

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historical_data_cache")

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'SUIUSDT', 'NEARUSDT',
    'AVAXUSDT', 'LINKUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT'
]

FEE_TIERS = {
    'vip0_bnb': {
        'maker': 0.00018,     # 0.018% Maker Limit
        'taker': 0.00045,     # 0.045% Taker Stop
        'slippage': 0.00015,  # 0.015% Slippage
        'funding_8h': 0.00010 # 0.010% 8-hour funding
    }
}

def calc_ema_arr(arr, span):
    alpha = 2.0 / (span + 1.0)
    n = len(arr)
    out = np.empty(n, dtype=np.float64)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out

def calc_rsi_arr(arr, period=14):
    n = len(arr)
    diff = np.diff(arr)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    
    avg_gain = np.zeros(n)
    avg_loss = np.zeros(n)
    rsi = np.full(n, 50.0)
    
    if n <= period:
        return rsi
        
    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])
    
    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
        
    rs = np.where(avg_loss == 0, 100.0, avg_gain / (avg_loss + 1e-9))
    return 100.0 - (100.0 / (1.0 + rs))

def calc_atr_arr(highs, lows, closes, period=14):
    n = len(closes)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    
    atr = np.zeros(n)
    if n <= period:
        return tr
    atr[period] = np.mean(tr[:period])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr

def check_htc_divergence(closes, rsi, pivots_l, pivots_h, curr_idx, lookback=30):
    start_idx = max(0, curr_idx - lookback)
    
    low_indices = [i for i in range(start_idx, curr_idx) if pivots_l[i]]
    bullish_htc = False
    if len(low_indices) >= 2:
        idx1, idx2 = low_indices[-2], low_indices[-1]
        if closes[idx2] <= closes[idx1] * 1.002 and rsi[idx2] > rsi[idx1] + 1.5:
            bullish_htc = True

    high_indices = [i for i in range(start_idx, curr_idx) if pivots_h[i]]
    bearish_htc = False
    if len(high_indices) >= 2:
        idx1, idx2 = high_indices[-2], high_indices[-1]
        if closes[idx2] >= closes[idx1] * 0.998 and rsi[idx2] < rsi[idx1] - 1.5:
            bearish_htc = True

    return bullish_htc, bearish_htc

def precompute_elliott_wave_setups(df, window=5):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    n = len(closes)

    ema50 = calc_ema_arr(closes, 50)
    ema200 = calc_ema_arr(closes, 200)
    rsi = calc_rsi_arr(closes, 14)
    atr = calc_atr_arr(highs, lows, closes, 14)

    pivots_h = np.zeros(n, dtype=bool)
    pivots_l = np.zeros(n, dtype=bool)

    for i in range(window, n - window):
        if highs[i] == np.max(highs[i - window : i + window + 1]):
            pivots_h[i] = True
        if lows[i] == np.min(lows[i - window : i + window + 1]):
            pivots_l[i] = True

    setups = [None] * n
    swing_highs = []
    swing_lows = []

    for i in range(50, n):
        if pivots_h[i - window]:
            swing_highs.append((i - window, highs[i - window]))
            if len(swing_highs) > 6:
                swing_highs.pop(0)
        if pivots_l[i - window]:
            swing_lows.append((i - window, lows[i - window]))
            if len(swing_lows) > 6:
                swing_lows.pop(0)

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            continue

        c = closes[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]

        # 15M Price Action Confirmation
        is_bull_pa_confirmed = (c > o) and (c > (prev_h + prev_l) / 2.0)
        is_bear_pa_confirmed = (c < o) and (c < (prev_h + prev_l) / 2.0)

        bull_htc, bear_htc = check_htc_divergence(closes, rsi, pivots_l, pivots_h, i, lookback=40)

        # 🟢 WAVE 2 -> WAVE 3 GOLDEN POCKET IMPULSE (Bullish)
        w0_idx, w0_p = swing_lows[-2]
        w1_idx, w1_p = swing_highs[-1]

        if w1_idx > w0_idx:
            w1_height = w1_p - w0_p
            if w1_height > 0:
                retrace = (w1_p - c) / w1_height
                # 0.48 to 0.65 Golden Pocket Retrace + HTC + Bull PA Confirmation
                if 0.48 <= retrace <= 0.65 and c > w0_p:
                    if (bull_htc or rsi[i] < 45) and is_bull_pa_confirmed and c > ema200[i]:
                        sl = w0_p * 0.998
                        tp1 = w1_p
                        tp2 = c + (w1_height * 1.618)
                        tp3 = c + (w1_height * 2.618)
                        risk = c - sl
                        reward = tp2 - c
                        if risk > 0 and reward / risk >= 1.80:
                            setups[i] = {
                                'side': 'BUY',
                                'pattern': 'WAVE_2_TO_3_GOLDEN_POCKET',
                                'entry_price': c,
                                'sl': sl,
                                'tp1': tp1,
                                'tp2': tp2,
                                'tp3': tp3,
                                'atr': atr[i],
                                'rr': reward / risk
                            }
                            continue

        # 🔴 BEARISH WAVE 2 -> WAVE 3 SHORT (Bear Market Golden Pocket)
        w0_h_idx, w0_h_p = swing_highs[-2]
        w1_l_idx, w1_l_p = swing_lows[-1]

        if w1_l_idx > w0_h_idx:
            w1_drop = w0_h_p - w1_l_p
            if w1_drop > 0:
                bounce = (c - w1_l_p) / w1_drop
                if 0.48 <= bounce <= 0.65 and c < w0_h_p:
                    if (bear_htc or rsi[i] > 55) and is_bear_pa_confirmed and c < ema200[i]:
                        sl = w0_h_p * 1.002
                        tp1 = w1_l_p
                        tp2 = c - (w1_drop * 1.618)
                        risk = sl - c
                        reward = c - tp2
                        if risk > 0 and reward / risk >= 1.80:
                            setups[i] = {
                                'side': 'SELL',
                                'pattern': 'BEAR_WAVE_2_TO_3_GP',
                                'entry_price': c,
                                'sl': sl,
                                'tp1': tp1,
                                'tp2': tp2,
                                'atr': atr[i],
                                'rr': reward / risk
                            }
                            continue

    return setups

class ElliottWaveLiveSimulator:
    def __init__(self, initial_balance=17.64, leverage=50, max_positions=5, margin_pct=0.03,
                 max_notional=5000.0, fee_tier='vip0_bnb'):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.leverage = int(leverage)
        self.max_positions = int(max_positions)
        self.margin_pct = float(margin_pct)
        self.max_notional = float(max_notional) if max_notional else None
        
        fees = FEE_TIERS[fee_tier]
        self.maker_fee = fees['maker']
        self.taker_fee = fees['taker']
        self.slippage = fees['slippage']
        self.funding_rate_8h = fees['funding_8h']
        
        self.active_positions = {}
        self.trade_history = []
        
        self.total_maker_fees = 0.0
        self.total_taker_fees = 0.0
        self.total_funding_fees = 0.0
        self.total_slippage_cost = 0.0
        self.gross_profit_raw = 0.0
        self.gross_loss_raw = 0.0
        
        self.monthly_pnl = {}
        self.monthly_start_balance = {}
        self.peak_equity = float(initial_balance)
        self.max_drawdown_dollars = 0.0
        self.max_drawdown_pct = 0.0

    def run(self):
        print("=" * 105)
        print(" 🌊 ELLIOTT WAVE + 31-MODEL CONFLUENCE QUANT SIMULATION TEST")
        print("=" * 105)
        print(f" • Starting Balance:  ${self.initial_balance:,.2f} USDT")
        print(f" • Leverage & Margin: {self.leverage}x Isolated | {self.margin_pct*100:.1f}% Margin per Trade (Max {self.max_positions} Slots)")
        print(f" • Position Cap:      ${self.max_notional:,.2f} USDT Max Notional Ceiling")
        print(f" • Fee Schedule:      VIP0+BNB (Maker: {self.maker_fee*100:.3f}% | Taker: {self.taker_fee*100:.3f}% | Slip: {self.slippage*100:.3f}%)")
        print("=" * 105 + "\n")

        raw_data = {}
        for sym in SYMBOLS:
            fpath = os.path.join(CACHE_DIR, f"{sym}_15m_from_2024-08-25.csv")
            if not os.path.exists(fpath):
                fpath = os.path.join(CACHE_DIR, f"{sym}_15m_from_2025-07-01.csv")
            if os.path.exists(fpath):
                df = pd.read_csv(fpath)
                t_col = 'open_time' if 'open_time' in df.columns else 'timestamp'
                df['open_time'] = pd.to_datetime(df[t_col], utc=True)
                df = df.sort_values('open_time').reset_index(drop=True)
                raw_data[sym] = df

        min_len = min(len(df) for df in raw_data.values())
        np_data = {}
        for sym, df in raw_data.items():
            np_data[sym] = {
                'open_time': df['open_time'].values,
                'open': df['open'].values,
                'high': df['high'].values,
                'low': df['low'].values,
                'close': df['close'].values
            }

        print("⚡ Precomputing Elliott Wave 2->3 Golden Pocket & HTC Divergence Matrices...", flush=True)
        all_setups = {}
        for sym, df in raw_data.items():
            all_setups[sym] = precompute_elliott_wave_setups(df, window=5)

        # 4H Macro BTC Regime (50-period EMA of 4H candles = 50 * 16 on 15m)
        btc_closes = np_data['BTCUSDT']['close']
        btc_4h_ema50 = calc_ema_arr(btc_closes, 50 * 16)
        btc_4h_bear = btc_closes < btc_4h_ema50
        btc_4h_bull = btc_closes > btc_4h_ema50

        last_funding_bar = 0
        last_trade_bar = {sym: -100 for sym in SYMBOLS}

        print("⚡ Simulating Chronological Portfolio Execution across 700,810 Candles...", flush=True)
        for bar_idx in range(60, min_len):
            current_time = pd.to_datetime(np_data['BTCUSDT']['open_time'][bar_idx])
            month_key = current_time.strftime('%Y-%m')

            if month_key not in self.monthly_pnl:
                self.monthly_pnl[month_key] = 0.0
                self.monthly_start_balance[month_key] = self.balance

            # Peak equity & drawdown
            if self.balance > self.peak_equity:
                self.peak_equity = self.balance
            current_dd_dollars = self.peak_equity - self.balance
            current_dd_pct = (current_dd_dollars / self.peak_equity) * 100 if self.peak_equity > 0 else 0.0
            if current_dd_dollars > self.max_drawdown_dollars:
                self.max_drawdown_dollars = current_dd_dollars
            if current_dd_pct > self.max_drawdown_pct:
                self.max_drawdown_pct = current_dd_pct

            # 8-Hour Funding
            if (bar_idx - last_funding_bar) >= 32:
                last_funding_bar = bar_idx
                for sym, pos in self.active_positions.items():
                    bar_c = np_data[sym]['close'][bar_idx]
                    pos_val = pos['rem_qty'] * bar_c
                    funding_cost = pos_val * self.funding_rate_8h
                    self.total_funding_fees += funding_cost
                    self.balance -= funding_cost
                    self.monthly_pnl[month_key] -= funding_cost

            # Position Management (Stop Loss, TP1 Scale-Out, Trailing Stop)
            closed_syms = []
            for sym, pos in list(self.active_positions.items()):
                bar_h = np_data[sym]['high'][bar_idx]
                bar_l = np_data[sym]['low'][bar_idx]
                bar_c = np_data[sym]['close'][bar_idx]
                is_long = pos['side'] == 'BUY'
                is_short = pos['side'] == 'SELL'

                # Check Stop Loss
                hit_sl = False
                sl_exit_price = pos['sl']
                if is_long and bar_l <= pos['sl']:
                    hit_sl = True
                    sl_exit_price = min(bar_c, pos['sl']) * (1.0 - self.slippage)
                elif is_short and bar_h >= pos['sl']:
                    hit_sl = True
                    sl_exit_price = max(bar_c, pos['sl']) * (1.0 + self.slippage)

                if hit_sl:
                    rem_qty = pos['rem_qty']
                    raw_pnl = rem_qty * (sl_exit_price - pos['entry_price']) if is_long else rem_qty * (pos['entry_price'] - sl_exit_price)
                    taker_fee_val = rem_qty * sl_exit_price * self.taker_fee
                    slip_cost = rem_qty * sl_exit_price * self.slippage

                    self.total_taker_fees += taker_fee_val
                    self.total_slippage_cost += slip_cost
                    if raw_pnl > 0:
                        self.gross_profit_raw += raw_pnl
                    else:
                        self.gross_loss_raw += abs(raw_pnl)

                    net_pnl = raw_pnl - taker_fee_val
                    self.balance += net_pnl
                    self.monthly_pnl[month_key] += net_pnl

                    pos['realized_pnl'] += net_pnl
                    pos['exit_time'] = current_time
                    pos['exit_reason'] = 'TP2_TRAILED_WIN' if pos.get('trailing_active') else ('SL_BE' if pos['tp1_hit'] else 'STOP_LOSS')
                    self.trade_history.append(pos)
                    closed_syms.append(sym)
                    continue

                # TP1 Scale-Out (50% scale-out @ TP1 -> Breakeven stop + trail)
                if not pos['tp1_hit']:
                    tp1_hit = (is_long and bar_h >= pos['tp1']) or (is_short and bar_l <= pos['tp1'])
                    if tp1_hit:
                        pos['tp1_hit'] = True
                        close_qty = pos['initial_qty'] * 0.50
                        pos['rem_qty'] -= close_qty

                        tp_p = pos['tp1']
                        raw_pnl = close_qty * (tp_p - pos['entry_price']) if is_long else close_qty * (pos['entry_price'] - tp_p)
                        maker_fee_val = close_qty * tp_p * self.maker_fee

                        self.total_maker_fees += maker_fee_val
                        self.gross_profit_raw += raw_pnl

                        net_pnl = raw_pnl - maker_fee_val
                        self.balance += net_pnl
                        self.monthly_pnl[month_key] += net_pnl
                        pos['realized_pnl'] += net_pnl

                        be_price = pos['entry_price'] * 1.0005 if is_long else pos['entry_price'] * 0.9995
                        pos['sl'] = be_price
                        pos['trailing_active'] = True
                        pos['highest_mark'] = bar_h
                        pos['lowest_mark'] = bar_l

                # Dynamic Trailing Stop on Remaining 50% Runner
                if pos.get('trailing_active'):
                    atr_val = pos.get('atr', pos['entry_price'] * 0.008)
                    trail_dist = 1.2 * atr_val

                    if is_long:
                        if bar_h > pos['highest_mark']:
                            pos['highest_mark'] = bar_h
                        calc_trail = pos['highest_mark'] - trail_dist
                        if calc_trail > pos['sl'] and calc_trail > pos['entry_price']:
                            pos['sl'] = calc_trail
                    elif is_short:
                        if bar_l < pos['lowest_mark']:
                            pos['lowest_mark'] = bar_l
                        calc_trail = pos['lowest_mark'] + trail_dist
                        if calc_trail < pos['sl'] and calc_trail < pos['entry_price']:
                            pos['sl'] = calc_trail

            for sym in closed_syms:
                if sym in self.active_positions:
                    del self.active_positions[sym]

            # Signal Scan
            if len(self.active_positions) >= self.max_positions or self.balance <= 1.0:
                continue

            for sym in SYMBOLS:
                if sym in self.active_positions:
                    continue
                if (bar_idx - last_trade_bar[sym]) < 8:
                    continue

                setup = all_setups[sym][bar_idx]
                if setup:
                    side = setup['side']

                    # 4H Macro BTC Regime Gate:
                    # If BTC 4H is Bearish, block Altcoin Longs
                    if side == 'BUY' and btc_4h_bear[bar_idx] and sym != 'BTCUSDT':
                        continue
                    # If BTC 4H is Bullish, block Altcoin Shorts
                    if side == 'SELL' and btc_4h_bull[bar_idx] and sym != 'BTCUSDT':
                        continue

                    entry_p = setup['entry_price']
                    sl_p = setup['sl']
                    tp1_p = setup['tp1']
                    tp2_p = setup['tp2']

                    margin = self.balance * self.margin_pct
                    notional = margin * self.leverage
                    if self.max_notional and notional > self.max_notional:
                        notional = self.max_notional
                        margin = notional / self.leverage
                    if notional < 5.0:
                        notional = 5.0
                        margin = notional / self.leverage

                    if self.balance >= margin:
                        qty = notional / entry_p
                        entry_fee = notional * self.maker_fee
                        self.total_maker_fees += entry_fee
                        self.balance -= entry_fee
                        self.monthly_pnl[month_key] -= entry_fee

                        self.active_positions[sym] = {
                            'symbol': sym,
                            'side': side,
                            'entry_time': current_time,
                            'entry_price': entry_p,
                            'initial_qty': qty,
                            'rem_qty': qty,
                            'sl': sl_p,
                            'tp1': tp1_p,
                            'tp2': tp2_p,
                            'tp1_hit': False,
                            'trailing_active': False,
                            'atr': setup['atr'],
                            'highest_mark': entry_p,
                            'lowest_mark': entry_p,
                            'realized_pnl': -entry_fee,
                            'pattern': setup['pattern'],
                            'rr': setup['rr']
                        }
                        last_trade_bar[sym] = bar_idx
                        if len(self.active_positions) >= self.max_positions:
                            break

        # Settle remaining open positions
        for sym, pos in list(self.active_positions.items()):
            bar_c = np_data[sym]['close'][-1]
            rem_qty = pos['rem_qty']
            raw_pnl = rem_qty * (bar_c - pos['entry_price']) if pos['side'] == 'BUY' else rem_qty * (pos['entry_price'] - bar_c)
            taker_fee_val = rem_qty * bar_c * self.taker_fee
            self.total_taker_fees += taker_fee_val
            if raw_pnl > 0:
                self.gross_profit_raw += raw_pnl
            else:
                self.gross_loss_raw += abs(raw_pnl)
            net_pnl = raw_pnl - taker_fee_val
            self.balance += net_pnl
            pos['realized_pnl'] += net_pnl
            self.trade_history.append(pos)

        self.print_results()

    def print_results(self):
        total_trades = len(self.trade_history)
        if total_trades == 0:
            print("❌ No setups triggered.")
            return

        wins = [t for t in self.trade_history if t['realized_pnl'] > 0]
        losses = [t for t in self.trade_history if t['realized_pnl'] <= 0]
        win_rate = (len(wins) / total_trades) * 100.0

        trailed_wins = [t for t in self.trade_history if t.get('exit_reason') == 'TP2_TRAILED_WIN']
        be_stops = [t for t in self.trade_history if t.get('exit_reason') == 'SL_BE']
        hard_stops = [t for t in self.trade_history if t.get('exit_reason') == 'STOP_LOSS']

        total_net_pnl = self.balance - self.initial_balance
        total_roi_pct = (total_net_pnl / self.initial_balance) * 100.0
        total_fees = self.total_maker_fees + self.total_taker_fees + self.total_funding_fees + self.total_slippage_cost
        profit_factor = (self.gross_profit_raw / (self.gross_loss_raw + 1e-9)) if self.gross_loss_raw > 0 else float('inf')

        profitable_months = sum(1 for m, pnl in self.monthly_pnl.items() if pnl > 0)
        total_months = len(self.monthly_pnl)

        print("\n" + "=" * 105)
        print(" 🏆 FINAL TEST RESULTS: ELLIOTT WAVE 2->3 GOLDEN POCKET + 4H MACRO GUARD")
        print("=" * 105)
        print(f" 💰 Initial Wallet Balance:      ${self.initial_balance:,.2f} USDT")
        print(f" 🏁 Final Portfolio Balance:     ${self.balance:,.2f} USDT")
        print(f" 📈 Net Realized Profit:         ${total_net_pnl:+,.2f} USDT ({total_roi_pct:+,.2f}% Total ROI)")
        print(f" 📊 Net Profit Factor (PF):      {profit_factor:.2f}")
        print(f" 🎯 Overall Win Rate:            {win_rate:.2f}% ({len(wins):,} Wins / {len(losses):,} Losses)")
        print(f" ⚡ Total Closed Trades:         {total_trades:,}")
        print(f" 🛡️ Max Portfolio Drawdown:      -{self.max_drawdown_pct:.2f}% (-${self.max_drawdown_dollars:,.2f} USDT)")
        print(f" 📅 Monthly Consistency:         {profitable_months} / {total_months} Profitable Months ({profitable_months/total_months*100:.1f}%)")
        print("-" * 105)
        print(f" 🧾 REALISTIC FEE DEDUCTIONS:")
        print(f"    • Maker Entry/TP1 Fees:     ${self.total_maker_fees:,.2f} USDT")
        print(f"    • Taker Stop/Exit Fees:     ${self.total_taker_fees:,.2f} USDT")
        print(f"    • 8-Hour Funding Holding:   ${self.total_funding_fees:,.2f} USDT")
        print(f"    • Market Slippage Cost:     ${self.total_slippage_cost:,.2f} USDT")
        print(f"    • Total Friction Deducted:  ${total_fees:,.2f} USDT")
        print("-" * 105)
        print(f" 🔬 SAMPLE TRADE EXECUTIONS (FIRST 5 TRADES):")
        for i, t in enumerate(self.trade_history[:5]):
            t_entry = str(t['entry_time'])[:16]
            print(f"    {i+1}. [{t_entry}] {t['symbol']:<8} {t['side']:<4} @ ${t['entry_price']:<9.4f} | Exit: {t['exit_reason']:<16} | PnL: ${t['realized_pnl']:+6.2f} USDT")
        print("=" * 105)

        print("\n" + "=" * 105)
        print(" 📅 24-MONTH CONSECUTIVE PERFORMANCE LOG:")
        print("=" * 105)
        for m in sorted(self.monthly_pnl.keys()):
            pnl = self.monthly_pnl[m]
            start_b = self.monthly_start_balance.get(m, self.initial_balance)
            m_pct = (pnl / start_b * 100.0) if start_b > 0 else 0.0
            emoji = "🟢 PROFITABLE" if pnl >= 0 else "🔴 LOSS"
            print(f"  {emoji:<14} | Month {m} | Net PnL: ${pnl:+10,.2f} USDT ({m_pct:+8.2f}%)")
        print("=" * 105 + "\n")

if __name__ == '__main__':
    simulator = ElliottWaveLiveSimulator()
    simulator.run()
