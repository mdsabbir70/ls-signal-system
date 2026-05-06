"""
Strategy Registry — every trading strategy the Discovery Bot will test.

Each strategy is a dict with:
  name     : human-readable name
  category : trend | reversal | breakout | momentum | volatility | multi | price_action
  func     : callable(df, **params) → pd.Series  (1=BUY, -1=SELL, 0=none)
  params   : dict of keyword arguments for func
  label    : compact string for reports

Strategies are grouped by type:
  A. Single-indicator   (20 types)
  B. Multi-indicator    (14 types)
  C. Price action       (3 types)

Total unique configs: ~110
"""

import pandas as pd
import numpy as np

REGISTRY: list[dict] = []


def _reg(name, category, func, param_grid):
    """Register one strategy type with all its parameter variations."""
    for params in param_grid:
        compact = ', '.join(f'{k}={v}' for k, v in params.items())
        REGISTRY.append({
            'name': name,
            'category': category,
            'func': func,
            'params': params,
            'label': f"{name}({compact})",
        })


# ═══════════════════════════════════════════════════════════════════════════════
#  A.  SINGLE-INDICATOR STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. SMA Crossover ────────────────────────────────────────────────────────
def sma_crossover(df, fast, slow):
    f = df[f'sma_{fast}']
    s = df[f'sma_{slow}']
    sig = pd.Series(0, index=df.index)
    sig[(f > s) & (f.shift(1) <= s.shift(1))] = 1
    sig[(f < s) & (f.shift(1) >= s.shift(1))] = -1
    return sig

_reg('SMA_Cross', 'trend', sma_crossover, [
    {'fast': 5,  'slow': 50},
    {'fast': 10, 'slow': 50},
    {'fast': 10, 'slow': 100},
    {'fast': 20, 'slow': 50},
    {'fast': 20, 'slow': 100},
    {'fast': 20, 'slow': 200},
    {'fast': 50, 'slow': 200},
])

# ── 2. EMA Crossover ────────────────────────────────────────────────────────
def ema_crossover(df, fast, slow):
    f = df[f'ema_{fast}']
    s = df[f'ema_{slow}']
    sig = pd.Series(0, index=df.index)
    sig[(f > s) & (f.shift(1) <= s.shift(1))] = 1
    sig[(f < s) & (f.shift(1) >= s.shift(1))] = -1
    return sig

_reg('EMA_Cross', 'trend', ema_crossover, [
    {'fast': 5,  'slow': 20},
    {'fast': 5,  'slow': 50},
    {'fast': 10, 'slow': 50},
    {'fast': 10, 'slow': 100},
    {'fast': 20, 'slow': 50},
    {'fast': 20, 'slow': 100},
    {'fast': 20, 'slow': 200},
    {'fast': 50, 'slow': 200},
])

# ── 3. Triple EMA Alignment ─────────────────────────────────────────────────
def triple_ema(df, fast, mid, slow):
    f = df[f'ema_{fast}']
    m = df[f'ema_{mid}']
    s = df[f'ema_{slow}']
    bull = (f > m) & (m > s)
    bear = (f < m) & (m < s)
    sig = pd.Series(0, index=df.index)
    sig[bull & ~bull.shift(1).fillna(False)] = 1
    sig[bear & ~bear.shift(1).fillna(False)] = -1
    return sig

_reg('Triple_EMA', 'trend', triple_ema, [
    {'fast': 8,  'mid': 21, 'slow': 50},
    {'fast': 10, 'mid': 30, 'slow': 100},
    {'fast': 13, 'mid': 50, 'slow': 200},
])

# ── 4. RSI Overbought / Oversold (Mean Reversion) ───────────────────────────
def rsi_reversal(df, period, ob=70, os_=30):
    rsi = df[f'rsi_{period}']
    sig = pd.Series(0, index=df.index)
    sig[(rsi > os_) & (rsi.shift(1) <= os_)] = 1      # cross above oversold
    sig[(rsi < ob) & (rsi.shift(1) >= ob)] = -1        # cross below overbought
    return sig

_reg('RSI_Reversal', 'reversal', rsi_reversal, [
    {'period': p, 'ob': ob, 'os_': os_}
    for p in [7, 14, 21]
    for ob, os_ in [(70, 30), (75, 25), (80, 20)]
])

