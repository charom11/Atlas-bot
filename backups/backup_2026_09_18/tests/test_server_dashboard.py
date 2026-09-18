import os
import sys
import subprocess
import pytest
from unittest.mock import MagicMock
import server
import core.server
import core.main

def test_servers_and_core_main_import_cleanly():
    """Verify that both root server, core.server, and core.main import cleanly with correct paths."""
    assert os.path.exists(server.PROJECT_DIR)
    assert os.path.exists(core.server.PROJECT_DIR)
    assert os.path.samefile(server.PROJECT_DIR, core.server.PROJECT_DIR)
    assert hasattr(core.main, 'get_binance_futures_positions')
    assert hasattr(core.main, 'place_binance_futures_tp_sl')
    assert hasattr(core.main, 'WeatherEnsembleBot')

def test_safe_path_traversal_prevention(tmp_path):
    """Verify safe_path allows safe relative paths and blocks directory traversal attempts."""
    root = str(tmp_path)
    safe_file = tmp_path / "valid.txt"
    safe_file.write_text("ok", encoding="utf-8")

    # Valid path inside root
    resolved = server.safe_path(root, "valid.txt")
    assert resolved is not None
    assert os.path.samefile(resolved, str(safe_file))

    # Path traversal attempts
    assert server.safe_path(root, "../secret.txt") is None
    assert server.safe_path(root, "../../boot.ini") is None
    assert server.safe_path(root, "/../../windows/system.ini") is None

def test_api_guard_authorization_logic(monkeypatch):
    """Test _api_authorized logic under loopback and token scenarios."""
    handler = server.WebDashboardHandler.__new__(server.WebDashboardHandler)
    handler.headers = {}

    # Loopback with no token -> authorized
    monkeypatch.setattr(server, 'API_TOKEN', '')
    monkeypatch.setattr(server, 'HOST', '127.0.0.1')
    assert handler._api_authorized() is True

    # Non-loopback with no token -> unauthorized
    monkeypatch.setattr(server, 'HOST', '0.0.0.0')
    assert handler._api_authorized() is False

    # Token configured -> requires valid X-Atlas-API-Key
    monkeypatch.setattr(server, 'API_TOKEN', 'secret123')
    handler.headers = {'X-Atlas-API-Key': 'wrong'}
    assert handler._api_authorized() is False

    handler.headers = {'X-Atlas-API-Key': 'secret123'}
    assert handler._api_authorized() is True

def test_read_json_body_validation():
    """Test body parsing and payload size limits."""
    handler = server.WebDashboardHandler.__new__(server.WebDashboardHandler)

    # Exceeding size limit (1MB)
    handler.headers = {'Content-Length': str(1024 * 1024 + 10)}
    assert handler._read_json_body() is None

    # Invalid JSON
    handler.headers = {'Content-Length': '10'}
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = b'not a json'
    assert handler._read_json_body() is None

    # Valid JSON dict
    handler.headers = {'Content-Length': '16'}
    handler.rfile.read.return_value = b'{"symbol":"BTC"}'
    assert handler._read_json_body() == {"symbol": "BTC"}

    # JSON array instead of dict -> should return None
    handler.headers = {'Content-Length': '7'}
    handler.rfile.read.return_value = b'[1,2,3]'
    assert handler._read_json_body() is None

def test_core_main_cli_execution():
    """Verify that core/main.py delegates to root main when executed as a script."""
    py_exec = sys.executable
    cmd = [py_exec, os.path.join(core.server.PROJECT_DIR, 'core', 'main.py'), '--help']
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert "Weather-Ensemble 31-Model Trading AI Bot" in proc.stdout
