"""
Liquidity Analysis Engine — Smart Money Concepts (SMC)

Detects institutional trading patterns from OHLCV data:
  - Swing Structure (Higher Highs/Lows, Lower Highs/Lows)
  - Liquidity Pools — BSL (Buy-Side) and SSL (Sell-Side)
  - Order Blocks — Last opposing candle before impulsive move
  - Fair Value Gaps — Price imbalances (3-candle gaps)
  - Break of Structure (BOS) — Continuation signals
  - Change of Character (CHoCH) — Reversal signals
  - Equal Highs/Lows — Engineered liquidity targets
  - Premium/Discount Zones — Fibonacci-based buy/sell zones

Usage:
    analyzer = LiquidityAnalyzer()
    result = analyzer.analyze(df_h1, pair='EURUSD', atr=0.0015)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger('liquidity')


# ═════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class LiquidityResult:
    """Output of the liquidity analysis — used by confluence scorer."""

    # ── Order Blocks ──────────────────────────────────────────────────────
    at_order_block: str = 'none'        # 'bullish' | 'bearish' | 'none'
    ob_strength: float = 0.0            # 0.0 – 1.0 (freshness + size)
    order_blocks: List[dict] = field(default_factory=list)

    # ── Fair Value Gaps ───────────────────────────────────────────────────
    at_fvg: str = 'none'                # 'bullish' | 'bearish' | 'none'
    fvg_strength: float = 0.0           # 0.0 – 1.0
    fvgs: List[dict] = field(default_factory=list)

    # ── Market Structure ──────────────────────────────────────────────────
    structure_trend: str = 'unknown'    # 'bullish' | 'bearish' | 'ranging'
    latest_break: str = 'none'          # 'BOS_bullish' | 'BOS_bearish' |
                                        # 'CHoCH_bullish' | 'CHoCH_bearish'
    structure_breaks: List[dict] = field(default_factory=list)

    # ── Liquidity Pools ───────────────────────────────────────────────────
    ssl_swept: bool = False             # Sell-Side swept → bullish bias
    bsl_swept: bool = False             # Buy-Side swept → bearish bias
    nearest_bsl: Optional[float] = None # Nearest buy-side liquidity level
    nearest_ssl: Optional[float] = None # Nearest sell-side liquidity level
    liquidity_pools: List[dict] = field(default_factory=list)

    # ── Equal Highs/Lows ─────────────────────────────────────────────────
    equal_highs_near: bool = False      # BSL accumulation above
    equal_lows_near: bool = False       # SSL accumulation below
    equal_levels: List[dict] = field(default_factory=list)

    # ── Premium / Discount ────────────────────────────────────────────────
    zone: str = 'equilibrium'           # 'premium' | 'discount' | 'equilibrium'

    # ── Swing Points (raw) ────────────────────────────────────────────────
    swing_highs: List[dict] = field(default_factory=list)
    swing_lows: List[dict] = field(default_factory=list)

    def summary(self, direction: str) -> str:
        """One-line summary for Telegram notifications."""
        parts = []
        is_buy = direction == 'BUY'

        if self.at_order_block != 'none':
            parts.append(f"OB: {self.at_order_block}")
        if self.at_fvg != 'none':
            parts.append(f"FVG: {self.at_fvg}")
        if self.latest_break != 'none':
            parts.append(self.latest_break.replace('_', ' '))
        if is_buy and self.ssl_swept:
            parts.append("SSL swept")
        if not is_buy and self.bsl_swept:
            parts.append("BSL swept")
        if self.zone != 'equilibrium':
            parts.append(f"Zone: {self.zone}")

        return " | ".join(parts) if parts else "No SMC confluence"


# ═════════════════════════════════════════════════════════════════════════════
#  LIQUIDITY ANALYZER
# ═════════════════════════════════════════════════════════════════════════════

class LiquidityAnalyzer:
    """Analyzes OHLCV data for Smart Money / Liquidity patterns."""

    SWING_LOOKBACK = 3          # Bars each side to confirm swing point
    OB_IMPULSE_RATIO = 1.8      # Impulsive candle body must be ≥ this × previous
    FVG_MIN_SIZE_ATR = 0.3      # Minimum FVG size relative to ATR
    EQUAL_LEVEL_PIPS = 5.0      # Tolerance for equal highs/lows (pips)
    LIQUIDITY_SWEEP_PIPS = 3.0  # How far past a level = sweep (pips)

    def analyze(
        self,
        df: pd.DataFrame,
        pair: str,
        atr: float,
        htf_df: pd.DataFrame = None,
    ) -> LiquidityResult:
        """
        Run full liquidity analysis on OHLCV data.
        Returns LiquidityResult with all SMC components.
        """
        result = LiquidityResult()

        if df is None or len(df) < 30:
            return result

        pip_size = self._pip_size(pair)
        current_price = float(df['close'].iloc[-1])

        # 1. Detect swing points
        swing_highs, swing_lows = self._find_swing_points(df)
        result.swing_highs = swing_highs
        result.swing_lows = swing_lows

        if not swing_highs or not swing_lows:
            return result

        # 2. Market structure (BOS / CHoCH)
        breaks, trend = self._detect_structure(swing_highs, swing_lows, current_price)
        result.structure_breaks = breaks
        result.structure_trend = trend
        if breaks:
            result.latest_break = breaks[-1].get('label', 'none')

        # 3. Order blocks
        obs = self._find_order_blocks(df, atr)
        result.order_blocks = obs
        self._check_at_order_block(result, current_price, atr)

        # 4. Fair value gaps
        fvgs = self._find_fvgs(df, atr)
        result.fvgs = fvgs
        self._check_at_fvg(result, current_price, atr)

        # 5. Liquidity pools (BSL / SSL)
        pools = self._find_liquidity_pools(swing_highs, swing_lows, pip_size)
        result.liquidity_pools = pools
        self._check_liquidity_sweeps(result, df, current_price, pip_size)

        # 6. Equal highs/lows
        eq_levels = self._find_equal_levels(swing_highs, swing_lows, pip_size)
        result.equal_levels = eq_levels
        self._check_equal_levels_near(result, current_price, atr)

        # 7. Premium / Discount zone
        result.zone = self._premium_discount(swing_highs, swing_lows, current_price)

        logger.debug(
            f"{pair} Liquidity: struct={result.structure_trend} "
            f"OB={result.at_order_block} FVG={result.at_fvg} "
            f"break={result.latest_break} zone={result.zone}"
        )

        return result

    # ═════════════════════════════════════════════════════════════════════════
    #  1. SWING POINT DETECTION
    # ═════════════════════════════════════════════════════════════════════════

    def _find_swing_points(self, df: pd.DataFrame) -> tuple:
        """Find swing highs and swing lows using N-bar lookback."""
        n = self.SWING_LOOKBACK
        highs, lows = [], []

        for i in range(n, len(df) - n):
            h = float(df['high'].iloc[i])
            l = float(df['low'].iloc[i])

            # Swing High: higher than N bars before AND after
            window_highs = df['high'].iloc[i - n:i + n + 1]
            if h >= float(window_highs.max()):
                highs.append({
                    'price': h,
                    'index': i,
                    'time': str(df.index[i]),
                })

            # Swing Low: lower than N bars before AND after
            window_lows = df['low'].iloc[i - n:i + n + 1]
            if l <= float(window_lows.min()):
                lows.append({
                    'price': l,
                    'index': i,
                    'time': str(df.index[i]),
                })

        return highs, lows

    # ═════════════════════════════════════════════════════════════════════════
    #  2. MARKET STRUCTURE (BOS / CHoCH)
    # ═════════════════════════════════════════════════════════════════════════

    def _detect_structure(
        self,
        swing_highs: List[dict],
        swing_lows: List[dict],
        current_price: float,
    ) -> tuple:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH).

        BOS: price breaks a swing point IN the direction of the current trend
             → trend continuation
        CHoCH: price breaks a swing point AGAINST the current trend
               → potential reversal
        """
        # Merge and sort all swing points by index
        all_swings = []
        for sh in swing_highs:
            all_swings.append({**sh, 'type': 'high'})
        for sl in swing_lows:
            all_swings.append({**sl, 'type': 'low'})
        all_swings.sort(key=lambda x: x['index'])

        if len(all_swings) < 4:
            return [], 'unknown'

        breaks = []
        trend = 'unknown'

        # Track the last significant swing high and low
        last_sh = None
        last_sl = None
        prev_sh = None
        prev_sl = None

        for swing in all_swings:
            if swing['type'] == 'high':
                if last_sh is not None:
                    if swing['price'] > last_sh['price']:
                        # Higher High
                        if trend == 'bearish':
                            # CHoCH — trend reversal to bullish
                            breaks.append({
                                'type': 'CHoCH',
                                'direction': 'bullish',
                                'price': last_sh['price'],
                                'index': swing['index'],
                                'time': swing['time'],
                                'label': 'CHoCH_bullish',
                            })
                        else:
                            # BOS — bullish continuation
                            breaks.append({
                                'type': 'BOS',
                                'direction': 'bullish',
                                'price': last_sh['price'],
                                'index': swing['index'],
                                'time': swing['time'],
                                'label': 'BOS_bullish',
                            })
                        trend = 'bullish'
                    else:
                        # Lower High → bearish pressure
                        pass
                prev_sh = last_sh
                last_sh = swing

            elif swing['type'] == 'low':
                if last_sl is not None:
                    if swing['price'] < last_sl['price']:
                        # Lower Low
                        if trend == 'bullish':
                            # CHoCH — trend reversal to bearish
                            breaks.append({
                                'type': 'CHoCH',
                                'direction': 'bearish',
                                'price': last_sl['price'],
                                'index': swing['index'],
                                'time': swing['time'],
                                'label': 'CHoCH_bearish',
                            })
                        else:
                            # BOS — bearish continuation
                            breaks.append({
                                'type': 'BOS',
                                'direction': 'bearish',
                                'price': last_sl['price'],
                                'index': swing['index'],
                                'time': swing['time'],
                                'label': 'BOS_bearish',
                            })
                        trend = 'bearish'
                prev_sl = last_sl
                last_sl = swing

        # Final trend based on recent structure
        if not breaks:
            trend = 'ranging'

        return breaks, trend

    # ═════════════════════════════════════════════════════════════════════════
    #  3. ORDER BLOCKS
    # ═════════════════════════════════════════════════════════════════════════

    def _find_order_blocks(self, df: pd.DataFrame, atr: float) -> List[dict]:
        """
        Detect Order Blocks — the last opposing candle before an impulsive move.

        Bullish OB: Last bearish (red) candle before a strong bullish impulse
                    → Institutional buying zone
        Bearish OB: Last bullish (green) candle before a strong bearish impulse
                    → Institutional selling zone
        """
        obs = []
        min_impulse = atr * self.OB_IMPULSE_RATIO

        for i in range(2, len(df)):
            curr_open = float(df['open'].iloc[i])
            curr_close = float(df['close'].iloc[i])
            curr_body = abs(curr_close - curr_open)

            prev_open = float(df['open'].iloc[i - 1])
            prev_close = float(df['close'].iloc[i - 1])
            prev_body = abs(prev_close - prev_open)

            if prev_body < atr * 0.1:
                continue  # Skip dojis

            is_curr_bullish = curr_close > curr_open
            is_prev_bearish = prev_close < prev_open
            is_curr_bearish = curr_close < curr_open
            is_prev_bullish = prev_close > prev_open

            # Bullish OB: bearish candle → strong bullish impulse
            if is_prev_bearish and is_curr_bullish and curr_body >= min_impulse:
                # Validate: current candle closes above the previous candle's open
                if curr_close > prev_open:
                    freshness = 1.0 - (len(df) - i) / len(df)  # 0=old, 1=recent
                    obs.append({
                        'type': 'bullish',
                        'high': float(df['high'].iloc[i - 1]),
                        'low': float(df['low'].iloc[i - 1]),
                        'mid': (float(df['high'].iloc[i - 1]) + float(df['low'].iloc[i - 1])) / 2,
                        'index': i - 1,
                        'time': str(df.index[i - 1]),
                        'strength': round(min(1.0, curr_body / (atr * 3)) * freshness, 2),
                        'mitigated': False,
                    })

            # Bearish OB: bullish candle → strong bearish impulse
            if is_prev_bullish and is_curr_bearish and curr_body >= min_impulse:
                if curr_close < prev_open:
                    freshness = 1.0 - (len(df) - i) / len(df)
                    obs.append({
                        'type': 'bearish',
                        'high': float(df['high'].iloc[i - 1]),
                        'low': float(df['low'].iloc[i - 1]),
                        'mid': (float(df['high'].iloc[i - 1]) + float(df['low'].iloc[i - 1])) / 2,
                        'index': i - 1,
                        'time': str(df.index[i - 1]),
                        'strength': round(min(1.0, curr_body / (atr * 3)) * freshness, 2),
                        'mitigated': False,
                    })

        # Mark mitigated OBs (price has already returned and passed through)
        if obs:
            current_price = float(df['close'].iloc[-1])
            for ob in obs:
                if ob['type'] == 'bullish':
                    # Mitigated if price went below OB low after it formed
                    post_data = df.iloc[ob['index'] + 2:]
                    if len(post_data) > 0 and float(post_data['low'].min()) < ob['low']:
                        ob['mitigated'] = True
                elif ob['type'] == 'bearish':
                    post_data = df.iloc[ob['index'] + 2:]
                    if len(post_data) > 0 and float(post_data['high'].max()) > ob['high']:
                        ob['mitigated'] = True

        # Keep only un-mitigated and recent OBs (last 50 bars)
        cutoff = len(df) - 80
        valid_obs = [ob for ob in obs if not ob['mitigated'] and ob['index'] >= cutoff]
        return valid_obs[-10:]  # Keep last 10 valid OBs

    def _check_at_order_block(self, result: LiquidityResult, price: float, atr: float):
        """Check if current price is at/near a valid Order Block."""
        tolerance = atr * 0.5

        for ob in result.order_blocks:
            if ob['type'] == 'bullish':
                if ob['low'] - tolerance <= price <= ob['high'] + tolerance:
                    result.at_order_block = 'bullish'
                    result.ob_strength = ob['strength']
                    return
            elif ob['type'] == 'bearish':
                if ob['low'] - tolerance <= price <= ob['high'] + tolerance:
                    result.at_order_block = 'bearish'
                    result.ob_strength = ob['strength']
                    return

    # ═════════════════════════════════════════════════════════════════════════
    #  4. FAIR VALUE GAPS (FVG)
    # ═════════════════════════════════════════════════════════════════════════

    def _find_fvgs(self, df: pd.DataFrame, atr: float) -> List[dict]:
        """
        Detect Fair Value Gaps — price imbalances in 3-candle patterns.

        Bullish FVG: candle[i-2].high < candle[i].low → gap going up
                     Price tends to fill this gap from above
        Bearish FVG: candle[i-2].low > candle[i].high → gap going down
                     Price tends to fill this gap from below
        """
        fvgs = []
        min_gap = atr * self.FVG_MIN_SIZE_ATR

        for i in range(2, len(df)):
            high_2 = float(df['high'].iloc[i - 2])
            low_0 = float(df['low'].iloc[i])
            low_2 = float(df['low'].iloc[i - 2])
            high_0 = float(df['high'].iloc[i])

            # Bullish FVG: gap between candle[i-2] high and candle[i] low
            if low_0 > high_2 and (low_0 - high_2) >= min_gap:
                fvg = {
                    'type': 'bullish',
                    'top': low_0,       # Upper edge of gap
                    'bottom': high_2,   # Lower edge of gap
                    'size': low_0 - high_2,
                    'index': i - 1,
                    'time': str(df.index[i - 1]),
                    'filled': False,
                }
                # Check if gap has been filled by subsequent price action
                post = df.iloc[i + 1:] if i + 1 < len(df) else pd.DataFrame()
                if len(post) > 0 and float(post['low'].min()) <= high_2:
                    fvg['filled'] = True
                fvgs.append(fvg)

            # Bearish FVG: gap between candle[i-2] low and candle[i] high
            if high_0 < low_2 and (low_2 - high_0) >= min_gap:
                fvg = {
                    'type': 'bearish',
                    'top': low_2,       # Upper edge
                    'bottom': high_0,   # Lower edge
                    'size': low_2 - high_0,
                    'index': i - 1,
                    'time': str(df.index[i - 1]),
                    'filled': False,
                }
                post = df.iloc[i + 1:] if i + 1 < len(df) else pd.DataFrame()
                if len(post) > 0 and float(post['high'].max()) >= low_2:
                    fvg['filled'] = True
                fvgs.append(fvg)

        # Keep only unfilled FVGs from recent history
        cutoff = len(df) - 80
        valid = [f for f in fvgs if not f['filled'] and f['index'] >= cutoff]
        return valid[-10:]

    def _check_at_fvg(self, result: LiquidityResult, price: float, atr: float):
        """Check if current price is inside an unfilled FVG."""
        tolerance = atr * 0.3

        for fvg in result.fvgs:
            if fvg['bottom'] - tolerance <= price <= fvg['top'] + tolerance:
                result.at_fvg = fvg['type']
                result.fvg_strength = min(1.0, fvg['size'] / (atr * 2))
                return

    # ═════════════════════════════════════════════════════════════════════════
    #  5. LIQUIDITY POOLS (BSL / SSL)
    # ═════════════════════════════════════════════════════════════════════════

    def _find_liquidity_pools(
        self,
        swing_highs: List[dict],
        swing_lows: List[dict],
        pip_size: float,
    ) -> List[dict]:
        """
        Identify liquidity pools where stop losses cluster.

        BSL (Buy-Side Liquidity): Above swing highs — buy stops of shorts
        SSL (Sell-Side Liquidity): Below swing lows — sell stops of longs
        """
        pools = []

        # Cluster swing highs that are close together → stronger BSL
        bsl_clusters = self._cluster_levels(
            [s['price'] for s in swing_highs], pip_size
        )
        for cluster in bsl_clusters:
            pools.append({
                'type': 'BSL',
                'level': cluster['avg'],
                'touches': cluster['count'],
                'strength': 'strong' if cluster['count'] >= 3 else 'moderate',
            })

        # Cluster swing lows → SSL
        ssl_clusters = self._cluster_levels(
            [s['price'] for s in swing_lows], pip_size
        )
        for cluster in ssl_clusters:
            pools.append({
                'type': 'SSL',
                'level': cluster['avg'],
                'touches': cluster['count'],
                'strength': 'strong' if cluster['count'] >= 3 else 'moderate',
            })

        return pools

    def _check_liquidity_sweeps(
        self,
        result: LiquidityResult,
        df: pd.DataFrame,
        current_price: float,
        pip_size: float,
    ):
        """Check if a liquidity pool was just swept (price spiked through and reversed)."""
        sweep_tolerance = self.LIQUIDITY_SWEEP_PIPS * pip_size

        if len(df) < 5:
            return

        recent_high = float(df['high'].iloc[-3:].max())
        recent_low = float(df['low'].iloc[-3:].min())

        nearest_bsl = None
        nearest_ssl = None

        for pool in result.liquidity_pools:
            if pool['type'] == 'BSL':
                # BSL sweep: price went above the level then came back down
                if recent_high >= pool['level'] and current_price < pool['level']:
                    result.bsl_swept = True
                # Track nearest BSL above price
                if pool['level'] > current_price:
                    if nearest_bsl is None or pool['level'] < nearest_bsl:
                        nearest_bsl = pool['level']

            elif pool['type'] == 'SSL':
                # SSL sweep: price went below the level then came back up
                if recent_low <= pool['level'] and current_price > pool['level']:
                    result.ssl_swept = True
                # Track nearest SSL below price
                if pool['level'] < current_price:
                    if nearest_ssl is None or pool['level'] > nearest_ssl:
                        nearest_ssl = pool['level']

        result.nearest_bsl = nearest_bsl
        result.nearest_ssl = nearest_ssl

    # ═════════════════════════════════════════════════════════════════════════
    #  6. EQUAL HIGHS / LOWS
    # ═════════════════════════════════════════════════════════════════════════

    def _find_equal_levels(
        self,
        swing_highs: List[dict],
        swing_lows: List[dict],
        pip_size: float,
    ) -> List[dict]:
        """
        Find equal highs and equal lows — engineered liquidity targets.
        Double/triple tops/bottoms where stop losses accumulate.
        """
        tolerance = self.EQUAL_LEVEL_PIPS * pip_size
        equals = []

        # Equal highs
        for i in range(len(swing_highs)):
            for j in range(i + 1, len(swing_highs)):
                if abs(swing_highs[i]['price'] - swing_highs[j]['price']) <= tolerance:
                    avg = (swing_highs[i]['price'] + swing_highs[j]['price']) / 2
                    equals.append({
                        'type': 'equal_highs',
                        'level': round(avg, 5),
                        'touches': 2,
                    })

        # Equal lows
        for i in range(len(swing_lows)):
            for j in range(i + 1, len(swing_lows)):
                if abs(swing_lows[i]['price'] - swing_lows[j]['price']) <= tolerance:
                    avg = (swing_lows[i]['price'] + swing_lows[j]['price']) / 2
                    equals.append({
                        'type': 'equal_lows',
                        'level': round(avg, 5),
                        'touches': 2,
                    })

        return equals

    def _check_equal_levels_near(
        self,
        result: LiquidityResult,
        current_price: float,
        atr: float,
    ):
        """Check if equal highs/lows are near current price."""
        proximity = atr * 3  # Within 3x ATR

        for eq in result.equal_levels:
            dist = abs(current_price - eq['level'])
            if dist <= proximity:
                if eq['type'] == 'equal_highs' and eq['level'] > current_price:
                    result.equal_highs_near = True
                elif eq['type'] == 'equal_lows' and eq['level'] < current_price:
                    result.equal_lows_near = True

    # ═════════════════════════════════════════════════════════════════════════
    #  7. PREMIUM / DISCOUNT ZONE
    # ═════════════════════════════════════════════════════════════════════════

    def _premium_discount(
        self,
        swing_highs: List[dict],
        swing_lows: List[dict],
        current_price: float,
    ) -> str:
        """
        Determine if price is in premium, discount, or equilibrium zone.

        Uses the range between recent swing high and swing low:
          - Above 61.8% of range = Premium (sell zone)
          - Below 38.2% of range = Discount (buy zone)
          - Between = Equilibrium
        """
        if not swing_highs or not swing_lows:
            return 'equilibrium'

        # Use the most recent significant swing high and low
        recent_high = max(s['price'] for s in swing_highs[-5:])
        recent_low = min(s['price'] for s in swing_lows[-5:])

        if recent_high <= recent_low:
            return 'equilibrium'

        full_range = recent_high - recent_low
        position = (current_price - recent_low) / full_range

        if position >= 0.618:
            return 'premium'
        elif position <= 0.382:
            return 'discount'
        return 'equilibrium'

    # ═════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _pip_size(pair: str) -> float:
        if 'JPY' in pair:
            return 0.01
        if 'XAU' in pair:
            return 0.1
        return 0.0001

    def _cluster_levels(self, levels: List[float], pip_size: float) -> List[dict]:
        """Group price levels that are within EQUAL_LEVEL_PIPS of each other."""
        if not levels:
            return []

        tolerance = self.EQUAL_LEVEL_PIPS * pip_size
        sorted_lvls = sorted(levels)
        clusters = []
        current_cluster = [sorted_lvls[0]]

        for i in range(1, len(sorted_lvls)):
            if abs(sorted_lvls[i] - current_cluster[-1]) <= tolerance:
                current_cluster.append(sorted_lvls[i])
            else:
                clusters.append({
                    'avg': round(sum(current_cluster) / len(current_cluster), 5),
                    'count': len(current_cluster),
                })
                current_cluster = [sorted_lvls[i]]

        clusters.append({
            'avg': round(sum(current_cluster) / len(current_cluster), 5),
            'count': len(current_cluster),
        })

        return clusters
