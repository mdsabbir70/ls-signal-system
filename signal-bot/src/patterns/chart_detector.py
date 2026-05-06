"""
Chart Pattern Detector
Detects structural patterns: Double/Triple Top/Bottom, Head & Shoulders,
Triangles, Wedges, Flags, Pennants, Cup & Handle, Rectangle,
Rounding, S/R Breakout, Liquidity sweeps.

Uses swing high/low detection to find pivot points.
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
        'category': 'chart_pattern',
    })


def get_all_chart_patterns() -> list[dict]:
    return PATTERN_REGISTRY.copy()


# ── Pivot / Swing detection ──────────────────────────────────────────────────

def _swing_highs(highs: np.ndarray, window: int = 5) -> np.ndarray:
    """Returns boolean array where True = local high (swing high)."""
    n = len(highs)
    result = np.zeros(n, dtype=bool)
    for i in range(window, n - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            result[i] = True
    return result


def _swing_lows(lows: np.ndarray, window: int = 5) -> np.ndarray:
    n = len(lows)
    result = np.zeros(n, dtype=bool)
    for i in range(window, n - window):
        if lows[i] == min(lows[i - window:i + window + 1]):
            result[i] = True
    return result


def _find_sr_levels(highs: np.ndarray, lows: np.ndarray, window: int = 10,
                     tolerance: float = 0.002) -> tuple[np.ndarray, np.ndarray]:
    """Find support and resistance levels from swing highs/lows."""
    sh = _swing_highs(highs, window)
    sl = _swing_lows(lows, window)

    resistance_levels = highs[sh]
    support_levels = lows[sl]

    return support_levels, resistance_levels


# ═══════════════════════════════════════════════════════════════════════════════
#  DOUBLE TOP / DOUBLE BOTTOM
# ═══════════════════════════════════════════════════════════════════════════════

def double_bottom(df: pd.DataFrame) -> pd.Series:
    """Double bottom: two similar lows with a peak between them."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_l = _swing_lows(l, window=5)
    sig = np.zeros(len(df))

    low_indices = np.where(sw_l)[0]
    for i in range(1, len(low_indices)):
        idx1, idx2 = low_indices[i - 1], low_indices[i]
        if idx2 - idx1 < 5 or idx2 - idx1 > 60:
            continue
        # Two lows within tolerance
        avg_price = (l[idx1] + l[idx2]) / 2.0
        if avg_price == 0:
            continue
        if abs(l[idx1] - l[idx2]) / avg_price < 0.005:
            # Find the peak between them
            mid_high = max(h[idx1:idx2 + 1])
            neckline = mid_high
            # Confirm: current price breaks above neckline
            if idx2 + 1 < len(df) and c[idx2 + 1] > neckline * 0.998:
                sig[min(idx2 + 1, len(df) - 1)] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Double_Bottom', double_bottom, 'Two equal lows + neckline break — bullish')


def double_top(df: pd.DataFrame) -> pd.Series:
    """Double top: two similar highs with a trough between them."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_h = _swing_highs(h, window=5)
    sig = np.zeros(len(df))

    high_indices = np.where(sw_h)[0]
    for i in range(1, len(high_indices)):
        idx1, idx2 = high_indices[i - 1], high_indices[i]
        if idx2 - idx1 < 5 or idx2 - idx1 > 60:
            continue
        avg_price = (h[idx1] + h[idx2]) / 2.0
        if avg_price == 0:
            continue
        if abs(h[idx1] - h[idx2]) / avg_price < 0.005:
            mid_low = min(l[idx1:idx2 + 1])
            neckline = mid_low
            if idx2 + 1 < len(df) and c[idx2 + 1] < neckline * 1.002:
                sig[min(idx2 + 1, len(df) - 1)] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Double_Top', double_top, 'Two equal highs + neckline break — bearish')


# ═══════════════════════════════════════════════════════════════════════════════
#  HEAD & SHOULDERS
# ═══════════════════════════════════════════════════════════════════════════════

def head_and_shoulders(df: pd.DataFrame) -> pd.Series:
    """Classic H&S: left shoulder, higher head, right shoulder."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_h = _swing_highs(h, window=5)
    sig = np.zeros(len(df))

    high_indices = np.where(sw_h)[0]
    for i in range(2, len(high_indices)):
        ls_idx = high_indices[i - 2]
        hd_idx = high_indices[i - 1]
        rs_idx = high_indices[i]

        if rs_idx - ls_idx > 80 or rs_idx - ls_idx < 10:
            continue

        ls_h, hd_h, rs_h = h[ls_idx], h[hd_idx], h[rs_idx]

        # Head must be highest, shoulders roughly equal
        if (hd_h > ls_h and hd_h > rs_h and
            abs(ls_h - rs_h) / max(ls_h, 1e-10) < 0.01):
            # Neckline: lowest point between shoulders
            neckline = min(l[ls_idx:rs_idx + 1])
            # Confirm break below neckline
            if rs_idx + 1 < len(df) and c[rs_idx + 1] < neckline:
                sig[min(rs_idx + 1, len(df) - 1)] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Head_Shoulders', head_and_shoulders, 'Head & Shoulders top — bearish')


