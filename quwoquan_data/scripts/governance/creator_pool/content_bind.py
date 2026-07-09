"""Deterministic creator-content binding via the real match_creator router.

Phase 3 of the no-breakpoint E2E closure needs real content bound to the active travel-photo
creators across the three carriers (article / image / video). The narrative body is
LLM-produced in the live pipeline, but the *authorship binding* — which active
creator authors which carrier — is routed deterministically here through the same
``match_creator`` used in production, and validated by the full
``creator_assignment_issues`` gate (carrier + semantic). The emitted
``creator_content.travel_photo_1k_v1.seed.json`` is the production binding truth source (``previewOnly``
is False), unlike ``content_supply`` round-robin preview samples.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from _common.creator_assignment import creator_assignment_from_profile, creator_assignment_issues
from _common.creator_pool.batch_policy import CANONICAL_BATCH_ID
from _common.creator_pool.io import repo_seed_fixture_dir
from _common.creator_pool.registry_bridge import load_travel_batch_creators
from _common.io import read_json, write_json
from _common.paths import REPO_ROOT, SERVICE_CONTRACTS_METADATA_ROOT, now_iso
from template.creator import carrier_affinity, match_creator
from template.registry import TemplateRegistry

CARRIERS: tuple[str, ...] = ("article", "image", "video")
CONTENT_TYPE_BY_CARRIER = {"article": "article", "image": "image", "video": "video"}
DEFAULT_VERTICAL = "travel"
WORKLOAD_LANES: tuple[str, ...] = ("travel", "photography", "cross")
_LANE_SEGMENT = {
    "travel": "travel_primary",
    "photography": "photography_primary",
    "cross": "travel_photography_cross",
}
_LANE_TAG_PREFIXES = {
    "travel": ("Topic/旅行/",),
    "photography": ("Topic/摄影/",),
    "cross": ("Topic/旅行/", "Topic/摄影/"),
}
_LANE_VERTICAL_BY_CARRIER = {
    "travel": {"article": "travel", "image": "travel", "video": "travel"},
    "photography": {"article": "photography", "image": "photography", "video": "photography"},
    "cross": {"article": "travel", "image": "photography", "video": "travel"},
}
CONTENT_SEED_NAME = "creator_content.travel_photo_1k_v1.seed.json"
_CONTENT_SCENARIOS_DIR = SERVICE_CONTRACTS_METADATA_ROOT / "content" / "test_fixtures" / "scenarios"
CONTENT_SCENARIOS_PATH = _CONTENT_SCENARIOS_DIR / "content_scenarios.json"
# alpha (App mock) + beta (real DB seed) share the full content_scenarios.json. gamma is a
# hash-locked curated showcase (≤100 pinned media, exactly 3 content refs) governed by the
# avatar/curated-bundle gate, so the creator-authored seedSet is intentionally NOT injected
# there; gamma creator-content inclusion is a separate curated-bundle regeneration item.
CONTENT_SCENARIOS_TARGETS = (CONTENT_SCENARIOS_PATH,)
CONTENT_SEED_SET_REF = "creator_authored_core"
# Reuse the committed sample video asset for the video carrier (creators carry only avatar/cover).
SAMPLE_VIDEO_OBJECT_KEY = "media/video/s/archived-video/beta-sample.mp4"
# fixture_ prefix keeps these posts inside the content-service reset namespace.
CONTENT_DOC_PREFIX = "fixture_"
CONTENT_BASE_CREATED_AT = "2026-06-01T08:00:00Z"
PRESET_MANIFEST_PATH = REPO_ROOT / "quwoquan_data" / "publish" / "user_media" / "profile_presets" / "manifest.json"
ENTITY_REF_FIXTURE_MAP = {
    "homepage/topic/travel": "fixture_homepage_travel_photo_west_lake",
    "homepage/topic/photography": "fixture_homepage_travel_gear_sony_a7m4",
    "homepage/tag/Topic_旅行_出行方式_自驾": "fixture_homepage_travel_route_chuanxi",
    "homepage/tag/Topic_旅行_玩法_摄影旅拍": "fixture_homepage_travel_photo_west_lake",
    "homepage/tag/Topic_旅行_玩法_节庆民俗": "fixture_homepage_travel_place_dali_oldtown",
    "homepage/tag/Topic_旅行_旅行主题_美食之旅": "homepage_restaurant_night_market",
    "homepage/tag/Topic_摄影_器材评测": "fixture_homepage_travel_gear_sony_a7m4",
    "homepage/tag/Topic_摄影_摄影教程": "fixture_homepage_travel_gear_lens_35",
    "homepage/tag/Topic_摄影_旅行摄影": "fixture_homepage_travel_photo_west_lake",
}
CIRCLE_REF_FIXTURE_MAP = {
    "circle/topic/travel": "fixture_circle_travel",
    "circle/topic/photography": "fixture_circle_photo",
}


def _registry_for_batch(batch_id: str) -> TemplateRegistry:
    registry = TemplateRegistry.load()
    batch_creators, batch_paths = load_travel_batch_creators(batch_id)
    if not batch_creators:
        return registry
    return replace(
        registry,
        creators={**registry.creators, **batch_creators},
        creator_paths={**registry.creator_paths, **batch_paths},
    )


def _active_batch_creators(registry: TemplateRegistry, batch_id: str) -> list[dict[str, Any]]:
    creators: list[dict[str, Any]] = []
    for creator in registry.creators.values():
        if str(creator.get("status") or "") != "active":
            continue
        if not _app_publish_allowed(creator):
            continue
        cohort = str(creator.get("cohortId") or creator.get("batchId") or "")
        creator_id = str(creator.get("creatorProfileId") or "")
        if cohort == batch_id:
            creators.append(creator)
    return creators


def _app_publish_allowed(creator: dict[str, Any]) -> bool:
    provenance = creator.get("provenance") if isinstance(creator.get("provenance"), dict) else {}
    commercial = provenance.get("commercialReadiness") if isinstance(provenance.get("commercialReadiness"), dict) else {}
    if commercial.get("appPublishAllowed") is False:
        return False
    rights = creator.get("rights") if isinstance(creator.get("rights"), dict) else {}
    if rights.get("appPublishAllowed") is False:
        return False
    return True


def _carrier_lead(creators: list[dict[str, Any]], carrier: str) -> dict[str, Any]:
    """Highest-affinity creator for a carrier (deterministic tie-break by id)."""
    pool = [c for c in creators if carrier_affinity(c, carrier) > 0]
    if not pool:
        pool = list(creators)
    pool.sort(key=lambda c: (-carrier_affinity(c, carrier), str(c.get("creatorProfileId") or "")))
    return pool[0]


def _brief_from_lead(
    lead: dict[str, Any],
    carrier: str,
    *,
    preferred_vertical: str | None = None,
    tag_prefixes: tuple[str, ...] = (),
    require_dual_topic_tags: bool = False,
) -> dict[str, Any]:
    """Build a content brief from a lead creator's own coverage so routing is real."""
    scope = lead.get("coverageScope") if isinstance(lead.get("coverageScope"), dict) else {}
    region_refs = [str(x) for x in (scope.get("regionRefs") or []) if x]
    region = region_refs[0] if region_refs else None
    preferred = [str(x) for x in (lead.get("preferredBlueprintIds") or []) if x]
    template_id = preferred[0] if preferred else ""
    pub_tags = [str(x) for x in (lead.get("publicProfileTagRefs") or []) if x]
    leaf_tags = [t for t in pub_tags if t.count("/") >= 2]
    if require_dual_topic_tags:
        tag_refs: list[str] = []
        for prefix in tag_prefixes:
            match = next((tag for tag in leaf_tags if tag.startswith(prefix)), "")
            if match:
                tag_refs.append(match)
        if len(tag_refs) < 2:
            tag_refs = leaf_tags[:2] or pub_tags[:2]
    else:
        preferred_leafs = [tag for tag in leaf_tags if any(tag.startswith(prefix) for prefix in tag_prefixes)]
        tag_refs = preferred_leafs[:1] or leaf_tags[:1] or pub_tags[:1]
    vertical_refs = [str(ref) for ref in (lead.get("verticalRefs") or [DEFAULT_VERTICAL]) if str(ref).strip()]
    if preferred_vertical and preferred_vertical in vertical_refs:
        content_vertical = preferred_vertical
    else:
        content_vertical = DEFAULT_VERTICAL if DEFAULT_VERTICAL in vertical_refs else vertical_refs[0]
    return {
        "carrier": carrier,
        "templateId": template_id,
        "creatorPersona": {"archetype": str(lead.get("creatorArchetype") or "")},
        "region": region,
        "vertical": content_vertical,
        "tagRefs": tag_refs,
    }


