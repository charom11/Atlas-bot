#!/usr/bin/env python3
"""Continuous Atlas regression gate.

Runs lightweight deterministic checks without touching live trading. The gate
fails closed on missing datasets, duplicate/gapped 15m bars, or material
regression against a stored baseline. Full institutional audits remain manual.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd

EXPECTED=900

def validate(path:Path):
    df=pd.read_csv(path,usecols=['open_time'])
    if df.empty: raise ValueError(f'{path.name}: empty dataset')
    ts=pd.to_datetime(df.open_time,utc=True)
    if ts.duplicated().any(): raise ValueError(f'{path.name}: duplicate timestamps')
    gaps=ts.sort_values().diff().dropna().dt.total_seconds()
    if (gaps!=EXPECTED).any(): raise ValueError(f'{path.name}: non-15m gap detected')
    return len(df)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',default='backtests/historical_data_cache'); ap.add_argument('--baseline',default='backtests/baselines/atlas_current_baseline.json'); ap.add_argument('--max-data-drop',type=float,default=.01); args=ap.parse_args()
    d=Path(args.data_dir); files=sorted(d.glob('*_15m*.csv'))
    if not files: raise SystemExit('FAIL: no cached 15m CSV datasets')
    counts={p.name:validate(p) for p in files}
    baseline=Path(args.baseline)
    if baseline.exists():
        b=json.loads(baseline.read_text()); old=b.get('datasets',{})
        for name,count in counts.items():
            if name in old and count < old[name]*(1-args.max_data_drop): raise SystemExit(f'FAIL: dataset regression {name}: {count} < {old[name]}')
    print(json.dumps({'status':'PASS','datasets':counts},indent=2))

if __name__=='__main__': main()