# ── 5. RSI Midline Cross (Trend-following) ───────────────────────────────────
def rsi_midline(df, period):
    rsi = df[f'rsi_{period}']
    sig = pd.Series(0, index=df.index)
    sig[(rsi > 50) & (rsi.shift(1) <= 50)] = 1
    sig[(rsi < 50) & (rsi.shift(1) >= 50)] = -1
    return sig

_reg('RSI_Midline', 'momentum', rsi_midline, [
    {'period': 7}, {'period': 14}, {'period': 21},
])

# ── 6. MACD Signal Crossover ────────────────────────────────────────────────
def macd_crossover(df, fast, slow):
    m = df[f'macd_{fast}_{slow}']
    s = df[f'macd_signal_{fast}_{slow}']
    sig = pd.Series(0, index=df.index)
    sig[(m > s) & (m.shift(1) <= s.shift(1))] = 1
    sig[(m < s) & (m.shift(1) >= s.shift(1))] = -1
    return sig

_reg('MACD_Cross', 'trend', macd_crossover, [
    {'fast': 8,  'slow': 21},
    {'fast': 12, 'slow': 26},
    {'fast': 16, 'slow': 30},
])

# ── 7. MACD Histogram Zero Cross ────────────────────────────────────────────
def macd_hist_zero(df, fast, slow):
    h = df[f'macd_hist_{fast}_{slow}']
    sig = pd.Series(0, index=df.index)
    sig[(h > 0) & (h.shift(1) <= 0)] = 1
    sig[(h < 0) & (h.shift(1) >= 0)] = -1
    return sig

_reg('MACD_Hist', 'momentum', macd_hist_zero, [
    {'fast': 8,  'slow': 21},
    {'fast': 12, 'slow': 26},
])

# ── 8. Bollinger Band Bounce (Mean Reversion) ───────────────────────────────
def bb_bounce(df, period, std):
    tag = f'bb_{period}_{str(std).replace(".", "")}'
    lo = df[f'{tag}_lower']
    up = df[f'{tag}_upper']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c.shift(1) <= lo.shift(1)) & (c > lo)] = 1     # bounce off lower
    sig[(c.shift(1) >= up.shift(1)) & (c < up)] = -1    # bounce off upper
    return sig

_reg('BB_Bounce', 'reversal', bb_bounce, [
    {'period': 20, 'std': 2.0},
    {'period': 20, 'std': 2.5},
    {'period': 25, 'std': 2.0},
])

# ── 9. Bollinger Band Breakout ──────────────────────────────────────────────
def bb_breakout(df, period, std):
    tag = f'bb_{period}_{str(std).replace(".", "")}'
    lo = df[f'{tag}_lower']
    up = df[f'{tag}_upper']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c > up) & (c.shift(1) <= up.shift(1))] = 1
    sig[(c < lo) & (c.shift(1) >= lo.shift(1))] = -1
    return sig

_reg('BB_Breakout', 'breakout', bb_breakout, [
    {'period': 20, 'std': 2.0},
    {'period': 20, 'std': 2.5},
    {'period': 25, 'std': 2.0},
])

# ── 10. Stochastic Crossover ────────────────────────────────────────────────
def stoch_crossover(df, k_period, d_period, ob=80, os_=20):
    k = df[f'stoch_k_{k_period}_{d_period}']
    d = df[f'stoch_d_{k_period}_{d_period}']
    sig = pd.Series(0, index=df.index)
    sig[(k > d) & (k.shift(1) <= d.shift(1)) & (d < os_ + 15)] = 1
    sig[(k < d) & (k.shift(1) >= d.shift(1)) & (d > ob - 15)] = -1
    return sig

_reg('Stoch_Cross', 'reversal', stoch_crossover, [
    {'k_period': 5,  'd_period': 3, 'ob': 80, 'os_': 20},
    {'k_period': 14, 'd_period': 3, 'ob': 80, 'os_': 20},
    {'k_period': 21, 'd_period': 3, 'ob': 80, 'os_': 20},
])

