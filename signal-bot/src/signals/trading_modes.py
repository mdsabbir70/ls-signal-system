"""
Trading Modes Configuration + Pattern-Based Signal Engine.

22 Trading Modes derived from mega pattern analysis (576,180 backtests):
  Mode 1:  Double_Bottom + RSI          → M15        (WR 71.6%, PF 5.91)
  Mode 2:  Rising_Wedge + ADX          → H4         (WR 74.0%, PF 18.82)
  Mode 3:  Double_Bottom + ADX         → H4 + M15   (WR 70.4%, PF 76.99)
  Mode 4:  Falling_Wedge + EMA_Trend   → M30        (WR 76.3%, PF 110.39)
  Mode 5:  Triple_Bottom + Alone       → M15 + H4   (WR 73.4%, PF 29.32)
  Mode 6:  Double_Top + RSI            → H1 SELL    (WR 73.0%, PF 4.59)
  Mode 7:  Ascending_Triangle + ADX    → H4 BUY     (WR 71.6%, PF 2.21)
  Mode 8:  Rounding_Bottom + RSI       → H4 BUY     (WR 69.3%, PF 5.19)
  Mode 9:  Descending_Triangle + ADX   → M30 SELL   (WR 69.7%, PF 2.13)
  Mode 10: Three_White_Soldiers + EMA  → H4 BUY     (WR 72.3%, PF 2.56)
  Mode 11: Mat_Hold + ADX              → H4 BUY     (WR 72.9%, PF 2.89)
  Mode 12: Rickshaw_Man + RSI          → M30 SELL   (WR 67.4%, PF 2.47)
  Mode 13: Shooting_Star + RSI         → M30 SELL   (WR 68.3%, PF 3.62)
  Mode 14: Upside_Gap_Three + Alone    → M15 BUY    (WR 71.2%, PF 3.25)
  Mode 15: Three_Line_Strike_Bear+EMA  → H1 SELL    (WR 70.2%, PF 1.82)
  Mode 16: Symmetrical_Triangle + EMA  → H1 BUY     (WR 69.0%, PF 3.12)
  Mode 17: Three_Outside_Down + RSI    → M30 SELL   (WR 66.9%, PF 3.38)
  Mode 18: Bull_Flag + Alone           → H1 BUY     (WR 62.1%, PF 1.60)
  Mode 19: Belt_Hold_Bull + EMA_Trend  → D1 BUY     (WR 69.1%, PF 3.18)
  Mode 20: Triple_Top + RSI            → H1 SELL    (WR 73.0%, PF 3.20)
  Mode 21: Tasuki_Gap_Bear + ADX       → M15 SELL   (WR 69.1%, PF 2.83)
  Mode 22: Tasuki_Gap_Bull + ADX       → M15 BUY    (WR 69.1%, PF 2.83)

Features:
  - All 21 modes run simultaneously (async)
  - Each signal tagged with mode name + emoji in Telegram
  - Economic calendar gate: block 30 min BEFORE, skip 30 min AFTER news
  - Cooldown per (mode, pair, timeframe) — avoids re-sending same pattern
  - SL/TP based on ATR × preset multiplier
"""

from __future__ import annotations

# ── Mode definitions ─────────────────────────────────────────────────────────

