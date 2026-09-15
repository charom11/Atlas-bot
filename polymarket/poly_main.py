#!/usr/bin/env python3
"""
================================================================================
POLYMARKET PREDICTION SUITE — MASTER ENTRY POINT (poly_main.py)
================================================================================
  python poly_main.py             (Interactive Menu)
  python poly_main.py --paper     (24/7 Autopilot Paper Trading across all sectors)
  python poly_main.py --5m        (BTC 5-Minute Up/Down High-Frequency Scalper)
  python poly_main.py --predict   (Predict +EV Opportunities Across ALL Sectors)
  python poly_main.py --scan      (Browse All Live Markets by Volume)
  python poly_main.py --live      (24/7 Live Trading via Polygon CLOB)
  python poly_main.py --audit     (Wallet & API Health Check)
================================================================================
"""
import os
import sys
import argparse
import time

POLY_DIR = os.path.dirname(os.path.abspath(__file__))
if POLY_DIR not in sys.path:
    sys.path.insert(0, POLY_DIR)

import polymarket_client  # noqa: F401


def run_paper():
    from polymarket_paper_trader import PolymarketPaperTrader
    print("\n" + "=" * 90)
    print(" 🤖 LAUNCHING UNIVERSAL ALL-MARKET PAPER TRADING AUTOPILOT")
    print("=" * 90)
    trader = PolymarketPaperTrader(starting_balance=100.00)
    trader.scan_and_trade()


def run_5m_sniper():
    from btc_5m_sniper import main as sniper_main
    sniper_main()


def run_predict_all():
    from predict_all_markets import predict_all_polymarket
    predict_all_polymarket()


def run_scan():
    from scan_all_live_markets import fetch_top_live_markets
    fetch_top_live_markets()


def run_live():
    from polymarket_autopilot_bot import PolymarketAutopilot, SCAN_INTERVAL_SECONDS
    from polymarket_trader import PolymarketTrader

    trader = PolymarketTrader()
    if not trader.authenticated:
        print("[!] Cannot start LIVE mode: Missing or invalid POLYMARKET_PRIVATE_KEY in .env.")
        return

    print("=" * 90)
    print(" 🚀 LAUNCHING 24/7 POLYMARKET LIVE TRADING AUTOPILOT")
    print(f" Signer Wallet: {trader.client.funder or 'Authenticated'}")
    print("=" * 90)

    bot = PolymarketAutopilot()
    while True:
        try:
            bot.run_cycle()
        except Exception as e:
            print(f"[!] Exception: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


def run_audit():
    from check_polymarket_account import check_polymarket_status
    check_polymarket_status()


def main():
    parser = argparse.ArgumentParser(description="Polymarket Universal Prediction Suite")
    parser.add_argument("--paper", action="store_true", help="Run Universal Paper Trading across all sectors")
    parser.add_argument("--5m", action="store_true", help="Run BTC 5-Minute Up/Down High-Frequency Scalper")
    parser.add_argument("--predict", action="store_true", help="Predict +EV opportunities across all sectors")
    parser.add_argument("--scan", action="store_true", help="Browse all live markets by volume")
    parser.add_argument("--live", action="store_true", help="24/7 Live Trading via CLOB")
    parser.add_argument("--audit", action="store_true", help="Wallet and API health check")
    args = parser.parse_args()

    if args.paper:
        run_paper()
    elif getattr(args, '5m'):
        run_5m_sniper()
    elif args.predict:
        run_predict_all()
    elif args.scan:
        run_scan()
    elif args.live:
        run_live()
    elif args.audit:
        run_audit()
    else:
        # Interactive menu
        print("\n ╔═══════════════════════════════════════════════════════════════════════════╗")
        print(" ║         🌐 POLYMARKET UNIVERSAL OMNI-PREDICTION ENGINE                    ║")
        print(" ║   Predicts: BTC 5M Scalps • Crypto • Politics • Sports • AI • Weather     ║")
        print(" ╚═══════════════════════════════════════════════════════════════════════════╝")
        print(" Select an operation:")
        print("   [1] 🤖 Run Universal Paper Trading (All Sectors — Zero Risk)")
        print("   [2] ⚡ BTC 5-Minute Up/Down High-Frequency Scalper (Sniper)")
        print("   [3] 🌐 Predict +EV Opportunities Across ALL Sectors (Matrix)")
        print("   [4] 📋 Browse All Active Polymarket Contracts by Volume")
        print("   [5] 🚀 Launch 24/7 Live Trading Bot (Polygon CLOB)")
        print("   [6] 💰 Check Wallet Balance & Connection Health")
        print("   [0] ❌ Exit\n")

        choice = input(" Choice [1]: ").strip() or '1'
        {
            '1': run_paper,
            '2': run_5m_sniper,
            '3': run_predict_all,
            '4': run_scan,
            '5': run_live,
            '6': run_audit
        }.get(choice, lambda: print("Exiting."))()


if __name__ == '__main__':
    main()
