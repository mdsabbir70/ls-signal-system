"""
Economic Calendar Integration

Fetches real-time economic events from multiple sources and provides:
  - High-impact event detection (NFP, FOMC, ECB, BOE, etc.)
  - Trading session awareness (London, New York, Tokyo, Sydney)
  - Pre-event trade blocking (configurable window)
  - Post-event bias adjustment (actual vs forecast)

Sources:
  - ForexFactory via nfs.faireconomy.media JSON endpoint
  - Fallback: scrape investing.com calendar

Usage:
    calendar = EconomicCalendar(db)
    await calendar.fetch_events()
    gate = calendar.check_gate('EURUSD', minutes_before=30)
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
import json

import requests
from utils.logger import setup_logger

logger = setup_logger('econ_calendar')

# Bangladesh Standard Time
BDT = timezone(timedelta(hours=6))


# ═════════════════════════════════════════════════════════════════════════════
#  CURRENCY → PAIR MAPPING
# ═════════════════════════════════════════════════════════════════════════════

CURRENCY_TO_PAIRS = {
    'USD': ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD',
            'XAUUSD', 'BTCUSDT', 'ETHUSDT'],
    'EUR': ['EURUSD', 'EURJPY', 'EURGBP'],
    'GBP': ['GBPUSD', 'GBPJPY', 'EURGBP'],
    'JPY': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY'],
    'AUD': ['AUDUSD', 'AUDJPY'],
    'CAD': ['USDCAD'],
    'CHF': ['USDCHF'],
    'NZD': ['NZDUSD'],
    'CNY': ['BTCUSDT', 'ETHUSDT'],  # China news affects crypto
}


# ═════════════════════════════════════════════════════════════════════════════
#  TRADING SESSIONS (UTC)
# ═════════════════════════════════════════════════════════════════════════════

SESSIONS = {
    'tokyo':  {'open': 0, 'close': 9,  'pairs': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'AUDUSD']},
    'london': {'open': 7, 'close': 16, 'pairs': ['EURUSD', 'GBPUSD', 'EURGBP', 'USDCHF', 'XAUUSD']},
    'new_york': {'open': 13, 'close': 22, 'pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']},
    'sydney': {'open': 22, 'close': 7,  'pairs': ['AUDUSD', 'NZDUSD', 'AUDJPY']},
}

# Crypto trades 24/7 — all sessions
CRYPTO_PAIRS = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'TONUSDT',
                'DOGEUSDT', 'BNBUSDT', 'PEPEUSDT', 'ADAUSDT', 'HYPEUSDT',
                'LINKUSDT', 'SUIUSDT', 'DOTUSDT'}


# ═════════════════════════════════════════════════════════════════════════════
#  HIGH-IMPACT EVENT KEYWORDS
# ═════════════════════════════════════════════════════════════════════════════

HIGH_IMPACT_KEYWORDS = [
    'Non-Farm', 'NFP', 'Interest Rate', 'Rate Decision',
    'FOMC', 'Fed Chair', 'ECB Press', 'BOE Rate', 'BOJ Rate',
    'CPI', 'GDP', 'Unemployment Rate', 'Retail Sales',
    'PMI', 'Core PCE', 'Federal Funds', 'Monetary Policy',
    'Jackson Hole', 'Inflation Rate',
]


# ═════════════════════════════════════════════════════════════════════════════
#  ECONOMIC CALENDAR
# ═════════════════════════════════════════════════════════════════════════════

class EconomicCalendar:
    """Fetches and manages economic calendar events."""

    URLS = [
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
        'https://nfs.faireconomy.media/ff_calendar_nextweek.json',
    ]
    CACHE_TTL = 1800    # 30 min cache

    def __init__(self, db=None):
        self.db = db
        self._events: List[dict] = []
        self._last_fetch: Optional[datetime] = None

    async def fetch_events(self) -> List[dict]:
        """Fetch this + next week's economic events. Caches for 30 min."""
        now = datetime.now(timezone.utc)
        if (self._last_fetch and
                (now - self._last_fetch).total_seconds() < self.CACHE_TTL and
                self._events):
            return self._events

        try:
            loop = asyncio.get_event_loop()
            events = await loop.run_in_executor(None, self._fetch_ff)
            if events:
                self._events = events
                self._last_fetch = now
                high_count = sum(1 for e in events if e.get('is_high_impact'))
                logger.info(f"Fetched {len(events)} economic events ({high_count} high-impact)")

                # Save to DB if available
                if self.db:
                    await loop.run_in_executor(None, self._save_to_db, events)

                return events
        except Exception as e:
            logger.error(f"Failed to fetch economic calendar: {e}")

        # Fallback: load from DB if API fails and no cache
        if not self._events and self.db:
            try:
                loop = asyncio.get_event_loop()
                db_events = await loop.run_in_executor(None, self._load_from_db)
                if db_events:
                    self._events = db_events
                    logger.info(f"Loaded {len(db_events)} events from DB (API fallback)")
            except Exception as e:
                logger.warning(f"DB fallback load failed: {e}")

        return self._events  # Return cached if fetch fails

    def _fetch_ff(self) -> List[dict]:
        """Fetch from ForexFactory JSON endpoint (this week + next week)."""
        all_events = []
        for url in self.URLS:
            try:
                events = self._fetch_one_url(url)
                all_events.extend(events)
            except Exception as e:
                logger.warning(f"Fetch failed for {url}: {e}")

        # Deduplicate by title + datetime
        seen = set()
        unique = []
        for ev in all_events:
            key = (ev.get('title', ''), str(ev.get('datetime', '')))
            if key not in seen:
                seen.add(key)
                unique.append(ev)

        return unique

    def _fetch_one_url(self, url: str) -> List[dict]:
        """Fetch events from a single ForexFactory JSON URL."""
        try:
            resp = requests.get(
                url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
            )
            resp.raise_for_status()
            raw_events = resp.json()

            events = []
            for ev in raw_events:
                event = {
                    'title': ev.get('title', ''),
                    'country': ev.get('country', ''),
                    'date': ev.get('date', ''),
                    'impact': ev.get('impact', 'Low'),
                    'forecast': ev.get('forecast', ''),
                    'previous': ev.get('previous', ''),
                    'actual': ev.get('actual', ''),
                }

                # Parse date
                try:
                    event['datetime'] = datetime.fromisoformat(
                        event['date'].replace('Z', '+00:00')
                    )
                except (ValueError, AttributeError):
                    event['datetime'] = None

                # Determine currency
                country_map = {
                    'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'JPY': 'JPY',
                    'AUD': 'AUD', 'CAD': 'CAD', 'CHF': 'CHF', 'NZD': 'NZD',
                    'CNY': 'CNY',
                }
                event['currency'] = country_map.get(event['country'], event['country'])

                # Determine if high impact
                impact_str = str(event['impact']).lower()
                is_high = impact_str in ('high', 'holiday')
                if not is_high:
                    is_high = any(kw.lower() in event['title'].lower()
                                 for kw in HIGH_IMPACT_KEYWORDS)
                event['is_high_impact'] = is_high

                # Affected pairs
                event['affected_pairs'] = CURRENCY_TO_PAIRS.get(
                    event['currency'], []
                )

                events.append(event)

            return events

        except Exception as e:
            logger.error(f"ForexFactory fetch error: {e}")
            return []

    def _save_to_db(self, events: List[dict]):
        """Save events to economic_events table."""
        try:
            raw_conn = self.db.engine.raw_connection()
            cursor = raw_conn.cursor()

            for ev in events:
                if not ev.get('datetime'):
                    continue
                cursor.execute(
                    """INSERT INTO economic_events
                       (event_title, currency, event_time, impact_level,
                        forecast_value, previous_value, actual_value,
                        affected_pairs)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                        actual_value = VALUES(actual_value),
                        impact_level = VALUES(impact_level)""",
                    (
                        ev['title'][:200],
                        ev['currency'],
                        ev['datetime'],
                        'high' if ev['is_high_impact'] else ev['impact'].lower(),
                        ev.get('forecast', '')[:50],
                        ev.get('previous', '')[:50],
                        ev.get('actual', '')[:50],
                        json.dumps(ev['affected_pairs']),
                    )
                )
            raw_conn.commit()
            cursor.close()
            raw_conn.close()
        except Exception as e:
            logger.warning(f"Failed to save events to DB: {e}")

    def _load_from_db(self) -> List[dict]:
        """Load upcoming events from DB (fallback when API is down)."""
        try:
            raw_conn = self.db.engine.raw_connection()
            cursor = raw_conn.cursor()
            cursor.execute(
                """SELECT event_title, currency, event_time, impact_level,
                          forecast_value, previous_value, actual_value,
                          affected_pairs
                   FROM economic_events
                   WHERE event_time >= NOW() - INTERVAL 1 HOUR
                   ORDER BY event_time ASC
                   LIMIT 200"""
            )
            rows = cursor.fetchall()
            cursor.close()
            raw_conn.close()

            events = []
            for row in rows:
                title, currency, event_time, impact, forecast, prev, actual, pairs_json = row
                is_high = impact == 'high'
                try:
                    affected = json.loads(pairs_json) if pairs_json else []
                except (json.JSONDecodeError, TypeError):
                    affected = CURRENCY_TO_PAIRS.get(currency, [])

                events.append({
                    'title': title,
                    'currency': currency,
                    'datetime': event_time.replace(tzinfo=timezone.utc) if event_time.tzinfo is None else event_time,
                    'impact': impact,
                    'forecast': forecast or '',
                    'previous': prev or '',
                    'actual': actual or '',
                    'is_high_impact': is_high,
                    'affected_pairs': affected,
                })
            return events
        except Exception as e:
            logger.warning(f"Failed to load events from DB: {e}")
            return []

    # ── Gate Logic ────────────────────────────────────────────────────────

    def check_gate(
        self,
        pair: str,
        minutes_before: int = 30,
        minutes_after: int = 15,
    ) -> Dict:
        """
        Check if trading should be blocked due to upcoming/recent events.

        Returns:
            {
                'action': 'BLOCK' | 'CAUTION' | 'CLEAR',
                'reason': str,
                'event': dict or None,
                'minutes_until': int or None,
            }
        """
        now = datetime.now(timezone.utc)

        for ev in self._events:
            if not ev.get('datetime') or not ev.get('is_high_impact'):
                continue

            # Check if this event affects the pair
            if pair not in ev.get('affected_pairs', []):
                continue

            ev_time = ev['datetime']
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)

            diff = (ev_time - now).total_seconds() / 60  # Minutes until event

            # Event is in the future, within blocking window
            if 0 < diff <= minutes_before:
                return {
                    'action': 'BLOCK',
                    'reason': f"High-impact event in {int(diff)}min: {ev['title']} ({ev['currency']})",
                    'event': ev,
                    'minutes_until': int(diff),
                }

            # Event just happened (within after-window)
            if -minutes_after <= diff <= 0:
                return {
                    'action': 'CAUTION',
                    'reason': f"High-impact event {int(abs(diff))}min ago: {ev['title']}",
                    'event': ev,
                    'minutes_until': int(diff),
                }

            # Event coming within 2 hours — caution
            if 0 < diff <= 120 and ev['is_high_impact']:
                return {
                    'action': 'CAUTION',
                    'reason': f"High-impact event in {int(diff)}min: {ev['title']}",
                    'event': ev,
                    'minutes_until': int(diff),
                }

        return {'action': 'CLEAR', 'reason': '', 'event': None, 'minutes_until': None}

    def get_upcoming(self, hours: int = 24, high_only: bool = True) -> List[dict]:
        """Get upcoming events within N hours."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        result = []

        for ev in self._events:
            if not ev.get('datetime'):
                continue
            ev_time = ev['datetime']
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)
            if now <= ev_time <= cutoff:
                if high_only and not ev.get('is_high_impact'):
                    continue
                result.append(ev)

        return sorted(result, key=lambda e: e['datetime'])

    def get_event_bias(self, pair: str) -> Dict:
        """
        Check recent events for bias — if actual > forecast, that's
        positive for the currency (hawkish/strong).

        Returns:
            {'bias': 'bullish'|'bearish'|'neutral', 'reason': str, 'strength': 0-1}
        """
        now = datetime.now(timezone.utc)
        recent_window = timedelta(hours=4)

        for ev in self._events:
            if not ev.get('datetime') or not ev.get('is_high_impact'):
                continue
            if pair not in ev.get('affected_pairs', []):
                continue

            ev_time = ev['datetime']
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)

            # Only look at events that already happened in the last 4 hours
            if not (now - recent_window <= ev_time <= now):
                continue

            actual = ev.get('actual', '')
            forecast = ev.get('forecast', '')
            if not actual or not forecast:
                continue

            try:
                act_val = float(actual.replace('%', '').replace('K', '000').replace('M', '000000').strip())
                fcast_val = float(forecast.replace('%', '').replace('K', '000').replace('M', '000000').strip())
            except (ValueError, AttributeError):
                continue

            diff_pct = (act_val - fcast_val) / abs(fcast_val) if fcast_val != 0 else 0
            currency = ev['currency']

            # Determine if the pair's base or quote is the event currency
            is_base = pair.startswith(currency)
            is_quote = pair[3:6] == currency if len(pair) >= 6 else False

            if abs(diff_pct) < 0.01:
                continue  # Negligible difference

            if diff_pct > 0:
                # Actual better than forecast = currency strong
                if is_base:
                    return {'bias': 'bullish', 'reason': f"{ev['title']}: actual > forecast ({actual} vs {forecast})", 'strength': min(1.0, abs(diff_pct))}
                elif is_quote:
                    return {'bias': 'bearish', 'reason': f"{ev['title']}: actual > forecast ({actual} vs {forecast})", 'strength': min(1.0, abs(diff_pct))}
            else:
                # Actual worse than forecast = currency weak
                if is_base:
                    return {'bias': 'bearish', 'reason': f"{ev['title']}: actual < forecast ({actual} vs {forecast})", 'strength': min(1.0, abs(diff_pct))}
                elif is_quote:
                    return {'bias': 'bullish', 'reason': f"{ev['title']}: actual < forecast ({actual} vs {forecast})", 'strength': min(1.0, abs(diff_pct))}

        return {'bias': 'neutral', 'reason': '', 'strength': 0.0}

    # ── Session Logic ─────────────────────────────────────────────────────

    @staticmethod
    def get_active_sessions() -> List[str]:
        """Get currently active trading sessions."""
        hour = datetime.now(timezone.utc).hour
        active = []
        for name, sess in SESSIONS.items():
            if sess['open'] < sess['close']:
                if sess['open'] <= hour < sess['close']:
                    active.append(name)
            else:  # Wraps midnight (sydney)
                if hour >= sess['open'] or hour < sess['close']:
                    active.append(name)
        return active

    @staticmethod
    def is_session_optimal(pair: str) -> bool:
        """Check if the current session is optimal for this pair."""
        if pair in CRYPTO_PAIRS:
            return True  # Crypto trades 24/7

        hour = datetime.now(timezone.utc).hour
        for name, sess in SESSIONS.items():
            if pair in sess['pairs']:
                if sess['open'] < sess['close']:
                    if sess['open'] <= hour < sess['close']:
                        return True
                else:
                    if hour >= sess['open'] or hour < sess['close']:
                        return True
        return False

    @staticmethod
    def get_session_info(pair: str) -> Dict:
        """Get session context for a pair."""
        active = EconomicCalendar.get_active_sessions()
        optimal = EconomicCalendar.is_session_optimal(pair)
        hour = datetime.now(timezone.utc).hour

        # London-NY overlap (13:00-16:00 UTC) = highest volatility
        overlap = 13 <= hour < 16

        return {
            'active_sessions': active,
            'is_optimal': optimal,
            'london_ny_overlap': overlap,
            'volatility_expected': 'high' if overlap else ('medium' if active else 'low'),
        }
