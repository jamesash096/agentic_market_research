from __future__ import annotations
import requests
from typing import Dict, Any, List

class ToolError(Exception):
    pass

class Tools:
    def __init__(self, api_base: str = "http://127.0.0.1:8000"):
        self.api_base = api_base.rstrip("/")

    def analyze(self, symbol: str, days: int = 365) -> Dict[str, Any]:
        url = f"{self.api_base}/analyze/{symbol}"
        r = requests.get(url, params={"days": days}, timeout=60)
        if not r.ok:
            raise ToolError(f"analyze failed: {r.status_code} {r.text}")
        return r.json()

    def screen(self, symbols: List[str], days: int = 365) -> Dict[str, Any]:
        url = f"{self.api_base}/screen"
        r = requests.post(url, json={"symbols": symbols, "days": days}, timeout=180)
        if not r.ok:
            raise ToolError(f"screen failed: {r.status_code} {r.text}")
        return r.json()

    def backtest(self, symbol: str, fast: int, slow: int, days: int = 1000) -> Dict[str, Any]:
        url = f"{self.api_base}/backtest"
        payload = {"symbol": symbol, "strategy": "sma_cross", "params": {"fast": fast, "slow": slow}, "days": days}
        r = requests.post(url, json=payload, timeout=180)
        if not r.ok:
            raise ToolError(f"backtest failed: {r.status_code} {r.text}")
        return r.json()

    def optimize_backtest(self, symbol: str, days: int, fast_values, slow_values, split: float = 0.7, top_k: int = 5) -> Dict[str, Any]:
        url = f"{self.api_base}/optimize_backtest"
        payload = {"symbol": symbol, "days": days, "fast_values": fast_values, "slow_values": slow_values, "split": split, "top_k": top_k}
        r = requests.post(url, json=payload, timeout=240)
        if not r.ok:
            raise ToolError(f"optimize_backtest failed: {r.status_code} {r.text}")
        return r.json()

    def exec_step(self, step: dict) -> Dict[str, Any]:
        tool = step.get("tool")
        args = step.get("args", {})
        if tool == "analyze":
            return self.analyze(**args)
        elif tool == "screen":
            return self.screen(**args)
        elif tool == "backtest":
            return self.backtest(**args)
        elif tool == "optimize_backtest":
            return self.optimize_backtest(**args)
        else:
            raise ToolError(f"Unknown tool: {tool}")