def inverse_head_and_shoulders(df: pd.DataFrame) -> pd.Series:
    """Inverse H&S: left shoulder, lower head, right shoulder."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_l = _swing_lows(l, window=5)
    sig = np.zeros(len(df))

    low_indices = np.where(sw_l)[0]
    for i in range(2, len(low_indices)):
        ls_idx = low_indices[i - 2]
        hd_idx = low_indices[i - 1]
        rs_idx = low_indices[i]

        if rs_idx - ls_idx > 80 or rs_idx - ls_idx < 10:
            continue

        ls_l, hd_l, rs_l = l[ls_idx], l[hd_idx], l[rs_idx]

        if (hd_l < ls_l and hd_l < rs_l and
            abs(ls_l - rs_l) / max(ls_l, 1e-10) < 0.01):
            neckline = max(h[ls_idx:rs_idx + 1])
            if rs_idx + 1 < len(df) and c[rs_idx + 1] > neckline:
                sig[min(rs_idx + 1, len(df) - 1)] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Inv_Head_Shoulders', inverse_head_and_shoulders, 'Inverse H&S bottom — bullish')


# ═══════════════════════════════════════════════════════════════════════════════
#  TRIANGLES
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_triangle(df: pd.DataFrame, kind: str) -> pd.Series:
    """
    kind: 'ascending' | 'descending' | 'symmetrical'
    Uses last N swing highs/lows to fit trendlines.
    """
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 30
    window = 4

    for i in range(lookback + window, len(df)):
        segment_h = h[i - lookback:i]
        segment_l = l[i - lookback:i]
        segment_c = c[i - lookback:i]

        sh = _swing_highs(segment_h, window)
        sl = _swing_lows(segment_l, window)

        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            continue

        # Slopes of highs and lows trendlines
        h_vals = segment_h[sh_idx[-2:]]
        l_vals = segment_l[sl_idx[-2:]]
        h_slope = h_vals[-1] - h_vals[-2]
        l_slope = l_vals[-1] - l_vals[-2]
        avg_price = np.mean(segment_c)
        if avg_price == 0:
            continue
        h_slope_norm = h_slope / avg_price
        l_slope_norm = l_slope / avg_price

        is_ascending = h_slope_norm < 0.001 and l_slope_norm > 0.001
        is_descending = h_slope_norm < -0.001 and l_slope_norm < 0.001
        is_symmetrical = h_slope_norm < -0.0005 and l_slope_norm > 0.0005

        if kind == 'ascending' and is_ascending:
            # Breakout above flat resistance
            if c[i] > h_vals[-1]:
                sig[i] = 1
        elif kind == 'descending' and is_descending:
            if c[i] < l_vals[-1]:
                sig[i] = -1
        elif kind == 'symmetrical' and is_symmetrical:
            if c[i] > h_vals[-1]:
                sig[i] = 1
            elif c[i] < l_vals[-1]:
                sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)


def ascending_triangle(df):
    return _detect_triangle(df, 'ascending')

def descending_triangle(df):
    return _detect_triangle(df, 'descending')

def symmetrical_triangle(df):
    return _detect_triangle(df, 'symmetrical')

_reg('Ascending_Triangle', ascending_triangle, 'Flat top + rising lows — bullish breakout')
_reg('Descending_Triangle', descending_triangle, 'Flat bottom + falling highs — bearish breakdown')
_reg('Symmetrical_Triangle', symmetrical_triangle, 'Converging trendlines — breakout either way')


# ═══════════════════════════════════════════════════════════════════════════════
#  WEDGES
# ═══════════════════════════════════════════════════════════════════════════════

def falling_wedge(df: pd.DataFrame) -> pd.Series:
    """Falling wedge: both highs and lows falling, converging — bullish."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 30
    window = 4

    for i in range(lookback + window, len(df)):
        segment_h = h[i - lookback:i]
        segment_l = l[i - lookback:i]

        sh = _swing_highs(segment_h, window)
        sl = _swing_lows(segment_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            continue

        h_vals = segment_h[sh_idx[-2:]]
        l_vals = segment_l[sl_idx[-2:]]
        h_slope = h_vals[-1] - h_vals[-2]
        l_slope = l_vals[-1] - l_vals[-2]

        # Both falling, highs falling faster (converging)
        if h_slope < 0 and l_slope < 0 and h_slope < l_slope:
            if c[i] > h_vals[-1]:
                sig[i] = 1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Falling_Wedge', falling_wedge, 'Both lines falling + converging — bullish breakout')


def rising_wedge(df: pd.DataFrame) -> pd.Series:
    """Rising wedge: both highs and lows rising, converging — bearish."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 30
    window = 4

    for i in range(lookback + window, len(df)):
        segment_h = h[i - lookback:i]
        segment_l = l[i - lookback:i]

        sh = _swing_highs(segment_h, window)
        sl = _swing_lows(segment_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            continue

        h_vals = segment_h[sh_idx[-2:]]
        l_vals = segment_l[sl_idx[-2:]]
        h_slope = h_vals[-1] - h_vals[-2]
        l_slope = l_vals[-1] - l_vals[-2]

        if h_slope > 0 and l_slope > 0 and l_slope > h_slope:
            if c[i] < l_vals[-1]:
                sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rising_Wedge', rising_wedge, 'Both lines rising + converging — bearish breakdown')


# ═══════════════════════════════════════════════════════════════════════════════
#  SUPPORT / RESISTANCE
# ═══════════════════════════════════════════════════════════════════════════════

def sr_breakout(df: pd.DataFrame) -> pd.Series:
    """Break above resistance or below support."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 40
    window = 5

    for i in range(lookback, len(df)):
        seg_h = h[i - lookback:i]
        seg_l = l[i - lookback:i]

        sh = _swing_highs(seg_h, window)
        sl = _swing_lows(seg_l, window)

        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 1 or len(sl_idx) < 1:
            continue

        resistance = np.max(seg_h[sh_idx])
        support = np.min(seg_l[sl_idx])

        if c[i] > resistance:
            sig[i] = 1
        elif c[i] < support:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('SR_Breakout', sr_breakout, 'Price breaks above resistance or below support')


def sr_rejection(df: pd.DataFrame) -> pd.Series:
    """Rejection at support (bullish) or resistance (bearish)."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))
    lookback = 40
    window = 5

    for i in range(lookback, len(df)):
        seg_h = h[i - lookback:i]
        seg_l = l[i - lookback:i]

        sh = _swing_highs(seg_h, window)
        sl = _swing_lows(seg_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 1 or len(sl_idx) < 1:
            continue

        resistance = np.max(seg_h[sh_idx])
        support = np.min(seg_l[sl_idx])
        rng = h[i] - l[i]
        if rng == 0:
            continue

        # Rejection at support: long lower wick near support, closes bullish
        lower_wick = min(o[i], c[i]) - l[i]
        if (l[i] <= support * 1.003 and lower_wick / rng > 0.5 and c[i] > o[i]):
            sig[i] = 1

        # Rejection at resistance: long upper wick near resistance, closes bearish
        upper_wick = h[i] - max(o[i], c[i])
        if (h[i] >= resistance * 0.997 and upper_wick / rng > 0.5 and c[i] < o[i]):
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('SR_Rejection', sr_rejection, 'Rejection candle at support/resistance level')


def breakout_retest(df: pd.DataFrame) -> pd.Series:
    """Breakout above resistance then retest as support (or vice versa)."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 40
    window = 5

    for i in range(lookback + 3, len(df)):
        seg_h = h[i - lookback - 3:i - 3]
        seg_l = l[i - lookback - 3:i - 3]

        sh = _swing_highs(seg_h, window)
        sl = _swing_lows(seg_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 1 or len(sl_idx) < 1:
            continue

        resistance = np.max(seg_h[sh_idx])
        support = np.min(seg_l[sl_idx])
        avg_price = (resistance + support) / 2.0
        if avg_price == 0:
            continue
        tol = avg_price * 0.003

        # Bullish: broke above resistance (c[i-2] > resistance), retested (l[i-1] near resistance), bounced (c[i] > resistance)
        if (c[i - 2] > resistance and l[i - 1] <= resistance + tol and
            c[i] > resistance and c[i] > c[i - 1]):
            sig[i] = 1

        # Bearish: broke below support, retested, continued down
        if (c[i - 2] < support and h[i - 1] >= support - tol and
            c[i] < support and c[i] < c[i - 1]):
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Breakout_Retest', breakout_retest, 'Breakout then retest of broken level')


# ═══════════════════════════════════════════════════════════════════════════════
#  LIQUIDITY PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

def liquidity_sweep(df: pd.DataFrame) -> pd.Series:
    """Liquidity sweep: price wicks beyond S/R to grab stops, then reverses."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))
    lookback = 30
    window = 5

    for i in range(lookback, len(df)):
        seg_h = h[i - lookback:i]
        seg_l = l[i - lookback:i]

        sh = _swing_highs(seg_h, window)
        sl = _swing_lows(seg_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 1 or len(sl_idx) < 1:
            continue

        resistance = np.max(seg_h[sh_idx])
        support = np.min(seg_l[sl_idx])

        # Bullish sweep: wick below support but closes above support (stop hunt below)
        if (l[i] < support and c[i] > support and c[i] > o[i]):
            sig[i] = 1

        # Bearish sweep: wick above resistance but closes below resistance
        if (h[i] > resistance and c[i] < resistance and c[i] < o[i]):
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Liquidity_Sweep', liquidity_sweep, 'Wick beyond S/R grabs stops then reverses')


def stop_hunt(df: pd.DataFrame) -> pd.Series:
    """Stop hunt: sudden spike beyond recent range then sharp reversal."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))

    for i in range(10, len(df)):
        recent_high = np.max(h[i - 10:i])
        recent_low = np.min(l[i - 10:i])
        rng = h[i] - l[i]
        if rng == 0:
            continue
        body = abs(c[i] - o[i])

        # Bullish stop hunt: new low below range, but closes in upper 1/3
        if (l[i] < recent_low and c[i] > l[i] + 0.66 * rng and c[i] > o[i]):
            sig[i] = 1

        # Bearish stop hunt: new high above range, closes in lower 1/3
        if (h[i] > recent_high and c[i] < h[i] - 0.66 * rng and c[i] < o[i]):
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Stop_Hunt', stop_hunt, 'Price spikes beyond range + reverses — stop hunt')


def volume_spike_reversal(df: pd.DataFrame) -> pd.Series:
    """High volume + reversal candle = institutional interest."""
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))

    has_volume = 'volume' in df.columns
    if not has_volume:
        return pd.Series(sig, index=df.index, dtype=int)

    vol = df['volume'].values.astype(float)

    for i in range(20, len(df)):
        avg_vol = np.mean(vol[i - 20:i])
        if avg_vol == 0:
            continue

        # Volume >= 2x average
        if vol[i] < 2.0 * avg_vol:
            continue

        rng = h[i] - l[i]
        if rng == 0:
            continue
        lower_wick = min(o[i], c[i]) - l[i]
        upper_wick = h[i] - max(o[i], c[i])

        # Bullish: high volume + hammer / bullish close
        if c[i] > o[i] and lower_wick / rng > 0.4:
            sig[i] = 1

        # Bearish: high volume + shooting star / bearish close
        if c[i] < o[i] and upper_wick / rng > 0.4:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Volume_Reversal', volume_spike_reversal, 'High volume spike + reversal candle')


