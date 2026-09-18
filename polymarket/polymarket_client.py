#!/usr/bin/env python3
"""
================================================================================
POLYMARKET UNIVERSAL QUANTITATIVE CLIENT & PREDICTION ENGINE
================================================================================
Universal multi-category prediction & analytics engine across:
1. 📈 Crypto & Fin (BTC, ETH, SOL, XRP, Altcoins)
2. 🏦 Macro & Economy (Fed Decisions, Interest Rates, CPI, Treasury)
3. 🏛️ Politics & Geopolitics (Elections, Ceasefires, Global Pacts)
4. ⚾ Sports & Esports (MLB, UEFA, Tennis, LoL, CS2)
5. 🎬 Pop Culture, Tech & AI (GTA VI, AI Models, Tweet Brackets)
6. 🌦️ Weather & Climate (City Daily Highs, NOAA Forecasts)
7. 🔬 Science & Innovation (SpaceX Launches, Biotech, Quantum)
================================================================================
"""
import os
import sys
import re
import json
import requests
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# ── Timezone: UTC+8 ──────────────────────────────────────────────────────────
TZ_UTC8 = timezone(timedelta(hours=8))

def get_now_utc8() -> datetime:
    return datetime.now(TZ_UTC8)

def get_now_utc8_str(fmt: str = "%Y-%m-%d %H:%M:%S UTC+8") -> str:
    return datetime.now(TZ_UTC8).strftime(fmt)

# ── One-time UTF-8 fix ──────────────────────────────────────────────────────
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

# ── One-time .env load ──────────────────────────────────────────────────────
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)

# ── Constants ────────────────────────────────────────────────────────────────
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
BINANCE_FUTURES_API = "https://fapi.binance.com"

# Polymarket Categories & Tag Slugs
POLYMARKET_CATEGORIES = {
    "crypto": {"name": "📈 Crypto & DeFi", "icon": "🪙"},
    "politics": {"name": "🏛️ Politics & Macro", "icon": "🗳️"},
    "sports": {"name": "⚾ Sports & Esports", "icon": "🏆"},
    "pop-culture": {"name": "🎬 Pop Culture & AI", "icon": "⚡"},
    "weather": {"name": "🌦️ Weather & Climate", "icon": "🌡️"},
    "business": {"name": "💼 Business & Economy", "icon": "📊"},
    "science": {"name": "🔬 Science & Tech", "icon": "🚀"}
}

_THRESHOLD_RE = re.compile(r'\$?([\d,]+(?:\.\d+)?)\s*k?\b', re.IGNORECASE)


class PolymarketClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Ensemble-Polymarket-Engine/2.5",
            "Accept": "application/json"
        })

    # ── Gamma API Discovery ──────────────────────────────────────────────────

    def get_events(self, tag_slug: str = "crypto", limit: int = 40,
                   query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active events from Gamma API by tag or query."""
        try:
            params = {
                "limit": limit, "active": "true", "closed": "false",
                "order": "volume24hr", "ascending": "false"
            }
            if query:
                params["q"] = query
            else:
                params["tag_slug"] = tag_slug
            res = self.session.get(f"{GAMMA_API_URL}/events", params=params, timeout=6)
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, list) else []
            return []
        except Exception as e:
            return []

    def get_all_active_events(self, per_category_limit: int = 25) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch active events across all Polymarket sectors."""
        all_events = {}
        for tag, meta in POLYMARKET_CATEGORIES.items():
            evs = self.get_events(tag_slug=tag, limit=per_category_limit)
            if not evs:
                evs = self.get_events(query=tag, limit=per_category_limit)
            all_events[tag] = evs
        return all_events

    def get_market_midpoint(self, token_id: str) -> Optional[float]:
        """Get live midpoint price for a token from CLOB."""
        try:
            res = self.session.get(
                f"{CLOB_API_URL}/midpoint",
                params={"token_id": token_id}, timeout=4
            )
            if res.status_code == 200:
                return float(res.json().get("mid", 0.0))
        except Exception:
            pass
        return None

    def get_market_orderbook(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Fetch live L2 orderbook for a specific token."""
        try:
            res = self.session.get(
                f"{CLOB_API_URL}/book",
                params={"token_id": token_id}, timeout=4
            )
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return None

    # ── Market Data Parsing & Normalization ──────────────────────────────────

    @staticmethod
    def parse_market(m: Dict[str, Any]) -> Optional[Tuple[List[str], List[float], List[str]]]:
        """Parse a Gamma market dict into (outcomes, prices, clob_token_ids)."""
        try:
            outcomes_raw = m.get('outcomes', '["Yes", "No"]')
            prices_raw = m.get('outcomePrices', '["0.5", "0.5"]')
            tokens_raw = m.get('clobTokenIds', '[]')

            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            prices_f = [float(p) for p in (json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw)]
            tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else (tokens_raw or [])

            if not outcomes or not prices_f or len(outcomes) != len(prices_f):
                return None
            return outcomes, prices_f, tokens
        except Exception:
            return None


# ── Universal Multi-Category Prediction Algorithms ──────────────────────────

class UniversalPredictor:
    """
    Quantitative prediction & valuation algorithms tailored for each market category.
    """

    @staticmethod
    def evaluate_crypto_contract(question: str, outcome: str, price: float, btc_eval: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crypto: Strike-to-spot distance + 15m/1H technical momentum confirmation.
        """
        threshold = _extract_threshold(question)
        curr_p = btc_eval.get('price', 0.0)
        bias = btc_eval.get('bias', 'NEUTRAL')
        strength = btc_eval.get('signal_strength', 0)

        out_upper = outcome.upper()
        direction = None
        conviction = 0

        if threshold and curr_p > 0:
            if threshold > curr_p:
                direction = 'BULL' if out_upper == 'YES' else 'BEAR'
            elif threshold < curr_p:
                direction = 'BEAR' if out_upper == 'YES' else 'BULL'

        # Score conviction based on technical alignment
        if (direction == 'BULL' and bias == 'BULLISH') or (direction == 'BEAR' and bias == 'BEARISH'):
            conviction = strength
        elif direction is None and strength >= 3:
            conviction = 2  # Generic crypto momentum

        is_ev = conviction >= 3 and (0.05 <= price <= 0.40)
        return {
            "category": "crypto",
            "direction": direction or bias,
            "conviction": conviction,
            "is_recommended": is_ev,
            "model_type": "Technical Trend & Strike Matrix",
            "payout_multiplier": (1.0 / price) if price > 0 else 0.0
        }

    @staticmethod
    def evaluate_macro_politics(question: str, outcome: str, price: float, all_outcomes: List[str], all_prices: List[float]) -> Dict[str, Any]:
        """
        Macro / Politics / Elections / Fed:
        - Multi-outcome probability sum check (Dutch-book / Over-round detection)
        - Favorite-Longshot Asymmetric mispricings (Underdogs between $0.15 - $0.35 with high volume)
        """
        total_market_prob = sum(all_prices)
        # Normalized true fair value probability
        fair_prob = (price / total_market_prob) if total_market_prob > 0 else price
        edge_spread = fair_prob - price

        # In Fed / Elections, binary contracts near 50/50 with >$1M volume represent crowd consensus
        conviction = 0
        if 0.10 <= price <= 0.35:
            # Asymmetric underdog value
            conviction = 3 if total_market_prob > 1.02 else 2
        elif 0.45 <= price <= 0.55:
            # Toss-up coinflip
            conviction = 1
        elif price >= 0.85:
            # High-certainty favorite
            conviction = 3

        is_ev = (0.08 <= price <= 0.38) and (conviction >= 2)
        return {
            "category": "politics/macro",
            "direction": outcome,
            "conviction": conviction,
            "is_recommended": is_ev,
            "model_type": "Multi-Outcome Sum & Asymmetric Odds",
            "payout_multiplier": (1.0 / price) if price > 0 else 0.0
        }

    @staticmethod
    def evaluate_sports_esports(question: str, outcome: str, price: float, all_outcomes: List[str], all_prices: List[float]) -> Dict[str, Any]:
        """
        Sports (MLB, Tennis, UEFA) & Esports (LoL, CS2):
        - Compares two-way moneyline probabilities
        - Identifies value on live matches and tournament favorites
        """
        is_two_way = len(all_outcomes) == 2
        conviction = 0
        direction = outcome

        if is_two_way and len(all_prices) == 2:
            p1, p2 = all_prices[0], all_prices[1]
            diff = abs(p1 - p2)
            if diff > 0.30:
                # Strong favorite vs underdog match
                if price <= 0.35:
                    conviction = 3  # High-upside underdog
                elif price >= 0.70:
                    conviction = 3  # Strong favorite lock
            else:
                conviction = 1  # Close match
        else:
            # Tournament winner outrights (e.g. US Open, Champions League)
            if 0.15 <= price <= 0.35:
                conviction = 3

        is_ev = (0.10 <= price <= 0.38) and conviction >= 2
        return {
            "category": "sports/esports",
            "direction": direction,
            "conviction": conviction,
            "is_recommended": is_ev,
            "model_type": "Moneyline & Underdog Distribution",
            "payout_multiplier": (1.0 / price) if price > 0 else 0.0
        }

    @staticmethod
    def evaluate_bracket_market(question: str, outcome: str, price: float, all_outcomes: List[str], all_prices: List[float]) -> Dict[str, Any]:
        """
        Pop Culture, Tech Brackets & Weather (GTA VI views, Tweet counts, City Daily Temperatures):
        - Models continuous distribution across bracket intervals
        - Flags mispriced tail brackets (< $0.25)
        """
        num_brackets = len(all_outcomes)
        conviction = 0

        if num_brackets >= 3:
            # Multi-bracket distribution
            max_p = max(all_prices) if all_prices else 0.5
            if price == max_p and price > 0.40:
                conviction = 3  # Mode of distribution (highest expected bracket)
            elif 0.08 <= price <= 0.30:
                conviction = 2  # Tail bracket with asymmetric upside
        else:
            if 0.08 <= price <= 0.35:
                conviction = 2

        is_ev = (0.06 <= price <= 0.35) and conviction >= 2
        return {
            "category": "brackets/culture/weather",
            "direction": outcome,
            "conviction": conviction,
            "is_recommended": is_ev,
            "model_type": "Continuous Bracket Bell-Curve",
            "payout_multiplier": (1.0 / price) if price > 0 else 0.0
        }


def _extract_threshold(question: str) -> Optional[float]:
    """Extract dollar threshold from question text."""
    matches = _THRESHOLD_RE.findall(question)
    if not matches:
        return None
    candidates = []
    for m in matches:
        try:
            val = float(m.replace(',', ''))
            idx = question.find(m)
            if idx >= 0:
                after = question[idx + len(m):idx + len(m) + 2].strip().lower()
                if after.startswith('k'):
                    val *= 1000
            if val > 1000:
                candidates.append(val)
        except ValueError:
            continue
    return max(candidates) if candidates else None


# ── BTC Quantitative Bias Evaluator ─────────────────────────────────────────

def evaluate_btc_bias() -> Optional[Dict[str, Any]]:
    """Evaluate BTC market structure from Binance Futures data."""
    try:
        r15 = requests.get(
            f"{BINANCE_FUTURES_API}/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "15m", "limit": 100}, timeout=4
        ).json()
        df15 = pd.DataFrame(r15, columns=['ot', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 't', 'tb_b', 'tb_q', 'i'])
        for col in ['o', 'h', 'l', 'c', 'v']: df15[col] = df15[col].astype(float)

        r1h = requests.get(
            f"{BINANCE_FUTURES_API}/fapi/v1/klines",
            params={"symbol": "BTCUSDT", "interval": "1h", "limit": 100}, timeout=4
        ).json()
        df1h = pd.DataFrame(r1h, columns=['ot', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 't', 'tb_b', 'tb_q', 'i'])
        for col in ['o', 'h', 'l', 'c', 'v']: df1h[col] = df1h[col].astype(float)

        c15, h15, l15 = df15['c'].values, df15['h'].values, df15['l'].values
        c1h = df1h['c'].values
        curr_p = c15[-1]

        e20_1h = pd.Series(c1h).ewm(span=20).mean().iloc[-1]
        e50_1h = pd.Series(c1h).ewm(span=50).mean().iloc[-1]
        e20_4h = pd.Series(c1h).ewm(span=80).mean().iloc[-1]
        e50_4h = pd.Series(c1h).ewm(span=200).mean().iloc[-1]

        bull_signals = 0; bear_signals = 0
        if c1h[-1] > e50_1h and e20_1h >= e50_1h: bull_signals += 1
        elif c1h[-1] < e50_1h and e20_1h <= e50_1h: bear_signals += 1

        if c1h[-1] > e50_4h and e20_4h >= e50_4h: bull_signals += 1
        elif c1h[-1] < e50_4h and e20_4h <= e50_4h: bear_signals += 1

        d15 = pd.Series(c15).diff()
        g = d15.where(d15 > 0, 0.0).rolling(14).mean()
        lo = (-d15.where(d15 < 0, 0.0)).rolling(14).mean()
        rsi15 = (100.0 - (100.0 / (1.0 + g / (lo + 1e-9)))).iloc[-1]
        if rsi15 > 55: bull_signals += 1
        elif rsi15 < 45: bear_signals += 1

        if curr_p > e20_1h: bull_signals += 1
        elif curr_p < e20_1h: bear_signals += 1

        bias = "BULLISH" if bull_signals >= 3 else ("BEARISH" if bear_signals >= 3 else "NEUTRAL")
        return {
            "price": curr_p, "rsi": rsi15, "bias": bias,
            "signal_strength": max(bull_signals, bear_signals),
            "bull_signals": bull_signals, "bear_signals": bear_signals
        }
    except Exception:
        return {"price": 0.0, "rsi": 50.0, "bias": "NEUTRAL", "signal_strength": 0}


# ── Resolution Detection ────────────────────────────────────────────────────

def check_market_resolved(market_id: str) -> Optional[Dict[str, Any]]:
    """Check if a Polymarket contract has resolved via Gamma API."""
    try:
        res = requests.get(f"{GAMMA_API_URL}/markets/{market_id}", timeout=4)
        if res.status_code == 200:
            data = res.json()
            is_resolved = data.get('closed', False) or data.get('resolved', False)
            if is_resolved:
                prices = data.get('outcomePrices', '["0.5","0.5"]')
                if isinstance(prices, str): prices = json.loads(prices)
                outcomes = data.get('outcomes', '["Yes","No"]')
                if isinstance(outcomes, str): outcomes = json.loads(outcomes)

                winner = None
                for out, p in zip(outcomes, [float(x) for x in prices]):
                    if p >= 0.99:
                        winner = out
                        break

                return {'resolved': True, 'winner': winner, 'prices': [float(x) for x in prices]}
            return {'resolved': False, 'winner': None, 'prices': None}
    except Exception:
        pass
    return None
