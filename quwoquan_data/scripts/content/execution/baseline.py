"""data baseline — 冻结数据专题规格与配置基线。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

from core.command_packet import build_packet, write_packet
from core.io import read_json, read_ndjson, write_json
from core.paths import REPO_ROOT, execution_spec_path
from content.execution.workspace import (
    execution_progress_path,
    ensure_execution_work_package_layout,
    execution_baseline_freeze_packet_path,
    execution_catalog_path,
    execution_shared_path,
)

# 默认基线文档锚定 core.paths 的唯一仓库根，不依赖进程 cwd、隔离 data root，
# 也不重复用 __file__.parents 推导目录层级。
DEFAULT_SPEC_DOC = REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/spec.md"
DEFAULT_DESIGN_DOC = REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/design.md"
DEFAULT_ACCEPTANCE_DOC = REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/acceptance.yaml"
DEFAULT_WORKFLOW_DOC = REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/workflow.md"
DEFAULT_COMMAND_MATRIX_DOC = (
    REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/command-matrix.md"
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


def _baseline_summary(
    *,
    spec: dict[str, Any],
    catalog_rows: list[dict[str, Any]],
    coverage_targets: list[str],
) -> dict[str, Any]:
    return {
        "catalogRowCount": len(catalog_rows),
        "coverageTargetCount": len(coverage_targets),
        "executionRegion": str((spec.get("scope") or {}).get("region") or ""),
        "executionEntityTypes": [
            str(value)
            for value in (spec.get("scope") or {}).get("entityTypes") or []
            if str(value)
        ],
        "catalogRequired": True,
    }


def _input_paths(
    *,
    execution_spec: Path,
    progress: Path,
    catalog: Path,
    spec_doc: Path,
    design_doc: Path,
    acceptance_doc: Path,
    workflow_doc: Path,
    command_matrix_doc: Path,
) -> dict[str, str]:
    return {
        "executionSpecPath": str(execution_spec),
        "progressPath": str(progress),
        "catalogPath": str(catalog),
        "specDocPath": str(spec_doc),
        "designDocPath": str(design_doc),
        "acceptanceDocPath": str(acceptance_doc),
        "workflowDocPath": str(workflow_doc),
        "commandMatrixDocPath": str(command_matrix_doc),
    }


def _write_failed_baseline_report(
    *,
    execution_id: str,
    report_path: Path,
    packet_path: Path,
    issues: list[str],
    input_paths: dict[str, str],
    summary: dict[str, Any],
) -> None:
    write_json(
        report_path,
        {
            "schemaVersion": "quwoquan.data.baseline_report/1",
            "executionId": execution_id,
            "status": "failed",
            "issues": issues,
            "packetPath": str(packet_path),
            "inputPaths": input_paths,
            "summary": summary,
        },
    )


def handle_baseline(args: argparse.Namespace) -> None:
    execution_id = str(args.execution_id).strip()
    root = ensure_execution_work_package_layout(execution_id)
    issues: list[str] = []

    execution_spec_path_value = execution_spec_path(execution_id)
    progress_path = execution_progress_path(execution_id)
    catalog_path = (
        Path(args.catalog)
        if getattr(args, "catalog", None)
        else execution_catalog_path(execution_id)
    )
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
        "execution-spec": execution_spec_path_value,
        "progress": progress_path,
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
    if execution_spec_path_value.exists():
        try:
            spec = _load_yaml(execution_spec_path_value)
        except Exception as exc:
            issues.append(f"execution-spec unreadable: {exc}")
            spec = {}
    _ensure_exists(catalog_path, "catalog", issues)
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

    spec_execution_id = str(spec.get("executionId") or "").strip() if isinstance(spec, dict) else ""
    if spec_execution_id and spec_execution_id != execution_id:
        issues.append(f"execution spec identity mismatch: {spec_execution_id} != {execution_id}")
    if isinstance(progress, dict) and str(progress.get("executionId") or "").strip() not in ("", execution_id):
        issues.append(f"execution progress identity mismatch: {progress.get('executionId')} != {execution_id}")
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

    summary = _baseline_summary(
        spec=spec if isinstance(spec, dict) else {},
        catalog_rows=catalog_rows,
        coverage_targets=coverage_targets,
    )
    packet_path = execution_baseline_freeze_packet_path(execution_id)
    report_path = execution_shared_path(execution_id, "baseline_report.json")
    input_paths = _input_paths(
        execution_spec=execution_spec_path_value,
        progress=progress_path,
        catalog=catalog_path,
        spec_doc=spec_doc,
        design_doc=design_doc,
        acceptance_doc=acceptance_doc,
        workflow_doc=workflow_doc,
        command_matrix_doc=command_matrix_doc,
    )
    if issues:
        _write_failed_baseline_report(
            execution_id=execution_id,
            report_path=report_path,
            packet_path=packet_path,
            issues=issues,
            input_paths=input_paths,
            summary=summary,
        )
        print(f"[baseline] executionId: {execution_id}")
        print(f"[baseline] Report: {report_path}")
        print(f"[baseline] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)

    packet_inputs = {
        "executionSpecPath": str(execution_spec_path_value),
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
        execution_id=execution_id,
        command="content execution baseline",
        object_kind="execution",
        object_ref=execution_id,
        stage="baseline",
        read_policy=[
            "0.plan/execution_spec.yaml",
            "_shared/execution_progress.json",
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
            "executionId mismatch",
            "catalog does not cover all explore targets",
            "catalog-config / geo-band-rules path mismatch",
        ],
        output_policy=[
            "write execution/_shared/baseline_freeze_packet.json",
            "write execution/_shared/baseline_report.json",
        ],
        inputs=packet_inputs,
        outputs={
            "packetPath": str(execution_baseline_freeze_packet_path(execution_id)),
            "reportPath": str(execution_shared_path(execution_id, "baseline_report.json")),
        },
        handoff_to="task geo-homepages",
        evidence={
            "required": ["baseline_freeze_packet.json", "baseline_report.json"],
            "optional": ["catalog.ndjson"],
        },
        summary=summary,
    )

    write_packet(packet_path, packet)

    report = {
        "schemaVersion": "quwoquan.data.baseline_report/1",
        "executionId": execution_id,
        "status": "passed",
        "issues": [],
        "packetPath": str(packet_path),
        "inputPaths": input_paths,
        "summary": packet["summary"],
    }
    write_json(report_path, report)
    if getattr(args, "output", None):
        output_path = Path(args.output)
        write_packet(output_path, packet)

    print(f"[baseline] executionId: {execution_id}")
    print(f"[baseline] Execution root: {root}")
    print(f"[baseline] Packet: {packet_path}")
    print(f"[baseline] Report: {report_path}")
    print(f"[baseline] Coverage targets: {len(coverage_targets)}")
    print(f"[baseline] Catalog rows: {len(catalog_rows)}")

    print("[baseline] PASSED")
