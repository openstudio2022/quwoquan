"""Build fail-closed canonical GC reachability snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.garbage_collection_contract import (
    GC_CANDIDATE_KINDS,
    file_digest,
)
from content.release.canonical.garbage_collection_protection import (
    release_identity_incident_refs,
    reviewed_closure_adoption_protected_refs,
)
from content.release.canonical.garbage_collection_reference_graph import (
    build_reference_graph,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.controller_lease import controller_lease_active
from core.release_layout import payload_file
from core.tree_integrity import tree_integrity_stats


def _execution_state(execution_root: Path) -> str:
    path = execution_root / "_shared/execution_state.json"
    if not path.is_file():
        return "unknown"
    return str(_read_json(path).get("status") or "unknown")


def _execution_manifest(execution_root: Path) -> dict[str, Any]:
    path = execution_root / "execution_manifest.json"
    return _read_json(path) if path.is_file() else {}


def _active_lease(execution_root: Path) -> bool:
    path = execution_root / "_shared/controller_lease.json"
    if not path.is_file():
        return False
    return controller_lease_active(_read_json(path))


def _collect_execution_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"executionId", "sourceTaskId", "retryOf"} and isinstance(
                child, str
            ):
                text = child.strip()
                if text:
                    refs.add(text)
            refs.update(_collect_execution_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_collect_execution_refs(child))
    return refs


def _publish_execution_refs(publish_root: Path) -> set[str]:
    refs: set[str] = set()
    if not publish_root.is_dir():
        return refs
    for path in publish_root.rglob("*.json"):
        if path.is_symlink() or not path.is_file():
            raise ObjectTransactionError(
                f"canonical publish JSON path is invalid: {path}"
            )
        refs.update(_collect_execution_refs(_read_json(path)))
    return refs


def _release_execution_refs(release_root: Path) -> set[str]:
    refs: set[str] = set()
    if not release_root.is_dir():
        return refs
    for release in sorted(path for path in release_root.iterdir() if path.is_dir()):
        header_path = payload_file(release, "release.json")
        if not header_path.is_file():
            raise ObjectTransactionError(
                f"GATE_BLOCK immutable release lacks payload/release.json: {release.name}"
            )
        execution_ids = _read_json(header_path).get("executionIds")
        if not isinstance(execution_ids, list):
            raise ObjectTransactionError(
                f"GATE_BLOCK immutable release executionIds are invalid: {release.name}"
            )
        refs.update(str(item).strip() for item in execution_ids if str(item).strip())
    return refs


def _age_hours(path: Path, *, now: datetime) -> float:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (now - modified).total_seconds() / 3600.0)


def _candidate(
    *,
    output_root: Path,
    path: Path,
    kind: str,
    reason: str,
) -> dict[str, Any]:
    if path.is_symlink() or not path.exists():
        raise ObjectTransactionError(f"GATE_BLOCK DATA.GC.CANDIDATE_INVALID: {path}")
    if path.is_file():
        merkle_root = file_digest(path)
        file_count = 1
        total_bytes = path.stat().st_size
        path_type = "file"
    elif path.is_dir():
        stats = tree_integrity_stats(path)
        merkle_root = stats["merkleRoot"]
        file_count = stats["fileCount"]
        total_bytes = stats["totalBytes"]
        path_type = "directory"
    else:
        raise ObjectTransactionError(f"GATE_BLOCK DATA.GC.CANDIDATE_INVALID: {path}")
    return {
        "kind": kind,
        "ref": path.relative_to(output_root).as_posix(),
        "reason": reason,
        "pathType": path_type,
        "merkleRoot": merkle_root,
        "fileCount": file_count,
        "bytes": total_bytes,
    }


def _artifact_is_protected(
    ref: str,
    protected: dict[str, set[str]],
) -> bool:
    prefix = ref.rstrip("/") + "/"
    return any(
        reasons and (candidate == ref or candidate.startswith(prefix))
        for candidate, reasons in protected.items()
    )


def reachability_snapshot(
    *,
    output_root: Path,
    publish_root: Path,
    release_root: Path,
    min_age_hours: float,
    now: datetime,
) -> dict[str, Any]:
    tasks_root = output_root / "data/tasks"
    transaction_root = output_root / "data/local/workspace/object-transactions"
    tasks = (
        {path.name: path for path in sorted(tasks_root.iterdir()) if path.is_dir()}
        if tasks_root.is_dir()
        else {}
    )
    manifests = {
        execution_id: _execution_manifest(path) for execution_id, path in tasks.items()
    }
    graph = build_reference_graph(
        output_root=output_root,
        publish_root=publish_root,
        release_root=release_root,
        tasks=tasks,
    )
    retry_parent = {
        str(manifest.get("retryOf") or "").strip()
        for manifest in manifests.values()
        if str(manifest.get("retryOf") or "").strip()
    }
    reasons: dict[str, set[str]] = {execution_id: set() for execution_id in tasks}
    for execution_id, execution_root in tasks.items():
        state = _execution_state(execution_root)
        if state != "succeeded":
            reasons[execution_id].add(f"execution_state:{state}")
        if _active_lease(execution_root):
            reasons[execution_id].add("active_controller_lease")
    for execution_id in retry_parent:
        if execution_id in reasons:
            reasons[execution_id].add("retry_ancestor")
    publish_refs = _publish_execution_refs(publish_root)
    release_refs = _release_execution_refs(release_root)
    for execution_id in publish_refs:
        if execution_id in reasons:
            reasons[execution_id].add("canonical_publish_reference")
    for execution_id in release_refs:
        if execution_id in reasons:
            reasons[execution_id].add("immutable_release_reference")
    incident_release_refs, incident_execution_refs = release_identity_incident_refs(
        output_root
    )
    for execution_id in incident_execution_refs:
        if execution_id in reasons:
            reasons[execution_id].add("release_identity_incident")
    adoption_release_refs, adoption_execution_refs = (
        reviewed_closure_adoption_protected_refs(output_root)
    )
    for execution_id in adoption_execution_refs:
        if execution_id in reasons:
            reasons[execution_id].add("reviewed_closure_adoption")
    for execution_id, graph_reasons in graph.protected_execution_reasons.items():
        if execution_id in reasons:
            reasons[execution_id].update(graph_reasons)

    changed = True
    while changed:
        changed = False
        for execution_id, manifest in manifests.items():
            if not reasons[execution_id]:
                continue
            parent = str(manifest.get("retryOf") or "").strip()
            if parent in reasons and "protected_retry_chain" not in reasons[parent]:
                reasons[parent].add("protected_retry_chain")
                changed = True

    candidates: list[dict[str, Any]] = []
    for execution_id, execution_root in tasks.items():
        if reasons[execution_id]:
            continue
        if _age_hours(execution_root, now=now) < min_age_hours:
            reasons[execution_id].add("retention_window")
            continue
        candidates.append(
            _candidate(
                output_root=output_root,
                path=execution_root,
                kind="execution",
                reason="terminal_unreferenced_execution",
            )
        )

    protected_transactions: list[dict[str, str]] = []
    transaction_candidate_refs: set[str] = set()
    if transaction_root.is_dir():
        for path in sorted(
            item for item in transaction_root.iterdir() if item.is_dir()
        ):
            report_path = path / "apply_report.json"
            audit_path = path / "audit_report.json"
            if not report_path.is_file() or not audit_path.is_file():
                protected_transactions.append(
                    {"transactionId": path.name, "reason": "incomplete_transaction"}
                )
                continue
            execution_id = str(_read_json(report_path).get("executionId") or "").strip()
            if reasons.get(execution_id):
                protected_transactions.append(
                    {"transactionId": path.name, "reason": "protected_execution"}
                )
                continue
            if execution_id in tasks and not any(
                row["kind"] == "execution" and row["ref"].endswith(f"/{execution_id}")
                for row in candidates
            ):
                protected_transactions.append(
                    {"transactionId": path.name, "reason": "retained_execution"}
                )
                continue
            if _age_hours(path, now=now) < min_age_hours:
                protected_transactions.append(
                    {"transactionId": path.name, "reason": "retention_window"}
                )
                continue
            candidates.append(
                _candidate(
                    output_root=output_root,
                    path=path,
                    kind="object_transaction",
                    reason="terminal_unreferenced_transaction",
                )
            )
            transaction_candidate_refs.add(path.relative_to(output_root).as_posix())

    if transaction_root.is_dir():
        for path in sorted(
            item for item in transaction_root.iterdir() if item.is_dir()
        ):
            transaction_ref = path.relative_to(output_root).as_posix()
            if transaction_ref in transaction_candidate_refs:
                continue
            staging = path / "staging"
            if not staging.is_dir() or staging.is_symlink():
                continue
            staging_ref = staging.relative_to(output_root).as_posix()
            if _artifact_is_protected(
                staging_ref,
                graph.protected_artifact_reasons,
            ):
                protected_transactions.append(
                    {
                        "transactionId": path.name,
                        "reason": "referenced_staging",
                    }
                )
                continue
            if _age_hours(staging, now=now) < min_age_hours:
                protected_transactions.append(
                    {
                        "transactionId": path.name,
                        "reason": "staging_retention_window",
                    }
                )
                continue
            candidates.append(
                _candidate(
                    output_root=output_root,
                    path=staging,
                    kind="transaction_staging",
                    reason="terminal_unreferenced_staging",
                )
            )

    candidate_refs = {str(row["ref"]) for row in candidates}
    for ref, (path, kind) in sorted(graph.artifacts.items()):
        if (
            kind not in GC_CANDIDATE_KINDS
            or kind in {"execution", "object_transaction", "transaction_staging"}
            or ref in candidate_refs
        ):
            continue
        if _artifact_is_protected(ref, graph.protected_artifact_reasons):
            continue
        if _age_hours(path, now=now) < min_age_hours:
            graph.protected_artifact_reasons[ref].add("retention_window")
            continue
        candidates.append(
            _candidate(
                output_root=output_root,
                path=path,
                kind=kind,
                reason=f"terminal_unreferenced_{kind}",
            )
        )
        candidate_refs.add(ref)

    candidates.sort(key=lambda row: (str(row["kind"]), str(row["ref"])))
    protected_executions = [
        {"executionId": execution_id, "reasons": sorted(values)}
        for execution_id, values in sorted(reasons.items())
        if values
    ]
    return {
        "candidates": candidates,
        "protectedExecutions": protected_executions,
        "protectedTransactions": protected_transactions,
        "releaseExecutionRefs": sorted(release_refs),
        "publishExecutionRefs": sorted(publish_refs),
        "releaseIdentityIncidentReleaseRefs": sorted(incident_release_refs),
        "releaseIdentityIncidentExecutionRefs": sorted(incident_execution_refs),
        "reviewedClosureAdoptionSourceReleaseRefs": sorted(adoption_release_refs),
        "reviewedClosureAdoptionExecutionRefs": sorted(adoption_execution_refs),
        # The terminal state `GWT-007` asks the plan to record: these executions
        # are referenced by evidence that cannot be rewritten, and the tombstone
        # is what lets the plan stay executable instead of failing on them.
        "reclaimedExecutions": [
            {
                "executionId": tombstone.execution_id,
                "reclaimReason": tombstone.reason.value,
                "tombstoneRef": tombstone.ref,
            }
            for _execution_id, tombstone in sorted(
                graph.reclaimed_execution_tombstones.items()
            )
        ],
        "referenceGraph": graph.document(),
    }


__all__ = ["reachability_snapshot"]
