"""CLI handler for an explicit immutable release cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.aggregate_release import build_pool_release
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT


def handle_pool_release_build(args: argparse.Namespace) -> None:
    try:
        report = build_pool_release(
            publish_root=Path(args.publish_root or PUBLISH_ROOT).resolve(),
            release_root=Path(args.release_root or OUTPUT_ROOT / "data/releases").resolve(),
            release_id=str(args.release_id),
            cohort_file=Path(args.cohort_file).expanduser().resolve(),
            release_class=str(args.release_class),
        )
    except (FileNotFoundError, OSError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release pool-build] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = ["handle_pool_release_build"]
