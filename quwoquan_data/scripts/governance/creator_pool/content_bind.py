"""Deterministic creator-content binding via the real match_creator router.

Phase 3 of the no-breakpoint E2E closure needs real content bound to the batch-100
creators across the three carriers (article / image / video). The narrative body is
LLM-produced in the live pipeline, but the *authorship binding* — which batch-100
creator authors which carrier — is routed deterministically here through the same
``match_creator`` used in production, and validated by the full
``creator_assignment_issues`` gate (carrier + semantic). The emitted
``creator_content.seed.json`` is the production binding truth source (``previewOnly``
is False), unlike ``content_supply`` round-robin preview samples.
"""
from __future__ import annotations

from typing import Any

from _common.creator_assignment import creator_assignment_from_profile, creator_assignment_issues
from _common.creator_pool.io import repo_seed_fixture_dir
from _common.io import read_json, write_json
from _common.paths import SERVICE_CONTRACTS_METADATA_ROOT, now_iso
from template.creator import carrier_affinity, match_creator
from template.registry import TemplateRegistry

CARRIERS: tuple[str, ...] = ("article", "image", "video")
CONTENT_TYPE_BY_CARRIER = {"article": "article", "image": "image", "video": "video"}
DEFAULT_VERTICAL = "travel"
CONTENT_SEED_NAME = "creator_content.seed.json"
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


def _active_batch_creators(registry: TemplateRegistry, batch_prefix: str) -> list[dict[str, Any]]:
    return [
        c
        for c in registry.creators.values()
        if str(c.get("creatorProfileId") or "").startswith(batch_prefix)
        and str(c.get("status") or "") == "active"
    ]


def _carrier_lead(creators: list[dict[str, Any]], carrier: str) -> dict[str, Any]:
    """Highest-affinity creator for a carrier (deterministic tie-break by id)."""
    pool = [c for c in creators if carrier_affinity(c, carrier) > 0]
    pool.sort(key=lambda c: (-carrier_affinity(c, carrier), str(c.get("creatorProfileId") or "")))
    return pool[0]


def _brief_from_lead(lead: dict[str, Any], carrier: str) -> dict[str, Any]:
    """Build a content brief from a lead creator's own coverage so routing is real."""
    scope = lead.get("coverageScope") if isinstance(lead.get("coverageScope"), dict) else {}
    region_refs = [str(x) for x in (scope.get("regionRefs") or []) if x]
    region = region_refs[0] if region_refs else None
    preferred = [str(x) for x in (lead.get("preferredBlueprintIds") or []) if x]
    template_id = preferred[0] if preferred else ""
    pub_tags = [str(x) for x in (lead.get("publicProfileTagRefs") or []) if x]
    # Prefer a specific topic tag over the bare vertical root for a real topic signal.
    tag_refs = [t for t in pub_tags if t.count("/") >= 2][:1] or pub_tags[:1]
    return {
        "carrier": carrier,
        "templateId": template_id,
        "creatorPersona": {"archetype": str(lead.get("creatorArchetype") or "")},
        "region": region,
        "vertical": DEFAULT_VERTICAL,
        "tagRefs": tag_refs,
    }


