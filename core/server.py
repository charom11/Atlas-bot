#!/usr/bin/env python3
"""
WEATHER-ENSEMBLE AI WEB DASHBOARD & BOT REST API SERVER
Serves the Web Dashboard and provides:
- Bot Process Control: /api/start, /api/stop, /api/status
- Live Engine Logs: /api/logs
- Live Binance Futures Positions & Account: /api/positions, /api/close_position, /api/close_all
"""

import os
import sys
import json
import hmac
import subprocess
import urllib.parse
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR_REAL = os.path.realpath(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import Binance helper functions from main bot module
try:
    from main import (
        get_binance_futures_positions,
        get_binance_futures_usdt_balance,
        close_binance_futures_position,
        close_all_binance_futures_positions,
        get_mtf_heatmap_data,
        MILESTONE_MANAGER,
        check_potato_sr_levels,
        get_divergence_status
    )
    from order_flow_engine import OrderFlowEngine
except Exception as e:
    import traceback
    print(f"[SERVER WARNING] Failed to import helpers from main/order_flow_engine: {e}", flush=True)
    traceback.print_exc()
    get_binance_futures_positions = lambda: []
    get_binance_futures_usdt_balance = lambda: 0.0
    close_binance_futures_position = lambda sym: {'error': 'Helper not available'}
    close_all_binance_futures_positions = lambda: []
    get_mtf_heatmap_data = lambda: []
    MILESTONE_MANAGER = None
    check_potato_sr_levels = lambda sym: {'status': 'error'}
    get_divergence_status = lambda sym: {'status': 'error'}
    OrderFlowEngine = None

BOT_PROCESS = None
BOT_LOG_FILE = None
PORT = int(os.getenv('ATLAS_PORT', '8080'))
HOST = os.getenv('ATLAS_BIND_HOST', '127.0.0.1').strip() or '127.0.0.1'
API_TOKEN = os.getenv('ATLAS_API_TOKEN', '').strip()
ALLOWED_ORIGIN = os.getenv('ATLAS_ALLOWED_ORIGIN', '').strip()
LOG_FILE_PATH = os.path.join(PROJECT_DIR, 'bot_output.log')

MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
}

def get_python_executable():
    """Detect virtual environment Python or fallback to current sys.executable."""
    venv_py_win = os.path.join(PROJECT_DIR, '.venv', 'Scripts', 'python.exe')
    venv_py_unix = os.path.join(PROJECT_DIR, '.venv', 'bin', 'python')
    if os.path.exists(venv_py_win):
        return venv_py_win
    if os.path.exists(venv_py_unix):
        return venv_py_unix
    return sys.executable

def is_loopback_host(host):
    return host in ('127.0.0.1', 'localhost', '::1')

def safe_path(root, requested_path):
    """Resolve a requested static path without allowing traversal outside root."""
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, requested_path.lstrip('/')))
    try:
        if os.path.commonpath([root_real, candidate]) != root_real:
            return None
    except ValueError:
        return None
    return candidate

