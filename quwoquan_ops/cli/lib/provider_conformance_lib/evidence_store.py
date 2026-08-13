"""Provider Conformance 证据文件的发现与加载。"""
from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.output_paths import output_root

from .constants import EVIDENCE_ENVIRONMENTS

def _issue(location: str, message: str) -> str:
    return f"{location}: {message}"


def _output_path(reference: str, *, root: Path) -> Path | None:
    parts = Path(reference).parts
    if not parts or parts[0] != ".qwq_output":
        return None
    candidate = root / Path(*parts[1:])
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def evidence_files(root: Path | None = None) -> list[Path]:
    base = Path(root) if root is not None else output_root()
    files: list[Path] = []
    for environment in EVIDENCE_ENVIRONMENTS:
        run_root = base / "env" / environment / "runs"
        if run_root.is_dir():
            files.extend(sorted(run_root.rglob("provider-conformance-*.evidence.json")))
    return files


def load_evidence_paths(
    paths: Iterable[Path],
    *,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load one caller-owned evidence set without inheriting historical runs."""
    configured_root = Path(root) if root is not None else output_root()
    resolved_root = configured_root.resolve()
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in sorted(Path(item) for item in paths):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            issues.append(
                _issue(
                    path.as_posix(),
                    "evidence path must be a regular file inside QWQ_OUTPUT_ROOT",
                )
            )
            continue
        if path.is_symlink() or not resolved.is_file():
            issues.append(
                _issue(path.as_posix(), "evidence path must be a regular non-symlink file")
            )
            continue
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue(path.as_posix(), f"invalid evidence JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            issues.append(_issue(path.as_posix(), "evidence root must be an object"))
            continue
        payload["_source"] = path
        evidence.append(payload)
    return evidence, issues


def load_evidence(root: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    return load_evidence_paths(evidence_files(root), root=root)
