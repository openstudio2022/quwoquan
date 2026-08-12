"""Test-only builder for a ready, short-lived semantic preflight receipt."""
from __future__ import annotations

import sys
from pathlib import Path

from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
)
from content.execution.preflight.receipt import (
    build_semantic_preflight_receipt,
    write_semantic_preflight_receipt,
)
from content.execution.preflight.selection import (
    resolve_semantic_preflight_selection,
)
from core.paths import OUTPUT_ROOT


def ready_semantic_preflight(
    semantic_selection_id: str,
    *,
    output_root: Path = OUTPUT_ROOT,
    effective_concurrency: int = 4,
) -> tuple[Path, dict[str, str]]:
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    report = {
        **selection.document(),
        "selectionDigest": selection.selection_digest,
        "fallbackPolicy": "forbidden",
        "prepare": {"ready": True, "python": sys.executable, "missing": []},
        "preflight": {
            "provider": selection.provider.value,
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "network": {"checked": True, "ready": True, "issues": []},
            "ready": True,
            "issues": [],
        },
        "provider": selection.provider.value,
        "semanticAgentCredential": {
            "provider": selection.provider.value,
            "source": "local_contract",
            "present": True,
            "valid": True,
            "issues": [],
        },
        "semanticAgentStartup": {
            "provider": selection.provider.value,
            "checked": True,
            "ready": True,
            "runtime": selection.runtime.value,
            "model": selection.model_selection.model_id,
            "issues": [],
        },
        "capacitySoak": {
            "semanticSelectionId": selection.selection_id,
            "selectionDigest": selection.selection_digest,
            "provider": selection.provider.value,
            "model": selection.model_selection.model_id,
            "modelParameters": selection.model_selection.parameters_document(),
            "runtimeProfileDigest": selection.runtime_profile_digest,
            "ready": True,
            "attempts": max(8, effective_concurrency),
            "successCount": max(8, effective_concurrency),
            "effectiveConcurrency": effective_concurrency,
            "bridgeDisconnectCount": 0,
            "issues": [],
        },
        "workspaceSmoke": {
            "ready": True,
            "workspaceCount": 4,
            "successCount": 4,
            "configuredConcurrency": 4,
            "effectiveConcurrency": 4,
            "cleanupStatus": "cleaned",
            "issues": [],
        },
        "startupRequested": True,
        "soakRequested": True,
        "workspaceSmokeRequested": True,
        "ready": True,
    }
    receipt = build_semantic_preflight_receipt(selection=selection, report=report)
    path = (
        output_root
        / "data/local/cache/semantic-preflight/local-contract"
        / f"{receipt['receiptId'].removeprefix('sha256:')}.json"
    )
    write_semantic_preflight_receipt(path, receipt)
    return path, bind_semantic_preflight_receipt(
        path,
        semantic_selection_id=semantic_selection_id,
        output_root=output_root,
    )


__all__ = ["ready_semantic_preflight"]