def build_creator_content(
    *,
    registry: TemplateRegistry | None = None,
    batch_id: str = CANONICAL_BATCH_ID,
) -> dict[str, Any]:
    """Route a representative article/image/video subset to active creators.

    Raises ValueError if any binding fails the creator assignment gate so the
    producer can never emit an invalid (wrong-carrier / wrong-coverage) author bind.
    """
    registry = registry or _registry_for_batch(batch_id)
    creators = _active_batch_creators(registry, batch_id)
    expected_posts = len(CARRIERS) * len(WORKLOAD_LANES)
    if len(creators) < expected_posts:
        raise ValueError(f"insufficient active batch creators: {len(creators)} < {expected_posts}")
    if len(creators) < len(CARRIERS):
        raise ValueError(f"insufficient active batch creators: {len(creators)}")
    posts: list[dict[str, Any]] = []
    used_authors: set[str] = set()
    used_creator_ids: set[str] = set()
    content_index = 0
    for lane in WORKLOAD_LANES:
        lane_creators = [
            creator for creator in creators if str(creator.get("verticalSegment") or "") == _LANE_SEGMENT[lane]
        ]
        if len(lane_creators) < len(CARRIERS):
            raise ValueError(f"insufficient {lane} creators for representative workload: {len(lane_creators)}")
        for carrier in CARRIERS:
            content_index += 1
            available_creators = [
                creator
                for creator in lane_creators
                if str(creator.get("creatorProfileId") or "") not in used_creator_ids
            ] or lane_creators
            available_ids = {str(creator.get("creatorProfileId") or "") for creator in available_creators}
            route_registry = replace(
                registry,
                creators={
                    creator_id: registry.creators[creator_id]
                    for creator_id in available_ids
                    if creator_id in registry.creators
                },
                creator_paths={
                    creator_id: path
                    for creator_id, path in registry.creator_paths.items()
                    if creator_id in available_ids
                },
            )
            lead = _carrier_lead(available_creators, carrier)
            brief = _brief_from_lead(
                lead,
                carrier,
                preferred_vertical=_LANE_VERTICAL_BY_CARRIER[lane][carrier],
                tag_prefixes=_LANE_TAG_PREFIXES[lane],
                require_dual_topic_tags=lane == "cross",
            )
            content_id = f"creator_content_{lane}_{carrier}_{content_index:03d}"
            chosen = match_creator(
                route_registry,
                brief,
                carrier=carrier,
                tag_refs=brief["tagRefs"],
                region=brief["region"],
                vertical=brief["vertical"],
                seed=content_id,
            )
            assignment = creator_assignment_from_profile(chosen)
            payload = {
                **assignment,
                "vertical": brief["vertical"],
                "region": brief["region"],
                "tagRefs": brief["tagRefs"],
            }
            issues = creator_assignment_issues(
                payload,
                carrier=carrier,
                content_vertical=brief["vertical"],
                content_region=brief["region"],
                content_tag_refs=brief["tagRefs"],
            )
            if issues:
                raise ValueError(f"{content_id} binding failed assignment gate: {issues}")
            sub_account_id = str(chosen.get("subAccountId") or "")
            author_id = str(chosen.get("authorId") or sub_account_id)
            avatar_key = _profile_media_object_key(chosen, "avatar")
            cover_key = _profile_media_object_key(chosen, "cover")
            display_name = str(chosen.get("displayName") or chosen.get("userHandle") or "")
            relations = chosen.get("relations") if isinstance(chosen.get("relations"), dict) else {}
            entity_refs = [str(ref) for ref in (relations.get("entityAffinityRefs") or []) if str(ref).strip()]
            circle_refs = [str(ref) for ref in (relations.get("circleAffinityRefs") or []) if str(ref).strip()]
            entity_refs = _normalize_fixture_refs(entity_refs, ENTITY_REF_FIXTURE_MAP)
            circle_refs = _normalize_fixture_refs(circle_refs, CIRCLE_REF_FIXTURE_MAP)
            posts.append(
                {
                    "postId": content_id,
                    "contentType": CONTENT_TYPE_BY_CARRIER[carrier],
                    "carrier": carrier,
                    "workloadLane": lane,
                    "authorId": author_id,
                    "subAccountId": sub_account_id,
                    "creatorProfileId": str(chosen.get("creatorProfileId") or ""),
                    "creatorArchetype": str(chosen.get("creatorArchetype") or ""),
                    "displayName": display_name,
                    "authorDisplayName": display_name,
                    "authorAvatarUrl": avatar_key,
                    "authorAvatarObjectKey": avatar_key,
                    "coverUrl": cover_key,
                    "coverObjectKey": cover_key,
                    "title": f"{lane}·{brief['vertical']}·{brief['templateId'] or carrier}",
                    "summary": f"{lane} lane {carrier} 内容（平台虚拟创作者出品）",
                    "tagRefs": brief["tagRefs"],
                    "contentTagRefs": brief["tagRefs"],
                    "entityRefs": entity_refs[:3],
                    "circleRefs": circle_refs[:3],
                    "region": brief["region"],
                    "templateId": brief["templateId"],
                    "vertical": brief["vertical"],
                    "cohortId": batch_id,
                    "routedBy": "match_creator",
                    "bodyMode": "deterministic_stub",
                }
            )
            used_authors.add(author_id)
            used_creator_ids.add(str(chosen.get("creatorProfileId") or ""))

    return {
        "schemaVersion": "creator_pool.content_bind/1",
        "batchId": batch_id,
        "vertical": DEFAULT_VERTICAL,
        "previewOnly": False,
        "routedBy": "match_creator",
        "distinctAuthors": len(used_authors),
        "posts": posts,
        "generatedAt": now_iso(),
    }


