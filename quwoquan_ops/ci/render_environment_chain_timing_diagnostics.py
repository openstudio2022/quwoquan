#!/usr/bin/env python3
"""汇总环境链路与主链耗时证据，输出超预算诊断报告。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_STACKCTL_PARTS = {"health", "inspect", "doctor", "rollback"}
CANONICAL_TIMING_SCHEMA = "ci-timing-summary"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-pipeline-root", default="")
    parser.add_argument("--delivery-gate-root", default="")
    parser.add_argument("--beta-summary-root", default="")
    parser.add_argument("--mainline-summary", required=True)
    parser.add_argument("--alpha-runs-root", default="")
    parser.add_argument("--beta-stackctl-root", default="")
    parser.add_argument("--gamma-stackctl-root", default="")
    parser.add_argument("--prod-rollout-stackctl-root", default="")
    parser.add_argument("--write-json", default="")
    parser.add_argument("--write-markdown", default="")
    parser.add_argument("--write-step-summary", action="store_true")
    parser.add_argument("--emit-annotations", action="store_true")
    return parser.parse_args()


def resolve_path(raw_path: str) -> Path | None:
    if not raw_path.strip():
        return None
    path = Path(raw_path.strip())
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"timing evidence must be an object: {path}")
    return payload


def require_timing_summary(summary: dict[str, Any], *, label: str) -> dict[str, Any]:
    if summary.get("schema") != CANONICAL_TIMING_SCHEMA:
        raise ValueError(f"{label} is not a canonical ci-timing-summary")
    critical_path = summary.get("criticalPath")
    budget = summary.get("budget")
    phases = summary.get("phases")
    if not isinstance(critical_path, dict) or not isinstance(budget, dict):
        raise ValueError(f"{label} is missing canonical criticalPath or budget")
    if not isinstance(phases, list):
        raise ValueError(f"{label} phases must be a list")
    if not isinstance(summary.get("missingEvidence"), list):
        raise ValueError(f"{label} missingEvidence must be a list")
    return summary


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def find_named_json(
    root: Path | None, filename: str
) -> tuple[dict[str, Any] | None, Path | None]:
    if root is None or not root.exists():
        return None, None
    if root.is_file():
        return (read_json(root), root) if root.name == filename else (None, None)
    matches = sorted(root.rglob(filename))
    if not matches:
        return None, None
    return read_json(matches[0]), matches[0]


def format_seconds(value: int | None) -> str:
    if value is None:
        return "missing"
    minutes, seconds = divmod(max(int(value), 0), 60)
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}m {seconds:02d}s"


def format_duration_ms(value: int) -> str:
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000.0:.2f}s"


def build_status(
    duration_seconds: int | None,
    soft_budget_seconds: int | None,
    *,
    hard_budget_seconds: int | None = None,
    slo_eligible: bool = True,
    evidence_status: str = "",
) -> dict[str, Any]:
    if not slo_eligible or duration_seconds is None or soft_budget_seconds is None:
        return {
            "durationSeconds": duration_seconds,
            "softBudgetSeconds": soft_budget_seconds,
            "hardBudgetSeconds": hard_budget_seconds,
            "status": evidence_status or "not_evaluated",
            "deltaFromSoftSeconds": None,
            "sloEligible": False,
        }
    delta = int(duration_seconds) - int(soft_budget_seconds)
    if hard_budget_seconds is not None and duration_seconds > hard_budget_seconds:
        status = "failed"
    elif delta > 0:
        status = "released_over_soft_budget"
    else:
        status = "within_budget"
    return {
        "durationSeconds": int(duration_seconds),
        "softBudgetSeconds": int(soft_budget_seconds),
        "hardBudgetSeconds": hard_budget_seconds,
        "status": status,
        "deltaFromSoftSeconds": delta,
        "sloEligible": True,
    }


def phase_index(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require_timing_summary(summary, label="timing summary")
    summary_eligible = summary.get("status") != "historical_incomplete"
    phases = summary.get("phases") or []
    items: dict[str, dict[str, Any]] = {}
    for phase in phases:
        if not isinstance(phase, dict):
            raise ValueError("timing summary phase must be an object")
        key = str(phase.get("name", "")).strip()
        if not key:
            raise ValueError("timing summary phase name is required")
        duration = phase.get("durationSeconds")
        budget = phase.get("budgetSeconds")
        items[key] = {
            "name": key,
            "durationSeconds": int(duration) if duration is not None else None,
            "budgetSeconds": int(budget) if budget is not None else None,
            "sloEligible": summary_eligible,
            "evidenceStatus": (
                str(summary.get("status") or "") if not summary_eligible else ""
            ),
        }
    return items


def missing_phase(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "durationSeconds": None,
        "budgetSeconds": None,
        "sloEligible": False,
        "evidenceStatus": "missing_evidence",
    }


def collect_stackctl_primary_summaries(
    root: Path | None, *, stage_label: str = ""
) -> list[dict[str, Any]]:
    if root is None or not root.exists():
        return []
    candidates = [root] if root.is_file() else sorted(root.rglob("summary.json"))
    items: list[dict[str, Any]] = []
    for path in candidates:
        if path.name != "summary.json":
            continue
        rel_parts = path.relative_to(root.parent if root.is_file() else root).parts
        if any(part in EXCLUDED_STACKCTL_PARTS for part in rel_parts[:-1]):
            continue
        try:
            payload = read_json(path)
        except json.JSONDecodeError:
            continue
        command = str(payload.get("command", "")).strip()
        duration_ms = int(payload.get("durationMs", 0) or 0)
        if not command or duration_ms <= 0:
            continue
        label = f"{stage_label}:{command}" if stage_label else command
        items.append(
            {
                "label": label,
                "command": command,
                "stageLabel": stage_label,
                "target": str(payload.get("target", "")).strip(),
                "status": str(payload.get("status", "")).strip(),
                "durationMs": duration_ms,
                "durationSeconds": int(round(duration_ms / 1000.0)),
                "summary": str(payload.get("summary", "")).strip(),
                "path": display_path(path),
            }
        )
    items.sort(key=lambda item: item["durationMs"], reverse=True)
    return items


def top_hotspots(
    items: list[dict[str, Any]], *, limit: int = 3
) -> list[dict[str, Any]]:
    return items[:limit]


def summary_item(
    summary: dict[str, Any], *, key: str, label: str, path: str = ""
) -> dict[str, Any]:
    require_timing_summary(summary, label=label)
    critical_path = summary.get("criticalPath") or {}
    budget = summary.get("budget") or {}
    status = str(summary.get("status") or "")
    eligible = status != "historical_incomplete"
    return {
        "key": key,
        "label": label,
        "path": path,
        **build_status(
            (
                int(critical_path["seconds"])
                if critical_path.get("seconds") is not None
                else None
            ),
            (
                int(budget["softSeconds"])
                if budget.get("softSeconds") is not None
                else None
            ),
            hard_budget_seconds=(
                int(budget["hardSeconds"])
                if budget.get("hardSeconds") is not None
                else None
            ),
            slo_eligible=eligible,
            evidence_status=status,
        ),
    }


def phase_item(
    item: dict[str, Any], *, key: str, label: str, path: str = ""
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "path": path,
        **build_status(
            item.get("durationSeconds"),
            item.get("budgetSeconds"),
            slo_eligible=bool(item.get("sloEligible", False)),
            evidence_status=str(item.get("evidenceStatus") or ""),
        ),
    }


def subphases(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    items: list[dict[str, Any]] = []
    for phase in summary.get("phases") or []:
        key = str(phase.get("name", "")).strip()
        if not key:
            continue
        items.append(
            {
                "name": key,
                "durationSeconds": (
                    int(phase["durationSeconds"])
                    if phase.get("durationSeconds") is not None
                    else None
                ),
                "budgetSeconds": (
                    int(phase["budgetSeconds"])
                    if phase.get("budgetSeconds") is not None
                    else None
                ),
            }
        )
    return items


def build_environment_entry(
    *,
    key: str,
    label: str,
    duration_seconds: int | None,
    soft_budget_seconds: int | None,
    slo_eligible: bool,
    evidence_status: str,
    phase_breakdown: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
    evidence_paths: list[str],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        **build_status(
            duration_seconds,
            soft_budget_seconds,
            slo_eligible=slo_eligible,
            evidence_status=evidence_status,
        ),
        "phaseBreakdown": phase_breakdown,
        "hotspots": hotspots,
        "evidencePaths": [item for item in evidence_paths if item],
        "notes": [item for item in notes if item],
    }


def recommendation_lines(
    over_budget_keys: set[str], missing_evidence: list[str]
) -> list[str]:
    recommendations: list[str] = []
    mapping = {
        "service_pipeline_02": (
            "优先检查 02 中最长的镜像构建 phase，继续压缩 build cache miss "
            "与 release snapshot fanout。"
        ),
        "delivery_gate": (
            "优先检查 03 Delivery Gate 的最长 fanout（service/app/portal），"
            "避免主链被非关键扫描拖慢。"
        ),
        "alpha_stage": (
            "优先检查 alpha-local 的 package/up/inspect 链路，"
            "能复用的本地产物尽量复用。"
        ),
        "beta_device_matrix": (
            "优先检查 beta bootstrap 与 mobile matrix fanout，"
            "坏环境要尽早 fail-fast，避免继续空转。"
        ),
        "gamma_local": (
            "优先检查 gamma-local 的预热数据面与增量启动，避免冷启动进入主链。"
        ),
        "prod_rollout_transaction": (
            "优先检查单一 Prod 事务的部署、SLO readback 与回滚探针。"
        ),
        "mainline_auto_prod": (
            "mainline-to-prod 已超过 10 分钟软门，先处理首个超预算阶段"
            "并保留 30 分钟硬门回滚余量。"
        ),
    }
    for key in sorted(over_budget_keys):
        line = mapping.get(key)
        if line and line not in recommendations:
            recommendations.append(line)
    if missing_evidence:
        recommendations.append(
            "存在耗时证据缺口，需补齐对应受控 summary.json 或运行面证据，"
            "否则无法稳定定位慢点与 flaky 来源。"
        )
    return recommendations


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Environment Chain Timing Diagnostics",
        "",
        "- chain:",
    ]
    for item in report["chain"]:
        lines.append(
            "  - `{0}`: `{1} / {2}` `{3}`".format(
                item["label"],
                format_seconds(item["durationSeconds"]),
                format_seconds(item["softBudgetSeconds"]),
                item["status"],
            )
        )
    over_budget = report.get("overBudgetItems") or []
    if over_budget:
        lines.append("- over-budget:")
        for item in over_budget:
            lines.append(
                "  - `{0}`: `{1}` over `{2}` (`+{3}`)".format(
                    item["label"],
                    format_seconds(item["durationSeconds"]),
                    format_seconds(item["softBudgetSeconds"]),
                    format_seconds(abs(int(item["deltaFromSoftSeconds"]))),
                )
            )
    else:
        lines.append("- over-budget: none")
    missing = report.get("missingEvidence") or []
    if missing:
        lines.append("- missing evidence:")
        for item in missing:
            lines.append(f"  - {item}")
    else:
        lines.append("- missing evidence: none")
    lines.append("- environments:")
    for environment in report["environments"]:
        lines.append(
            "  - `{0}`: `{1} / {2}` `{3}`".format(
                environment["label"],
                format_seconds(environment["durationSeconds"]),
                format_seconds(environment["softBudgetSeconds"]),
                environment["status"],
            )
        )
        for phase in environment.get("phaseBreakdown") or []:
            budget = phase.get("budgetSeconds")
            suffix = f" / {format_seconds(budget)}" if budget is not None else ""
            lines.append(
                "    - phase `{0}`: `{1}{2}`".format(
                    phase["name"],
                    format_seconds(phase.get("durationSeconds")),
                    suffix,
                )
            )
        for hotspot in environment.get("hotspots") or []:
            lines.append(
                "    - hotspot `{0}`: `{1}` `{2}`".format(
                    hotspot["label"],
                    format_duration_ms(int(hotspot["durationMs"])),
                    hotspot.get("status", ""),
                ).rstrip()
            )
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("- recommendations:")
        for item in recommendations:
            lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def write_outputs(
    *,
    payload: dict[str, Any],
    markdown: str,
    json_path: str,
    markdown_path: str,
    write_step_summary: bool,
) -> None:
    if json_path.strip():
        json_file = resolve_path(json_path)
        assert json_file is not None
        json_file.parent.mkdir(parents=True, exist_ok=True)
        json_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if markdown_path.strip():
        markdown_file = resolve_path(markdown_path)
        assert markdown_file is not None
        markdown_file.parent.mkdir(parents=True, exist_ok=True)
        markdown_file.write_text(markdown, encoding="utf-8")
    if write_step_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(markdown + "\n")


def emit_annotations(report: dict[str, Any]) -> None:
    for item in report.get("overBudgetItems") or []:
        print(
            "::error::[timing-diagnostic/{0}] {1}={2} exceeds budget {3}".format(
                item["key"],
                item["label"],
                format_seconds(item["durationSeconds"]),
                format_seconds(item["softBudgetSeconds"]),
            )
        )
    for message in report.get("missingEvidence") or []:
        print(f"::warning::[timing-diagnostic/missing-evidence] {message}")


def main() -> int:
    args = parse_args()

    mainline_summary_path = resolve_path(args.mainline_summary)
    assert mainline_summary_path is not None
    mainline_summary = require_timing_summary(
        read_json(mainline_summary_path),
        label="mainline timing summary",
    )

    service_summary, service_summary_path = find_named_json(
        resolve_path(args.service_pipeline_root),
        "service-pipeline-summary.json",
    )
    delivery_summary, delivery_summary_path = find_named_json(
        resolve_path(args.delivery_gate_root),
        "delivery-gate-summary.json",
    )
    beta_summary, beta_summary_path = find_named_json(
        resolve_path(args.beta_summary_root),
        "app-env-device-matrix-summary.json",
    )
    for label, summary in (
        ("service pipeline timing summary", service_summary),
        ("delivery gate timing summary", delivery_summary),
        ("beta device timing summary", beta_summary),
    ):
        if summary is not None:
            require_timing_summary(summary, label=label)

    alpha_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.alpha_runs_root)
    )
    beta_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.beta_stackctl_root)
    )
    gamma_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.gamma_stackctl_root),
    )
    prod_rollout_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.prod_rollout_stackctl_root),
        stage_label="rollout",
    )

    mainline_phases = phase_index(mainline_summary)

    service_pipeline_phase = mainline_phases.get(
        "service_pipeline", missing_phase("service_pipeline")
    )
    app_pipeline_phase = mainline_phases.get(
        "app_pipeline", missing_phase("app_pipeline")
    )
    delivery_phase = mainline_phases.get(
        "delivery_gate", missing_phase("delivery_gate")
    )
    alpha_phase = mainline_phases.get("alpha_stage", missing_phase("alpha_stage"))
    beta_phase = mainline_phases.get(
        "beta_device_matrix", missing_phase("beta_device_matrix")
    )
    gamma_phase = mainline_phases.get("gamma_local", missing_phase("gamma_local"))
    prod_rollout_phase = mainline_phases.get(
        "prod_rollout_transaction", missing_phase("prod_rollout_transaction")
    )
    chain = [
        phase_item(
            service_pipeline_phase,
            key="service_pipeline_02",
            label="02. Service Pipeline",
            path=display_path(service_summary_path),
        ),
        phase_item(
            app_pipeline_phase,
            key="app_pipeline",
            label="App Candidate Pipeline",
            path="",
        ),
        phase_item(
            delivery_phase,
            key="delivery_gate",
            label="03. Delivery Gate (share in 07)",
            path=display_path(delivery_summary_path),
        ),
        summary_item(
            mainline_summary,
            key="mainline_auto_prod",
            label="Mainline Commit To Prod",
            path=display_path(mainline_summary_path),
        ),
    ]

    environments = [
        build_environment_entry(
            key="alpha_stage",
            label="alpha-local",
            duration_seconds=alpha_phase["durationSeconds"],
            soft_budget_seconds=alpha_phase["budgetSeconds"],
            slo_eligible=bool(alpha_phase["sloEligible"]),
            evidence_status=str(alpha_phase["evidenceStatus"]),
            phase_breakdown=[],
            hotspots=top_hotspots(alpha_evidence),
            evidence_paths=[item["path"] for item in alpha_evidence],
            notes=[],
        ),
        build_environment_entry(
            key="beta_device_matrix",
            label="beta-local",
            duration_seconds=beta_phase["durationSeconds"],
            soft_budget_seconds=beta_phase["budgetSeconds"],
            slo_eligible=bool(beta_phase["sloEligible"]),
            evidence_status=str(beta_phase["evidenceStatus"]),
            phase_breakdown=subphases(beta_summary),
            hotspots=top_hotspots(beta_evidence),
            evidence_paths=[
                display_path(beta_summary_path),
                *[item["path"] for item in beta_evidence],
            ],
            notes=(
                [
                    "05 的本地预算用于 PR 默认跳过场景；mainline 诊断以 "
                    "07.beta_device_matrix 的 share 为准。"
                ]
                if beta_summary
                else []
            ),
        ),
        build_environment_entry(
            key="gamma_local",
            label="gamma-local",
            duration_seconds=gamma_phase["durationSeconds"],
            soft_budget_seconds=gamma_phase["budgetSeconds"],
            slo_eligible=bool(gamma_phase["sloEligible"]),
            evidence_status=str(gamma_phase["evidenceStatus"]),
            phase_breakdown=[],
            hotspots=top_hotspots(gamma_evidence),
            evidence_paths=[item["path"] for item in gamma_evidence],
            notes=[],
        ),
        build_environment_entry(
            key="prod_rollout_transaction",
            label="prod-hosted",
            duration_seconds=prod_rollout_phase["durationSeconds"],
            soft_budget_seconds=prod_rollout_phase["budgetSeconds"],
            slo_eligible=bool(prod_rollout_phase["sloEligible"]),
            evidence_status=str(prod_rollout_phase["evidenceStatus"]),
            phase_breakdown=[],
            hotspots=top_hotspots(prod_rollout_evidence, limit=4),
            evidence_paths=[item["path"] for item in prod_rollout_evidence],
            notes=[],
        ),
    ]

    over_budget_items: list[dict[str, Any]] = []
    for item in chain:
        if item["status"] in {"released_over_soft_budget", "failed"}:
            over_budget_items.append(item)
    for environment in environments:
        if environment["status"] in {"released_over_soft_budget", "failed"}:
            over_budget_items.append(
                {
                    "key": environment["key"],
                    "label": environment["label"],
                    "durationSeconds": environment["durationSeconds"],
                    "softBudgetSeconds": environment["softBudgetSeconds"],
                    "hardBudgetSeconds": environment["hardBudgetSeconds"],
                    "status": environment["status"],
                    "deltaFromSoftSeconds": environment["deltaFromSoftSeconds"],
                    "sloEligible": environment["sloEligible"],
                }
            )
    over_budget_items.sort(
        key=lambda item: int(item.get("deltaFromSoftSeconds", 0) or 0),
        reverse=True,
    )

    missing_evidence: list[str] = []
    # 成功路径不再把 Actions Artifact 当作跨 job 证据仓。调用方若显式给出
    # 本地/受控运行面根目录，才要求相应细节证据；主链 phase 输出本身仍构成
    # 时序门禁的最小事实来源。
    if args.service_pipeline_root and service_summary is None:
        missing_evidence.append("缺少 02.service_pipeline timing summary.json。")
    if args.delivery_gate_root and delivery_summary is None:
        missing_evidence.append("缺少 03.delivery_gate timing summary.json。")
    if args.beta_summary_root and beta_summary is None:
        missing_evidence.append("缺少 05.app_env_device_matrix timing summary.json。")
    if args.alpha_runs_root and not alpha_evidence:
        missing_evidence.append("缺少 alpha-local stackctl summary.json 证据。")
    if args.beta_stackctl_root and not beta_evidence:
        missing_evidence.append("缺少 beta-local stackctl summary.json 证据。")
    if args.gamma_stackctl_root and not gamma_evidence:
        missing_evidence.append("缺少 gamma-local stackctl summary.json 证据。")
    if args.prod_rollout_stackctl_root and not prod_rollout_evidence:
        missing_evidence.append("缺少 prod rollout stackctl summary.json 证据。")
    for label, summary in (
        ("07.mainline_auto_prod", mainline_summary),
        ("02.service_pipeline", service_summary),
        ("03.delivery_gate", delivery_summary),
        ("05.app_env_device_matrix", beta_summary),
    ):
        if summary is None or summary.get("status") != "historical_incomplete":
            continue
        declared_missing = ", ".join(str(item) for item in summary["missingEvidence"])
        missing_evidence.append(
            f"{label} 为 historical_incomplete，不参与 SLO 统计：{declared_missing}"
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "title": "Environment Chain Timing Diagnostics",
        "servicePipelineSummaryPath": display_path(service_summary_path),
        "deliveryGateSummaryPath": display_path(delivery_summary_path),
        "betaSummaryPath": display_path(beta_summary_path),
        "mainlineSummaryPath": display_path(mainline_summary_path),
        "chain": chain,
        "environments": environments,
        "overBudgetItems": over_budget_items,
        "missingEvidence": missing_evidence,
        "recommendations": recommendation_lines(
            {item["key"] for item in over_budget_items},
            missing_evidence,
        ),
    }

    markdown = render_markdown(payload)
    write_outputs(
        payload=payload,
        markdown=markdown,
        json_path=args.write_json,
        markdown_path=args.write_markdown,
        write_step_summary=args.write_step_summary,
    )
    print(markdown)
    if args.emit_annotations:
        emit_annotations(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
