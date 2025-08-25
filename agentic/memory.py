from __future__ import annotations
import json, os, datetime as dt
from typing import Dict, Any, List, Optional

class Memory:
    def __init__(self, base_dir: str = "reports"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.mem_file = os.path.join(self.base_dir, "memory.jsonl")

    def append(self, record: Dict[str, Any]) -> None:
        with open(self.mem_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, n: int = 5) -> List[Dict[str, Any]]:
        if not os.path.exists(self.mem_file):
            return []
        with open(self.mem_file, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        return [json.loads(x) for x in lines[-n:]]

    def path_for_date(self, date: Optional[dt.date] = None) -> str:
        if date is None:
            date = dt.date.today()
        d = os.path.join(self.base_dir, date.isoformat())
        os.makedirs(d, exist_ok=True)
        return d
    
    def last_best_params(self, symbol: str):
        for rec in reversed(self.recent(50)):
            if rec.get("top_pick") == symbol:
                bp = rec.get("best_params")
                if bp and bp.get("fast") and bp.get("slow"):
                    return int(bp["fast"]), int(bp["slow"])
        return None

    def write_run(self, dpath: str, name: str, obj: dict):
        with open(os.path.join(dpath, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)