# 🔮 Polymarket Prediction Market Quantitative Suite

An institutional prediction market quantitative trading engine for **Polymarket** (Polygon network USDC collateralized Central Limit Order Book).

---

## 🏛️ Why Polymarket Over Traditional Perpetuals

1. **Zero Liquidation Risk**:
   * On Polymarket, contracts trade between **`$0.00` and `$1.00`**.
   * Max loss is strictly capped at what you pay for the share. No 1-minute liquidation stop-hunts.
2. **Fixed Asymmetric Payouts (2x to 10x ROI)**:
   * Buying an undervalued contract for **`$0.20`** pays out **`$1.00`** upon YES resolution (**`5.00x Payout / +400% ROI`**).
3. **No Funding Rate Bleed**:
   * Holding contracts for days/weeks incurs **zero funding rate fees**.
4. **Emotional Retail Inefficiency**:
   * Polymarket participants are primarily retail bettors rather than HFT arbitrage algorithms, creating massive probability mispricings.

---

## 📁 Architecture

* **[`polymarket_client.py`](file:///d:/Bot2/polymarket/polymarket_client.py)**: Low-latency REST client for Polymarket Gamma API and CLOB L2 Order Books.
* **[`polymarket_scanner.py`](file:///d:/Bot2/polymarket/polymarket_scanner.py)**: Real-time probability scanner that identifies high-volume +EV mispricings across crypto and weather markets.

---

## 🚀 How to Run

To scan live Polymarket contracts:
```powershell
& "d:\Bot2\.venv\Scripts\python.exe" "d:\Bot2\polymarket\polymarket_scanner.py"
```
