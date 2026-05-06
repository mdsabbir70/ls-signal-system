"""
Pattern + Indicator Combination Strategies.

Each pattern signal is filtered through an indicator confirmation:
  - Pattern alone (baseline)
  - Pattern + RSI filter
  - Pattern + EMA trend filter
  - Pattern + MACD confirmation
  - Pattern + ADX strength filter
  - Pattern + Bollinger Band proximity

This multiplies each pattern by 6 indicator filters.
"""

from __future__ import annotations
import pandas as pd
import numpy as np

from patterns.candlestick_detector import get_all_candlestick_patterns
from patterns.chart_detector import get_all_chart_patterns


# ── Indicator filter functions ───────────────────────────────────────────────

def _filter_rsi(df: pd.DataFrame, signals: pd.Series, period: int = 14) -> pd.Series:
    """Keep BUY only if RSI < 40 (not overbought), SELL only if RSI > 60."""
    col = f'rsi_{period}'
    if col not in df.columns:
        return signals
    rsi = df[col].values
    out = signals.copy().values.astype(float)
    for i in range(len(out)):
        if out[i] == 1 and rsi[i] > 60:
            out[i] = 0
        elif out[i] == -1 and rsi[i] < 40:
            out[i] = 0
    return pd.Series(out, index=df.index, dtype=int)


def _filter_ema_trend(df: pd.DataFrame, signals: pd.Series,
                       fast: int = 20, slow: int = 50) -> pd.Series:
    """Keep BUY only if EMA fast > EMA slow (uptrend), SELL only if downtrend."""
    f_col = f'ema_{fast}'
    s_col = f'ema_{slow}'
    if f_col not in df.columns or s_col not in df.columns:
        return signals
    ema_f = df[f_col].values
    ema_s = df[s_col].values
    out = signals.copy().values.astype(float)
    for i in range(len(out)):
        if out[i] == 1 and ema_f[i] < ema_s[i]:
            out[i] = 0
        elif out[i] == -1 and ema_f[i] > ema_s[i]:
            out[i] = 0
    return pd.Series(out, index=df.index, dtype=int)


def _filter_macd(df: pd.DataFrame, signals: pd.Series) -> pd.Series:
    """Keep BUY only if MACD histogram > 0, SELL if < 0."""
    col = 'macd_hist'
    if col not in df.columns:
        return signals
    hist = df[col].values
    out = signals.copy().values.astype(float)
    for i in range(len(out)):
        if out[i] == 1 and hist[i] < 0:
            out[i] = 0
        elif out[i] == -1 and hist[i] > 0:
            out[i] = 0
    return pd.Series(out, index=df.index, dtype=int)


def _filter_adx(df: pd.DataFrame, signals: pd.Series, threshold: int = 20) -> pd.Series:
    """Only keep signals when ADX > threshold (strong trend)."""
    col = 'adx_14'
    if col not in df.columns:
        return signals
    adx = df[col].values
    out = signals.copy().values.astype(float)
    for i in range(len(out)):
        if out[i] != 0 and adx[i] < threshold:
            out[i] = 0
    return pd.Series(out, index=df.index, dtype=int)


def _filter_bb(df: pd.DataFrame, signals: pd.Series) -> pd.Series:
    """BUY only near lower BB, SELL only near upper BB."""
    if 'bb_lower_20' not in df.columns or 'bb_upper_20' not in df.columns:
        return signals
    lower = df['bb_lower_20'].values
    upper = df['bb_upper_20'].values
    close = df['close'].values
    out = signals.copy().values.astype(float)
    for i in range(len(out)):
        bb_range = upper[i] - lower[i]
        if bb_range == 0:
            continue
        pos = (close[i] - lower[i]) / bb_range  # 0=lower, 1=upper
        if out[i] == 1 and pos > 0.5:
            out[i] = 0
        elif out[i] == -1 and pos < 0.5:
            out[i] = 0
    return pd.Series(out, index=df.index, dtype=int)


# ── Build strategy registry ─────────────────────────────────────────────────

INDICATOR_FILTERS = [
    {'name': 'Alone',     'func': None,               'label': ''},
    {'name': 'RSI',       'func': _filter_rsi,         'label': '+RSI'},
    {'name': 'EMA_Trend', 'func': _filter_ema_trend,   'label': '+EMA'},
    {'name': 'MACD',      'func': _filter_macd,        'label': '+MACD'},
    {'name': 'ADX',       'func': _filter_adx,         'label': '+ADX'},
    {'name': 'BB',        'func': _filter_bb,           'label': '+BB'},
]


def get_all_pattern_strategies() -> list[dict]:
    """
    Returns all pattern × indicator filter combinations.
    Each entry: {name, category, pattern_func, filter_func, label}
    """
    all_patterns = get_all_candlestick_patterns() + get_all_chart_patterns()
    strategies = []

    for pat in all_patterns:
        for filt in INDICATOR_FILTERS:
            strategies.append({
                'name': f"{pat['name']}_{filt['name']}" if filt['name'] != 'Alone' else pat['name'],
                'pattern_name': pat['name'],
                'category': pat['category'],
                'pattern_func': pat['func'],
                'filter_func': filt['func'],
                'filter_name': filt['name'],
                'label': f"{pat['name']} {filt['label']}".strip(),
                'description': pat.get('description', ''),
            })

    return strategies


def get_pattern_count() -> int:
    all_patterns = get_all_candlestick_patterns() + get_all_chart_patterns()
    return len(all_patterns)
