#!/usr/bin/env python3
"""Atlas canonical institutional audit v2.

Research-only deterministic OHLCV engine with risk sizing, leverage cap,
exchange gates, portfolio limits, real cached funding when available, costs,
and fail-closed dataset validation. This is a transparent baseline and does
not claim unavailable L2/ML production features.
"""
from __future__ import annotations
import argparse,csv,json
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Optional
import numpy as np,pandas as pd

SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT","AVAXUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","NEARUSDT","BNBUSDT","SUIUSDT"]
@dataclass
class RiskConfig:
    initial_equity:float=1000.; risk_per_trade:float=.005; leverage_cap:float=5.; min_notional:float=5.; fee_rate:float=.00045; slippage_bps:float=1.5; max_drawdown:float=.10; max_consecutive_losses:int=5; max_positions:int=5

def load_symbol(path:Path,start:str,end:str)->pd.DataFrame:
    df=pd.read_csv(path); req={"open_time","open","high","low","close","volume"}; missing=req.difference(df.columns)
    if missing: raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    df["open_time"]=pd.to_datetime(df["open_time"],utc=True); df=df[(df.open_time>=pd.Timestamp(start,tz="UTC"))&(df.open_time<=pd.Timestamp(end,tz="UTC"))].copy()
    if df.empty: raise ValueError(f"{path.name}: no bars in requested window")
    df=df.sort_values("open_time").reset_index(drop=True)
    dup=df.open_time.duplicated(keep=False)
    if dup.any(): raise ValueError(f"{path.name}: {int(dup.sum())} duplicate timestamps detected")
    delta=df.open_time.diff().dropna().dt.total_seconds(); bad=int((delta!=900).sum())
    if bad: raise ValueError(f"{path.name}: {bad} non-15m gaps detected")
    return df

def funding_map(path:Path)->dict[int,float]:
    if not path.exists(): return {}
    df=pd.read_csv(path); tcol="fundingTime" if "fundingTime" in df.columns else "timestamp"; rcol="fundingRate" if "fundingRate" in df.columns else "rate"
    if tcol not in df or rcol not in df: raise ValueError(f"Invalid funding file: {path}")
    out={}
    for t,r in zip(df[tcol],df[rcol]):
        ts=int(float(t)); rate=float(r)
        if ts<=0 or not np.isfinite(rate): raise ValueError(f"Invalid funding row in {path}: {t},{r}")
        if ts in out: raise ValueError(f"Duplicate funding timestamp in {path}: {ts}")
        out[ts]=rate
    return out

def ema(x,n): return pd.Series(x).ewm(span=n,adjust=False).mean().to_numpy()
def atr(df,n=14):
    h,l,c=df.high.to_numpy(),df.low.to_numpy(),df.close.to_numpy(); prev=np.roll(c,1); tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev))); tr[0]=h[0]-l[0]; return pd.Series(tr).ewm(alpha=1/n,adjust=False).mean().to_numpy()
def signal(df,i)->Optional[str]:
    if i<200:return None
    c=df.close.to_numpy(); e9,e20,e50,e100,e200=[ema(c,n)[i] for n in (9,20,50,100,200)]
    if e9>e20>e50>e100>e200 and c[i-1]<=e20 and c[i]>e20:return "LONG"
    if e9<e20<e50<e100<e200 and c[i-1]>=e20 and c[i]<e20:return "SHORT"
    return None

