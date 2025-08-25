from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, List
import numpy as np
import pandas as pd
from nltk.sentiment import SentimentIntensityAnalyzer
from data import get_price_history, get_news_headlines
from indicators import sma, rsi, momentum

@dataclass
class AnalysisResult:
    symbol: str
    signals: Dict[str, float]
    sentiment_compound: float
    recommendation: str
    confidence: float
    rationale: str

class MarketAgent:
    def __init__(self):
        try:
            self._sent = SentimentIntensityAnalyzer()
        except Exception:
            self._sent = None

    def _news_sentiment(self, symbol: str):
        headlines = get_news_headlines(symbol)
        titles = [t for (t, _, _) in headlines]
        if not titles or self._sent is None:
            return 0.0, titles
        scores = [self._sent.polarity_scores(t)["compound"] for t in titles]
        return float(np.mean(scores)), titles
    
    def screen(self, symbols: List[str], days: int = 365):
        results, errors = [], []
        for s in symbols:
            try:
                r = self.analyze(s, days=days)
                results.append({
                    "symbol": r.symbol,
                    "recommendation": r.recommendation,
                    "confidence": float(r.confidence if r.confidence == r.confidence else 0.5),
                    "signals": r.signals
                })
            except Exception:
                errors.append({"symbol": s, "error": str(e)})
        results.sort(key=lambda x: x['confidence'], reverse=True)
        return {"results": results, "errors": errors}
    
    def analyze(self, symbol: str, days: int = 365):
        df = get_price_history(symbol, days=days)
        if "close" in df.columns:
            close_obj = df["close"]
        elif "adj close" in df.columns:
            close_obj = df["adj close"]
        else:
            # fallback to first numeric column
            close_obj = df.select_dtypes(include=[np.number]).iloc[:, 0]

        # If it’s a 1-col DataFrame or a (N,1) ndarray, squeeze it to 1-D
        if isinstance(close_obj, pd.DataFrame):
            close = close_obj.iloc[:, 0]
        else:
            # handles Series or ndarray
            close = pd.Series(np.asarray(close_obj).ravel(), index=df.index)

        close = pd.to_numeric(close, errors="coerce").dropna().astype(float)

        # --- Indicators as SERIES ---
        sma_fast_series = sma(close, 50)
        sma_slow_series = sma(close, 200)
        rsi_series      = rsi(close, 14)
        lookback        = max(1, min(126, len(close) // 2))
        mom_series      = close.pct_change(lookback)

        # --- Align last valid row across SMAs to avoid NaN at tail ---
        tail = (
            pd.concat([sma_fast_series, sma_slow_series], axis=1)
            .dropna()
        )
        if tail.empty:
            # Not enough history for SMAs; degrade gracefully
            trend_val = 0.0
        else:
            fast_last = float(tail.iloc[-1, 0])
            slow_last = float(tail.iloc[-1, 1])
            trend_val = 1.0 if fast_last > slow_last else 0.0  # SCALAR comparison ✅

        # --- Safe scalar extraction for RSI & Momentum ---
        rsi_val = float(rsi_series.dropna().iloc[-1]) if rsi_series.dropna().size else np.nan
        mom_val = float(mom_series.dropna().iloc[-1]) if mom_series.dropna().size else 0.0

        # --- Scores (normalize to [0,1]) ---
        # Momentum: squash tails
        mom_score = (np.tanh(mom_val * 3.0) + 1.0) / 2.0

        # RSI: reward <30, penalize >70; neutral otherwise
        if np.isnan(rsi_val):
            rsi_score = 0.5
        elif rsi_val >= 70:
            rsi_score = 0.2
        elif rsi_val <= 30:
            rsi_score = 0.8
        else:
            rsi_score = 0.5

        # Sentiment
        sent_raw, _ = self._news_sentiment(symbol)
        sent_score = (sent_raw + 1.0) / 2.0  # -1..1 -> 0..1

        # --- Blend (weights configurable later) ---
        w = {"momentum": 0.45, "rsi": 0.20, "trend": 0.15, "sentiment": 0.20}
        overall = (
            w["momentum"] * float(mom_score) +
            w["rsi"]      * float(rsi_score) +
            w["trend"]    * float(trend_val) +
            w["sentiment"]* float(sent_score)
        )

        rec = "BUY" if overall > 0.60 else ("HOLD" if overall > 0.40 else "SELL")
        rationale = (
            f"Momentum={mom_score:.2f}, RSI flag={rsi_score:.2f}, Trend={trend_val:.2f}, "
            f"News sentiment={sent_score:.2f} ⇒ {rec} (conf {overall:.2f})"
        )

        return AnalysisResult(
            symbol=symbol,
            signals={
                "momentum": float(mom_score),
                "rsi": float(rsi_score),
                "trend": float(trend_val),
                "sentiment": float(sent_score),
                "overall": float(overall),
            },
            sentiment_compound=float(sent_raw),
            recommendation=rec,
            confidence=float(overall),
            rationale=rationale,
        )