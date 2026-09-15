#!/usr/bin/env python3
"""
================================================================================
🌐 POLYMARKET UNIVERSAL OMNI-MARKET PREDICTOR & +EV MATRIX
================================================================================
Predicts and ranks trading opportunities across ALL Polymarket sectors:
- 📈 Crypto & Fin (BTC, ETH, SOL, Altcoins)
- 🏛️ Politics & Geopolitics (Fed Decisions, Ceasefires, Elections)
- ⚾ Sports & Esports (MLB, UEFA, Tennis WTA/US Open, LoL, CS2)
- 🎬 Pop Culture, Tech & AI (GTA VI, Model Releases, Tweets)
- 🌦️ Weather & Climate (City Daily Highs)
- 💼 Business & Global Pacts
================================================================================
"""
import sys
from datetime import datetime, timezone
from polymarket_client import (
    PolymarketClient, UniversalPredictor, evaluate_btc_bias,
    POLYMARKET_CATEGORIES, get_now_utc8_str
)


def predict_all_polymarket():
    client = PolymarketClient()
    print("=" * 135)
    print(" 🌐 POLYMARKET UNIVERSAL OMNI-MARKET PREDICTION & QUANT MATRIX")
    print(f" Timestamp: {get_now_utc8_str()}")
    print("=" * 135)

    # 1. Fetch live BTC bias for crypto modeling
    btc_eval = evaluate_btc_bias()
    if btc_eval and btc_eval.get('price', 0) > 0:
        print(f" 📊 BTC Reference: ${btc_eval['price']:,.2f} | 15m RSI: {btc_eval['rsi']:.1f} | Bias: {btc_eval['bias']} (Conviction: {btc_eval['signal_strength']}/4)")
        print("-" * 135)

    all_predictions = []

    # 2. Iterate through all categories
    for tag_slug, meta in POLYMARKET_CATEGORIES.items():
        events = client.get_events(tag_slug=tag_slug, limit=25)
        if not events:
            events = client.get_events(query=tag_slug, limit=20)

        for ev in events:
            title = ev.get('title', '')
            volume_24h = float(ev.get('volume24hr') or ev.get('volume') or 0.0)

            for m in ev.get('markets', []):
                parsed = PolymarketClient.parse_market(m)
                if not parsed:
                    continue
                outcomes, prices, tokens = parsed
                question = m.get('question', title)

                for idx, (outcome, price) in enumerate(zip(outcomes, prices)):
                    if price < 0.04 or price > 0.96:
                        continue  # Skip extreme dust

                    # Run Category-Specific Quant Predictor
                    pred = {}
                    if tag_slug == "crypto":
                        pred = UniversalPredictor.evaluate_crypto_contract(question, outcome, price, btc_eval)
                    elif tag_slug in ["politics", "business"]:
                        pred = UniversalPredictor.evaluate_macro_politics(question, outcome, price, outcomes, prices)
                    elif tag_slug == "sports":
                        pred = UniversalPredictor.evaluate_sports_esports(question, outcome, price, outcomes, prices)
                    else:
                        pred = UniversalPredictor.evaluate_bracket_market(question, outcome, price, outcomes, prices)

                    if pred.get('is_recommended', False):
                        all_predictions.append({
                            "category_name": meta['name'],
                            "icon": meta['icon'],
                            "event_title": title,
                            "question": question,
                            "outcome": outcome,
                            "price": price,
                            "implied_pct": price * 100.0,
                            "payout_mult": pred['payout_multiplier'],
                            "conviction": pred['conviction'],
                            "model_type": pred['model_type'],
                            "volume": volume_24h
                        })

    # Sort predictions by Conviction (descending) and Volume (descending)
    all_predictions = sorted(all_predictions, key=lambda x: (x['conviction'], x['volume']), reverse=True)

    print(f"\n {'Sector':<20} | {'Prediction Contract':<50} | {'Pick':<10} | {'Price':<8} | {'Implied':<8} | {'Payout':<8} | {'Conviction':<12} | {'Model Engine'}")
    print("-" * 135)

    displayed = 0
    for p in all_predictions[:25]:
        price_str = f"${p['price']:.3f}"
        imp_str = f"{p['implied_pct']:.1f}%"
        payout_str = f"{p['payout_mult']:.2f}x"
        conv_stars = "★" * p['conviction'] + "☆" * (3 - p['conviction'])
        vol_str = f"${p['volume']:,.0f}"

        print(f" {p['icon']} {p['category_name'][:17]:<17} | {p['question'][:48]:<50} | {p['outcome'][:8]:<10} | {price_str:<8} | {imp_str:<8} | {payout_str:<8} | {conv_stars:<12} | {p['model_type']}")
        displayed += 1

    print("=" * 135)
    print(f" ✨ Displaying top {displayed} asymmetric +EV predictions across ALL Polymarket sectors.")
    print(" 💡 Strategy: Exploit favorable risk/reward ($0.08–$0.38 entries with 2.6x to 12.5x payout multipliers).")
    print("=" * 135)


if __name__ == '__main__':
    predict_all_polymarket()