# ═══════════════════════════════════════════════════════════════════════════════
#  TRIPLE TOP / TRIPLE BOTTOM
# ═══════════════════════════════════════════════════════════════════════════════

def triple_bottom(df: pd.DataFrame) -> pd.Series:
    """Triple bottom: three similar lows."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_l = _swing_lows(l, window=5)
    sig = np.zeros(len(df))
    low_indices = np.where(sw_l)[0]
    for i in range(2, len(low_indices)):
        idx1, idx2, idx3 = low_indices[i-2], low_indices[i-1], low_indices[i]
        if idx3 - idx1 > 90 or idx3 - idx1 < 15:
            continue
        avg = (l[idx1] + l[idx2] + l[idx3]) / 3.0
        if avg == 0:
            continue
        if (abs(l[idx1] - avg) / avg < 0.005 and
            abs(l[idx2] - avg) / avg < 0.005 and
            abs(l[idx3] - avg) / avg < 0.005):
            neckline = max(h[idx1:idx3+1])
            if idx3 + 1 < len(df) and c[idx3+1] > neckline * 0.998:
                sig[min(idx3+1, len(df)-1)] = 1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Triple_Bottom', triple_bottom, 'Three equal lows + neckline break — bullish')


def triple_top(df: pd.DataFrame) -> pd.Series:
    """Triple top: three similar highs."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sw_h = _swing_highs(h, window=5)
    sig = np.zeros(len(df))
    high_indices = np.where(sw_h)[0]
    for i in range(2, len(high_indices)):
        idx1, idx2, idx3 = high_indices[i-2], high_indices[i-1], high_indices[i]
        if idx3 - idx1 > 90 or idx3 - idx1 < 15:
            continue
        avg = (h[idx1] + h[idx2] + h[idx3]) / 3.0
        if avg == 0:
            continue
        if (abs(h[idx1] - avg) / avg < 0.005 and
            abs(h[idx2] - avg) / avg < 0.005 and
            abs(h[idx3] - avg) / avg < 0.005):
            neckline = min(l[idx1:idx3+1])
            if idx3 + 1 < len(df) and c[idx3+1] < neckline * 1.002:
                sig[min(idx3+1, len(df)-1)] = -1
    return pd.Series(sig, index=df.index, dtype=int)

