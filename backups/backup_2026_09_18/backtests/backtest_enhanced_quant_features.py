#!/usr/bin/env python3
"""
================================================================================
🔬 QUANT LAB BACKTEST: BENCHMARKING PROPOSED ENHANCEMENTS (AUG 2024 – AUG 2026)
================================================================================
Compares 4 Strategy Configurations on $17.64 Live Starting Balance:
1. Baseline: Current Fixed 3% Margin Sizing + 15m Filter
2. Feature 1: ATR-Targeted Dynamic Sizing (1R Equalized Risk per Asset)
3. Feature 2: 4H Macro BTC Filter (Restricts Alt Longs when BTC 4H is Bearish)
4. Combined Suite: ATR Sizing + 4H Macro BTC Filter + Exchange-Grade Trailing

DOES NOT MODIFY main.py. Purely an isolated backtesting lab.
================================================================================
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historical_data_cache")

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'SUIUSDT', 'NEARUSDT',
    'AVAXUSDT', 'LINKUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT'
]

FEE_TIERS = {
    'vip0_bnb': {
        'maker': 0.00018,     # 0.018% Maker
        'taker': 0.00045,     # 0.045% Taker
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

def precompute_setups(df, window=5):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    n = len(closes)

    ema20 = calc_ema_arr(closes, 20)
    ema50 = calc_ema_arr(closes, 50)
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
    last_h_idx = -1
    last_l_idx = -1
    prev_h_idx = -1
    prev_l_idx = -1

    for i in range(50, n):
        if pivots_h[i - window]:
            prev_h_idx = last_h_idx
            last_h_idx = i - window
        if pivots_l[i - window]:
            prev_l_idx = last_l_idx
            last_l_idx = i - window

        if last_h_idx > 0 and last_l_idx > 0 and prev_l_idx > 0 and prev_h_idx > 0:
            c = closes[i]
            # Bullish Golden Pocket Setup
            if last_h_idx > prev_l_idx and last_h_idx > last_l_idx:
                w1_h = highs[last_h_idx] - lows[prev_l_idx]
                if w1_h > 0:
                    retrace = (highs[last_h_idx] - c) / w1_h
                    if 0.48 <= retrace <= 0.65 and c > lows[prev_l_idx]:
                        if c > ema50[i] and rsi[i] >= 46:
                            sl = lows[prev_l_idx] * 0.998
                            tp1 = c + (highs[last_h_idx] - c) * 0.90
                            tp2 = lows[last_l_idx] + (w1_h * 1.618)
                            risk = c - sl
                            reward = tp2 - c
                            if risk > 0 and reward / risk >= 1.80:
                                setups[i] = {
                                    'side': 'BUY',
                                    'entry_price': c,
                                    'sl': sl,
                                    'tp1': tp1,
                                    'tp2': tp2,
                                    'atr': atr[i],
                                    'rr': reward / risk
                                }

            # Bearish Golden Pocket Setup
            elif last_l_idx > prev_h_idx and last_l_idx > last_h_idx:
                w1_h = highs[prev_h_idx] - lows[last_l_idx]
                if w1_h > 0:
                    bounce = (c - lows[last_l_idx]) / w1_h
                    if 0.48 <= bounce <= 0.65 and c < highs[prev_h_idx]:
                        if c < ema50[i] and rsi[i] <= 54:
                            sl = highs[prev_h_idx] * 1.002
                            tp1 = c - (c - lows[last_l_idx]) * 0.90
                            tp2 = highs[last_h_idx] - (w1_h * 1.618)
                            risk = sl - c
                            reward = c - tp2
                            if risk > 0 and reward / risk >= 1.80:
                                setups[i] = {
                                    'side': 'SELL',
                                    'entry_price': c,
                                    'sl': sl,
                                    'tp1': tp1,
                                    'tp2': tp2,
                                    'atr': atr[i],
                                    'rr': reward / risk
                                }

    return setups

def run_strategy_backtest(raw_data, all_setups, np_data, btc_4h_bull, btc_4h_bear,
                          use_atr_sizing=False, use_4h_btc_filter=False,
                          initial_balance=17.64, leverage=50, max_positions=5,
                          margin_pct=0.03, max_notional=5000.0):
    fees = FEE_TIERS['vip0_bnb']
    maker_fee = fees['maker']
    taker_fee = fees['taker']
    slippage = fees['slippage']
    funding_rate_8h = fees['funding_8h']

    balance = float(initial_balance)
    active_positions = {}
    trade_history = []

    total_maker_fees = 0.0
    total_taker_fees = 0.0
    total_funding_fees = 0.0
    total_slippage_cost = 0.0
    gross_profit_raw = 0.0
    gross_loss_raw = 0.0

    monthly_pnl = {}
    monthly_start_balance = {}
    peak_equity = float(initial_balance)
    max_drawdown_dollars = 0.0
    max_drawdown_pct = 0.0

    min_len = min(len(df) for df in raw_data.values())
    last_funding_bar = 0
    last_trade_bar = {sym: -100 for sym in SYMBOLS}

    for bar_idx in range(60, min_len):
        current_time = pd.to_datetime(np_data['BTCUSDT']['open_time'][bar_idx])
        month_key = current_time.strftime('%Y-%m')

        if month_key not in monthly_pnl:
            monthly_pnl[month_key] = 0.0
            monthly_start_balance[month_key] = balance

        # Track Drawdowns
        if balance > peak_equity:
            peak_equity = balance
        current_dd_dollars = peak_equity - balance
        current_dd_pct = (current_dd_dollars / peak_equity) * 100 if peak_equity > 0 else 0.0
        if current_dd_dollars > max_drawdown_dollars:
            max_drawdown_dollars = current_dd_dollars
        if current_dd_pct > max_drawdown_pct:
            max_drawdown_pct = current_dd_pct

        # 8-Hour Funding Fee
        if (bar_idx - last_funding_bar) >= 32:
            last_funding_bar = bar_idx
            for sym, pos in active_positions.items():
                bar_c = np_data[sym]['close'][bar_idx]
                pos_val = pos['rem_qty'] * bar_c
                funding_cost = pos_val * funding_rate_8h
                total_funding_fees += funding_cost
                balance -= funding_cost
                monthly_pnl[month_key] -= funding_cost

        # Position Management
        closed_syms = []
        for sym, pos in list(active_positions.items()):
            bar_h = np_data[sym]['high'][bar_idx]
            bar_l = np_data[sym]['low'][bar_idx]
            bar_c = np_data[sym]['close'][bar_idx]
            is_long = pos['side'] == 'BUY'
            is_short = pos['side'] == 'SELL'

            # Stop Loss Check
            hit_sl = False
            sl_exit_price = pos['sl']
            if is_long and bar_l <= pos['sl']:
                hit_sl = True
                sl_exit_price = min(bar_c, pos['sl']) * (1.0 - slippage)
            elif is_short and bar_h >= pos['sl']:
                hit_sl = True
                sl_exit_price = max(bar_c, pos['sl']) * (1.0 + slippage)

            if hit_sl:
                rem_qty = pos['rem_qty']
                raw_pnl = rem_qty * (sl_exit_price - pos['entry_price']) if is_long else rem_qty * (pos['entry_price'] - sl_exit_price)
                taker_fee_val = rem_qty * sl_exit_price * taker_fee
                slip_cost = rem_qty * sl_exit_price * slippage

                total_taker_fees += taker_fee_val
                total_slippage_cost += slip_cost
                if raw_pnl > 0:
                    gross_profit_raw += raw_pnl
                else:
                    gross_loss_raw += abs(raw_pnl)

                net_pnl = raw_pnl - taker_fee_val
                balance += net_pnl
                monthly_pnl[month_key] += net_pnl

                pos['realized_pnl'] += net_pnl
                pos['exit_time'] = current_time
                pos['exit_reason'] = 'TP2_TRAILED_WIN' if pos.get('trailing_active') else ('SL_BE' if pos['tp1_hit'] else 'STOP_LOSS')
                trade_history.append(pos)
                closed_syms.append(sym)
                continue

            # TP1 Scale-Out (50% @ 1.00x extension -> Breakeven)
            if not pos['tp1_hit']:
                tp1_hit = (is_long and bar_h >= pos['tp1']) or (is_short and bar_l <= pos['tp1'])
                if tp1_hit:
                    pos['tp1_hit'] = True
                    close_qty = pos['initial_qty'] * 0.50
                    pos['rem_qty'] -= close_qty

                    tp_p = pos['tp1']
                    raw_pnl = close_qty * (tp_p - pos['entry_price']) if is_long else close_qty * (pos['entry_price'] - tp_p)
                    maker_fee_val = close_qty * tp_p * maker_fee

                    total_maker_fees += maker_fee_val
                    gross_profit_raw += raw_pnl

                    net_pnl = raw_pnl - maker_fee_val
                    balance += net_pnl
                    monthly_pnl[month_key] += net_pnl
                    pos['realized_pnl'] += net_pnl

                    be_price = pos['entry_price'] * 1.0005 if is_long else pos['entry_price'] * 0.9995
                    pos['sl'] = be_price
                    pos['trailing_active'] = True
                    pos['highest_mark'] = bar_h
                    pos['lowest_mark'] = bar_l

            # Trailing Stop
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
            if sym in active_positions:
                del active_positions[sym]

        # Scan for New Setups
        if len(active_positions) >= max_positions or balance <= 1.0:
            continue

        for sym in SYMBOLS:
            if sym in active_positions:
                continue
            if (bar_idx - last_trade_bar[sym]) < 8:
                continue

            setup = all_setups[sym][bar_idx]
            if setup:
                side = setup['side']
                
                # 4H Macro BTC Filter Check
                if use_4h_btc_filter:
                    # If BTC 4H is Bearish, block Altcoin Longs (permit only Shorts or BTC Long)
                    if side == 'BUY' and btc_4h_bear[bar_idx] and sym != 'BTCUSDT':
                        continue
                    # If BTC 4H is Bullish, block Altcoin Shorts
                    if side == 'SELL' and btc_4h_bull[bar_idx] and sym != 'BTCUSDT':
                        continue

                entry_p = setup['entry_price']
                sl_p = setup['sl']
                tp1_p = setup['tp1']
                tp2_p = setup['tp2']

                # Sizing Calculation: ATR-Targeted vs Fixed Margin Sizing
                if use_atr_sizing:
                    # Risk exactly 1.5% of portfolio per trade
                    target_dollar_risk = balance * 0.015
                    stop_dist_pct = abs(entry_p - sl_p) / entry_p
                    if stop_dist_pct < 0.005:
                        stop_dist_pct = 0.005 # Guard against micro stops
                    
                    notional = target_dollar_risk / stop_dist_pct
                    margin = notional / leverage
                else:
                    margin = balance * margin_pct
                    notional = margin * leverage

                # Bounds checking
                if max_notional and notional > max_notional:
                    notional = max_notional
                    margin = notional / leverage
                if notional < 5.0:
                    notional = 5.0
                    margin = notional / leverage

                if balance >= margin:
                    qty = notional / entry_p
                    entry_fee = notional * maker_fee
                    total_maker_fees += entry_fee
                    balance -= entry_fee
                    monthly_pnl[month_key] -= entry_fee

                    active_positions[sym] = {
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
                        'rr': setup['rr']
                    }
                    last_trade_bar[sym] = bar_idx
                    if len(active_positions) >= max_positions:
                        break

    # Settle remaining
    for sym, pos in list(active_positions.items()):
        bar_c = np_data[sym]['close'][-1]
        rem_qty = pos['rem_qty']
        raw_pnl = rem_qty * (bar_c - pos['entry_price']) if pos['side'] == 'BUY' else rem_qty * (pos['entry_price'] - bar_c)
        taker_fee_val = rem_qty * bar_c * taker_fee
        total_taker_fees += taker_fee_val
        if raw_pnl > 0:
            gross_profit_raw += raw_pnl
        else:
            gross_loss_raw += abs(raw_pnl)
        net_pnl = raw_pnl - taker_fee_val
        balance += net_pnl
        pos['realized_pnl'] += net_pnl
        trade_history.append(pos)

    total_trades = len(trade_history)
    wins = [t for t in trade_history if t['realized_pnl'] > 0]
    losses = [t for t in trade_history if t['realized_pnl'] <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (gross_profit_raw / (gross_loss_raw + 1e-9)) if gross_loss_raw > 0 else float('inf')
    net_pnl = balance - initial_balance
    roi_pct = (net_pnl / initial_balance * 100.0)
    profitable_months = sum(1 for m, pnl in monthly_pnl.items() if pnl > 0)
    total_months = len(monthly_pnl)

    return {
        'final_balance': balance,
        'net_pnl': net_pnl,
        'roi_pct': roi_pct,
        'profit_factor': profit_factor,
        'win_rate': win_rate,
        'total_trades': total_trades,
        'wins': len(wins),
        'losses': len(losses),
        'max_dd_pct': max_drawdown_pct,
        'max_dd_dollars': max_drawdown_dollars,
        'green_months': profitable_months,
        'total_months': total_months,
        'monthly_pnl': monthly_pnl
    }

def main_benchmark():
    print("=" * 105)
    print(" 🔬 QUANT LAB BENCHMARK: TESTING PROPOSED IMPROVEMENTS (2-YEAR AUDIT / 700,810 CANDLES)")
    print("=" * 105)
    print(" • Starting Balance:  $17.64 USDT (Live Account Starting Capital)")
    print(" • Leverage:          50x Isolated")
    print(" • Max Positions:     5 Concurrent Slots")
    print(" • Position Cap:      $5,000.00 USDT Max Cap per Position")
    print(" • Fee Schedule:      Binance VIP0+BNB (Maker 0.018% / Taker 0.045% / Funding / Slippage)")
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

    print("⚡ Precomputing signal matrix across universe...", flush=True)
    all_setups = {}
    for sym, df in raw_data.items():
        all_setups[sym] = precompute_setups(df, window=5)

    # Precompute BTC 4H Macro Regime (4H = 16 bars of 15m)
    btc_closes = np_data['BTCUSDT']['close']
    btc_4h_ema50 = calc_ema_arr(btc_closes, 50 * 16) # 50-period 4H EMA mapped to 15m bars
    btc_4h_bull = btc_closes > btc_4h_ema50
    btc_4h_bear = btc_closes < btc_4h_ema50

    # -------------------------------------------------------------
    # RUN 4 TEST CONFIGURATIONS
    # -------------------------------------------------------------
    configs = [
        ('1. Baseline (Current Fixed 3% Sizing + 15m Filter)', False, False),
        ('2. Feature 1: ATR-Targeted Dynamic Risk Sizing', True, False),
        ('3. Feature 2: Enhanced 4H Macro BTC Filter', False, True),
        ('4. Combined Suite: ATR Sizing + 4H Macro BTC Filter', True, True)
    ]

    results = []
    for label, use_atr, use_4h in configs:
        print(f"🚀 Running Simulation: {label}...", flush=True)
        res = run_strategy_backtest(
            raw_data, all_setups, np_data, btc_4h_bull, btc_4h_bear,
            use_atr_sizing=use_atr, use_4h_btc_filter=use_4h
        )
        res['label'] = label
        results.append(res)

    print("\n" + "=" * 115)
    print(" 📊 COMPARATIVE PERFORMANCE MATRIX (2-YEAR HISTORICAL AUDIT):")
    print("=" * 115)
    header = f"{'Configuration / Strategy':<52} | {'Final Balance':<15} | {'Net Return':<12} | {'Win Rate':<10} | {'Profit Factor':<14} | {'Max DD (%)':<10}"
    print(header)
    print("-" * 115)
    for r in results:
        b_str = f"${r['final_balance']:,.2f}"
        ret_str = f"{r['roi_pct']:+,.1f}%"
        wr_str = f"{r['win_rate']:.2f}%"
        pf_str = f"{r['profit_factor']:.2f}"
        dd_str = f"-{r['max_dd_pct']:.2f}%"
        print(f"{r['label']:<52} | {b_str:>15} | {ret_str:>12} | {wr_str:>10} | {pf_str:>14} | {dd_str:>10}")
    print("=" * 115)

if __name__ == '__main__':
    main_benchmark()