def build_creator_content(
    *,
    registry: TemplateRegistry | None = None,
    batch_id: str = "travel_batch_100_v1",
) -> dict[str, Any]:
    """Route a representative article/image/video subset to batch-100 creators.

    Raises ValueError if any binding fails the creator assignment gate so the
    producer can never emit an invalid (wrong-carrier / wrong-coverage) author bind.
    """
    registry = registry or TemplateRegistry.load()
    batch_prefix = "qwq_creator_" + DEFAULT_VERTICAL + "_"
    creators = _active_batch_creators(registry, batch_prefix)
    if len(creators) < len(CARRIERS):
        raise ValueError(f"insufficient active batch creators: {len(creators)}")

    posts: list[dict[str, Any]] = []
    used_authors: set[str] = set()
    for idx, carrier in enumerate(CARRIERS):
        lead = _carrier_lead(creators, carrier)
        brief = _brief_from_lead(lead, carrier)
        content_id = f"creator_content_{carrier}_{idx + 1:03d}"
        chosen = match_creator(
            registry,
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
        author_id = str(chosen.get("authorId") or "")
        avatar_key = str(chosen.get("avatarObjectKey") or "")
        # Cover lives in VCS alongside the avatar under the deterministic media layout
        # (avatar.jpg / cover.jpg); the registry profile only stores the avatar key.
        cover_key = avatar_key.rsplit("/", 1)[0] + "/cover.jpg" if avatar_key else ""
        posts.append(
            {
                "postId": content_id,
                "contentType": CONTENT_TYPE_BY_CARRIER[carrier],
                "carrier": carrier,
                "authorId": author_id,
                "creatorProfileId": str(chosen.get("creatorProfileId") or ""),
                "creatorArchetype": str(chosen.get("creatorArchetype") or ""),
                "displayName": str(chosen.get("displayName") or chosen.get("userHandle") or ""),
                "authorAvatarUrl": avatar_key,
                "coverUrl": cover_key,
                "title": f"{brief['region'] or DEFAULT_VERTICAL}·{brief['templateId'] or carrier}",
                "summary": f"{brief['region'] or ''} {carrier} 内容（平台虚拟创作者出品）",
                "tagRefs": brief["tagRefs"],
                "region": brief["region"],
                "templateId": brief["templateId"],
                "vertical": brief["vertical"],
                "cohortId": batch_id,
                "routedBy": "match_creator",
                "bodyMode": "deterministic_stub",
            }
        )
        used_authors.add(author_id)

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


def _content_document(post: dict[str, Any], index: int) -> dict[str, Any]:
    """Project a lean binding post into a content-service / app feed post document.

    The narrative body is a deterministic stub; the authorship binding is the real
    match_creator output. Field aliases mirror existing content_scenarios posts so
    both the Go content-service mapper and the Dart mock loader can consume it.
    """
    carrier = post["carrier"]
    doc_id = f"{CONTENT_DOC_PREFIX}{post['postId']}"
    cover = post["coverUrl"]
    image_urls = [cover] if cover else []
    body = (
        f"{post['region'] or DEFAULT_VERTICAL}主题 {carrier} 内容，由平台虚拟创作者"
        f"{post['displayName']}（{post['creatorArchetype']}）出品。"
    )
    return {
        "postId": doc_id,
        "id": doc_id,
        "contentType": post["contentType"],
        "type": post["contentType"],
        "contentIdentity": "work",
        "identity": "work",
        "authorId": post["authorId"],
        "subAccountId": post["authorId"],
        "creatorProfileId": post["creatorProfileId"],
        "displayName": post["displayName"],
        "authorAvatarUrl": post["authorAvatarUrl"],
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
        "locationName": post["region"] or "",
        "likeCount": 12 + index,
        "commentCount": 3 + index,
        "shareCount": 1 + index,
        "createdAt": CONTENT_BASE_CREATED_AT,
    }


def materialize_content_scenarios_seed_set(
    *, batch_id: str = "travel_batch_100_v1"
) -> dict[str, Any]:
    """Inject the creator-authored posts as a content_scenarios seedSet (single source).

    The binding seed is the authorship truth; this seedSet is its content-document
    projection that the content-service env seeders and the alpha mock app consume.
    """
    payload = build_creator_content(batch_id=batch_id)
    posts = [_content_document(p, i) for i, p in enumerate(payload["posts"])]
    written: list[str] = []
    for target in CONTENT_SCENARIOS_TARGETS:
        if not target.is_file():
            continue
        scenarios = read_json(target)
        seed_sets = scenarios.setdefault("seedSets", {})
        seed_sets[CONTENT_SEED_SET_REF] = {
            "description": "batch-100 虚拟创作者经 match_creator 绑定的文章/图片/视频内容（Phase3 E2E）。",
            "posts": posts,
        }
        write_json(target, scenarios)
        written.append(str(target))
    return {"ref": CONTENT_SEED_SET_REF, "posts": len(posts), "paths": written}


def write_creator_content_seed(*, batch_id: str = "travel_batch_100_v1") -> str:
    payload = build_creator_content(batch_id=batch_id)
    path = repo_seed_fixture_dir() / CONTENT_SEED_NAME
    write_json(path, payload)
    materialize_content_scenarios_seed_set(batch_id=batch_id)
    return str(path)
