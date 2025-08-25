from __future__ import annotations
import json
from typing import Dict, Any
from .prompts import SYSTEM_PROMPT

class Planner:
    def __init__(self, ollama, max_steps: int = 6):
        self.ollama = ollama
        self.max_steps = max_steps

    def plan(self, goal, context: Dict[str, Any]):
        ctx_lines = [f"- {k}: {v}" for k, v in context.items() if v is not None]
        user = f"Objective: {goal}\nContext:\n" + "\n".join(ctx_lines) + f"\nReturn JSON plan (max {self.max_steps} steps)."
        try:
            raw = self.ollama.generate(SYSTEM_PROMPT + "\n\n" + user)
            plan = json.loads(raw)
        except Exception:
            plan = {
                "objective": goal,
                "steps": [
                    {"tool": "screen", "args": {"symbols": context.get("universe", []), "days": context.get("days", 365)}}
                ],
            }
        if "steps" in plan and isinstance(plan["steps"], list):
            plan["steps"] = plan["steps"][:self.max_steps]
        return plan