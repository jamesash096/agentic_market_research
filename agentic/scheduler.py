from __future__ import annotations
from typing import List
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import time
from zoneinfo import ZoneInfo
from .config import Config
from .agent_loop import run_once

def scheduled_run(universe: List[str], days: int = 365):
    print("Starting scheduled agent run...")
    report = run_once(universe=universe, days=days, config=Config())
    print("Run complete. Picks:", report.get("picks"))

def start_daily(universe: List[str], days: int = 365, hour: int = 17, minute: int = 30, tz: str = "America/Chicago"):
    sched = BlockingScheduler(timezone=ZoneInfo(tz))
    sched.add_job(lambda: scheduled_run(universe, days), "cron", hour=hour, minute=minute)
    print(f"Scheduler running — daily at {hour:02d}:{minute:02d} {tz}. Ctrl+C to stop.")
    sched.start()