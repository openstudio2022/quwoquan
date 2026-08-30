"""Shared create-once evidence primitives for failed campaign reconciliation."""

from __future__ import annotations

import fcntl
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from content.execution.campaign.submission_reconciliation_contract import (
    file_digest,
    reconciliation_receipt_path,
    safe_regular_ref,
)

SCHEMA = "quwoquan_data.campaign_failed_execution_reconciliation_receipt"
_ERROR_CODES = {
    "source_drift": "DATA.CAMPAIGN.FAILED_EXECUTION_SOURCE_DRIFT",
    "controller_interrupted_before_claim": "DATA.CAMPAIGN.CONTROLLER_INTERRUPTED_BEFORE_CLAIM",
    "claimed_execution_source_drift": "DATA.CAMPAIGN.CLAIMED_EXECUTION_SOURCE_DRIFT",
    "post_publish_partial_terminal": "DATA.CAMPAIGN.POST_PUBLISH_PARTIAL_TERMINAL",
    "mixed_finalized_partial_terminal": "DATA.CAMPAIGN.MIXED_FINALIZED_PARTIAL_TERMINAL",
    "terminal_unpublished_source_drift": "DATA.CAMPAIGN.TERMINAL_UNPUBLISHED_SOURCE_DRIFT",
    "terminal_unpublished_retryable_shortfall": "DATA.CAMPAIGN.TERMINAL_UNPUBLISHED_RETRYABLE_SHORTFALL",
}
_SHA256_RE = re.compile(r"^sha256:([a-f0-9]{64})$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock = path.parent / ".lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _file_binding(
    path: Path, *, output_root: Path, label: str
) -> dict[str, str]:
    return {
        "ref": safe_regular_ref(path, output_root=output_root, label=label),
        "sha256": file_digest(path),
    }


def terminal_unpublished_receipt_path(
    root_execution_id: str,
    observed_source_revision: object,
    *,
    output_root: Path,
) -> Path:
    """Return the create-once receipt path for one successor source identity."""

    match = _SHA256_RE.fullmatch(str(observed_source_revision or ""))
    if match is None:
        raise ValueError("terminal unpublished observed sourceRevision is invalid")
    base = reconciliation_receipt_path(
        root_execution_id,
        output_root=output_root,
    )
    return base.parent / "terminal-unpublished-source-drift" / f"{match[1]}.json"


def terminal_unpublished_shortfall_receipt_path(
    root_execution_id: str,
    observed_source_revision: object,
    *,
    output_root: Path,
) -> Path:
    """Return the create-once shortfall receipt path for one source identity."""

    match = _SHA256_RE.fullmatch(str(observed_source_revision or ""))
    if match is None:
        raise ValueError("terminal unpublished observed sourceRevision is invalid")
    base = reconciliation_receipt_path(
        root_execution_id,
        output_root=output_root,
    )
    return (
        base.parent
        / "terminal-unpublished-retryable-shortfall"
        / f"{match[1]}.json"
    )


file_binding = _file_binding

__all__ = [
    "SCHEMA",
    "_ERROR_CODES",
    "_file_binding",
    "_lock",
    "_now",
    "file_binding",
    "terminal_unpublished_receipt_path",
    "terminal_unpublished_shortfall_receipt_path",
]