def _profile_media_object_key(profile: dict[str, Any], kind: str) -> str:
    legacy_field = "avatarObjectKey" if kind == "avatar" else "backgroundObjectKey"
    legacy_key = str(profile.get(legacy_field) or profile.get("coverObjectKey") or "")
    if legacy_key:
        return legacy_key
    preset_id = str(profile.get("avatarPresetId" if kind == "avatar" else "coverPresetId") or "")
    manifest = _preset_manifest()
    rows = manifest.get("avatars" if kind == "avatar" else "covers") or []
    for row in rows:
        if str(row.get("presetId") or "") == preset_id:
            return str(row.get("objectKey") or "")
    return ""


def _normalize_fixture_refs(refs: list[str], mapping: dict[str, str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        target = mapping.get(ref, ref)
        if target and target not in seen:
            normalized.append(target)
            seen.add(target)
    return normalized


def _preset_manifest() -> dict[str, Any]:
    if PRESET_MANIFEST_PATH.is_file():
        return read_json(PRESET_MANIFEST_PATH)
    return {"avatars": [], "covers": []}


def _stub_article_markdown(*, title: str, summary: str, body: str) -> str:
    """Deterministic-stub QWQ Markdown for the article carrier.

    Long-form truth source is Markdown (`articleMarkdown`), never the retired
    `articleDocument`. The narrative is a deterministic stub (bodyMode stub binding);
    front matter mirrors the compliant content_scenarios article fixtures so the
    markdown reader (codec → AST → pagination) renders a real long-form layout.
    """
    return (
        "---\n"
        f"title: {title}\n"
        f"summary: {summary}\n"
        "template: journal\n"
        "fontPreset: clean\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{body}\n"
    )


def _stub_article_render_profile(*, vertical: str) -> dict[str, Any]:
    """Deterministic-stub render profile (dict) aligned to compliant article fixtures."""
    return {
        "template": "journal",
        "fontPreset": "clean",
        "paperThemeMode": "system",
        "paperTexture": "warmBlack",
        "contentVertical": vertical or DEFAULT_VERTICAL,
        "layoutPolicy": {
            "wrapDowngrade": "compactWidthToFullWidth",
            "galleryDowngrade": "singleColumn",
        },
    }


def _content_document(post: dict[str, Any], index: int) -> dict[str, Any]:
    """Project a lean binding post into a content-service / app feed post document.

    The narrative body is a deterministic stub; the authorship binding is the real
    match_creator output. Field aliases mirror existing content_scenarios posts so
    both the Go content-service mapper and the Dart mock loader can consume it.
    Article carrier carries the Markdown kernel (`articleMarkdown` +
    `articleRenderProfile`, no `articleDocument`) per the markdown-article-kernel
    contract.
    """
    carrier = post["carrier"]
    doc_id = f"{CONTENT_DOC_PREFIX}{post['postId']}"
    cover = post["coverUrl"]
    image_urls = [cover] if cover else []
    body = (
        f"{post['region'] or DEFAULT_VERTICAL}主题 {carrier} 内容，由平台虚拟创作者"
        f"{post['displayName']}（{post['creatorArchetype']}）出品。"
    )
    document: dict[str, Any] = {
        "postId": doc_id,
        "id": doc_id,
        "contentType": post["contentType"],
        "type": post["contentType"],
        "contentIdentity": "work",
        "identity": "work",
        "authorId": post["authorId"],
        "subAccountId": post.get("subAccountId") or post["authorId"],
        "creatorSubAccountId": post.get("subAccountId"),
        "creatorProfileId": post["creatorProfileId"],
        "displayName": post["displayName"],
        "authorDisplayName": post.get("authorDisplayName") or post["displayName"],
        "authorAvatarUrl": post["authorAvatarUrl"],
        "authorAvatarObjectKey": post.get("authorAvatarObjectKey") or post["authorAvatarUrl"],
        "avatarUrl": post["authorAvatarUrl"],
        "title": post["title"],
        "summary": post["summary"],
        "body": body,
        "coverUrl": cover,
        "thumbnailUrl": cover,
        "mediaUrls": image_urls,
        "imageUrls": image_urls,
        "videoUrl": SAMPLE_VIDEO_OBJECT_KEY if carrier == "video" else None,
        "tagRefs": post["tagRefs"],
        "contentTagRefs": post.get("contentTagRefs") or post["tagRefs"],
        "entityRefs": post.get("entityRefs") or [],
        "circleRefs": post.get("circleRefs") or [],
        "locationName": post["region"] or "",
        "likeCount": 12 + index,
        "commentCount": 3 + index,
        "shareCount": 1 + index,
        "createdAt": CONTENT_BASE_CREATED_AT,
    }
    if carrier == "article":
        document["articleMarkdown"] = _stub_article_markdown(
            title=post["title"], summary=post["summary"], body=body
        )
        document["articleRenderProfile"] = _stub_article_render_profile(
            vertical=post["vertical"]
        )
    return document


def materialize_content_scenarios_seed_set(
    *, batch_id: str = CANONICAL_BATCH_ID
) -> dict[str, Any]:
    """Inject the creator-authored posts as a content_scenarios seedSet (single source).

    The binding seed is the authorship truth; this seedSet is its content-document
    projection that the content-service env seeders and the alpha mock app consume.
    """
    payload = build_creator_content(batch_id=batch_id)
    posts = [_content_document(p, i) for i, p in enumerate(payload["posts"])]
    seed_set_ref = CONTENT_SEED_SET_REF if batch_id == CANONICAL_BATCH_ID else f"creator_authored_{batch_id}_core"
    written: list[str] = []
    for target in CONTENT_SCENARIOS_TARGETS:
        if not target.is_file():
            continue
        scenarios = read_json(target)
        seed_sets = scenarios.setdefault("seedSets", {})
        if batch_id == CANONICAL_BATCH_ID:
            seed_sets.pop(f"creator_authored_{batch_id}_core", None)
        seed_sets[seed_set_ref] = {
            "description": f"{batch_id} 虚拟创作者经 match_creator 绑定的文章/图片/视频内容。",
            "posts": posts,
        }
        write_json(target, scenarios)
        written.append(str(target))
    return {"ref": seed_set_ref, "posts": len(posts), "paths": written}


def write_creator_content_seed(*, batch_id: str = CANONICAL_BATCH_ID) -> str:
    payload = build_creator_content(batch_id=batch_id)
    seed_name = CONTENT_SEED_NAME if batch_id == CANONICAL_BATCH_ID else f"creator_content.{batch_id}.seed.json"
    path = repo_seed_fixture_dir() / seed_name
    write_json(path, payload)
    materialize_content_scenarios_seed_set(batch_id=batch_id)
    return str(path)