class WebDashboardHandler(BaseHTTPRequestHandler):
    def _api_authorized(self):
        """Protect API access when exposed beyond localhost or when a token is configured."""
        if API_TOKEN:
            supplied = self.headers.get('X-Atlas-API-Key', '')
            return hmac.compare_digest(supplied, API_TOKEN)
        return is_loopback_host(HOST)

    def _api_guard(self):
        if self._api_authorized():
            return True
        self.send_json_response(401, {'status': 'error', 'error': 'Unauthorized'})
        return False

    def _cors_origin(self):
        return ALLOWED_ORIGIN or (f'http://localhost:{PORT}' if is_loopback_host(HOST) else '')

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/') and not self._api_guard():
            return

        if path == '/api/status':
            self.handle_api_status()
            return
        elif path == '/api/logs':
            self.handle_api_logs()
            return
        elif path == '/api/positions':
            self.handle_api_positions()
            return
        elif path == '/api/orderflow':
            self.handle_api_orderflow(parsed)
            return
        elif path == '/api/mtf_heatmap':
            self.handle_api_mtf_heatmap()
            return
        elif path == '/api/milestones':
            self.handle_api_milestones()
            return
        elif path == '/api/potato_sr':
            self.handle_api_potato_sr(parsed)
            return
        elif path == '/api/divergence':
            self.handle_api_divergence(parsed)
            return

        if path in ['/', '']:
            path = '/index.html'

        # Check in frontend/dist first, then web/, fallback to PROJECT_DIR.
        candidate_dist = safe_path(os.path.join(PROJECT_DIR, 'frontend', 'dist'), path)
        candidate_web = safe_path(os.path.join(PROJECT_DIR, 'web'), path)
        candidate_root = safe_path(PROJECT_DIR, path)

        if candidate_dist and os.path.isfile(candidate_dist):
            filepath = candidate_dist
        elif candidate_web and os.path.isfile(candidate_web):
            filepath = candidate_web
        elif candidate_root and os.path.isfile(candidate_root):
            filepath = candidate_root
        else:
            spa_index = safe_path(os.path.join(PROJECT_DIR, 'frontend', 'dist'), '/index.html')
            filepath = spa_index if spa_index and os.path.isfile(spa_index) else candidate_root

        if filepath and os.path.isfile(filepath):
            _, ext = os.path.splitext(filepath)
            mime = MIME_TYPES.get(ext.lower(), 'application/octet-stream')
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
            except OSError as e:
                self.send_error(500, f'Unable to read file: {e}')
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            origin = self._cors_origin()
            if origin:
                self.send_header('Access-Control-Allow-Origin', origin)
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "File Not Found")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self._api_guard():
            return
        if path == '/api/start':
            self.handle_api_start()
        elif path == '/api/stop':
            self.handle_api_stop()
        elif path == '/api/close_position':
            self.handle_api_close_position()
        elif path == '/api/close_all':
            self.handle_api_close_all()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_api_status(self):
        global BOT_PROCESS
        is_running = BOT_PROCESS is not None and BOT_PROCESS.poll() is None
        pid = BOT_PROCESS.pid if is_running else None

        if not is_running:
            try:
                import psutil
                target_main = os.path.realpath(os.path.join(PROJECT_DIR, 'main.py'))
                target_weather = os.path.realpath(os.path.join(PROJECT_DIR, 'weather_ensemble_bot.py'))
                for p in psutil.process_iter(['pid', 'cmdline']):
                    cmd = p.info.get('cmdline') or []
                    for arg in cmd:
                        if not isinstance(arg, str) or not arg:
                            continue
                        try:
                            resolved = os.path.realpath(arg)
                        except OSError:
                            continue
                        if resolved in (target_main, target_weather):
                            is_running = True
                            pid = p.info.get('pid')
                            break
                    if is_running:
                        break
            except Exception:
                pass

        data = {'running': is_running, 'pid': pid}
        self.send_json_response(200, data)

    def handle_api_logs(self):
        lines = []
        if os.path.exists(LOG_FILE_PATH):
            try:
                with open(LOG_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    lines = all_lines[-75:] if len(all_lines) > 75 else all_lines
            except Exception as e:
                lines = [f"Error reading log file: {str(e)}"]
        self.send_json_response(200, {'logs': ''.join(lines)})

    def handle_api_positions(self):
        try:
            positions = get_binance_futures_positions()
            usdt_bal = get_binance_futures_usdt_balance()
            total_unrealized_pnl = sum(float(p.get('unrealizedProfit', 0.0)) for p in positions)
            data = {
                'status': 'success',
                'balance': usdt_bal,
                'total_unrealized_pnl': total_unrealized_pnl,
                'positions_count': len(positions),
                'positions': positions
            }
        except Exception as e:
            data = {
                'status': 'error',
                'balance': 0.0,
                'total_unrealized_pnl': 0.0,
                'positions_count': 0,
                'positions': [],
                'error': str(e)
            }
        self.send_json_response(200, data)

    def handle_api_orderflow(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        symbol = query.get('symbol', ['XRPUSDT'])[0]
        if OrderFlowEngine:
            try:
                engine = OrderFlowEngine(symbol=symbol)
                res = engine.analyze_order_flow()
                self.send_json_response(200, {'status': 'success', 'data': res})
            except Exception as e:
                self.send_json_response(500, {'status': 'error', 'message': str(e)})
        else:
            self.send_json_response(200, {'status': 'error', 'message': 'OrderFlowEngine unavailable'})

    def handle_api_mtf_heatmap(self):
        try:
            data = get_mtf_heatmap_data()
            self.send_json_response(200, {'status': 'success', 'heatmap': data})
        except Exception as e:
            self.send_json_response(200, {'status': 'error', 'error': str(e), 'heatmap': []})

    def handle_api_milestones(self):
        try:
            bal = get_binance_futures_usdt_balance()
            if MILESTONE_MANAGER:
                locked = MILESTONE_MANAGER.update(bal)
                peak = MILESTONE_MANAGER.peak_balance
                next_m = next((m for m in MILESTONE_MANAGER.milestones if m > bal), MILESTONE_MANAGER.milestones[-1])
            else:
                locked, peak, next_m = 0.0, bal, 30.0
            data = {
                'status': 'success',
                'current_balance': bal,
                'peak_balance': peak,
                'locked_milestone': locked,
                'next_milestone': next_m,
                'progress_pct': min(100.0, (bal / next_m) * 100.0) if next_m > 0 else 100.0
            }
        except Exception as e:
            data = {'status': 'error', 'error': str(e)}
        self.send_json_response(200, data)

    def handle_api_potato_sr(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        symbol = query.get('symbol', ['XRPUSDT'])[0]
        data = check_potato_sr_levels(symbol=symbol)
        self.send_json_response(200, data)

    def handle_api_divergence(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        symbol = query.get('symbol', ['XRPUSDT'])[0]
        data = get_divergence_status(symbol=symbol)
        self.send_json_response(200, data)

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            return None
        if content_length < 0 or content_length > 1024 * 1024:
            return None
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
        try:
            data = json.loads(body)
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def handle_api_close_position(self):
        params = self._read_json_body()
        if params is None:
            self.send_json_response(400, {'error': 'Invalid JSON body'})
            return
        symbol = params.get('symbol')
        if not isinstance(symbol, str) or not symbol.strip():
            self.send_json_response(400, {'error': 'Missing symbol parameter'})
            return
        symbol = symbol.strip().upper()
        if len(symbol) > 30 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in symbol):
            self.send_json_response(400, {'error': 'Invalid symbol parameter'})
            return
        res = close_binance_futures_position(symbol)
        self.send_json_response(200, {'status': 'success', 'result': res, 'symbol': symbol})

    def handle_api_close_all(self):
        results = close_all_binance_futures_positions()
        self.send_json_response(200, {'status': 'success', 'message': 'Close all executed', 'closed_positions': results})

    def handle_api_start(self):
        global BOT_PROCESS, BOT_LOG_FILE
        params = self._read_json_body()
        if params is None:
            self.send_json_response(400, {'status': 'error', 'message': 'Invalid JSON body'})
            return

        mode = params.get('sizing_mode', 'margin')
        margin_pct = params.get('margin_pct', 0.03)
        leverage = params.get('leverage', 50)
        threshold = params.get('threshold', 30)
        timeframe = params.get('timeframe', '15m')
        max_positions = params.get('max_positions', 8)
        directional_cap = params.get('directional_cap', 4)

        if BOT_PROCESS is None or BOT_PROCESS.poll() is not None:
            if BOT_LOG_FILE is not None:
                try:
                    BOT_LOG_FILE.close()
                except OSError:
                    pass
                BOT_LOG_FILE = None
            py_exec = get_python_executable()
            cmd = [
                py_exec,
                os.path.join(PROJECT_DIR, 'main.py'),
                '--trade-live',
                '--sizing-mode', str(mode),
                '--margin-pct', str(margin_pct),
                '--leverage', str(leverage),
                '--threshold', str(threshold),
                '--timeframe', str(timeframe),
                '--max-positions', str(max_positions),
                '--directional-cap', str(directional_cap)
            ]
            try:
                BOT_LOG_FILE = open(LOG_FILE_PATH, 'a', encoding='utf-8')
                BOT_LOG_FILE.write(f"\n--- BOT STARTED: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} ---\n")
                BOT_LOG_FILE.flush()
                BOT_PROCESS = subprocess.Popen(cmd, cwd=PROJECT_DIR, stdout=BOT_LOG_FILE, stderr=subprocess.STDOUT)
                res = {'status': 'success', 'message': f'Bot started (PID: {BOT_PROCESS.pid})', 'running': True, 'pid': BOT_PROCESS.pid}
            except Exception as e:
                if BOT_LOG_FILE is not None:
                    try:
                        BOT_LOG_FILE.close()
                    except OSError:
                        pass
                    BOT_LOG_FILE = None
                BOT_PROCESS = None
                res = {'status': 'error', 'message': f'Failed to start bot: {str(e)}', 'running': False}
        else:
            res = {'status': 'already_running', 'message': f'Bot is already running (PID: {BOT_PROCESS.pid})', 'running': True, 'pid': BOT_PROCESS.pid}

        self.send_json_response(200, res)

    def handle_api_stop(self):
        global BOT_PROCESS, BOT_LOG_FILE
        if BOT_PROCESS is not None and BOT_PROCESS.poll() is None:
            BOT_PROCESS.terminate()
            try:
                BOT_PROCESS.wait(timeout=3)
            except subprocess.TimeoutExpired:
                BOT_PROCESS.kill()
                try:
                    BOT_PROCESS.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            BOT_PROCESS = None
            res = {'status': 'success', 'message': 'Bot stopped successfully', 'running': False}
        else:
            BOT_PROCESS = None
            res = {'status': 'not_running', 'message': 'Bot is not running', 'running': False}
        if BOT_LOG_FILE is not None:
            try:
                BOT_LOG_FILE.flush()
                BOT_LOG_FILE.close()
            except OSError:
                pass
            BOT_LOG_FILE = None
        self.send_json_response(200, res)

    def send_json_response(self, code, data):
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            origin = self._cors_origin()
            if origin:
                self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Atlas-API-Key')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self._cors_origin()
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Atlas-API-Key')
        self.end_headers()

if __name__ == '__main__':
    os.chdir(PROJECT_DIR)
    if not is_loopback_host(HOST) and not API_TOKEN:
        raise RuntimeError('ATLAS_API_TOKEN is required when ATLAS_BIND_HOST is not localhost')
    server = ThreadingHTTPServer((HOST, PORT), WebDashboardHandler)
    print('=======================================================')
    print(' WEATHER-ENSEMBLE WEB DASHBOARD & BOT CONTROL SERVER ACTIVE')
    print(f' URL: http://localhost:{PORT}')
    print(f' Bind: {HOST}:{PORT}')
    print(' API Endpoints: /api/start, /api/stop, /api/status, /api/logs, /api/positions, /api/close_position, /api/close_all')
    print(f' Python Interpreter: {get_python_executable()}')
    print('=======================================================')
    server.serve_forever()
