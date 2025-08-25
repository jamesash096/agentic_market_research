# Agentic Market Research Agent

**LLM-planned FastAPI + Streamlit app for equity screening, sentiment-aware analysis, and walk-forward backtesting.**
Planner–executor architecture (Ollama) calls tool endpoints to build daily reports and charts.

> **Educational demo only — not financial advice.**

---

## ✨ Features

* **Agentic AI**: LLM planner (Ollama) → JSON plan → executor runs `/screen`, `/analyze`, `/optimize_backtest`, `/backtest`
* **Signals**: momentum, RSI, trend + **news sentiment (NLTK VADER)**
* **Backtesting**: SMA crossover, grid search optimization, **IS/OS (walk-forward)**
* **Autonomy**: guardrails, reflection fallback, and **memory reuse** of best params
* **UI**: Streamlit dashboard (picks, leaderboard, equity curve)
* **API**: FastAPI microservice + CSV export + dated report retrieval
* **Logging**: Loguru per-run logs; artifacts saved as `run.json` and `report.md`

---

## 🧭 Architecture

```
[Streamlit UI]  ── calls ──>  [FastAPI Tools]
                               ├─ /screen  /analyze
                               ├─ /optimize_backtest  /backtest
                               └─ /report/* exports
    ▲                                 ▲
    │                                 │
    └──────── [Agentic Planner–Executor (Ollama)] ── writes ──> /reports/YYYY-MM-DD/{run.json, report.md, run.log}
                                   │
                                   └─ Guardrails + Reflection + Memory reuse
```

---

## 🗂️ Project layout (key files)

```
autonomous_research_agent/
├─ main.py                    # FastAPI app (endpoints are here for now)
├─ data.py                    # yfinance + headlines + price cache
├─ backtest.py                # SMA cross + optimizer
├─ streamlit_app.py           # Streamlit dashboard
├─ requirements.txt
├─ schemas.py                 # Pydantic models
├─ deps.py                    # API key dependency (optional)
└─ agentic/
   ├─ config.py               # loads .env (API_BASE, OLLAMA_*, etc.)
   ├─ prompts.py / planner.py # LLM planning (JSON only)
   ├─ tools.py                # clients for FastAPI endpoints
   ├─ agent_loop.py           # executor, guardrails, reflection, memory, report builder
   ├─ memory.py               # run history + best params lookup
   ├─ logging_setup.py        # Loguru sinks (console + run.log)
   └─ run_once.py             # quick entrypoint for one cycle
```

*Note: Modular FastAPI routers (e.g., `routers/backtest.py`, `routers/reports.py`) are **planned** for a future update; today all routes live in `main.py`.*
autonomous\_research\_agent/
├─ main.py                    # FastAPI app; endpoints live here for now
├─ data.py                    # yfinance + headlines + price cache
├─ backtest.py                # SMA cross + optimizer
├─ streamlit\_app.py           # Streamlit dashboard
├─ requirements.txt
├─ (routers/ — planned)       # Future: move endpoints from main.py into modular routers
├─ schemas.py                 # Pydantic models (optional)
├─ deps.py                    # API key dependency (optional)
└─ agentic/
├─ config.py               # loads .env (API\_BASE, OLLAMA\_\*, etc.)
├─ prompts.py / planner.py # LLM planning (JSON only)
├─ tools.py                # clients for FastAPI endpoints
├─ agent\_loop.py           # executor, guardrails, reflection, memory, report builder
├─ memory.py               # run history + best params lookup
├─ logging\_setup.py        # Loguru sinks (console + run.log)
└─ run\_once.py             # quick entrypoint for one cycle

````

---

## ⚙️ Setup

### 1) Create and activate a venv
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
````

### 2) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Create `.env` in repo root

> `.env` is auto-loaded by `agentic/config.py` and `streamlit_app.py` (via `python-dotenv`).

### 4) NLTK VADER lexicon (if needed)

