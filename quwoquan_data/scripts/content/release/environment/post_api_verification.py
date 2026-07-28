"""Verify release-imported posts through the public content API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import yaml

from core.control_types import ContentType
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid
from content.release.environment.importers import assert_import_report_contract
from content.release.environment.public_api_client import (
    PublicApiClient,
    PublicApiClientError,
)
from content.release.model import DeploymentEnvironment


SERVICE_PAGINATION_CONTRACT_PATH = (
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/types.yaml"
)


class PostApiVerificationError(ValueError):
    """An imported post cannot be consumed through its public API."""


@dataclass(frozen=True)
class PostApiCase:
    post_ref: str
    post_id: str
    content_type: ContentType
    author_id: str
    source_attribution: Mapping[str, Any] | None


@dataclass(frozen=True)
class CreatorProfileCase:
    creator_ref: str
    author_id: str
    sub_account_id: str


def _required_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PostApiVerificationError(f"{endpoint} lacks required {field}")
    return value.strip()


def _object(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PostApiVerificationError(f"{label} must be an object")
    return value


def _normalized_post_ref(value: object) -> str:
    ref = str(value or "").strip().replace("\\", "/")
    if ref.startswith("posts/"):
        ref = ref.removeprefix("posts/")
    if not ref or ref.startswith("/") or ".." in ref.split("/"):
        raise PostApiVerificationError("post reference is invalid")
    return ref


def _post_feed_page_limit() -> int:
    try:
        document = yaml.safe_load(
            SERVICE_PAGINATION_CONTRACT_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise PostApiVerificationError(
            f"service pagination contract unreadable: {SERVICE_PAGINATION_CONTRACT_PATH}"
        ) from exc
    if not isinstance(document, Mapping):
        raise PostApiVerificationError("service pagination contract must be an object")
    types = _object(document.get("types"), label="service pagination types")
    pagination = _object(types.get("Pagination"), label="service pagination")
    fields = pagination.get("fields")
    if not isinstance(fields, list):
        raise PostApiVerificationError("service pagination fields must be an array")
    for field in fields:
        if not isinstance(field, Mapping) or field.get("name") != "limit":
            continue
        maximum = field.get("max")
        if isinstance(maximum, int) and maximum > 0:
            return maximum
    raise PostApiVerificationError("service pagination limit max is missing")


def _read_cases(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    release_root: Path,
    importer_report_path: Path,
    creator_importer_report_path: Path,
) -> tuple[list[PostApiCase], dict[str, CreatorProfileCase]]:
    try:
        desired = read_json(payload_file(release_root, "desired_state.json"))
        report = assert_import_report_contract(
            importer_report_path,
            expected_release_id=release_id,
        )
        creator_report = assert_import_report_contract(
            creator_importer_report_path,
            expected_release_id=release_id,
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        raise PostApiVerificationError(f"post import evidence is invalid: {exc}") from exc
    if desired.get("schema") != "quwoquan_data.release_desired_state":
        raise PostApiVerificationError("release desired state schema is invalid")
    if str(desired.get("releaseId") or "") != release_id:
        raise PostApiVerificationError("release desired state releaseId mismatch")
    if report.get("status") != "active":
        raise PostApiVerificationError("post importer report is not active")
    if creator_report.get("status") != "active":
        raise PostApiVerificationError("creator importer report is not active")
    if str(report.get("environment") or "") != environment.value:
        raise PostApiVerificationError("post importer report environment mismatch")
    desired_refs = _object(desired.get("desiredRefs"), label="release desiredRefs")
    expected = {
        _normalized_post_ref(value)
        for value in desired_refs.get("posts", [])
        if str(value or "").strip()
    }
    raw_creator_refs = desired_refs.get("creators", [])
    if not isinstance(raw_creator_refs, list):
        raise PostApiVerificationError("release desiredRefs.creators must be an array")
    creators_by_author: dict[str, CreatorProfileCase] = {}
    for raw_ref in raw_creator_refs:
        creator_ref = _normalized_post_ref(raw_ref)
        try:
            profile = _object(
                read_json(release_root / "payload" / "objects" / "creators" / creator_ref / "profile.json"),
                label=f"creator profile {creator_ref}",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise PostApiVerificationError(
                f"creator profile is unreadable for {creator_ref}: {exc}"
            ) from exc
        if profile.get("schema") != "quwoquan_data.creator_profile":
            raise PostApiVerificationError(f"creator profile schema is invalid: {creator_ref}")
        author_id = _required_text(profile, "authorId", endpoint=f"creator profile {creator_ref}")
        sub_account_id = _required_text(
            profile,
            "subAccountId",
            endpoint=f"creator profile {creator_ref}",
        )
        if author_id in creators_by_author:
            raise PostApiVerificationError(f"duplicate creator authorId: {author_id}")
        creators_by_author[author_id] = CreatorProfileCase(
            creator_ref=creator_ref,
            author_id=author_id,
            sub_account_id=sub_account_id,
        )
    imported_authors = creator_report.get("authorIds")
    if not isinstance(imported_authors, list) or {
        str(value).strip() for value in imported_authors if str(value).strip()
    } != set(creators_by_author):
        raise PostApiVerificationError(
            "creator importer receipt does not exactly match release creator profiles"
        )
    verified_creators = creator_report.get("verifiedCreatorIds")
    if (
        creator_report.get("projectionDatabase") != "quwoquan_user"
        or not isinstance(verified_creators, list)
        or {str(value).strip() for value in verified_creators if str(value).strip()}
        != {case.creator_ref for case in creators_by_author.values()}
    ):
        raise PostApiVerificationError(
            "creator importer readback does not exactly match release creator authority"
        )
    bindings = report.get("postBindings")
    if not isinstance(bindings, list):
        raise PostApiVerificationError("post importer report lacks postBindings")
    cases: list[PostApiCase] = []
    observed: set[str] = set()
    post_ids: set[str] = set()
    for index, raw in enumerate(bindings):
        row = _object(raw, label=f"post binding {index}")
        post_ref = _normalized_post_ref(row.get("postRef"))
        if post_ref in observed:
            raise PostApiVerificationError(f"duplicate imported post reference: {post_ref}")
        post_id = _required_text(row, "postId", endpoint=f"post binding {index}")
        if post_id in post_ids:
            raise PostApiVerificationError(f"duplicate imported post id: {post_id}")
        try:
            content_type = ContentType(
                _required_text(row, "contentType", endpoint=f"post binding {index}")
            )
        except ValueError as exc:
            raise PostApiVerificationError(
                f"post binding {index} has unsupported contentType"
            ) from exc
        if content_type is ContentType.HOMEPAGE:
            raise PostApiVerificationError("homepage is not a post API carrier")
        cases.append(
            PostApiCase(
                post_ref=post_ref,
                post_id=post_id,
                content_type=content_type,
                author_id=_required_text(row, "authorId", endpoint=f"post binding {index}"),
                source_attribution=_source_attribution(
                    release_root,
                    post_ref,
                    content_type=content_type,
                ),
            )
        )
        observed.add(post_ref)
        post_ids.add(post_id)
    if observed != expected:
        raise PostApiVerificationError("post importer bindings do not exactly match release desired state")
    missing_creators = sorted({case.author_id for case in cases} - set(creators_by_author))
    if missing_creators:
        raise PostApiVerificationError(
            f"post authors are not owned by the release creator import: {missing_creators[:3]}"
        )
    return sorted(cases, key=lambda case: case.post_ref), creators_by_author


def _source_attribution(
    release_root: Path,
    post_ref: str,
    *,
    content_type: ContentType,
) -> Mapping[str, Any] | None:
    path = (
        release_root
        / "payload"
        / "objects"
        / "posts"
        / post_ref
        / "manifest.json"
    )
    try:
        manifest = _object(read_json(path), label=f"post manifest {post_ref}")
    except (OSError, TypeError, ValueError) as exc:
        raise PostApiVerificationError(
            f"post manifest is unreadable for {post_ref}: {exc}"
        ) from exc
    raw = manifest.get("sourceAttribution")
    if raw is None:
        if content_type is ContentType.VIDEO:
            raise PostApiVerificationError(
                f"video manifest lacks sourceAttribution: {post_ref}"
            )
        return None
    return _object(raw, label=f"sourceAttribution {post_ref}")


def _require_media(
    payload: Mapping[str, Any],
    content_type: ContentType,
) -> tuple[list[str], str, str]:
    if content_type is ContentType.ARTICLE:
        _required_text(payload, "body", endpoint="article detail")
        return [], "", ""
    media_urls = payload.get("mediaUrls")
    urls = [
        str(url).strip()
        for url in media_urls
        if isinstance(url, str) and url.strip()
    ] if isinstance(media_urls, list) else []
    if not urls:
        raise PostApiVerificationError(f"{content_type.value} detail has no media URLs")
    cover_url = _required_text(payload, "coverUrl", endpoint=f"{content_type.value} detail")
    video_url = ""
    if content_type is ContentType.VIDEO:
        video_url = _required_text(payload, "videoUrl", endpoint="video detail")
    return urls, cover_url, video_url


def _verify_binary_media(
    client: PublicApiClient,
    url: str,
    *,
    expected_kind: str,
) -> None:
    response = client.get_bytes(url)
    if response.status not in {HTTPStatus.OK, HTTPStatus.PARTIAL_CONTENT}:
        raise PostApiVerificationError(
            f"public {expected_kind} media returned status={response.status}: {url}"
        )
    content_type = response.content_type.split(";", 1)[0].strip().lower()
    if not content_type.startswith(f"{expected_kind}/"):
        raise PostApiVerificationError(
            f"public media MIME mismatch for {url}: {response.content_type!r}"
        )
    if not response.body:
        raise PostApiVerificationError(f"public media returned empty bytes: {url}")
    if expected_kind == "video":
        if response.status != HTTPStatus.PARTIAL_CONTENT or not response.content_range.startswith(
            "bytes "
        ):
            raise PostApiVerificationError(
                f"public video does not honor byte ranges: {url}"
            )
        if b"ftyp" not in response.body[:64] and not response.body.startswith(
            b"\x1a\x45\xdf\xa3"
        ):
            raise PostApiVerificationError(
                f"public video first range is not a playable MP4/WebM header: {url}"
            )


def _verify_source_attribution(
    payload: Mapping[str, Any],
    case: PostApiCase,
) -> None:
    expected = case.source_attribution
    if expected is None:
        return
    actual = _object(
        payload.get("sourceAttribution"),
        label=f"post detail sourceAttribution {case.post_ref}",
    )
    fields = (
        "isOriginal",
        "originalCreatorName",
        "platform",
        "sourcePostUrl",
        "attributionText",
        "rightsBasis",
        "commercialAuthorizationStatus",
        "publicationAdmission",
        "watermarkStatus",
        "audioRightsStatus",
    )
    drifted = [
        field
        for field in fields
        if expected.get(field) is not None and actual.get(field) != expected.get(field)
    ]
    if drifted:
        raise PostApiVerificationError(
            f"post detail sourceAttribution drift for {case.post_ref}: {drifted}"
        )


def _verify_detail(client: PublicApiClient, case: PostApiCase) -> dict[str, Any]:
    response = client.get_json(f"content/posts/{quote(case.post_id, safe='')}")
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(f"post detail returned non-200 for {case.post_ref}")
    payload = response.payload
    if _required_text(payload, "postId", endpoint="post detail") != case.post_id:
        raise PostApiVerificationError(f"post detail id mismatch for {case.post_ref}")
    if _required_text(payload, "authorId", endpoint="post detail") != case.author_id:
        raise PostApiVerificationError(f"post detail author mismatch for {case.post_ref}")
    if _required_text(payload, "contentType", endpoint="post detail") != case.content_type.value:
        raise PostApiVerificationError(f"post detail content type mismatch for {case.post_ref}")
    media_urls, cover_url, video_url = _require_media(payload, case.content_type)
    _verify_source_attribution(payload, case)
    probed: set[str] = set()
    if cover_url:
        _verify_binary_media(client, cover_url, expected_kind="image")
        probed.add(cover_url)
    if video_url:
        _verify_binary_media(client, video_url, expected_kind="video")
        probed.add(video_url)
    expected_kind = "image" if case.content_type is ContentType.IMAGE else ""
    for url in media_urls:
        if url in probed:
            continue
        kind = expected_kind
        if not kind:
            continue
        _verify_binary_media(client, url, expected_kind=kind)
        probed.add(url)
    return {
        "detailStatus": response.status,
        "mediaReady": case.content_type is ContentType.ARTICLE or bool(probed),
        "mediaProbeCount": len(probed),
        "sourceAttributionReady": True,
    }


def _verify_author_profile(
    client: PublicApiClient,
    creator: CreatorProfileCase,
) -> int:
    response = client.get_json(f"user/{quote(creator.sub_account_id, safe='')}")
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(
            "creator public profile returned "
            f"status={response.status} for canonical "
            f"subAccountId={creator.sub_account_id} ({creator.creator_ref})"
        )
    if _required_text(response.payload, "subAccountId", endpoint="creator public profile") != creator.sub_account_id:
        raise PostApiVerificationError(
            f"creator public profile identity mismatch for {creator.creator_ref}"
        )
    if _required_text(response.payload, "displayName", endpoint="creator public profile") == "":
        raise PostApiVerificationError(
            f"creator public profile lacks display name for {creator.creator_ref}"
        )
    return response.status


def _verify_typed_feed(
    client: PublicApiClient,
    cases: list[PostApiCase],
) -> dict[str, int]:
    page_limit = _post_feed_page_limit()
    expected_by_type: dict[ContentType, dict[str, PostApiCase]] = {}
    for case in cases:
        expected_by_type.setdefault(case.content_type, {})[case.post_id] = case
    feed_status: dict[str, int] = {}
    for content_type, expected in expected_by_type.items():
        cursor = ""
        seen: set[str] = set()
        seen_cursors: set[str] = set()
        while len(seen) < len(expected):
            query = {"type": content_type.value, "limit": str(page_limit)}
            if cursor:
                query["cursor"] = cursor
            response = client.get_json("content/feed", query=query)
            if response.status != HTTPStatus.OK:
                raise PostApiVerificationError(
                    f"typed feed returned non-200 for {content_type.value}"
                )
            items = response.payload.get("items")
            if not isinstance(items, list):
                raise PostApiVerificationError("typed feed lacks items")
            for index, raw in enumerate(items):
                item = _object(raw, label=f"typed feed {content_type.value} item {index}")
                post_id = _required_text(item, "postId", endpoint="typed feed")
                expected_case = expected.get(post_id)
                if expected_case is None:
                    continue
                if _required_text(item, "authorId", endpoint="typed feed") != expected_case.author_id:
                    raise PostApiVerificationError(
                        f"typed feed author mismatch for {expected_case.post_ref}"
                    )
                if _required_text(item, "contentType", endpoint="typed feed") != content_type.value:
                    raise PostApiVerificationError(
                        f"typed feed content type mismatch for {expected_case.post_ref}"
                    )
                seen.add(post_id)
                feed_status[post_id] = response.status
            next_cursor = str(response.payload.get("nextCursor") or "").strip()
            if len(seen) == len(expected):
                break
            if not next_cursor or next_cursor in seen_cursors:
                missing = sorted(set(expected) - seen)
                raise PostApiVerificationError(
                    f"typed feed omitted imported {content_type.value} posts: {missing[:3]}"
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
    return feed_status


def write_post_api_verification(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    run_id: str,
    release_root: Path,
    importer_report_path: Path,
    creator_importer_report_path: Path,
    output_path: Path,
    api_base_url: str,
    insecure_tls: bool,
    resolve_host: str = "",
) -> Path:
    """Write schema-validated, release-bound public post API evidence."""
    try:
        client = PublicApiClient(
            base_url=api_base_url,
            insecure_tls=insecure_tls,
            resolve_host=resolve_host.strip(),
        )
        cases, creators_by_author = _read_cases(
            environment=environment,
            release_id=release_id,
            release_root=release_root,
            importer_report_path=importer_report_path,
            creator_importer_report_path=creator_importer_report_path,
        )
        feed_status = _verify_typed_feed(client, cases)
        rows = []
        for case in cases:
            detail = _verify_detail(client, case)
            author_profile_status = _verify_author_profile(
                client,
                creators_by_author[case.author_id],
            )
            rows.append(
                {
                    "postRef": case.post_ref,
                    "postId": case.post_id,
                    "contentType": case.content_type.value,
                    "authorId": case.author_id,
                    "detailStatus": detail["detailStatus"],
                    "feedStatus": feed_status[case.post_id],
                    "mediaReady": detail["mediaReady"],
                    "mediaProbeCount": detail["mediaProbeCount"],
                    "sourceAttributionReady": detail["sourceAttributionReady"],
                    "authorProfileStatus": author_profile_status,
                }
            )
    except PublicApiClientError as exc:
        raise PostApiVerificationError(str(exc)) from exc
    try:
        importer_ref = importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
        creator_importer_ref = creator_importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise PostApiVerificationError("post importer report must be below QWQ_OUTPUT_ROOT") from exc
    payload = {
        "schema": "quwoquan_data.post_api_verification",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "sourceImportReportRef": importer_ref,
        "creatorImportReportRef": creator_importer_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "posts": rows,
        "issues": [],
    }
    if resolve_host:
        payload["apiResolveHost"] = resolve_host
    try:
        assert_valid(payload, "release", "post_api_verification", label="post_api_verification")
    except (TypeError, ValueError) as exc:
        raise PostApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise PostApiVerificationError(f"post API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = ["PostApiVerificationError", "write_post_api_verification"]
