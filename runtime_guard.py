#!/usr/bin/env python3
"""Safety wrapper for Atlas Bot production startup.

The wrapper deliberately defaults to non-live operation. Live trading requires
ATLAS_LIVE_TRADING=true and explicit risk limits supplied through environment
variables. This prevents a Docker restart/deploy from silently enabling live
orders.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid {name}: {raw!r}") from exc


def build_command() -> list[str]:
    live = _bool_env("ATLAS_LIVE_TRADING", False)
    leverage = _float_env("ATLAS_LEVERAGE", 1.0)
    margin_pct = _float_env("ATLAS_MARGIN_PCT", 0.01)
    threshold = _float_env("ATLAS_THRESHOLD", 30.0)
    timeframe = os.getenv("ATLAS_TIMEFRAME", "15m")
    max_positions = int(os.getenv("ATLAS_MAX_POSITIONS", "5"))

    if leverage < 1 or leverage > 125:
        raise SystemExit("ATLAS_LEVERAGE must be between 1 and 125")
    if not 0 < margin_pct <= 1:
        raise SystemExit("ATLAS_MARGIN_PCT must be > 0 and <= 1")
    if max_positions < 1:
        raise SystemExit("ATLAS_MAX_POSITIONS must be >= 1")

    if live:
        if not _bool_env("ATLAS_LIVE_CONFIRM", False):
            raise SystemExit(
                "LIVE TRADING BLOCKED: set ATLAS_LIVE_TRADING=true and "
                "ATLAS_LIVE_CONFIRM=true explicitly."
            )
        if not os.getenv("BINANCE_API_KEY") or not os.getenv("BINANCE_API_SECRET"):
            raise SystemExit("LIVE TRADING BLOCKED: Binance credentials are missing")

    command = [
        sys.executable,
        "main.py",
        "--sizing-mode",
        "margin",
        "--margin-pct",
        str(margin_pct),
        "--leverage",
        str(leverage),
        "--threshold",
        str(threshold),
        "--timeframe",
        timeframe,
        "--max-positions",
        str(max_positions),
    ]
    if live:
        command.append("--trade-live")
    return command


def main() -> int:
    command = build_command()
    mode = "LIVE" if _bool_env("ATLAS_LIVE_TRADING") else "NON-LIVE"
    print(f"[ATLAS SAFETY GUARD] Starting in {mode} mode", flush=True)
    print(f"[ATLAS SAFETY GUARD] Command: {' '.join(command)}", flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
