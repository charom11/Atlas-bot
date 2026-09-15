#!/usr/bin/env python3
"""
================================================================================
POLYMARKET PREDICTION SUITE — ENTRY POINT
================================================================================
  python main.py             (Interactive Menu)
  python main.py --paper     (24/7 Autopilot Paper Trading)
  python main.py --live      (24/7 Live Trading via CLOB)
  python main.py --scan      (Scan All Live Markets)
  python main.py --audit     (Wallet & API Health Check)
================================================================================
"""
import argparse
import time

# Shared env/UTF-8 handled by polymarket_client import
import polymarket_client  # noqa: F401


def run_paper():
    from polymarket_autopilot_bot import main as autopilot_main
    autopilot_main()


def run_live():
    from polymarket_autopilot_bot import PolymarketAutopilot, SCAN_INTERVAL_SECONDS
    from polymarket_trader import PolymarketTrader

    trader = PolymarketTrader()
    if not trader.authenticated:
        print("[!] Cannot start LIVE mode: Missing POLYMARKET_PRIVATE_KEY in .env.")
        return

    print("=" * 80)
    print(" POLYMARKET LIVE TRADING AUTOPILOT")
    print(f" Wallet: {trader.client.funder or 'Authenticated'}")
    print("=" * 80)

    bot = PolymarketAutopilot()
    while True:
        try:
            bot.run_cycle()
        except Exception as e:
            print(f"[!] Exception: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


def run_scan():
    from scan_all_live_markets import fetch_top_live_markets
    fetch_top_live_markets()


def run_audit():
    from check_polymarket_account import check_polymarket_status
    check_polymarket_status()


def main():
    parser = argparse.ArgumentParser(description="Polymarket Prediction Suite")
    parser.add_argument("--paper", action="store_true", help="24/7 Paper Trading")
    parser.add_argument("--live", action="store_true", help="24/7 Live Trading")
    parser.add_argument("--scan", action="store_true", help="Scan all live markets")
    parser.add_argument("--audit", action="store_true", help="Wallet health check")
    args = parser.parse_args()

    if args.paper:
        run_paper()
    elif args.live:
        run_live()
    elif args.scan:
        run_scan()
    elif args.audit:
        run_audit()
    else:
        # Interactive menu
        print("\n Polymarket Prediction Suite")
        print("  [1] Paper Trading Autopilot (24/7)")
        print("  [2] Live Trading Autopilot (24/7)")
        print("  [3] Scan All Live Markets")
        print("  [4] Wallet & API Check")
        print("  [0] Exit\n")

        choice = input(" Choice [1]: ").strip() or '1'
        {'1': run_paper, '2': run_live, '3': run_scan, '4': run_audit}.get(choice, lambda: print("Exiting."))()


if __name__ == '__main__':
    main()
