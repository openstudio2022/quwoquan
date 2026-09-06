"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.producer_release_handoff import (
    ProducerReleaseHandoffError,
    read_producer_release_handoff,
    write_producer_release_handoff,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT


def handle_publish_object(args: argparse.Namespace) -> None:
    from content.release.canonical.publish_object import handle_publish_object as handle

    handle(args)


def handle_release_finalize(args: argparse.Namespace) -> None:
    """pool-build → release-integrity → create-once handoff，一次完成并固定 producer END。"""

    from content.release.canonical.aggregate_release import build_pool_release
    from content.release.canonical.integrity import scan_release_integrity

    output_root = Path(OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    release_root = Path(args.release_root or output_root / "data/releases").resolve()
    cohort_file = Path(args.cohort_file).expanduser().resolve()
    release_id = str(args.release_id)
    try:
        cohort = json.loads(cohort_file.read_bytes())
        release_class = str(cohort.get("releaseClass") or "research")
        if not (release_root / release_id / "payload/release.json").is_file():
            build_report = build_pool_release(
                publish_root=publish_root,
                release_root=release_root,
                release_id=release_id,
                cohort_file=cohort_file,
                release_class=release_class,
            )
        else:
            build_report = {"status": "replayed", "releaseId": release_id}
        integrity = scan_release_integrity(release_id)
        if not integrity.get("passed"):
            raise ObjectTransactionError(
                "release integrity failed: " + "; ".join(str(issue) for issue in integrity.get("issues") or [])
            )
        document, path, replayed = write_producer_release_handoff(
            release_id=release_id,
            cohort_file=cohort_file,
            milestone=str(args.milestone),
            producer_baseline_revision=str(args.producer_baseline_revision),
            repo_root=Path(REPO_ROOT).resolve(),
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
        )
    except (FileNotFoundError, OSError, ProducerReleaseHandoffError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release finalize] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.release_finalize_result",
        "releaseId": release_id,
        "milestone": str(args.milestone),
        "build": {key: build_report.get(key) for key in ("status", "releaseId", "canonicalMerkle", "counts") if key in build_report},
        "integrity": {"passed": True, "canonicalMerkle": integrity.get("canonicalMerkle")},
        "handoff": {
            "status": "replayed" if replayed else "created",
            "handoffRef": path.relative_to(output_root).as_posix(),
            "handoffDigest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "carrierCounts": document.get("carrierCounts"),
            "producerBaselineRevision": document.get("producerBaselineRevision"),
            "producerContractDigest": document.get("producerContractDigest"),
        },
        "terminal": "END",
    }, ensure_ascii=False, indent=2))


def handle_handoff_verify(args: argparse.Namespace) -> None:
    output_root = Path(OUTPUT_ROOT).resolve()
    release_root = Path(args.release_root or output_root / "data/releases").resolve()
    path = release_root / str(args.release_id) / "producer_release_handoff.json"
    try:
        document = read_producer_release_handoff(
            path,
            repo_root=Path(REPO_ROOT).resolve(),
            output_root=output_root,
            release_root=release_root,
        )
    except (FileNotFoundError, OSError, ProducerReleaseHandoffError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release handoff-verify] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.handoff_verify_result",
        "releaseId": document["releaseId"],
        "milestone": document["milestone"],
        "carrierCounts": document["carrierCounts"],
        "handoffDigest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "passed": True,
    }, ensure_ascii=False, indent=2))


from content.release.canonical.handler_cli import register_parser  # noqa: F401
