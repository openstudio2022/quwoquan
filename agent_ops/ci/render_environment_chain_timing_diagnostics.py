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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-pipeline-root", default="")
    parser.add_argument("--delivery-gate-root", default="")
    parser.add_argument("--beta-summary-root", default="")
    parser.add_argument("--mainline-summary", required=True)
    parser.add_argument("--commit-summary", required=True)
    parser.add_argument("--alpha-stackctl-root", default="")
    parser.add_argument("--beta-stackctl-root", default="")
    parser.add_argument("--prod-initial-stackctl-root", default="")
    parser.add_argument("--prod-full-stackctl-root", default="")
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
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def find_named_json(root: Path | None, filename: str) -> tuple[dict[str, Any] | None, Path | None]:
    if root is None or not root.exists():
        return None, None
    if root.is_file():
        return (read_json(root), root) if root.name == filename else (None, None)
    matches = sorted(root.rglob(filename))
    if not matches:
        return None, None
    return read_json(matches[0]), matches[0]


def format_seconds(value: int) -> str:
    minutes, seconds = divmod(max(int(value), 0), 60)
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}m {seconds:02d}s"


def format_duration_ms(value: int) -> str:
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000.0:.2f}s"


def build_status(seconds: int, budget_seconds: int) -> dict[str, Any]:
    delta = int(seconds) - int(budget_seconds)
    return {
        "seconds": int(seconds),
        "budgetSeconds": int(budget_seconds),
        "budgetStatus": "within_budget" if delta <= 0 else "over_budget",
        "deltaSeconds": delta,
    }


def phase_index(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases = summary.get("phases") or []
    items: dict[str, dict[str, Any]] = {}
    for phase in phases:
        key = str(phase.get("key", "")).strip()
        if not key:
            continue
        items[key] = {
            "key": key,
            "seconds": int(phase.get("seconds", 0) or 0),
            "budgetSeconds": (
                int(phase.get("budgetSeconds", 0) or 0)
                if phase.get("budgetSeconds") is not None
                else 0
            ),
        }
    return items


def collect_stackctl_primary_summaries(root: Path | None, *, stage_label: str = "") -> list[dict[str, Any]]:
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


def top_hotspots(items: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    return items[:limit]


def summary_item(summary: dict[str, Any], *, key: str, label: str, path: str = "") -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "path": path,
        **build_status(
            int(summary.get("criticalPathSeconds", 0) or 0),
            int(summary.get("budgetSeconds", 0) or 0),
        ),
    }


def phase_item(item: dict[str, Any], *, key: str, label: str, path: str = "") -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "path": path,
        **build_status(int(item.get("seconds", 0) or 0), int(item.get("budgetSeconds", 0) or 0)),
    }


