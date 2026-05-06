"""
Stop Hunt Detector
Detects if proposed SL/TP levels are at common "stop hunt" zones:
  - Swing high/low levels (within ATR tolerance)
  - Round numbers (e.g. 1.1000, 1.1050)
  - Whole/half pip clusters

Returns adjusted SL/TP if a hunt zone is detected.
"""

from __future__ import annotations
import math
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger('stop_hunt')


class StopHuntDetector:
    """Detects and avoids stop hunt zones around SL/TP levels."""

    # How close to a round number triggers a warning (in pips)
    ROUND_NUMBER_BUFFER_PIPS = 5.0
    # How close to a swing level triggers a warning (in pips)
    SWING_LEVEL_BUFFER_PIPS  = 3.0

    def check(
        self,
        pair: str,
        direction: str,
        stop_loss: float,
        take_profit: float,
        swing_highs: list[float],
        swing_lows:  list[float],
        atr: float,
    ) -> dict:
        """
        Check if SL/TP are in stop hunt zones.
        Returns dict with:
          - is_safe (bool)
          - warnings (list of strings)
          - adjusted_sl (float)  — adjusted if near a hunt zone
          - adjusted_tp (float)
        """
        pip_size = self._pip_size(pair)

        warnings = []
        adjusted_sl = stop_loss
        adjusted_tp = take_profit

        # ── SL checks ─────────────────────────────────────────────────────
        sl_round, sl_round_dist = self._nearest_round_number(stop_loss, pair)
        if sl_round_dist < self.ROUND_NUMBER_BUFFER_PIPS:
            warnings.append(
                f"SL near round number {sl_round:.5f} ({sl_round_dist:.1f} pips away)"
            )
            # Push SL further away from the round number
            buffer = (self.ROUND_NUMBER_BUFFER_PIPS + 2) * pip_size
            if direction == 'BUY':
                adjusted_sl = stop_loss - buffer  # Move SL down (further from entry)
            else:
                adjusted_sl = stop_loss + buffer  # Move SL up

        # Check SL vs swing levels
        hunt_level = self._nearest_swing_level(
            stop_loss, swing_lows if direction == 'BUY' else swing_highs, pip_size
        )
        if hunt_level is not None:
            dist_pips = abs(stop_loss - hunt_level) / pip_size
            if dist_pips < self.SWING_LEVEL_BUFFER_PIPS:
                warnings.append(
                    f"SL near swing level {hunt_level:.5f} ({dist_pips:.1f} pips away)"
                )
                buffer = (self.SWING_LEVEL_BUFFER_PIPS + 2) * pip_size
                if direction == 'BUY':
                    adjusted_sl = min(adjusted_sl, hunt_level - buffer)
                else:
                    adjusted_sl = max(adjusted_sl, hunt_level + buffer)

        # ── TP checks ─────────────────────────────────────────────────────
        tp_round, tp_round_dist = self._nearest_round_number(take_profit, pair)
        if tp_round_dist < self.ROUND_NUMBER_BUFFER_PIPS:
            warnings.append(
                f"TP near round number {tp_round:.5f} ({tp_round_dist:.1f} pips away)"
            )
            # Pull TP slightly before the round number (take profit before crowd)
            buffer = (self.ROUND_NUMBER_BUFFER_PIPS + 1) * pip_size
            if direction == 'BUY':
                adjusted_tp = tp_round - buffer
            else:
                adjusted_tp = tp_round + buffer

        tp_hunt = self._nearest_swing_level(
            take_profit, swing_highs if direction == 'BUY' else swing_lows, pip_size
        )
        if tp_hunt is not None:
            dist_pips = abs(take_profit - tp_hunt) / pip_size
            if dist_pips < self.SWING_LEVEL_BUFFER_PIPS:
                warnings.append(
                    f"TP near swing level {tp_hunt:.5f} ({dist_pips:.1f} pips away)"
                )
                buffer = (self.SWING_LEVEL_BUFFER_PIPS + 1) * pip_size
                if direction == 'BUY':
                    adjusted_tp = tp_hunt - buffer
                else:
                    adjusted_tp = tp_hunt + buffer

        is_safe = len(warnings) == 0

        if warnings:
            logger.debug(
                f"Stop hunt zones detected for {pair} {direction}: {'; '.join(warnings)}"
            )

        return {
            'is_safe':     is_safe,
            'warnings':    warnings,
            'adjusted_sl': round(adjusted_sl, 5),
            'adjusted_tp': round(adjusted_tp, 5),
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _pip_size(pair: str) -> float:
        """Return pip size for a given pair."""
        if 'JPY' in pair:
            return 0.01
        if 'XAU' in pair:
            return 0.1
        return 0.0001

    def _nearest_round_number(self, price: float, pair: str) -> tuple[float, float]:
        """
        Find the nearest round number and return (round_price, distance_in_pips).
        Round numbers for Forex: X.XX00, X.XX50 (every 50 pips)
        For JPY pairs: X.00, X.50
        For Gold: XX0.0, XX5.0
        """
        pip_size = self._pip_size(pair)

        if 'JPY' in pair:
            # Round numbers every 0.50
            step = 0.50
        elif 'XAU' in pair:
            # Round numbers every 5.0 (e.g. 2000, 2005, 2010...)
            step = 5.0
        else:
            # Round numbers every 0.0050 (50 pips)
            step = 0.0050

        rounded = round(price / step) * step
        dist_pips = abs(price - rounded) / pip_size

        return round(rounded, 5), round(dist_pips, 1)

    @staticmethod
    def _nearest_swing_level(
        price: float,
        levels: list[float],
        pip_size: float,
    ) -> Optional[float]:
        """Find the swing level nearest to price. Returns None if list empty."""
        if not levels:
            return None
        return min(levels, key=lambda lvl: abs(price - lvl))
