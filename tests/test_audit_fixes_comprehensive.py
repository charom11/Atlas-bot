import threading
import time
import pytest
import pandas as pd
import numpy as np
import main
from smc_mss_strategy import SmartMoneyStructureEngine

def test_mtf_cache_lock_present_and_safe():
    assert hasattr(main, "_MTF_CACHE_LOCK")
    assert isinstance(main._MTF_CACHE_LOCK, type(threading.Lock()))

def test_sync_server_time_retains_offset_on_failure(monkeypatch):
    # Set known state
    main._SERVER_TIME_OFFSET = 1234
    main._SERVER_TIME_SYNCED = True

    # Inject failure into requests.get
    def mock_failing_get(*args, **kwargs):
        raise ConnectionError("Simulated network timeout")

    monkeypatch.setattr(main.requests, "get", mock_failing_get)
    main.sync_server_time()

    # Offset must be retained, not wiped to 0
    assert main._SERVER_TIME_OFFSET == 1234
    assert main._SERVER_TIME_SYNCED is True

def test_circuit_breaker_drawdown_uses_total_equity():
    cb = main.CircuitBreakerManager(daily_drawdown_limit_pct=0.05, max_consecutive_losses=3)
    cb.daily_start_balance = 1000.0
    
    # If total equity dropped by 2% (from 1000 to 980), should be allowed
    assert cb.check_and_update(980.0) is True
    assert cb.circuit_tripped is False

    # If total equity dropped by 6% (from 1000 to 940), should trip
    assert cb.check_and_update(940.0) is False
    assert cb.circuit_tripped is True
    assert "Daily drawdown hit" in cb.trip_reason

def test_fetch_binance_klines_limit_default_is_250():
    bot = main.WeatherEnsembleBot(consensus_threshold=30, live_trading=False)
    import inspect
    sig = inspect.signature(bot.fetch_binance_klines)
    assert sig.parameters['limit'].default == 250

def test_smc_mss_and_main_fractal_swings_congruence():
    # Test that both engines treat swing points consistently
    highs = [10.0, 12.0, 18.0, 14.0, 11.0, 9.0]
    lows = [8.0, 9.0, 13.0, 10.0, 7.0, 6.0]
    df = pd.DataFrame({'high': highs, 'low': lows})
    
    strat = SmartMoneyStructureEngine()
    smc_sh, smc_sl = strat.identify_swings(df, window=1)
    main_sh, main_sl = main.detect_fractal_swings_series(highs, lows, window=1)
    
    # Both identify peak 18.0 as swing high
    assert any(price == 18.0 for _, price in smc_sh)
    assert any(price == 18.0 for _, price in main_sh)
