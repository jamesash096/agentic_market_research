# streamlit_app.py
from __future__ import annotations
import os
import sys
import json
import time
import math
import requests
import pandas as pd
import plotly.graph_objs as go
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# -----------------------------
# Config
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

DEFAULT_API_BASE = os.getenv("MARKET_AGENT_API_BASE")

st.set_page_config(page_title="Market Research Agent", layout="wide")

# -----------------------------
# Helpers: API client wrappers
# -----------------------------
class ApiError(Exception): ...

def api_get(api_base: str, path: str, params: dict | None = None):
    url = f"{api_base.rstrip('/')}{path}"
    r = requests.get(url, params=params or {}, timeout=60)
    if not r.ok:
        raise ApiError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
    return r.json()

def api_post(api_base: str, path: str, payload: dict):
    url = f"{api_base.rstrip('/')}{path}"
    r = requests.post(url, json=payload, timeout=120)
    if not r.ok:
        raise ApiError(f"POST {path} -> {r.status_code}: {r.text[:200]}")
    return r.json()

# Cache reports & dates briefly (avoid hammering the API)
@st.cache_data(ttl=60)
def get_report_dates(api_base: str):
    try:
        return api_get(api_base, "/reports/dates")
    except ApiError:
        # If the API doesn't expose dates yet, fallback to just ["latest"]
        return ["latest"]

@st.cache_data(ttl=60)
def get_report_latest(api_base: str):
    return api_get(api_base, "/report/latest")

@st.cache_data(ttl=60)
def get_report_by_date(api_base: str, date: str):
    return api_get(api_base, f"/report/{date}")

@st.cache_data(ttl=30)
def post_backtest(api_base: str, symbol: str, fast: int, slow: int, days: int, include_series: bool = True):
    payload = {
        "symbol": symbol,
        "strategy": "sma_cross",
        "params": {"fast": int(fast), "slow": int(slow)},
        "days": int(days),
        "include_series": bool(include_series),
    }
    return api_post(api_base, "/backtest", payload)

@st.cache_data(ttl=30)
def post_optimize(api_base: str, symbol: str, days: int, fast_values, slow_values, split: float, top_k: int):
    payload = {
        "symbol": symbol,
        "days": int(days),
        "fast_values": list(map(int, fast_values)),
        "slow_values": list(map(int, slow_values)),
        "split": float(split),
        "top_k": int(top_k),
    }
    return api_post(api_base, "/optimize_backtest", payload)

def maybe_post_agent_run(api_base: str, symbols: list[str] | None, days: int):
    try:
        payload = {"symbols": symbols, "days": int(days)}
        return api_post(api_base, "/agent/run_once", payload)
    except ApiError as e:
        # Endpoint optional; surface a friendly message
        st.warning("`/agent/run_once` endpoint not available in your API (optional).")
        return None

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("Settings")
api_base = st.sidebar.text_input("FastAPI base URL", DEFAULT_API_BASE)

cols = st.sidebar.columns(2)
with cols[0]:
    refresh = st.button("🔄 Refresh")
with cols[1]:
    # Optional: trigger agent once (works if you added the endpoint earlier)
    run_agent = st.button("🤖 Run agent now")

# Select date (latest or specific)
dates = get_report_dates(api_base)
date_choice = st.sidebar.selectbox("Report date", options=(["latest"] + dates if "latest" not in dates else dates))

# Advanced (collapsed)
with st.sidebar.expander("Advanced", expanded=False):
    default_days_bt = st.number_input("Backtest days", min_value=200, max_value=3000, value=1200, step=50)
    # Defaults for optimizer in the UI
    fvals = st.text_input("Fast values (comma-separated)", "10,20,50")
    svals = st.text_input("Slow values (comma-separated)", "100,150,200,250")
    split = st.slider("IS/OS split", 0.5, 0.9, 0.7, 0.05)
    topk = st.slider("Optimizer top_k", 1, 10, 5, 1)

if refresh:
    st.cache_data.clear()

