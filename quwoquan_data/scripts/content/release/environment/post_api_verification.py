"""Verify release-imported posts through the public content API."""
from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from content.release.environment.post_api_feed_verification import (
    _verify_typed_feed,
)
from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    ReleaseMediaAssetCase,
    _optional_text,
    _public_media_path,
    _require_media,
    _required_text,
    _verify_binary_media,
    _verify_research_denied_media,
    _verify_source_attribution,
)
from content.release.environment.post_api_projection_verification import (
    verify_search_projection as _verify_search_projection,
)
from content.release.environment.post_api_release_cases import (
    CreatorProfileCase,
    read_post_and_creator_cases,
)
from content.release.environment.public_api_client import (
    PublicApiClient,
    PublicApiClientError,
)
from content.release.model import DeploymentEnvironment
from core.control_types import ContentType
from core.io import write_json
from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from verify.release_publishability import readiness_phase_issue

POST_DETAIL_PAGE_ID = "content.post.get"
USER_PROFILE_PAGE_ID = "user.profile"
ORIGINAL_ACCESS_PAGE_ID = "content.media.original_access"


def _research_consumer_credential(
    *,
    environment: str,
    release_id: str,
    run_id: str,
) -> dict[str, str]:
    """经 stackctl 签发 research 消费凭证；凭证只在进程内存传递。"""
    command = [
        "python3",
        str(REPO_ROOT / "quwoquan_ops/cli/stackctl.py"),
        "--output-format",
        "json",
        "research-consumer-credential",
        "--env",
        environment,
        "--release-id",
        release_id,
        "--verify-run-id",
        run_id,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=active_runtime_policy().research_credential_issuance_timeout_seconds,
            check=False,
            cwd=str(REPO_ROOT),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PostApiVerificationError(
            f"research consumer credential issuance failed to run: {exc}"
        ) from exc
    try:
        result = json.loads(completed.stdout or "{}")
    except ValueError as exc:
        raise PostApiVerificationError(
            "research consumer credential issuance returned invalid JSON"
        ) from exc
    if completed.returncode != 0 or result.get("exitCode") != 0:
        raise PostApiVerificationError(
            "DATA.RESEARCH.CONSUMER_CREDENTIAL_UNAVAILABLE: "
            f"{result.get('details') or completed.stderr.strip() or 'issuance failed'}"
        )
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        raise PostApiVerificationError(
            "research consumer credential issuance lacks evidence"
        )
    bearer_token = str(evidence.get("bearerToken") or "").strip()
    subject_hash = str(evidence.get("subjectHash") or "").strip()
    if not bearer_token or not subject_hash:
        raise PostApiVerificationError(
            "research consumer credential evidence lacks bearerToken/subjectHash"
        )
    return {"bearerToken": bearer_token, "subjectHash": subject_hash}


def _research_signed_media_probe(
    client: PublicApiClient,
    asset: ReleaseMediaAssetCase,
) -> dict[str, Any]:
    """采样一次原图短签授权并按 release 权威校验取回字节。"""
    issuance_path = (
        f"content/media/{quote(asset.asset_id, safe='')}/original:access"
    )
    response = client.post_json(
        issuance_path,
        page_id=ORIGINAL_ACCESS_PAGE_ID,
        body={"mediaId": asset.asset_id, "purpose": "view"},
        extra_headers={"Idempotency-Key": f"readiness-{uuid.uuid4().hex}"},
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(
            "research signed media issuance returned "
            f"status={response.status} for {asset.asset_id}"
        )
    original_url = _required_text(
        response.payload,
        "originalUrl",
        endpoint="research signed media issuance",
    )
    if not urlsplit(original_url).query:
        raise PostApiVerificationError(
            f"research signed media URL lacks a signature: {asset.asset_id}"
        )
    return _verify_binary_media(
        client,
        original_url,
        expected_kind="image",
        expected_bytes=asset.expected_bytes,
        expected_sha256=asset.expected_sha256,
        expected_mime_type=asset.expected_mime_type,
        evidence_policy="private_target",
    )


def _verify_detail(
    client: PublicApiClient,
    case: PostApiCase,
    creator: CreatorProfileCase,
    *,
    media_origin: str = "",
    signed_sample_asset_id: str = "",
) -> dict[str, Any]:
    response = client.get_json(
        f"content/posts/{quote(case.post_id, safe='')}",
        page_id=POST_DETAIL_PAGE_ID,
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(f"post detail returned non-200 for {case.post_ref}")
    payload = response.payload
    if _required_text(payload, "postId", endpoint="post detail") != case.post_id:
        raise PostApiVerificationError(f"post detail id mismatch for {case.post_ref}")
    if _required_text(payload, "authorId", endpoint="post detail") != case.author_id:
        raise PostApiVerificationError(f"post detail author mismatch for {case.post_ref}")
    if (
        _required_text(payload, "authorDisplayName", endpoint="post detail")
        != creator.display_name
    ):
        raise PostApiVerificationError(
            f"post detail author display name mismatch for {case.post_ref}"
        )
    detail_avatar_url = (
        _required_text(payload, "authorAvatarUrl", endpoint="post detail")
        if creator.avatar_url
        else _optional_text(payload, "authorAvatarUrl", endpoint="post detail")
    )
    if _public_media_path(detail_avatar_url) != _public_media_path(creator.avatar_url):
        raise PostApiVerificationError(
            f"post detail author avatar mismatch for {case.post_ref}"
        )
    if _required_text(payload, "contentType", endpoint="post detail") != case.content_type.value:
        raise PostApiVerificationError(f"post detail content type mismatch for {case.post_ref}")
    if _required_text(payload, "contentIdentity", endpoint="post detail") != "work":
        raise PostApiVerificationError(f"post detail content identity mismatch for {case.post_ref}")
    media_urls, cover_url, video_url = _require_media(payload, case.content_type)
    _verify_source_attribution(payload, case)
    observed_urls = {url for url in (*media_urls, cover_url, video_url) if url}
    expected_urls = {asset.public_url for asset in case.media_assets}
    if case.content_type is not ContentType.ARTICLE and observed_urls != expected_urls:
        raise PostApiVerificationError(
            f"post media URLs drift from release authority for {case.post_ref}"
        )
    probes: list[dict[str, Any]] = []
    for asset in case.media_assets:
        if asset.delivery_ref:
            # research：私有交付资产逐个证明匿名不可达；对采样资产附加一次
            # 原图短签取回校验（配额窗口内只采样一次，避免撞 grant 限额）。
            probe = _verify_research_denied_media(
                client,
                media_origin=media_origin,
                asset=asset,
            )
            if asset.asset_id == signed_sample_asset_id:
                probe["signedProbe"] = _research_signed_media_probe(client, asset)
            probes.append(probe)
            continue
        full_identity = asset.kind == "image"
        probe = _verify_binary_media(
            client,
            asset.public_url,
            expected_kind="video" if asset.kind == "video" else "image",
            expected_bytes=asset.expected_bytes if full_identity else 0,
            expected_sha256=asset.expected_sha256 if full_identity else "",
            expected_mime_type=asset.expected_mime_type,
        )
        probes.append(
            {
                "assetId": asset.asset_id,
                "kind": asset.kind,
                "expectedBytes": asset.expected_bytes,
                "expectedSha256": asset.expected_sha256,
                **probe,
            }
        )
    return {
        "detailStatus": response.status,
        "mediaReady": case.content_type is ContentType.ARTICLE or bool(probes),
        "mediaProbeCount": len(probes),
        "mediaProbes": probes,
        "sourceAttributionReady": True,
    }


def _verify_author_profile(
    client: PublicApiClient,
    creator: CreatorProfileCase,
) -> dict[str, Any]:
    response = client.get_json(
        f"user/{quote(creator.persona_id, safe='')}",
        page_id=USER_PROFILE_PAGE_ID,
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(
            "creator public profile returned "
            f"status={response.status} for canonical "
            f"personaId={creator.persona_id} ({creator.creator_ref})"
        )
    if _required_text(response.payload, "personaId", endpoint="creator public profile") != creator.persona_id:
        raise PostApiVerificationError(
            f"creator public profile identity mismatch for {creator.creator_ref}"
        )
    if _required_text(response.payload, "displayName", endpoint="creator public profile") == "":
        raise PostApiVerificationError(
            f"creator public profile lacks display name for {creator.creator_ref}"
        )
    avatar_url = _optional_text(
        response.payload,
        "avatarUrl",
        endpoint="creator public profile",
    )
    # Persona public profiles append ?v=<avatarVersion> for cache busting; the
    # release authority binds the public slice path without that query.
    if _public_media_path(avatar_url) != _public_media_path(creator.avatar_url):
        raise PostApiVerificationError(
            f"creator public avatar URL drift for {creator.creator_ref}"
        )
    if creator.avatar_asset_id is None:
        if avatar_url:
            raise PostApiVerificationError(
                f"creator public avatar unexpectedly exists for {creator.creator_ref}"
            )
        return {
            "creatorRef": creator.creator_ref,
            "authorId": creator.author_id,
            "personaId": creator.persona_id,
            "profileStatus": response.status,
            "avatarAssetId": None,
            "avatarUrl": "",
            "avatarMediaReady": False,
            "avatarProbeCount": 0,
            "avatarProbe": None,
            "usesPlatformDefaultAvatar": True,
        }
    if (
        creator.avatar_bytes is None
        or creator.avatar_sha256 is None
        or creator.avatar_mime_type is None
    ):
        raise PostApiVerificationError(
            f"creator avatar authority is incomplete for {creator.creator_ref}"
        )
    if not creator.avatar_url.startswith("https://"):
        # research 私有交付 avatar：回读与权威的相对 CAS key 一致即绪；
        # 匿名不可达由 post 私有媒体探测与边缘守卫覆盖，不再按资产取回。
        return {
            "creatorRef": creator.creator_ref,
            "authorId": creator.author_id,
            "personaId": creator.persona_id,
            "profileStatus": response.status,
            "avatarAssetId": creator.avatar_asset_id,
            "avatarUrl": creator.avatar_url,
            "avatarMediaReady": True,
            "avatarProbeCount": 0,
            "avatarProbe": None,
            "usesPlatformDefaultAvatar": False,
        }
    avatar_probe = _verify_binary_media(
        client,
        avatar_url,
        expected_kind="image",
        expected_bytes=creator.avatar_bytes,
        expected_sha256=creator.avatar_sha256,
        expected_mime_type=creator.avatar_mime_type,
    )
    return {
        "creatorRef": creator.creator_ref,
        "authorId": creator.author_id,
        "personaId": creator.persona_id,
        "profileStatus": response.status,
        "avatarAssetId": creator.avatar_asset_id,
        "avatarUrl": avatar_url,
        "avatarMediaReady": True,
        "avatarProbeCount": 1,
        "avatarProbe": avatar_probe,
        "usesPlatformDefaultAvatar": False,
    }


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
    media_delivery_base_url: str,
    ssl_cafile: str = "",
    readiness_phase: str = "commercial",
) -> Path:
    """Write schema-validated, release-bound public post API evidence."""
    phase_issue = readiness_phase_issue(readiness_phase)
    if phase_issue is not None:
        raise PostApiVerificationError(f"post API verification {phase_issue}")
    research = readiness_phase == "research"
    try:
        cases, creators_by_author = read_post_and_creator_cases(
            environment=environment,
            release_id=release_id,
            release_root=release_root,
            importer_report_path=importer_report_path,
            creator_importer_report_path=creator_importer_report_path,
            media_delivery_base_url=media_delivery_base_url,
            readiness_phase=readiness_phase,
        )
        media_origin = media_delivery_base_url.rstrip("/")
        guest = None
        internal_subject_hash = ""
        signed_sample_asset_id = ""
        if research:
            # research 证据禁止匿名 guest；消费身份是受保护白名单研究账号，
            # 凭证经 stackctl 进程内存签发（DEC-032 能力面之内的消费核验）。
            credential = _research_consumer_credential(
                environment=environment.value,
                release_id=release_id,
                run_id=run_id,
            )
            internal_subject_hash = credential["subjectHash"]
            client = PublicApiClient(
                base_url=api_base_url,
                bearer_token=credential["bearerToken"],
                ssl_cafile=ssl_cafile,
            )
            signed_sample_asset_id = min(
                (
                    asset.asset_id
                    for case in cases
                    for asset in case.media_assets
                    if asset.kind == "image" and asset.delivery_ref
                ),
                default="",
            )
        else:
            unauthenticated_client = PublicApiClient(
                base_url=api_base_url,
                ssl_cafile=ssl_cafile,
            )
            guest = unauthenticated_client.login_fresh_guest()
            client = unauthenticated_client.for_guest(guest)
        feed_status, feed_queries = _verify_typed_feed(
            client,
            cases,
            creators_by_author,
            # App 视频书唯一消费 premium_stream 池；全部 readiness phase 都必须
            # 证明 premium_stream release-bound 非空读回（environment-topology-
            # and-packaging spec），否则 typed_video 绿会被误当成视频书绿。
            include_premium_stream=True,
        )
        creator_rows = [
            _verify_author_profile(client, creator)
            for creator in sorted(
                creators_by_author.values(),
                key=lambda item: item.creator_ref,
            )
        ]
        creator_status_by_author = {
            str(row["authorId"]): int(row["profileStatus"])
            for row in creator_rows
        }
        search_queries = _verify_search_projection(
            client,
            release_root=release_root,
            cases=cases,
            creators_by_author=creators_by_author,
        )
        rows = []
        for case in cases:
            detail = _verify_detail(
                client,
                case,
                creators_by_author[case.author_id],
                media_origin=media_origin,
                signed_sample_asset_id=signed_sample_asset_id,
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
                    "mediaProbes": detail["mediaProbes"],
                    "sourceAttributionReady": detail["sourceAttributionReady"],
                    "authorProfileStatus": creator_status_by_author[case.author_id],
                }
            )
    except PublicApiClientError as exc:
        raise PostApiVerificationError(str(exc)) from exc
    try:
        importer_ref = importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
        creator_importer_ref = creator_importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise PostApiVerificationError("post importer report must be below QWQ_OUTPUT_ROOT") from exc
    identity_evidence: dict[str, Any] = (
        {"internalSubjectHash": internal_subject_hash}
        if research
        else {
            "guestActorHash": guest.guest_actor_hash,
            "guestLogin": guest.login_operation.as_payload(),
        }
    )
    payload = {
        "schema": "quwoquan_data.post_api_verification",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "readinessPhase": readiness_phase,
        "sourceImportReportRef": importer_ref,
        "creatorImportReportRef": creator_importer_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "mediaDeliveryBaseUrl": media_delivery_base_url.rstrip("/"),
        **identity_evidence,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "feedQueries": feed_queries,
        "searchQueries": search_queries,
        "creators": creator_rows,
        "posts": rows,
        "issues": [],
    }
    try:
        assert_valid(payload, "release", "post_api_verification", label="post_api_verification")
    except (TypeError, ValueError) as exc:
        raise PostApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise PostApiVerificationError(f"post API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = ["PostApiVerificationError", "write_post_api_verification"]
