#!/usr/bin/env python3
"""文章契约纯洁性门禁：禁止旧 article 表示与 publishedAt 借壳回潮。

扫描面：
- 生成 Post DTO 的 createdAt 解析不得 fallback 到 publishedAt
- 文章阅读投射不得再消费 articleBlocks / articlePages / articleDocument wire
- ArticleDetailDocumentSource 枚举只允许 markdown / empty
- 云侧 Post 实体不得再声明 articleDocument 字段
- article_post 投影不得再用 body/summary 互相借壳
- mock 发现流 wire 不得把 publishedAt 压扁成 createdAt
"""

from __future__ import annotations

import re
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

POST_DTO_FILES = [
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/article_post_dto.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/photo_post_dto.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/video_post_dto.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/micro_post_dto.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/feed_item_dto.g.dart",
]

CREATED_AT_PUBLISHED_FALLBACK = re.compile(
    r"createdAt:\s*[^\n]*\['publishedAt'\]"
)

READ_PATH_FILES = [
    ROOT / "quwoquan_app/lib/ui/content/content/post_view_projection.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/models/content_post_detail_payload.dart",
    ROOT
    / "quwoquan_service/services/content-service/contracts/content/post/projections/content_post_detail_wire.yaml",
]

FORBIDDEN_READ_WIRE = (
    "articleDocument",
    "articleBlocks",
    "articlePages",
)


def _non_comment_lines(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)

ARTICLE_DETAIL_VIEW = ROOT / "quwoquan_app/lib/ui/content/models/article_detail_view.dart"
POST_FIELDS = (
    ROOT / "quwoquan_service/services/content-service/contracts/content/post/fields.yaml"
)
ARTICLE_POST_PROJECTION = (
    ROOT / "quwoquan_service/services/content-service/contracts/content/post/projections/article_post.yaml"
)
MOCK_DISCOVERY_WIRE_MAP = (
    ROOT / "quwoquan_app/lib/cloud/services/content/feed_item_discovery_wire_map.dart"
)
CONTENT_SCENARIO_FIXTURES = [
    ROOT
    / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json",
    ROOT
    / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.lite.json",
    ROOT
    / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.gamma-curated.json",
]

DEAD_ARTIFACTS = [
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/article_block_wire_keys.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/generated/content/article_card_wire_keys.g.dart",
    ROOT
    / "quwoquan_app/lib/cloud/runtime/generated/content/content_post_detail_article_block_wire_dto.g.dart",
    ROOT
    / "quwoquan_app/lib/cloud/runtime/generated/content/content_post_detail_article_page_wire_dto.g.dart",
    ROOT
    / "quwoquan_app/lib/cloud/runtime/generated/content/content_post_detail_card_wire_dto.g.dart",
    ROOT / "quwoquan_app/lib/cloud/runtime/models/article_document_wire_dto.dart",
    ROOT / "quwoquan_app/lib/ui/content/pages/article_detail_page.dart",
    ROOT / "quwoquan_app/lib/ui/content/pages/photo_detail_page.dart",
    ROOT / "quwoquan_app/lib/ui/content/pages/video_detail_page.dart",
    ROOT
    / "quwoquan_service/services/content-service/contracts/content/post/article_document_schema.yaml",
]


def _field_block(text: str, field_name: str) -> str:
    pattern = re.compile(
        rf"(^\s*-\s+name:\s+{re.escape(field_name)}\s*$)([\s\S]*?)(?=^\s*-\s+name:\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def _article_fixture_posts(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    seed_sets = payload.get("seedSets") or {}
    discovery = seed_sets.get("content_discovery_core") or {}
    posts = discovery.get("posts") or []
    return [
        item
        for item in posts
        if isinstance(item, dict)
        and item.get("postType") == "articlePost"
        and item.get("postId") == "fixture_article_001"
    ]


def main() -> int:
    failures: list[str] = []

    for path in POST_DTO_FILES:
        if not path.exists():
            failures.append(f"missing generated dto: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if CREATED_AT_PUBLISHED_FALLBACK.search(text):
            failures.append(
                f"{path.relative_to(ROOT)}: createdAt must not fallback to publishedAt"
            )

    for path in READ_PATH_FILES:
        if not path.exists():
            continue
        text = _non_comment_lines(path.read_text(encoding="utf-8"))
        for token in FORBIDDEN_READ_WIRE:
            if token in text:
                failures.append(
                    f"{path.relative_to(ROOT)}: forbidden retired wire token {token!r}"
                )

    if ARTICLE_DETAIL_VIEW.exists():
        view = ARTICLE_DETAIL_VIEW.read_text(encoding="utf-8")
        enum_match = re.search(
            r"enum ArticleDetailDocumentSource\s*\{([^}]+)\}",
            view,
            re.MULTILINE,
        )
        if enum_match:
            values = {
                part.strip().split("(")[0].strip()
                for part in enum_match.group(1).split(",")
                if part.strip()
            }
            allowed = {"markdown", "empty"}
            extra = values - allowed
            if extra:
                failures.append(
                    f"{ARTICLE_DETAIL_VIEW.relative_to(ROOT)}: "
                    f"ArticleDetailDocumentSource has retired values {sorted(extra)}"
                )

    if POST_FIELDS.exists():
        fields = POST_FIELDS.read_text(encoding="utf-8")
        if re.search(r"^\s*- name: articleDocument\s*$", fields, re.MULTILINE):
            failures.append(
                f"{POST_FIELDS.relative_to(ROOT)}: articleDocument field must be removed"
            )

    if ARTICLE_POST_PROJECTION.exists():
        projection = ARTICLE_POST_PROJECTION.read_text(encoding="utf-8")
        body_block = _field_block(projection, "body")
        summary_block = _field_block(projection, "summary")
        if re.search(r"aliases:\s*\[[^\]]*\bsummary\b[^\]]*\]", body_block):
            failures.append(
                f"{ARTICLE_POST_PROJECTION.relative_to(ROOT)}: body aliases must not borrow summary"
            )
        if re.search(r"aliases:\s*\[[^\]]*\bbody\b[^\]]*\]", summary_block):
            failures.append(
                f"{ARTICLE_POST_PROJECTION.relative_to(ROOT)}: summary aliases must not borrow body"
            )

    if MOCK_DISCOVERY_WIRE_MAP.exists():
        wire_map = MOCK_DISCOVERY_WIRE_MAP.read_text(encoding="utf-8")
        if (
            "'publishedAt': createdIso" in wire_map
            or "publishedAt ?? createdAt" in wire_map
        ):
            failures.append(
                f"{MOCK_DISCOVERY_WIRE_MAP.relative_to(ROOT)}: publishedAt must not be flattened to createdAt"
            )

    for path in CONTENT_SCENARIO_FIXTURES:
        if not path.exists():
            continue
        fixture_posts = _article_fixture_posts(path)
        if not fixture_posts:
            failures.append(
                f"{path.relative_to(ROOT)}: fixture_article_001 article fixture missing"
            )
            continue
        article = fixture_posts[0]
        if not str(article.get("updatedAt") or "").strip():
            failures.append(
                f"{path.relative_to(ROOT)}: fixture_article_001 must keep explicit updatedAt"
            )
        if not str(article.get("publishedAt") or "").strip():
            failures.append(
                f"{path.relative_to(ROOT)}: fixture_article_001 must keep explicit publishedAt"
            )

    for path in DEAD_ARTIFACTS:
        if path.exists():
            failures.append(
                f"{path.relative_to(ROOT)}: retired article artifact must stay deleted"
            )

    if failures:
        print("FAIL: article contract purity gate")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("OK: article contract purity gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
