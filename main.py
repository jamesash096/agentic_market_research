from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from pathlib import Path
import numpy as np
import json, csv, io
from agent import MarketAgent
from data import get_price_history
from backtest import backtest_sma_cross, optimize_sma_grid

app = FastAPI(title='Autonomous Market Research Agent', version="0.1.0")
agent = MarketAgent()

REPORTS_DIR = Path("reports")

class AnalyzeResponse(BaseModel):
    symbol: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    sentiment_compound: float
    signals: dict
    rationale: str

@app.get("/")
def root():
    return {"status": "ok", "message": "See /docs for API docs."}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/analyze/{symbol}", response_model=AnalyzeResponse)
def analyze(symbol: str, days: int = Query(365, ge=60, le=2000)):
    try:
        result = agent.analyze(symbol.upper(), days = days)
        return AnalyzeResponse(
            symbol=result.symbol,
            recommendation=result.recommendation,
            confidence=result.confidence,
            sentiment_compound=result.sentiment_compound,
            signals=result.signals,
            rationale=result.rationale,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
# ----- Screen -----
class ScreenRequest(BaseModel):
    symbols: List[str]
    days: int = 365

class ScreenError(BaseModel):
    symbol: str
    error: str

class ScreenItem(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    signals: Dict[str, float]

class ScreenResponse(BaseModel):
    results: List[ScreenItem]
    errors: Optional[List[ScreenError]] = None

@app.post("/screen", response_model=ScreenResponse)
def screen(req: ScreenRequest):
    out = agent.screen([s.upper() for s in req.symbols], days=req.days)
    return ScreenResponse(
        results=[ScreenItem(**r) for r in out["results"]],
        errors=[ScreenError(**e) for e in out.get("errors", [])] or None   
    )

# ----- Backtest -----
class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = Field("sma_cross", description="Currently only 'sma_cross'")
    params: Dict[str, int] = Field(default_factory=lambda: {"fast": 50, "slow": 200})
    days: int = 1000
    include_series: bool = False

class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    params: Dict[str, int]
    metrics: Dict[str, float]
    equity: Optional[List[float]] = None
    equity_index: Optional[List[str]] = None

@app.post("/backtest", response_model=BacktestResponse)
def backtest(req: BacktestRequest):
    if req.strategy != "sma_cross":
        raise HTTPException(status_code=400, detail="Only 'sma_cross' is supported.")
    try:
        fast = int(req.params.get("fast", 50))
        slow = int(req.params.get("slow", 200))
        if fast >= slow:
            raise HTTPException(status_code=400, detail="For SMA cross, fast must be < slow.")
        df = get_price_history(req.symbol.upper(), days=req.days)
        prices = df["close"] if "close" in df.columns else df.select_dtypes("number").iloc[:, 0]
        res = backtest_sma_cross(prices, fast=fast, slow=slow)

        payload = BacktestResponse(
            symbol=req.symbol.upper(),
            strategy=req.strategy,
            params={"fast": fast, "slow": slow},
            metrics=res.metrics,
        )

        if req.include_series:
            eq = res.equity
            # downsample to <= 300 points for lightweight charts
            if len(eq) > 300:
                idx = np.linspace(0, len(eq) - 1, 300).astype(int)
                eq = eq.iloc[idx]

            payload.equity = [float(x) for x in eq.values]
            # stringify index (supports Timestamp or plain indices)
            payload.equity_index = [
                str(getattr(i, "date", lambda: i)()) if hasattr(i, "date") else str(i)
                for i in eq.index
            ]

        return payload
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Backtest failed.")
    
class OptimizeBacktestRequest(BaseModel):
    symbol: str
    days: int = 1000
    fast_values: List[int] = Field(default_factory=lambda: [10, 20, 50])
    slow_values: List[int] = Field(default_factory=lambda: [100, 150, 200, 250])
    split: float = Field(0.7, ge=0.5, le=0.9)
    top_k: int = Field(5, ge=1, le=20)

class OptimizeBacktestResponse(BaseModel):
    symbol: str
    split: float
    bars_total: int
    bars_is: int
    bars_os: int
    best: Dict[str, Any]
    leaderboard: List[Dict[str, Any]]

@app.post("/optimize_backtest", response_model=OptimizeBacktestResponse)
def optimize_backtest(req: OptimizeBacktestRequest):
    try:
        df = get_price_history(req.symbol.upper(), days=req.days)
        prices = df["close"] if "close" in df.columns else df.select_dtypes("number").iloc[:, 0]
        out = optimize_sma_grid(
            prices=prices,
            fast_values=req.fast_values,
            slow_values=req.slow_values,
            split=req.split,
            top_k=req.top_k,
        )
        return OptimizeBacktestResponse(
            symbol=req.symbol.upper(),
            split=out["split"],
            bars_total=out["bars_total"],
            bars_is=out["bars_is"],
            bars_os=out["bars_os"],
            best=out["best"],
            leaderboard=out["leaderboard"],
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Optimization failed.")

@app.get("/reports/dates", response_model=List[str])
def list_report_dates():
    if not REPORTS_DIR.exists():
        return []
    return sorted([p.name for p in REPORTS_DIR.iterdir() if p.is_dir()])

@app.get("/report/latest")
def get_report_latest():
    if not REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="No reports directory")
    dates = sorted([p for p in REPORTS_DIR.iterdir() if p.is_dir()], reverse=True)
    if not dates:
        raise HTTPException(status_code=404, detail="No reports yet")
    run_path = dates[0] / "run.json"
    if not run_path.exists():
        raise HTTPException(status_code=404, detail="Latest date has no run.json")
    return json.loads(run_path.read_text(encoding="utf-8"))

@app.get("/report/{date}")
def get_report_by_date(date: str):
    run_path = REPORTS_DIR / date / "run.json"
    if not run_path.exists():
        raise HTTPException(status_code=404, detail=f"No report for {date}")
    return json.loads(run_path.read_text(encoding="utf-8"))

@app.get("/download/{date}/screen.csv")
def download_screen_csv(date: str):
    run_path = REPORTS_DIR / date / "run.json"
    if not run_path.exists():
        raise HTTPException(status_code=404, detail=f"No report for {date}")
    report = json.loads(run_path.read_text(encoding="utf-8"))
    rows = (report.get("artifacts") or {}).get("screen", {}).get("results", [])
    if not rows:
        raise HTTPException(status_code=404, detail="No screen results to export")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "symbol","recommendation","confidence","momentum","rsi","trend","sentiment","overall"
    ])
    writer.writeheader()
    for r in rows:
        sig = (r.get("signals") or {})
        writer.writerow({
            "symbol": r.get("symbol"),
            "recommendation": r.get("recommendation"),
            "confidence": r.get("confidence"),
            "momentum": sig.get("momentum"),
            "rsi": sig.get("rsi"),
            "trend": sig.get("trend"),
            "sentiment": sig.get("sentiment"),
            "overall": sig.get("overall"),
        })
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="screen_{date}.csv"'}
    )
