#!/usr/bin/env python3
"""Fail when retired terminology appears in repository text files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".dart_tool",
    "build",
    "node_modules",
    ".idea",
    ".vscode",
    ".venv",
}

TEXT_SUFFIXES = {
    ".arb",
    ".dart",
    ".go",
    ".gradle",
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".mdc",
    ".mjs",
    ".properties",
    ".py",
    ".rb",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_NAMES = {
    "Makefile",
    "Podfile",
}

TERMS = (
    "".join(("leg", "acy")),
    "".join(("Leg", "acy")),
    "".join(("LEG", "ACY")),
    chr(0x9057) + chr(0x7559),
    chr(0x65E7) + chr(0x7248),
    chr(0x5386) + chr(0x53F2),
)

ALLOWLIST_PREFIXES = {
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/",
}

ALLOWLIST_PATHS = {
    "deploy/shared/media_slice_registry.json",
    "deploy/shared/process_domain_mapping_runbook.md",
    "quwoquan_app/lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart",
    "quwoquan_service/contracts/metadata/messages/conversation/fields.yaml",
    "quwoquan_service/contracts/metadata/messages/conversation/service.yaml",
    "quwoquan_service/runtime/media/slice_object_key.go",
    "quwoquan_service/runtime/media/slice_object_key_test.go",
    "quwoquan_service/services/chat-service/internal/application/conversation_kind.go",
    "quwoquan_service/services/chat-service/internal/application/group_avatar_support_test.go",
    "quwoquan_service/services/user-service/tests/auth_contract_test.go",
    "quwoquan_service/services/user-service/tests/helpers_test.go",
    "quwoquan_service/services/user-service/tests/invite_contract_test.go",
    "quwoquan_service/services/user-service/tests/profile_subject_view_contract_test.go",
    "quwoquan_service/specs/runtime/media/04-object-key-and-url-spec.md",
    "scripts/media_slice_registry.py",
    "scripts/shared_pool_real_asset_pipeline.py",
    "scripts/verify_avatar_user_pool_consistency.py",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/design.md",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md",
}


def is_scannable(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.is_file() and (
        path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES
    )


def is_allowlisted(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in ALLOWLIST_PATHS:
        return True
    return any(rel.startswith(prefix) for prefix in ALLOWLIST_PREFIXES)


def main() -> int:
    violations: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not is_scannable(path):
            continue
        if is_allowlisted(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lower = text.lower()
        if any(term.lower() in lower for term in TERMS):
            violations.append(path.relative_to(ROOT).as_posix())

    if violations:
        print("verify_retired_terms_zero: FAIL")
        for rel in violations:
            print(f"  - {rel}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
