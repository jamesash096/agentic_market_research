from __future__ import annotations
from .agent_loop import run_once
from .config import Config

# Tweak as you like
DEFAULT_UNIVERSE = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","NFLX","AMD","AVGO","ADBE","COST","PEP","ORCL","LIN"]

if __name__ == "__main__":
    report = run_once(universe=DEFAULT_UNIVERSE, days=365, config=Config())
    print("Top picks:", report.get("picks"))
    print("Artifacts saved under ./reports/YYYY-MM-DD/")