# ── 11. ADX + DI Direction (Trend Strength) ─────────────────────────────────
def adx_trend(df, period, threshold):
    adx = df[f'adx_{period}']
    dip = df[f'di_pos_{period}']
    din = df[f'di_neg_{period}']
    strong = adx > threshold
    sig = pd.Series(0, index=df.index)
    buy  = strong & (dip > din) & (~(strong.shift(1).fillna(False) & (dip.shift(1) > din.shift(1))))
    sell = strong & (din > dip) & (~(strong.shift(1).fillna(False) & (din.shift(1) > dip.shift(1))))
    sig[buy.fillna(False)]  = 1
    sig[sell.fillna(False)] = -1
    return sig

_reg('ADX_Trend', 'trend', adx_trend, [
    {'period': 14, 'threshold': 20},
    {'period': 14, 'threshold': 25},
    {'period': 21, 'threshold': 20},
    {'period': 21, 'threshold': 25},
])

# ── 12. CCI Reversal ────────────────────────────────────────────────────────
def cci_reversal(df, period, level=100):
    cci = df[f'cci_{period}']
    sig = pd.Series(0, index=df.index)
    sig[(cci > -level) & (cci.shift(1) <= -level)] = 1
    sig[(cci < level)  & (cci.shift(1) >= level)]  = -1
    return sig

_reg('CCI_Reversal', 'reversal', cci_reversal, [
    {'period': 14, 'level': 100},
    {'period': 14, 'level': 200},
    {'period': 20, 'level': 100},
    {'period': 20, 'level': 200},
    {'period': 30, 'level': 100},
])

# ── 13. Williams %R ─────────────────────────────────────────────────────────
def williams_r(df, period, ob=-20, os_=-80):
    w = df[f'willr_{period}']
    sig = pd.Series(0, index=df.index)
    sig[(w > os_) & (w.shift(1) <= os_)] = 1
    sig[(w < ob) & (w.shift(1) >= ob)]   = -1
    return sig

_reg('Williams_R', 'reversal', williams_r, [
    {'period': 7,  'ob': -20, 'os_': -80},
    {'period': 14, 'ob': -20, 'os_': -80},
    {'period': 21, 'ob': -20, 'os_': -80},
])

# ── 14. Parabolic SAR ───────────────────────────────────────────────────────
def parabolic_sar(df):
    c = df['close']
    p = df['psar']
    sig = pd.Series(0, index=df.index)
    sig[(c > p) & (c.shift(1) <= p.shift(1))] = 1
    sig[(c < p) & (c.shift(1) >= p.shift(1))] = -1
    return sig

_reg('PSAR', 'trend', parabolic_sar, [{}])

# ── 15. Donchian Channel Breakout ───────────────────────────────────────────
def donchian_breakout(df, period):
    up = df[f'dc_{period}_upper']
    lo = df[f'dc_{period}_lower']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c >= up) & (c.shift(1) < up.shift(1))] = 1
    sig[(c <= lo) & (c.shift(1) > lo.shift(1))] = -1
    return sig

_reg('Donchian_Break', 'breakout', donchian_breakout, [
    {'period': 10}, {'period': 20}, {'period': 30},
])

# ── 16. Keltner Channel Bounce ──────────────────────────────────────────────
def keltner_bounce(df, period):
    up = df[f'kc_{period}_upper']
    lo = df[f'kc_{period}_lower']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c.shift(1) <= lo.shift(1)) & (c > lo)] = 1
    sig[(c.shift(1) >= up.shift(1)) & (c < up)] = -1
    return sig

_reg('Keltner_Bounce', 'reversal', keltner_bounce, [
    {'period': 14}, {'period': 20},
])