def main():
    p=argparse.ArgumentParser(); p.add_argument('--data-dir',default='backtests/historical_data_cache'); p.add_argument('--funding-dir',default='backtests/historical_data_cache/funding'); p.add_argument('--start',default='2022-09-18T00:00:00Z'); p.add_argument('--end',default='2026-09-18T00:00:00Z'); p.add_argument('--output',default='backtests/reports/canonical_v2_trades.csv'); p.add_argument('--summary',default='backtests/reports/canonical_v2_summary.json'); p.add_argument('--initial-equity',type=float,default=1000.); p.add_argument('--risk-per-trade',type=float,default=.005); p.add_argument('--leverage',type=float,default=5.); args=p.parse_args()
    cfg=RiskConfig(initial_equity=args.initial_equity,risk_per_trade=args.risk_per_trade,leverage_cap=args.leverage); d=Path(args.data_dir); fd=Path(args.funding_dir); datasets={}
    for sym in SYMBOLS:
        files=sorted(d.glob(f'{sym}_15m*.csv'))
        if not files: continue
        datasets[sym]=load_symbol(files[0],args.start,args.end)
    if not datasets: raise SystemExit('No cached CSV datasets found.')
    prepared={s:df.assign(atr14=atr(df)) for s,df in datasets.items()}; funding={s:funding_map(fd/f'{s}_funding.csv') for s in prepared}
    timeline=sorted(set(ts for df in prepared.values() for ts in df.open_time)); equity=cfg.initial_equity; peak=equity; maxdd=0.; streak=0; halted=False; halt_reason=None; rejected=0; openp={}; trades=[]
    for ts in timeline:
        if halted: break
        for sym in list(openp):
            pos=openp[sym]; df=prepared[sym]; m=df.index[df.open_time==ts]
            if len(m)==0: continue
            r=df.iloc[int(m[0])]; h,l=float(r.high),float(r.low); exitp=why=None
            if pos['side']=='LONG':
                if l<=pos['stop']: exitp,why=pos['stop'],'SL'
                elif h>=pos['tp']: exitp,why=pos['tp'],'TP'
            else:
                if h>=pos['stop']: exitp,why=pos['stop'],'SL'
                elif l<=pos['tp']: exitp,why=pos['tp'],'TP'
            if exitp is None: continue
            slip=cfg.slippage_bps/10000; exitp*=1-slip if pos['side']=='LONG' else 1+slip; gross=(exitp-pos['entry'])*pos['qty'] if pos['side']=='LONG' else (pos['entry']-exitp)*pos['qty']; fees=(pos['entry']*pos['qty']+exitp*pos['qty'])*cfg.fee_rate; fund=sum(pos['notional']*rate*(-1 if pos['side']=='LONG' else 1) for ft,rate in funding[sym].items() if pos['entry_ts']<ft<=int(ts.timestamp()*1000)); net=gross-fees-fund; equity+=net; peak=max(peak,equity); dd=(peak-equity)/peak if peak else 1.; maxdd=max(maxdd,dd); streak=streak+1 if net<0 else 0
            trades.append({**pos,'exit_time':ts.isoformat(),'exit':exitp,'gross_pnl':gross,'fees':fees,'funding':fund,'net_pnl':net,'equity':equity,'reason':why}); del openp[sym]
            if dd>=cfg.max_drawdown: halted=True; halt_reason='max_drawdown'
            elif streak>=cfg.max_consecutive_losses: halted=True; halt_reason='max_consecutive_losses'
        if halted or len(openp)>=cfg.max_positions: continue
        for sym,df in prepared.items():
            if sym in openp or len(openp)>=cfg.max_positions: continue
            m=df.index[df.open_time==ts]
            if len(m)==0: continue
            i=int(m[0]); side=signal(df,i)
            if not side: continue
            av=float(df.iloc[i].atr14); raw=float(df.iloc[i].close); slip=cfg.slippage_bps/10000; entry=raw*(1+slip if side=='LONG' else 1-slip); dist=max(.75*av,entry*.001); qty=(equity*cfg.risk_per_trade)/dist; notional=qty*entry; margin=notional/cfg.leverage_cap
            if notional<cfg.min_notional or margin>=equity: rejected+=1; continue
            stop=entry-dist if side=='LONG' else entry+dist; tp=entry+1.5*dist if side=='LONG' else entry-1.5*dist; openp[sym]={'symbol':sym,'side':side,'entry_time':ts.isoformat(),'entry_ts':int(ts.timestamp()*1000),'entry':entry,'qty':qty,'notional':notional,'stop':stop,'tp':tp}
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); fields=list(trades[0]) if trades else ['symbol','side','entry_time','exit_time','entry','exit','qty','notional','stop','tp','gross_pnl','fees','funding','net_pnl','equity','reason'];
    with out.open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(trades)
    wins=[t for t in trades if t['net_pnl']>0]; losses=[t for t in trades if t['net_pnl']<0]; gw=sum(t['net_pnl'] for t in wins); gl=abs(sum(t['net_pnl'] for t in losses)); summary={'period':{'start':args.start,'end':args.end},'datasets':{s:len(x) for s,x in prepared.items()},'initial_equity':cfg.initial_equity,'ending_equity':equity,'net_pnl':equity-cfg.initial_equity,'return_pct':(equity/cfg.initial_equity-1)*100,'trades':len(trades),'win_rate_pct':100*len(wins)/len(trades) if trades else 0,'profit_factor':gw/gl if gl else None,'fees':sum(t['fees'] for t in trades),'funding':sum(t['funding'] for t in trades),'max_drawdown_pct':maxdd*100,'rejected_min_margin':rejected,'halted':halted,'halt_reason':halt_reason,'risk_config':asdict(cfg),'methodology':'Fail-closed OHLCV baseline; duplicate/gap validation; real cached funding only; unavailable L2/ML history is not fabricated.'}; sp=Path(args.summary); sp.parent.mkdir(parents=True,exist_ok=True); sp.write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
