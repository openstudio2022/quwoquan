#!/usr/bin/env python3
"""Validate the single, environment-orthogonal `.qwq_output` layout."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import output_root  # noqa: E402


MANIFEST_PATH = ROOT / "quwoquan_ops" / "environments" / "output_layout_manifest.yaml"
FORBIDDEN_SOURCE_TRUTH_DIRS = frozenset(
    {
        "control_plane",
        "prompts",
        "templates",
        "schema",
        "specs",
        "policies",
        "reference",
    }
)
OPAQUE_DISPOSABLE_CACHE_DIRS = frozenset(
    {
        "cache",
        "dist",
        "node_modules",
        "python-test-deps",
        "site-packages",
        "toolchains",
    }
)
FORBIDDEN_LOCAL_TARGETS = frozenset({"python-envs", "python-test-deps", "toolchains"})
FORBIDDEN_OUTPUT_FILE_NAME = re.compile(
    r"(?i)(?:^\.env(?:\.|$)|(?:^|[._-])(?:config|configuration|secret|credential|certificate|tls|pki)(?:[._-]|$)|caddyfile$|(?:\.pem|\.key|\.crt|\.p12|\.pfx)$)"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|password|token|private[_-]?key|credential)s?\b"
    r"\s*[:=]\s*(\S+)"
)
SAFE_SECRET_REFERENCES = frozenset(
    {
        "runtime_secret:",
        "<redacted>",
        "redacted",
        "missing",
        "not_set",
        "none",
        "null",
    }
)
MAX_INSPECTED_OUTPUT_FILE_BYTES = 1_000_000
INSPECTED_OUTPUT_TEXT_SUFFIXES = frozenset(
    {".conf", ".env", ".ini", ".json", ".log", ".toml", ".txt", ".yaml", ".yml"}
)
EXPECTED_OUTPUT_CONSUMPTION = {
    "same_execution_stage",
    "verification_evidence",
}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def layout_manifest_issues() -> list[str]:
    try:
        manifest = _manifest()
    except (OSError, json.JSONDecodeError) as exc:
        return [f"output layout manifest unreadable: {exc}"]
    if set(manifest) != {"root", "contract", "topLevel"}:
        return ["output layout manifest must contain only root, contract and topLevel"]
    if manifest.get("root") != ".qwq_output":
        return ["output layout manifest root must be .qwq_output"]
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        return ["output layout manifest contract must be an object"]
    if contract.get("disposable") is not True or contract.get("sourceTruthAllowed") is not False:
        return ["output layout manifest must declare disposable output and forbid source truth"]
    if contract.get("deletionInvariant") != "repository_remains_buildable":
        return ["output layout manifest must require repository rebuildability after output deletion"]
    if contract.get("cachePersistenceRequired") is not False:
        return ["output layout manifest must declare that cache persistence is never required"]
    consumption = contract.get("allowedOutputConsumption")
    if not isinstance(consumption, list) or set(consumption) != EXPECTED_OUTPUT_CONSUMPTION:
        return ["output layout manifest has invalid allowed output consumption boundaries"]
    rebuild_sources = contract.get("rebuildSources")
    if not isinstance(rebuild_sources, list) or not rebuild_sources:
        return ["output layout manifest must declare repository rebuild sources"]
    for relative in rebuild_sources:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            return ["output layout rebuild sources must be non-empty repository-relative paths"]
        source = (ROOT / relative).resolve()
        try:
            source.relative_to(ROOT.resolve())
        except ValueError:
            return [f"output layout rebuild source escapes repository: {relative}"]
        if ".qwq_output" in source.parts:
            return [f"output layout rebuild source cannot point into output: {relative}"]
        if not source.exists():
            return [f"output layout rebuild source does not exist: {relative}"]
    top = manifest.get("topLevel")
    if not isinstance(top, dict) or set(top) != {"env", "data"}:
        return ["output layout manifest topLevel must contain exactly env and data"]
    return []


def output_layout_issues(root: Path | None = None) -> list[str]:
    path = Path(root) if root is not None else output_root()
    issues = layout_manifest_issues()
    if not path.exists():
        return issues
    if not path.is_dir():
        return [*issues, f"{_rel(path)}: output root must be a directory"]
    allowed_top = {"env", "data"}
    for entry in sorted(path.iterdir()):
        if entry.name not in allowed_top or not entry.is_dir():
            issues.append(f"{_rel(entry)}: output root only permits env/ and data/")
    env = path / "env"
    if env.is_dir():
        for entry in sorted(env.iterdir()):
            if not entry.is_dir() or entry.name not in {"alpha", "beta", "gamma", "prod", "repo"}:
                issues.append(f"{_rel(entry)}: env only permits alpha/beta/gamma/prod/repo")
                continue
            allowed = {"runs", "observability", "local"}
            for child in sorted(entry.iterdir()):
                if not child.is_dir() or child.name not in allowed:
                    issues.append(f"{_rel(child)}: invalid {entry.name} output category")
            local = entry / "local"
            if local.is_dir():
                for target in sorted(local.iterdir()):
                    if not target.is_dir():
                        issues.append(f"{_rel(target)}: local target must be a directory")
                        continue
                    if target.name in FORBIDDEN_LOCAL_TARGETS:
                        issues.append(
                            f"{_rel(target)}: interpreter caches belong in the external tool cache, "
                            "never under disposable output"
                        )
                        continue
                    for child in sorted(target.iterdir()):
                        if not child.is_dir() or child.name not in {"process", "cache"}:
                            issues.append(
                                f"{_rel(child)}: output local state only permits process/ and cache/; "
                                "configuration, TLS and volumes belong to deployment infrastructure"
                            )
    data = path / "data"
    if data.is_dir():
        for entry in sorted(data.iterdir()):
            if not entry.is_dir() or entry.name not in {"tasks", "releases", "local"}:
                issues.append(f"{_rel(entry)}: data only permits tasks/releases/local")
    issues.extend(output_source_truth_issues(path))
    return issues


def output_source_truth_issues(root: Path) -> list[str]:
    """Reject reusable configuration, certificate and unredacted secret material."""
    issues: list[str] = []
    if not root.is_dir():
        return issues
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        retained: list[str] = []
        for name in dirnames:
            child = current_path / name
            if name in FORBIDDEN_SOURCE_TRUTH_DIRS:
                issues.append(
                    f"{_rel(child)}: reusable source truth is forbidden under disposable output"
                )
                continue
            if name in OPAQUE_DISPOSABLE_CACHE_DIRS:
                continue
            retained.append(name)
        dirnames[:] = retained
        for filename in filenames:
            candidate = current_path / filename
            if FORBIDDEN_OUTPUT_FILE_NAME.search(filename):
                issues.append(
                    f"{_rel(candidate)}: deployment configuration, TLS or secret material "
                    "is forbidden under disposable output"
                )
                continue
            if candidate.suffix.lower() not in INSPECTED_OUTPUT_TEXT_SUFFIXES:
                continue
            try:
                if candidate.stat().st_size > MAX_INSPECTED_OUTPUT_FILE_BYTES:
                    continue
                lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                match = SECRET_ASSIGNMENT.search(line)
                if match is None:
                    continue
                value = match.group(1).strip().strip("\"'")
                normalized = value.lower()
                if (
                    any(normalized.startswith(prefix) for prefix in SAFE_SECRET_REFERENCES)
                    or normalized.startswith("$")
                ):
                    continue
                issues.append(
                    f"{_rel(candidate)}:{line_number}: unredacted secret assignment is forbidden "
                    "under disposable output"
                )
    return issues


def main() -> int:
    issues = output_layout_issues()
    if issues:
        print("[verify_output_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_output_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
