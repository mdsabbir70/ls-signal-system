"""
Economic Calendar — Multi-Source

Sources (priority order):
  1. Finnhub /calendar/economic — free, real-time, round-robin keys
  2. ForexFactory thisweek JSON — free, works (nextweek sometimes 404s)
  3. DB cache — fallback if all APIs fail

Data saved to economic_events table every fetch.
Cache TTL: 30 minutes in memory.
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
import requests

from utils.logger import setup_logger

logger = setup_logger('econ_calendar')

BDT = timezone(timedelta(hours=6))

# ── Currency / Pair mapping ──────────────────────────────────────────────────

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
    'CNY': ['BTCUSDT', 'ETHUSDT'],
}

# Finnhub country code → currency mapping
COUNTRY_TO_CURRENCY = {
    'US': 'USD', 'EU': 'EUR', 'DE': 'EUR', 'FR': 'EUR', 'IT': 'EUR',
    'ES': 'EUR', 'PT': 'EUR', 'NL': 'EUR', 'BE': 'EUR', 'AT': 'EUR',
    'FI': 'EUR', 'GR': 'EUR', 'IE': 'EUR', 'LU': 'EUR', 'SK': 'EUR',
    'GB': 'GBP', 'UK': 'GBP',
    'JP': 'JPY',
    'AU': 'AUD',
    'CA': 'CAD',
    'CH': 'CHF',
    'NZ': 'NZD',
    'CN': 'CNY',
}

# ForexFactory country field → currency
FF_COUNTRY_CURRENCY = {
    'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'JPY': 'JPY',
    'AUD': 'AUD', 'CAD': 'CAD', 'CHF': 'CHF', 'NZD': 'NZD', 'CNY': 'CNY',
}

HIGH_IMPACT_KEYWORDS = [
    'Non-Farm', 'NFP', 'Non Farm', 'Payroll',
    'Interest Rate', 'Rate Decision',
    'FOMC', 'Fed Chair', 'Federal Funds',
    'ECB Press', 'ECB Rate',
    'BOE Rate', 'BOJ Rate',
    'CPI', 'Core CPI', 'Inflation Rate',
    'GDP', 'Gross Domestic',
    'Unemployment Rate',
    'Retail Sales',
    'PMI',
    'Core PCE',
    'Monetary Policy',
    'Jackson Hole',
    'Balance of Trade', 'Trade Balance',
    'Michigan Consumer',
]

SESSIONS = {
    'tokyo':    {'open': 0,  'close': 9,  'pairs': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'AUDUSD']},
    'london':   {'open': 7,  'close': 16, 'pairs': ['EURUSD', 'GBPUSD', 'EURGBP', 'USDCHF', 'XAUUSD']},
    'new_york': {'open': 13, 'close': 22, 'pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']},
    'sydney':   {'open': 22, 'close': 7,  'pairs': ['AUDUSD', 'NZDUSD', 'AUDJPY']},
}

CRYPTO_PAIRS = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'TONUSDT',
                'DOGEUSDT', 'BNBUSDT', 'PEPEUSDT', 'ADAUSDT', 'HYPEUSDT',
                'LINKUSDT', 'SUIUSDT', 'DOTUSDT'}


class EconomicCalendar:
    """Fetches and manages economic calendar events."""

    CACHE_TTL = 1800  # 30 minutes

    def __init__(self, db=None):
        self.db = db
        self._events: List[dict] = []
        self._last_fetch: Optional[datetime] = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def fetch_events(self) -> List[dict]:
        """Fetch events. Cache 30 min. Sources: Finnhub → ForexFactory → DB."""
        now = datetime.now(timezone.utc)
        if (self._last_fetch and
                (now - self._last_fetch).total_seconds() < self.CACHE_TTL and
                self._events):
            return self._events

        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(None, self._fetch_all)

        if events:
            self._events = events
            self._last_fetch = now
            high = sum(1 for e in events if e.get('is_high_impact'))
            logger.info(f"Economic calendar: {len(events)} events ({high} high-impact)")
            if self.db:
                await loop.run_in_executor(None, self._save_to_db, events)
        else:
            # All APIs failed — load from DB
            db_events = await loop.run_in_executor(None, self._load_from_db)
            if db_events:
                self._events = db_events
                logger.info(f"Calendar: loaded {len(db_events)} events from DB (API fallback)")

        return self._events

    # ── Fetch Sources ─────────────────────────────────────────────────────────

    def _fetch_all(self) -> List[dict]:
        """Try sources in order: Finnhub → ForexFactory."""
        # Source 1: Finnhub
        events = self._fetch_finnhub()
        if len(events) >= 5:
            return events

        # Source 2: ForexFactory thisweek
        logger.info("Finnhub calendar failed/empty, trying ForexFactory...")
        events = self._fetch_forexfactory()
        if events:
            return events

        logger.warning("All calendar sources failed — will use DB cache")
        return []

    def _fetch_finnhub(self) -> List[dict]:
        """Fetch from Finnhub /calendar/economic (free, 700+ events/2 weeks)."""
        try:
            from data.market_data_cache import _get_finnhub_key
            api_key = _get_finnhub_key()
            if not api_key:
                logger.warning("No Finnhub API key available for calendar")
                return []

            now       = datetime.now(timezone.utc)
            date_from = now.strftime('%Y-%m-%d')
            date_to   = (now + timedelta(days=14)).strftime('%Y-%m-%d')

            url = (f"https://finnhub.io/api/v1/calendar/economic"
                   f"?from={date_from}&to={date_to}&token={api_key}")

            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            resp.raise_for_status()

            data = resp.json()
            raw_events = data.get('economicCalendar', [])
            if not raw_events:
                logger.warning("Finnhub calendar: empty economicCalendar")
                return []

            events = []
            for ev in raw_events:
                title    = ev.get('event', '')
                country  = ev.get('country', '')
                currency = COUNTRY_TO_CURRENCY.get(country, '')
                if not currency:
                    continue  # Skip events with unknown currency

                impact = str(ev.get('impact', 'low')).lower()
                time_str = ev.get('time', '')

                try:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    continue

                is_high = (impact == 'high') or any(
                    kw.lower() in title.lower() for kw in HIGH_IMPACT_KEYWORDS
                )

                # Finnhub returns numbers for actual/estimate/prev
                actual   = str(ev['actual'])   if ev.get('actual')   is not None else ''
                forecast = str(ev['estimate']) if ev.get('estimate') is not None else ''
                previous = str(ev['prev'])     if ev.get('prev')     is not None else ''

                events.append({
                    'title':          title,
                    'country':        country,
                    'currency':       currency,
                    'datetime':       dt,
                    'impact':         impact,
                    'forecast':       forecast,
                    'previous':       previous,
                    'actual':         actual,
                    'is_high_impact': is_high,
                    'affected_pairs': CURRENCY_TO_PAIRS.get(currency, []),
                    'source':         'finnhub',
                })

            logger.info(f"Finnhub calendar: {len(events)} events fetched")
            return events

        except Exception as e:
            logger.error(f"Finnhub calendar error: {e}")
            return []

    def _fetch_forexfactory(self) -> List[dict]:
        """Fetch from ForexFactory thisweek JSON (nextweek skipped — often 404)."""
        url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            resp.raise_for_status()
            raw_events = resp.json()

            events = []
            for ev in raw_events:
                title    = ev.get('title', '')
                country  = ev.get('country', '')
                currency = FF_COUNTRY_CURRENCY.get(country, country)
                impact   = str(ev.get('impact', 'Low'))

                try:
                    dt = datetime.fromisoformat(ev.get('date', '').replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    continue

                is_high = (impact.lower() in ('high', 'holiday')) or any(
                    kw.lower() in title.lower() for kw in HIGH_IMPACT_KEYWORDS
                )

                events.append({
                    'title':          title,
                    'country':        country,
                    'currency':       currency,
                    'datetime':       dt,
                    'impact':         impact.lower(),
                    'forecast':       ev.get('forecast', ''),
                    'previous':       ev.get('previous', ''),
                    'actual':         ev.get('actual', ''),
                    'is_high_impact': is_high,
                    'affected_pairs': CURRENCY_TO_PAIRS.get(currency, []),
                    'source':         'forexfactory',
                })

            logger.info(f"ForexFactory: {len(events)} events fetched")
            return events

        except Exception as e:
            logger.error(f"ForexFactory error: {e}")
            return []

    # ── DB Save / Load ────────────────────────────────────────────────────────

    def _save_to_db(self, events: List[dict]):
        """Upsert events into economic_events table."""
        if not self.db:
            return
        try:
            raw_conn = self.db.engine.raw_connection()
            cursor   = raw_conn.cursor()
            saved = 0
            for ev in events:
                if not ev.get('datetime'):
                    continue
                try:
                    cursor.execute(
                        """INSERT INTO economic_events
                           (event_title, currency, event_time, impact_level,
                            forecast_value, previous_value, actual_value, affected_pairs)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                             actual_value   = VALUES(actual_value),
                             impact_level   = VALUES(impact_level),
                             forecast_value = VALUES(forecast_value)""",
                        (
                            ev['title'][:200],
                            ev['currency'],
                            ev['datetime'],
                            'high' if ev['is_high_impact'] else ev['impact'],
                            ev.get('forecast', '')[:50],
                            ev.get('previous', '')[:50],
                            ev.get('actual', '')[:50],
                            json.dumps(ev['affected_pairs']),
                        )
                    )
                    saved += 1
                except Exception:
                    pass
            raw_conn.commit()
            cursor.close()
            raw_conn.close()
            logger.info(f"Calendar: saved/updated {saved} events in DB")
        except Exception as e:
            logger.warning(f"Calendar DB save failed: {e}")

    def _load_from_db(self) -> List[dict]:
        """Load upcoming events from DB (fallback when all APIs fail)."""
        if not self.db:
            return []
        try:
            raw_conn = self.db.engine.raw_connection()
            cursor   = raw_conn.cursor()
            cursor.execute(
                """SELECT event_title, currency, event_time, impact_level,
                          forecast_value, previous_value, actual_value, affected_pairs
                   FROM economic_events
                   WHERE event_time >= NOW() - INTERVAL 2 HOUR
                   ORDER BY event_time ASC
                   LIMIT 500"""
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

                dt = event_time
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                events.append({
                    'title': title, 'currency': currency, 'datetime': dt,
                    'impact': impact, 'forecast': forecast or '',
                    'previous': prev or '', 'actual': actual or '',
                    'is_high_impact': is_high, 'affected_pairs': affected,
                    'source': 'db',
                })
            return events
        except Exception as e:
            logger.warning(f"Calendar DB load failed: {e}")
            return []

    # ── Gate / Signal Logic ───────────────────────────────────────────────────

    def check_gate(self, pair: str, minutes_before: int = 30,
                   minutes_after: int = 15) -> Dict:
        """Block/caution trading around high-impact events."""
        now = datetime.now(timezone.utc)
        for ev in self._events:
            if not ev.get('datetime') or not ev.get('is_high_impact'):
                continue
            if pair not in ev.get('affected_pairs', []):
                continue
            ev_time = ev['datetime']
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)
            diff = (ev_time - now).total_seconds() / 60
            if 0 < diff <= minutes_before:
                return {
                    'action': 'BLOCK',
                    'reason': f"High-impact in {int(diff)}min: {ev['title']} ({ev['currency']})",
                    'event': ev, 'minutes_until': int(diff),
                }
            if -minutes_after <= diff <= 0:
                return {
                    'action': 'CAUTION',
                    'reason': f"High-impact {int(abs(diff))}min ago: {ev['title']}",
                    'event': ev, 'minutes_until': int(diff),
                }
            if 0 < diff <= 120:
                return {
                    'action': 'CAUTION',
                    'reason': f"High-impact in {int(diff)}min: {ev['title']}",
                    'event': ev, 'minutes_until': int(diff),
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
        """Check recent events for directional bias (actual vs forecast)."""
        now = datetime.now(timezone.utc)
        recent = timedelta(hours=4)
        for ev in self._events:
            if not ev.get('datetime') or not ev.get('is_high_impact'):
                continue
            if pair not in ev.get('affected_pairs', []):
                continue
            ev_time = ev['datetime']
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)
            if not (now - recent <= ev_time <= now):
                continue
            actual   = ev.get('actual', '')
            forecast = ev.get('forecast', '')
            if not actual or not forecast:
                continue
            try:
                act_v   = float(str(actual).replace('%', '').replace('K', '000')
                                .replace('M', '000000').strip())
                fcast_v = float(str(forecast).replace('%', '').replace('K', '000')
                                .replace('M', '000000').strip())
            except (ValueError, AttributeError):
                continue
            diff_pct = (act_v - fcast_v) / abs(fcast_v) if fcast_v != 0 else 0
            if abs(diff_pct) < 0.01:
                continue
            currency = ev['currency']
            is_base  = pair.startswith(currency)
            is_quote = pair[3:6] == currency if len(pair) >= 6 else False
            reason   = f"{ev['title']}: actual={actual} vs forecast={forecast}"
            if diff_pct > 0:
                if is_base:  return {'bias': 'bullish', 'reason': reason, 'strength': min(1.0, abs(diff_pct))}
                if is_quote: return {'bias': 'bearish', 'reason': reason, 'strength': min(1.0, abs(diff_pct))}
            else:
                if is_base:  return {'bias': 'bearish', 'reason': reason, 'strength': min(1.0, abs(diff_pct))}
                if is_quote: return {'bias': 'bullish', 'reason': reason, 'strength': min(1.0, abs(diff_pct))}
        return {'bias': 'neutral', 'reason': '', 'strength': 0.0}

    # ── Session Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def get_active_sessions() -> List[str]:
        hour = datetime.now(timezone.utc).hour
        active = []
        for name, sess in SESSIONS.items():
            if sess['open'] < sess['close']:
                if sess['open'] <= hour < sess['close']:
                    active.append(name)
            else:
                if hour >= sess['open'] or hour < sess['close']:
                    active.append(name)
        return active

    @staticmethod
    def is_session_optimal(pair: str) -> bool:
        if pair in CRYPTO_PAIRS:
            return True
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
        active  = EconomicCalendar.get_active_sessions()
        optimal = EconomicCalendar.is_session_optimal(pair)
        hour    = datetime.now(timezone.utc).hour
        overlap = 13 <= hour < 16
        return {
            'active_sessions':     active,
            'is_optimal':          optimal,
            'london_ny_overlap':   overlap,
            'volatility_expected': 'high' if overlap else ('medium' if active else 'low'),
        }
