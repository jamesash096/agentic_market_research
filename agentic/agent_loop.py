# agentic/agent_loop.py
from __future__ import annotations
import os, json, datetime as dt
from typing import Dict, Any, List
from loguru import logger

from .config import Config
from .ollama_client import OllamaClient
from .planner import Planner
from .tools import Tools, ToolError
from .memory import Memory
from .logging import setup_logging_for_run

MIN_CONF = 0.60  # filter low-confidence picks in report

ALLOWED_TOOLS = {"screen", "analyze", "optimize_backtest", "backtest"}
MAX_PLAN_STEPS = 6

def _validate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce tool whitelist, cap steps, sanitize args, and dedupe identical steps.
    Logs what it drops/changes. Returns a cleaned plan.
    """
    steps = list(plan.get("steps") or [])
    clean: List[Dict[str, Any]] = []
    seen = set()

    for s in steps[:MAX_PLAN_STEPS]:
        t = (s.get("tool") or "").strip()
        if t not in ALLOWED_TOOLS:
            logger.warning("Dropping disallowed tool: {}", t)
            continue

        args = dict(s.get("args") or {})
        # --- sanitize per tool ---
        if t == "screen":
            symbols = [str(x).upper() for x in (args.get("symbols") or [])][:50]
            days = int(args.get("days", 365))
            days = max(60, min(days, 2000))
            args = {"symbols": symbols, "days": days}

        elif t == "analyze":
            sym = str(args.get("symbol", "")).upper()
            days = int(args.get("days", 365))
            days = max(60, min(days, 2000))
            if not sym:
                logger.warning("Dropping analyze with empty symbol")
                continue
            args = {"symbol": sym, "days": days}

        elif t == "optimize_backtest":
            sym = str(args.get("symbol", "")).upper()
            days = int(args.get("days", 1200))
            days = max(200, min(days, 3000))
            fast_values = [int(v) for v in (args.get("fast_values") or [10, 20, 50]) if 2 <= int(v) <= 200]
            slow_values = [int(v) for v in (args.get("slow_values") or [100, 150, 200, 250]) if 5 <= int(v) <= 400]
            fast_values = sorted(set(fast_values))[:8]
            slow_values = sorted(set(slow_values))[:8]
            split = float(args.get("split", 0.7))
            split = round(max(0.5, min(split, 0.9)), 2)
            top_k = int(args.get("top_k", 5))
            top_k = max(1, min(top_k, 10))
            if not sym:
                logger.warning("Dropping optimize_backtest with empty symbol")
                continue
            args = {
                "symbol": sym,
                "days": days,
                "fast_values": fast_values,
                "slow_values": slow_values,
                "split": split,
                "top_k": top_k,
            }

        elif t == "backtest":
            sym = str(args.get("symbol", "")).upper()
            fast = int(args.get("fast", 50))
            slow = int(args.get("slow", 200))
            days = int(args.get("days", 1200))
            if not sym or fast >= slow:
                logger.warning("Dropping backtest with invalid params: {}", args)
                continue
            days = max(200, min(days, 3000))
            fast = max(2, min(fast, 200))
            slow = max(5, min(slow, 400))
            args = {"symbol": sym, "fast": fast, "slow": slow, "days": days}

        key = (t, json.dumps(args, sort_keys=True))
        if key in seen:
            logger.info("Deduping repeated step: {}", key)
            continue
        seen.add(key)
        clean.append({"tool": t, "args": args})

    plan["steps"] = clean
    return plan

def pick_top_candidates(screen_result: Dict[str, Any], limit: int = 3) -> List[str]:
    items = (screen_result or {}).get("results", [])
    items = sorted(items, key=lambda x: x.get("confidence", 0.0), reverse=True)
    return [x["symbol"] for x in items[:limit]]

def run_once(universe: List[str], days: int = 365, config: Config = Config()) -> Dict[str, Any]:
    tools = Tools(api_base=config.api_base)
    memory = Memory(base_dir="reports")
    dpath = memory.path_for_date()

    # Loguru sinks per run
    setup_logging_for_run(dpath)
    logger.info("Run started | universe={} | days={}", universe, days)

    # Planner
    ollama = OllamaClient(base_url=config.ollama_base, model=config.ollama_model)
    planner = Planner(ollama=ollama, max_steps=config.max_steps)
    context = {
        "universe": universe,
        "days": days,
        "recent_runs": memory.recent(3),
        "confidence_threshold": config.confidence_threshold,
    }
    goal = "Identify promising BUY candidates from the universe and justify with signals and (optionally) a backtest."
    plan = planner.plan(goal, context)
    plan = _validate_plan(plan)
    logger.debug("Plan: {}", plan)

    executed: List[Dict[str, Any]] = []
    artifacts: Dict[str, Any] = {}

    # Execute planned steps
    for step in plan.get("steps", []):
        try:
            result = tools.exec_step(step)
            executed.append({"step": step, "result": result})
            t = step.get("tool")
            if t == "screen":
                artifacts["screen"] = result
            elif t == "analyze":
                sym = step["args"].get("symbol")
                artifacts.setdefault("analysis", {})[sym] = result
            elif t == "optimize_backtest":
                sym = step["args"].get("symbol")
                artifacts.setdefault("optimizations", {})[sym] = result
            elif t == "backtest":
                sym = step["args"].get("symbol")
                artifacts.setdefault("backtests", {})[sym] = result
            logger.success("Step ok | tool={}", t)
        except ToolError as e:
            executed.append({"step": step, "error": str(e)})
            logger.warning("Tool failed | step={} | error={}", step, str(e))

    # Auto-analyze top 3 if only screened
    if artifacts.get("screen"):
        top_syms = pick_top_candidates(artifacts["screen"], limit=3)
        for sym in top_syms:
            if sym not in (artifacts.get("analysis") or {}):
                try:
                    res = tools.analyze(symbol=sym, days=days)
                    executed.append({"step": {"tool": "analyze", "args": {"symbol": sym, "days": days}}, "result": res})
                    artifacts.setdefault("analysis", {})[sym] = res
                    logger.info("Auto-analyzed {}", sym)
                except ToolError as e:
                    executed.append({"step": {"tool": "analyze", "args": {"symbol": sym, "days": days}}, "error": str(e)})
                    logger.warning("Auto-analyze failed | {} | {}", sym, str(e))

    # Reflection: ensure we have at least one backtest
    if artifacts.get("analysis") and not artifacts.get("backtests"):
        if artifacts.get("optimizations"):
            # Convert existing optimizations to backtests (if planner ran them)
            for sym, opt in artifacts["optimizations"].items():
                try:
                    best = (opt or {}).get("best", {})
                    f, s = int(best.get("fast", 50)), int(best.get("slow", 200))
                    bt = tools.backtest(symbol=sym, fast=f, slow=s, days=max(1000, days))
                    executed.append({"step": {"tool": "backtest", "args": {"symbol": sym, "fast": f, "slow": s, "days": max(1000, days)}}, "result": bt})
                    artifacts.setdefault("backtests", {})[sym] = bt
                    logger.info("Backtested {} with optimized params {} / {}", sym, f, s)
                except Exception as e:
                    executed.append({"step": {"tool": "backtest", "args": {"symbol": sym}}, "error": str(e)})
                    logger.warning("Backtest from optimization failed | {} | {}", sym, str(e))
        else:
            # No optimization yet: reuse memory if possible; else optimize top-1 then backtest
            top1 = pick_top_candidates(artifacts.get("screen", {}), limit=1)
            for sym in top1:
                try:
                    reuse = memory.last_best_params(sym)
                    if reuse:
                        f, s = reuse
                        bt = tools.backtest(symbol=sym, fast=f, slow=s, days=max(1200, days))
                        executed.append({"step": {"tool": "backtest", "args": {"symbol": sym, "fast": f, "slow": s, "days": max(1200, days)}}, "result": bt})
                        artifacts.setdefault("backtests", {})[sym] = bt
                        logger.info("Reused best params from memory for {} -> {}/{}", sym, f, s)
                    else:
                        opt = tools.optimize_backtest(
                            symbol=sym, days=max(1200, days),
                            fast_values=[10, 20, 50],
                            slow_values=[100, 150, 200, 250],
                            split=0.7, top_k=5,
                        )
                        executed.append({"step": {"tool": "optimize_backtest", "args": {"symbol": sym}}, "result": opt})
                        artifacts.setdefault("optimizations", {})[sym] = opt
                        best = (opt or {}).get("best", {})
                        f, s = int(best.get("fast", 50)), int(best.get("slow", 200))
                        bt = tools.backtest(symbol=sym, fast=f, slow=s, days=max(1200, days))
                        executed.append({"step": {"tool": "backtest", "args": {"symbol": sym, "fast": f, "slow": s, "days": max(1200, days)}}, "result": bt})
                        artifacts.setdefault("backtests", {})[sym] = bt
                        logger.info("Optimized+backtested {} -> {}/{}", sym, f, s)
                except Exception as e:
                    executed.append({"step": {"tool": "reflect"}, "error": str(e)})
                    logger.warning("Reflection failed | {} | {}", sym, str(e))

    # If still nothing, backtest screen top-1 with defaults
    if not artifacts.get("backtests") and artifacts.get("screen"):
        top = pick_top_candidates(artifacts["screen"], limit=1)
        if top:
            try:
                bt = tools.backtest(symbol=top[0], fast=50, slow=200, days=max(1000, days))
                executed.append({"step": {"tool": "backtest", "args": {"symbol": top[0], "fast": 50, "slow": 200, "days": max(1000, days)}}, "result": bt})
                artifacts.setdefault("backtests", {})[top[0]] = bt
                logger.info("Fallback backtest {} with defaults 50/200", top[0])
            except Exception as e:
                executed.append({"step": {"tool": "backtest", "args": {"symbol": top[0]}}, "error": str(e)})
                logger.warning("Fallback backtest failed | {} | {}", top[0], str(e))

    # ---- Build picks (prefer analysis; fallback to screen values) ----
    def _from_screen(screen: dict, sym: str):
        for row in (screen or {}).get("results", []):
            if row.get("symbol") == sym:
                return row.get("recommendation"), row.get("confidence")
        return None, None

    picks: List[Dict[str, Any]] = []
    chosen_syms = list((artifacts.get("analysis") or {}).keys()) or pick_top_candidates(artifacts.get("screen", {}), limit=3)
    for sym in chosen_syms:
        ana = (artifacts.get("analysis") or {}).get(sym)
        if ana:
            rec = ana.get("recommendation")
            conf = ana.get("confidence")
        else:
            rec, conf = _from_screen(artifacts.get("screen", {}), sym)
        picks.append({"symbol": sym, "recommendation": rec, "confidence": conf})

    # Confidence filter (report cleanliness)
    picks = [p for p in picks if (p.get("confidence") or 0) >= MIN_CONF]

    # ---- Persist JSON report ----
    report = {
        "date": dt.datetime.now().isoformat(),
        "universe": universe,
        "plan": plan,
        "steps_executed": executed,
        "picks": picks,
        "artifacts": artifacts,
        "disclaimer": "Educational demo only — not financial advice.",
    }
    with open(os.path.join(dpath, "run.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.success("Wrote {}", os.path.join(dpath, "run.json"))

    # ---- Build Markdown report ----
    def _pct(x):
        try: return f"{float(x)*100:.1f}%"
        except: return "—"
    def _num(x, nd=2):
        try: return f"{float(x):.{nd}f}"
        except: return "—"

    screen_rows = (artifacts.get("screen") or {}).get("results", [])[:10]
    analyses = artifacts.get("analysis") or {}
    optis = artifacts.get("optimizations") or {}
    btests = artifacts.get("backtests") or {}

    today = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [
        "# Daily Market Research (Autonomous Agent)",
        f"**Date:** {today}",
        "",
        f"Universe size: **{len(universe)}**",
        "",
        "## Top Picks",
    ]
    if picks:
        for p in picks:
            sym = p["symbol"]
            rec = p.get("recommendation", "—")
            conf = p.get("confidence", None)
            conf_s = _num(conf) if conf is not None else "—"
            lines.append(f"- **{sym}** — {rec} (confidence: {conf_s})")
            sigs = (analyses.get(sym) or {}).get("signals") or {}
            if sigs:
                lines.append(
                    f"  - Signals: momentum {_num(sigs.get('momentum'))}, rsi {_num(sigs.get('rsi'))}, "
                    f"trend {_num(sigs.get('trend'))}, sentiment {_num(sigs.get('sentiment'))}, overall {_num(sigs.get('overall'))}"
                )
            # Optimizer outcome
            opt = optis.get(sym)
            if opt:
                best = opt.get("best", {})
                f = best.get("fast"); s = best.get("slow")
                os_metrics = (best.get("OS") or {})
                lines.append(
                    f"  - Optimized params: fast={f}, slow={s} "
                    f"(OS Sharpe {_num(os_metrics.get('Sharpe'))}, "
                    f"OS CAGR {_pct(os_metrics.get('CAGR'))}, "
                    f"OS MaxDD {_pct(os_metrics.get('MaxDrawdown'))})"
                )
            # Backtest metrics
            bt = btests.get(sym)
            if bt:
                m = bt.get("metrics", {})
                lines.append(
                    f"  - Backtest: Sharpe {_num(m.get('Sharpe'))}, "
                    f"CAGR {_pct(m.get('CAGR'))}, MaxDD {_pct(m.get('MaxDrawdown'))}, "
                    f"WinRate {_pct(m.get('WinRate'))}"
                )
    else:
        lines.append("- No confident candidates today.")

    if screen_rows:
        lines += ["", "## Screen Leaderboard (Top 10)"]
        lines.append("| Symbol | Rec | Confidence | Momentum | Trend | Sentiment | Overall |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for r in screen_rows:
            lines.append(
                f"| {r.get('symbol','—')} | {r.get('recommendation','—')} | {_num(r.get('confidence'))} | "
                f"{_num((r.get('signals') or {}).get('momentum'))} | {_num((r.get('signals') or {}).get('trend'))} | "
                f"{_num((r.get('signals') or {}).get('sentiment'))} | {_num((r.get('signals') or {}).get('overall'))} |"
            )

    lines += ["", "## Notes", "This report was generated by an autonomous planner calling FastAPI tools.", "_Educational demo only — not financial advice._"]
    with open(os.path.join(dpath, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.success("Wrote {}", os.path.join(dpath, "report.md"))

    # ---- Update memory (keep best params if we have them) ----
    best_sym = picks[0]["symbol"] if picks else None
    best_params = None
    if best_sym and best_sym in optis:
        b = optis[best_sym].get("best", {})
        best_params = {"fast": b.get("fast"), "slow": b.get("slow")}
    memory.append({
        "date": report["date"],
        "universe_size": len(universe),
        "top_pick": best_sym,
        "top_conf": picks[0]["confidence"] if picks else None,
        "best_params": best_params,
    })
    logger.info("Memory updated | top_pick={} | best_params={}", best_sym, best_params)

    return report
