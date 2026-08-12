#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = (
    ROOT
    / "quwoquan_app/test/support/service/content_service/content/post/home_showcase_core_fixture.g.dart"
)


def main() -> int:
    if not GENERATED.is_file():
        print("[verify_app_generated_fixture_assets] FAIL")
        print(f"  - generated UI object examples are missing: {GENERATED}")
        return 1
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
    if not json_match:
        issues.append("generated JSON constant is missing")
    if sha_match and json_match:
        embedded_json = json_match.group(1)
        embedded_sha = hashlib.sha256(embedded_json.encode("utf-8")).hexdigest()
        if sha_match.group(1) != embedded_sha:
            issues.append("generated SHA does not match embedded UI object examples")
        try:
            posts = json.loads(embedded_json)
        except json.JSONDecodeError as exc:
            issues.append(f"generated JSON is invalid: {exc}")
        else:
            if not isinstance(posts, list) or len(posts) != 21:
                issues.append("home showcase must contain exactly 21 named UI object examples")
            else:
                post_ids = [item.get("postId") for item in posts if isinstance(item, dict)]
                if len(post_ids) != 21 or len(set(post_ids)) != 21 or any(not item for item in post_ids):
                    issues.append("home showcase postId values must be non-empty and unique")

    if issues:
        print("[verify_app_generated_fixture_assets] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_app_generated_fixture_assets] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
