import os

import pytest

import runtime_guard


def test_default_is_non_live(monkeypatch):
    monkeypatch.delenv("ATLAS_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ATLAS_LIVE_CONFIRM", raising=False)
    command = runtime_guard.build_command()
    assert "--trade-live" not in command
    assert command[:2] == [runtime_guard.sys.executable, "main.py"]


def test_live_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setenv("ATLAS_LIVE_TRADING", "true")
    monkeypatch.delenv("ATLAS_LIVE_CONFIRM", raising=False)
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret")
    with pytest.raises(SystemExit, match="LIVE TRADING BLOCKED"):
        runtime_guard.build_command()


def test_live_requires_credentials(monkeypatch):
    monkeypatch.setenv("ATLAS_LIVE_TRADING", "true")
    monkeypatch.setenv("ATLAS_LIVE_CONFIRM", "true")
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(SystemExit, match="credentials are missing"):
        runtime_guard.build_command()


def test_invalid_leverage_is_rejected(monkeypatch):
    monkeypatch.setenv("ATLAS_LEVERAGE", "126")
    with pytest.raises(SystemExit, match="ATLAS_LEVERAGE"):
        runtime_guard.build_command()


def test_explicit_live_mode_adds_trade_live(monkeypatch):
    monkeypatch.setenv("ATLAS_LIVE_TRADING", "true")
    monkeypatch.setenv("ATLAS_LIVE_CONFIRM", "true")
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret")
    monkeypatch.setenv("ATLAS_LEVERAGE", "3")
    command = runtime_guard.build_command()
    assert "--trade-live" in command
    assert command[command.index("--leverage") + 1] == "3.0"
