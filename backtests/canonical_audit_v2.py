#!/usr/bin/env python3
"""Atlas canonical institutional audit v2.

Research-only, deterministic OHLCV engine with:
- risk-based sizing (not fixed margin sizing)
- hard leverage cap (default 5x)
- minimum-notional and minimum-margin gates
- permanent risk halt after drawdown / loss streak
- actual cached funding rates when available; never synthetic funding
- fee + slippage accounting
- portfolio-level simultaneous-position cap
- chronological, no-lookahead signal evaluation

This is deliberately a transparent baseline. It does not claim to reproduce
production-only L2/ML features unless their historical datasets are supplied.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT","AVAXUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","NEARUSDT","BNBUSDT","SUIUSDT"]

@dataclass
class RiskConfig:
    initial_equity: float = 1000.0
    risk_per_trade: float = 0.005
    leverage_cap: float = 5.0
    min_notional: float = 5.0
    fee_rate: float = 0.00045
    slippage_bps: float = 1.5
    max_drawdown: float = 0.10
    max_consecutive_losses: int = 5
    max_positions: int = 5


def load_symbol(path: Path, start: str, end: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"open_time", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df[(df.open_time >= pd.Timestamp(start, tz="UTC")) & (df.open_time <= pd.Timestamp(end, tz="UTC"))].copy()
    df = df.sort_values("open_time").drop_duplicates("open_time")
    if df.empty:
        raise ValueError(f"{path.name}: no bars in requested window")
    delta = df.open_time.diff().dropna().dt.total_seconds()
    gaps = int((delta != 900).sum())
    if gaps:
        raise ValueError(f"{path.name}: {gaps} non-15m gaps detected")
    return df.reset_index(drop=True)


def funding_map(path: Path) -> dict[int, float]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    tcol = "fundingTime" if "fundingTime" in df.columns else "timestamp"
    rcol = "fundingRate" if "fundingRate" in df.columns else "rate"
    if tcol not in df or rcol not in df:
        raise ValueError(f"Invalid funding file: {path}")
    return {int(float(t)): float(r) for t, r in zip(df[tcol], df[rcol])}


def ema(x: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    tr = np.maximum(h-l, np.maximum(np.abs(h-np.roll(c,1)), np.abs(l-np.roll(c,1))))
    tr[0] = h[0]-l[0]
    return pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().to_numpy()


def signal(df: pd.DataFrame, i: int) -> Optional[str]:
    if i < 200:
        return None
    c = df.close.to_numpy()
    e9,e20,e50,e100,e200 = [ema(c,n)[i] for n in (9,20,50,100,200)]
    if e9 > e20 > e50 > e100 > e200 and c[i-1] <= e20 and c[i] > e20:
        return "LONG"
    if e9 < e20 < e50 < e100 < e200 and c[i-1] >= e20 and c[i] < e20:
        return "SHORT"
    return None


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-dir",default="backtests/historical_data_cache")
    ap.add_argument("--funding-dir",default="backtests/historical_data_cache/funding")
    ap.add_argument("--start",default="2022-09-18T00:00:00Z")
    ap.add_argument("--end",default="2026-09-18T00:00:00Z")
    ap.add_argument("--output",default="backtests/reports/canonical_v2_trades.csv")
    ap.add_argument("--summary",default="backtests/reports/canonical_v2_summary.json")
    ap.add_argument("--initial-equity",type=float,default=1000.0)
    ap.add_argument("--risk-per-trade",type=float,default=0.005)
    ap.add_argument("--leverage",type=float,default=5.0)
    args=ap.parse_args()
    cfg=RiskConfig(initial_equity=args.initial_equity,risk_per_trade=args.risk_per_trade,leverage_cap=args.leverage)
    data_dir=Path(args.data_dir); funding_dir=Path(args.funding_dir)
    datasets={}
    for sym in SYMBOLS:
        candidates=sorted(data_dir.glob(f"{sym}_15m*.csv"))
        if not candidates:
            continue
        datasets[sym]=load_symbol(candidates[0],args.start,args.end)
    if not datasets:
        raise SystemExit("No cached CSV datasets found.")

    prepared={}
    for sym,df in datasets.items():
        df=df.copy(); df["atr14"]=atr(df); prepared[sym]=df
    timeline=sorted(set(ts for df in prepared.values() for ts in df.open_time))
    equity=cfg.initial_equity; peak=equity; maxdd=0.; streak=0; halted=False; halt_reason=None; open_positions={}; trades=[]; rejected=0

    # One portfolio clock. Signals use only the last closed candle at decision time.
    for ts in timeline:
        if halted: break
        # Mark existing positions by deterministic future-bar simulation only.
        # New entries are capped by actual simultaneous open positions.
        for sym in list(open_positions):
            pos=open_positions[sym]
            df=prepared[sym]; row=df[df.open_time==ts]
            if row.empty: continue
            r=row.iloc[0]; h,l=float(r.high),float(r.low); exitp=None; why=None
            if pos["side"]=="LONG":
                if l<=pos["stop"]: exitp,why=pos["stop"],"SL"
                elif h>=pos["tp"]: exitp,why=pos["tp"],"TP"
            else:
                if h>=pos["stop"]: exitp,why=pos["stop"],"SL"
                elif l<=pos["tp"]: exitp,why=pos["tp"],"TP"
            if exitp is None: continue
            slip=cfg.slippage_bps/10000; exitp*=1-slip if pos["side"]=="LONG" else 1+slip
            gross=(exitp-pos["entry"])*pos["qty"] if pos["side"]=="LONG" else (pos["entry"]-exitp)*pos["qty"]
            fees=(pos["entry"]*pos["qty"]+exitp*pos["qty"])*cfg.fee_rate
            funding=0.; f=funding_map(funding_dir/f"{sym}_funding.csv")
            for ft,rate in f.items():
                if pos["entry_ts"]<ft<=int(ts.timestamp()*1000):
                    funding += pos["notional"]*rate*(-1 if pos["side"]=="LONG" else 1)
            net=gross-fees-funding; equity+=net; peak=max(peak,equity); dd=(peak-equity)/peak if peak else 1.; maxdd=max(maxdd,dd); streak=streak+1 if net<0 else 0
            trades.append({**pos,"exit_time":ts.isoformat(),"exit":exitp,"gross_pnl":gross,"fees":fees,"funding":funding,"net_pnl":net,"equity":equity,"reason":why})
            del open_positions[sym]
            if dd>=cfg.max_drawdown: halted=True; halt_reason="max_drawdown"
            elif streak>=cfg.max_consecutive_losses: halted=True; halt_reason="max_consecutive_losses"

        if halted or len(open_positions)>=cfg.max_positions: continue
        for sym,df in prepared.items():
            if sym in open_positions or len(open_positions)>=cfg.max_positions: continue
            matches=df.index[df.open_time==ts]
            if len(matches)==0: continue
            i=int(matches[0]); side=signal(df,i)
            if not side: continue
            av=float(df.iloc[i].atr14); entry_raw=float(df.iloc[i].close); slip=cfg.slippage_bps/10000; entry=entry_raw*(1+slip if side=="LONG" else 1-slip)
            stop_dist=max(.75*av,entry*.001); risk_cash=equity*cfg.risk_per_trade; qty=risk_cash/stop_dist; notional=qty*entry; margin=notional/cfg.leverage_cap
            if notional<cfg.min_notional or margin>=equity: rejected+=1; continue
            stop=entry-stop_dist if side=="LONG" else entry+stop_dist; tp=entry+1.5*stop_dist if side=="LONG" else entry-1.5*stop_dist
            open_positions[sym]={"symbol":sym,"side":side,"entry_time":ts.isoformat(),"entry_ts":int(ts.timestamp()*1000),"entry":entry,"qty":qty,"notional":notional,"stop":stop,"tp":tp}

    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    fields=list(trades[0].keys()) if trades else ["symbol","side","entry_time","exit_time","entry","exit","qty","notional","stop","tp","gross_pnl","fees","funding","net_pnl","equity","reason"]
    with out.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(trades)
    wins=[x for x in trades if x["net_pnl"]>0]; losses=[x for x in trades if x["net_pnl"]<0]; gw=sum(x["net_pnl"] for x in wins); gl=abs(sum(x["net_pnl"] for x in losses))
    summary={"period":{"start":args.start,"end":args.end},"datasets":{s:len(df) for s,df in prepared.items()},"initial_equity":cfg.initial_equity,"ending_equity":equity,"net_pnl":equity-cfg.initial_equity,"return_pct":(equity/cfg.initial_equity-1)*100,"trades":len(trades),"win_rate_pct":100*len(wins)/len(trades) if trades else 0,"profit_factor":gw/gl if gl else None,"fees":sum(x["fees"] for x in trades),"funding":sum(x["funding"] for x in trades),"max_drawdown_pct":maxdd*100,"rejected_min_margin":rejected,"halted":halted,"halt_reason":halt_reason,"risk_config":asdict(cfg),"methodology":"OHLCV baseline; real cached funding only; unavailable L2/ML history is not fabricated; risk sizing and portfolio caps are enforced."}
    Path(args.summary).parent.mkdir(parents=True,exist_ok=True); Path(args.summary).write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))

if __name__=="__main__": main()
