#!/usr/bin/env python3
"""Detect which CI scopes are impacted by the current change set."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALL_SCOPE_PREFIXES = (
    ".github/workflows/",
    "quwoquan_ops/", "quwoquan_app/scripts/", "quwoquan_service/scripts/", "quwoquan_data/scripts/",
)
DATA_PREFIXES = (
    "quwoquan_data/",
    ".cursor/skills/quwoquan-data-content/",
    ".cursor/commands/crawl",
    ".cursor/commands/data-",
)
DATA_DOCUMENT_PREFIXES = ("specs/feature-tree/discovery-content/",)
SERVICE_PREFIXES = (
    "quwoquan_service/",
)
APP_PREFIXES = (
    "quwoquan_app/",
    "quwoquan_app/packages/quwoquan_cloud_contracts/",
)
PORTAL_PREFIXES = (
    "quwoquan_ops/portal/",
)
TOPOLOGY_PREFIXES = (
    "quwoquan_ops/environments/",
)
METADATA_PREFIX = "quwoquan_service/contracts/metadata/"
SERVICE_CONTRACT_PREFIX = "quwoquan_service/services/"
SERVICE_CONTRACT_SEGMENT = "/contracts/"
ROOT_LEVEL_ALL_SCOPE_FILES = {
    "Makefile",
}
DOC_ONLY_PREFIXES = (
    "specs/",
    "docs/",
)
DOC_ONLY_SUFFIXES = {
    ".md",
    ".mdc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
}
FEATURE_SPEC_SCOPE_RULES: tuple[tuple[str, dict[str, bool]], ...] = (
    (
        "specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/",
        {"service": False, "app": True, "portal": False, "topology": False},
    ),
    (
        "specs/feature-tree/runtime/runtime-client-foundation/",
        {"service": False, "app": True, "portal": False, "topology": False},
    ),
    (
        "specs/feature-tree/product-ops-growth/",
        {"service": True, "app": True, "portal": True, "topology": False},
    ),
    (
        "specs/feature-tree/platform-ops-governance/",
        {"service": True, "app": False, "portal": True, "topology": False},
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="HEAD")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Explicit changed file path relative to repo root. Repeatable.",
    )
    parser.add_argument(
        "--github-output",
        default="",
        help="Optional path to write GitHub Actions outputs.",
    )
    return parser.parse_args()


def git_changed_files(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha.strip():
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_doc_only(path: str) -> bool:
    pure = Path(path)
    if path.startswith("specs/feature-tree/") and pure.name in {"spec.md", "design.md"}:
        return False
    return pure.suffix.lower() in DOC_ONLY_SUFFIXES and path.startswith(DOC_ONLY_PREFIXES)


def classify_feature_spec_path(path: str) -> dict[str, bool] | None:
    pure = Path(path)
    if not path.startswith("specs/feature-tree/") or pure.name not in {"spec.md", "design.md"}:
        return None
    for prefix, scope_flags in FEATURE_SPEC_SCOPE_RULES:
        if path.startswith(prefix):
            return scope_flags
    return {"service": True, "app": True, "portal": True, "topology": False}


def classify(paths: list[str]) -> dict[str, bool]:
    impacted = {
        "service": False,
        "app": False,
        "portal": False,
        "topology": False,
        "data": False,
    }
    for raw_path in paths:
        path = raw_path.strip()
        if path.startswith("./"):
            path = path[2:]
        if not path or is_doc_only(path):
            if path.startswith(DATA_DOCUMENT_PREFIXES):
                impacted["data"] = True
            continue
        feature_scope = classify_feature_spec_path(path)
        if feature_scope is not None:
            for key, value in feature_scope.items():
                impacted[key] = impacted[key] or value
            if path.startswith("specs/feature-tree/discovery-content/"):
                impacted["data"] = True
            continue
        if path in ROOT_LEVEL_ALL_SCOPE_FILES:
            impacted["service"] = True
            impacted["app"] = True
            impacted["portal"] = True
            impacted["topology"] = True
            impacted["data"] = True
            continue
        if path.startswith(ALL_SCOPE_PREFIXES):
            impacted["service"] = True
            impacted["app"] = True
            impacted["portal"] = True
            impacted["topology"] = True
            continue
        if path.startswith(METADATA_PREFIX):
            impacted["service"] = True
            impacted["app"] = True
            impacted["portal"] = True
            continue
        if path.startswith(SERVICE_CONTRACT_PREFIX) and SERVICE_CONTRACT_SEGMENT in path:
            impacted["service"] = True
            impacted["app"] = True
            impacted["portal"] = True
            continue
        if path.startswith(TOPOLOGY_PREFIXES):
            impacted["topology"] = True
        if path.startswith(DATA_PREFIXES):
            impacted["data"] = True
            continue
        if path.startswith(SERVICE_PREFIXES):
            impacted["service"] = True
        if path.startswith(APP_PREFIXES):
            impacted["app"] = True
        if path.startswith(PORTAL_PREFIXES):
            impacted["portal"] = True
    return impacted


def write_github_outputs(path: str, impacted: dict[str, bool]) -> None:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in impacted.items()]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        changed_files = [path for path in args.changed_file if path.strip()]
        if not changed_files:
            changed_files = git_changed_files(args.base_sha, args.head_sha)
        if not changed_files:
            impacted = {
                "service": True,
                "app": True,
                "portal": True,
                "topology": True,
                "data": True,
            }
            print(
                "No diff range available; defaulting all scopes to impacted for safety.",
                file=sys.stderr,
            )
        else:
            impacted = classify(changed_files)
    except Exception as exc:  # noqa: BLE001
        print(f"detect_ci_impacted_scopes: FAIL: {exc}", file=sys.stderr)
        return 1

    if args.github_output:
        write_github_outputs(args.github_output, impacted)

    for key, value in impacted.items():
        print(f"{key}={'true' if value else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
