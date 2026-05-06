"""
AI News Analyzer — Claude Haiku
Analyzes recent Forex news to determine market sentiment per currency pair.

Returns: {pair: {sentiment: bullish|bearish|neutral, ai_confidence: 0-100}}

Cost optimization:
  - Batch all pairs into one API call
  - Cache results for 30 minutes
  - Only call when news/hybrid/ai mode is active
  - Max 5 news items per batch (most recent)
"""

from __future__ import annotations
import asyncio
import json
import time
from typing import Optional

import anthropic

from utils.logger import setup_logger

logger = setup_logger('ai_analyzer')


class NewsAnalyzer:
    """Analyzes news using Claude Haiku for Forex sentiment."""

    CACHE_TTL = 1800  # 30 minutes

    def __init__(self, config):
        self.config = config
        self._client: Optional[anthropic.Anthropic] = None
        self._cache: dict = {}   # {cache_key: (result, timestamp)}
        self._init_client()

    def _init_client(self):
        """Initialize Claude client."""
        api_key = self.config.ANTHROPIC_API_KEY
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — AI analysis disabled")
            return
        try:
            self._client = anthropic.Anthropic(api_key=api_key)
            logger.info(f"Claude client initialized (model: {self.config.claude_model})")
        except Exception as e:
            logger.error(f"Failed to init Claude client: {e}")

    async def analyze_batch(self, news_items: list[dict]) -> dict:
        """
        Analyze a batch of news items for all Forex pairs.
        Returns dict: {pair: {sentiment, ai_confidence, reasoning}}
        """
        if not self._client:
            return {}

        if not news_items:
            return {}

        # Check cache
        cache_key = self._cache_key(news_items)
        cached = self._cache.get(cache_key)
        if cached:
            result, ts = cached
            if time.time() - ts < self.CACHE_TTL:
                logger.debug("AI analysis from cache")
                return result

        # Prepare news text (top 5 most recent)
        sorted_news = sorted(
            news_items,
            key=lambda x: x.get('published_at', ''),
            reverse=True
        )[:5]

        news_text = "\n\n".join([
            f"[{i+1}] {item['title']}\n{item.get('summary', '')[:300]}"
            for i, item in enumerate(sorted_news)
        ])

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self._call_claude, news_text
        )

        if result:
            self._cache[cache_key] = (result, time.time())

        return result or {}

    def _call_claude(self, news_text: str) -> Optional[dict]:
        """Make the Claude API call (blocking — run in executor)."""
        threshold = self.config.ai_confidence_threshold

        prompt = f"""You are a professional Forex analyst. Analyze the following recent news headlines and summaries.

NEWS:
{news_text}

For each major Forex pair listed below, determine:
1. Sentiment: bullish, bearish, or neutral
2. Confidence: 0-100 (how confident you are in this sentiment)
3. Brief reasoning (1 sentence max)

Only include pairs where the news has a clear, direct impact (confidence ≥ {threshold}).
If unclear or insufficient data, set sentiment to "neutral" with confidence < {threshold}.

Respond in valid JSON only, no other text:
{{
  "EURUSD": {{"sentiment": "bullish|bearish|neutral", "ai_confidence": 0-100, "reasoning": "..."}},
  "GBPUSD": {{"sentiment": "...", "ai_confidence": 0, "reasoning": "..."}},
  "USDJPY": {{"sentiment": "...", "ai_confidence": 0, "reasoning": "..."}},
  "XAUUSD": {{"sentiment": "...", "ai_confidence": 0, "reasoning": "..."}}
}}"""

        try:
            message = self._client.messages.create(
                model=self.config.claude_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            content = message.content[0].text.strip()

            # Extract JSON from response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            result = json.loads(content)

            # Filter by confidence threshold
            filtered = {}
            for pair, data in result.items():
                if isinstance(data, dict) and data.get('ai_confidence', 0) >= threshold:
                    filtered[pair] = data

            logger.info(f"AI analysis complete: {len(filtered)} pairs above {threshold}% confidence")
            return filtered

        except json.JSONDecodeError as e:
            logger.error(f"Claude returned invalid JSON: {e}")
            return None
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return None
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None

    @staticmethod
    def _cache_key(news_items: list[dict]) -> str:
        """Generate cache key from news titles."""
        titles = sorted([item.get('title', '') for item in news_items])
        return str(hash(tuple(titles)))
