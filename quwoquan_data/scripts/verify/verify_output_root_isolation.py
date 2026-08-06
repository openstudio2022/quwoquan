"""Fail closed on Data output ownership and the single output-root contract."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import (  # noqa: F401 -- RELEASE_ROOT is a public gate seam for tests.
    DATA_EXECUTIONS_ROOT,
    DATA_LOCAL_ROOT,
    RELEASE_ROOT,
    REPO_ROOT,
)
from governance.protected_quarantine_evidence import (
    load_protected_quarantine_receipts,
)

_TRACKED_FORBIDDEN = (
    "quwoquan_data/runtime",
    "quwoquan_data/release",
    ".qwq_output",
    ".qwq_sandbox",
    ".qwq_state",
    "artifacts",
)
_RETIRED_ROOTS = (
    "quwoquan_data/.qwq_output",
    "quwoquan_data/runtime",
    "quwoquan_data/release",
    "quwoquan_data/control_plane/tasks",
    "quwoquan_data/sop",
    "quwoquan_data/docs",
    "quwoquan_data/deploy",
    "runtime/tasks",
    "runtime/batches",
    "data/runs",
    "content_runs",
    "artifacts",
)
_LEGACY_MARKERS = frozenset({"LEGACY_READONLY.md", "legacy_index.json", "migration_manifest.json"})
_OUTPUT_CHILDREN = frozenset({"tasks", "releases", "local"})
_LOCAL_CHILDREN = frozenset({"cache", "workspace"})
_FORBIDDEN_SOURCE_TRUTH_DIRS = frozenset(
    {"control_plane", "prompts", "templates", "schema", "specs", "policies", "reference"}
)


def _tracked_issues(repo_root: Path = REPO_ROOT) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *_TRACKED_FORBIDDEN],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"git ls-files failed: {exc}"]
    return [
        f"{path}: generated output or retired root must not be version controlled"
        for path in result.stdout.splitlines()
        if path.strip()
    ]


def _retired_root_issues(repo_root: Path = REPO_ROOT) -> list[str]:
    return [f"{rel}: retired; delete it and rerun from .qwq_output/data" for rel in _RETIRED_ROOTS if (repo_root / rel).exists()]


def _legacy_marker_issues(*roots: Path) -> list[str]:
    issues: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.name not in _LEGACY_MARKERS:
                continue
            try:
                rendered = str(path.relative_to(REPO_ROOT))
            except ValueError:
                rendered = str(path)
            issues.append(f"{rendered}: legacy marker is forbidden")
    return issues


def _output_layout_issues() -> list[str]:
    root = DATA_EXECUTIONS_ROOT.parent
    if not root.exists():
        return []
    issues: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name not in _OUTPUT_CHILDREN:
            issues.append(f"{entry}: data output only allows tasks/, releases/, local/")
    if DATA_LOCAL_ROOT.exists():
        for entry in sorted(DATA_LOCAL_ROOT.iterdir()):
            if entry.name not in _LOCAL_CHILDREN:
                issues.append(f"{entry}: data/local only allows cache/ and workspace/")
    return issues


def _output_source_truth_issues(root: Path | None = None) -> list[str]:
    """Data output may contain rendered evidence, never reusable source truth."""
    output = (root or DATA_EXECUTIONS_ROOT.parent).expanduser().resolve()
    if not output.is_dir():
        return []
    protected, receipt_issues = load_protected_quarantine_receipts(
        data_output_root=output
    )
    issues: list[str] = [
        f"{output}: invalid protected quarantine evidence: {issue}"
        for issue in receipt_issues
    ]
    for current, dirnames, _filenames in os.walk(output):
        current_path = Path(current)
        retained: list[str] = []
        for name in dirnames:
            child = current_path / name
            if name in _FORBIDDEN_SOURCE_TRUTH_DIRS:
                if any(
                    child == quarantine_root or child.is_relative_to(quarantine_root)
                    for quarantine_root in protected
                ):
                    retained.append(name)
                    continue
                issues.append(
                    f"{child}: reusable source truth is forbidden under disposable data output"
                )
                continue
            if name == "cache":
                continue
            retained.append(name)
        dirnames[:] = retained
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    issues.extend(_tracked_issues())
    issues.extend(_retired_root_issues())
    issues.extend(_legacy_marker_issues(REPO_ROOT / "quwoquan_data", DATA_EXECUTIONS_ROOT.parent))
    issues.extend(_output_layout_issues())
    issues.extend(_output_source_truth_issues())
    return issues


def main() -> int:
    issues = scan_all()
    if issues:
        print("FAIL verify_output_root_isolation:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS verify_output_root_isolation")
    return 0
