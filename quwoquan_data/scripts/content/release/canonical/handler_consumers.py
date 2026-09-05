"""Lazy handlers for retained downstream/maintenance release commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.application import rollback_object_transaction
from content.release.canonical.build_lookup_indexes import build_publish_lookup_indexes
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.object_transaction_replay import replay_object_transaction_package
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT


def handle_object_transaction_rollback(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        report = rollback_object_transaction(
            publish_root=publish_root,
            output_root=output_root,
            transaction_id=str(args.transaction_id),
        )
    except (FileNotFoundError, OSError, ObjectTransactionError, ValueError) as exc:
        raise SystemExit(
            f"[release object-transaction rollback] GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_object_transaction_replay_package(args: argparse.Namespace) -> None:
    try:
        report = replay_object_transaction_package(
            replay_id=str(args.replay_id),
            source_package_root=Path(args.source_package_root),
            media_library_root=Path(args.media_library_root),
            output_root=Path(args.output_root or OUTPUT_ROOT).resolve(),
            publish_root=Path(args.publish_root or PUBLISH_ROOT).resolve(),
        )
    except (FileNotFoundError, OSError, ObjectTransactionError, ValueError) as exc:
        raise SystemExit(
            f"[release object-transaction replay-package] GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_build_lookup_indexes(args: argparse.Namespace) -> None:
    release_id = str(args.release_id)
    publish_root = Path(args.publish_root or PUBLISH_ROOT)
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    try:
        with (
            release_operation_guard(
                lock_root=release_operation_lock_root(release_root),
                release_ids=(release_id,),
                exclusive_releases=True,
            ),
            canonical_publish_lock(publish_root),
        ):
            report = build_publish_lookup_indexes(
                release_id=release_id,
                canonical_root=publish_root,
                release_root=release_root,
                taxonomy_root=(
                    Path(args.taxonomy_root) if args.taxonomy_root else None
                ),
            )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        ReleaseOperationConflict,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release build-lookups] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = [
    "handle_build_lookup_indexes",
    "handle_object_transaction_replay_package",
    "handle_object_transaction_rollback",
]
