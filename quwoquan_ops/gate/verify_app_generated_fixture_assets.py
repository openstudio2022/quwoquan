#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.lite.json"
)
GENERATED = (
    ROOT
    / "quwoquan_app/test/support/service/content_service/content/post/home_showcase_core_fixture.g.dart"
)


def _render_generated(posts_json: str, sha: str) -> str:
    return (
        "// GENERATED CODE - DO NOT MODIFY BY HAND.\n"
        "// Source: quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.lite.json\n"
        "// Seed set: home_showcase_core.posts\n\n"
        f"const String kHomeShowcaseCorePostsSha256 = '{sha}';\n\n"
        f"const String kHomeShowcaseCorePostsJson = r'''{posts_json}''';\n"
    )


def main() -> int:
    source_doc = json.loads(SOURCE.read_text(encoding="utf-8"))
    posts = source_doc["seedSets"]["home_showcase_core"]["posts"]
    expected_json = json.dumps(posts, ensure_ascii=False, separators=(",", ":"))
    expected_sha = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()

    if "--regenerate" in sys.argv[1:]:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(
            _render_generated(expected_json, expected_sha),
            encoding="utf-8",
        )
        print(f"[verify_app_generated_fixture_assets] regenerated {GENERATED}")
        return 0

    generated_text = GENERATED.read_text(encoding="utf-8")
    sha_match = re.search(
        r"const\s+String\s+kHomeShowcaseCorePostsSha256\s*=\s*"
        r"'([0-9a-f]{64})';",
        generated_text,
        flags=re.S,
    )
    json_match = re.search(
        r"const\s+String\s+kHomeShowcaseCorePostsJson\s*=\s*r'''(.*)''';",
        generated_text,
        flags=re.S,
    )
    issues: list[str] = []
    if not sha_match:
        issues.append("generated SHA constant is missing")
    elif sha_match.group(1) != expected_sha:
        issues.append("generated SHA does not match content_scenarios.lite home_showcase_core.posts")
    if not json_match:
        issues.append("generated JSON constant is missing")
    elif json_match.group(1) != expected_json:
        issues.append("generated JSON does not match content_scenarios.lite home_showcase_core.posts")

    if issues:
        print("[verify_app_generated_fixture_assets] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        print(
            "Regenerate with: python3 quwoquan_ops/gate/verify_app_generated_fixture_assets.py --regenerate"
        )
        return 1
    print("[verify_app_generated_fixture_assets] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
