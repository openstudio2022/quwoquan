#!/usr/bin/env python3
"""Verify static performance-gate wiring or a release-bound candidate evidence matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nonfunctional_coverage_lib import Failures, ROOT


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_runtime_media_playback_evidence import validate_evidence_document


EVIDENCE_GATE = ROOT / "quwoquan_ops/gate/verify_runtime_media_playback_evidence.py"
ARTIFACT_GATE = ROOT / "quwoquan_ops/gate/runtime_media_playback_artifacts.py"
EVIDENCE_TEST = (
    ROOT
    / "quwoquan_ops/tests/local_contract/media/"
    "test_runtime_media_playback_evidence__local_contract_test.py"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--artifact-root", type=Path, default=ROOT)
    parser.add_argument("--require-candidate", action="store_true")
    return parser.parse_args()


def _verify_static_contract(failures: Failures) -> None:
    for path, label in (
        (EVIDENCE_GATE, "runtime-media playback evidence gate"),
        (ARTIFACT_GATE, "runtime-media artifact validator"),
        (EVIDENCE_TEST, "runtime-media evidence local_contract"),
    ):
        failures.require_path(path, label)
    if not ARTIFACT_GATE.is_file() or not EVIDENCE_TEST.is_file():
        return
    gate = ARTIFACT_GATE.read_text(encoding="utf-8")
    tests = EVIDENCE_TEST.read_text(encoding="utf-8")
    for token in (
        "homepage-content-performance-evidence",
        "samplesFromProductionReporter",
        "worstBuildFrameMs",
        "worstRasterFrameMs",
        "peakResidentMemoryBytes",
        "activeVideoControllerMax",
        "mediaDownloadQueuedMax",
        "iosPerformanceTracePath",
        "iosPerformanceSummaryPath",
    ):
        if token not in gate or token not in tests:
            failures.add(f"structured performance evidence contract missing tested field: {token}")
    if "_homepage_jank_ratio_target" not in gate:
        failures.add("performance evidence gate must read the canonical jank target")


def _verify_candidate(args: argparse.Namespace, failures: Failures) -> None:
    if args.evidence is None:
        if args.require_candidate:
            failures.add("candidate performance evidence is required; pass --evidence")
        return
    evidence_path = args.evidence.expanduser().resolve()
    if not evidence_path.is_file():
        failures.add(f"candidate performance evidence does not exist: {evidence_path}")
        return
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.add(f"candidate performance evidence is not valid JSON: {error}")
        return
    failures.items.extend(
        validate_evidence_document(
            document,
            require_matrix=True,
            check_artifacts=True,
            artifact_root=args.artifact_root.expanduser().resolve(),
        ),
    )


def main() -> int:
    args = _parse_args()
    failures = Failures()
    _verify_static_contract(failures)
    _verify_candidate(args, failures)
    message = (
        "[verify] OK: release-bound candidate performance evidence passed"
        if args.evidence is not None
        else "[verify] OK: performance evidence gate contract checked; no candidate evaluated"
    )
    return failures.exit_code(message)


if __name__ == "__main__":
    raise SystemExit(main())