if run_agent:
    with st.spinner("Running agent once..."):
        res = maybe_post_agent_run(api_base, symbols=None, days=365)
    if res is not None:
        st.success("Agent run invoked. Click Refresh in a few seconds.")

# -----------------------------
# Load report
# -----------------------------
try:
    if date_choice == "latest":
        report = get_report_latest(api_base)
    else:
        report = get_report_by_date(api_base, date_choice)
except ApiError as e:
    st.error(f"Could not load report: {e}")
    st.stop()

# -----------------------------
# Header
# -----------------------------
st.title("Daily Market Research (Autonomous Agent)")
st.caption("Educational demo only — not financial advice.")
st.write(f"**Report time:** {report.get('date','?')}")
universe = report.get("universe", [])
st.write(f"**Universe size:** {len(universe)}")
artifacts = report.get("artifacts", {})

# -----------------------------
# Top Picks section
# -----------------------------
picks = report.get("picks", []) or []
left, right = st.columns([0.55, 0.45])

# Build a DataFrame for picks
def picks_df(picks):
    rows = []
    for p in picks:
        sym = p.get("symbol")
        ana = (artifacts.get("analysis") or {}).get(sym, {})
        sig = ana.get("signals", {}) if ana else {}
        rows.append({
            "symbol": sym,
            "recommendation": p.get("recommendation"),
            "confidence": p.get("confidence"),
            "momentum": sig.get("momentum"),
            "rsi": sig.get("rsi"),
            "trend": sig.get("trend"),
            "sentiment": sig.get("sentiment"),
            "overall": sig.get("overall"),
        })
    return pd.DataFrame(rows)

with left:
    st.subheader("Top Picks")
    if picks:
        dfp = picks_df(picks)
        st.dataframe(dfp, use_container_width=True, hide_index=True)
    else:
        st.info("No confident picks in this report.")

# Choose a symbol for charting (top pick default)
default_sym = picks[0]["symbol"] if picks else (artifacts.get("screen", {}).get("results", [{}])[0].get("symbol") if artifacts.get("screen") else None)
with right:
    st.subheader("Select symbol")
    all_syms = sorted(set([default_sym] + [r.get("symbol") for r in (artifacts.get("screen", {}).get("results", [])) if r.get("symbol")] if default_sym else
                          [r.get("symbol") for r in (artifacts.get("screen", {}).get("results", [])) if r.get("symbol")]))
    symbol = st.selectbox("Symbol", options=all_syms if all_syms else ["—"])
    if symbol == "—":
        st.stop()

# -----------------------------
# Optimizer context (if available)
# -----------------------------
opt_for_sym = (artifacts.get("optimizations") or {}).get(symbol)
best_fast = best_slow = None
if opt_for_sym and isinstance(opt_for_sym, dict):
    best = opt_for_sym.get("best", {})
    best_fast, best_slow = best.get("fast"), best.get("slow")

bt_for_sym = (artifacts.get("backtests") or {}).get(symbol, {})
bt_metrics = bt_for_sym.get("metrics", {}) if isinstance(bt_for_sym, dict) else {}

# -----------------------------
# Backtest / Equity chart
# -----------------------------
st.markdown("---")
st.subheader("Backtest")

col1, col2, col3, col4 = st.columns(4)
with col1:
    fast = st.number_input("Fast window", min_value=2, max_value=200, value=int(best_fast or 50), step=1)
with col2:
    slow = st.number_input("Slow window", min_value=5, max_value=400, value=int(best_slow or 200), step=1)
with col3:
    days_bt = st.number_input("Days", min_value=200, max_value=3000, value=int(default_days_bt), step=50)
with col4:
    run_bt = st.button("Run backtest")

# If optimizer inputs are visible, offer a one-click optimize
with st.expander("Optimize parameters", expanded=False):
    f_list = [int(x.strip()) for x in fvals.split(",") if x.strip().isdigit()]
    s_list = [int(x.strip()) for x in svals.split(",") if x.strip().isdigit()]
    do_opt = st.button("Run optimize on selected symbol")

equity_fig = None
bt_out = None

