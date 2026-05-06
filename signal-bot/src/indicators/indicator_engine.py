"""
Indicator Engine
Calculates all technical indicators from OHLCV data using 'ta' library.
Supports multiple timeframes: H1, H4, D1

Indicators:
  - EMA (20, 50, 200)
  - RSI (14)
  - MACD (12,26,9)
  - ADX (14) + DI+/DI-
  - ATR (14)
  - Bollinger Bands (20,2)
  - Stochastic (14,3,3)
  - VWAP (intraday)
  - Support / Resistance levels (swing pivot)
"""

from __future__ import annotations
import pandas as pd
import ta
from dataclasses import dataclass
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger('indicators')


@dataclass
class IndicatorResult:
    """Snapshot of all indicators for a single bar (the latest close)."""
    timeframe: str

    # Price
    open:  float = 0.0
    high:  float = 0.0
    low:   float = 0.0
    close: float = 0.0

    # EMAs
    ema20:  Optional[float] = None
    ema50:  Optional[float] = None
    ema200: Optional[float] = None

    # RSI
    rsi: Optional[float] = None

    # MACD
    macd:        Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist:   Optional[float] = None

    # ADX
    adx:     Optional[float] = None
    dmi_pos: Optional[float] = None
    dmi_neg: Optional[float] = None

    # ATR
    atr:     Optional[float] = None
    atr_pct: Optional[float] = None

    # Bollinger Bands
    bb_upper: Optional[float] = None
    bb_mid:   Optional[float] = None
    bb_lower: Optional[float] = None
    bb_width: Optional[float] = None
    bb_pct:   Optional[float] = None

    # Stochastic
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None

    # VWAP
    vwap: Optional[float] = None

    # Support / Resistance
    nearest_support:    Optional[float] = None
    nearest_resistance: Optional[float] = None

    # Derived signals
    trend_direction:    str  = 'SIDEWAYS'
    is_oversold:        bool = False
    is_overbought:      bool = False
    macd_bullish_cross: bool = False
    macd_bearish_cross: bool = False
    price_above_ema200: bool = False
    adx_strong_trend:   bool = False

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class IndicatorEngine:
    """Calculates technical indicators using the 'ta' library."""

    ATR_SL_MULTIPLIER = 1.5
    ATR_TP_MULTIPLIER = 3.0

    def calculate(self, df: pd.DataFrame, timeframe: str) -> IndicatorResult:
        if df is None or len(df) < 50:
            logger.warning(f"Not enough data for {timeframe}: {len(df) if df is not None else 0} bars")
            return IndicatorResult(timeframe=timeframe)

        df = df.copy()
        close  = df['close']
        high   = df['high']
        low    = df['low']

        result = IndicatorResult(
            timeframe=timeframe,
            open=float(df['open'].iloc[-1]),
            high=float(high.iloc[-1]),
            low=float(low.iloc[-1]),
            close=float(close.iloc[-1]),
        )

        # ── EMAs ──────────────────────────────────────────────────────────
        result.ema20  = self._last(ta.trend.EMAIndicator(close, window=20).ema_indicator())
        result.ema50  = self._last(ta.trend.EMAIndicator(close, window=50).ema_indicator())
        if len(df) >= 200:
            result.ema200 = self._last(ta.trend.EMAIndicator(close, window=200).ema_indicator())

        # ── RSI ───────────────────────────────────────────────────────────
        result.rsi = self._last(ta.momentum.RSIIndicator(close, window=14).rsi())

        # ── MACD ──────────────────────────────────────────────────────────
        macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line   = macd_ind.macd()
        signal_line = macd_ind.macd_signal()
        hist_line   = macd_ind.macd_diff()

        result.macd        = self._last(macd_line)
        result.macd_signal = self._last(signal_line)
        result.macd_hist   = self._last(hist_line)

        if len(df) >= 2:
            prev_macd   = self._safe_float(macd_line.iloc[-2])
            prev_signal = self._safe_float(signal_line.iloc[-2])
            curr_macd   = result.macd
            curr_signal = result.macd_signal
            if all(v is not None for v in [prev_macd, prev_signal, curr_macd, curr_signal]):
                result.macd_bullish_cross = (prev_macd <= prev_signal) and (curr_macd > curr_signal)
                result.macd_bearish_cross = (prev_macd >= prev_signal) and (curr_macd < curr_signal)

        # ── ADX / DMI ─────────────────────────────────────────────────────
        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        result.adx     = self._last(adx_ind.adx())
        result.dmi_pos = self._last(adx_ind.adx_pos())
        result.dmi_neg = self._last(adx_ind.adx_neg())
        if result.adx is not None:
            result.adx_strong_trend = result.adx > 25

        # ── ATR ───────────────────────────────────────────────────────────
        result.atr = self._last(ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range())
        if result.atr is not None and result.close > 0:
            result.atr_pct = result.atr / result.close * 100

        # ── Bollinger Bands ───────────────────────────────────────────────
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        result.bb_upper = self._last(bb.bollinger_hband())
        result.bb_mid   = self._last(bb.bollinger_mavg())
        result.bb_lower = self._last(bb.bollinger_lband())
        if result.bb_upper and result.bb_lower and result.bb_mid:
            result.bb_width = (result.bb_upper - result.bb_lower) / result.bb_mid
            rng = result.bb_upper - result.bb_lower
            if rng > 0:
                result.bb_pct = (result.close - result.bb_lower) / rng

        # ── Stochastic ────────────────────────────────────────────────────
        stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
        result.stoch_k = self._last(stoch.stoch())
        result.stoch_d = self._last(stoch.stoch_signal())

        # ── VWAP ──────────────────────────────────────────────────────────
        if timeframe != 'D1' and 'volume' in df.columns:
            try:
                result.vwap = self._last(
                    ta.volume.VolumeWeightedAveragePrice(high, low, close, df['volume']).volume_weighted_average_price()
                )
            except Exception:
                pass

        # ── Support / Resistance ──────────────────────────────────────────
        result.nearest_support, result.nearest_resistance = self._calc_sr(df, result.close)

        # ── Derived ───────────────────────────────────────────────────────
        result.is_oversold   = result.rsi is not None and result.rsi < 30
        result.is_overbought = result.rsi is not None and result.rsi > 70
        if result.ema200 is not None:
            result.price_above_ema200 = result.close > result.ema200
        result.trend_direction = self._determine_trend(result)

        return result

    # ── ATR-based SL/TP ────────────────────────────────────────────────────

    def calc_sl_tp(self, entry: float, direction: str, atr: float) -> tuple:
        if direction == 'BUY':
            sl = entry - (self.ATR_SL_MULTIPLIER * atr)
            tp = entry + (self.ATR_TP_MULTIPLIER * atr)
        else:
            sl = entry + (self.ATR_SL_MULTIPLIER * atr)
            tp = entry - (self.ATR_TP_MULTIPLIER * atr)
        return round(sl, 5), round(tp, 5)

    def calc_pip_distance(self, price1: float, price2: float, pair: str) -> float:
        diff = abs(price1 - price2)
        if pair.endswith('USDT'):
            # Crypto: 1 pip = $0.01 for coins > $1, proportional for smaller coins
            avg_price = (abs(price1) + abs(price2)) / 2 if price1 and price2 else 1
            if avg_price >= 1000:       # BTC, BNB
                return round(diff / 1.0, 1)
            elif avg_price >= 1:        # ETH, SOL, XRP, TON, ADA, LINK, SUI, DOT, HYPE
                return round(diff / 0.01, 1)
            else:                       # DOGE, PEPE (sub-dollar)
                return round(diff / 0.0001, 1)
        if 'JPY' in pair:
            return round(diff / 0.01, 1)
        if 'XAU' in pair:
            return round(diff / 0.1, 1)
        return round(diff / 0.0001, 1)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _last(series) -> Optional[float]:
        if series is None or series.empty:
            return None
        val = series.iloc[-1]
        if pd.isna(val):
            return None
        return float(val)

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    def _determine_trend(self, r: IndicatorResult) -> str:
        up = down = 0
        if r.ema20 and r.ema50:
            if r.close > r.ema20 > r.ema50:
                up += 2
            elif r.close < r.ema20 < r.ema50:
                down += 2
        if r.ema200:
            if r.close > r.ema200: up += 1
            else: down += 1
        if r.dmi_pos and r.dmi_neg:
            if r.dmi_pos > r.dmi_neg: up += 1
            else: down += 1
        if up >= 2: return 'UP'
        if down >= 2: return 'DOWN'
        return 'SIDEWAYS'

    @staticmethod
    def _calc_sr(df: pd.DataFrame, price: float, lookback: int = 50) -> tuple:
        sub = df.tail(min(lookback, len(df)))
        highs, lows = [], []
        for i in range(2, len(sub) - 2):
            h = sub['high'].iloc[i]
            l = sub['low'].iloc[i]
            if h >= sub['high'].iloc[i-2:i].max() and h >= sub['high'].iloc[i+1:i+3].max():
                highs.append(h)
            if l <= sub['low'].iloc[i-2:i].min() and l <= sub['low'].iloc[i+1:i+3].min():
                lows.append(l)
        support    = max((p for p in lows  if p < price), default=None)
        resistance = min((p for p in highs if p > price), default=None)
        return (
            round(support,    5) if support    else None,
            round(resistance, 5) if resistance else None,
        )
