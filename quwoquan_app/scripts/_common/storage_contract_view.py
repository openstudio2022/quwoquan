"""Fail-closed bridge to the canonical service storage contract view."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _common.paths import REPO_ROOT


_SERVICE_ROOT = REPO_ROOT / "quwoquan_service"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_Runner = Callable[..., subprocess.CompletedProcess[str]]


def load_storage_contract_view(
    storage_path: Path,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    _run: _Runner = subprocess.run,
) -> dict[str, Any]:
    """Decode ``storage.yaml`` through the canonical Go schema bridge.

    The App verifier must not reinterpret storage YAML. Any bridge execution,
    timeout, or JSON-shape failure blocks the caller instead of falling back to
    a second Python decoder.
    """

    command = [
        "go",
        "run",
        "./tools/storage_contract_view",
        "--input",
        str(storage_path.resolve()),
    ]
    try:
        completed = _run(
            command,
            cwd=_SERVICE_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(
            f"storage-contract-view timed out after {timeout_seconds:g}s"
        ) from error
    except OSError as error:
        raise ValueError(f"storage-contract-view could not start: {error}") from error

    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or "no diagnostic"
        raise ValueError(
            "storage-contract-view failed with exit "
            f"{completed.returncode}: {diagnostic}"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("storage-contract-view returned non-JSON output") from error
    if not isinstance(document, dict):
        raise ValueError("storage-contract-view JSON root must be an object")
    return document
