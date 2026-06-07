"""Gate entry for bundled fonts verification."""

from __future__ import annotations

from pathlib import Path

from fonts.verify import run_verify


def gate_verify(*, manifest_file: Path | None = None, pubspec_file: Path | None = None) -> None:
    run_verify(manifest_file=manifest_file, pubspec_file=pubspec_file)