_reg('Triple_Top', triple_top, 'Three equal highs + neckline break — bearish')


# ═══════════════════════════════════════════════════════════════════════════════
#  CUP AND HANDLE
# ═══════════════════════════════════════════════════════════════════════════════

def cup_and_handle(df: pd.DataFrame) -> pd.Series:
    """Cup and Handle: U-shaped bottom with small pullback then breakout."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    cup_len = 30

    for i in range(cup_len + 10, len(df)):
        seg_c = c[i - cup_len - 10:i - 10]
        seg_h = h[i - cup_len - 10:i - 10]

        if len(seg_c) < cup_len:
            continue

        left_rim = seg_c[0]
        right_rim = seg_c[-1]
        cup_bottom = np.min(seg_c)
        bottom_idx = np.argmin(seg_c)

        if left_rim == 0 or cup_bottom == 0:
            continue

        # Cup: U-shape — bottom in middle third, rims similar height
        if not (cup_len * 0.25 < bottom_idx < cup_len * 0.75):
            continue
        if abs(left_rim - right_rim) / left_rim > 0.02:
            continue
        cup_depth = (left_rim - cup_bottom) / left_rim
        if cup_depth < 0.02 or cup_depth > 0.15:
            continue

        # Handle: small pullback in last 10 candles
        handle_seg = c[i - 10:i]
        handle_low = np.min(handle_seg)
        handle_drop = (right_rim - handle_low) / max(right_rim, 1e-10)
        if handle_drop < 0.005 or handle_drop > cup_depth * 0.5:
            continue

        # Breakout above right rim
        if c[i] > right_rim and c[i] > c[i-1]:
            sig[i] = 1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Cup_Handle', cup_and_handle, 'U-shaped recovery + handle pullback + breakout — bullish')


def inverse_cup_and_handle(df: pd.DataFrame) -> pd.Series:
    """Inverse Cup and Handle: inverted U with small bounce then breakdown."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    cup_len = 30

    for i in range(cup_len + 10, len(df)):
        seg_c = c[i - cup_len - 10:i - 10]

        if len(seg_c) < cup_len:
            continue

        left_rim = seg_c[0]
        right_rim = seg_c[-1]
        cup_top = np.max(seg_c)
        top_idx = np.argmax(seg_c)

        if left_rim == 0 or cup_top == 0:
            continue

        if not (cup_len * 0.25 < top_idx < cup_len * 0.75):
            continue
        if abs(left_rim - right_rim) / max(left_rim, 1e-10) > 0.02:
            continue
        cup_height = (cup_top - left_rim) / max(left_rim, 1e-10)
        if cup_height < 0.02 or cup_height > 0.15:
            continue

        handle_seg = c[i - 10:i]
        handle_high = np.max(handle_seg)
        handle_bounce = (handle_high - right_rim) / max(right_rim, 1e-10)
        if handle_bounce < 0.005 or handle_bounce > cup_height * 0.5:
            continue

        if c[i] < right_rim and c[i] < c[i-1]:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Inv_Cup_Handle', inverse_cup_and_handle, 'Inverted U + handle bounce + breakdown — bearish')


