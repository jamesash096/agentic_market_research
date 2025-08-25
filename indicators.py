from __future__ import annotations
import numpy as np
import pandas as pd

def sma(series: pd.Series, window: int):
    return series.rolling(window, min_periods=window).mean()

def rsi(series: pd.Series, window: int = 14):
    delta = series.diff()
    up = (delta.clip(lower=0)).ewm(alpha=1/window, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/window, adjust=False).mean()
    rs = up / (down + 1e-12)
    return 100 - (100 / (1 + rs))

def momentum(series: pd.Series, lookback: int = 126):
    return series.pct_change(lookback)