If you see a `vader_lexicon not found` error:

```bash
python -c "import nltk; nltk.download('vader_lexicon')"
```

### 5) Ollama (LLM planner)

```bash
ollama serve
ollama pull llama3.1
```

---

## 🚀 Run

### A) Start the FastAPI service

```bash
uvicorn main:app --reload
# Health check: http://127.0.0.1:8000/health  -> {"status":"ok"}
```

### B) Start Streamlit

```bash
streamlit run streamlit_app.py
# UI at http://localhost:8501
```

### C) Run the autonomous loop once (writes a new report)

```bash
python -m agentic.run_once
# Output in reports/YYYY-MM-DD/{run.json, report.md, run.log}
```

### D) (Optional) Schedule daily runs

```python
# example: inside a Python shell
from agentic.scheduler import start_daily
from agentic.run_once import DEFAULT_UNIVERSE
start_daily(DEFAULT_UNIVERSE, tz='America/Chicago', hour=17, minute=30)
```

---

## 🧪 API (quick reference)

*Note: endpoints are currently implemented in `main.py`. Splitting into modular FastAPI routers is **planned**.*

*Note: For now, all endpoints are implemented in `main.py`. Modular FastAPI routers are planned and will move these routes into `routers/`.*

* `POST /backtest` → SMA cross backtest (optionally returns equity series for charts)

  ```json
  {
    "symbol": "AAPL",
    "strategy": "sma_cross",
    "params": {"fast": 50, "slow": 200},
    "days": 1000,
    "include_series": true
  }
  ```

* `POST /optimize_backtest` → grid search with IS/OS split

  ```json
  {
    "symbol":"NVDA",
    "days": 1200,
    "fast_values":[10,20,50],
    "slow_values":[100,150,200,250],
    "split":0.7,
    "top_k":5
  }
  ```

* `GET /reports/dates` → list of report folders

* `GET /report/latest` or `/report/{YYYY-MM-DD}` → full JSON report

* `GET /download/{date}/screen.csv` → CSV of screen leaderboard

* *(Optional)* `POST /agent/run_once` → trigger a full agent run via API

> If you set `AGENT_API_KEY`, include header `X-API-Key: <value>` in POST requests.

---

## 🖥️ Streamlit Dashboard

* **Top Picks** (BUY/HOLD/SELL + confidence + signals)
* **Equity Curve** (uses `include_series=true` backtests)
* **Optimize** (optional button to run `/optimize_backtest`)
* **Screen Leaderboard** (Top-10, CSV download)

Change the backend URL or API key in the sidebar; values are read from `.env` by default.

---

## 🛡️ Reliability & Safety

* **Guardrails**: tool whitelist, step cap, arg bounds, deduplication
* **Reflection**: if the plan omits optimization/backtest, the executor reuses prior best params or optimizes the top candidate
* **Memory**: persists top pick and best `(fast, slow)` across days
* **Logging**: `reports/YYYY-MM-DD/run.log` (Loguru), plus `run.json` and `report.md`

---

## 🗺️ Roadmap

* Modular **FastAPI routers** (move endpoints out of `main.py` into `routers/`)
* API key enforcement on write routes (if not already enabled)
* Additional strategies (EMA, breakout) and transaction fee modeling
* CI/CD and Dockerization (via WSL2 or cloud build)

---

## 🧰 Troubleshooting

* **`vader_lexicon not found`**
  Run: `python -c "import nltk; nltk.download('vader_lexicon')"`

* **Ollama connection refused**
  Ensure `ollama serve` is running and `OLLAMA_BASE` matches.

* **FastAPI connection refused**
  Start Uvicorn: `uvicorn main:app --reload`

* **Windows & Docker**
  Prefer WSL2 (Docker Engine inside Ubuntu) or use Rancher Desktop/Podman if you later containerize.

---

## 📄 License & Disclaimer
* This project is for **educational purposes only** and does **not** constitute financial advice.

---
