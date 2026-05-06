"""
News Fetcher — RSS-based Forex news from free sources.
Sources:
  - ForexFactory Calendar (HTML scrape)
  - Reuters (RSS)
  - FXStreet (RSS)
  - Investing.com (RSS)
  - DailyFX (RSS)

Saves to news_archive table in DB.
"""

from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from utils.logger import setup_logger

logger = setup_logger('news_fetcher')

# Free RSS feeds for Forex news
RSS_FEEDS = [
    {
        'name':  'CNBC Forex',
        'url':   'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362',
        'keywords': ['forex', 'dollar', 'euro', 'yen', 'pound', 'currency', 'fed', 'ecb', 'boe', 'gold'],
    },
    {
        'name':  'FXStreet',
        'url':   'https://www.fxstreet.com/rss/news',
        'keywords': [],
    },
    {
        'name':  'Google News Forex',
        'url':   'https://news.google.com/rss/search?q=forex+currency+trading&hl=en-US&gl=US&ceid=US:en',
        'keywords': ['forex', 'dollar', 'euro', 'yen', 'pound', 'currency', 'fed', 'ecb', 'gold'],
    },
    {
        'name':  'Investing.com Forex',
        'url':   'https://www.investing.com/rss/news_301.rss',
        'keywords': [],
    },
    {
        'name':  'ForexLive',
        'url':   'https://www.forexlive.com/feed',
        'keywords': [],
    },
]

# Currency keywords to detect affected currencies
CURRENCY_KEYWORDS = {
    'USD': ['dollar', 'usd', 'fed', 'federal reserve', 'fomc', 'powell', 'nfp', 'cpi', 'us inflation'],
    'EUR': ['euro', 'eur', 'ecb', 'lagarde', 'eurozone', 'european'],
    'GBP': ['pound', 'gbp', 'sterling', 'boe', 'bank of england', 'bailey', 'uk'],
    'JPY': ['yen', 'jpy', 'boj', 'bank of japan', 'ueda', 'japan'],
    'CHF': ['franc', 'chf', 'snb', 'swiss'],
    'AUD': ['aussie', 'aud', 'rba', 'australia'],
    'CAD': ['loonie', 'cad', 'boc', 'bank of canada', 'canada'],
    'NZD': ['kiwi', 'nzd', 'rbnz', 'new zealand'],
    'XAU': ['gold', 'xau', 'bullion', 'precious metal'],
}


class NewsFetcher:
    """Fetches and stores Forex news from RSS feeds."""

    def __init__(self, db):
        self.db = db

    async def fetch_latest(self, hours: int = 4) -> list[dict]:
        """
        Fetch news from all sources published in the last N hours.
        Returns list of news dicts ready for AI analysis.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        loop = asyncio.get_event_loop()
        all_news = []

        for feed_config in RSS_FEEDS:
            try:
                items = await loop.run_in_executor(
                    None, self._fetch_feed, feed_config, cutoff
                )
                all_news.extend(items)
            except Exception as e:
                logger.error(f"Feed error ({feed_config['name']}): {e}")

        # Deduplicate by title hash
        seen = set()
        unique_news = []
        for item in all_news:
            h = hashlib.md5(item['title'].encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique_news.append(item)

        # Save to DB (ignore duplicates)
        self._save_to_db(unique_news)

        logger.info(f"Fetched {len(unique_news)} unique news items (last {hours}h)")
        return unique_news

    def _fetch_feed(self, feed_config: dict, cutoff: datetime) -> list[dict]:
        """Fetch and parse a single RSS feed."""
        items = []
        try:
            parsed = feedparser.parse(feed_config['url'])

            for entry in parsed.entries:
                # Parse publish time
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    import time
                    ts = time.mktime(entry.published_parsed)
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)

                if published_at and published_at < cutoff:
                    continue  # Skip old articles

                title   = getattr(entry, 'title', '')
                summary = getattr(entry, 'summary', '')
                link    = getattr(entry, 'link', '')

                # Filter by keywords if configured
                if feed_config['keywords']:
                    text_lower = (title + summary).lower()
                    if not any(kw in text_lower for kw in feed_config['keywords']):
                        continue

                # Detect affected currencies
                affected = self._detect_currencies(title + ' ' + summary)

                items.append({
                    'source':               feed_config['name'],
                    'title':                title[:500],
                    'summary':              summary[:2000],
                    'link':                 link[:500],
                    'published_at':         published_at or datetime.now(timezone.utc),
                    'affected_currencies':  affected,
                })

        except Exception as e:
            logger.error(f"RSS parse error ({feed_config['name']}): {e}")

        return items

    def _save_to_db(self, news_items: list[dict]):
        """Save news items to DB (skip duplicates by title)."""
        import json
        bullish_kw = ['rally', 'surge', 'jump', 'gain', 'bullish', 'hawkish', 'strong',
                       'rise', 'higher', 'beat', 'exceed', 'positive', 'optimis', 'boom']
        bearish_kw = ['drop', 'fall', 'crash', 'plunge', 'bearish', 'dovish', 'weak',
                       'decline', 'lower', 'miss', 'disappoint', 'negative', 'pessimis', 'slump']
        high_impact = ['nfp', 'fomc', 'rate decision', 'cpi', 'gdp', 'employment',
                        'non-farm', 'inflation', 'central bank', 'interest rate']

        for item in news_items:
            try:
                text = (item['title'] + ' ' + item.get('summary', '')).lower()
                bull = sum(1 for kw in bullish_kw if kw in text)
                bear = sum(1 for kw in bearish_kw if kw in text)

                if bull > bear + 1:
                    sentiment = 'bullish'
                elif bear > bull + 1:
                    sentiment = 'bearish'
                else:
                    sentiment = 'neutral'

                has_high = any(kw in text for kw in high_impact)
                impact_level = 'high' if has_high else ('medium' if bull + bear >= 3 else 'low')
                impact_strength = min(1.0, (bull + bear) * 0.15)

                self.db.execute_write(
                    """INSERT IGNORE INTO news_archive
                       (source, title, summary, link, published_at, affected_currencies,
                        sentiment, impact_level, impact_strength)
                       VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8)""",
                    (
                        item['source'],
                        item['title'],
                        item.get('summary', ''),
                        item.get('link', ''),
                        item['published_at'].strftime('%Y-%m-%d %H:%M:%S'),
                        json.dumps(item.get('affected_currencies', [])),
                        sentiment,
                        impact_level,
                        impact_strength,
                    )
                )
            except Exception as e:
                logger.debug(f"News save skipped (likely duplicate): {e}")

    @staticmethod
    def _detect_currencies(text: str) -> list[str]:
        """Detect which currencies are mentioned in the text."""
        text_lower = text.lower()
        affected = []
        for currency, keywords in CURRENCY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                affected.append(currency)
        return affected
