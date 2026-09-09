#!/usr/bin/env python3
"""独立发布仓仅允许单 manifest、真实来源、记录与随体媒体。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import PUBLISH_ROOT
from core.publish_repository import canonical_files
from content.release.canonical.object_transaction_audit import validate_publish_invariants
from content.release.canonical.object_transaction_contract import canonical_destination

_RETIRED = {"_entity.json", "asset.refs.json", "creator.refs.json", "tag.refs.json", "source_catalog.json", "rights.json"}
_FORBIDDEN = {"_pool", "rights_snapshots", "draft", "drafts", "prompts", "logs", "receipts", "5.review", "4.draft"}


def publish_structure_issues(publish_root: Path = PUBLISH_ROOT) -> list[str]:
    issues = []
    try:
        paths = canonical_files(publish_root)
        for path in paths:
            relative = path.relative_to(publish_root)
            if path.name in _RETIRED or set(relative.parts) & _FORBIDDEN:
                issues.append(f"DATA.PUBLISH.RETIRED_SIDECAR: {relative}")
            try:
                canonical_destination(relative.as_posix(), label="publish path")
            except RuntimeError as exc:
                issues.append(str(exc))
    except (ValueError, OSError) as exc:
        issues.append(str(exc))
    return issues


def publish_purity_issues(publish_root: Path = PUBLISH_ROOT) -> list[str]:
    issues = publish_structure_issues(publish_root)
    if issues:
        return issues
    for issue in validate_publish_invariants(publish_root)["issues"]:
        issues.append(f"{issue['code']}: {issue['ref']}")
    return issues


def main() -> int:
    issues = publish_purity_issues()
    print("[verify_publish_purity] " + ("FAIL" if issues else "OK"))
    for issue in issues:
        print(f"  - {issue}")
    return int(bool(issues))
