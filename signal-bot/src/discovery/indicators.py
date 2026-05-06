"""
Indicator Library — computes ALL technical indicators on an OHLCV DataFrame.

Called ONCE per pair/timeframe, then reused across every strategy backtest.
Uses the 'ta' library (same as the main signal bot).
"""

import pandas as pd
import numpy as np
import ta


# ── Periods that strategies reference (keep in sync with strategies.py) ──────
MA_PERIODS   = [5, 8, 10, 13, 20, 21, 30, 50, 100, 200]
RSI_PERIODS  = [7, 9, 14, 21]
MACD_CFGS    = [(8, 21, 7), (12, 26, 9), (16, 30, 12)]
ADX_PERIODS  = [7, 14, 21]
ATR_PERIODS  = [7, 14, 21]
BB_CFGS      = [(20, 2.0), (20, 2.5), (25, 2.0)]
STOCH_CFGS   = [(5, 3), (14, 3), (21, 3)]
CCI_PERIODS  = [14, 20, 30]
WILLR_PERIODS = [7, 14, 21]
DC_PERIODS   = [10, 20, 30]
KC_PERIODS   = [14, 20]
ROC_PERIODS  = [5, 10, 20]


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add every indicator column that any strategy might reference.
    Returns a copy — original df is not mutated.
    Collects all new columns in a dict, then concat once (avoids fragmentation).
    """
    df = df.copy()
    close = df['close'].astype(float)
    high  = df['high'].astype(float)
    low   = df['low'].astype(float)
    cols: dict[str, pd.Series] = {}

    n = len(df)

    # ── Moving Averages ───────────────────────────────────────────────────
    for p in MA_PERIODS:
        if n >= p:
            cols[f'sma_{p}'] = ta.trend.SMAIndicator(close, window=p).sma_indicator()
            cols[f'ema_{p}'] = ta.trend.EMAIndicator(close, window=p).ema_indicator()

    # ── RSI ───────────────────────────────────────────────────────────────
    for p in RSI_PERIODS:
        if n >= p + 1:
            cols[f'rsi_{p}'] = ta.momentum.RSIIndicator(close, window=p).rsi()

    # ── MACD ──────────────────────────────────────────────────────────────
    for fast, slow, sig in MACD_CFGS:
        if n >= slow + sig:
            m = ta.trend.MACD(close, window_fast=fast, window_slow=slow, window_sign=sig)
            cols[f'macd_{fast}_{slow}']       = m.macd()
            cols[f'macd_signal_{fast}_{slow}'] = m.macd_signal()
            cols[f'macd_hist_{fast}_{slow}']   = m.macd_diff()

    # ── ADX / DI± ────────────────────────────────────────────────────────
    for p in ADX_PERIODS:
        if n >= p * 2:
            a = ta.trend.ADXIndicator(high, low, close, window=p)
            cols[f'adx_{p}']    = a.adx()
            cols[f'di_pos_{p}'] = a.adx_pos()
            cols[f'di_neg_{p}'] = a.adx_neg()

    # ── ATR ───────────────────────────────────────────────────────────────
    for p in ATR_PERIODS:
        if n >= p + 1:
            cols[f'atr_{p}'] = ta.volatility.AverageTrueRange(
                high, low, close, window=p
            ).average_true_range()

    # ── Bollinger Bands ───────────────────────────────────────────────────
    for period, std in BB_CFGS:
        if n >= period:
            bb = ta.volatility.BollingerBands(close, window=period, window_dev=std)
            tag = f'bb_{period}_{str(std).replace(".", "")}'
            cols[f'{tag}_upper'] = bb.bollinger_hband()
            cols[f'{tag}_lower'] = bb.bollinger_lband()
            cols[f'{tag}_mid']   = bb.bollinger_mavg()
            cols[f'{tag}_width'] = bb.bollinger_wband()
            cols[f'{tag}_pct']   = bb.bollinger_pband()

    # ── Stochastic ────────────────────────────────────────────────────────
    for k, d in STOCH_CFGS:
        if n >= k + d:
            s = ta.momentum.StochasticOscillator(high, low, close, window=k, smooth_window=d)
            cols[f'stoch_k_{k}_{d}'] = s.stoch()
            cols[f'stoch_d_{k}_{d}'] = s.stoch_signal()

    # ── CCI ───────────────────────────────────────────────────────────────
    for p in CCI_PERIODS:
        if n >= p:
            cols[f'cci_{p}'] = ta.trend.CCIIndicator(high, low, close, window=p).cci()

    # ── Williams %R ───────────────────────────────────────────────────────
    for p in WILLR_PERIODS:
        if n >= p:
            cols[f'willr_{p}'] = ta.momentum.WilliamsRIndicator(high, low, close, lbp=p).williams_r()

    # ── Parabolic SAR ────────────────────────────────────────────────────
    try:
        psar = ta.trend.PSARIndicator(high, low, close)
        cols['psar']      = psar.psar()
        cols['psar_up']   = psar.psar_up()
        cols['psar_down'] = psar.psar_down()
    except Exception:
        pass

    # ── Donchian Channel ──────────────────────────────────────────────────
    for p in DC_PERIODS:
        if n >= p:
            dc = ta.volatility.DonchianChannel(high, low, close, window=p)
            cols[f'dc_{p}_upper'] = dc.donchian_channel_hband()
            cols[f'dc_{p}_lower'] = dc.donchian_channel_lband()
            cols[f'dc_{p}_mid']   = dc.donchian_channel_mband()

    # ── Keltner Channel ──────────────────────────────────────────────────
    for p in KC_PERIODS:
        if n >= p:
            kc = ta.volatility.KeltnerChannel(high, low, close, window=p)
            cols[f'kc_{p}_upper'] = kc.keltner_channel_hband()
            cols[f'kc_{p}_lower'] = kc.keltner_channel_lband()
            cols[f'kc_{p}_mid']   = kc.keltner_channel_mband()

    # ── Ichimoku ──────────────────────────────────────────────────────────
    if n >= 52:
        ich = ta.trend.IchimokuIndicator(high, low)
        cols['ich_tenkan']   = ich.ichimoku_conversion_line()
        cols['ich_kijun']    = ich.ichimoku_base_line()
        cols['ich_senkou_a'] = ich.ichimoku_a()
        cols['ich_senkou_b'] = ich.ichimoku_b()

    # ── Aroon ────────────────────────────────────────────────────────────
    if n >= 26:
        ar = ta.trend.AroonIndicator(high, low, window=25)
        cols['aroon_up']   = ar.aroon_up()
        cols['aroon_down'] = ar.aroon_down()

    # ── Rate of Change ───────────────────────────────────────────────────
    for p in ROC_PERIODS:
        if n >= p + 1:
            cols[f'roc_{p}'] = ta.momentum.ROCIndicator(close, window=p).roc()

    # ── Volume indicators (only if volume data exists) ───────────────────
    if 'volume' in df.columns and df['volume'].sum() > 0:
        vol = df['volume'].astype(float)
        for p in [10, 14]:
            try:
                cols[f'mfi_{p}'] = ta.volume.MFIIndicator(
                    high, low, close, vol, window=p
                ).money_flow_index()
            except Exception:
                pass
        try:
            cols['obv'] = ta.volume.OnBalanceVolumeIndicator(close, vol).on_balance_volume()
        except Exception:
            pass

    # ── Merge all indicator columns at once ──────────────────────────────
    if cols:
        indicators_df = pd.DataFrame(cols, index=df.index)
        df = pd.concat([df, indicators_df], axis=1)

    return df
