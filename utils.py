from __future__ import annotations
import numpy as np
import pandas as pd

def max_drawdown(equity: pd.Series):
    e = pd.Series(equity, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if e.empty:
        return 0.0
    peak = e.cummax()
    dd = (peak - e) / peak           # 0..1 by construction
    dd = dd.clip(lower=0, upper=1)   # safety clamp
    return float(dd.max())

def cagr(equity: pd.Series, periods_per_year: int = 252):
    e = pd.Series(equity, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if e.empty or e.iloc[0] <= 0:
        return 0.0
    years = len(e) / periods_per_year
    if years <= 0:
        return 0.0
    total = e.iloc[-1] / e.iloc[0]
    if total <= 0:
        return 0.0
    return float(total ** (1 / years) - 1)

def sharpe(returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252):
    r = pd.Series(returns, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty or r.std(ddof=0) == 0:
        return 0.0
    excess = r - (rf / periods_per_year)
    return float(np.sqrt(periods_per_year) * (excess.mean() / (excess.std(ddof=0) + 1e-12)))