"""
Candlestick Pattern Detector
Detects 65 candlestick patterns from OHLCV data.
Returns: pd.Series with 1=BULLISH, -1=BEARISH, 0=none
"""

from __future__ import annotations
import numpy as np
import pandas as pd

PATTERN_REGISTRY: list[dict] = []


def _reg(name: str, func, description: str = ''):
    PATTERN_REGISTRY.append({
        'name': name,
        'func': func,
        'description': description,
        'category': 'candlestick',
    })


def get_all_candlestick_patterns() -> list[dict]:
    return PATTERN_REGISTRY.copy()


# ── Helper functions ─────────────────────────────────────────────────────────

def _body(o, c):
    return abs(c - o)

def _upper_wick(h, o, c):
    return h - np.maximum(o, c)

def _lower_wick(o, c, l):
    return np.minimum(o, c) - l

def _range_(h, l):
    return h - l

def _is_bullish(o, c):
    return c > o

def _is_bearish(o, c):
    return o > c


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGLE CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Hammer ────────────────────────────────────────────────────────────────
def hammer(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    upper = _upper_wick(h, o, c)
    rng = _range_(h, l)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        # Hammer: small body at top, long lower wick (>= 2x body), small upper wick
        if (body[i] > 0 and
            lower[i] >= 2.0 * body[i] and
            upper[i] <= body[i] * 0.5 and
            body[i] / rng[i] < 0.4):
            # Must be after a downtrend (prior 3 candles average close declining)
            if i >= 3 and c[i-1] < c[i-3]:
                sig[i] = 1  # Bullish
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Hammer', hammer, 'Small body at top, long lower wick after downtrend')


# ── 2. Inverted Hammer ──────────────────────────────────────────────────────
def inverted_hammer(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    upper = _upper_wick(h, o, c)
    rng = _range_(h, l)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (body[i] > 0 and
            upper[i] >= 2.0 * body[i] and
            lower[i] <= body[i] * 0.5 and
            body[i] / rng[i] < 0.4):
            if i >= 3 and c[i-1] < c[i-3]:
                sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Inverted_Hammer', inverted_hammer, 'Small body at bottom, long upper wick after downtrend')


# ── 3. Shooting Star ────────────────────────────────────────────────────────
def shooting_star(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(o, c, l)
    rng = _range_(h, l)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (body[i] > 0 and
            upper[i] >= 2.0 * body[i] and
            lower[i] <= body[i] * 0.5 and
            body[i] / rng[i] < 0.4):
            if i >= 3 and c[i-1] > c[i-3]:
                sig[i] = -1  # Bearish
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Shooting_Star', shooting_star, 'Small body at bottom, long upper wick after uptrend')


# ── 4. Hanging Man ──────────────────────────────────────────────────────────
def hanging_man(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    upper = _upper_wick(h, o, c)
    rng = _range_(h, l)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (body[i] > 0 and
            lower[i] >= 2.0 * body[i] and
            upper[i] <= body[i] * 0.5):
            if i >= 3 and c[i-1] > c[i-3]:
                sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Hanging_Man', hanging_man, 'Hammer shape after uptrend — bearish reversal')


# ── 5. Doji ─────────────────────────────────────────────────────────────────
def doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if body[i] / rng[i] < 0.1:
            # Direction based on prior trend
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1  # Bearish reversal at top
                elif c[i-1] < c[i-3]:
                    sig[i] = 1   # Bullish reversal at bottom
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Doji', doji, 'Open == Close, indecision/reversal signal')


# ── 6. Dragonfly Doji ───────────────────────────────────────────────────────
def dragonfly_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    upper = _upper_wick(h, o, c)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if body[i] / rng[i] < 0.1 and lower[i] >= 0.7 * rng[i] and upper[i] < 0.1 * rng[i]:
            sig[i] = 1  # Bullish
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Dragonfly_Doji', dragonfly_doji, 'Doji with long lower wick — bullish')


# ── 7. Gravestone Doji ──────────────────────────────────────────────────────
def gravestone_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    upper = _upper_wick(h, o, c)

    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if body[i] / rng[i] < 0.1 and upper[i] >= 0.7 * rng[i] and lower[i] < 0.1 * rng[i]:
            sig[i] = -1  # Bearish
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Gravestone_Doji', gravestone_doji, 'Doji with long upper wick — bearish')


# ── 8. Marubozu Bullish ─────────────────────────────────────────────────────
def marubozu_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)

    sig = np.zeros(len(df))
    for i in range(len(df)):
        if rng[i] == 0:
            continue
        if c[i] > o[i] and body[i] / rng[i] >= 0.9:
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Marubozu_Bull', marubozu_bullish, 'Full body bullish candle — strong momentum')


# ── 9. Marubozu Bearish ─────────────────────────────────────────────────────
def marubozu_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)

    sig = np.zeros(len(df))
    for i in range(len(df)):
        if rng[i] == 0:
            continue
        if o[i] > c[i] and body[i] / rng[i] >= 0.9:
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Marubozu_Bear', marubozu_bearish, 'Full body bearish candle — strong momentum')


# ═══════════════════════════════════════════════════════════════════════════════
#  TWO-CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 10. Bullish Engulfing ────────────────────────────────────────────────────
def bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        # Previous: bearish, Current: bullish, Current body engulfs previous
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] <= c[i-1] and c[i] >= o[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bullish_Engulfing', bullish_engulfing, 'Bullish candle fully engulfs prior bearish')


# ── 11. Bearish Engulfing ────────────────────────────────────────────────────
def bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (c[i-1] > o[i-1] and o[i] > c[i] and
            o[i] >= c[i-1] and c[i] <= o[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bearish_Engulfing', bearish_engulfing, 'Bearish candle fully engulfs prior bullish')


# ── 12. Bullish Harami ──────────────────────────────────────────────────────
def bullish_harami(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] >= c[i-1] and c[i] <= o[i-1] and
            _body(o[i], c[i]) < _body(o[i-1], c[i-1]) * 0.6):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bullish_Harami', bullish_harami, 'Small bullish inside large bearish')


# ── 13. Bearish Harami ──────────────────────────────────────────────────────
def bearish_harami(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (c[i-1] > o[i-1] and o[i] > c[i] and
            c[i] >= o[i-1] and o[i] <= c[i-1] and
            _body(o[i], c[i]) < _body(o[i-1], c[i-1]) * 0.6):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bearish_Harami', bearish_harami, 'Small bearish inside large bullish')


# ── 14. Piercing Line ───────────────────────────────────────────────────────
def piercing_line(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        mid_prev = (o[i-1] + c[i-1]) / 2.0
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] < c[i-1] and c[i] > mid_prev and c[i] < o[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Piercing_Line', piercing_line, 'Bullish opens below prior close, closes above midpoint')


# ── 15. Dark Cloud Cover ────────────────────────────────────────────────────
def dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        mid_prev = (o[i-1] + c[i-1]) / 2.0
        if (c[i-1] > o[i-1] and o[i] > c[i] and
            o[i] > c[i-1] and c[i] < mid_prev and c[i] > o[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Dark_Cloud', dark_cloud_cover, 'Bearish opens above prior close, closes below midpoint')


# ── 16. Tweezer Bottom ──────────────────────────────────────────────────────
def tweezer_bottom(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        # Two candles with nearly equal lows
        if (abs(l[i] - l[i-1]) < _range_(h[i], l[i]) * 0.05 and
            o[i-1] > c[i-1] and c[i] > o[i]):  # First bear, second bull
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tweezer_Bottom', tweezer_bottom, 'Two candles with equal lows — bullish reversal')


# ── 17. Tweezer Top ─────────────────────────────────────────────────────────
def tweezer_top(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (abs(h[i] - h[i-1]) < _range_(h[i], l[i]) * 0.05 and
            c[i-1] > o[i-1] and o[i] > c[i]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tweezer_Top', tweezer_top, 'Two candles with equal highs — bearish reversal')


# ═══════════════════════════════════════════════════════════════════════════════
#  THREE-CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 18. Morning Star ────────────────────────────────────────────────────────
def morning_star(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        body0 = _body(o[i-2], c[i-2])
        body1 = _body(o[i-1], c[i-1])
        body2 = _body(o[i], c[i])
        # 1st: large bearish, 2nd: small body (gap down), 3rd: large bullish
        if (o[i-2] > c[i-2] and body0 > 0 and
            body1 < body0 * 0.4 and
            c[i] > o[i] and body2 > body0 * 0.5 and
            c[i] > (o[i-2] + c[i-2]) / 2.0):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Morning_Star', morning_star, 'Bear + small body + bull — bullish reversal')


# ── 19. Evening Star ────────────────────────────────────────────────────────
def evening_star(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        body0 = _body(o[i-2], c[i-2])
        body1 = _body(o[i-1], c[i-1])
        body2 = _body(o[i], c[i])
        if (c[i-2] > o[i-2] and body0 > 0 and
            body1 < body0 * 0.4 and
            o[i] > c[i] and body2 > body0 * 0.5 and
            c[i] < (o[i-2] + c[i-2]) / 2.0):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Evening_Star', evening_star, 'Bull + small body + bear — bearish reversal')


# ── 20. Three White Soldiers ────────────────────────────────────────────────
def three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and c[i] > o[i] and  # all bullish
            c[i] > c[i-1] > c[i-2] and  # progressively higher closes
            o[i-1] > o[i-2] and o[i] > o[i-1] and  # higher opens
            _body(o[i-2], c[i-2]) / max(rng[i-2], 1e-10) > 0.5 and
            _body(o[i-1], c[i-1]) / max(rng[i-1], 1e-10) > 0.5 and
            _body(o[i], c[i]) / max(rng[i], 1e-10) > 0.5):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_White_Soldiers', three_white_soldiers, 'Three consecutive large bullish candles')


# ── 21. Three Black Crows ───────────────────────────────────────────────────
def three_black_crows(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and o[i-1] > c[i-1] and o[i] > c[i] and
            c[i] < c[i-1] < c[i-2] and
            o[i-1] < o[i-2] and o[i] < o[i-1] and
            _body(o[i-2], c[i-2]) / max(rng[i-2], 1e-10) > 0.5 and
            _body(o[i-1], c[i-1]) / max(rng[i-1], 1e-10) > 0.5 and
            _body(o[i], c[i]) / max(rng[i], 1e-10) > 0.5):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Black_Crows', three_black_crows, 'Three consecutive large bearish candles')


# ── 22. Three Inside Up (Bullish) ───────────────────────────────────────────
def three_inside_up(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        # 1st: large bearish, 2nd: small bullish inside 1st (harami), 3rd: bullish closes above 1st open
        if (o[i-2] > c[i-2] and
            c[i-1] > o[i-1] and o[i-1] >= c[i-2] and c[i-1] <= o[i-2] and
            c[i] > o[i] and c[i] > o[i-2]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Inside_Up', three_inside_up, 'Harami + confirmation — bullish')


# ── 23. Three Inside Down (Bearish) ─────────────────────────────────────────
def three_inside_down(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and
            o[i-1] > c[i-1] and c[i-1] >= o[i-2] and o[i-1] <= c[i-2] and
            o[i] > c[i] and c[i] < o[i-2]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Inside_Down', three_inside_down, 'Harami + confirmation — bearish')


# ═══════════════════════════════════════════════════════════════════════════════
#  ADDITIONAL SINGLE CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 24. Long-Legged Doji ───────────────────────────────────────────────────
def long_legged_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(o, c, l)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (body[i] / rng[i] < 0.1 and
            upper[i] >= 0.3 * rng[i] and lower[i] >= 0.3 * rng[i]):
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1
                elif c[i-1] < c[i-3]:
                    sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Long_Legged_Doji', long_legged_doji, 'Doji with long upper and lower wicks — indecision')


# ── 25. Four Price Doji ────────────────────────────────────────────────────
def four_price_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if o[i] == h[i] == l[i] == c[i]:
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1
                elif c[i-1] < c[i-3]:
                    sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Four_Price_Doji', four_price_doji, 'All four prices equal — extreme indecision')


# ── 26. Spinning Top ──────────────────────────────────────────────────────
def spinning_top(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(o, c, l)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        br = body[i] / rng[i]
        if (0.1 <= br <= 0.35 and
            upper[i] >= body[i] and lower[i] >= body[i]):
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1
                elif c[i-1] < c[i-3]:
                    sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Spinning_Top', spinning_top, 'Small body with roughly equal wicks — indecision')


# ── 27. High Wave Candle ──────────────────────────────────────────────────
def high_wave_candle(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(o, c, l)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        br = body[i] / rng[i]
        if (br < 0.2 and
            upper[i] >= 0.35 * rng[i] and lower[i] >= 0.35 * rng[i]):
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1
                elif c[i-1] < c[i-3]:
                    sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('High_Wave', high_wave_candle, 'Very long wicks both sides, tiny body — major indecision')


# ── 28. Rickshaw Man ──────────────────────────────────────────────────────
def rickshaw_man(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(o, c, l)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        mid = (h[i] + l[i]) / 2.0
        body_mid = (o[i] + c[i]) / 2.0
        if (body[i] / rng[i] < 0.05 and
            abs(body_mid - mid) / rng[i] < 0.05 and
            upper[i] >= 0.35 * rng[i] and lower[i] >= 0.35 * rng[i]):
            if i >= 3:
                if c[i-1] > c[i-3]:
                    sig[i] = -1
                elif c[i-1] < c[i-3]:
                    sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rickshaw_Man', rickshaw_man, 'Long-legged doji with body exactly at midpoint')


# ── 29. Belt Hold Bullish ─────────────────────────────────────────────────
def belt_hold_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    lower = _lower_wick(o, c, l)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (c[i] > o[i] and body[i] / rng[i] >= 0.6 and
            lower[i] / rng[i] < 0.05):
            if i >= 3 and c[i-1] < c[i-3]:
                sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Belt_Hold_Bull', belt_hold_bullish, 'Opens at low, strong bullish close after downtrend')


# ── 30. Belt Hold Bearish ─────────────────────────────────────────────────
def belt_hold_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    upper = _upper_wick(h, o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (o[i] > c[i] and body[i] / rng[i] >= 0.6 and
            upper[i] / rng[i] < 0.05):
            if i >= 3 and c[i-1] > c[i-3]:
                sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Belt_Hold_Bear', belt_hold_bearish, 'Opens at high, strong bearish close after uptrend')


# ═══════════════════════════════════════════════════════════════════════════════
#  ADDITIONAL TWO-CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 31. Bullish Harami Cross ──────────────────────────────────────────────
def bullish_harami_cross(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (o[i-1] > c[i-1] and
            body[i] / rng[i] < 0.1 and
            o[i] >= c[i-1] and c[i] <= o[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bullish_Harami_Cross', bullish_harami_cross, 'Doji inside large bearish — bullish reversal')


# ── 32. Bearish Harami Cross ──────────────────────────────────────────────
def bearish_harami_cross(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (c[i-1] > o[i-1] and
            body[i] / rng[i] < 0.1 and
            c[i] >= o[i-1] and o[i] <= c[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bearish_Harami_Cross', bearish_harami_cross, 'Doji inside large bullish — bearish reversal')


# ── 33. On-Neck Pattern ──────────────────────────────────────────────────
def on_neck(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] < c[i-1] and
            abs(c[i] - l[i-1]) / max(abs(h[i-1] - l[i-1]), 1e-10) < 0.05):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('On_Neck', on_neck, 'Bullish closes at prior low — bearish continuation')


# ── 34. In-Neck Pattern ──────────────────────────────────────────────────
def in_neck(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] < c[i-1] and
            abs(c[i] - c[i-1]) / max(abs(h[i-1] - l[i-1]), 1e-10) < 0.1):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('In_Neck', in_neck, 'Bullish closes near prior close — bearish continuation')


# ── 35. Thrusting Pattern ────────────────────────────────────────────────
def thrusting(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        mid_prev = (o[i-1] + c[i-1]) / 2.0
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            o[i] < l[i-1] and
            c[i] > c[i-1] and c[i] < mid_prev):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Thrusting', thrusting, 'Bullish closes below prior midpoint — bearish continuation')


# ── 36. Homing Pigeon ────────────────────────────────────────────────────
def homing_pigeon(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (o[i-1] > c[i-1] and o[i] > c[i] and
            o[i] <= o[i-1] and c[i] >= c[i-1] and
            body[i] < body[i-1] * 0.6):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Homing_Pigeon', homing_pigeon, 'Small bearish inside large bearish — bullish reversal')


# ── 37. Matching Low ─────────────────────────────────────────────────────
def matching_low(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if (o[i-1] > c[i-1] and o[i] > c[i] and
            abs(c[i] - c[i-1]) / max(c[i-1], 1e-10) < 0.002):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Matching_Low', matching_low, 'Two bearish candles with equal closes — support found')


# ── 38. Kicking Bullish ──────────────────────────────────────────────────
def kicking_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i-1] == 0 or rng[i] == 0:
            continue
        if (o[i-1] > c[i-1] and body[i-1] / rng[i-1] >= 0.85 and
            c[i] > o[i] and body[i] / rng[i] >= 0.85 and
            o[i] > o[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Kicking_Bull', kicking_bullish, 'Bearish marubozu + gap up + bullish marubozu')


# ── 39. Kicking Bearish ──────────────────────────────────────────────────
def kicking_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i-1] == 0 or rng[i] == 0:
            continue
        if (c[i-1] > o[i-1] and body[i-1] / rng[i-1] >= 0.85 and
            o[i] > c[i] and body[i] / rng[i] >= 0.85 and
            o[i] < o[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Kicking_Bear', kicking_bearish, 'Bullish marubozu + gap down + bearish marubozu')


# ── 40. Separating Lines Bullish ──────────────────────────────────────────
def separating_lines_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (o[i-1] > c[i-1] and c[i] > o[i] and
            abs(o[i] - o[i-1]) / max(o[i-1], 1e-10) < 0.002 and
            body[i] / rng[i] >= 0.6):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Separating_Lines_Bull', separating_lines_bullish, 'Same open — bearish then bullish marubozu')


# ── 41. Separating Lines Bearish ──────────────────────────────────────────
def separating_lines_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if rng[i] == 0:
            continue
        if (c[i-1] > o[i-1] and o[i] > c[i] and
            abs(o[i] - o[i-1]) / max(o[i-1], 1e-10) < 0.002 and
            body[i] / rng[i] >= 0.6):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Separating_Lines_Bear', separating_lines_bearish, 'Same open — bullish then bearish marubozu')


# ── 42. Window Gap Up ────────────────────────────────────────────────────
def window_gap_up(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if l[i] > h[i-1]:
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Window_Gap_Up', window_gap_up, 'Gap up — bullish continuation')


# ── 43. Window Gap Down ──────────────────────────────────────────────────
def window_gap_down(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(1, len(df)):
        if h[i] < l[i-1]:
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Window_Gap_Down', window_gap_down, 'Gap down — bearish continuation')


# ═══════════════════════════════════════════════════════════════════════════════
#  ADDITIONAL THREE-CANDLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 44. Morning Doji Star ────────────────────────────────────────────────
def morning_doji_star(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-1] == 0:
            continue
        if (o[i-2] > c[i-2] and _body(o[i-2], c[i-2]) > 0 and
            body[i-1] / rng[i-1] < 0.1 and
            c[i] > o[i] and _body(o[i], c[i]) > _body(o[i-2], c[i-2]) * 0.5 and
            c[i] > (o[i-2] + c[i-2]) / 2.0):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Morning_Doji_Star', morning_doji_star, 'Bear + doji + bull — strong bullish reversal')


# ── 45. Evening Doji Star ────────────────────────────────────────────────
def evening_doji_star(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-1] == 0:
            continue
        if (c[i-2] > o[i-2] and _body(o[i-2], c[i-2]) > 0 and
            body[i-1] / rng[i-1] < 0.1 and
            o[i] > c[i] and _body(o[i], c[i]) > _body(o[i-2], c[i-2]) * 0.5 and
            c[i] < (o[i-2] + c[i-2]) / 2.0):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Evening_Doji_Star', evening_doji_star, 'Bull + doji + bear — strong bearish reversal')


# ── 46. Three Outside Up ────────────────────────────────────────────────
def three_outside_up(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and
            c[i-1] > o[i-1] and o[i-1] <= c[i-2] and c[i-1] >= o[i-2] and
            c[i] > o[i] and c[i] > c[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Outside_Up', three_outside_up, 'Engulfing + bullish confirmation')


# ── 47. Three Outside Down ──────────────────────────────────────────────
def three_outside_down(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and
            o[i-1] > c[i-1] and o[i-1] >= c[i-2] and c[i-1] <= o[i-2] and
            o[i] > c[i] and c[i] < c[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Outside_Down', three_outside_down, 'Engulfing + bearish confirmation')


# ── 48. Abandoned Baby Bottom ───────────────────────────────────────────
def abandoned_baby_bottom(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-1] == 0:
            continue
        if (o[i-2] > c[i-2] and
            body[i-1] / rng[i-1] < 0.1 and
            h[i-1] < l[i-2] and
            l[i] > h[i-1] and
            c[i] > o[i]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Abandoned_Baby_Bottom', abandoned_baby_bottom, 'Gap down doji + gap up — strong bullish reversal')


# ── 49. Abandoned Baby Top ──────────────────────────────────────────────
def abandoned_baby_top(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-1] == 0:
            continue
        if (c[i-2] > o[i-2] and
            body[i-1] / rng[i-1] < 0.1 and
            l[i-1] > h[i-2] and
            h[i] < l[i-1] and
            o[i] > c[i]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Abandoned_Baby_Top', abandoned_baby_top, 'Gap up doji + gap down — strong bearish reversal')


# ── 50. Tri-Star Bottom ─────────────────────────────────────────────────
def tri_star_bottom(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-2] == 0 or rng[i-1] == 0 or rng[i] == 0:
            continue
        if (body[i-2] / rng[i-2] < 0.1 and
            body[i-1] / rng[i-1] < 0.1 and
            body[i] / rng[i] < 0.1):
            mid1 = (o[i-1] + c[i-1]) / 2.0
            mid0 = (o[i-2] + c[i-2]) / 2.0
            mid2 = (o[i] + c[i]) / 2.0
            if mid1 < mid0 and mid1 < mid2:
                sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tri_Star_Bottom', tri_star_bottom, 'Three dojis with middle lowest — bullish reversal')


# ── 51. Tri-Star Top ────────────────────────────────────────────────────
def tri_star_top(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if rng[i-2] == 0 or rng[i-1] == 0 or rng[i] == 0:
            continue
        if (body[i-2] / rng[i-2] < 0.1 and
            body[i-1] / rng[i-1] < 0.1 and
            body[i] / rng[i] < 0.1):
            mid1 = (o[i-1] + c[i-1]) / 2.0
            mid0 = (o[i-2] + c[i-2]) / 2.0
            mid2 = (o[i] + c[i]) / 2.0
            if mid1 > mid0 and mid1 > mid2:
                sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tri_Star_Top', tri_star_top, 'Three dojis with middle highest — bearish reversal')


# ── 52. Unique Three River Bottom ───────────────────────────────────────
def unique_three_river(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and body[i-2] > 0 and
            o[i-1] > c[i-1] and c[i-1] >= c[i-2] and l[i-1] < l[i-2] and
            c[i] > o[i] and body[i] < body[i-1] * 0.5 and
            c[i] < c[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Unique_Three_River', unique_three_river, 'Bear + harami-like bear + small bull — bullish')


# ── 53. Concealing Baby Swallow ──────────────────────────────────────────
def concealing_baby_swallow(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(3, len(df)):
        if rng[i-3] == 0 or rng[i-2] == 0:
            continue
        if (o[i-3] > c[i-3] and body[i-3] / rng[i-3] >= 0.85 and
            o[i-2] > c[i-2] and body[i-2] / rng[i-2] >= 0.85 and
            o[i-1] > c[i-1] and h[i-1] > c[i-2] and
            o[i] > c[i] and o[i] >= h[i-1] and c[i] <= l[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Concealing_Baby_Swallow', concealing_baby_swallow, 'Four bearish: 2 marubozu + gap up bear + engulfing')


# ── 54. Stick Sandwich ──────────────────────────────────────────────────
def stick_sandwich(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and
            c[i-1] > o[i-1] and
            o[i] > c[i] and
            abs(c[i] - c[i-2]) / max(c[i-2], 1e-10) < 0.002):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Stick_Sandwich', stick_sandwich, 'Bear-bull-bear with equal closes on bears — bullish')


# ── 55. Ladder Bottom ───────────────────────────────────────────────────
def ladder_bottom(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    rng = _range_(h, l)
    upper = _upper_wick(h, o, c)
    sig = np.zeros(len(df))
    for i in range(4, len(df)):
        if (o[i-4] > c[i-4] and o[i-3] > c[i-3] and o[i-2] > c[i-2] and
            c[i-4] > c[i-3] > c[i-2] and
            rng[i-1] > 0 and upper[i-1] / rng[i-1] >= 0.5 and o[i-1] > c[i-1] and
            c[i] > o[i] and c[i] > o[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Ladder_Bottom', ladder_bottom, 'Three falling bears + shooting star bear + bullish')


# ── 56. Advance Block ───────────────────────────────────────────────────
def advance_block(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    rng = _range_(h, l)
    upper = _upper_wick(h, o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and c[i] > o[i] and
            c[i] > c[i-1] > c[i-2] and
            body[i] < body[i-1] < body[i-2] and
            rng[i] > 0 and upper[i] / rng[i] > 0.3):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Advance_Block', advance_block, 'Three rising bulls with shrinking bodies — bearish')


# ── 57. Deliberation ────────────────────────────────────────────────────
def deliberation(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        b0, b1, b2 = body[i-2], body[i-1], body[i]
        if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and c[i] > o[i] and
            b0 > 0 and b1 > 0 and
            b2 < b0 * 0.4 and b2 < b1 * 0.4 and
            o[i] >= c[i-1] * 0.998):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Deliberation', deliberation, 'Two large bulls + small spinning top — bearish stalling')


# ── 58. Identical Three Crows ───────────────────────────────────────────
def identical_three_crows(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and o[i-1] > c[i-1] and o[i] > c[i] and
            c[i] < c[i-1] < c[i-2] and
            abs(o[i-1] - c[i-2]) / max(c[i-2], 1e-10) < 0.003 and
            abs(o[i] - c[i-1]) / max(c[i-1], 1e-10) < 0.003):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Identical_Three_Crows', identical_three_crows, 'Three bears each opening at prior close')


# ── 59. Upside Gap Two Crows ────────────────────────────────────────────
def upside_gap_two_crows(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and
            o[i-1] > c[i-1] and o[i-1] > c[i-2] and c[i-1] > c[i-2] and
            o[i] > c[i] and o[i] > o[i-1] and c[i] < c[i-1] and c[i] > c[i-2]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Upside_Gap_Two_Crows', upside_gap_two_crows, 'Bull + gap up + two bearish candles — bearish reversal')


# ── 60. Three-Line Strike Bullish ───────────────────────────────────────
def three_line_strike_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(3, len(df)):
        if (c[i-3] > o[i-3] and c[i-2] > o[i-2] and c[i-1] > o[i-1] and
            c[i-1] > c[i-2] > c[i-3] and
            o[i] > c[i] and o[i] >= c[i-1] and c[i] <= o[i-3]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Line_Strike_Bull', three_line_strike_bullish, 'Three bulls + large engulfing bear — bullish continuation')


# ── 61. Three-Line Strike Bearish ───────────────────────────────────────
def three_line_strike_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(3, len(df)):
        if (o[i-3] > c[i-3] and o[i-2] > c[i-2] and o[i-1] > c[i-1] and
            c[i-1] < c[i-2] < c[i-3] and
            c[i] > o[i] and c[i] >= o[i-3] and o[i] <= c[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Three_Line_Strike_Bear', three_line_strike_bearish, 'Three bears + large engulfing bull — bearish continuation')


# ── 62. Tasuki Gap Bullish ──────────────────────────────────────────────
def tasuki_gap_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and
            o[i-1] > c[i-2] and
            o[i] > c[i] and
            o[i] < c[i-1] and o[i] > o[i-1] and
            c[i] > o[i-1] and c[i] < c[i-2]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tasuki_Gap_Bull', tasuki_gap_bullish, 'Bull gap up bull + bearish that fails to fill gap')


# ── 63. Tasuki Gap Bearish ──────────────────────────────────────────────
def tasuki_gap_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and o[i-1] > c[i-1] and
            c[i-1] < o[i-2] and
            c[i] > o[i] and
            c[i] < o[i-1] and c[i] > c[i-1] and
            o[i] > c[i-1] and o[i] < o[i-2]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Tasuki_Gap_Bear', tasuki_gap_bearish, 'Bear gap down bear + bullish that fails to fill gap')


# ── 64. Side-by-Side White Lines ────────────────────────────────────────
def side_by_side_white(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and
            c[i-1] > o[i-1] and o[i-1] > c[i-2] and
            c[i] > o[i] and
            abs(o[i] - o[i-1]) / max(o[i-1], 1e-10) < 0.003 and
            abs(body[i] - body[i-1]) / max(body[i-1], 1e-10) < 0.2):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Side_By_Side_White', side_by_side_white, 'Gap up + two similar bullish candles')


# ═══════════════════════════════════════════════════════════════════════════════
#  FIVE-CANDLE / CONTINUATION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 65. Rising Three Methods ────────────────────────────────────────────
def rising_three_methods(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(4, len(df)):
        if not (c[i-4] > o[i-4]):
            continue
        mid_bear = True
        for j in range(i-3, i):
            if c[j] >= o[j]:
                mid_bear = False
                break
            if h[j] > h[i-4] or l[j] < l[i-4]:
                mid_bear = False
                break
        if mid_bear and c[i] > o[i] and c[i] > c[i-4] and o[i] > c[i-1]:
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rising_Three_Methods', rising_three_methods, 'Bull + 3 small bears inside + bull — bullish continuation')


# ── 66. Falling Three Methods ───────────────────────────────────────────
def falling_three_methods(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(4, len(df)):
        if not (o[i-4] > c[i-4]):
            continue
        mid_bull = True
        for j in range(i-3, i):
            if o[j] >= c[j]:
                mid_bull = False
                break
            if h[j] > h[i-4] or l[j] < l[i-4]:
                mid_bull = False
                break
        if mid_bull and o[i] > c[i] and c[i] < c[i-4] and o[i] < c[i-1]:
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Falling_Three_Methods', falling_three_methods, 'Bear + 3 small bulls inside + bear — bearish continuation')


# ── 67. Mat Hold Bullish ────────────────────────────────────────────────
def mat_hold(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(4, len(df)):
        if not (c[i-4] > o[i-4]):
            continue
        if not (o[i-3] > c[i-3] and o[i-3] > c[i-4]):
            continue
        mid_ok = True
        for j in range(i-3, i):
            if l[j] < l[i-4]:
                mid_ok = False
                break
        if mid_ok and c[i] > o[i] and c[i] > h[i-4]:
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Mat_Hold', mat_hold, 'Bull + gap up small bears + bull breakout — bullish')


# ── 68. Upside Gap Three Methods ────────────────────────────────────────
def upside_gap_three_methods(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (c[i-2] > o[i-2] and c[i-1] > o[i-1] and
            o[i-1] > c[i-2] and
            o[i] > c[i] and o[i] >= c[i-1] and c[i] <= o[i-2]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Upside_Gap_Three', upside_gap_three_methods, 'Two bulls with gap + bearish fills gap — bullish continuation')


# ── 69. Downside Gap Three Methods ──────────────────────────────────────
def downside_gap_three_methods(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    for i in range(2, len(df)):
        if (o[i-2] > c[i-2] and o[i-1] > c[i-1] and
            c[i-1] < o[i-2] and
            c[i] > o[i] and c[i] >= o[i-2] and o[i] <= c[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Downside_Gap_Three', downside_gap_three_methods, 'Two bears with gap + bullish fills gap — bearish continuation')


# ── 70. High Price Gapping Play ─────────────────────────────────────────
def high_price_gapping_play(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    rng = _range_(h, l)
    sig = np.zeros(len(df))
    for i in range(3, len(df)):
        if rng[i-3] == 0:
            continue
        if not (c[i-3] > o[i-3] and body[i-3] / rng[i-3] >= 0.6):
            continue
        small = True
        for j in range(i-2, i):
            if rng[j] == 0 or body[j] / rng[j] > 0.4:
                small = False
                break
            if l[j] < c[i-3]:
                small = False
                break
        if small and c[i] > o[i] and c[i] > max(h[i-2], h[i-1]):
            sig[i] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('High_Price_Gapping', high_price_gapping_play, 'Large bull + 2 small candles near high + breakout')


# ── 71. Low Price Gapping Play ──────────────────────────────────────────
def low_price_gapping_play(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = _body(o, c)
    rng = _range_(h, l)
    sig = np.zeros(len(df))
    for i in range(3, len(df)):
        if rng[i-3] == 0:
            continue
        if not (o[i-3] > c[i-3] and body[i-3] / rng[i-3] >= 0.6):
            continue
        small = True
        for j in range(i-2, i):
            if rng[j] == 0 or body[j] / rng[j] > 0.4:
                small = False
                break
            if h[j] > c[i-3]:
                small = False
                break
        if small and o[i] > c[i] and c[i] < min(l[i-2], l[i-1]):
            sig[i] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Low_Price_Gapping', low_price_gapping_play, 'Large bear + 2 small candles near low + breakdown')
