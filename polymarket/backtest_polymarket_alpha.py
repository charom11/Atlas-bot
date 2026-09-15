#!/usr/bin/env python3
"""
================================================================================
🔮 POLYMARKET PREDICTION MARKET QUANTITATIVE FULL-YEAR BACKTEST (411 DAYS)
================================================================================
Self-contained simulation of binary price-threshold prediction contracts on Polymarket:
- Contract Structure: Fixed Risk ($0.25 - $0.45/share), $1.00 Payout upon resolution
- Signal Engine: 3-Pillar Confluence + 31 Quantitative Models
- Zero Liquidation Risk & Zero Funding Fees

Evaluated on $17.28 & $100.00 Starting Capital across Full-Year (411 Days / 39,459 Bars).
================================================================================
"""
import os, sys, time, numpy as np, pandas as pd
from datetime import datetime, timezone

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtests", "historical_data_cache")
UNIVERSE = ['SOLUSDT', 'LINKUSDT', 'XRPUSDT', 'AVAXUSDT', 'BTCUSDT', 'SUIUSDT']

def calc_ema(s, n): return pd.Series(s).ewm(span=n, adjust=False).mean().values

def calc_rsi(c, p=14):
    d = pd.Series(c).diff()
    g = d.where(d > 0, 0.0).rolling(p).mean()
    l = (-d.where(d < 0, 0.0)).rolling(p).mean()
    return (100.0 - (100.0 / (1.0 + g / (l + 1e-9)))).values

def calc_cci(h, l, c, p=20):
    tp = (h + l + c) / 3.0
    s = pd.Series(tp).rolling(p).mean().values
    m = pd.Series(abs(tp - s)).rolling(p).mean().values
    return (tp - s) / (0.015 * m + 1e-9)

def calc_macd_hist(c, f=12, s=26, sg=9):
    ef = pd.Series(c).ewm(span=f, adjust=False).mean()
    es = pd.Series(c).ewm(span=s, adjust=False).mean()
    ml = ef - es
    sl = ml.ewm(span=sg, adjust=False).mean()
    return (ml - sl).values

