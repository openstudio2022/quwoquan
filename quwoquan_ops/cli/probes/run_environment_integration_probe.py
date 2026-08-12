#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.media_delivery_manifest import build_media_delivery_url
from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)

DEFAULT_REPORT = (
    REPO_ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "runs"
    / "integration-probe"
    / "report.json"
)
CONTENT_POST_PROJECTION_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "post"
    / "projections"
    / "content_post_projection.yaml"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=1)
def _content_post_projection_fields() -> frozenset[str]:
    """Load public feed-item keys from the canonical projection contract."""
    try:
        document = yaml.safe_load(
            CONTENT_POST_PROJECTION_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            "canonical ContentPostProjection contract is unreadable: "
            f"{CONTENT_POST_PROJECTION_PATH}"
        ) from exc
    if (
        not isinstance(document, dict)
        or document.get("read_model") != "ContentPostProjection"
    ):
        raise ValueError("canonical ContentPostProjection contract has invalid read_model")
    raw_fields = document.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError(
            "canonical ContentPostProjection contract fields must be a non-empty array"
        )
    fields: set[str] = set()
    for index, raw_field in enumerate(raw_fields):
        if not isinstance(raw_field, dict):
            raise ValueError(
                f"canonical ContentPostProjection field {index} must be an object"
            )
        name = str(raw_field.get("name") or "").strip()
        if not name or name in fields:
            raise ValueError(
                f"canonical ContentPostProjection field {index} has invalid name"
            )
        fields.add(name)
    return frozenset(fields)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run readonly integration probes for alpha/beta/gamma/prod environments.",
    )
    parser.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
        help=(
            "Canonical Data release-readiness.json. Required when the media "
            "sample probe is enabled; no fixture/default media identity exists."
        ),
    )
    parser.add_argument("--test-auth-token", default="")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--request-timeout-seconds", type=int, default=12)
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument(
        "--only-check",
        action="append",
        default=[],
        help="Run only the named check; repeat for multiple checks (for example global_search).",
    )
    parser.add_argument(
        "--require-non-empty-content-feed",
        action="store_true",
        help=(
            "Release-readiness mode: require discovery, exact video-book and premium "
            "feed queries to return at least one item."
        ),
    )
    parser.add_argument(
        "--expected-discovery-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound postId accepted by the identity=work readback; repeatable. "
            "At least one returned item must match."
        ),
    )
    parser.add_argument(
        "--expected-video-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound video postId accepted by the identity=work&type=video "
            "readback; repeatable."
        ),
    )
    parser.add_argument(
        "--expected-premium-video-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound playable video postId accepted by the premium_stream "
            "readback; repeatable."
        ),
    )
    parser.add_argument(
        "--video-page-size",
        type=int,
        default=1,
        help="Exact video-book page size used by release-bound App UAT.",
    )
    parser.add_argument(
        "--release-search-canary",
        action="append",
        default=[],
        help=(
            "Canonical JSON object containing kind/query/expectedObjectType/"
            "expectedObjectId; repeat for Post, Homepage, and Persona."
        ),
    )
    parser.add_argument(
        "--release-sample",
        action="append",
        default=[],
        help=(
            "Canonical JSON object for one exact release-bound homepage/Post read; "
            "repeat exactly once for every stratified sample."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("readonly", "post-deploy"),
        default="readonly",
    )
    args = parser.parse_args()
    args.test_auth_token = _resolve_test_auth_token(args.env, args.test_auth_token)
    return args


def _resolve_test_auth_token(env_name: str, explicit_token: str) -> str:
    token = explicit_token.strip()
    if token:
        return token
    token_envs = {
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "gamma": ("GAMMA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "prod": ("PROD_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
    }
    for env_var in token_envs.get(env_name, ("TEST_AUTH_TOKEN",)):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return ""


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 12,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
) -> tuple[bool, int | None, str]:
    retry_markers = (
        "timed out",
        "Remote end closed connection without response",
        "Connection reset",
        "Connection closed",
    )
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        req = urllib.request.Request(
            url, headers=headers or {}, data=body, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return True, int(response.status), payload
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), payload
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if attempt >= total_attempts or not any(
                marker in message for marker in retry_markers
            ):
                return False, None, message
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown request failure"


def _common_headers(test_auth_token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    token = test_auth_token.strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _json_headers(test_auth_token: str) -> dict[str, str]:
    headers = _common_headers(test_auth_token)
    headers["Content-Type"] = "application/json"
    return headers


def _public_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


_INTEGRATION_FEED_SESSION_ID = "stackctl-environment-integration-probe"


def _feed_headers(test_auth_token: str = "") -> dict[str, str]:
    """Ranked recommend feeds require a session id (query or X-Client-Session-Id)."""

    headers = _common_headers(test_auth_token)
    headers["X-Client-Session-Id"] = _INTEGRATION_FEED_SESSION_ID
    return headers


def _feed_url(base: str, query: str) -> str:
    separator = "&" if "?" in query else "?"
    return (
        f"{base.rstrip('/')}/content/feed{query}"
        f"{separator}sessionId={_INTEGRATION_FEED_SESSION_ID}"
    )


def _owner_matches_post(owner_ref: object, post_ref: str) -> bool:
    owner = str(owner_ref or "").strip().strip("/")
    post = str(post_ref or "").strip().strip("/")
    return owner == post or owner == f"posts/{post}"


def _release_probe_identity(args: argparse.Namespace) -> dict[str, Any]:
    raw_receipt = str(getattr(args, "release_readiness", "") or "").strip()
    if not raw_receipt:
        raise ReleaseVideoDeliveryError(
            "DATA_RELEASE_READINESS_RECEIPT is required for the media integration probe"
        )
    identity = load_release_content_identity(
        resolve_readiness_path(raw_receipt),
        expected_environment=args.env,
    )
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
        raise ReleaseVideoDeliveryError(
            "canonical Data readiness/import receipt has no release-bound image asset"
        )
    media = candidates[0]
    version = media.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise ReleaseVideoDeliveryError(
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
        if (
            kind not in expected_types
            or kind in observed_kinds
            or canary["expectedObjectType"] != expected_types[kind]
            or not canary["query"]
            or not canary["expectedObjectId"]
        ):
            raise ValueError(f"release search canary {index} identity is invalid")
        observed_kinds.add(kind)
        canaries.append(canary)
    if observed_kinds != set(expected_types):
        raise ValueError("release search canaries must cover Post, Homepage, and Persona")
    return canaries


def _release_samples(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_samples = getattr(args, "release_sample", []) or []
    samples: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    expected_fields = {
        "sampleId",
        "carrier",
        "sourceReadback",
        "sourceObjectId",
        "ordinal",
        "readObjectId",
        "expectedContentType",
    }
    for index, raw in enumerate(raw_samples):
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"release sample {index} is not canonical JSON") from exc
        if not isinstance(value, dict) or set(value) != expected_fields:
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


def build_checks(
    args: argparse.Namespace,
    *,
    release_identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base = args.base_url.rstrip("/")
    require_non_empty_content_feed = bool(
        getattr(args, "require_non_empty_content_feed", False)
    )
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
    homepage_query = next(
        (
            item["query"]
            for item in search_canaries
            if item["kind"] == "homepage"
        ),
        "quwoquan",
    )
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
            "headers": _feed_headers(),
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
            "query": "quwoquan",
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
                    {"query": canary["query"], "mode": "result", "limit": 20},
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
    if require_non_empty_content_feed:
        video_page_size = int(getattr(args, "video_page_size", 1) or 1)
        if not 1 <= video_page_size <= 100:
            raise ValueError("video page size must be between 1 and 100")
        feed_headers = _feed_headers()
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


def _content_feed_semantic_issue(payload: str) -> tuple[str | None, int | None]:
    issue, count, _post_ids = _content_feed_semantic_result(payload)
    return issue, count


def _content_feed_semantic_result(
    payload: str,
    *,
    expected_post_ids: set[str] | None = None,
) -> tuple[str | None, int | None, set[str]]:
    body = payload.strip()
    if not body:
        return "response body is empty", 0, set()
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None, set()
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None, set()
    object_cards = decoded.get("objectCards")
    if not isinstance(object_cards, list):
        return 'response payload is missing array "objectCards"', None, set()
    items: list[Any] | None = None
    candidate_items = decoded.get("items")
    if isinstance(candidate_items, list):
        items = candidate_items
    if items is None:
        return None, None, set()
    if not items:
        return 'response payload has empty "items"', 0, set()
    try:
        allowed_item_fields = _content_post_projection_fields()
    except ValueError as exc:
        return str(exc), None, set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return f"response items[{index}] must be a JSON object", None, set()
        unknown = sorted(set(item) - allowed_item_fields)
        if unknown:
            return (
                f"response items[{index}] has unknown ContentPostProjection fields: "
                + ", ".join(unknown),
                None,
                set(),
            )
    returned_post_ids = {
        str(item.get("postId") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("postId") or "").strip()
    }
    expected = {
        str(item).strip() for item in (expected_post_ids or set()) if str(item).strip()
    }
    if expected and not returned_post_ids.intersection(expected):
        return (
            "response has no postId bound to the expected immutable release",
            len(items),
            returned_post_ids,
        )
    return None, len(items), returned_post_ids


def _expected_release_post_ids(args: argparse.Namespace, check_name: str) -> set[str]:
    argument_names = {
        "content_feed": "expected_discovery_post_id",
        "video_book_feed": "expected_video_post_id",
        "premium_feed": "expected_premium_video_post_id",
    }
    argument_name = argument_names.get(check_name)
    if argument_name is None:
        return set()
    return {
        str(item).strip()
        for item in getattr(args, argument_name, [])
        if str(item).strip()
    }


def _search_semantic_issue(
    payload: str,
    *,
    expected_object_type: str = "",
    expected_object_id: str = "",
) -> tuple[str | None, int | None]:
    body = payload.strip()
    if not body:
        return "response body is empty", None
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None
    request_id = decoded.get("requestId")
    if not isinstance(request_id, str) or not request_id.strip():
        return 'response payload is missing non-empty "requestId"', None
    hits = decoded.get("hits")
    if not isinstance(hits, list):
        return 'response payload is missing array "hits"', None
    expected_type = expected_object_type.strip()
    expected_id = expected_object_id.strip()
    if expected_type and expected_id and not any(
        isinstance(hit, dict)
        and str(hit.get("objectType") or "").strip() == expected_type
        and str(hit.get("objectId") or "").strip() == expected_id
        for hit in hits
    ):
        return (
            "response has no exact release-bound "
            f"{expected_type}/{expected_id} hit",
            len(hits),
        )
    return None, len(hits)


def _release_sample_semantic_result(
    payload: str,
    *,
    carrier: str,
    read_object_id: str,
    expected_content_type: str,
) -> tuple[str | None, str, str]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", "", ""
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", "", ""
    id_field = "homepageId" if carrier == "homepage" else "postId"
    returned_id = str(decoded.get(id_field) or "").strip()
    returned_type = (
        "" if carrier == "homepage" else str(decoded.get("contentType") or "").strip()
    )
    if returned_id != read_object_id:
        return f"response {id_field} is not the exact release sample", returned_id, returned_type
    if carrier != "homepage" and returned_type != expected_content_type:
        return "response contentType is not the exact release sample type", returned_id, returned_type
    return None, returned_id, returned_type


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    findings: list[str] = []
    results: list[dict[str, Any]] = []
    mode = str(getattr(args, "mode", "readonly") or "readonly")
    media_image_base_url = str(
        getattr(
            args,
            "media_image_base_url",
            getattr(args, "media_base_url", ""),
        )
        or ""
    )
    request_timeout_seconds = int(getattr(args, "request_timeout_seconds", 12))
    retry_attempts = int(getattr(args, "retry_attempts", 1))
    retry_sleep_seconds = float(getattr(args, "retry_sleep_seconds", 0.0))
    require_non_empty_content_feed = bool(
        getattr(args, "require_non_empty_content_feed", False)
    )
    if mode == "post-deploy" and not args.test_auth_token:
        findings.append(
            "GATE_BLOCK: post-deploy integration requires a valid environment test auth token"
        )
    release_identity: dict[str, Any] | None = None
    if media_image_base_url.rstrip("/"):
        try:
            release_identity = _release_probe_identity(args)
        except (ReleaseVideoDeliveryError, ValueError) as exc:
            findings.append(f"GATE_BLOCK: {exc}")
    available_checks = build_checks(args, release_identity=release_identity)
    only_checks = {
        str(value).strip()
        for value in getattr(args, "only_check", [])
        if str(value).strip()
    }
    available_names = {check["name"] for check in available_checks}
    unknown_checks = sorted(only_checks - available_names)
    if unknown_checks:
        findings.append(
            "GATE_BLOCK: unknown integration check(s): " + ", ".join(unknown_checks)
        )
    selected_checks = [
        check
        for check in available_checks
        if not only_checks or check["name"] in only_checks
    ]
    for check in selected_checks:
        ok, status_code, payload = request(
            check["method"],
            check["url"],
            headers=check.get("headers"),
            body=check.get("body"),
            timeout=max(1, request_timeout_seconds),
            retry_attempts=max(1, retry_attempts),
            retry_sleep_seconds=max(0.0, retry_sleep_seconds),
        )
        expected_statuses = list(check.get("expected_statuses") or [])
        matched = ok and status_code in expected_statuses
        preview = payload[:1200]
        entry = {
            "name": check["name"],
            "method": check["method"],
            "url": check["url"],
            "statusCode": status_code,
            "ok": matched,
            "bodyPreview": preview,
        }
        if (
            matched
            and require_non_empty_content_feed
            and check["name"] in {"content_feed", "video_book_feed", "premium_feed"}
        ):
            semantic_issue, item_count, returned_post_ids = (
                _content_feed_semantic_result(
                    payload,
                    expected_post_ids=_expected_release_post_ids(
                        args,
                        check["name"],
                    ),
                )
            )
            if item_count is not None:
                entry["contentItemCount"] = item_count
            if returned_post_ids:
                entry["returnedPostIds"] = sorted(returned_post_ids)
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if matched and check["name"] == "global_search":
            semantic_issue, hit_count = _search_semantic_issue(
                payload,
                expected_object_type=str(
                    check.get("expectedSearchObjectType") or ""
                ),
                expected_object_id=str(
                    check.get("expectedSearchObjectId") or ""
                ),
            )
            if hit_count is not None:
                entry["searchHitCount"] = hit_count
            entry["searchCanaryKind"] = str(
                check.get("searchCanaryKind") or "generic"
            )
            entry["expectedSearchObjectType"] = str(
                check.get("expectedSearchObjectType") or ""
            )
            entry["expectedSearchObjectId"] = str(
                check.get("expectedSearchObjectId") or ""
            )
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if matched and check["name"] == "release_sample":
            semantic_issue, returned_id, returned_type = _release_sample_semantic_result(
                payload,
                carrier=str(check.get("carrier") or ""),
                read_object_id=str(check.get("readObjectId") or ""),
                expected_content_type=str(check.get("expectedContentType") or ""),
            )
            for field in (
                "sampleId",
                "carrier",
                "sourceReadback",
                "sourceObjectId",
                "ordinal",
                "readObjectId",
                "expectedContentType",
            ):
                entry[field] = check.get(field)
            entry["returnedObjectId"] = returned_id
            entry["returnedContentType"] = returned_type
            entry["responseDigest"] = "sha256:" + hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()
            entry["responseBytes"] = len(payload.encode("utf-8"))
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        results.append(entry)
        if not matched:
            detail = entry.get("semanticError")
            findings.append(
                f"{check['name']} failed: {status_code or 'ERR'} {check['url']}"
                + (f" ({detail})" if detail else "")
            )
    return {
        "schema": "environment-integration-probe-report",
        "status": "passed" if not findings else "failed",
        "env": args.env,
        "mode": mode,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "baseUrl": args.base_url.rstrip("/"),
        "productOpsBaseUrl": args.product_ops_base_url.rstrip("/"),
        "mediaImageBaseUrl": media_image_base_url.rstrip("/"),
        "releaseIdentity": release_identity or {},
        "requestTimeoutSeconds": request_timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "onlyChecks": sorted(only_checks),
        "requireNonEmptyContentFeed": require_non_empty_content_feed,
        "checks": results,
        "findings": findings,
    }


def main() -> int:
    args = parse_args()
    report = run_checks(args)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[environment-integration-probe] report: {report_path}")
    print(f"[environment-integration-probe] status: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