# ═══════════════════════════════════════════════════════════════════════════════
#  FLAGS & PENNANTS
# ═══════════════════════════════════════════════════════════════════════════════

def bull_flag(df: pd.DataFrame) -> pd.Series:
    """Bull Flag: sharp rise (pole) then small downward channel (flag) then breakout."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))

    for i in range(15, len(df)):
        # Pole: strong upward move in candles i-15 to i-8
        pole_start = c[i - 15]
        pole_end = c[i - 8]
        if pole_start == 0:
            continue
        pole_gain = (pole_end - pole_start) / pole_start
        if pole_gain < 0.01:
            continue

        # Flag: slight downward drift in i-7 to i-1
        flag_highs = h[i-7:i]
        flag_lows = l[i-7:i]
        flag_h_slope = flag_highs[-1] - flag_highs[0]
        flag_l_slope = flag_lows[-1] - flag_lows[0]

        if flag_h_slope >= 0 or flag_l_slope >= 0:
            continue

        flag_drop = (c[i-8] - c[i-1]) / max(c[i-8], 1e-10)
        if flag_drop < 0 or flag_drop > pole_gain * 0.5:
            continue

        if c[i] > max(flag_highs) and c[i] > o[i]:
            sig[i] = 1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bull_Flag', bull_flag, 'Sharp rise + downward channel + breakout — bullish')


def bear_flag(df: pd.DataFrame) -> pd.Series:
    """Bear Flag: sharp drop then small upward channel then breakdown."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))

    for i in range(15, len(df)):
        pole_start = c[i - 15]
        pole_end = c[i - 8]
        if pole_start == 0:
            continue
        pole_drop = (pole_start - pole_end) / pole_start
        if pole_drop < 0.01:
            continue

        flag_highs = h[i-7:i]
        flag_lows = l[i-7:i]
        flag_h_slope = flag_highs[-1] - flag_highs[0]
        flag_l_slope = flag_lows[-1] - flag_lows[0]

        if flag_h_slope <= 0 or flag_l_slope <= 0:
            continue

        flag_rise = (c[i-1] - c[i-8]) / max(c[i-8], 1e-10)
        if flag_rise < 0 or flag_rise > pole_drop * 0.5:
            continue

        if c[i] < min(flag_lows) and c[i] < o[i]:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bear_Flag', bear_flag, 'Sharp drop + upward channel + breakdown — bearish')


