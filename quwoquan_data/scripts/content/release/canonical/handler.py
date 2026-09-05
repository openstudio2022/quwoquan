"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.producer_release_handoff import (
    ProducerReleaseHandoffError,
    write_producer_release_handoff,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT



def handle_pool_release_build(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_pool import (
        handle_pool_release_build as handle,
    )

    handle(args)


def handle_publish_object(args: argparse.Namespace) -> None:
    from content.release.canonical.publish_object import handle_publish_object as handle

    handle(args)


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



from content.release.canonical.handler_cli import register_parser  # noqa: F401
