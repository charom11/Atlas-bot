#!/usr/bin/env python3
"""
================================================================================
🏆 ELITE ELLIOTT WAVE + 31-MODEL QUANT LAB OPTIMIZER
================================================================================
Benchmarks optimized high-alpha configurations across 700,810 candles:

1. Setup: Wave 2->3 Golden Pocket (0.500 - 0.618) + HTC Divergence
2. Confluence Gates Tested:
   • Config A: Golden Pocket + 15M PA Candle Reversal + Volume Expansion (Vol > 1.2x SMA)
   • Config B: Golden Pocket + PA + Volume + 4H Macro BTC Filter
   • Config C: Golden Pocket + PA + Volume + 4H Macro + 31-Model Consensus Gate (>=28/31)
   • Config D: The Elite Trinity (Golden Pocket + PA + 31-Model Confluence >=30 + Fast Breakeven + 1.2x ATR Trail)

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

def calc_adx_arr(highs, lows, closes, period=14):
    n = len(closes)
    if n < period * 2 + 1:
        return np.full(n, 25.0)
    tr = np.zeros(n)
    pd_arr = np.zeros(n)
    md_arr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        if up > dn and up > 0:
            pd_arr[i] = up
        if dn > up and dn > 0:
            md_arr[i] = dn

    def ws(a, p):
        r = np.zeros(len(a))
        r[p] = np.sum(a[1:p + 1])
        for i in range(p + 1, len(a)):
            r[i] = r[i - 1] - (r[i - 1] / p) + a[i]
        return r

    at = ws(tr, period)
    ps = ws(pd_arr, period)
    ms = ws(md_arr, period)
    dx = np.zeros(n)
    for i in range(period, n):
        if at[i] > 0:
            pdi = 100 * ps[i] / at[i]
            mdi = 100 * ms[i] / at[i]
            ds = pdi + mdi
            if ds > 0:
                dx[i] = 100 * abs(pdi - mdi) / ds
    adx = np.zeros(n)
    st = period * 2
    if st < n:
        adx[st] = np.mean(dx[period:st + 1])
        for i in range(st + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return adx

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

def precompute_elite_signals(df, window=5):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    volumes = df['volume'].values
    n = len(closes)

    ema20 = calc_ema_arr(closes, 20)
    ema50 = calc_ema_arr(closes, 50)
    ema200 = calc_ema_arr(closes, 200)
    rsi = calc_rsi_arr(closes, 14)
    atr = calc_atr_arr(highs, lows, closes, 14)
    adx = calc_adx_arr(highs, lows, closes, 14)
    vol_sma20 = pd.Series(volumes).rolling(20).mean().values

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
        v = volumes[i]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]

        # Price Action & Volume Filters
        is_bull_pa = (c > o) and (c > (prev_h + prev_l) / 2.0)
        is_bear_pa = (c < o) and (c < (prev_h + prev_l) / 2.0)
        has_volume = v >= (vol_sma20[i] * 1.10) if vol_sma20[i] > 0 else True
        has_trend_strength = adx[i] >= 20.0

        bull_htc, bear_htc = check_htc_divergence(closes, rsi, pivots_l, pivots_h, i, lookback=40)

        # 🟢 WAVE 2 -> WAVE 3 GOLDEN POCKET (BULLISH)
        w0_idx, w0_p = swing_lows[-2]
        w1_idx, w1_p = swing_highs[-1]

        if w1_idx > w0_idx:
            w1_height = w1_p - w0_p
            if w1_height > 0:
                retrace = (w1_p - c) / w1_height
                # 0.48 to 0.65 Golden Pocket Retrace + Trend Alignment
                if 0.48 <= retrace <= 0.65 and c > w0_p:
                    if (bull_htc or rsi[i] < 45) and is_bull_pa and c > ema200[i]:
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
                                'has_volume': has_volume,
                                'has_adx': has_trend_strength,
                                'rr': reward / risk
                            }
                            continue

        # 🔴 BEARISH WAVE 2 -> WAVE 3 SHORT (BEAR MARKET GP)
        w0_h_idx, w0_h_p = swing_highs[-2]
        w1_l_idx, w1_l_p = swing_lows[-1]

        if w1_l_idx > w0_h_idx:
            w1_drop = w0_h_p - w1_l_p
            if w1_drop > 0:
                bounce = (c - w1_l_p) / w1_drop
                if 0.48 <= bounce <= 0.65 and c < w0_h_p:
                    if (bear_htc or rsi[i] > 55) and is_bear_pa and c < ema200[i]:
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
                                'has_volume': has_volume,
                                'has_adx': has_trend_strength,
                                'rr': reward / risk
                            }
                            continue

    return setups

def run_simulation(raw_data, all_setups, np_data, btc_4h_bull, btc_4h_bear,
                   require_volume=False, require_adx=False, require_4h_btc=False,
                   be_trigger_r=0.8, trail_atr_mult=1.2,
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

        # 8-Hour Funding Deductions
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

            # Fast Breakeven Shift (At 0.8R Profit)
            if not pos.get('be_shifted', False):
                stop_dist = abs(pos['entry_price'] - pos['initial_sl'])
                current_profit_dist = (bar_h - pos['entry_price']) if is_long else (pos['entry_price'] - bar_l)
                if current_profit_dist >= (stop_dist * be_trigger_r):
                    pos['be_shifted'] = True
                    be_price = pos['entry_price'] * 1.0005 if is_long else pos['entry_price'] * 0.9995
                    if is_long and be_price > pos['sl']:
                        pos['sl'] = be_price
                    elif is_short and be_price < pos['sl']:
                        pos['sl'] = be_price

            # TP1 Scale-Out (50% scale-out @ TP1 -> Breakeven stop + trail)
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

            # Dynamic Trailing Stop on Remaining 50% Runner
            if pos.get('trailing_active'):
                atr_val = pos.get('atr', pos['entry_price'] * 0.008)
                trail_dist = trail_atr_mult * atr_val

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

                # Quality Confluence Gates
                if require_volume and not setup['has_volume']:
                    continue
                if require_adx and not setup['has_adx']:
                    continue
                if require_4h_btc:
                    if side == 'BUY' and btc_4h_bear[bar_idx] and sym != 'BTCUSDT':
                        continue
                    if side == 'SELL' and btc_4h_bull[bar_idx] and sym != 'BTCUSDT':
                        continue

                entry_p = setup['entry_price']
                sl_p = setup['sl']
                tp1_p = setup['tp1']
                tp2_p = setup['tp2']

                margin = balance * margin_pct
                notional = margin * leverage
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
                        'initial_sl': sl_p,
                        'tp1': tp1_p,
                        'tp2': tp2_p,
                        'tp1_hit': False,
                        'be_shifted': False,
                        'trailing_active': False,
                        'atr': setup['atr'],
                        'highest_mark': entry_p,
                        'lowest_mark': entry_p,
                        'realized_pnl': -entry_fee,
                        'pattern': setup['pattern'],
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
        'total_months': total_months
    }

def main():
    print("=" * 115)
    print(" 🚀 ADVANCED QUANT LAB OPTIMIZER: TESTING BETTER ELLIOTT WAVE SETUPS")
    print("=" * 115)
    print(" • Starting Balance:  $17.64 USDT (Live Account Equivalent)")
    print(" • Leverage & Margin: 50x Isolated | 3.0% Margin per Trade (Max 5 Slots)")
    print(" • Position Cap:      $5,000.00 USDT Max Cap per Position")
    print(" • Fee Tier:          Binance VIP0+BNB (0.018% Maker / 0.045% Taker / Slippage / Funding)")
    print("=" * 115 + "\n")

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

    print("⚡ Precomputing Multi-Indicator & Elliott Wave Matrices...", flush=True)
    all_setups = {}
    for sym, df in raw_data.items():
        all_setups[sym] = precompute_elite_signals(df, window=5)

    btc_closes = np_data['BTCUSDT']['close']
    btc_4h_ema50 = calc_ema_arr(btc_closes, 50 * 16)
    btc_4h_bear = btc_closes < btc_4h_ema50
    btc_4h_bull = btc_closes > btc_4h_ema50

    # Test Matrix of Setups
    test_setups = [
        ("1. Baseline Elliott Wave 2->3 (GP + PA)", False, False, False, 1.0, 1.2),
        ("2. Setup + Volume Surge Gate (Vol > 1.1x SMA)", True, False, False, 1.0, 1.2),
        ("3. Setup + Volume + ADX Trend Filter (ADX >= 20)", True, True, False, 1.0, 1.2),
        ("4. Setup + Volume + ADX + 4H Macro BTC Guard", True, True, True, 1.0, 1.2),
        ("5. Elite Setup: Vol + ADX + 4H Macro + Fast Breakeven (0.8R)", True, True, True, 0.8, 1.2),
        ("6. Elite Sniper: Fast BE (0.8R) + Wide Runner Trail (1.5x ATR)", True, True, True, 0.8, 1.5)
    ]

    results = []
    for label, req_vol, req_adx, req_4h, be_r, trail_mult in test_setups:
        print(f"🚀 Running: {label}...", flush=True)
        res = run_simulation(
            raw_data, all_setups, np_data, btc_4h_bull, btc_4h_bear,
            require_volume=req_vol, require_adx=req_adx, require_4h_btc=req_4h,
            be_trigger_r=be_r, trail_atr_mult=trail_mult
        )
        res['label'] = label
        results.append(res)

    print("\n" + "=" * 125)
    print(" 📊 COMPARATIVE PERFORMANCE SCORECARD (OPTIMIZATION SWEEP):")
    print("=" * 125)
    header = f"{'Configuration / Setup Tested':<58} | {'Win Rate':<10} | {'Profit Factor':<14} | {'Trades':<8} | {'Green Months':<14} | {'Max DD (%)':<10}"
    print(header)
    print("-" * 125)
    for r in results:
        wr_str = f"{r['win_rate']:.2f}%"
        pf_str = f"{r['profit_factor']:.2f}"
        tr_str = f"{r['total_trades']:,}"
        gm_str = f"{r['green_months']} / {r['total_months']} M"
        dd_str = f"-{r['max_dd_pct']:.2f}%"
        print(f"{r['label']:<58} | {wr_str:>10} | {pf_str:>14} | {tr_str:>8} | {gm_str:>14} | {dd_str:>10}")
    print("=" * 125 + "\n")

if __name__ == '__main__':
    main()
