#!/usr/bin/env python3
"""
Bridge Module: core.main
========================
Provides backward compatibility by exposing all root `main.py` symbols,
classes, and engines under the `core.main` namespace.
"""

import os
import sys
import importlib.util

# Ensure project root is prioritized on sys.path
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CORE_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_root_main_path = os.path.normpath(os.path.join(_PROJECT_ROOT, 'main.py'))

if 'main' in sys.modules and getattr(sys.modules['main'], '__file__', None) and os.path.normpath(sys.modules['main'].__file__) == _root_main_path:
    _root_main = sys.modules['main']
else:
    spec = importlib.util.spec_from_file_location('main', _root_main_path)
    _root_main = importlib.util.module_from_spec(spec)
    sys.modules['main'] = _root_main
    spec.loader.exec_module(_root_main)

# Re-export all symbols from root main into core.main namespace
for _k, _v in _root_main.__dict__.items():
    if not _k.startswith('__'):
        globals()[_k] = _v

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

if __name__ == '__main__':
    if hasattr(_root_main, 'main'):
        _root_main.main()