def subphases(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    items: list[dict[str, Any]] = []
    for phase in summary.get("phases") or []:
        key = str(phase.get("key", "")).strip()
        if not key:
            continue
        items.append(
            {
                "key": key,
                "seconds": int(phase.get("seconds", 0) or 0),
                "budgetSeconds": (
                    int(phase.get("budgetSeconds", 0) or 0)
                    if phase.get("budgetSeconds") is not None
                    else 0
                ),
            }
        )
    return items


def build_environment_entry(
    *,
    key: str,
    label: str,
    seconds: int,
    budget_seconds: int,
    phase_breakdown: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
    evidence_paths: list[str],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        **build_status(seconds, budget_seconds),
        "phaseBreakdown": phase_breakdown,
        "hotspots": hotspots,
        "evidencePaths": [item for item in evidence_paths if item],
        "notes": [item for item in notes if item],
    }


def recommendation_lines(over_budget_keys: set[str], missing_evidence: list[str]) -> list[str]:
    recommendations: list[str] = []
    mapping = {
        "service_pipeline_02": "优先检查 02 中最长的镜像构建 phase，继续压缩 build cache miss 与 release snapshot fanout。",
        "delivery_gate": "优先检查 03 Delivery Gate 的最长 fanout（service/app/portal），避免主链被非关键扫描拖慢。",
        "alpha_stage": "优先检查 alpha-local 的 package/up/inspect 链路，能复用的本地产物尽量复用。",
        "beta_device_matrix": "优先检查 beta bootstrap 与 mobile matrix fanout，坏环境要尽早 fail-fast，避免继续空转。",
        "prod_initial_checks": "优先检查 prod initial rollout 的 deploy 与 post-deploy 探针，避免首段放量过慢。",
        "prod_full": "优先检查 prod full rollout 与回滚探针，继续收敛重复 health/inspect/doctor。",
        "main_commit_to_prod": "commit-to-prod 已触达 15 分钟红线，先处理上面首个超预算阶段，再看总链路余量。",
    }
    for key in sorted(over_budget_keys):
        line = mapping.get(key)
        if line and line not in recommendations:
            recommendations.append(line)
    if missing_evidence:
        recommendations.append("存在耗时证据缺口，需补齐对应 artifact/summary.json，否则无法稳定定位慢点与 flaky 来源。")
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
                format_seconds(item["seconds"]),
                format_seconds(item["budgetSeconds"]),
                item["budgetStatus"],
            )
        )
    over_budget = report.get("overBudgetItems") or []
    if over_budget:
        lines.append("- over-budget:")
        for item in over_budget:
            lines.append(
                "  - `{0}`: `{1}` over `{2}` (`+{3}`)".format(
                    item["label"],
                    format_seconds(item["seconds"]),
                    format_seconds(item["budgetSeconds"]),
                    format_seconds(abs(int(item["deltaSeconds"]))),
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
                format_seconds(environment["seconds"]),
                format_seconds(environment["budgetSeconds"]),
                environment["budgetStatus"],
            )
        )
        for phase in environment.get("phaseBreakdown") or []:
            budget = int(phase.get("budgetSeconds", 0) or 0)
            suffix = f" / {format_seconds(budget)}" if budget > 0 else ""
            lines.append(
                "    - phase `{0}`: `{1}{2}`".format(
                    phase["key"],
                    format_seconds(int(phase.get("seconds", 0) or 0)),
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
                format_seconds(item["seconds"]),
                format_seconds(item["budgetSeconds"]),
            )
        )
    for message in report.get("missingEvidence") or []:
        print(f"::warning::[timing-diagnostic/missing-evidence] {message}")


