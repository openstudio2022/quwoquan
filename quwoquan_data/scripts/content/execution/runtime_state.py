"""Execution 级运行状态与共享来源投影。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.paths import execution_runtime_state_path, execution_source_catalog_path, normalize_execution_workspace_command
from core.asset_sequence import allocate_execution_sequence
from core.source_catalog import load_source_catalog
from content.execution.contracts import ExecutionRuntimeState

RUNTIME_STATE_SCHEMA = "quwoquan_data.execution_runtime_state"
SOURCE_CATALOG_SCHEMA = "quwoquan_data.execution_source_catalog"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_execution_runtime_state(execution_id: str) -> ExecutionRuntimeState | None:
    path = execution_runtime_state_path(execution_id)
    if not path.is_file():
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"execution runtime state must be an object: {path}")
    _assert_manifest_contract(data)
    return ExecutionRuntimeState.from_mapping(data)


def _coerce_execution_sequence(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def write_execution_runtime_state(
    execution_id: str,
    *,
    command: str = "",
) -> Path:
    """Write mutable process state without duplicating execution identity."""
    from content.execution.workspace import load_execution_manifest

    identity = load_execution_manifest(execution_id)
    path = execution_runtime_state_path(execution_id)
    now = _now_iso()
    current = load_execution_runtime_state(execution_id)
    if current is None:
        manifest = {
            "schema": RUNTIME_STATE_SCHEMA,
            "executionId": execution_id,
            "targetSetSha256": str(identity["targetSetSha256"]),
            "commandChain": [],
            "createdAt": now,
            "executionSequence": allocate_execution_sequence(),
        }
    else:
        manifest = current.to_dict()
        seq = _coerce_execution_sequence(manifest.get("executionSequence"))
        if seq > 0:
            manifest["executionSequence"] = seq
        else:
            manifest["executionSequence"] = allocate_execution_sequence()
        if manifest.get("targetSetSha256") != identity.get("targetSetSha256"):
            raise ValueError("runtime state target set digest drift")
    if command:
        workspace_command = normalize_execution_workspace_command(command)
        chain = manifest.setdefault("commandChain", [])
        if workspace_command not in chain:
            chain.append(workspace_command)
    manifest["updatedAt"] = now
    _assert_manifest_contract(manifest)
    write_json(path, manifest)
    return path


def _assert_manifest_contract(manifest: Mapping[str, Any]) -> None:
    from core.schema import assert_valid

    assert_valid(dict(manifest), "execution", "runtime_state", label=f"runtime_state:{manifest.get('executionId', '')}")


def write_source_catalog(execution_id: str) -> Path:
    """把 committed 受控来源类目投影到执行 `_shared`（只读引用，不另维护第二套清单）。"""
    path = execution_source_catalog_path(execution_id)
    catalog = load_source_catalog()
    kinds: list[dict[str, str]] = []
    for category in catalog.get("categories") or []:
        if not isinstance(category, Mapping):
            continue
        cid = str(category.get("id") or "").strip()
        if not cid:
            continue
        kinds.append(
            {
                "kind": cid,
                "label": str(category.get("label") or category.get("name") or cid),
                "note": str(category.get("note") or ""),
            }
        )
    write_json(
        path,
        {
            "schema": SOURCE_CATALOG_SCHEMA,
            "source": "control_plane/_shared/catalogs/source_catalog.yaml",
            "sourceKinds": kinds,
        },
    )
    return path