# Try to use existing backtest from artifacts if windows match; else call API
if run_bt:
    st.cache_data.clear()  # ensure fresh chart
    with st.spinner("Backtesting..."):
        try:
            bt_out = post_backtest(api_base, symbol, fast, slow, days_bt, include_series=True)
        except ApiError as e:
            st.error(f"Backtest failed: {e}")
else:
    # Autoload a backtest using best params (if present), else current fast/slow defaults
    try:
        bt_out = post_backtest(api_base, symbol, int(fast), int(slow), int(days_bt), include_series=True)
    except ApiError:
        bt_out = None

if bt_out and bt_out.get("equity") and bt_out.get("equity_index"):
    equity = bt_out["equity"]
    x = bt_out["equity_index"]
    equity_fig = go.Figure(data=[go.Scatter(x=x, y=equity, mode="lines", name="Equity")])
    equity_fig.update_layout(
        margin=dict(l=40, r=10, t=10, b=30),
        yaxis=dict(title="Equity (×)"),
        hovermode="x unified"
    )
    st.plotly_chart(equity_fig, use_container_width=True)
    # Show metrics if present
    metrics = bt_out.get("metrics") or {}
    if metrics:
        mcols = st.columns(4)
        mcols[0].metric("Sharpe", f"{metrics.get('Sharpe', 0):.2f}")
        mcols[1].metric("CAGR", f"{metrics.get('CAGR', 0)*100:.1f}%")
        mcols[2].metric("MaxDD", f"{metrics.get('MaxDrawdown', 0)*100:.1f}%")
        mcols[3].metric("WinRate", f"{metrics.get('WinRate', 0)*100:.1f}%")

if do_opt:
    with st.spinner("Optimizing..."):
        try:
            opt = post_optimize(api_base, symbol, int(days_bt), f_list, s_list, float(split), int(topk))
            st.success("Optimization complete.")
            st.json(opt)
            # If we have a winner, trigger a backtest with those params
            best = (opt or {}).get("best", {})
            if best.get("fast") and best.get("slow"):
                fast_opt, slow_opt = int(best["fast"]), int(best["slow"])
                bt_opt = post_backtest(api_base, symbol, fast_opt, slow_opt, int(days_bt), include_series=True)
                st.info(f"Backtest with optimized params: fast={fast_opt}, slow={slow_opt}")
                if bt_opt and bt_opt.get("equity"):
                    fig2 = go.Figure(data=[go.Scatter(x=bt_opt["equity_index"], y=bt_opt["equity"], mode="lines", name="Equity (opt)")])
                    fig2.update_layout(margin=dict(l=40, r=10, t=10, b=30), yaxis=dict(title="Equity (×)"), hovermode="x unified")
                    st.plotly_chart(fig2, use_container_width=True)
        except ApiError as e:
            st.error(f"Optimize failed: {e}")

# -----------------------------
# Screen Leaderboard
# -----------------------------
st.markdown("---")
st.subheader("Screen Leaderboard (Top 10)")

screen_rows = (artifacts.get("screen") or {}).get("results", [])[:10]
def screen_df(rows):
    data = []
    for r in rows:
        sig = r.get("signals", {}) or {}
        data.append({
            "symbol": r.get("symbol"),
            "recommendation": r.get("recommendation"),
            "confidence": r.get("confidence"),
            "momentum": sig.get("momentum"),
            "rsi": sig.get("rsi"),
            "trend": sig.get("trend"),
            "sentiment": sig.get("sentiment"),
            "overall": sig.get("overall"),
        })
    return pd.DataFrame(data)

if screen_rows:
    st.dataframe(screen_df(screen_rows), use_container_width=True, hide_index=True)
    # Allow CSV export directly from the report content
    csv_btn = st.download_button(
        "Download screen (CSV)",
        data=screen_df(screen_rows).to_csv(index=False).encode("utf-8"),
        file_name=f"screen_{(report.get('date','')[:10] or 'latest')}.csv",
        mime="text/csv",
        use_container_width=False,
    )
else:
    st.info("No screen results available in this report.")