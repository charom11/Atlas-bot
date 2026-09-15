#!/usr/bin/env python3
"""
================================================================================
POLYMARKET ALL LIVE MARKETS DIRECTORY
================================================================================
Queries Polymarket Gamma API across all categories and displays
live active contracts sorted by 24h volume.
================================================================================
"""
import json
from datetime import datetime, timezone
from polymarket_client import PolymarketClient, get_now_utc8_str

CATEGORIES = [
    ("CRYPTO", "crypto"),
    ("POLITICS", "politics"),
    ("WEATHER", "weather"),
    ("GLOBAL", "pop-culture")
]


def fetch_top_live_markets():
    client = PolymarketClient()
    print("=" * 120)
    print(" POLYMARKET ALL LIVE ACTIVE MARKETS")
    print(f" {get_now_utc8_str()}")
    print("=" * 120)

    for cat_title, tag_slug in CATEGORIES:
        events = client.get_events(tag_slug=tag_slug, limit=25)
        if not events:
            events = client.get_events(query=tag_slug, limit=20)

        print(f"\n {cat_title} (by 24h Volume):")
        print(f" {'Question':<56} | {'Outcome':<14} | {'Price':<10} | {'Implied':<13} | {'Volume'}")
        print("-" * 120)

        displayed = 0
        for ev in events:
            title = ev.get('title', '')
            vol = float(ev.get('volume24hr') or ev.get('volume') or 0.0)
            for m in ev.get('markets', []):
                parsed = PolymarketClient.parse_market(m)
                if not parsed:
                    continue
                outcomes, prices, _ = parsed
                q = m.get('question', title)

                # Pick YES outcome if available, else highest prob
                top_idx = 0
                yes_idx = next((i for i, o in enumerate(outcomes) if o.lower() == 'yes'), None)
                if yes_idx is not None and prices[yes_idx] >= 0.03:
                    top_idx = yes_idx
                else:
                    top_idx = prices.index(max(prices))

                top_out = outcomes[top_idx]
                top_p = prices[top_idx]
                if top_p <= 0.005 or top_p >= 0.995:
                    continue

                icon = "🎯" if top_p <= 0.40 else "📊"
                print(f" {icon} {q[:53]:<53} | {top_out[:12]:<14} | ${top_p:<9.3f} | {top_p*100:<12.1f}% | ${vol:,.0f}")
                displayed += 1
                if displayed >= 8:
                    break
            if displayed >= 8:
                break

        if displayed == 0:
            print("   (no active markets)")

    print("\n" + "=" * 120)


if __name__ == '__main__':
    fetch_top_live_markets()
