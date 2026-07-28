"""本地四环境门禁矩阵的分阶段计时与预算加载。"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BUDGETS_PATH = ROOT / "quwoquan_ops" / "environments" / "pr_gate_timing_budgets.json"
MATRIX_GATE_ID = "01.local_env_matrix"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PhaseTimer:
    name: str
    started_monotonic: float = field(default_factory=time.monotonic)
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str = "running"
    details: list[str] = field(default_factory=list)
    report_dir: str = ""

    def finish(self, *, status: str, details: list[str] | None = None, report_dir: str = "") -> dict[str, Any]:
        self.ended_at = utc_now()
        self.duration_ms = int((time.monotonic() - self.started_monotonic) * 1000)
        self.status = status
        if details:
            self.details = list(details)
        if report_dir:
            self.report_dir = report_dir
        return self.as_dict()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "durationMs": self.duration_ms,
            "status": self.status,
            "details": self.details,
            "reportDir": self.report_dir,
        }


def load_local_env_matrix_budgets() -> dict[str, Any]:
    payload = json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))
    gate = (payload.get("gates") or {}).get(MATRIX_GATE_ID) or {}
    soft = int(gate.get("budgetSeconds") or 600)
    hard = int(gate.get("hardFailSeconds") or 1800)
    return {
        "gateId": MATRIX_GATE_ID,
        "softBudgetSeconds": soft,
        "hardBudgetSeconds": hard,
        "phaseBudgetsSeconds": dict(gate.get("phaseBudgetsSeconds") or {}),
        "criticalPath": str(gate.get("criticalPath") or ""),
        "cacheModeNotes": str(gate.get("cacheModeNotes") or ""),
    }


def write_timing_bundle(
    output_dir: Path,
    *,
    phases: list[dict[str, Any]],
    wall_clock_seconds: float,
    budgets: dict[str, Any],
    claim: str,
    cache_mode: str,
    extras: dict[str, Any] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    soft = int(budgets["softBudgetSeconds"])
    hard = int(budgets["hardBudgetSeconds"])
    payload = {
        "schema": "local-env-gate-timing",
        "generatedAt": utc_now(),
        "gateId": budgets["gateId"],
        "cacheMode": cache_mode,
        "claim": claim,
        "wallClockSeconds": round(wall_clock_seconds, 3),
        "softBudgetSeconds": soft,
        "hardBudgetSeconds": hard,
        "overSoftBudget": wall_clock_seconds > soft,
        "overHardBudget": wall_clock_seconds > hard,
        "phases": phases,
        **(extras or {}),
    }
    path = output_dir / "timing.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