# ── 17. Ichimoku Cloud ──────────────────────────────────────────────────────
def ichimoku_cloud(df):
    tenkan = df.get('ich_tenkan')
    kijun  = df.get('ich_kijun')
    sen_a  = df.get('ich_senkou_a')
    sen_b  = df.get('ich_senkou_b')
    if tenkan is None or kijun is None or sen_a is None:
        return pd.Series(0, index=df.index)
    c = df['close']
    cloud_top = pd.concat([sen_a, sen_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([sen_a, sen_b], axis=1).min(axis=1)
    tk_up = (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
    tk_dn = (tenkan < kijun) & (tenkan.shift(1) >= kijun.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[tk_up & (c > cloud_top)] = 1
    sig[tk_dn & (c < cloud_bot)] = -1
    return sig

_reg('Ichimoku', 'trend', ichimoku_cloud, [{}])

# ── 18. Aroon Crossover ─────────────────────────────────────────────────────
def aroon_crossover(df):
    up = df.get('aroon_up')
    dn = df.get('aroon_down')
    if up is None or dn is None:
        return pd.Series(0, index=df.index)
    sig = pd.Series(0, index=df.index)
    sig[(up > dn) & (up.shift(1) <= dn.shift(1))] = 1
    sig[(dn > up) & (dn.shift(1) <= up.shift(1))] = -1
    return sig

_reg('Aroon_Cross', 'trend', aroon_crossover, [{}])

# ── 19. ROC Momentum ────────────────────────────────────────────────────────
def roc_momentum(df, period, threshold=0):
    r = df[f'roc_{period}']
    sig = pd.Series(0, index=df.index)
    sig[(r > threshold)  & (r.shift(1) <= threshold)]  = 1
    sig[(r < -threshold) & (r.shift(1) >= -threshold)] = -1
    return sig

_reg('ROC_Momentum', 'momentum', roc_momentum, [
    {'period': 5,  'threshold': 0},
    {'period': 10, 'threshold': 0},
    {'period': 20, 'threshold': 0},
    {'period': 10, 'threshold': 1},
    {'period': 20, 'threshold': 1},
])

# ── 20. SuperTrend (ATR-based) ──────────────────────────────────────────────
def supertrend(df, atr_period, multiplier):
    atr = df[f'atr_{atr_period}']
    hl2 = (df['high'] + df['low']) / 2.0
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    c = df['close']
    direction = pd.Series(1, index=df.index)
    for i in range(1, len(df)):
        if pd.isna(upper.iloc[i]) or pd.isna(lower.iloc[i]):
            direction.iloc[i] = direction.iloc[i - 1]
            continue
        if c.iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif c.iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
    sig = pd.Series(0, index=df.index)
    sig[(direction == 1) & (direction.shift(1) == -1)] = 1
    sig[(direction == -1) & (direction.shift(1) == 1)] = -1
    return sig

_reg('SuperTrend', 'trend', supertrend, [
    {'atr_period': 7,  'multiplier': 2.0},
    {'atr_period': 7,  'multiplier': 3.0},
    {'atr_period': 14, 'multiplier': 2.0},
    {'atr_period': 14, 'multiplier': 3.0},
])


# ═══════════════════════════════════════════════════════════════════════════════
#  B.  MULTI-INDICATOR STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 21. EMA Cross + RSI Filter ──────────────────────────────────────────────
def ema_cross_rsi(df, ema_fast, ema_slow, rsi_period, rsi_low=40, rsi_high=60):
    fe = df[f'ema_{ema_fast}']
    se = df[f'ema_{ema_slow}']
    rsi = df[f'rsi_{rsi_period}']
    ema_buy  = (fe > se) & (fe.shift(1) <= se.shift(1))
    ema_sell = (fe < se) & (fe.shift(1) >= se.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[ema_buy  & (rsi > rsi_low) & (rsi < 70)] = 1
    sig[ema_sell & (rsi < rsi_high) & (rsi > 30)] = -1
    return sig

_reg('EMA_RSI', 'multi', ema_cross_rsi, [
    {'ema_fast': 10, 'ema_slow': 50,  'rsi_period': 14},
    {'ema_fast': 20, 'ema_slow': 100, 'rsi_period': 14},
    {'ema_fast': 50, 'ema_slow': 200, 'rsi_period': 14},
    {'ema_fast': 10, 'ema_slow': 50,  'rsi_period': 7},
])

# ── 22. EMA Cross + MACD Confirmation ───────────────────────────────────────
def ema_cross_macd(df, ema_fast, ema_slow, macd_fast, macd_slow):
    fe = df[f'ema_{ema_fast}']
    se = df[f'ema_{ema_slow}']
    m  = df[f'macd_{macd_fast}_{macd_slow}']
    ms = df[f'macd_signal_{macd_fast}_{macd_slow}']
    ema_buy  = (fe > se) & (fe.shift(1) <= se.shift(1))
    ema_sell = (fe < se) & (fe.shift(1) >= se.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[ema_buy  & (m > ms)] = 1
    sig[ema_sell & (m < ms)] = -1
    return sig

_reg('EMA_MACD', 'multi', ema_cross_macd, [
    {'ema_fast': 10, 'ema_slow': 50,  'macd_fast': 12, 'macd_slow': 26},
    {'ema_fast': 20, 'ema_slow': 100, 'macd_fast': 12, 'macd_slow': 26},
    {'ema_fast': 50, 'ema_slow': 200, 'macd_fast': 12, 'macd_slow': 26},
])

# ── 23. RSI + MACD ──────────────────────────────────────────────────────────
def rsi_macd(df, rsi_period, macd_fast, macd_slow, rsi_os=30, rsi_ob=70):
    rsi = df[f'rsi_{rsi_period}']
    m   = df[f'macd_{macd_fast}_{macd_slow}']
    ms  = df[f'macd_signal_{macd_fast}_{macd_slow}']
    macd_bull = (m > ms) & (m.shift(1) <= ms.shift(1))
    macd_bear = (m < ms) & (m.shift(1) >= ms.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[macd_bull & (rsi > rsi_os) & (rsi < rsi_ob)] = 1
    sig[macd_bear & (rsi < rsi_ob) & (rsi > rsi_os)] = -1
    return sig

_reg('RSI_MACD', 'multi', rsi_macd, [
    {'rsi_period': 14, 'macd_fast': 12, 'macd_slow': 26},
    {'rsi_period': 7,  'macd_fast': 12, 'macd_slow': 26},
    {'rsi_period': 14, 'macd_fast': 8,  'macd_slow': 21},
])

# ── 24. RSI + Bollinger Bands ───────────────────────────────────────────────
def rsi_bollinger(df, rsi_period, bb_period, bb_std, rsi_os=30, rsi_ob=70):
    rsi = df[f'rsi_{rsi_period}']
    tag = f'bb_{bb_period}_{str(bb_std).replace(".", "")}'
    lo = df[f'{tag}_lower']
    up = df[f'{tag}_upper']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c <= lo) & (rsi < rsi_os)] = 1
    sig[(c >= up) & (rsi > rsi_ob)] = -1
    return sig

_reg('RSI_BB', 'multi', rsi_bollinger, [
    {'rsi_period': 14, 'bb_period': 20, 'bb_std': 2.0},
    {'rsi_period': 7,  'bb_period': 20, 'bb_std': 2.0},
    {'rsi_period': 14, 'bb_period': 20, 'bb_std': 2.5},
])

# ── 25. Stochastic + RSI ────────────────────────────────────────────────────
def stoch_rsi(df, k_period, d_period, rsi_period, rsi_os=30, rsi_ob=70):
    k   = df[f'stoch_k_{k_period}_{d_period}']
    d   = df[f'stoch_d_{k_period}_{d_period}']
    rsi = df[f'rsi_{rsi_period}']
    sig = pd.Series(0, index=df.index)
    k_cross_up = (k > d) & (k.shift(1) <= d.shift(1))
    k_cross_dn = (k < d) & (k.shift(1) >= d.shift(1))
    sig[k_cross_up & (rsi < rsi_ob) & (rsi > rsi_os)] = 1
    sig[k_cross_dn & (rsi > rsi_os) & (rsi < rsi_ob)] = -1
    return sig

_reg('Stoch_RSI', 'multi', stoch_rsi, [
    {'k_period': 14, 'd_period': 3, 'rsi_period': 14},
    {'k_period': 14, 'd_period': 3, 'rsi_period': 7},
    {'k_period': 5,  'd_period': 3, 'rsi_period': 14},
])

# ── 26. ADX + EMA Direction ─────────────────────────────────────────────────
def adx_ema(df, adx_period, adx_thresh, ema_fast, ema_slow):
    adx = df[f'adx_{adx_period}']
    fe  = df[f'ema_{ema_fast}']
    se  = df[f'ema_{ema_slow}']
    trending = adx > adx_thresh
    sig = pd.Series(0, index=df.index)
    ema_buy  = (fe > se) & (fe.shift(1) <= se.shift(1))
    ema_sell = (fe < se) & (fe.shift(1) >= se.shift(1))
    sig[ema_buy  & trending] = 1
    sig[ema_sell & trending] = -1
    return sig

_reg('ADX_EMA', 'multi', adx_ema, [
    {'adx_period': 14, 'adx_thresh': 20, 'ema_fast': 10, 'ema_slow': 50},
    {'adx_period': 14, 'adx_thresh': 25, 'ema_fast': 20, 'ema_slow': 100},
    {'adx_period': 14, 'adx_thresh': 20, 'ema_fast': 20, 'ema_slow': 200},
])

# ── 27. MACD + Bollinger ────────────────────────────────────────────────────
def macd_bollinger(df, macd_fast, macd_slow, bb_period, bb_std):
    m  = df[f'macd_{macd_fast}_{macd_slow}']
    ms = df[f'macd_signal_{macd_fast}_{macd_slow}']
    tag = f'bb_{bb_period}_{str(bb_std).replace(".", "")}'
    lo = df[f'{tag}_lower']
    up = df[f'{tag}_upper']
    c  = df['close']
    sig = pd.Series(0, index=df.index)
    macd_bull = m > ms
    macd_bear = m < ms
    sig[(c <= lo) & macd_bull] = 1
    sig[(c >= up) & macd_bear] = -1
    return sig

_reg('MACD_BB', 'multi', macd_bollinger, [
    {'macd_fast': 12, 'macd_slow': 26, 'bb_period': 20, 'bb_std': 2.0},
    {'macd_fast': 8,  'macd_slow': 21, 'bb_period': 20, 'bb_std': 2.0},
])

# ── 28. Stochastic + MACD ───────────────────────────────────────────────────
def stoch_macd(df, k_period, d_period, macd_fast, macd_slow):
    k  = df[f'stoch_k_{k_period}_{d_period}']
    d  = df[f'stoch_d_{k_period}_{d_period}']
    m  = df[f'macd_{macd_fast}_{macd_slow}']
    ms = df[f'macd_signal_{macd_fast}_{macd_slow}']
    sig = pd.Series(0, index=df.index)
    k_up = (k > d) & (k.shift(1) <= d.shift(1))
    k_dn = (k < d) & (k.shift(1) >= d.shift(1))
    sig[k_up & (m > ms)] = 1
    sig[k_dn & (m < ms)] = -1
    return sig

_reg('Stoch_MACD', 'multi', stoch_macd, [
    {'k_period': 14, 'd_period': 3, 'macd_fast': 12, 'macd_slow': 26},
    {'k_period': 5,  'd_period': 3, 'macd_fast': 12, 'macd_slow': 26},
])

# ── 29. ADX + RSI ───────────────────────────────────────────────────────────
def adx_rsi(df, adx_period, adx_thresh, rsi_period):
    adx = df[f'adx_{adx_period}']
    dip = df[f'di_pos_{adx_period}']
    din = df[f'di_neg_{adx_period}']
    rsi = df[f'rsi_{rsi_period}']
    trending = adx > adx_thresh
    sig = pd.Series(0, index=df.index)
    sig[trending & (dip > din) & (rsi > 50) & (rsi < 70)] = 1
    sig[trending & (din > dip) & (rsi < 50) & (rsi > 30)] = -1
    # Only trigger on first bar of condition
    sig_shifted = sig.shift(1).fillna(0)
    sig[(sig == sig_shifted) & (sig != 0)] = 0
    return sig

_reg('ADX_RSI', 'multi', adx_rsi, [
    {'adx_period': 14, 'adx_thresh': 20, 'rsi_period': 14},
    {'adx_period': 14, 'adx_thresh': 25, 'rsi_period': 14},
])

# ── 30. Trend System: ADX + EMA + MACD ──────────────────────────────────────
def trend_system(df, adx_period, adx_thresh, ema_fast, ema_slow, macd_fast, macd_slow):
    adx = df[f'adx_{adx_period}']
    dip = df[f'di_pos_{adx_period}']
    din = df[f'di_neg_{adx_period}']
    fe  = df[f'ema_{ema_fast}']
    se  = df[f'ema_{ema_slow}']
    m   = df[f'macd_{macd_fast}_{macd_slow}']
    ms  = df[f'macd_signal_{macd_fast}_{macd_slow}']
    trending = adx > adx_thresh
    sig = pd.Series(0, index=df.index)
    bull = trending & (dip > din) & (fe > se) & (m > ms)
    bear = trending & (din > dip) & (fe < se) & (m < ms)
    sig[bull & ~bull.shift(1).fillna(False)] = 1
    sig[bear & ~bear.shift(1).fillna(False)] = -1
    return sig

_reg('Trend_System', 'multi', trend_system, [
    {'adx_period': 14, 'adx_thresh': 20, 'ema_fast': 10, 'ema_slow': 50, 'macd_fast': 12, 'macd_slow': 26},
    {'adx_period': 14, 'adx_thresh': 25, 'ema_fast': 20, 'ema_slow': 100, 'macd_fast': 12, 'macd_slow': 26},
    {'adx_period': 14, 'adx_thresh': 20, 'ema_fast': 20, 'ema_slow': 50, 'macd_fast': 8, 'macd_slow': 21},
])

# ── 31. Reversal System: RSI + BB + Stochastic ──────────────────────────────
def reversal_system(df, rsi_period, bb_period, bb_std, k_period, d_period):
    rsi = df[f'rsi_{rsi_period}']
    tag = f'bb_{bb_period}_{str(bb_std).replace(".", "")}'
    lo  = df[f'{tag}_lower']
    up  = df[f'{tag}_upper']
    k   = df[f'stoch_k_{k_period}_{d_period}']
    c   = df['close']
    sig = pd.Series(0, index=df.index)
    sig[(c <= lo) & (rsi < 30) & (k < 20)] = 1
    sig[(c >= up) & (rsi > 70) & (k > 80)] = -1
    # Fire only once per cluster
    sig_prev = sig.shift(1).fillna(0)
    sig[(sig == sig_prev) & (sig != 0)] = 0
    return sig

_reg('Reversal_System', 'multi', reversal_system, [
    {'rsi_period': 14, 'bb_period': 20, 'bb_std': 2.0, 'k_period': 14, 'd_period': 3},
    {'rsi_period': 7,  'bb_period': 20, 'bb_std': 2.0, 'k_period': 5,  'd_period': 3},
    {'rsi_period': 14, 'bb_period': 20, 'bb_std': 2.5, 'k_period': 14, 'd_period': 3},
])

# ── 32. Breakout System: Donchian + ADX ─────────────────────────────────────
def breakout_system(df, dc_period, adx_period, adx_thresh):
    up  = df[f'dc_{dc_period}_upper']
    lo  = df[f'dc_{dc_period}_lower']
    adx = df[f'adx_{adx_period}']
    c   = df['close']
    sig = pd.Series(0, index=df.index)
    strong = adx > adx_thresh
    sig[(c >= up) & (c.shift(1) < up.shift(1)) & strong] = 1
    sig[(c <= lo) & (c.shift(1) > lo.shift(1)) & strong] = -1
    return sig

_reg('Breakout_System', 'multi', breakout_system, [
    {'dc_period': 20, 'adx_period': 14, 'adx_thresh': 20},
    {'dc_period': 20, 'adx_period': 14, 'adx_thresh': 25},
    {'dc_period': 30, 'adx_period': 14, 'adx_thresh': 20},
])

# ── 33. Full Confluence: RSI + MACD + BB + ADX ──────────────────────────────
def full_confluence(df, rsi_period, macd_fast, macd_slow, bb_period, bb_std, adx_period, adx_thresh):
    rsi = df[f'rsi_{rsi_period}']
    m   = df[f'macd_{macd_fast}_{macd_slow}']
    ms  = df[f'macd_signal_{macd_fast}_{macd_slow}']
    tag = f'bb_{bb_period}_{str(bb_std).replace(".", "")}'
    lo  = df[f'{tag}_lower']
    up  = df[f'{tag}_upper']
    mid = df[f'{tag}_mid']
    adx = df[f'adx_{adx_period}']
    c   = df['close']
    sig = pd.Series(0, index=df.index)
    bull = (rsi > 40) & (rsi < 70) & (m > ms) & (c > mid) & (adx > adx_thresh)
    bear = (rsi < 60) & (rsi > 30) & (m < ms) & (c < mid) & (adx > adx_thresh)
    sig[bull & ~bull.shift(1).fillna(False)] = 1
    sig[bear & ~bear.shift(1).fillna(False)] = -1
    return sig

_reg('Full_Confluence', 'multi', full_confluence, [
    {'rsi_period': 14, 'macd_fast': 12, 'macd_slow': 26, 'bb_period': 20, 'bb_std': 2.0, 'adx_period': 14, 'adx_thresh': 20},
    {'rsi_period': 14, 'macd_fast': 12, 'macd_slow': 26, 'bb_period': 20, 'bb_std': 2.0, 'adx_period': 14, 'adx_thresh': 25},
])

# ── 34. Ichimoku + RSI ──────────────────────────────────────────────────────
def ichimoku_rsi(df, rsi_period):
    tenkan = df.get('ich_tenkan')
    kijun  = df.get('ich_kijun')
    sen_a  = df.get('ich_senkou_a')
    sen_b  = df.get('ich_senkou_b')
    if tenkan is None or kijun is None or sen_a is None:
        return pd.Series(0, index=df.index)
    rsi = df[f'rsi_{rsi_period}']
    c = df['close']
    cloud_top = pd.concat([sen_a, sen_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([sen_a, sen_b], axis=1).min(axis=1)
    tk_up = (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
    tk_dn = (tenkan < kijun) & (tenkan.shift(1) >= kijun.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[tk_up & (c > cloud_top) & (rsi > 50) & (rsi < 70)] = 1
    sig[tk_dn & (c < cloud_bot) & (rsi < 50) & (rsi > 30)] = -1
    return sig

_reg('Ichimoku_RSI', 'multi', ichimoku_rsi, [
    {'rsi_period': 14}, {'rsi_period': 7},
])


# ═══════════════════════════════════════════════════════════════════════════════
#  C.  PRICE ACTION STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 35. Inside Bar Breakout ──────────────────────────────────────────────────
def inside_bar(df):
    h = df['high']
    l = df['low']
    c = df['close']
    # Inside bar: current bar's range inside previous bar's range
    ib = (h < h.shift(1)) & (l > l.shift(1))
    # Breakout of inside bar on next bar
    sig = pd.Series(0, index=df.index)
    sig[ib.shift(1).fillna(False) & (c > h.shift(1))] = 1     # break above mother bar
    sig[ib.shift(1).fillna(False) & (c < l.shift(1))] = -1    # break below mother bar
    return sig

_reg('Inside_Bar', 'price_action', inside_bar, [{}])

# ── 36. Engulfing Pattern ───────────────────────────────────────────────────
def engulfing(df):
    o = df['open']
    c = df['close']
    h = df['high']
    l = df['low']
    prev_body_up   = c.shift(1) > o.shift(1)
    prev_body_down = c.shift(1) < o.shift(1)
    curr_body_up   = c > o
    curr_body_down = c < o
    sig = pd.Series(0, index=df.index)
    # Bullish engulfing: prev red, curr green engulfs prev
    bull = prev_body_down & curr_body_up & (o <= c.shift(1)) & (c >= o.shift(1))
    # Bearish engulfing: prev green, curr red engulfs prev
    bear = prev_body_up & curr_body_down & (o >= c.shift(1)) & (c <= o.shift(1))
    sig[bull] = 1
    sig[bear] = -1
    return sig

_reg('Engulfing', 'price_action', engulfing, [{}])

# ── 37. Pin Bar / Hammer ────────────────────────────────────────────────────
def pin_bar(df):
    o = df['open']
    c = df['close']
    h = df['high']
    l = df['low']
    body = (c - o).abs()
    full = h - l
    upper_wick = h - pd.concat([o, c], axis=1).max(axis=1)
    lower_wick = pd.concat([o, c], axis=1).min(axis=1) - l
    sig = pd.Series(0, index=df.index)
    # Bullish pin: long lower wick, small body, small upper wick
    bull = (lower_wick > 2 * body) & (upper_wick < body) & (full > 0)
    # Bearish pin: long upper wick, small body, small lower wick
    bear = (upper_wick > 2 * body) & (lower_wick < body) & (full > 0)
    sig[bull] = 1
    sig[bear] = -1
    return sig

_reg('Pin_Bar', 'price_action', pin_bar, [{}])


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_strategies() -> list[dict]:
    """Return the full strategy registry."""
    return REGISTRY


def get_strategy_count() -> int:
    return len(REGISTRY)