def bull_pennant(df: pd.DataFrame) -> pd.Series:
    """Bull Pennant: sharp rise then converging triangle then breakout."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))

    for i in range(15, len(df)):
        pole_start = c[i - 15]
        pole_end = c[i - 8]
        if pole_start == 0:
            continue
        pole_gain = (pole_end - pole_start) / pole_start
        if pole_gain < 0.01:
            continue

        flag_highs = h[i-7:i]
        flag_lows = l[i-7:i]
        h_slope = flag_highs[-1] - flag_highs[0]
        l_slope = flag_lows[-1] - flag_lows[0]

        # Converging: highs falling, lows rising
        if not (h_slope < 0 and l_slope > 0):
            continue

        if c[i] > max(flag_highs) and c[i] > o[i]:
            sig[i] = 1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bull_Pennant', bull_pennant, 'Sharp rise + converging triangle + breakout — bullish')


def bear_pennant(df: pd.DataFrame) -> pd.Series:
    """Bear Pennant: sharp drop then converging triangle then breakdown."""
    h, l, c, o = df['high'].values, df['low'].values, df['close'].values, df['open'].values
    sig = np.zeros(len(df))

    for i in range(15, len(df)):
        pole_start = c[i - 15]
        pole_end = c[i - 8]
        if pole_start == 0:
            continue
        pole_drop = (pole_start - pole_end) / pole_start
        if pole_drop < 0.01:
            continue

        flag_highs = h[i-7:i]
        flag_lows = l[i-7:i]
        h_slope = flag_highs[-1] - flag_highs[0]
        l_slope = flag_lows[-1] - flag_lows[0]

        if not (h_slope < 0 and l_slope > 0):
            continue

        if c[i] < min(flag_lows) and c[i] < o[i]:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Bear_Pennant', bear_pennant, 'Sharp drop + converging triangle + breakdown — bearish')


# ═══════════════════════════════════════════════════════════════════════════════
#  RECTANGLE PATTERN
# ═══════════════════════════════════════════════════════════════════════════════

def rectangle_pattern(df: pd.DataFrame) -> pd.Series:
    """Rectangle: price oscillates between flat support and resistance then breaks."""
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    sig = np.zeros(len(df))
    lookback = 30
    window = 5

    for i in range(lookback + window, len(df)):
        seg_h = h[i - lookback:i]
        seg_l = l[i - lookback:i]

        sh = _swing_highs(seg_h, window)
        sl = _swing_lows(seg_l, window)
        sh_idx = np.where(sh)[0]
        sl_idx = np.where(sl)[0]

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            continue

        res_vals = seg_h[sh_idx]
        sup_vals = seg_l[sl_idx]

        avg_res = np.mean(res_vals)
        avg_sup = np.mean(sup_vals)

        if avg_res == 0 or avg_sup == 0:
            continue

        # All resistance levels similar, all support levels similar
        res_tight = np.std(res_vals) / avg_res < 0.005
        sup_tight = np.std(sup_vals) / avg_sup < 0.005

        if not (res_tight and sup_tight):
            continue

        if c[i] > avg_res:
            sig[i] = 1
        elif c[i] < avg_sup:
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rectangle', rectangle_pattern, 'Flat S/R channel breakout — direction of break')


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUNDING BOTTOM / TOP
# ═══════════════════════════════════════════════════════════════════════════════

def rounding_bottom(df: pd.DataFrame) -> pd.Series:
    """Rounding bottom: gradual U-shape in closes over lookback period."""
    c = df['close'].values
    sig = np.zeros(len(df))
    lookback = 30

    for i in range(lookback + 1, len(df)):
        seg = c[i - lookback:i]
        mid_idx = lookback // 2
        left = np.mean(seg[:5])
        middle = np.mean(seg[mid_idx - 2:mid_idx + 3])
        right = np.mean(seg[-5:])

        if left == 0 or middle == 0:
            continue

        # U-shape: left and right higher than middle, right >= left
        left_drop = (left - middle) / left
        right_rise = (right - middle) / max(middle, 1e-10)

        if (left_drop > 0.01 and right_rise > 0.01 and
            abs(left - right) / left < 0.02 and
            c[i] > right and c[i] > c[i-1]):
            sig[i] = 1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rounding_Bottom', rounding_bottom, 'Gradual U-shaped recovery — bullish')


def rounding_top(df: pd.DataFrame) -> pd.Series:
    """Rounding top: inverted U-shape in closes."""
    c = df['close'].values
    sig = np.zeros(len(df))
    lookback = 30

    for i in range(lookback + 1, len(df)):
        seg = c[i - lookback:i]
        mid_idx = lookback // 2
        left = np.mean(seg[:5])
        middle = np.mean(seg[mid_idx - 2:mid_idx + 3])
        right = np.mean(seg[-5:])

        if left == 0 or middle == 0:
            continue

        left_rise = (middle - left) / max(left, 1e-10)
        right_drop = (middle - right) / max(middle, 1e-10)

        if (left_rise > 0.01 and right_drop > 0.01 and
            abs(left - right) / max(left, 1e-10) < 0.02 and
            c[i] < right and c[i] < c[i-1]):
            sig[i] = -1

    return pd.Series(sig, index=df.index, dtype=int)

_reg('Rounding_Top', rounding_top, 'Inverted U-shape decline — bearish')
