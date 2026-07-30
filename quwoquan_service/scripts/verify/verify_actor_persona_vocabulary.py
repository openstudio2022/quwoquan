#!/usr/bin/env python3
"""Reject retired actor vocabulary outside generated output."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = (
    "quwoquan_service",
    "quwoquan_app",
    "quwoquan_data",
    "quwoquan_ops",
    "specs",
)
REQUIRED_ANCHORS = (
    "quwoquan_service/services/user-service/contracts/persona_management/persona/fields.yaml",
    "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/user/account_session_contracts.dart",
    "quwoquan_data/schema/content/creator_profile.schema.json",
    "quwoquan_ops/cli/stackctl.py",
    "specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md",
)
TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".dart",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_PARTS = {
    ".dart_tool",
    ".git",
    ".qwq_output",
    ".venv",
    "__pycache__",
    "build",
    "generated",
    "node_modules",
    "Pods",
    "vendor",
}
SKIP_FILES = {
    "contract_graph.lock.json",
    "generated_manifest.json",
}
SKIP_PATHS = {
    "quwoquan_app/lib/core/auth/auth_session_persona_key_migration.dart",
    "quwoquan_app/tool/cloud_codegen/contract_graph.breaking.json",
    "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence/mongo_following_subject_persona_migration.go",
}
IMMUTABLE_MIGRATION_PARTS = ("resources", "migrations")
MINIMUM_SCANNED_FILES = 100

LEGACY_SPLIT_ACTOR = re.compile(
    r"sub"
    + r"account|sub[_-]account|(?<![A-Za-z0-9_])sub[ \t]+accounts?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
LEGACY_ACTIVE_ACTOR = re.compile(
    r"active[\s_-]*sub(?:[\s_-]*(?:account(?:[\s_-]*id)?|id|envelope))?\b",
    re.IGNORECASE,
)


def _should_scan(relative: Path) -> bool:
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    if relative.as_posix() in SKIP_PATHS:
        return False
    parts = relative.parts
    if any(
        parts[index : index + len(IMMUTABLE_MIGRATION_PARTS)]
        == IMMUTABLE_MIGRATION_PARTS
        for index in range(len(parts) - len(IMMUTABLE_MIGRATION_PARTS) + 1)
    ):
        # Applied SQL migrations are append-only history. Canonical vocabulary
        # must be enforced in current contracts/runtime and in the forward
        # migration, never by rewriting historical migration bytes.
        return False
    if relative.name in SKIP_FILES or relative.name.endswith(".g.dart"):
        return False
    return relative.suffix in TEXT_SUFFIXES


def _matches(value: str) -> bool:
    return bool(
        LEGACY_SPLIT_ACTOR.search(value)
        or LEGACY_ACTIVE_ACTOR.search(value)
    )


def _verify_matcher_contract() -> list[str]:
    split = "sub"
    positives = (
        split + "AccountId",
        split + "_account_id",
        split + "-account",
        split + " account",
        split + " accounts",
        "active" + split.title() + "Id",
        "active_" + split + "_id",
    )
    negatives = (
        "personaId",
        "activePersonaId",
        "activeSubTab",
        "activeSubCategory",
        "activeSubscriptions",
    )
    failures = [
        f"matcher contract missed retired vocabulary: {value!r}"
        for value in positives
        if not _matches(value)
    ]
    failures.extend(
        f"matcher contract rejected distinct concept: {value!r}"
        for value in negatives
        if _matches(value)
    )
    scan_cases = {
        Path(
            "quwoquan_app/lib/core/auth/"
            "auth_session_persona_key_migration.dart"
        ): False,
        Path(
            "quwoquan_service/services/user-service/internal/account/"
            "user_account/infrastructure/persistence/"
            "mongo_following_subject_persona_migration.go"
        ): False,
        Path("quwoquan_app/tool/cloud_codegen/contract_graph.breaking.json"): False,
        Path("quwoquan_service/contract_graph.breaking.json"): True,
        Path(
            "quwoquan_service/services/user-service/resources/migrations/"
            "account/user_account/001_user_profiles.up.sql"
        ): False,
        Path("quwoquan_service/services/user-service/current_schema.sql"): True,
    }
    failures.extend(
        f"scan exception contract mismatch: {path.as_posix()}"
        for path, expected in scan_cases.items()
        if _should_scan(path) != expected
    )
    return failures


def main() -> int:
    failures = _verify_matcher_contract()
    scanned: set[str] = set()
    for root_name in SCAN_ROOTS:
        root = REPOSITORY_ROOT / root_name
        if not root.is_dir():
            failures.append(f"missing scan root: {root_name}")
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(REPOSITORY_ROOT)
            if not _should_scan(relative):
                continue
            relative_text = relative.as_posix()
            scanned.add(relative_text)
            if _matches(relative_text):
                failures.append(f"{relative_text}: retired actor vocabulary in path")
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                failures.append(f"{relative_text}: invalid UTF-8: {error}")
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if _matches(line):
                    failures.append(
                        f"{relative_text}:{line_number}: retired actor vocabulary"
                    )

    if len(scanned) < MINIMUM_SCANNED_FILES:
        failures.append(
            f"empty-green guard: scanned {len(scanned)} files, "
            f"require at least {MINIMUM_SCANNED_FILES}"
        )
    for anchor in REQUIRED_ANCHORS:
        if anchor not in scanned:
            failures.append(f"empty-green guard: required anchor not scanned: {anchor}")

    if failures:
        print("[actor-persona-vocabulary] FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"[actor-persona-vocabulary] OK: scanned={len(scanned)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
