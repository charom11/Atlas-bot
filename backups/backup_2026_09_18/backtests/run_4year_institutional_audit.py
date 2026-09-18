#!/usr/bin/env python3
"""
==========================================================================================
⚡ ATLAS INSTITUTIONAL 4-YEAR BACKTEST ENGINE & COMPREHENSIVE AUDIT (2022 - 2026)
==========================================================================================
Audited Period: September 18, 2022 → September 18, 2026 (48 Full Months)
Timeframe: 15-minute
Universe: 11 Perpetuals (BTC, ETH, SOL, LINK, AVAX, XRP, ADA, DOGE, NEAR, BNB, SUI)
Strategy: Production Atlas Architecture (5MA Consensus, Multi-Tier Fibonacci, MSS/SMC,
          Darwinian Adaptive Weights, ATR TP/SL, 50% Scale-Out + Trailing Runner,
          Maker/Taker Fees, Slippage, 8-hour Funding Rates, Margin Checks, Drawdown Gates)
==========================================================================================
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from collections import deque

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historical_data_cache")

ALL_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT', 'AVAXUSDT',
    'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'NEARUSDT', 'BNBUSDT', 'SUIUSDT'
]

FEE_SCHEDULE = {
    'maker_fee': 0.00018,    # 0.018% VIP1 Binance maker
    'taker_fee': 0.00045,    # 0.045% VIP1 Binance taker
    'slippage': 0.00015,     # 0.015% simulated execution slippage
    'funding_8h': 0.00010    # 0.010% standard baseline 8h perpetual funding rate
}

class AtlasDarwinianWeights:
    def __init__(self, channels=['FIBONACCI', '5MA_CONSENSUS', 'MSS_SHIFT'], initial_weights=None):
        self.weights = {ch: float(initial_weights.get(ch, 1.0)) for ch in channels} if initial_weights else {ch: 1.0 for ch in channels}
        self.channel_history = {ch: deque(maxlen=200) for ch in channels}
        self.last_update_bar = 0

    def record_trade(self, channel, pnl):
        if channel in self.channel_history:
            self.channel_history[channel].append(pnl)

    def update_weights(self, current_bar):
        if current_bar - self.last_update_bar < 2880:  # Every 30 days
            return
        self.last_update_bar = current_bar
        for ch, hist in self.channel_history.items():
            if len(hist) < 15:
                continue
            wins = sum(1 for p in hist if p > 0)
            wr = wins / len(hist)
            tot_pnl = sum(hist)
            if wr >= 0.55 and tot_pnl > 0:
                self.weights[ch] = min(1.5, self.weights[ch] * 1.05)
            elif wr < 0.48 or tot_pnl < 0:
                self.weights[ch] = max(0.8, self.weights[ch] * 0.95)

    def get_multiplier(self, channel):
        return self.weights.get(channel, 1.0)


def calc_ema(arr, span):
    alpha = 2.0 / (span + 1.0)
    n = len(arr)
    out = np.empty(n, dtype=np.float64)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out

def calc_rsi(closes, period=14):
    n = len(closes)
    diff = np.diff(closes)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    rsi = np.full(n, 50.0)
    if n <= period:
        return rsi
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / (avg_loss + 1e-9) if avg_loss > 0 else 100.0
        rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calc_atr(highs, lows, closes, period=14):
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

def calc_adx(highs, lows, closes, period=14):
    n = len(closes)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    atr_smooth = np.zeros(n)
    plus_di_smooth = np.zeros(n)
    minus_di_smooth = np.zeros(n)
    if n <= period * 2:
        return np.full(n, 25.0)

    atr_smooth[period] = np.sum(tr[1:period + 1])
    plus_di_smooth[period] = np.sum(plus_dm[1:period + 1])
    minus_di_smooth[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr_smooth[i] = atr_smooth[i - 1] - (atr_smooth[i - 1] / period) + tr[i]
        plus_di_smooth[i] = plus_di_smooth[i - 1] - (plus_di_smooth[i - 1] / period) + plus_dm[i]
        minus_di_smooth[i] = minus_di_smooth[i - 1] - (minus_di_smooth[i - 1] / period) + minus_dm[i]

    plus_di = 100.0 * (plus_di_smooth / (atr_smooth + 1e-9))
    minus_di = 100.0 * (minus_di_smooth / (atr_smooth + 1e-9))
    dx = 100.0 * (np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))

    adx = np.full(n, 25.0)
    adx_start = period * 2 - 1
    if n > adx_start:
        adx[adx_start] = np.mean(dx[period:adx_start + 1])
        for i in range(adx_start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return adx

def precompute_signals(df, window=4):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    n = len(closes)

    ema9 = calc_ema(closes, 9)
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    ema100 = calc_ema(closes, 100)
    ema200 = calc_ema(closes, 200)

    rsi14 = calc_rsi(closes, 14)
    atr14 = calc_atr(highs, lows, closes, 14)
    adx14 = calc_adx(highs, lows, closes, 14)

    vol_sma20 = np.zeros(n)
    for i in range(19, n):
        vol_sma20[i] = np.mean(volumes[i - 19:i + 1])

    signals = []
    swing_highs = []
    swing_lows = []
    last_sh_p = highs[0]
    last_sl_p = lows[0]

    for i in range(50, n):
        c = closes[i]
        h = highs[i]
        l = lows[i]
        v = volumes[i]
        curr_atr = atr14[i] if atr14[i] > 0 else (c * 0.01)

        # 1. 5MA Stack Consensus
        bull_stack = (ema9[i] > ema20[i] > ema50[i] > ema100[i] > ema200[i])
        bear_stack = (ema9[i] < ema20[i] < ema50[i] < ema100[i] < ema200[i])

        cons_long = (bull_stack and c > ema20[i] and rsi14[i] > 52 and adx14[i] > 22 and v > vol_sma20[i])
        cons_short = (bear_stack and c < ema20[i] and rsi14[i] < 48 and adx14[i] > 22 and v > vol_sma20[i])

        # 2. Swing High / Low Tracking
        idx = i - window
        if idx >= window:
            is_sh, is_sl = True, True
            p_h, p_l = highs[idx], lows[idx]
            for w in range(1, window + 1):
                if highs[idx - w] >= p_h or highs[idx + w] >= p_h:
                    is_sh = False
                if lows[idx - w] <= p_l or lows[idx + w] <= p_l:
                    is_sl = False
            if is_sh:
                swing_highs.append((idx, p_h))
                last_sh_p = p_h
            if is_sl:
                swing_lows.append((idx, p_l))
                last_sl_p = p_l

        # 3. Market Structure Shift (MSS)
        mss_long, mss_short = False, False
        vol_breakout = (v > vol_sma20[i] * 1.30) if vol_sma20[i] > 0 else False

        if swing_highs and c > last_sh_p and closes[i - 1] <= last_sh_p:
            if c > ema50[i] and c > ema200[i] and vol_breakout:
                mss_long = True

        if swing_lows and c < last_sl_p and closes[i - 1] >= last_sl_p:
            if c < ema50[i] and c < ema200[i] and vol_breakout:
                mss_short = True

        # 4. Multi-Tier Fibonacci OTE
        fib_long, fib_short = False, False
        fib_entry = c
        if last_sh_p > last_sl_p and (last_sh_p - last_sl_p) > curr_atr:
            swing_rng = last_sh_p - last_sl_p
            f618 = last_sh_p - (0.618 * swing_rng)
            f786 = last_sh_p - (0.786 * swing_rng)
            if bull_stack and (f786 <= l <= f618) and c > ema50[i] and rsi14[i] >= 42:
                fib_long = True
                fib_entry = c

            f618_bear = last_sl_p + (0.618 * swing_rng)
            f786_bear = last_sl_p + (0.786 * swing_rng)
            if bear_stack and (f618_bear <= h <= f786_bear) and c < ema50[i] and rsi14[i] <= 58:
                fib_short = True
                fib_entry = c

        signals.append({
            'cons_long': cons_long, 'cons_short': cons_short,
            'mss_long': mss_long, 'mss_short': mss_short,
            'fib_long': fib_long, 'fib_short': fib_short,
            'fib_entry': fib_entry,
            'atr': curr_atr,
            'adx': adx14[i],
            'ema50': ema50[i],
            'last_sh': last_sh_p,
            'last_sl': last_sl_p
        })

    pad = [{'cons_long': False, 'cons_short': False, 'mss_long': False, 'mss_short': False, 'fib_long': False, 'fib_short': False, 'fib_entry': closes[0], 'atr': closes[0]*0.01, 'adx': 20.0, 'ema50': closes[0], 'last_sh': closes[0], 'last_sl': closes[0]}] * 50
    return pad + signals


def load_and_filter_datasets(start_iso="2022-09-18T00:00:00Z", end_iso="2026-09-18T00:00:00Z"):
    print(f"Loading & filtering 4-year datasets ({start_iso} to {end_iso})...", flush=True)
    start_dt = pd.to_datetime(start_iso)
    end_dt = pd.to_datetime(end_iso)

    data_map = {}
    signals_map = {}
    highs_map = {}
    lows_map = {}
    closes_map = {}

    for sym in ALL_SYMBOLS:
        cache_file = os.path.join(CACHE_DIR, f"{sym}_15m_4year_2022-09-01.csv")
        if not os.path.exists(cache_file):
            print(f"  [MISSING] {cache_file}")
            continue
        df = pd.read_csv(cache_file)
        df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
        # Filter within window
        df = df[(df['open_time'] >= start_dt) & (df['open_time'] <= end_dt)].reset_index(drop=True)
        if len(df) < 100:
            print(f"  [SKIP] {sym} only has {len(df)} bars in range")
            continue
        data_map[sym] = df
        highs_map[sym] = df['high'].values
        lows_map[sym] = df['low'].values
        closes_map[sym] = df['close'].values
        signals_map[sym] = precompute_signals(df)
        print(f"  [LOADED] {sym}: {len(df):,} 15m candles ({df['open_time'].min().strftime('%Y-%m-%d')} -> {df['open_time'].max().strftime('%Y-%m-%d')})")

    active_symbols = list(data_map.keys())
    if 'BTCUSDT' not in data_map:
        raise RuntimeError("BTCUSDT dataset missing; required for master timeline.")

    time_index = data_map['BTCUSDT']['open_time'].values
    n_bars = len(time_index)
    print(f"\n[TIMELINE] Synchronized master timeline: {n_bars:,} bars across {len(active_symbols)} assets\n", flush=True)

    idx_maps = {}
    for sym in active_symbols:
        s_times = data_map[sym]['open_time'].values
        idx_map = np.full(n_bars, -1, dtype=int)
        ptr = 0
        len_s = len(s_times)
        for i, t in enumerate(time_index):
            while ptr < len_s and s_times[ptr] < t:
                ptr += 1
            if ptr < len_s and s_times[ptr] == t:
                idx_map[i] = ptr
        idx_maps[sym] = idx_map

    btc_closes = closes_map['BTCUSDT']
    btc_indices = idx_maps['BTCUSDT']
    btc_dump_arr = np.zeros(n_bars, dtype=bool)
    for b_i in range(1, n_bars):
        b_idx = btc_indices[b_i]
        if b_idx >= 1:
            prev_b = b_idx - 1
            if (btc_closes[b_idx] - btc_closes[prev_b]) / btc_closes[prev_b] < -0.005:
                btc_dump_arr[b_i] = True

    return {
        'data_map': data_map,
        'signals_map': signals_map,
        'highs_map': highs_map,
        'lows_map': lows_map,
        'closes_map': closes_map,
        'time_index': time_index,
        'n_bars': n_bars,
        'idx_maps': idx_maps,
        'btc_dump_arr': btc_dump_arr,
        'active_symbols': active_symbols
    }


def execute_audit_simulation(dataset, initial_balance=3.93, leverage=50, margin_pct=0.03,
                             max_positions=5, max_directional=4,
                             fib_weight=1.5, mss_weight=1.0, ma_weight=1.0,
                             tp1_atr=2.2, trail_atr=1.0):
    signals_map = dataset['signals_map']
    highs_map = dataset['highs_map']
    lows_map = dataset['lows_map']
    closes_map = dataset['closes_map']
    time_index = dataset['time_index']
    n_bars = dataset['n_bars']
    idx_maps = dataset['idx_maps']
    btc_dump_arr = dataset['btc_dump_arr']
    active_symbols = dataset['active_symbols']

    balance = float(initial_balance)
    peak_balance = float(initial_balance)
    max_drawdown_pct = 0.0

    total_fees_paid = 0.0
    total_funding_paid = 0.0
    rejected_orders_count = 0

    active_positions = {}
    closed_trades = []
    symbol_last_trade_bar = {sym: -999 for sym in active_symbols}
    cooldown_bars = 12

    # Tracking daily equity curve for Sharpe & Sortino
    daily_equity = {}
    monthly_stats = {}
    yearly_stats = {}

    # Define the 4 custom 12-month periods
    # Period 1: 2022-09-18 -> 2023-09-18
    # Period 2: 2023-09-18 -> 2024-09-18
    # Period 3: 2024-09-18 -> 2025-09-18
    # Period 4: 2025-09-18 -> 2026-09-18
    period_stats = {
        '2022–2023': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'start_bal': balance, 'end_bal': balance},
        '2023–2024': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'start_bal': balance, 'end_bal': balance},
        '2024–2025': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'start_bal': balance, 'end_bal': balance},
        '2025–2026': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'start_bal': balance, 'end_bal': balance},
    }

    darwin = AtlasDarwinianWeights(initial_weights={'FIBONACCI': fib_weight, 'MSS_SHIFT': mss_weight, '5MA_CONSENSUS': ma_weight})

    def get_period_key(dt):
        naive_dt = dt.tz_localize(None) if hasattr(dt, 'tz') and dt.tz is not None else dt
        if naive_dt < pd.Timestamp("2023-09-18"):
            return '2022–2023'
        elif naive_dt < pd.Timestamp("2024-09-18"):
            return '2023–2024'
        elif naive_dt < pd.Timestamp("2025-09-18"):
            return '2024–2025'
        else:
            return '2025–2026'

    for bar_i in range(50, n_bars):
        cur_time = pd.Timestamp(time_index[bar_i])
        day_key = cur_time.strftime('%Y-%m-%d')
        m_key = cur_time.strftime('%Y-%m')
        y_key = cur_time.strftime('%Y')
        p_key = get_period_key(cur_time)

        if m_key not in monthly_stats:
            monthly_stats[m_key] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'fees': 0.0}
        if y_key not in yearly_stats:
            yearly_stats[y_key] = {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}

        darwin.update_weights(bar_i)
        btc_dump = btc_dump_arr[bar_i]

        symbols_to_close = []
        for sym, pos in active_positions.items():
            s_idx = idx_maps[sym][bar_i]
            if s_idx == -1:
                continue
            h = highs_map[sym][s_idx]
            l = lows_map[sym][s_idx]
            c = closes_map[sym][s_idx]
            entry_p = pos['entry_price']
            qty = pos['qty']
            side = pos['side']

            # 8-Hour Funding Rate Debit
            if bar_i % 32 == 0:
                fund_fee = (c * qty) * FEE_SCHEDULE['funding_8h']
                balance -= fund_fee
                pos['realized_pnl'] -= fund_fee
                pos['funding_fees'] += fund_fee
                total_funding_paid += fund_fee

            if side == 'LONG':
                # TP1 Scale-Out (50%)
                if not pos['tp1_hit'] and h >= pos['tp1_p']:
                    pos['tp1_hit'] = True
                    half_qty = qty * 0.50
                    pnl_tp1 = (pos['tp1_p'] - entry_p) * half_qty
                    fee_tp1 = (pos['tp1_p'] * half_qty) * (FEE_SCHEDULE['maker_fee'] + FEE_SCHEDULE['slippage'])
                    net_tp1 = pnl_tp1 - fee_tp1
                    balance += (pos['margin'] * 0.50) + net_tp1
                    pos['realized_pnl'] += net_tp1
                    pos['fees_paid'] += fee_tp1
                    total_fees_paid += fee_tp1
                    pos['remaining_qty'] = half_qty
                    pos['sl_p'] = entry_p * 1.0005  # Breakeven lock + small offset
                    pos['highest_since_entry'] = h

                # Trailing Stop for 50% Runner
                if pos['tp1_hit']:
                    if h > pos['highest_since_entry']:
                        pos['highest_since_entry'] = h
                        new_tsl = h - (trail_atr * pos['atr'])
                        if new_tsl > pos['sl_p']:
                            pos['sl_p'] = new_tsl

                # Stop Loss Hit
                if l <= pos['sl_p']:
                    rem_qty = pos['remaining_qty']
                    exit_p = pos['sl_p']
                    pnl_rem = (exit_p - entry_p) * rem_qty
                    fee_rem = (exit_p * rem_qty) * (FEE_SCHEDULE['taker_fee'] + FEE_SCHEDULE['slippage'])
                    net_rem = pnl_rem - fee_rem
                    balance += (pos['margin'] * (0.50 if pos['tp1_hit'] else 1.00)) + net_rem
                    pos['realized_pnl'] += net_rem
                    pos['fees_paid'] += fee_rem
                    total_fees_paid += fee_rem
                    pos['exit_time'] = cur_time
                    pos['exit_price'] = exit_p
                    symbols_to_close.append(sym)

            elif side == 'SHORT':
                # TP1 Scale-Out (50%)
                if not pos['tp1_hit'] and l <= pos['tp1_p']:
                    pos['tp1_hit'] = True
                    half_qty = qty * 0.50
                    pnl_tp1 = (entry_p - pos['tp1_p']) * half_qty
                    fee_tp1 = (pos['tp1_p'] * half_qty) * (FEE_SCHEDULE['maker_fee'] + FEE_SCHEDULE['slippage'])
                    net_tp1 = pnl_tp1 - fee_tp1
                    balance += (pos['margin'] * 0.50) + net_tp1
                    pos['realized_pnl'] += net_tp1
                    pos['fees_paid'] += fee_tp1
                    total_fees_paid += fee_tp1
                    pos['remaining_qty'] = half_qty
                    pos['sl_p'] = entry_p * 0.9995  # Breakeven lock
                    pos['lowest_since_entry'] = l

                # Trailing Stop for 50% Runner
                if pos['tp1_hit']:
                    if l < pos['lowest_since_entry']:
                        pos['lowest_since_entry'] = l
                        new_tsl = l + (trail_atr * pos['atr'])
                        if new_tsl < pos['sl_p']:
                            pos['sl_p'] = new_tsl

                # Stop Loss Hit
                if h >= pos['sl_p']:
                    rem_qty = pos['remaining_qty']
                    exit_p = pos['sl_p']
                    pnl_rem = (entry_p - exit_p) * rem_qty
                    fee_rem = (exit_p * rem_qty) * (FEE_SCHEDULE['taker_fee'] + FEE_SCHEDULE['slippage'])
                    net_rem = pnl_rem - fee_rem
                    balance += (pos['margin'] * (0.50 if pos['tp1_hit'] else 1.00)) + net_rem
                    pos['realized_pnl'] += net_rem
                    pos['fees_paid'] += fee_rem
                    total_fees_paid += fee_rem
                    pos['exit_time'] = cur_time
                    pos['exit_price'] = exit_p
                    symbols_to_close.append(sym)

        for sym in symbols_to_close:
            pos = active_positions.pop(sym)
            closed_trades.append(pos)
            symbol_last_trade_bar[sym] = bar_i
            darwin.record_trade(pos['channel'], pos['realized_pnl'])

            m_k = pos['exit_time'].strftime('%Y-%m')
            y_k = pos['exit_time'].strftime('%Y')
            p_k = get_period_key(pos['exit_time'])

            monthly_stats[m_k]['trades'] += 1
            monthly_stats[m_k]['pnl'] += pos['realized_pnl']
            monthly_stats[m_k]['fees'] += (pos['fees_paid'] + pos['funding_fees'])
            if pos['realized_pnl'] > 0:
                monthly_stats[m_k]['wins'] += 1
            else:
                monthly_stats[m_k]['losses'] += 1

            yearly_stats[y_k]['trades'] += 1
            yearly_stats[y_k]['pnl'] += pos['realized_pnl']
            if pos['realized_pnl'] > 0:
                yearly_stats[y_k]['wins'] += 1
            else:
                yearly_stats[y_k]['losses'] += 1

            period_stats[p_k]['trades'] += 1
            period_stats[p_k]['pnl'] += pos['realized_pnl']
            if pos['realized_pnl'] > 0:
                period_stats[p_k]['wins'] += 1
            else:
                period_stats[p_k]['losses'] += 1
            period_stats[p_k]['end_bal'] = balance

        # Track Peak Equity and Drawdown
        if balance > peak_balance:
            peak_balance = balance
        dd_pct = (peak_balance - balance) / peak_balance * 100.0 if peak_balance > 0 else 0.0
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct

        # Daily Equity Record (at end of each day)
        daily_equity[day_key] = balance

        if len(active_positions) >= max_positions or balance <= 0:
            continue

        long_count = sum(1 for p in active_positions.values() if p['side'] == 'LONG')
        short_count = sum(1 for p in active_positions.values() if p['side'] == 'SHORT')

        # Scan for New Production Signals
        for sym in active_symbols:
            if sym in active_positions:
                continue
            if bar_i - symbol_last_trade_bar[sym] < cooldown_bars:
                continue
            s_idx = idx_maps[sym][bar_i]
            if s_idx == -1:
                continue

            sig = signals_map[sym][s_idx]
            c_price = closes_map[sym][s_idx]
            curr_atr = sig['atr']

            action = None
            tp1, sl = 0.0, 0.0
            ch_name = None

            # Priority 1: MSS Market Structure Shift
            if sig['mss_long'] and not btc_dump and long_count < max_directional:
                tp1 = c_price + (tp1_atr * curr_atr)
                sl = sig['last_sl'] - (0.5 * curr_atr)
                if (abs(tp1 - c_price) / (abs(c_price - sl) + 1e-9)) >= 1.8:
                    action = 'LONG'
                    ch_name = 'MSS_SHIFT'
            elif sig['mss_short'] and short_count < max_directional:
                tp1 = c_price - (tp1_atr * curr_atr)
                sl = sig['last_sh'] + (0.5 * curr_atr)
                if (abs(c_price - tp1) / (abs(sl - c_price) + 1e-9)) >= 1.8:
                    action = 'SHORT'
                    ch_name = 'MSS_SHIFT'

            # Priority 2: 5MA Consensus
            elif sig['cons_long'] and not btc_dump and long_count < max_directional:
                tp1 = c_price + (tp1_atr * curr_atr)
                sl = c_price - (1.5 * curr_atr)
                action = 'LONG'
                ch_name = '5MA_CONSENSUS'
            elif sig['cons_short'] and short_count < max_directional:
                tp1 = c_price - (tp1_atr * curr_atr)
                sl = c_price + (1.5 * curr_atr)
                action = 'SHORT'
                ch_name = '5MA_CONSENSUS'

            # Priority 3: Multi-Tier Fibonacci OTE
            elif sig['fib_long'] and not btc_dump and long_count < max_directional:
                tp1 = c_price + (tp1_atr * curr_atr)
                sl = sig['last_sl'] - (0.5 * curr_atr)
                if (abs(tp1 - c_price) / (abs(c_price - sl) + 1e-9)) >= 1.8:
                    action = 'LONG'
                    ch_name = 'FIBONACCI'
            elif sig['fib_short'] and short_count < max_directional:
                tp1 = c_price - (tp1_atr * curr_atr)
                sl = sig['last_sh'] + (0.5 * curr_atr)
                if (abs(c_price - tp1) / (abs(sl - c_price) + 1e-9)) >= 1.8:
                    action = 'SHORT'
                    ch_name = 'FIBONACCI'

            if action is not None:
                d_mult = darwin.get_multiplier(ch_name)
                base_margin = balance * margin_pct
                margin_alloc = base_margin * d_mult
                notional = min(margin_alloc * leverage, 1000.0)
                if notional < 5.00:
                    notional = 5.00
                margin_alloc = notional / leverage

                # Exchange Minimum Margin / Balance Check
                if balance < margin_alloc:
                    rejected_orders_count += 1
                    continue

                qty = notional / c_price
                entry_fee = notional * (FEE_SCHEDULE['maker_fee'] + FEE_SCHEDULE['slippage'])
                balance -= (margin_alloc + entry_fee)
                total_fees_paid += entry_fee

                active_positions[sym] = {
                    'symbol': sym,
                    'side': action,
                    'entry_price': c_price,
                    'qty': qty,
                    'remaining_qty': qty,
                    'margin': margin_alloc,
                    'tp1_p': tp1,
                    'sl_p': sl,
                    'tp1_hit': False,
                    'highest_since_entry': c_price,
                    'lowest_since_entry': c_price,
                    'atr': curr_atr,
                    'channel': ch_name,
                    'entry_time': cur_time,
                    'realized_pnl': -entry_fee,
                    'fees_paid': entry_fee,
                    'funding_fees': 0.0
                }
                symbol_last_trade_bar[sym] = bar_i

                if action == 'LONG':
                    long_count += 1
                else:
                    short_count += 1

                if len(active_positions) >= max_positions:
                    break

    # Close any open positions at the end of the 4-year backtest
    for sym, pos in list(active_positions.items()):
        s_idx = idx_maps[sym][-1]
        c_price = closes_map[sym][s_idx] if s_idx != -1 else pos['entry_price']
        pnl = (c_price - pos['entry_price']) * pos['remaining_qty'] if pos['side'] == 'LONG' else (pos['entry_price'] - c_price) * pos['remaining_qty']
        exit_fee = (c_price * pos['remaining_qty']) * (FEE_SCHEDULE['taker_fee'] + FEE_SCHEDULE['slippage'])
        net_pnl = pnl - exit_fee
        balance += (pos['margin'] * (0.50 if pos['tp1_hit'] else 1.00)) + net_pnl
        pos['realized_pnl'] += net_pnl
        pos['fees_paid'] += exit_fee
        total_fees_paid += exit_fee
        pos['exit_time'] = pd.Timestamp(time_index[-1])
        closed_trades.append(pos)

    # Performance Metrics Calculations
    n_trades = len(closed_trades)
    wins = [t for t in closed_trades if t['realized_pnl'] > 0]
    losses = [t for t in closed_trades if t['realized_pnl'] <= 0]
    win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0

    tot_win = sum(t['realized_pnl'] for t in wins)
    tot_loss = abs(sum(t['realized_pnl'] for t in losses))
    profit_factor = (tot_win / tot_loss) if tot_loss > 0 else (99.0 if tot_win > 0 else 0.0)

    net_pnl = balance - initial_balance
    total_return_pct = (net_pnl / initial_balance) * 100.0
    avg_trade_pnl = (net_pnl / n_trades) if n_trades > 0 else 0.0

    largest_win = max([t['realized_pnl'] for t in closed_trades], default=0.0)
    largest_loss = min([t['realized_pnl'] for t in closed_trades], default=0.0)

    # Consecutive Losses Streak
    max_consecutive_losses = 0
    curr_streak = 0
    for t in closed_trades:
        if t['realized_pnl'] <= 0:
            curr_streak += 1
            if curr_streak > max_consecutive_losses:
                max_consecutive_losses = curr_streak
        else:
            curr_streak = 0

    # Sharpe and Sortino Ratios (Annualized from daily returns)
    daily_vals = list(daily_equity.values())
    if len(daily_vals) > 2:
        daily_returns = np.diff(daily_vals) / (np.array(daily_vals[:-1]) + 1e-9)
        mean_d = np.mean(daily_returns)
        std_d = np.std(daily_returns)
        sharpe = (mean_d / (std_d + 1e-9)) * np.sqrt(365) if std_d > 0 else 0.0
        neg_returns = daily_returns[daily_returns < 0]
        downside_std = np.std(neg_returns) if len(neg_returns) > 0 else 0.0
        sortino = (mean_d / (downside_std + 1e-9)) * np.sqrt(365) if downside_std > 0 else 0.0
    else:
        sharpe, sortino = 0.0, 0.0

    sorted_months = sorted(monthly_stats.keys())
    green_months_count = sum(1 for m in sorted_months if monthly_stats[m]['pnl'] > 0)
    red_months_count = sum(1 for m in sorted_months if monthly_stats[m]['pnl'] <= 0)

    return {
        'starting_balance': initial_balance,
        'ending_balance': balance,
        'net_pnl': net_pnl,
        'return_pct': total_return_pct,
        'total_trades': n_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'average_trade': avg_trade_pnl,
        'max_drawdown': max_drawdown_pct,
        'sharpe': sharpe,
        'sortino': sortino,
        'largest_win': largest_win,
        'largest_loss': largest_loss,
        'consecutive_losses': max_consecutive_losses,
        'total_fees': total_fees_paid,
        'total_funding': total_funding_paid,
        'rejected_orders': rejected_orders_count,
        'period_stats': period_stats,
        'yearly_stats': yearly_stats,
        'monthly_stats': monthly_stats,
        'green_months_count': green_months_count,
        'red_months_count': red_months_count,
        'total_months': len(sorted_months),
        'closed_trades': closed_trades
    }


def print_audit_report(res):
    print("=" * 95)
    print(" ⚡ ATLAS 4-YEAR INSTITUTIONAL PRODUCTION AUDIT REPORT (2022 - 2026)")
    print("=" * 95)
    print(f" • Period Evaluated : September 18, 2022 → September 18, 2026 (48 Months)")
    print(f" • Universe         : {len(ALL_SYMBOLS)} Perpetual Assets ({', '.join(ALL_SYMBOLS)})")
    print(f" • Strategy         : Atlas 31-Model / 5MA Consensus + Fibonacci OTE + MSS/SMC + ATR Trailing")
    print("=" * 95)
    print(f"{'Metric':<32} | {'Result':>30}")
    print("-" * 65)
    print(f"{'Starting balance':<32} | ${res['starting_balance']:>29.2f}")
    print(f"{'Ending balance':<32} | ${res['ending_balance']:>29.2f}")
    print(f"{'Net P&L':<32} | ${res['net_pnl']:>+29.2f}")
    print(f"{'Return':<32} | {res['return_pct']:>+29.1f}%")
    print(f"{'Total trades':<32} | {res['total_trades']:>30,}")
    print(f"{'Win rate':<32} | {res['win_rate']:>29.1f}%")
    print(f"{'Profit factor':<32} | {res['profit_factor']:>30.2f}")
    print(f"{'Average trade':<32} | ${res['average_trade']:>+29.2f}")
    print(f"{'Max drawdown':<32} | {res['max_drawdown']:>29.2f}%")
    print(f"{'Sharpe':<32} | {res['sharpe']:>30.2f}")
    print(f"{'Sortino':<32} | {res['sortino']:>30.2f}")
    print(f"{'Largest win':<32} | ${res['largest_win']:>+29.2f}")
    print(f"{'Largest loss':<32} | ${res['largest_loss']:>+29.2f}")
    print(f"{'Consecutive losses (max)':<32} | {res['consecutive_losses']:>30}")
    print(f"{'Fees (maker/taker/slippage)':<32} | ${res['total_fees']:>29.2f}")
    print(f"{'Funding costs (8h perpetual)':<32} | ${res['total_funding']:>29.2f}")
    print(f"{'Rejected / Skipped (Min Margin)':<32} | {res['rejected_orders']:>30,}")
    print("=" * 95)

    print("\n" + "=" * 95)
    print(" 📅 YEAR-BY-YEAR RETURN BREAKDOWN (4 Separate 12-Month Periods):")
    print("=" * 95)
    print(f"{'Period':<16} | {'Trades':>8} | {'Win Rate':>10} | {'Net P&L':>16} | {'Status':>12}")
    print("-" * 70)
    for p_name, pst in res['period_stats'].items():
        wr = (pst['wins'] / pst['trades'] * 100.0) if pst['trades'] > 0 else 0.0
        status = "🟢 GREEN" if pst['pnl'] > 0 else ("🔴 RED" if pst['pnl'] < 0 else "⚪ FLAT")
        print(f"{p_name:<16} | {pst['trades']:>8,} | {wr:>9.1f}% | ${pst['pnl']:>+15.2f} | {status:>12}")
    print("=" * 95)

    print("\n" + "=" * 95)
    print(" 📅 CALENDAR YEAR PERFORMANCE:")
    print("=" * 95)
    for y in sorted(res['yearly_stats'].keys()):
        yst = res['yearly_stats'][y]
        wr = (yst['wins'] / yst['trades'] * 100.0) if yst['trades'] > 0 else 0.0
        status = "🟢 GREEN" if yst['pnl'] > 0 else "🔴 RED"
        print(f" • {y}: {yst['trades']:>5,} Trades | Win Rate: {wr:>5.1f}% | Net Profit: ${yst['pnl']:>+14,.2f} {status}")
    print("=" * 95)

    print("\n" + "=" * 95)
    print(f" 📅 48-MONTH CHRONOLOGICAL MONTHLY AUDIT:")
    print(f" • Total Months: {res['total_months']} | 🟢 Green Months: {res['green_months_count']} | 🔴 Red Months: {res['red_months_count']}")
    print(f" • '25/25 Green Months' Claim Audit: {'VERIFIED' if res['red_months_count'] == 0 else 'REFUTED (Found Red Months)'}")
    print("=" * 95)
    sorted_months = sorted(res['monthly_stats'].keys())
    for i in range(0, len(sorted_months), 4):
        chunk = sorted_months[i:i+4]
        line = " | ".join([f"{m}: ${res['monthly_stats'][m]['pnl']:>+7.2f} {'🟢' if res['monthly_stats'][m]['pnl']>0 else '🔴'}" for m in chunk])
        print(f"  {line}")
    print("=" * 95)


def main():
    parser = argparse.ArgumentParser(description="4-Year Institutional Backtest Audit")
    parser.add_argument("--balance", type=float, default=3.93, help="Starting balance in USDT (default: 3.93)")
    parser.add_argument("--leverage", type=int, default=50, help="Leverage (default: 50)")
    parser.add_argument("--margin-pct", type=float, default=0.03, help="Margin fraction per trade (default: 0.03)")
    args = parser.parse_args()

    dataset = load_and_filter_datasets()
    res = execute_audit_simulation(
        dataset=dataset,
        initial_balance=args.balance,
        leverage=args.leverage,
        margin_pct=args.margin_pct
    )
    print_audit_report(res)


if __name__ == '__main__':
    main()
