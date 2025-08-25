from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from indicators import sma
from utils import max_drawdown, cagr, sharpe

@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    metrics: Dict[str, float]

def _to_1d_series(x: Any, index=None) -> pd.Series:
    # ndarray/list/tuple → raveled 1-D
    if isinstance(x, (np.ndarray, list, tuple)):
        arr = np.asarray(x).reshape(-1)          # <- key line (ravel to 1-D)
        s = pd.Series(arr, index=index)
    elif isinstance(x, pd.DataFrame):
        s = x.iloc[:, 0]                          # first column
    elif isinstance(x, pd.Series):
        s = x
    else:
        # last resort: try to build a Series then ravel
        s = pd.Series(np.asarray(x).reshape(-1), index=index)
    s = pd.to_numeric(s, errors="coerce").astype(float).dropna()
    return s

def backtest_sma_cross(prices: Any, fast: int = 50, slow: int = 200) -> BacktestResult:
    prices = _to_1d_series(prices)

    if not isinstance(fast, int) or not isinstance(slow, int):
        raise ValueError("fast and slow must be integers.")
    if fast >= slow:
        raise ValueError("For SMA cross, fast must be < slow.")

    need = max(slow, fast) + 5
    if len(prices) < need:
        raise ValueError(f"Not enough data: have {len(prices)}, need ≥ {need}.")

    fast_sma = sma(prices, fast)
    slow_sma = sma(prices, slow)

    signal = (fast_sma > slow_sma).astype(int).shift(1).reindex(prices.index).fillna(0)
    daily_ret = prices.pct_change().fillna(0.0)
    strat_ret = daily_ret * signal
    equity = (1.0 + strat_ret).cumprod()

    metrics = {
        "CAGR": float(cagr(equity)),
        "Sharpe": float(sharpe(strat_ret)),
        "MaxDrawdown": float(max_drawdown(equity)),
        "WinRate": float((strat_ret > 0).mean()),
    }
    return BacktestResult(equity=equity, returns=strat_ret, metrics=metrics)

def optimize_sma_grid(
    prices: Any,
    fast_values: List[int],
    slow_values: List[int],
    split: float = 0.7,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Grid search fast/slow. Rank by in-sample Sharpe, choose best by out-of-sample Sharpe."""
    series = _to_1d_series(prices)
    n = len(series)
    if n < 260:
        raise ValueError("Need at least ~260 bars for a meaningful split.")
    split_idx = max(1, min(n - 1, int(n * split)))
    is_prices = series.iloc[:split_idx]
    os_prices = series.iloc[split_idx:]

    rows: List[Dict[str, Any]] = []
    for f in sorted(set(fast_values)):
        for s in sorted(set(slow_values)):
            if f >= s:
                continue
            # ensure each segment has enough data
            need = max(f, s) + 5
            if len(is_prices) < need or len(os_prices) < need:
                continue
            try:
                is_res = backtest_sma_cross(is_prices, fast=f, slow=s)
                os_res = backtest_sma_cross(os_prices, fast=f, slow=s)
                rows.append({
                    "fast": f, "slow": s,
                    "IS": is_res.metrics, "OS": os_res.metrics
                })
            except Exception:
                continue

    if not rows:
        raise ValueError("No valid parameter pairs (fast<slow) with enough data.")

    # rank by IS Sharpe, keep top_k
    rows.sort(key=lambda r: r["IS"].get("Sharpe", 0.0), reverse=True)
    finalists = rows[:max(1, top_k)]

    # pick best by OS Sharpe
    best = max(finalists, key=lambda r: r["OS"].get("Sharpe", -1e9))

    return {
        "split": split,
        "bars_total": n,
        "bars_is": int(len(is_prices)),
        "bars_os": int(len(os_prices)),
        "best": best,
        "leaderboard": finalists,
    }