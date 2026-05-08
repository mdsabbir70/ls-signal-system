"""
pair_config.py — Single source of truth for all pair-specific settings.

Every module imports from here. NEVER hardcode pip_size, pip_value,
or decimal places anywhere else.

Usage:
    from utils.pair_config import get_pair_config
    cfg = get_pair_config('PEPEUSDT')
    cfg['pip_size']    # 0.00000001
    cfg['pip_value']   # 1.0
    cfg['decimals']    # 8
    cfg['max_lot']     # 10.0
    cfg['is_crypto']   # True
"""

_PAIR_CONFIGS = {
    # ── Crypto ────────────────────────────────────────────────────────
    'BTCUSDT':  {'pip_size': 1.0,          'pip_value': 1.0, 'decimals': 2, 'max_lot': 10.0},
    'ETHUSDT':  {'pip_size': 0.1,          'pip_value': 1.0, 'decimals': 2, 'max_lot': 10.0},
    'BNBUSDT':  {'pip_size': 0.1,          'pip_value': 1.0, 'decimals': 2, 'max_lot': 10.0},
    'SOLUSDT':  {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'LINKUSDT': {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'DOTUSDT':  {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'ADAUSDT':  {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'TONUSDT':  {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'HYPEUSDT': {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'SUIUSDT':  {'pip_size': 0.01,         'pip_value': 1.0, 'decimals': 4, 'max_lot': 10.0},
    'XRPUSDT':  {'pip_size': 0.001,        'pip_value': 1.0, 'decimals': 6, 'max_lot': 10.0},
    'DOGEUSDT': {'pip_size': 0.001,        'pip_value': 1.0, 'decimals': 6, 'max_lot': 10.0},
    'PEPEUSDT': {'pip_size': 0.00000001,   'pip_value': 1.0, 'decimals': 8, 'max_lot': 10.0},
}

# ── Forex defaults (by suffix/keyword) ───────────────────────────────
_FOREX_DEFAULTS = {
    'JPY':  {'pip_size': 0.01,  'pip_value': 10.0, 'decimals': 3, 'max_lot': 1.0},
    'XAU':  {'pip_size': 0.1,   'pip_value': 10.0, 'decimals': 2, 'max_lot': 1.0},
    'XAG':  {'pip_size': 0.1,   'pip_value': 10.0, 'decimals': 2, 'max_lot': 1.0},
}
_FOREX_FALLBACK = {'pip_size': 0.0001, 'pip_value': 10.0, 'decimals': 5, 'max_lot': 1.0}


def get_pair_config(pair: str) -> dict:
    """Return pip_size, pip_value, decimals, max_lot, is_crypto for any pair."""
    # Exact match first (crypto)
    if pair in _PAIR_CONFIGS:
        cfg = dict(_PAIR_CONFIGS[pair])
        cfg['is_crypto'] = True
        return cfg

    # Forex keyword match
    for key, cfg in _FOREX_DEFAULTS.items():
        if key in pair:
            out = dict(cfg)
            out['is_crypto'] = False
            return out

    # Forex fallback
    out = dict(_FOREX_FALLBACK)
    out['is_crypto'] = False
    return out


def pip_size(pair: str) -> float:
    return get_pair_config(pair)['pip_size']

def pip_value(pair: str) -> float:
    return get_pair_config(pair)['pip_value']

def price_decimals(pair: str) -> int:
    return get_pair_config(pair)['decimals']

def max_lot(pair: str) -> float:
    return get_pair_config(pair)['max_lot']

def is_crypto(pair: str) -> bool:
    return get_pair_config(pair)['is_crypto']

def price_fmt(price: float, pair: str) -> str:
    """Format price with correct decimal places."""
    d = price_decimals(pair)
    return f"{price:.{d}f}"
