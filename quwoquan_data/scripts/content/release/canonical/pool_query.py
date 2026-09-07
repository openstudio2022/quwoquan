"""只读查询 canonical publish 池：哪些对象可进入 release cohort，哪些被排除及原因。

cohort 的选择仍由 AI 决定；本模块只把 finalize 会用到的准入判据（post 候选闭包、
homepage 有效准入、`publish/entity.schema.json` 合规、posts→entities 引用闭合）
一次性算出来，避免 AI 反复试错 finalize。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_selection import (
    discover_explicit_cohort_candidates,
)
from content.release.canonical.content_pool_record import is_pool_record_admitted
from content.release.canonical.effective_admission import (
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from core.schema import validate_result

_CARRIERS = ("homepage", "article", "image", "video")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _post_refs(publish_root: Path) -> list[str]:
    posts = publish_root / "posts"
    if not posts.is_dir():
        return []
    return sorted(
        manifest.parent.relative_to(posts).as_posix()
        for manifest in posts.rglob("manifest.json")
        if "_pool" not in manifest.parts
    )


def _homepages(publish_root: Path) -> tuple[list[str], dict[str, str]]:
    """eligible homepage refs 与 excluded {ref: code}。"""

    entities = publish_root / "entities"
    ok: list[str] = []
    bad: dict[str, str] = {}
    if not entities.is_dir():
        return ok, bad
    for manifest in sorted(entities.rglob("manifest.json")):
        if "_pool" in manifest.parts:
            continue
        root = manifest.parent
        ref = root.relative_to(entities).as_posix()
        entity_path = root / "_entity.json"
        if not entity_path.is_file():
            bad[ref] = "ENTITY_MISSING"
            continue
        # OPEN-021：存量实体不满足 publish entity schema 的显式排除。
        if validate_result(_read_json(entity_path), "publish", "entity"):
            bad[ref] = "ENTITY_SCHEMA_INVALID"
            continue
        try:
            admission = resolve_effective_admission(
                root, object_type="homepage", document=_read_json(manifest)
            )
        except Exception as exc:  # noqa: BLE001 - 排除码来自异常首段
            bad[ref] = str(exc).split(":", 1)[0].strip() or "ADMISSION_INVALID"
            continue
        if not is_pool_record_admitted(admission.record):
            bad[ref] = "NOT_ADMITTED"
        elif not effective_source_attribution_ready(admission):
            bad[ref] = "SOURCE_ATTRIBUTION_INCOMPLETE"
        else:
            ok.append(ref)
    return sorted(ok), bad


def _illustrated_article_issue(publish_root: Path, post_ref: str) -> str:
    """release admission 要求 illustrated 文章恰有一张封面加至少一张正文图；提前在这里报出。"""

    if not post_ref.startswith("article/"):
        return ""
    manifest = _read_json(publish_root / "posts" / post_ref / "manifest.json")
    if str(manifest.get("publishMediaMode") or "") == "text_only":
        return ""
    assets = [asset for asset in manifest.get("assets") or [] if isinstance(asset, dict)]
    covers = [asset for asset in assets if str(asset.get("role") or "") == "cover"]
    # illustrated 只要求「有图即恰好一张封面」；正文图张数不设下限。
    if len(covers) != 1:
        return f"illustrated article has {len(covers)} cover assets (needs exactly 1 cover)"
    return ""


def _entity_refs_of(publish_root: Path, post_ref: str) -> list[str]:
    manifest = _read_json(publish_root / "posts" / post_ref / "manifest.json")
    return sorted(
        str(ref).removeprefix("/entity/").strip("/") for ref in manifest.get("entityRefs") or []
    )


def query_pool(publish_root: Path) -> dict[str, Any]:
    homepages, bad_homepages = _homepages(publish_root)
    homepage_set = set(homepages)
    candidates, excluded_posts = discover_explicit_cohort_candidates(
        publish_root=publish_root, post_refs=_post_refs(publish_root)
    )
    eligible_posts: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = [
        {"objectRef": f"posts/{row.post_ref}", "code": str(row.code)} for row in excluded_posts
    ]
    for candidate in candidates:
        illustrated_issue = _illustrated_article_issue(publish_root, candidate.post_ref)
        if illustrated_issue:
            excluded.append(
                {"objectRef": f"posts/{candidate.post_ref}", "code": "ARTICLE_ILLUSTRATED_INCOMPLETE", "detail": illustrated_issue}
            )
            continue
        entity_refs = _entity_refs_of(publish_root, candidate.post_ref)
        missing = [ref for ref in entity_refs if ref not in homepage_set]
        if missing:
            excluded.append(
                {
                    "objectRef": f"posts/{candidate.post_ref}",
                    "code": "REFERENCED_ENTITY_EXCLUDED",
                    "detail": ", ".join(f"{ref}={bad_homepages.get(ref, 'MISSING')}" for ref in missing),
                }
            )
            continue
        eligible_posts.append(
            {
                "objectRef": f"posts/{candidate.post_ref}",
                "carrier": str(candidate.content_type),
                "entityRefs": [f"entities/{ref}" for ref in entity_refs],
            }
        )
    excluded.extend(
        {"objectRef": f"entities/{ref}", "code": code} for ref, code in sorted(bad_homepages.items())
    )
    counts = Counter(str(row["carrier"]) for row in eligible_posts)
    counts["homepage"] = len(homepages)
    return {
        "schema": "quwoquan_data.release_pool_query",
        "publishRoot": publish_root.as_posix(),
        "counts": {carrier: int(counts.get(carrier, 0)) for carrier in _CARRIERS},
        "eligible": {
            "homepages": [f"entities/{ref}" for ref in homepages],
            "posts": eligible_posts,
        },
        "excluded": sorted(excluded, key=lambda row: (row["code"], row["objectRef"])),
    }


__all__ = ["query_pool"]