def main() -> int:
    args = parse_args()

    mainline_summary_path = resolve_path(args.mainline_summary)
    commit_summary_path = resolve_path(args.commit_summary)
    assert mainline_summary_path is not None
    assert commit_summary_path is not None
    mainline_summary = read_json(mainline_summary_path)
    commit_summary = read_json(commit_summary_path)

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

    alpha_evidence = collect_stackctl_primary_summaries(resolve_path(args.alpha_stackctl_root))
    beta_evidence = collect_stackctl_primary_summaries(resolve_path(args.beta_stackctl_root))
    prod_initial_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.prod_initial_stackctl_root),
        stage_label="initial",
    )
    prod_full_evidence = collect_stackctl_primary_summaries(
        resolve_path(args.prod_full_stackctl_root),
        stage_label="full",
    )

    mainline_phases = phase_index(mainline_summary)
    commit_phases = phase_index(commit_summary)

    delivery_phase = mainline_phases.get("delivery_gate", {"seconds": 0, "budgetSeconds": 0})
    alpha_phase = mainline_phases.get("alpha_stage", {"seconds": 0, "budgetSeconds": 0})
    beta_phase = mainline_phases.get("beta_device_matrix", {"seconds": 0, "budgetSeconds": 0})
    prod_initial_phase = mainline_phases.get("prod_initial_checks", {"seconds": 0, "budgetSeconds": 0})
    prod_full_phase = mainline_phases.get("prod_full", {"seconds": 0, "budgetSeconds": 0})
    service_pipeline_phase = commit_phases.get("service_pipeline_02", {"seconds": 0, "budgetSeconds": 0})
    mainline_phase = commit_phases.get("mainline_auto_prod_07", {"seconds": 0, "budgetSeconds": 0})

    chain = [
        phase_item(
            service_pipeline_phase,
            key="service_pipeline_02",
            label="02. Service Pipeline",
            path=display_path(service_summary_path),
        ),
        phase_item(
            delivery_phase,
            key="delivery_gate",
            label="03. Delivery Gate (share in 07)",
            path=display_path(delivery_summary_path),
        ),
        phase_item(
            mainline_phase,
            key="mainline_auto_prod_07",
            label="07. Mainline Auto Prod",
            path=display_path(mainline_summary_path),
        ),
        summary_item(
            commit_summary,
            key="main_commit_to_prod",
            label="Main Commit To Prod",
            path=display_path(commit_summary_path),
        ),
    ]

    prod_total_seconds = int(prod_initial_phase["seconds"]) + int(prod_full_phase["seconds"])
    prod_total_budget = int(prod_initial_phase["budgetSeconds"]) + int(prod_full_phase["budgetSeconds"])

    environments = [
        build_environment_entry(
            key="alpha_stage",
            label="alpha-local",
            seconds=int(alpha_phase["seconds"]),
            budget_seconds=int(alpha_phase["budgetSeconds"]),
            phase_breakdown=[],
            hotspots=top_hotspots(alpha_evidence),
            evidence_paths=[item["path"] for item in alpha_evidence],
            notes=[],
        ),
        build_environment_entry(
            key="beta_device_matrix",
            label="beta-local",
            seconds=int(beta_phase["seconds"]),
            budget_seconds=int(beta_phase["budgetSeconds"]),
            phase_breakdown=subphases(beta_summary),
            hotspots=top_hotspots(beta_evidence),
            evidence_paths=[display_path(beta_summary_path), *[item["path"] for item in beta_evidence]],
            notes=(
                [
                    "05 的本地预算用于 PR 默认跳过场景；mainline 诊断以 07.beta_device_matrix 的 share 为准。"
                ]
                if beta_summary
                else []
            ),
        ),
        build_environment_entry(
            key="prod_hosted",
            label="prod-hosted",
            seconds=prod_total_seconds,
            budget_seconds=prod_total_budget,
            phase_breakdown=[
                {
                    "key": "prod_initial_checks",
                    "seconds": int(prod_initial_phase["seconds"]),
                    "budgetSeconds": int(prod_initial_phase["budgetSeconds"]),
                },
                {
                    "key": "prod_full",
                    "seconds": int(prod_full_phase["seconds"]),
                    "budgetSeconds": int(prod_full_phase["budgetSeconds"]),
                },
            ],
            hotspots=top_hotspots(prod_initial_evidence + prod_full_evidence, limit=4),
            evidence_paths=[
                *[item["path"] for item in prod_initial_evidence],
                *[item["path"] for item in prod_full_evidence],
            ],
            notes=[],
        ),
    ]

    over_budget_items: list[dict[str, Any]] = []
    for item in chain:
        if item["budgetStatus"] == "over_budget":
            over_budget_items.append(item)
    for environment in environments:
        if environment["budgetStatus"] == "over_budget":
            over_budget_items.append(
                {
                    "key": environment["key"],
                    "label": environment["label"],
                    "seconds": environment["seconds"],
                    "budgetSeconds": environment["budgetSeconds"],
                    "deltaSeconds": environment["deltaSeconds"],
                }
            )
    for item in (
        phase_item(prod_initial_phase, key="prod_initial_checks", label="prod initial"),
        phase_item(prod_full_phase, key="prod_full", label="prod full"),
    ):
        if item["budgetStatus"] == "over_budget":
            over_budget_items.append(item)
    over_budget_items.sort(key=lambda item: int(item.get("deltaSeconds", 0) or 0), reverse=True)

    missing_evidence: list[str] = []
    if service_summary is None:
        missing_evidence.append("缺少 02.service_pipeline timing artifact（service-pipeline-summary.json）。")
    if delivery_summary is None:
        missing_evidence.append("缺少 03.delivery_gate timing artifact（delivery-gate-summary.json）。")
    if beta_summary is None:
        missing_evidence.append("缺少 05.app_env_device_matrix timing artifact（app-env-device-matrix-summary.json）。")
    if not alpha_evidence:
        missing_evidence.append("缺少 alpha-local stackctl summary.json 证据。")
    if not beta_evidence:
        missing_evidence.append("缺少 beta-local stackctl summary.json 证据。")
    if not prod_initial_evidence:
        missing_evidence.append("缺少 prod initial stackctl summary.json 证据。")
    if not prod_full_evidence:
        missing_evidence.append("缺少 prod full stackctl summary.json 证据。")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "title": "Environment Chain Timing Diagnostics",
        "servicePipelineSummaryPath": display_path(service_summary_path),
        "deliveryGateSummaryPath": display_path(delivery_summary_path),
        "betaSummaryPath": display_path(beta_summary_path),
        "mainlineSummaryPath": display_path(mainline_summary_path),
        "commitSummaryPath": display_path(commit_summary_path),
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