TRADING_MODES = [
    {
        'id':         1,
        'name':       'Mode_1',
        'emoji':      '🔵',
        'label':      '🔵 Mode 1: Double_Bottom + RSI',
        'pattern':    'Double_Bottom',
        'filter':     'RSI',
        'timeframes': ['M15'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 71.6% | PF 5.91 | 8,942 trades',
    },
    {
        'id':         2,
        'name':       'Mode_2',
        'emoji':      '🟠',
        'label':      '🟠 Mode 2: Rising_Wedge + ADX',
        'pattern':    'Rising_Wedge',
        'filter':     'ADX',
        'timeframes': ['H4'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 74.0% | PF 18.82 | 959 trades',
    },
    {
        'id':         3,
        'name':       'Mode_3',
        'emoji':      '🟢',
        'label':      '🟢 Mode 3: Double_Bottom + ADX',
        'pattern':    'Double_Bottom',
        'filter':     'ADX',
        'timeframes': ['H4', 'M15'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 70.4% | PF 76.99 (H4) | 6,554 trades',
    },
    {
        'id':         4,
        'name':       'Mode_4',
        'emoji':      '🟡',
        'label':      '🟡 Mode 4: Falling_Wedge + EMA_Trend',
        'pattern':    'Falling_Wedge',
        'filter':     'EMA_Trend',
        'timeframes': ['M30'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 76.3% | PF 110.39 | 520 trades',
    },
    {
        'id':         5,
        'name':       'Mode_5',
        'emoji':      '🟣',
        'label':      '🟣 Mode 5: Triple_Bottom + Alone',
        'pattern':    'Triple_Bottom',
        'filter':     'Alone',
        'timeframes': ['M15', 'H4'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 73.4% | PF 29.32 (H4) | 8,256 trades',
    },

    # ── Modes 6-21: Added from top 20 backtest strategies ────────────────────

    {
        'id':         6,
        'name':       'Mode_6',
        'emoji':      '🔴',
        'label':      '🔴 Mode 6: Double_Top + RSI',
        'pattern':    'Double_Top',
        'filter':     'RSI',
        'timeframes': ['H1'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 73.0% | PF 4.59 | 111,570 trades',
    },
    {
        'id':         7,
        'name':       'Mode_7',
        'emoji':      '🔶',
        'label':      '🔶 Mode 7: Ascending_Triangle + ADX',
        'pattern':    'Ascending_Triangle',
        'filter':     'ADX',
        'timeframes': ['H4'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 71.6% | PF 2.21 | 41,723 trades',
    },
    {
        'id':         8,
        'name':       'Mode_8',
        'emoji':      '🔷',
        'label':      '🔷 Mode 8: Rounding_Bottom + RSI',
        'pattern':    'Rounding_Bottom',
        'filter':     'RSI',
        'timeframes': ['H4'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.3% | PF 5.19 | 33,688 trades',
    },
    {
        'id':         9,
        'name':       'Mode_9',
        'emoji':      '🟥',
        'label':      '🟥 Mode 9: Descending_Triangle + ADX',
        'pattern':    'Descending_Triangle',
        'filter':     'ADX',
        'timeframes': ['M30'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.7% | PF 2.13 | 33,847 trades',
    },
    {
        'id':         10,
        'name':       'Mode_10',
        'emoji':      '🟦',
        'label':      '🟦 Mode 10: Three_White_Soldiers + EMA_Trend',
        'pattern':    'Three_White_Soldiers',
        'filter':     'EMA_Trend',
        'timeframes': ['H4'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 72.3% | PF 2.56 | 31,781 trades',
    },
    {
        'id':         11,
        'name':       'Mode_11',
        'emoji':      '🟧',
        'label':      '🟧 Mode 11: Mat_Hold + ADX',
        'pattern':    'Mat_Hold',
        'filter':     'ADX',
        'timeframes': ['H4'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 72.9% | PF 2.89 | 29,464 trades',
    },
    {
        'id':         12,
        'name':       'Mode_12',
        'emoji':      '🩶',
        'label':      '🩶 Mode 12: Rickshaw_Man + RSI',
        'pattern':    'Rickshaw_Man',
        'filter':     'RSI',
        'timeframes': ['M30'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 67.4% | PF 2.47 | 33,191 trades',
    },
    {
        'id':         13,
        'name':       'Mode_13',
        'emoji':      '🩷',
        'label':      '🩷 Mode 13: Shooting_Star + RSI',
        'pattern':    'Shooting_Star',
        'filter':     'RSI',
        'timeframes': ['M30'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 68.3% | PF 3.62 | 28,890 trades',
    },
    {
        'id':         14,
        'name':       'Mode_14',
        'emoji':      '🩵',
        'label':      '🩵 Mode 14: Upside_Gap_Three + Alone',
        'pattern':    'Upside_Gap_Three',
        'filter':     'Alone',
        'timeframes': ['M15'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 71.2% | PF 3.25 | 16,499 trades',
    },
    {
        'id':         15,
        'name':       'Mode_15',
        'emoji':      '🖤',
        'label':      '🖤 Mode 15: Three_Line_Strike_Bear + EMA_Trend',
        'pattern':    'Three_Line_Strike_Bear',
        'filter':     'EMA_Trend',
        'timeframes': ['H1'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 70.2% | PF 1.82 | 14,124 trades',
    },
    {
        'id':         16,
        'name':       'Mode_16',
        'emoji':      '🤍',
        'label':      '🤍 Mode 16: Symmetrical_Triangle + EMA_Trend',
        'pattern':    'Symmetrical_Triangle',
        'filter':     'EMA_Trend',
        'timeframes': ['H1'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.0% | PF 3.12 | 53,011 trades',
    },
    {
        'id':         17,
        'name':       'Mode_17',
        'emoji':      '🟫',
        'label':      '🟫 Mode 17: Three_Outside_Down + RSI',
        'pattern':    'Three_Outside_Down',
        'filter':     'RSI',
        'timeframes': ['M30'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 66.9% | PF 3.38 | 93,859 trades',
    },
    # Mode 18 (Bull_Flag + Alone H1) DISABLED:
    # WR 62.1% with SL2.0/TP1.0 → negative EV (break-even needs WR ≥ 66.7%)
    # Re-enable only if a better SL/TP combo is found in backtest.
    # {
    #     'id': 18, 'name': 'Mode_18', 'pattern': 'Bull_Flag',
    #     'filter': 'Alone', 'timeframes': ['H1'], 'direction': 'BUY',
    #     'sl_mult': 2.0, 'tp_mult': 1.0,
    # },
    {
        'id':         19,
        'name':       'Mode_19',
        'emoji':      '🧡',
        'label':      '🧡 Mode 19: Belt_Hold_Bull + EMA_Trend',
        'pattern':    'Belt_Hold_Bull',
        'filter':     'EMA_Trend',
        'timeframes': ['D1'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.1% | PF 3.18 | 66,366 trades',
    },
    {
        'id':         20,
        'name':       'Mode_20',
        'emoji':      '❤️',
        'label':      '❤️ Mode 20: Triple_Top + RSI',
        'pattern':    'Triple_Top',
        'filter':     'RSI',
        'timeframes': ['H1'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 73.0% | PF 3.20 | 74,391 trades',
    },
    {
        'id':         21,
        'name':       'Mode_21',
        'emoji':      '💙',
        'label':      '💙 Mode 21: Tasuki_Gap_Bear + ADX',
        'pattern':    'Tasuki_Gap_Bear',
        'filter':     'ADX',
        'timeframes': ['M15'],
        'direction':  'SELL',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.1% | PF 2.83 | 52,977 trades',
    },
    {
        'id':         22,
        'name':       'Mode_22',
        'emoji':      '💚',
        'label':      '💚 Mode 22: Tasuki_Gap_Bull + ADX',
        'pattern':    'Tasuki_Gap_Bull',
        'filter':     'ADX',
        'timeframes': ['M15'],
        'direction':  'BUY',
        'sl_mult':    2.0,
        'tp_mult':    1.0,
        'stats':      'WR 69.1% | PF 2.83 | 52,977 trades',
    },
]

# Bars to fetch per timeframe (enough history for pattern detection)
TF_BARS = {
    'M5':  500,
    'M15': 300,
    'M30': 200,
    'H1':  200,
    'H4':  150,
    'D1':  200,
}

# Cooldown minutes per timeframe — skip re-sending same (mode, pair, tf) pair
TF_COOLDOWN_MINS = {
    'M5':   30,
    'M15':  60,
    'M30':  90,
    'H1':   180,
    'H4':   480,
    'D1':   1440,
}
