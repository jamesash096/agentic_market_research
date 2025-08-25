from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf
import feedparser
import requests

PRICE_CACHE: dict[tuple[str, int], pd.DataFrame] = {}

def get_price_history(symbol: str, days: int = 365):
    key = (symbol.upper(), int(days))
    if key in PRICE_CACHE:
        # return a copy so callers don't mutate the cached frame
        return PRICE_CACHE[key].copy()

    df = yf.download(
        symbol,
        period=f"{days}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
        group_by="column",   # ensure non-multiindex columns
    )
    if df is None or df.empty:
        raise ValueError(f"No price data for {symbol}")

    df = df.rename(columns=lambda c: str(c).strip().lower())
    # ensure a 'close' column exists
    if "close" not in df.columns:
        if "adj close" in df.columns:
            df["close"] = df["adj close"]
        elif isinstance(df.columns, pd.MultiIndex):
            # rare case: squeeze multiindex like ('Close', '') → 'close'
            candidates = [c for c in df.columns if str(c[0]).lower() == "close"]
            if candidates:
                df["close"] = df[candidates[0]]
            else:
                # last resort: first numeric col
                num = df.select_dtypes(include=[np.number])
                if not num.empty:
                    df["close"] = num.iloc[:, 0]
                else:
                    raise ValueError(f"Missing close prices for {symbol}")
        else:
            # last resort: first numeric col
            num = df.select_dtypes(include=[np.number])
            if not num.empty:
                df["close"] = num.iloc[:, 0]
            else:
                raise ValueError(f"Missing close prices for {symbol}")

    df = df.dropna()
    # store a copy in cache; return another copy to caller
    PRICE_CACHE[key] = df.copy()
    return df.copy()

def get_news_headlines(symbol: str, limit: int = 20):
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
    feed = feedparser.parse(url)
    items = [(e.get("title",""), e.get("link",""), e.get("published","")) for e in feed.entries]
    if not items:
        q = requests.utils.quote(f"{symbol} stock")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        items = [(e.get("title",""), e.get("link",""), e.get("published","")) for e in feed.entries]
    return items[:limit]