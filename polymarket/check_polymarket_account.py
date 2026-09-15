#!/usr/bin/env python3
"""
================================================================================
POLYMARKET ACCOUNT & WALLET BALANCE CHECKER
================================================================================
Tests Polymarket / Polygon wallet connection and USDC balance.
================================================================================
"""
import os
import requests

# Shared env/UTF-8 handled by polymarket_client import
import polymarket_client  # noqa: F401

PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
FUNDER_ADDRESS = os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip()

# Polygon RPC endpoint for USDC balance checking
POLYGON_RPC = "https://polygon-rpc.com"
USDC_E_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # Bridged USDC.e (Polymarket collateral)
NATIVE_USDC_CONTRACT = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # Native USDC

def check_polymarket_status():
    print("=" * 80)
    print("        🔮 POLYMARKET WALLET & API CONNECTION TEST")
    print("=" * 80)

    if not FUNDER_ADDRESS and not PRIVATE_KEY:
        print(" [!] Missing Polymarket credentials in .env file.")
        print(" 📌 Please open your .env file and fill in:")
        print("    POLYMARKET_PRIVATE_KEY=0x...")
        print("    POLYMARKET_FUNDER_ADDRESS=0x...\n")
        return

    wallet_addr = FUNDER_ADDRESS
    if not wallet_addr and PRIVATE_KEY:
        try:
            from eth_account import Account
            account = Account.from_key(PRIVATE_KEY)
            wallet_addr = account.address
        except Exception:
            wallet_addr = "Derived from Private Key"

    print(f" • Wallet Public Address: {wallet_addr}")
    print(f" • Private Key Configured: {'✅ YES (Securely loaded)' if PRIVATE_KEY else '❌ NO'}")

    # Check USDC balance on Polygon via Public RPC
    try:
        data_payload = "0x70a08231000000000000000000000000" + wallet_addr.replace("0x", "").lower().zfill(40)
        
        # Check USDC.e
        req = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": USDC_E_CONTRACT, "data": data_payload}, "latest"],
            "id": 1
        }
        res = requests.post(POLYGON_RPC, json=req, timeout=5).json()
        raw_bal = int(res.get("result", "0x0"), 16)
        usdc_e_bal = raw_bal / 1e6

        # Check POL/MATIC for gas
        req_gas = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [wallet_addr, "latest"],
            "id": 2
        }
        res_gas = requests.post(POLYGON_RPC, json=req_gas, timeout=5).json()
        raw_gas = int(res_gas.get("result", "0x0"), 16)
        pol_bal = raw_gas / 1e18

        print("-" * 80)
        print(" 💰 POLYGON ON-CHAIN BALANCES:")
        print(f"   • Polymarket Collateral (USDC.e): ${usdc_e_bal:,.4f} USDC")
        print(f"   • Polygon Gas Token (POL/MATIC):   {pol_bal:,.4f} POL")
        print("-" * 80)

        if usdc_e_bal > 0:
            print(" ✅ Ready for automated prediction trading on Polymarket!")
        else:
            print(" ℹ️ Deposit USDC.e to your Polygon wallet address above to start placing prediction bets.")

    except Exception as e:
        print(f" [!] Error querying on-chain balance: {e}")

    print("=" * 80)

if __name__ == '__main__':
    check_polymarket_status()
