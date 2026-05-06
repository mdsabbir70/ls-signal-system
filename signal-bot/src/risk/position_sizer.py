"""
Position Sizer — Forex
Calculates lot size based on:
  - Account balance
  - Risk % per trade (from settings)
  - Stop loss distance in pips
  - Pair pip value

Formula:
  Lot Size = (Balance × Risk%) / (SL pips × Pip Value per lot)

Pip values (per standard lot = 100,000 units):
  EURUSD: $10 per pip
  GBPUSD: $10 per pip
  USDJPY: ~$7.60 per pip (varies with USD/JPY rate)
  XAUUSD: $10 per pip (0.1 movement)

Lot size limits:
  Min: 0.01 (micro lot)
  Max: configurable (default 1.0 standard lot)
"""

from __future__ import annotations
from utils.logger import setup_logger

logger = setup_logger('position_sizer')

# Approximate pip values per standard lot in USD
# Accurate enough for signal-only system (not live execution)
PIP_VALUES_USD = {
    'EURUSD': 10.0,
    'GBPUSD': 10.0,
    'USDJPY': 9.0,    # Approximate; depends on current rate
    'USDCHF': 10.0,
    'AUDUSD': 10.0,
    'USDCAD': 7.7,
    'NZDUSD': 10.0,
    'XAUUSD': 10.0,   # Gold: 1 pip = $0.1, 100 pips = $10 per mini lot
    'EURJPY': 9.0,
    'GBPJPY': 9.0,
    'AUDJPY': 9.0,
    'EURGBP': 12.8,   # Approximate in USD
}


class PositionSizer:
    """Calculates Forex lot size with risk management."""

    MIN_LOT   = 0.01
    MAX_LOT   = 1.0
    LOT_STEP  = 0.01  # Broker minimum increment

    def __init__(self, max_lot: float = 1.0):
        self.MAX_LOT = max_lot

    def calculate(
        self,
        pair: str,
        account_balance: float,
        risk_pct: float,
        sl_pips: float,
    ) -> dict:
        """
        Calculate lot size.
        Returns dict with lot_size, risk_amount, pip_value.
        """
        if account_balance <= 0:
            logger.warning("Account balance is 0 or negative")
            return self._result(0.0, 0.0, pair)

        if sl_pips <= 0:
            logger.warning(f"Invalid SL pips: {sl_pips}")
            return self._result(0.0, 0.0, pair)

        pip_value = PIP_VALUES_USD.get(pair, 10.0)
        risk_amount = account_balance * (risk_pct / 100.0)

        # Lot size = risk_amount / (sl_pips × pip_value)
        raw_lot = risk_amount / (sl_pips * pip_value)

        # Clamp to allowed range
        lot_size = max(self.MIN_LOT, min(self.MAX_LOT, raw_lot))

        # Round to broker step size
        lot_size = round(int(lot_size / self.LOT_STEP) * self.LOT_STEP, 2)

        actual_risk = lot_size * sl_pips * pip_value

        logger.debug(
            f"{pair}: balance=${account_balance:.0f} risk={risk_pct}% "
            f"sl={sl_pips:.0f}pips → lot={lot_size} risk=${actual_risk:.2f}"
        )

        return self._result(lot_size, actual_risk, pair)

    @staticmethod
    def _result(lot_size: float, risk_amount: float, pair: str) -> dict:
        return {
            'lot_size':    lot_size,
            'risk_amount': round(risk_amount, 2),
            'pip_value':   PIP_VALUES_USD.get(pair, 10.0),
        }
