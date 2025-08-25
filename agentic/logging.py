# agentic/logging_setup.py
from __future__ import annotations
import os, sys, logging
from loguru import logger

def _intercept_std_logging():
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            logger.bind(name=record.name).opt(
                depth=6, exception=record.exc_info
            ).log(level, record.getMessage())
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "requests"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False

def setup_logging_for_run(dpath: str):
    os.makedirs(dpath, exist_ok=True)
    log_path = os.path.join(dpath, "run.log")
    logger.remove()  # reset sinks per run

    # Console
    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <7}</level> | {message}",
    )

    # File (rotated)
    logger.add(
        log_path,
        level="DEBUG",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        rotation="5 MB",
        retention="14 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {message}",
    )

    _intercept_std_logging()
    return logger