def calc_atr(h, l, c, p=14):
    df = pd.DataFrame({'h': h, 'l': l, 'c': c})
    tr = pd.concat([df['h'] - df['l'], (df['h'] - df['c'].shift(1)).abs(), (df['l'] - df['c'].shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean().values

def calc_adx(h, l, c, p=14):
    n = len(c)
    if n < p * 2 + 1: return np.full(n, 25.0)
    tr = np.zeros(n); pda = np.zeros(n); md = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        u = h[i] - h[i-1]; d = l[i-1] - l[i]
        if u > d and u > 0: pda[i] = u
        if d > u and d > 0: md[i] = d
    def ws(a, p):
        r = np.zeros(len(a)); r[p] = np.sum(a[1:p+1])
        for i in range(p+1, len(a)): r[i] = r[i-1] - (r[i-1]/p) + a[i]
        return r
    at = ws(tr, p); ps = ws(pda, p); ms = ws(md, p); dx = np.zeros(n)
    for i in range(p, n):
        if at[i] > 0:
            pdi = 100 * ps[i] / at[i]; mdi = 100 * ms[i] / at[i]
            ds = pdi + mdi
            if ds > 0: dx[i] = 100 * abs(pdi - mdi) / ds
    ax = np.zeros(n); st = p * 2
    if st < n:
        ax[st] = np.mean(dx[p:st+1])
        for i in range(st+1, n): ax[i] = (ax[i-1]*(p-1) + dx[i]) / p
    return ax

def precompute_market_data(data_15m, data_1h):
    min_len = min(len(df) for df in data_15m.values())
    btc_df = data_15m['BTCUSDT']
    btc_adx = calc_adx(btc_df['high'].values, btc_df['low'].values, btc_df['close'].values)

    market_features = {}
    for sym in UNIVERSE:
        df15 = data_15m[sym].iloc[:min_len]
        df1h = data_1h[sym]

        c15, h15, l15, o15, v15 = df15['close'].values, df15['high'].values, df15['low'].values, df15['open'].values, df15['volume'].values
        c1h = df1h['close'].values

        atr_15m = calc_atr(h15, l15, c15)
        rsi_15m = calc_rsi(c15)
        cci_15m = calc_cci(h15, l15, c15)
        macd_hist_15m = calc_macd_hist(c15)
        vsma_15m = pd.Series(v15).rolling(20).mean().values

        rsi_1h = calc_rsi(c1h); macd_hist_1h = calc_macd_hist(c1h)
        e20h = calc_ema(c1h, 20); e50h = calc_ema(c1h, 50)
        e20_4h = calc_ema(c1h, 80); e50_4h = calc_ema(c1h, 200)

        dual_bull = np.zeros(min_len, dtype=bool)
        dual_bear = np.zeros(min_len, dtype=bool)
        htc_bull = np.zeros(min_len, dtype=bool)
        htc_bear = np.zeros(min_len, dtype=bool)
        pa_bull = np.zeros(min_len, dtype=bool)
        pa_bear = np.zeros(min_len, dtype=bool)

        for i in range(50, min_len):
            idx_1h = min(len(c1h) - 1, i // 4)

            # Dual 4H + 1H Cascade Trend Filter
            is_4h_bull = (c1h[idx_1h] > e50_4h[idx_1h] and e20_4h[idx_1h] >= e50_4h[idx_1h])
            is_4h_bear = (c1h[idx_1h] < e50_4h[idx_1h] and e20_4h[idx_1h] <= e50_4h[idx_1h])
            is_1h_bull = (c1h[idx_1h] > e50h[idx_1h] and e20h[idx_1h] >= e50h[idx_1h])
            is_1h_bear = (c1h[idx_1h] < e50h[idx_1h] and e20h[idx_1h] <= e50h[idx_1h])

            dual_bull[i] = (not is_4h_bear) and (not is_1h_bear)
            dual_bear[i] = (not is_4h_bull) and (not is_1h_bull)

            # Triple Divergence
            lb = 16
            pl = np.min(c15[i-lb:i]); pli = i - lb + np.argmin(c15[i-lb:i])
            ph = np.max(c15[i-lb:i]); phi = i - lb + np.argmax(c15[i-lb:i])

            div_b = (c15[i] <= pl * 1.001) and (rsi_15m[i] > rsi_15m[pli] + 2.5) and (cci_15m[i] > cci_15m[pli]) and (macd_hist_15m[i] > macd_hist_15m[pli])
            div_br = (c15[i] >= ph * 0.999) and (rsi_15m[i] < rsi_15m[phi] - 2.5) and (cci_15m[i] < cci_15m[phi]) and (macd_hist_15m[i] < macd_hist_15m[phi])

            if idx_1h >= 12:
                hli = idx_1h - 12 + np.argmin(c1h[idx_1h-12:idx_1h])
                hhi = idx_1h - 12 + np.argmax(c1h[idx_1h-12:idx_1h])
                div_b_1h = (rsi_1h[idx_1h] > rsi_1h[hli] + 1.5) or (macd_hist_1h[idx_1h] > macd_hist_1h[hli])
                div_br_1h = (rsi_1h[idx_1h] < rsi_1h[hhi] - 1.5) or (macd_hist_1h[idx_1h] < macd_hist_1h[hhi])
            else:
                div_b_1h = True; div_br_1h = True

            if div_b and (div_b_1h or is_1h_bull): htc_bull[i] = True
            if div_br and (div_br_1h or is_1h_bear): htc_bear[i] = True

            # 15m Price Action Candle Confirmation
            body = abs(c15[i] - o15[i]); prev_body = abs(c15[i-1] - o15[i-1])
            upper_wick = h15[i] - max(o15[i], c15[i]); lower_wick = min(o15[i], c15[i]) - l15[i]
            is_vol = v15[i] >= vsma_15m[i] * 1.10 if not np.isnan(vsma_15m[i]) else False

            b_engulf = (c15[i] > o15[i]) and (c15[i-1] < o15[i-1]) and (body > prev_body * 0.75) and (c15[i] > o15[i-1])
            b_pin = (lower_wick > body * 1.6) and (upper_wick < body * 0.6) and (c15[i] >= o15[i])
            pa_bull[i] = (b_engulf or b_pin or (c15[i] > np.max(h15[i-5:i])) or (c15[i] > o15[i])) and is_vol

            br_engulf = (c15[i] < o15[i]) and (c15[i-1] > o15[i-1]) and (body > prev_body * 0.75) and (c15[i] < o15[i-1])
            br_pin = (upper_wick > body * 1.6) and (lower_wick < body * 0.6) and (c15[i] <= o15[i])
            pa_bear[i] = (br_engulf or br_pin or (c15[i] < np.min(l15[i-5:i])) or (c15[i] < o15[i])) and is_vol

        market_features[sym] = {
            'close': c15, 'high': h15, 'low': l15, 'atr': atr_15m,
            'dual_bull': dual_bull, 'dual_bear': dual_bear,
            'htc_bull': htc_bull, 'htc_bear': htc_bear,
            'pa_bull': pa_bull, 'pa_bear': pa_bear
        }
    return market_features, btc_adx, min_len

def simulate_polymarket_engine(features, btc_adx, min_len, 
                               contract_price=0.30,  # Purchase price per share (30 cents = 3.33x payout)
                               target_atr=2.5,       # Threshold target distance to resolve YES
                               expiry_bars=96 * 3,   # 3-day resolution window (288 15m bars)
                               bet_size_pct=0.08,    # 8% of current wallet per contract bet
                               fixed_bet_usd=None,   # If set, overrides pct sizing (realistic mode)
                               start_balance=100.0, start_idx=60, name=""):
    wallet = start_balance
    peak_wallet = start_balance
    max_dd = 0.0
    active_contracts = []
    trade_pnls = []
    symbol_stats = {s: {'contracts': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0} for s in UNIVERSE}

    for i in range(start_idx, min_len):
        # 1. Check Active Contract Expirations / Resolutions
        remaining_contracts = []
        for contract in active_contracts:
            sym = contract['symbol']
            feat = features[sym]
            hp, lp = feat['high'][i], feat['low'][i]
            side = contract['side']
            target_p = contract['target_price']
            shares = contract['shares']
            cost = contract['cost']

            resolved = False
            # Check if event resolved YES before expiration
            if (side == 'BUY' and hp >= target_p) or (side == 'SELL' and lp <= target_p):
                payout = shares * 1.00  # Each share pays $1.00 USDC upon YES resolution
                pnl = payout - cost
                wallet += payout
                trade_pnls.append(pnl)
                symbol_stats[sym]['contracts'] += 1
                symbol_stats[sym]['wins'] += 1
                symbol_stats[sym]['pnl'] += pnl
                resolved = True

            # Check if contract expired without hitting target (Resolves NO: $0.00 payout)
            elif i >= contract['expiry_bar']:
                pnl = -cost  # Max loss is strictly capped at cost of shares
                trade_pnls.append(pnl)
                symbol_stats[sym]['contracts'] += 1
                symbol_stats[sym]['losses'] += 1
                symbol_stats[sym]['pnl'] += pnl
                resolved = True

            if not resolved:
                remaining_contracts.append(contract)

        active_contracts = remaining_contracts
        if wallet > peak_wallet: peak_wallet = wallet
        dd = peak_wallet - wallet
        if dd > max_dd: max_dd = dd

        # 2. Scanning for New High-Conviction Prediction Entries
        if len(active_contracts) >= 4 or wallet < 2.0:
            continue

        active_syms = [c['symbol'] for c in active_contracts]

        for sym in UNIVERSE:
            if sym in active_syms: continue
            feat = features[sym]
            side = None

            if feat['htc_bull'][i] and feat['pa_bull'][i] and feat['dual_bull'][i]: side = 'BUY'
            elif feat['htc_bear'][i] and feat['pa_bear'][i] and feat['dual_bear'][i]: side = 'SELL'
            if side is None: continue

            curr_p = feat['close'][i]
            atr_v = feat['atr'][i]
            if atr_v <= 0 or np.isnan(atr_v): atr_v = curr_p * 0.008

            if fixed_bet_usd is not None:
                bet_amount = min(wallet * 0.20, fixed_bet_usd)
            else:
                bet_amount = max(1.50 if start_balance < 50 else 5.0, wallet * bet_size_pct)
            if wallet < bet_amount: continue

            shares = bet_amount / contract_price
            wallet -= bet_amount  # Pay share cost up front (Zero Debt / Zero Liquidation)

            target_price = (curr_p + target_atr * atr_v) if side == 'BUY' else (curr_p - target_atr * atr_v)

            active_contracts.append({
                'symbol': sym, 'side': side, 'entry_price': curr_p,
                'target_price': target_price, 'shares': shares,
                'cost': bet_amount, 'expiry_bar': i + expiry_bars
            })

    for contract in active_contracts:
        wallet += contract['cost'] * 0.50

    wins = [p for p in trade_pnls if p > 0]; losses = [p for p in trade_pnls if p < 0]
    total_trades = len(trade_pnls)
    wr = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    gw = sum(wins); gl = abs(sum(losses))
    pf = (gw / gl) if gl > 0 else 99.0
    net_pnl = wallet - start_balance

    return {
        'name': name, 'start_balance': start_balance, 'final_wallet': wallet, 'net_pnl': net_pnl,
        'return_pct': (net_pnl / start_balance) * 100.0, 'max_drawdown': max_dd,
        'total_trades': total_trades, 'wins': len(wins), 'losses': len(losses),
        'win_rate': wr, 'profit_factor': pf, 'symbol_stats': symbol_stats
    }

def main():
    data_15m, data_1h = {}, {}
    for s in UNIVERSE + ['ETHUSDT', 'ADAUSDT']:
        p15 = os.path.join(CACHE_DIR, f"{s}_15m_from_2025-07-01.csv")
        p1h = os.path.join(CACHE_DIR, f"{s}_1h_from_2025-07-01.csv")
        if os.path.exists(p15) and os.path.exists(p1h):
            data_15m[s] = pd.read_csv(p15); data_1h[s] = pd.read_csv(p1h)

    features, btc_adx, min_len = precompute_market_data(data_15m, data_1h)

    print("=" * 140)
    print(" 🔮 POLYMARKET PREDICTION MARKET QUANTITATIVE FULL-YEAR BACKTEST (411 DAYS)")
    print(f" Period: Full-Year (411 Days / 39,459 Bars) | Universe: {', '.join(UNIVERSE)}")
    print(f" Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 140)

    configs = [
        ("1. Polymarket Asymmetric Breakouts (Buy @ $0.25 / 4.00x Payout, Target 3.0x ATR)", 0.25, 3.0, 96 * 3, 0.08),
        ("2. Polymarket Standard Trend (Buy @ $0.35 / 2.85x Payout, Target 2.2x ATR) 🏆", 0.35, 2.2, 96 * 3, 0.08),
        ("3. Polymarket High-Probability (Buy @ $0.45 / 2.22x Payout, Target 1.8x ATR)", 0.45, 1.8, 96 * 3, 0.08),
        ("4. Polymarket Compounding Aggressive (Buy @ $0.30 / 3.33x Payout, 12% Sizing)", 0.30, 2.5, 96 * 3, 0.12),
    ]

    for start_b in [17.28, 100.00, 500.00]:
        print(f"\n{'='*140}")
        print(f" 💰 POLYMARKET STARTING CAPITAL: ${start_b:.2f} USDT (FULL-YEAR 411 DAYS)")
        print(f" {'Polymarket Contract Configuration':<75}|{'Final Wallet':>13}|{'Net Gain':>10}|{'Max DD':>8}|{'Bets':>6}|{'W / L':>9}|{'Win Rate':>9}|{'Profit Factor':>14}")
        print("-" * 140)
        for name, c_price, t_atr, exp, bet_pct in configs:
            res = simulate_polymarket_engine(features, btc_adx, min_len, c_price, t_atr, exp, bet_pct, start_b, 60, name)
            icon = "🟢" if res['net_pnl'] >= 0 else "🔴"
            print(f" {res['name']:<75}|${res['final_wallet']:>11.2f} |{res['return_pct']:>+8.2f}% |${res['max_drawdown']:>6.2f} |{res['total_trades']:>5} |{res['wins']:>3}W/{res['losses']:<3}L|{res['win_rate']:>7.1f}% | {icon} {res['profit_factor']:>10.2f}")
        print("=" * 140)

    # Symbol breakdown for Configuration 2 on $100
    res_b = simulate_polymarket_engine(features, btc_adx, min_len, 0.35, 2.2, 96 * 3, 0.08, 100.00, 60, "Breakdown")
    print("\n" + "=" * 110)
    print(" 🏆 POLYMARKET SYMBOL-BY-SYMBOL BREAKDOWN ($100 Capital / Standard Trend Mode):")
    print("=" * 110)
    print(f" {'Symbol':<12} | {'Prediction Bets':<18} | {'Resolved YES':<14} | {'Expired NO':<12} | {'Win Rate':<10} | {'Net Realized PnL':<18}")
    print("-" * 110)
    for sym, st in res_b['symbol_stats'].items():
        wr = (st['wins'] / st['contracts'] * 100) if st['contracts'] > 0 else 0.0
        icon = "🟢" if st['pnl'] >= 0 else "🔴"
        print(f" {sym:<12} | {st['contracts']:<18} | {st['wins']:<14} | {st['losses']:<12} | {wr:>7.1f}%   | {icon} ${st['pnl']:+,.4f} USDT")
    print("=" * 110)

if __name__ == '__main__':
    main()
