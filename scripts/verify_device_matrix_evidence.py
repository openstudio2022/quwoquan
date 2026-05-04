#!/usr/bin/env python3
"""Verify downloaded device-matrix artifacts contain auditable evidence files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--report-glob", action="append", default=[])
    return parser.parse_args()


def resolve_evidence_path(report_file: Path, artifact_root: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    raw = Path(raw_path)
    candidate_paths: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(path: Path) -> None:
        if path not in seen:
            seen.add(path)
            candidate_paths.append(path)

    add_candidate(raw)
    if not raw.is_absolute():
        parts = raw.parts
        if len(parts) >= 2 and parts[0] == "artifacts" and parts[1] == "device-matrix":
            stripped = Path(*parts[2:])
            if str(stripped) not in {"", "."}:
                add_candidate(stripped)

    for path in candidate_paths:
        if path.is_absolute():
            if path.exists():
                return path
            continue
        for base in [report_file.parent, *report_file.parents]:
            try:
                base.relative_to(artifact_root)
            except ValueError:
                continue
            candidate = base / path
            if candidate.exists():
                return candidate
        candidate = artifact_root / path
        if candidate.exists():
            return candidate
    return None


def expect_path(
    errors: list[str],
    report_file: Path,
    artifact_root: Path,
    raw_path: str,
    *,
    label: str,
    required: bool,
) -> None:
    if not raw_path:
        if required:
            errors.append(f"{report_file}: missing {label}")
        return
    if resolve_evidence_path(report_file, artifact_root, raw_path) is None:
        errors.append(f"{report_file}: {label} not found -> {raw_path}")


def validate_screenshot(
    errors: list[str],
    report_file: Path,
    artifact_root: Path,
    name: str,
    payload: Any,
) -> None:
    if not isinstance(payload, dict):
        errors.append(f"{report_file}: {name} must be an object")
        return
    status = str(payload.get("status", "")).strip()
    if not status:
        errors.append(f"{report_file}: {name}.status missing")
        return
    if status == "captured":
        expect_path(
            errors,
            report_file,
            artifact_root,
            str(payload.get("path", "")),
            label=f"{name}.path",
            required=True,
        )


def validate_report(report_file: Path, artifact_root: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    devices = payload.get("devices") or []
    if not devices:
        errors.append(f"{report_file}: devices is empty")
    expect_path(
        errors,
        report_file,
        artifact_root,
        str(payload.get("deviceInventoryPath", "")),
        label="deviceInventoryPath",
        required=True,
    )
    runs = payload.get("runs") or []
    if not runs:
        errors.append(f"{report_file}: runs is empty")
    for index, run in enumerate(runs, start=1):
        evidence = run.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{report_file}: run[{index}] missing evidence object")
            continue
        expect_path(
            errors,
            report_file,
            artifact_root,
            str(evidence.get("deviceManifestPath", "")),
            label=f"run[{index}].deviceManifestPath",
            required=True,
        )
        if "commandPath" in evidence:
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("commandPath", "")),
                label=f"run[{index}].commandPath",
                required=True,
            )
        if "probeCommandPath" in evidence:
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("probeCommandPath", "")),
                label=f"run[{index}].probeCommandPath",
                required=True,
            )
        if "patrolCommandPath" in evidence and evidence.get("patrolCommandPath"):
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("patrolCommandPath", "")),
                label=f"run[{index}].patrolCommandPath",
                required=False,
            )
        if "rawLogPath" in evidence:
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("rawLogPath", "")),
                label=f"run[{index}].rawLogPath",
                required=True,
            )
        if "probeLogPath" in evidence:
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("probeLogPath", "")),
                label=f"run[{index}].probeLogPath",
                required=True,
            )
        if "patrolLogPath" in evidence and evidence.get("patrolLogPath"):
            expect_path(
                errors,
                report_file,
                artifact_root,
                str(evidence.get("patrolLogPath", "")),
                label=f"run[{index}].patrolLogPath",
                required=False,
            )
        for screenshot_name in ("beforeScreenshot", "afterScreenshot", "failureScreenshot"):
            if screenshot_name in evidence:
                validate_screenshot(
                    errors,
                    report_file,
                    artifact_root,
                    f"run[{index}].{screenshot_name}",
                    evidence.get(screenshot_name),
                )
    return errors


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root)
    report_globs = args.report_glob or ["**/*.json"]
    report_files: list[Path] = []
    seen: set[Path] = set()
    for pattern in report_globs:
        for path in artifact_root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                report_files.append(path)
    if not report_files:
        print("no report files matched", file=sys.stderr)
        return 2
    errors: list[str] = []
    for report_file in sorted(report_files):
        errors.extend(validate_report(report_file, artifact_root))
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1
    print(f"validated {len(report_files)} report file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
