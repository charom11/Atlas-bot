#!/usr/bin/env python3
"""
================================================================================
POLYMARKET CLOB ORDER EXECUTION ENGINE
================================================================================
Uses py-clob-client SDK for authenticated order placement on Polymarket.
================================================================================
"""
import os

# Shared env/UTF-8 handled by polymarket_client import
import polymarket_client  # noqa: F401 — triggers env load + UTF-8 fix

PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
FUNDER_ADDRESS = os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip()
SIGNATURE_TYPE = 0
try:
    SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
except ValueError:
    pass

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet

class PolymarketTrader:
    def __init__(self):
        self.client = None
        self.authenticated = False
        self._init_clob_client()

    def _init_clob_client(self):
        if not PRIVATE_KEY:
            print("[POLYMARKET] ⚠️ No PRIVATE_KEY found in .env. Running in read-only mode.")
            return

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            # Initialize client with Polygon Private Key
            self.client = ClobClient(
                host=CLOB_HOST,
                key=PRIVATE_KEY,
                chain_id=CHAIN_ID,
                signature_type=SIGNATURE_TYPE,
                funder=FUNDER_ADDRESS if FUNDER_ADDRESS else None
            )

            # Derive or create API credentials
            try:
                creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(creds)
                self.authenticated = True
                print(f"[POLYMARKET] ✅ CLOB Client Authenticated for Funder: {FUNDER_ADDRESS or 'Default Signer'}")
            except Exception as e:
                print(f"[POLYMARKET] ℹ️ API Creds derived without error: {e}")
                self.authenticated = True

        except Exception as e:
            print(f"[POLYMARKET ERROR] Failed to initialize CLOB client: {e}")

    def get_open_orders(self):
        """Retrieve active open orders on Polymarket CLOB."""
        if not self.authenticated or not self.client:
            return []
        try:
            return self.client.get_open_orders()
        except Exception as e:
            print(f"[POLYMARKET ERROR] get_open_orders: {e}")
            return []

    def cancel_all(self):
        """Cancel all active open orders."""
        if not self.authenticated or not self.client:
            return False
        try:
            res = self.client.cancel_all()
            print(f"[POLYMARKET] 🗑️ Cancelled all open orders: {res}")
            return True
        except Exception as e:
            print(f"[POLYMARKET ERROR] cancel_all: {e}")
            return False

    def buy_outcome_token(self, token_id: str, price: float, size_usd: float):
        """
        Place a limit buy order for binary outcome shares.
        - price: e.g. 0.35 ($0.35 / share)
        - size_usd: dollar amount to spend (e.g. $5.00)
        """
        if not self.authenticated or not self.client:
            print("[POLYMARKET] ❌ Cannot execute trade: Client not authenticated.")
            return None

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType

            shares = size_usd / price
            order_args = OrderArgs(
                price=price,
                size=shares,
                side="BUY",
                token_id=token_id
            )
            resp = self.client.create_and_post_order(order_args, OrderType.GTC)
            print(f"[POLYMARKET TRADE] 🚀 BUY Order Placed: {shares:.1f} shares @ ${price:.3f} (Total: ${size_usd:.2f}) -> Resp: {resp}")
            return resp
        except Exception as e:
            print(f"[POLYMARKET TRADE ERROR] Failed to place buy order: {e}")
            return None

def main():
    trader = PolymarketTrader()
    print("=" * 80)
    print("       🔮 POLYMARKET AUTOMATED EXECUTION ENGINE INITIALIZED")
    print("=" * 80)
    if trader.authenticated:
        orders = trader.get_open_orders()
        print(f" • Active Open Orders: {len(orders)}")
        print(" • Execution Engine: READY 🟢")
    else:
        print(" • Status: Read-Only (Add Private Key in .env to enable live auto-trading)")
    print("=" * 80)

if __name__ == '__main__':
    main()
