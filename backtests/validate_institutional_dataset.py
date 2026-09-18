#!/usr/bin/env python3
"""Fail-closed validation for Atlas 15m OHLCV and funding datasets."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT","AVAXUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","NEARUSDT","BNBUSDT","SUIUSDT"]
STEP_MS = 15 * 60 * 1000


def validate_ohlcv(path: Path) -> dict:
    rows = []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            rows.append(int(float(r["open_time"])))
    if not rows:
        raise ValueError(f"{path.name}: empty dataset")
    if rows != sorted(rows):
        raise ValueError(f"{path.name}: timestamps are not ordered")
    duplicates = len(rows) - len(set(rows))
    if duplicates:
        raise ValueError(f"{path.name}: {duplicates} duplicate timestamps")
    gaps = [b-a for a,b in zip(rows, rows[1:]) if b-a != STEP_MS]
    if gaps:
        raise ValueError(f"{path.name}: {len(gaps)} non-15m intervals detected")
    return {"rows": len(rows), "start_ms": rows[0], "end_ms": rows[-1], "gaps": 0}


def validate_funding(path: Path) -> dict:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames or []
        t = "fundingTime" if "fundingTime" in names else "timestamp" if "timestamp" in names else None
        r = "fundingRate" if "fundingRate" in names else "rate" if "rate" in names else None
        if not t or not r:
            raise ValueError(f"{path.name}: missing funding timestamp/rate columns")
        rows = list(reader)
    times = [int(float(x[t])) for x in rows]
    if times != sorted(times):
        raise ValueError(f"{path.name}: funding timestamps are not ordered")
    if len(times) != len(set(times)):
        raise ValueError(f"{path.name}: duplicate funding timestamps")
    return {"rows": len(rows), "start_ms": times[0] if times else None, "end_ms": times[-1] if times else None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="backtests/historical_data_cache")
    p.add_argument("--funding-dir", default="backtests/historical_data_cache/funding")
    p.add_argument("--require-funding", action="store_true")
    p.add_argument("--output", default="backtests/reports/dataset_validation.json")
    args = p.parse_args()
    data_dir, funding_dir = Path(args.data_dir), Path(args.funding_dir)
    report = {"symbols": {}, "funding": {}, "valid": True, "errors": []}
    for symbol in SYMBOLS:
        files = sorted(data_dir.glob(f"{symbol}_15m*.csv"))
        if not files:
            report["errors"].append(f"Missing OHLCV dataset: {symbol}")
            continue
        try:
            report["symbols"][symbol] = validate_ohlcv(files[0])
        except Exception as e:
            report["errors"].append(str(e))
        fp = funding_dir / f"{symbol}_funding.csv"
        if not fp.exists():
            if args.require_funding:
                report["errors"].append(f"Missing funding dataset: {symbol}")
            continue
        try:
            report["funding"][symbol] = validate_funding(fp)
        except Exception as e:
            report["errors"].append(str(e))
    report["valid"] = not report["errors"]
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
