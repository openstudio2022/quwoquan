"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.application import rollback_object_transaction
from content.release.canonical.build_lookup_indexes import (
    build_publish_lookup_indexes,
)
from content.release.canonical.publish_object import handle_publish_object  # noqa: F401
from content.release.canonical.handler_pool import handle_pool_release_build  # noqa: F401
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.object_transaction_replay import (
    replay_object_transaction_package,
)
from content.release.canonical.producer_release_handoff import (
    ProducerReleaseHandoffError,
    write_producer_release_handoff,
)
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from content.release.canonical.reset import handle_reset_canonical  # noqa: F401
from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT
from core.release_layout import attestation_root



def handle_producer_release_handoff(args: argparse.Namespace) -> None:
    """Materialize one cycle-free producer handoff after release CLOSE."""
    output_root = Path(OUTPUT_ROOT).resolve()
    release_root = Path(args.release_root or output_root / "data/releases").resolve()
    try:
        document, path, replayed = write_producer_release_handoff(
            release_id=str(args.release_id),
            cohort_file=Path(args.cohort_file).expanduser().resolve(),
            milestone=str(args.milestone),
            producer_baseline_revision=str(args.producer_baseline_revision),
            repo_root=Path(REPO_ROOT).resolve(),
            output_root=output_root,
            publish_root=Path(args.publish_root or PUBLISH_ROOT).resolve(),
            release_root=release_root,
        )
    except (FileNotFoundError, OSError, ProducerReleaseHandoffError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release handoff] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.producer_release_handoff_result",
        "status": "replayed" if replayed else "created",
        "handoffRef": path.relative_to(output_root).as_posix(),
        "handoffDigest": "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        "handoff": document,
    }, ensure_ascii=False, indent=2))

def handle_object_transaction_rollback(args: argparse.Namespace) -> None:
    """Rollback one exact applied canonical object transaction."""

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
    """Replay one reviewed package whose media bodies live in a content library."""

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


from content.release.canonical.handler_cli import register_parser  # noqa: F401
