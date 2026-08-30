"""Reset the disposable canonical publish tree after an empty full-sync baseline."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, RELEASE_ROOT
from core.release_layout import payload_file
from content.release.canonical.canonical_inventory import canonical_inventory_path
from content.release.canonical.object_transaction_contract import (
    ALLOWED_CANONICAL_ROOTS,
    _safe_id,
)
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.release_operation_lock import (
    release_operation_guard,
    release_operation_lock_root,
)
from content.release.model import ReleaseKind
from verify.verify_no_active_data_runtime import active_runtime_processes


def _empty_baseline_is_applied(
    *,
    output_root: Path,
    release_id: str,
    environments: Iterable[str],
) -> bool:
    for environment in environments:
        evidence_root = (
            output_root
            / "env"
            / environment
            / "runs"
            / "data-release"
            / release_id
        )
        receipts = tuple(evidence_root.glob("*/applied_ref.json"))
        if not any(
            isinstance(payload := read_json(receipt), dict)
            and payload.get("releaseId") == release_id
            for receipt in receipts
        ):
            return False
    return True


def reset_canonical_publish(
    *,
    empty_baseline_release: str,
    environments: tuple[str, ...],
    publish_root: Path = PUBLISH_ROOT,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[str, ...]:
    """Clear only canonical output after the named empty baseline is applied.

    Canonical objects are final data output, not reusable configuration.  The
    baseline receipt precondition prevents an operator from deleting objects
    still represented in a target environment, while the publish lock serializes
    reset against the next promotion transaction.

    The inventory sidecar is a derived index of exactly this tree, and every
    other writer mutates the two together inside the same fence.  Reset is the
    only sanctioned out-of-band tree mutation, so it must drop the index in the
    same fenced step; otherwise the next promotion would read entries for files
    the reset deleted and fail with an inventory CAS drift.
    """

    release_id = _safe_id(empty_baseline_release, label="emptyBaselineRelease")
    if not environments or any(not environment for environment in environments):
        raise ValueError("at least one target environment is required")
    if active_runtime_processes():
        raise RuntimeError("GATE_BLOCK active task execute owns canonical publish")

    with release_operation_guard(
        lock_root=release_operation_lock_root(release_root),
        global_exclusive=True,
    ):
        release = release_root / release_id
        header = read_json(payload_file(release, "release.json"))
        desired_state = read_json(payload_file(release, "desired_state.json"))
        if header.get("releaseKind") != ReleaseKind.EMPTY_BASELINE:
            raise ValueError("emptyBaselineRelease must be an immutable empty baseline")
        desired_refs = desired_state.get("desiredRefs")
        if desired_refs != {"creators": [], "entities": [], "posts": [], "tags": []}:
            raise ValueError("emptyBaselineRelease desired state must be empty")
        if not _empty_baseline_is_applied(
            output_root=output_root,
            release_id=release_id,
            environments=environments,
        ):
            raise RuntimeError("GATE_BLOCK empty baseline is not applied in every requested environment")

        publish_root.mkdir(parents=True, exist_ok=True)
        with canonical_publish_lock(publish_root):
            unknown_roots = sorted(
                entry.name
                for entry in publish_root.iterdir()
                if entry.name not in ALLOWED_CANONICAL_ROOTS
            )
            if unknown_roots:
                raise ValueError(
                    "canonical publish contains unknown roots; refusing destructive reset: "
                    + ", ".join(unknown_roots)
                )
            removed_roots = tuple(
                root_name
                for root_name in sorted(ALLOWED_CANONICAL_ROOTS)
                if (publish_root / root_name).exists()
            )
            for root_name in removed_roots:
                shutil.rmtree(publish_root / root_name)
            inventory_path = canonical_inventory_path(publish_root)
            inventory_path.unlink(missing_ok=True)
            inventory_path.with_name(f"{inventory_path.name}-journal").unlink(
                missing_ok=True
            )
    return removed_roots


def handle_reset_canonical(args: argparse.Namespace) -> None:
    environments = tuple(
        item.strip() for item in str(args.env).split(",") if item.strip()
    )
    try:
        removed = reset_canonical_publish(
            empty_baseline_release=str(args.empty_baseline_release),
            environments=environments,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[release reset-canonical] GATE_BLOCK {exc}") from exc
    print(
        "[release reset-canonical] removed roots="
        + (", ".join(removed) if removed else "none")
    )


__all__ = ["reset_canonical_publish"]
