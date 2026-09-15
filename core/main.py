#!/usr/bin/env python3
"""
Bridge Module: core.main
========================
Provides backward compatibility by exposing all root `main.py` symbols,
classes, and engines under the `core.main` namespace.
"""

import os
import sys

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import main
from main import *

# Backward-compatibility exports for archived and experimental modules
try:
    from market_state_ws import MarketStateManager
except ImportError:
    try:
        from archive_candidate_v9_experiments.market_state_ws import MarketStateManager
    except ImportError:
        class MarketStateManager:
            """Fallback placeholder for MarketStateManager."""
            def __init__(self, *args, **kwargs):
                self.ws_connected = False
                self.funding_rates = {}
                self.mark_prices = {}

try:
    from execution_reconciliation import submit_market_order_idempotent
except ImportError:
    try:
        from archive_candidate_v9_experiments.execution_reconciliation import submit_market_order_idempotent
    except ImportError:
        def submit_market_order_idempotent(*args, **kwargs):
            """Fallback placeholder for submit_market_order_idempotent."""
            return None
