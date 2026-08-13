"""对象级差异汇总、model_version 判定与兼容性报告落盘。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .comparison import (
    _compare_command_operation,
    _compare_query_operation,
    _compare_storage,
)
from .evidence import _migration_valid, _window_closed
from .graph_view import ChangeSet, GraphView, ModelVersion
from .primitives import COMPATIBILITY_LEVELS, InputError, REPORT_SCHEMA


def _by_object(
    operations: Iterable[Mapping[str, Any]], kind: str
) -> dict[str, dict[str, Mapping[str, Any]]]:
    result: dict[str, dict[str, Mapping[str, Any]]] = {}
    for operation in operations:
        if operation.get("kind") != kind:
            continue
        object_id = operation.get("objectId")
        operation_id = operation.get("id")
        if not isinstance(object_id, str) or not isinstance(operation_id, str):
            raise InputError("operation id/objectId must be non-empty strings")
        result.setdefault(object_id, {})[operation_id] = operation
    return result


def _operation_changes(
    baseline_graph: GraphView,
    current_graph: GraphView,
    object_id: str,
    kind: str,
) -> tuple[ChangeSet, set[str]]:
    baseline_operations = list(baseline_graph.operations.values()) + list(
        baseline_graph.graphql_operations.values()
    )
    current_operations = list(current_graph.operations.values()) + list(
        current_graph.graphql_operations.values()
    )
    old_map = _by_object(baseline_operations, kind).get(object_id, {})
    new_map = _by_object(current_operations, kind).get(object_id, {})
    changes = ChangeSet()
    incompatible_operations: set[str] = set()
    noun = "query" if kind == "query" else "command"
    for operation_id in sorted(set(old_map) - set(new_map)):
        changes.add("incompatible", f"{noun}_operation_removed", operation_id)
        incompatible_operations.add(operation_id)
    for operation_id in sorted(set(new_map) - set(old_map)):
        changes.add("compatible", f"{noun}_operation_added", operation_id)
    for operation_id in sorted(set(old_map) & set(new_map)):
        if kind == "query":
            delta = _compare_query_operation(
                baseline_graph, current_graph, old_map[operation_id], new_map[operation_id]
            )
        else:
            delta = _compare_command_operation(
                baseline_graph, current_graph, old_map[operation_id], new_map[operation_id]
            )
        changes.extend(delta)
        if delta.level == "incompatible":
            incompatible_operations.add(operation_id)
    return changes, incompatible_operations


def build_report(
    baseline_graph: GraphView,
    current_graph: GraphView,
    baseline_receipt: Mapping[str, Any],
    compatibility_window: Mapping[str, Mapping[str, Any]],
    compatibility_window_digest: str | None,
    migration_plans: Mapping[str, Mapping[str, Any]],
    migration_plan_digest: str | None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    for detail in baseline_graph.input_issues + current_graph.input_issues:
        issues.append({"code": "GRAPHQL.CONTRACT.INVALID", "detail": detail})
    object_reports: list[dict[str, Any]] = []
    all_object_ids = sorted(set(baseline_graph.objects) | set(current_graph.objects))
    for object_id in all_object_ids:
        if object_id not in baseline_graph.objects:
            current_version = current_graph.model_version(object_id)
            required_version = ModelVersion(1, 0)
            version_ok = current_version == required_version
            if not version_ok:
                issues.append(
                    {
                        "code": "MODEL_VERSION.NEW_OBJECT_INVALID",
                        "detail": f"{object_id}: expected 1.0, declared {current_version}",
                    }
                )
            object_reports.append(
                {
                    "objectId": object_id,
                    "baselineModelVersion": None,
                    "currentModelVersion": str(current_version),
                    "requiredModelVersion": str(required_version),
                    "changeImpact": {
                        "query": "compatible",
                        "command": "compatible",
                        "storage": "compatible",
                    },
                    "migrationMode": "additive",
                    "changes": [
                        {
                            "level": "compatible",
                            "code": "object_added",
                            "detail": object_id,
                        }
                    ],
                    "compatibilityWindow": [],
                    "versionDeclarationValid": version_ok,
                }
            )
            continue
        baseline_version = baseline_graph.model_version(object_id)
        if object_id not in current_graph.objects:
            required_version = baseline_version.next_major()
            issues.append(
                {
                    "code": "DOMAIN_MODEL.OBJECT_REMOVED",
                    "detail": f"{object_id}: object removal has no current owner for required {required_version}",
                }
            )
            object_reports.append(
                {
                    "objectId": object_id,
                    "baselineModelVersion": str(baseline_version),
                    "currentModelVersion": None,
                    "requiredModelVersion": str(required_version),
                    "changeImpact": {
                        "query": "incompatible",
                        "command": "incompatible",
                        "storage": "incompatible",
                    },
                    "migrationMode": "quiesced_atomic",
                    "changes": [
                        {
                            "level": "incompatible",
                            "code": "object_removed",
                            "detail": object_id,
                        }
                    ],
                    "compatibilityWindow": [],
                    "versionDeclarationValid": False,
                }
            )
            continue
        current_version = current_graph.model_version(object_id)
        query_changes, query_incompatible = _operation_changes(
            baseline_graph, current_graph, object_id, "query"
        )
        command_changes, command_incompatible = _operation_changes(
            baseline_graph, current_graph, object_id, "command"
        )
        storage_changes = _compare_storage(
            baseline_graph.storage_signature(object_id),
            current_graph.storage_signature(object_id),
        )
        overall_level = max(
            (query_changes.level, command_changes.level, storage_changes.level),
            key=COMPATIBILITY_LEVELS.__getitem__,
        )
        if overall_level == "incompatible":
            required_version = baseline_version.next_major()
        elif overall_level == "compatible":
            required_version = baseline_version.next_minor()
        else:
            required_version = baseline_version
        version_ok = current_version == required_version
        if not version_ok:
            issues.append(
                {
                    "code": "MODEL_VERSION.DECLARATION_MISMATCH",
                    "detail": (
                        f"{object_id}: declared {current_version}, required {required_version}; "
                        "the gate never rewrites object.yaml"
                    ),
                }
            )
        window_results: list[dict[str, Any]] = []
        for operation_id in sorted(query_incompatible | command_incompatible):
            closed, result = _window_closed(operation_id, compatibility_window)
            result["status"] = "closed" if closed else "blocked"
            window_results.append(result)
            if not closed:
                issues.append(
                    {
                        "code": "COMPATIBILITY_WINDOW.OPEN",
                        "detail": f"{object_id}/{operation_id}: minimum App support window is not closed",
                    }
                )
        migration_mode = (
            "quiesced_atomic"
            if storage_changes.level == "incompatible"
            else ("additive" if storage_changes.level == "compatible" else "none")
        )
        migration_status = "not_required"
        if storage_changes.level == "incompatible":
            migration_ok, migration_status = _migration_valid(object_id, migration_plans)
            if not migration_ok:
                issues.append(
                    {
                        "code": "STORAGE.MIGRATION.BLOCKED",
                        "detail": f"{object_id}: {migration_status}",
                    }
                )
        all_changes = sorted(
            query_changes.changes + command_changes.changes + storage_changes.changes,
            key=lambda item: (item["code"], item["detail"], item["level"]),
        )
        object_reports.append(
            {
                "objectId": object_id,
                "baselineModelVersion": str(baseline_version),
                "currentModelVersion": str(current_version),
                "requiredModelVersion": str(required_version),
                "changeImpact": {
                    "query": query_changes.level,
                    "command": command_changes.level,
                    "storage": storage_changes.level,
                },
                "migrationMode": migration_mode,
                "migrationEvidence": migration_status,
                "changes": all_changes,
                "compatibilityWindow": window_results,
                "versionDeclarationValid": version_ok,
            }
        )
    issues.sort(key=lambda item: (item["code"], item["detail"]))
    return {
        "schema": REPORT_SCHEMA,
        "status": "blocked" if issues else "passed",
        "baseline": {
            "authority": baseline_receipt.get("authority"),
            "stage": str(baseline_receipt.get("stage")),
            "receiptId": baseline_receipt.get("receiptId"),
            "committedGeneration": baseline_receipt.get("committedGeneration"),
            "contractGraphDigest": baseline_graph.digest,
        },
        "current": {"contractGraphDigest": current_graph.digest},
        "evidence": {
            "compatibilityWindowDigest": compatibility_window_digest,
            "storageMigrationPlanDigest": migration_plan_digest,
        },
        "objects": object_reports,
        "issues": issues,
        "invariants": {
            "wireModelVersion": "forbidden",
            "automaticSourceRewrite": False,
            "breakingStorageMigration": "quiesced_atomic",
            "dualRead": "forbidden",
            "dualWrite": "forbidden",
        },
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise InputError(f"cannot write report {path}: {error}") from error
