#!/usr/bin/env python3
"""
WEATHER-ENSEMBLE BINANCE FUTURES LIVE AI TRADING AGENT + INTERACTIVE TELEGRAM C2
================================================================================
Production Hardened Version:
- 30x Fast Recovery Sizing (20% margin allocation, micro-lot assets)
- L2 Order Book Depth Imbalance Gate (Top-20 Bids vs Asks)
- 8-Hour Funding Rate & Squeeze Filter
- Automated Orphaned Order Garbage Collection (Prevents accidental reverse entries)
- Partial Take-Profit Scaling (50% TP1 @ 1.5x ATR, 50% Trailing Runner)
- 6% Daily Drawdown Circuit Breaker
- Interactive Telegram Inline Keyboard (1-Tap mobile buttons) & C2 Commands
"""

import os
import sys
import time
import math
import json
import random
import hmac
import hashlib
import urllib.parse
import argparse
import threading
from datetime import datetime, timezone
import requests
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# --------------------------------------------------------------------------
# Environment Configuration (.env Loader)
# --------------------------------------------------------------------------
def load_env_file(env_file='.env'):
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

load_env_file()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
TELEGRAM_NOTIFICATIONS = os.getenv('TELEGRAM_NOTIFICATIONS', 'true').lower() == 'true'

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

# Bug #4 Fix: Global ccxt exchange instance (initialized once, reused everywhere)
_CCXT_EXCHANGE = None
def get_ccxt_exchange():
    global _CCXT_EXCHANGE
    if _CCXT_EXCHANGE is None:
        import ccxt
        _CCXT_EXCHANGE = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY', BINANCE_API_KEY),
            'secret': os.getenv('BINANCE_API_SECRET', BINANCE_API_SECRET),
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })
        _CCXT_EXCHANGE.load_time_difference()
    return _CCXT_EXCHANGE

OPTIMIZED_SYMBOLS = [
    # 🏆 Alpha Champions Universe (Proven Institutional Performance & Consistent 30-Day Edge)
    # Heavyweights & Core Trend Leaders:
    "ETHUSDT", "LINKUSDT", "BTCUSDT", "ADAUSDT", "XRPUSDT", "AVAXUSDT", "APTUSDT", "PAXGUSDT"
]

# --------------------------------------------------------------------------
# Circuit Breaker & Risk Protection Manager
# --------------------------------------------------------------------------
