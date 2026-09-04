"""环境集成探针的 release 输入解析与检查项装配。

入口模块保留 CLI、执行循环和既有可 patch 符号；本模块只负责把规范化输入
投影为只读检查描述，避免单一 runner 同时承担装配与执行职责。
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from typing import Any

from quwoquan_ops.cli.lib.media_delivery_manifest import build_media_delivery_url
from quwoquan_ops.cli.probes.environment_probe_semantics import (
    CREATOR_PROFILE_CHECK_NAME,
    PRIVATE_FEED_CHECK_NAMES,
    SIGNED_MEDIA_CHECK_NAME,
)

def _owner_matches_post(owner_ref: object, post_ref: str) -> bool:
    owner = str(owner_ref or "").strip().strip("/")
    post = str(post_ref or "").strip().strip("/")
    return owner == post or owner == f"posts/{post}"


def _release_probe_identity(
    args: argparse.Namespace,
    *,
    load_release_content_identity_fn,
    resolve_readiness_path_fn,
    release_video_delivery_error,
) -> dict[str, Any]:
    raw_receipt = str(getattr(args, "release_readiness", "") or "").strip()
    if not raw_receipt:
        raise release_video_delivery_error(
            "DATA_RELEASE_READINESS_RECEIPT is required for the media integration probe"
        )
    identity = load_release_content_identity_fn(
        resolve_readiness_path_fn(raw_receipt),
        expected_environment=args.env,
    )
    if str(identity["receipt"].get("releaseClass") or "") == "research":
        # research 私有交付（DEC-031）不存在匿名可采样图片，media_sample
        # 语义不成立；identity 其余字段照常供 feed 绑定检查使用。
        return {
            "releaseId": identity["releaseId"],
            "manifestDigest": identity["manifestDigest"],
            "importRunId": identity["importRunId"],
            "verifyRunId": identity["verifyRunId"],
            "readinessReceiptRef": identity["readinessReceiptRef"],
            "media": None,
        }
    image_posts = {
        str(binding["postRef"]).strip().strip("/")
        for binding in identity["postBindings"]
        if binding.get("contentType") == "image"
    }
    candidates = sorted(
        (
            dict(asset)
            for asset in identity["mediaAssets"]
            if asset.get("kind") == "image"
            and str(asset.get("contentType") or "").lower().startswith("image/")
            and str(asset.get("publicSliceKey") or "").startswith("media/image/s/")
            and any(
                _owner_matches_post(owner, post_ref)
                for owner in asset.get("ownerRefs") or []
                for post_ref in image_posts
            )
        ),
        key=lambda asset: (
            str(asset.get("assetId") or ""),
            str(asset.get("publicSliceKey") or ""),
        ),
    )
    if not candidates:
        raise release_video_delivery_error(
            "canonical Data readiness/import receipt has no release-bound image asset"
        )
    media = candidates[0]
    version = media.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise release_video_delivery_error(
            "release-bound image asset version must be a positive integer"
        )
    return {
        "releaseId": identity["releaseId"],
        "manifestDigest": identity["manifestDigest"],
        "importRunId": identity["importRunId"],
        "verifyRunId": identity["verifyRunId"],
        "readinessReceiptRef": identity["readinessReceiptRef"],
        "media": {
            "assetId": str(media["assetId"]),
            "version": version,
            "publicSliceKey": str(media["publicSliceKey"]),
            "sha256": str(media.get("sha256") or ""),
            "contentType": str(media["contentType"]),
        },
    }


def _release_search_canaries(args: argparse.Namespace) -> list[dict[str, str]]:
    raw_canaries = getattr(args, "release_search_canary", []) or []
    if not raw_canaries:
        return []
    expected_types = {
        "homepage": "entity.homepage",
        "article": "content.post",
        "image": "content.post",
        "video": "content.post",
    }
    previous_expected_types = {
        "post": "content.post",
        "homepage": "entity.homepage",
        "persona": "user.profile",
    }
    canaries: list[dict[str, str]] = []
    observed_kinds: set[str] = set()
    for index, raw in enumerate(raw_canaries):
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"release search canary {index} is not canonical JSON"
            ) from exc
        if not isinstance(value, dict) or set(value) != {
            "kind",
            "query",
            "expectedObjectType",
            "expectedObjectId",
        }:
            raise ValueError(f"release search canary {index} fields are invalid")
        canary = {key: str(value.get(key) or "").strip() for key in value}
        kind = canary["kind"]
        active_types = (
            previous_expected_types
            if set(
                str(json.loads(str(item)).get("kind") or "")
                for item in raw_canaries
                if isinstance(json.loads(str(item)), dict)
            ).issubset(previous_expected_types)
            else expected_types
        )
        if (
            kind not in active_types
            or kind in observed_kinds
            or canary["expectedObjectType"] != active_types[kind]
            or not canary["query"]
            or not canary["expectedObjectId"]
        ):
            raise ValueError(f"release search canary {index} identity is invalid")
        observed_kinds.add(kind)
        canaries.append(canary)
    if observed_kinds != set(expected_types) and observed_kinds != set(
        previous_expected_types
    ):
        raise ValueError(
            "release search canaries must cover Homepage/Article/Image/Video "
            "or the previous Post/Homepage/Persona set"
        )
    return canaries


def _release_samples(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_samples = getattr(args, "release_sample", []) or []
    samples: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    required_fields = {
        "sampleId",
        "carrier",
        "sourceReadback",
        "sourceObjectId",
        "ordinal",
        "readObjectId",
        "expectedContentType",
    }
    creator_fields = {
        "expectedAuthorId",
        "expectedPersonaId",
        "expectedAuthorDisplayName",
        "expectedAvatarAssetId",
        "expectedAvatarDeliveryRef",
    }
    for index, raw in enumerate(raw_samples):
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"release sample {index} is not canonical JSON") from exc
        if (
            not isinstance(value, dict)
            or not required_fields.issubset(value)
            or set(value) - required_fields - creator_fields
        ):
            raise ValueError(f"release sample {index} fields are invalid")
        sample_id = str(value.get("sampleId") or "").strip()
        carrier = str(value.get("carrier") or "").strip()
        source_object_id = str(value.get("sourceObjectId") or "").strip()
        read_object_id = str(value.get("readObjectId") or "").strip()
        content_type = str(value.get("expectedContentType") or "").strip()
        if (
            not sample_id
            or sample_id in observed_ids
            or carrier not in {"homepage", "article", "image", "video"}
            or not source_object_id
            or not read_object_id
            or content_type != ("" if carrier == "homepage" else carrier)
        ):
            raise ValueError(f"release sample {index} identity is invalid")
        observed_ids.add(sample_id)
        samples.append(dict(value))
    return samples


def _release_creator_profiles(args: argparse.Namespace) -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    observed: set[str] = set()
    expected_fields = {
        "creatorRef", "authorId", "personaId", "displayName",
        "avatarAssetId", "avatarDeliveryRef",
    }
    for index, raw in enumerate(getattr(args, "release_creator_profile", []) or []):
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"release creator profile {index} is not canonical JSON"
            ) from exc
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise ValueError(f"release creator profile {index} fields are invalid")
        profile = {key: str(value.get(key) or "").strip() for key in value}
        if (
            not all(profile.values())
            or profile["personaId"] in observed
            or not profile["avatarDeliveryRef"].startswith("media/objects/sha256/")
        ):
            raise ValueError(f"release creator profile {index} identity is invalid")
        observed.add(profile["personaId"])
        profiles.append(profile)
    return profiles


def _release_signed_media(args: argparse.Namespace) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    observed_categories: set[str] = set()
    expected_fields = {
        "assetId", "kind", "expectedBytes", "expectedSha256",
        "expectedMimeType", "privateDeliveryRef", "classifications",
        "requireRange",
    }
    for index, raw in enumerate(getattr(args, "release_signed_media", []) or []):
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"release signed media {index} is not canonical JSON"
            ) from exc
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise ValueError(f"release signed media {index} fields are invalid")
        asset_id = str(value.get("assetId") or "").strip()
        kind = str(value.get("kind") or "").strip()
        categories = value.get("classifications")
        expected_bytes = value.get("expectedBytes")
        require_range = value.get("requireRange")
        if (
            not asset_id
            or asset_id in observed_ids
            or kind not in {"avatar", "image", "video"}
            or not isinstance(categories, list)
            or not categories
            or any(
                str(category) not in {
                    "avatar", "image", "typed_video", "premium_video"
                }
                for category in categories
            )
            or len(categories) != len(set(categories))
            or not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes <= 0
            or require_range is not (kind == "video")
            or not str(value.get("privateDeliveryRef") or "").startswith(
                "media/objects/sha256/"
            )
        ):
            raise ValueError(f"release signed media {index} identity is invalid")
        observed_ids.add(asset_id)
        observed_categories.update(str(category) for category in categories)
        assets.append(dict(value))
    if assets and observed_categories != {
        "avatar", "image", "typed_video", "premium_video"
    }:
        raise ValueError("release signed media classifications are incomplete")
    return assets


def build_checks(
    args: argparse.Namespace,
    *,
    release_identity: dict[str, Any] | None = None,
    default_environment_search_query: str,
    common_headers,
    feed_headers,
    feed_url,
    json_headers,
    public_headers,
    release_search_canaries,
    release_samples,
    release_creator_profiles,
    release_signed_media,
) -> list[dict[str, Any]]:
    DEFAULT_ENVIRONMENT_SEARCH_QUERY = default_environment_search_query
    _common_headers = common_headers
    _feed_headers = feed_headers
    _feed_url = feed_url
    _json_headers = json_headers
    _public_headers = public_headers
    _release_search_canaries = release_search_canaries
    _release_samples = release_samples
    _release_creator_profiles = release_creator_profiles
    _release_signed_media = release_signed_media
    base = args.base_url.rstrip("/")
    require_non_empty_content_feed = bool(
        getattr(args, "require_non_empty_content_feed", False)
    )
    research_anonymous_convergence = bool(
        getattr(args, "research_anonymous_convergence", False)
    )
    research_consumer_readback = bool(
        getattr(args, "research_consumer_readback", False)
    )
    # feed 检查默认走匿名面（发现面语义）；research consumer 模式下四个
    # private feed 必须统一走同一 Bearer。匿名收敛即使进程存在环境凭证也显式
    # 去掉 Authorization，避免把“非研究认证”误当匿名隔离证据。
    feed_auth_token = args.test_auth_token if research_consumer_readback else ""
    if research_consumer_readback and not str(feed_auth_token or "").strip():
        raise ValueError("research consumer readback requires a bearer token")
    media_image_base_url = str(
        getattr(
            args,
            "media_image_base_url",
            getattr(args, "media_base_url", ""),
        )
        or ""
    )
    public_headers = (
        _public_headers()
        if args.env == "prod"
        else _common_headers(args.test_auth_token)
    )
    search_canaries = _release_search_canaries(args)
    release_samples = _release_samples(args)
    creator_profiles = _release_creator_profiles(args)
    signed_media_assets = _release_signed_media(args)
    search_limit = 20 if search_canaries else 1
    homepage_query = next(
        (
            item["query"]
            for item in search_canaries
            if item["kind"] == "homepage"
        ),
        DEFAULT_ENVIRONMENT_SEARCH_QUERY,
    )
    if PRIVATE_FEED_CHECK_NAMES != {
        "content_feed",
        "homepage_recommend",
        "video_book_feed",
        "premium_feed",
    }:
        raise ValueError("private feed check registry drifted")
    checks: list[dict[str, Any]] = [
        {
            "name": "gateway_healthz",
            "method": "GET",
            "url": f"{base}/healthz",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "app_config",
            "method": "GET",
            "url": f"{base}/config/app",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "content_feed",
            "method": "GET",
            "url": _feed_url(base, "?identity=work&sort=recommend&limit=1"),
            "headers": _feed_headers(feed_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "homepage_recommend",
            "method": "GET",
            "url": _feed_url(
                base, "?sort=recommend&channelId=recommend&limit=20"
            ),
            "headers": _feed_headers(feed_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "entity_homepage_search",
            "method": "GET",
            "url": (
                f"{base}/homepages/search?query="
                f"{urllib.parse.quote(homepage_query)}&limit=1"
            ),
            "headers": _common_headers(args.test_auth_token),
            "expected_statuses": [200],
        },
    ]
    for canary in search_canaries or [
        {
            "kind": "generic",
            "query": DEFAULT_ENVIRONMENT_SEARCH_QUERY,
            "expectedObjectType": "",
            "expectedObjectId": "",
        }
    ]:
        checks.append(
            {
                "name": "global_search",
                "method": "POST",
                "url": f"{base}/search",
                "headers": {
                    **_json_headers(args.test_auth_token),
                    "X-Session-Id": "stackctl-environment-probe",
                },
                "body": json.dumps(
                    {
                        "query": canary["query"],
                        "mode": "result",
                        "limit": search_limit,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                "expected_statuses": [200],
                "searchCanaryKind": canary["kind"],
                "expectedSearchObjectType": canary["expectedObjectType"],
                "expectedSearchObjectId": canary["expectedObjectId"],
            }
        )
    for sample in release_samples:
        carrier = str(sample["carrier"])
        read_object_id = urllib.parse.quote(str(sample["readObjectId"]), safe="")
        path = (
            f"homepages/{read_object_id}"
            if carrier == "homepage"
            else f"content/posts/{read_object_id}"
        )
        checks.append(
            {
                "name": "release_sample",
                "method": "GET",
                "url": f"{base}/{path}",
                "headers": _common_headers(args.test_auth_token),
                "expected_statuses": [200],
                **sample,
            }
        )
    for profile in creator_profiles:
        persona_id = urllib.parse.quote(profile["personaId"], safe="")
        checks.append(
            {
                "name": CREATOR_PROFILE_CHECK_NAME,
                "method": "GET",
                "url": f"{base}/user/{persona_id}",
                "headers": _common_headers(args.test_auth_token),
                "expected_statuses": [200],
                **profile,
            }
        )
    if signed_media_assets:
        checks.append(
            {
                "name": SIGNED_MEDIA_CHECK_NAME,
                "method": "INTERNAL",
                "url": f"{base}/content/media",
                "headers": {},
                "expected_statuses": [200],
                "assets": signed_media_assets,
            }
        )
    if (
        require_non_empty_content_feed
        or research_anonymous_convergence
        or research_consumer_readback
    ):
        video_page_size = int(getattr(args, "video_page_size", 1) or 1)
        if not 1 <= video_page_size <= 100:
            raise ValueError("video page size must be between 1 and 100")
        feed_headers = _feed_headers(feed_auth_token)
        checks.extend(
            [
                {
                    "name": "video_book_feed",
                    "method": "GET",
                    "url": _feed_url(
                        base,
                        "?identity=work&type=video&sort=recommend&limit="
                        f"{video_page_size}",
                    ),
                    "headers": feed_headers,
                    "expected_statuses": [200],
                },
                {
                    "name": "premium_feed",
                    "method": "GET",
                    "url": _feed_url(
                        base,
                        "?sort=recommend&channelId=premium_stream&limit=1",
                    ),
                    "headers": feed_headers,
                    "expected_statuses": [200],
                },
            ]
        )
    if args.test_auth_token:
        checks.append(
            {
                "name": "user_sync",
                "method": "POST",
                "url": f"{base}/user/sync",
                "headers": _json_headers(args.test_auth_token),
                "body": json.dumps(
                    {"afterSeq": 0, "limit": 1}, ensure_ascii=False
                ).encode("utf-8"),
                "expected_statuses": [200],
            }
        )
    product_ops = args.product_ops_base_url.rstrip("/")
    if product_ops:
        checks.append(
            {
                "name": "product_ops_healthz",
                "method": "GET",
                "url": f"{product_ops}/healthz",
                "headers": public_headers,
                "expected_statuses": [200],
            }
        )
    media_base = media_image_base_url.rstrip("/")
    media = (
        release_identity.get("media")
        if isinstance(release_identity, dict)
        else None
    )
    if media_base and isinstance(media, dict):
        checks.append(
            {
                "name": "media_sample",
                "method": "GET",
                "url": build_media_delivery_url(
                    {"mediaImage": media_base},
                    {
                        "mediaType": "image",
                        "publicSliceKey": media["publicSliceKey"],
                        "version": media["version"],
                    },
                ),
                "headers": public_headers,
                "expected_statuses": [200],
            }
        )
    return checks
