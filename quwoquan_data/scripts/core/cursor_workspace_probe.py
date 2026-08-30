"""Cursor public catalog and isolated-workspace concurrency probes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.cursor_model import CursorModelSelection
from core.cursor_startup_probe import cursor_startup_probe
from core.python_environment import (
    DEFAULT_SEMANTIC_AGENT_MODEL,
    DEFAULT_SEMANTIC_AGENT_RUNTIME,
    REPO_ROOT,
    _redact_secret_text,
    _redact_secret_value,
    resolve_data_agent_python,
)
from core.runtime_policy import active_runtime_policy


def _catalog_selection_support(
    models: list[dict],
    selection: CursorModelSelection | None,
) -> dict:
    """Prove one governed model/parameter binding exists in the account catalog.

    Listing a model id is not enough: a reasoning tier such as ``effort=xhigh``
    only exists on some model versions, so the requested parameters must match a
    declared parameter value and a declared variant combination.
    """
    if selection is None:
        return {"checked": False, "supported": True, "issues": []}
    requested = {parameter.id: parameter.value for parameter in selection.parameters}
    support: dict = {
        "checked": True,
        "supported": False,
        "requestedModel": selection.model_id,
        "requestedParameters": selection.parameters_document(),
        "issues": [],
    }
    entry = next(
        (row for row in models if str(row.get("id") or "") == selection.model_id),
        None,
    )
    if entry is None:
        support["issues"] = [
            f"model {selection.model_id} is absent from the account model catalog"
        ]
        return support
    declared = {
        str(row.get("id") or ""): {str(value) for value in row.get("values") or []}
        for row in entry.get("parameters") or []
        if isinstance(row, Mapping)
    }
    issues: list[str] = []
    for parameter_id, value in requested.items():
        if parameter_id not in declared:
            issues.append(
                f"model {selection.model_id} does not declare parameter {parameter_id}"
            )
        elif value not in declared[parameter_id]:
            issues.append(
                f"model {selection.model_id} parameter {parameter_id} does not offer "
                f"{value}; declared values are {sorted(declared[parameter_id])}"
            )
    variants = [row for row in entry.get("variants") or [] if isinstance(row, list)]
    if not issues and variants:
        matched = any(
            all(
                any(
                    isinstance(pair, Mapping)
                    and str(pair.get("id") or "") == parameter_id
                    and str(pair.get("value") or "") == value
                    for pair in variant
                )
                for parameter_id, value in requested.items()
            )
            for variant in variants
        )
        if not matched:
            issues.append(
                f"model {selection.model_id} does not declare a variant matching "
                f"{selection.parameters_document()}"
            )
    support["issues"] = issues
    support["supported"] = not issues
    return support


def cursor_model_catalog(
    selection: CursorModelSelection | None = None,
) -> dict:
    """Read the account-visible model catalog through the public Cursor facade."""
    try:
        from core.cursor_credentials import (
            cursor_credential_subprocess_env,
            protected_cursor_api_key_fd,
            resolve_cursor_api_key,
        )
    except Exception:  # noqa: BLE001
        from cursor_credentials import (  # type: ignore
            cursor_credential_subprocess_env,
            protected_cursor_api_key_fd,
            resolve_cursor_api_key,
        )
    key = resolve_cursor_api_key()
    if not key:
        return {
            "schema": "quwoquan_data.cursor_model_catalog",
            "checked": False,
            "ready": False,
            "issues": ["credential_not_ready"],
            "modelIds": [],
            "models": [],
            "selectionSupport": {
                "checked": False,
                "supported": False,
                "requestedModel": selection.model_id if selection else None,
                "requestedParameters": (
                    selection.parameters_document() if selection else []
                ),
                "issues": ["credential_not_ready"],
            },
        }
    catalog_python = resolve_data_agent_python(include_current=True) or Path(sys.executable)
    code = r'''
import importlib.metadata
import json
import os
import sys

try:
    from cursor_sdk import Cursor
except Exception as exc:
    print(json.dumps({
        "ready": False,
        "errorClass": type(exc).__name__,
        "error": f"cursor_sdk unavailable: {exc}",
    }, ensure_ascii=False))
    raise SystemExit(0)

credential_fd = int(os.environ.pop("QWQ_CURSOR_API_KEY_FD"))
with os.fdopen(credential_fd, "r", encoding="utf-8", closefd=True) as credential_stream:
    api_key = credential_stream.readline().strip()
try:
    models = Cursor().models.list(api_key=api_key)
    rows = []
    for model in models:
        model_id = str(getattr(model, "id", "") or "").strip()
        if not model_id:
            continue
        rows.append({
            "id": model_id,
            "parameters": [
                {
                    "id": str(getattr(parameter, "id", "") or ""),
                    "values": [
                        str(getattr(value, "value", "") or "")
                        for value in getattr(parameter, "values", ())
                    ],
                }
                for parameter in getattr(model, "parameters", ())
            ],
            "variants": [
                [
                    {
                        "id": str(getattr(pair, "id", "") or ""),
                        "value": str(getattr(pair, "value", "") or ""),
                    }
                    for pair in getattr(variant, "params", ())
                ]
                for variant in getattr(model, "variants", ())
            ],
        })
    print(json.dumps({
        "ready": bool(rows),
        "sdkVersion": importlib.metadata.version("cursor-sdk"),
        "modelIds": sorted({row["id"] for row in rows}),
        "models": rows,
    }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({
        "ready": False,
        "errorClass": type(exc).__name__,
        "error": str(exc),
    }, ensure_ascii=False))
'''
    try:
        with protected_cursor_api_key_fd(key) as credential_fd:
            proc = subprocess.run(
                [str(catalog_python), "-c", code],
                capture_output=True,
                text=True,
                check=False,
                timeout=max(
                    30,
                    active_runtime_policy().preflight_network_timeout_seconds * 3,
                ),
                env=cursor_credential_subprocess_env(
                    os.environ, credential_fd=credential_fd
                ),
                stdin=subprocess.DEVNULL,
                pass_fds=(credential_fd,),
                cwd=REPO_ROOT,
            )
        payload = json.loads((proc.stdout or "{}").strip() or "{}")
        if not isinstance(payload, dict):
            raise TypeError("Cursor model catalog returned a non-object payload")
        model_ids = [
            str(model_id)
            for model_id in payload.get("modelIds") or []
            if str(model_id)
        ]
        models = [row for row in payload.get("models") or [] if isinstance(row, Mapping)]
        support = _catalog_selection_support([dict(row) for row in models], selection)
        ready = bool(
            proc.returncode == 0
            and payload.get("ready")
            and model_ids
            and support["supported"]
        )
        error = _redact_secret_text(
            str(payload.get("error") or proc.stderr or ""),
            secrets=(key,),
        )
        issues = list(support["issues"])
        if not ready and not issues:
            issues = [error or "Cursor account model catalog request failed"]
        return {
            "schema": "quwoquan_data.cursor_model_catalog",
            "checked": True,
            "ready": ready,
            "sdkVersion": str(payload.get("sdkVersion") or ""),
            "modelCount": len(model_ids),
            "modelIds": model_ids,
            "models": models,
            "selectionSupport": support,
            "autoSelection": {
                "requestedId": "auto",
                "literalCatalogEntry": "auto" in model_ids,
                "providerDefaultEntry": "default" in model_ids,
            },
            "errorClass": payload.get("errorClass"),
            "error": error or None,
            "issues": issues,
        }
    except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {
            "schema": "quwoquan_data.cursor_model_catalog",
            "checked": True,
            "ready": False,
            "sdkVersion": "",
            "modelCount": 0,
            "modelIds": [],
            "models": [],
            "selectionSupport": {
                "checked": False,
                "supported": False,
                "requestedModel": selection.model_id if selection else None,
                "requestedParameters": (
                    selection.parameters_document() if selection else []
                ),
                "issues": ["Cursor account model catalog request failed"],
            },
            "errorClass": type(exc).__name__,
            "error": _redact_secret_text(str(exc), secrets=(key,)),
            "issues": ["Cursor account model catalog request failed"],
        }


def cursor_workspace_probe_suite(
    *,
    workspaces: Sequence[Path],
    model: str | CursorModelSelection = DEFAULT_SEMANTIC_AGENT_MODEL,
    runtime: str = DEFAULT_SEMANTIC_AGENT_RUNTIME,
    timeout_seconds: float | None = None,
) -> dict:
    """Prove that isolated campaign workspaces can start Cursor runs together."""
    resolved = tuple(Path(workspace).resolve() for workspace in workspaces)
    if not resolved:
        raise ValueError("Cursor workspace smoke requires at least one workspace")
    if len(set(resolved)) != len(resolved):
        raise ValueError("Cursor workspace smoke paths must be unique")
    missing = [workspace.as_posix() for workspace in resolved if not workspace.is_dir()]
    if missing:
        raise ValueError(f"Cursor workspace smoke paths are missing: {missing}")

    policy = active_runtime_policy()
    selection = CursorModelSelection.from_value(model)
    # workspaces 已经是调用方选择后的 exact workload；全部尝试启动，结果仅作
    # 观测，不用静态 campaign worker 配置制造本机容量结论。
    worker_limit = len(resolved)
    effective_timeout_seconds = float(
        timeout_seconds
        if timeout_seconds is not None
        else policy.startup_timeout_seconds
    )
    active_workers = 0
    maximum_active_workers = 0
    active_lock = threading.Lock()
    suite_started = time.monotonic()

    def run_probe(index: int, workspace: Path) -> dict:
        nonlocal active_workers, maximum_active_workers
        with active_lock:
            active_workers += 1
            maximum_active_workers = max(maximum_active_workers, active_workers)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        started = time.monotonic()
        try:
            payload = cursor_startup_probe(
                model=selection,
                runtime=runtime,
                timeout_seconds=effective_timeout_seconds,
                cwd=workspace,
            )
        except Exception as exc:  # noqa: BLE001 - external SDK boundary
            payload = {
                "ready": False,
                "status": "error",
                "errorClass": type(exc).__name__,
                "error": _redact_secret_text(str(exc)),
            }
        finally:
            with active_lock:
                active_workers -= 1
        return {
            "lane": index,
            "workspace": workspace.name,
            "startedAt": started_at,
            "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsedSeconds": round(time.monotonic() - started, 4),
            "ready": bool(payload.get("ready")),
            "status": payload.get("status"),
            "agentId": payload.get("agentId"),
            "runId": payload.get("runId"),
            "sdkVersion": payload.get("sdkVersion"),
            "errorClass": _redact_secret_value(payload.get("errorClass")),
            "errorCode": payload.get("errorCode"),
        }

    with ThreadPoolExecutor(max_workers=worker_limit) as executor:
        futures = [
            executor.submit(run_probe, index, workspace)
            for index, workspace in enumerate(resolved, start=1)
        ]
        rows = [future.result() for future in as_completed(futures)]
    rows.sort(key=lambda row: int(row["lane"]))

    ready_rows = [row for row in rows if row["ready"]]
    agent_ids = [str(row.get("agentId") or "") for row in ready_rows]
    run_ids = [str(row.get("runId") or "") for row in ready_rows]
    issues: list[str] = []
    if len(ready_rows) != len(rows):
        issues.append(
            "Cursor workspace smoke requires every lane ready: "
            f"{len(ready_rows)}/{len(rows)}"
        )
    if maximum_active_workers < worker_limit:
        issues.append(
            "Cursor workspace smoke did not realize requested parallelism: "
            f"{maximum_active_workers}<{worker_limit}"
        )
    if any(not value for value in (*agent_ids, *run_ids)):
        issues.append("Cursor workspace smoke returned an empty agentId/runId")
    if len(set(agent_ids)) != len(agent_ids):
        issues.append("Cursor workspace smoke agentId values must be lane-unique")
    if len(set(run_ids)) != len(run_ids):
        issues.append("Cursor workspace smoke runId values must be lane-unique")
    return {
        "schema": "quwoquan_data.cursor_workspace_probe_suite",
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "runtime": runtime,
        "workspaceCount": len(resolved),
        "configuredConcurrency": worker_limit,
        "effectiveConcurrency": maximum_active_workers,
        "successCount": len(ready_rows),
        "elapsedSeconds": round(time.monotonic() - suite_started, 4),
        "ready": not issues,
        "issues": issues,
        "runs": rows,
    }
