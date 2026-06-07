"""data baseline — 冻结数据专题规格与配置基线。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

from _common.command_packet import build_packet, write_packet
from _common.io import read_json, read_ndjson, write_json
from _common.paths import (
    committed_task_progress,
    committed_task_spec,
    ensure_task_layout,
    task_baseline_freeze_packet_path,
    task_catalog,
    task_shared_dir,
)

DEFAULT_SPEC_DOC = Path("specs/feature-tree/runtime/runtime-data-engineering/spec.md")
DEFAULT_DESIGN_DOC = Path("specs/feature-tree/runtime/runtime-data-engineering/design.md")
DEFAULT_ACCEPTANCE_DOC = Path("specs/feature-tree/runtime/runtime-data-engineering/acceptance.yaml")
DEFAULT_WORKFLOW_DOC = Path("specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/workflow.md")
DEFAULT_COMMAND_MATRIX_DOC = Path(
    "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/command-matrix.md"
)


def _file_snapshot(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def _ensure_exists(path: Path, label: str, issues: list[str]) -> None:
    if not path.exists():
        issues.append(f"{label} missing: {path}")


def _load_yaml(path: Path) -> Any:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if raw is not None else {}


def _validate_catalog_config_pair(catalog_config: Path | None, geo_band_rules: Path | None, issues: list[str]) -> None:
    if not catalog_config or not geo_band_rules:
        return
    _ensure_exists(catalog_config, "catalog-config", issues)
    _ensure_exists(geo_band_rules, "geo-band-rules", issues)
    if issues:
        return
    doc = _load_yaml(catalog_config)
    if not isinstance(doc, dict):
        issues.append(f"catalog-config not a mapping: {catalog_config}")
        return
    rel = str(doc.get("geo_band_rules_path") or "").strip()
    if not rel:
        issues.append(f"catalog-config missing geo_band_rules_path: {catalog_config}")
        return
    expected = (catalog_config.parent / rel).resolve()
    actual = geo_band_rules.resolve()
    if expected != actual:
        issues.append(
            "catalog-config / geo-band-rules mismatch: "
            f"expected={expected} actual={actual}"
        )


def _catalog_topic_ids(catalog_path: Path) -> list[str]:
    rows = read_ndjson(catalog_path) if catalog_path.exists() else []
    topic_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic_id") or row.get("entityId") or "").strip()
        if topic:
            topic_ids.append(topic)
    return topic_ids


def handle_baseline(args: argparse.Namespace) -> None:
    task_id = str(args.task).strip()
    root = ensure_task_layout(task_id)
    issues: list[str] = []

    task_spec_path = committed_task_spec(task_id)
    progress_path = committed_task_progress(task_id)
    catalog_path = Path(args.catalog) if getattr(args, "catalog", None) else task_catalog(task_id)
    spec_doc = _optional_path(getattr(args, "spec_doc", None)) or DEFAULT_SPEC_DOC
    design_doc = _optional_path(getattr(args, "design_doc", None)) or DEFAULT_DESIGN_DOC
    acceptance_doc = _optional_path(getattr(args, "acceptance_doc", None)) or DEFAULT_ACCEPTANCE_DOC
    workflow_doc = _optional_path(getattr(args, "workflow_doc", None)) or DEFAULT_WORKFLOW_DOC
    command_matrix_doc = _optional_path(getattr(args, "command_matrix_doc", None)) or DEFAULT_COMMAND_MATRIX_DOC
    catalog_config = _optional_path(getattr(args, "catalog_config", None))
    naming_rules = _optional_path(getattr(args, "naming_rules", None))
    geo_band_rules = _optional_path(getattr(args, "geo_band_rules", None))
    schema_files = [Path(p) for p in (getattr(args, "schema_files", None) or [])]
    config_files = [Path(p) for p in (getattr(args, "config_files", None) or [])]

    required_files = {
        "task-spec": task_spec_path,
        "progress": progress_path,
        "catalog": catalog_path,
        "spec-doc": spec_doc,
        "design-doc": design_doc,
        "acceptance-doc": acceptance_doc,
        "workflow-doc": workflow_doc,
        "command-matrix-doc": command_matrix_doc,
    }
    for label, path in required_files.items():
        _ensure_exists(path, label, issues)
    for idx, path in enumerate(schema_files, start=1):
        _ensure_exists(path, f"schema-file[{idx}]", issues)
    for idx, path in enumerate(config_files, start=1):
        _ensure_exists(path, f"config-file[{idx}]", issues)
    if naming_rules:
        _ensure_exists(naming_rules, "naming-rules", issues)
    _validate_catalog_config_pair(catalog_config, geo_band_rules, issues)

    spec = {}
    progress = {}
    catalog_rows: list[dict[str, Any]] = []
    if task_spec_path.exists():
        try:
            spec = _load_yaml(task_spec_path)
        except Exception as exc:
            issues.append(f"task-spec unreadable: {exc}")
            spec = {}
    if progress_path.exists():
        try:
            progress = read_json(progress_path)
        except Exception as exc:
            issues.append(f"progress unreadable: {exc}")
            progress = {}
    if catalog_path.exists():
        try:
            catalog_rows = read_ndjson(catalog_path)
        except Exception as exc:
            issues.append(f"catalog unreadable: {exc}")
            catalog_rows = []

    task_spec_task_id = str(spec.get("taskId") or "").strip() if isinstance(spec, dict) else ""
    if task_spec_task_id and task_spec_task_id != task_id:
        issues.append(f"task-spec taskId mismatch: {task_spec_task_id} != {task_id}")
    if isinstance(progress, dict) and str(progress.get("taskId") or "").strip() not in ("", task_id):
        issues.append(f"progress taskId mismatch: {progress.get('taskId')} != {task_id}")
    if not catalog_rows:
        issues.append("catalog.ndjson is empty")

    coverage_targets = [
        str(t.get("entityType") or "") + "/" + str(t.get("name") or "")
        for t in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(t, dict) and t.get("entityType") and t.get("name")
    ]
    catalog_topic_ids = _catalog_topic_ids(catalog_path)
    missing = sorted(set(coverage_targets) - set(catalog_topic_ids))
    if missing:
        issues.append(f"catalog missing coverage targets: {missing}")

    packet_inputs = {
        "taskSpecPath": str(task_spec_path),
        "progressPath": str(progress_path),
        "catalogPath": str(catalog_path),
        "specDoc": _file_snapshot(spec_doc),
        "designDoc": _file_snapshot(design_doc),
        "acceptanceDoc": _file_snapshot(acceptance_doc),
        "workflowDoc": _file_snapshot(workflow_doc),
        "commandMatrixDoc": _file_snapshot(command_matrix_doc),
        "schemaFiles": [_file_snapshot(path) for path in schema_files],
        "configFiles": [_file_snapshot(path) for path in config_files],
    }
    if catalog_config:
        packet_inputs["catalogConfig"] = _file_snapshot(catalog_config)
    if naming_rules:
        packet_inputs["namingRules"] = _file_snapshot(naming_rules)
    if geo_band_rules:
        packet_inputs["geoBandRules"] = _file_snapshot(geo_band_rules)

    packet = build_packet(
        task_id=task_id,
        command="data baseline",
        object_kind="task",
        object_ref=task_id,
        stage="baseline",
        read_policy=[
            "task.yaml",
            "progress.json",
            "catalog.ndjson",
            "spec.md",
            "design.md",
            "acceptance.yaml",
            "workflow.md",
            "command-matrix.md",
            "schema/config list",
        ],
        stop_if=[
            "any required doc/config/schema missing",
            "taskId mismatch",
            "catalog does not cover all explore targets",
            "catalog-config / geo-band-rules path mismatch",
        ],
        output_policy=[
            "write task/_shared/baseline_freeze_packet.json",
            "write task/_shared/baseline_report.json",
        ],
        inputs=packet_inputs,
        outputs={
            "packetPath": str(task_baseline_freeze_packet_path(task_id)),
            "reportPath": str(task_shared_dir(task_id) / "baseline_report.json"),
        },
        handoff_to="data workflow run",
        evidence={
            "required": ["baseline_freeze_packet.json", "baseline_report.json"],
            "optional": ["catalog.ndjson"],
        },
        summary={
            "catalogRowCount": len(catalog_rows),
            "coverageTargetCount": len(coverage_targets),
            "taskRegion": str((spec.get("scope") or {}).get("region") or ""),
            "taskEntityTypes": [str(v) for v in (spec.get("scope") or {}).get("entityTypes") or [] if str(v)],
        },
    )

    packet_path = task_baseline_freeze_packet_path(task_id)
    write_packet(packet_path, packet)

    report = {
        "schemaVersion": "quwoquan.data.baseline_report/1",
        "taskId": task_id,
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "packetPath": str(packet_path),
        "inputs": packet_inputs,
        "summary": packet["summary"],
    }
    report_path = task_shared_dir(task_id) / "baseline_report.json"
    write_json(report_path, report)
    if getattr(args, "output", None):
        output_path = Path(args.output)
        write_packet(output_path, packet)

    print(f"[baseline] Task: {task_id}")
    print(f"[baseline] Task root: {root}")
    print(f"[baseline] Packet: {packet_path}")
    print(f"[baseline] Report: {report_path}")
    print(f"[baseline] Coverage targets: {len(coverage_targets)}")
    print(f"[baseline] Catalog rows: {len(catalog_rows)}")

    if issues:
        print(f"[baseline] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[baseline] PASSED")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("baseline", help="Freeze data spec/docs/configs before workflow")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--catalog", help="catalog.ndjson path (default: task catalog)")
    p.add_argument("--spec-doc", dest="spec_doc", help="spec.md path")
    p.add_argument("--design-doc", dest="design_doc", help="design.md path")
    p.add_argument("--acceptance-doc", dest="acceptance_doc", help="acceptance.yaml path")
    p.add_argument("--workflow-doc", dest="workflow_doc", help="workflow.md path")
    p.add_argument("--command-matrix-doc", dest="command_matrix_doc", help="command-matrix.md path")
    p.add_argument("--catalog-config", help="geo_catalog_config.yaml path")
    p.add_argument("--naming-rules", help="entity_naming_rules.yaml path")
    p.add_argument("--geo-band-rules", help="geo_band_rules.yaml path")
    p.add_argument("--schema-files", nargs="*", default=[], help="Schema file list")
    p.add_argument("--config-files", nargs="*", default=[], help="Config file list")
    p.add_argument("--output", help="Optional packet copy path")
    p.set_defaults(handler=handle_baseline)
