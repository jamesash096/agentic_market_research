import pandas as pd
import numpy as np
from backtest import backtest_sma_cross

def test_backtest_shapes_and_metrics():
    np.random.seed(0)
    prices = pd.Series(100*np.exp(np.cumsum(np.random.normal(0,0.01,1000))))
    res = backtest_sma_cross(prices, fast=20, slow=100)
    assert "CAGR" in res.metrics and "Sharpe" in res.metrics
    assert len(res.equity) == len(prices)
    assert np.isfinite(list(res.metrics.values())).all()