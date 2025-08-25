from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)

@dataclass
class Config:
    # FastAPI service (your tools)
    api_base: str = os.getenv("API_BASE")

    # Ollama (local LLM planner)
    ollama_base: str = os.getenv("OLLAMA_BASE")
    ollama_model: str = os.getenv("OLLAMA_MODEL")

    # Planning / autonomy
    max_steps: int = os.getenv("MAX_STEPS")
    confidence_threshold: float = os.getenv("CONFIDENCE_THRESHOLD")

    # Defaults
    default_days: int = os.getenv("DEFAULT_DAYS")