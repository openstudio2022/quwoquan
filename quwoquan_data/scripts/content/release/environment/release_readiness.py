"""Build the single Data-owned receipt consumed by environment readiness gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from content.release.environment.app_uat_envelope import (
    AppUatEnvelopeError,
    build_app_uat_envelope,
)
from content.release.model import DataSourceOwner, ReleaseKind
from core.io import read_json, write_json
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid


class EnvironmentReleaseReadinessError(ValueError):
    """Release/environment evidence cannot support a commercial readiness claim."""


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise EnvironmentReleaseReadinessError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, Mapping):
        raise EnvironmentReleaseReadinessError(f"{label} must be an object: {path}")
    return dict(value)


def _sorted_strings(value: object, *, label: str, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise EnvironmentReleaseReadinessError(f"{label} must be an array")
    result = sorted(str(item).strip() for item in value if str(item).strip())
    if len(result) != len(value) or len(result) != len(set(result)):
        raise EnvironmentReleaseReadinessError(f"{label} must contain unique non-empty strings")
    if nonempty and not result:
        raise EnvironmentReleaseReadinessError(f"{label} must not be empty")
    return result


def _relative(path: Path, *, output_root: Path, label: str) -> str:
    try:
        return path.relative_to(output_root).as_posix()
    except ValueError as exc:
        raise EnvironmentReleaseReadinessError(f"{label} must be below QWQ_OUTPUT_ROOT") from exc


def _checksum(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def write_environment_release_readiness(
    *,
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    release_root: Path,
    import_report_path: Path,
    creator_import_report_path: Path,
    tag_consumer_verification_path: Path,
    homepage_api_verification_path: Path,
    post_api_verification_path: Path,
    output_root: Path,
    output_path: Path,
    readiness_phase: str = "commercial",
) -> Path:
    """Write append-only, release-bound proof for Ops readiness composition."""
    if readiness_phase not in {"research", "consumer", "commercial"}:
        raise EnvironmentReleaseReadinessError(
            "readiness_phase must be research, consumer or commercial"
        )

    header_path = payload_file(release_root, "release.json")
    desired_path = payload_file(release_root, "desired_state.json")
    media_manifest_path = payload_file(release_root, "media_manifest.json")
    asset_admission_path = payload_file(release_root, "asset_admission.json")
    attestation_path = attestation_root(release_root) / "release.json"
    header = _object(header_path, label="release header")
    desired = _object(desired_path, label="release desired state")
    media_manifest = _object(media_manifest_path, label="release media manifest")
    asset_admission = _object(
        asset_admission_path,
        label="release asset admission",
    )
    attestation = _object(attestation_path, label="release attestation")
    import_report = _object(import_report_path, label="content import report")
    creator_report = _object(creator_import_report_path, label="creator import report")
    tag_report = _object(tag_consumer_verification_path, label="tag consumer verification")
    homepage_report = _object(homepage_api_verification_path, label="homepage API verification")
    post_report = _object(post_api_verification_path, label="post API verification")
    for document, schema_name, label in (
        (header, "release_header", "release header"),
        (desired, "release_desired_state", "release desired state"),
        (attestation, "release_attestation", "release attestation"),
        (media_manifest, "media_manifest", "release media manifest"),
        (asset_admission, "release_asset_admission", "release asset admission"),
        (import_report, "import_report", "content import report"),
        (creator_report, "creator_import_report", "creator import report"),
        (tag_report, "tag_consumer_verification", "tag consumer verification"),
        (homepage_report, "homepage_api_verification", "homepage API verification"),
        (post_report, "post_api_verification", "post API verification"),
    ):
        try:
            assert_valid(document, "release", schema_name, label=label)
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise EnvironmentReleaseReadinessError(str(exc)) from exc
    if any(
        document.get("releaseId") != release_id
        for document in (
            header,
            desired,
            attestation,
            media_manifest,
            asset_admission,
            import_report,
            creator_report,
            tag_report,
            homepage_report,
            post_report,
        )
    ):
        raise EnvironmentReleaseReadinessError("readiness evidence releaseId drift")
    if header.get("releaseKind") != ReleaseKind.CONTENT:
        raise EnvironmentReleaseReadinessError("readiness receipt requires a content release")
    release_class = str(header.get("releaseClass") or "")
    product_lifecycle_state = str(header.get("productLifecycleState") or "")
    expected_release_class = "research" if readiness_phase == "research" else "commercial" if readiness_phase == "commercial" else release_class
    if readiness_phase in {"research", "commercial"} and (
        release_class != expected_release_class
        or product_lifecycle_state != expected_release_class
    ):
        raise EnvironmentReleaseReadinessError(
            "readiness phase drifts from immutable release lifecycle"
        )
    lifecycle_fields = (
        "releaseClass",
        "productLifecycleState",
        "containsUnverifiedAssets",
        "rightsStatusCounts",
        "authorizationRequiredAssetIds",
        "researchAcceptedCount",
        "commercialAcceptedCount",
    )
    if any(
        document.get(field) != header.get(field)
        for document in (attestation, asset_admission)
        for field in lifecycle_fields
    ):
        raise EnvironmentReleaseReadinessError(
            "release lifecycle/admission projection drift"
        )
    if readiness_phase == "commercial" and (
        header.get("containsUnverifiedAssets") is not False
        or header.get("authorizationRequiredAssetIds") != []
    ):
        raise EnvironmentReleaseReadinessError(
            "commercial readiness cannot contain authorization-required assets"
        )
    if (
        header.get("sourceOwner") != DataSourceOwner.QWQ_DATA
        or attestation.get("sourceOwner") != DataSourceOwner.QWQ_DATA
        or media_manifest.get("sourceOwner") != DataSourceOwner.QWQ_DATA
        or import_report.get("sourceOwner") != DataSourceOwner.QWQ_DATA
        or creator_report.get("sourceOwner") != DataSourceOwner.QWQ_DATA
    ):
        raise EnvironmentReleaseReadinessError("readiness evidence sourceOwner drift")
    if any(
        document.get("environment") != environment
        for document in (import_report, creator_report, tag_report, homepage_report, post_report)
    ):
        raise EnvironmentReleaseReadinessError("readiness evidence environment drift")

    desired_refs = desired.get("desiredRefs")
    if not isinstance(desired_refs, Mapping):
        raise EnvironmentReleaseReadinessError("release desiredRefs must be an object")
    entity_refs = _sorted_strings(desired_refs.get("entities"), label="desired entities")
    post_refs = _sorted_strings(desired_refs.get("posts"), label="desired posts")
    creator_ids = _sorted_strings(desired_refs.get("creators"), label="desired creators")
    tag_refs = _sorted_strings(desired_refs.get("tags"), label="desired tags")

    bindings = import_report.get("postBindings")
    if not isinstance(bindings, list):
        raise EnvironmentReleaseReadinessError("content import postBindings must be an array")
    binding_refs = sorted(str(row.get("postRef") or "") for row in bindings if isinstance(row, Mapping))
    post_ids = sorted(str(row.get("postId") or "") for row in bindings if isinstance(row, Mapping))
    if binding_refs != post_refs or not post_ids or len(post_ids) != len(set(post_ids)):
        raise EnvironmentReleaseReadinessError("content import bindings drift from release posts")
    if creator_report.get("verifiedCreatorIds") != creator_ids:
        raise EnvironmentReleaseReadinessError("creator attribution drifts from release creators")
    if tag_report.get("tagRefs") != tag_refs or tag_report.get("passed") is not True:
        raise EnvironmentReleaseReadinessError("tag attribution drifts from release tags")
    if homepage_report.get("passed") is not True or sorted(
        str(row.get("entityRef") or "")
        for row in homepage_report.get("entities") or []
        if isinstance(row, Mapping)
    ) != entity_refs:
        raise EnvironmentReleaseReadinessError("homepage verification drifts from release entities")
    verified_post_ids = sorted(
        str(row.get("postId") or "")
        for row in post_report.get("posts") or []
        if isinstance(row, Mapping)
    )
    if post_report.get("passed") is not True or verified_post_ids != post_ids:
        raise EnvironmentReleaseReadinessError("post verification drifts from imported postIds")
    if post_report.get("readinessPhase") != readiness_phase:
        raise EnvironmentReleaseReadinessError(
            "post verification readinessPhase drift"
        )
    if any(
        not isinstance(row, Mapping)
        or not isinstance(row.get("mediaProbes"), list)
        or row.get("mediaProbeCount") != len(row.get("mediaProbes") or [])
        for row in post_report.get("posts") or []
    ):
        raise EnvironmentReleaseReadinessError(
            "post media probe count drifts from typed evidence"
        )
    creator_evidence = [
        row
        for row in post_report.get("creators") or []
        if isinstance(row, Mapping)
    ]
    verified_creator_refs = sorted(
        str(row.get("creatorRef") or "") for row in creator_evidence
    )
    avatar_asset_ids = sorted(
        str(row.get("avatarAssetId") or "") for row in creator_evidence
    )
    if (
        verified_creator_refs != creator_ids
        or not avatar_asset_ids
        or any(not item for item in avatar_asset_ids)
        or len(avatar_asset_ids) != len(set(avatar_asset_ids))
        or any(
            row.get("profileStatus") != 200
            or row.get("avatarMediaReady") is not True
            or row.get("avatarProbeCount") != 1
            for row in creator_evidence
        )
    ):
        raise EnvironmentReleaseReadinessError(
            "creator avatar verification drifts from release creators"
        )

    feed_queries = post_report.get("feedQueries")
    if not isinstance(feed_queries, list):
        raise EnvironmentReleaseReadinessError("post verification lacks feedQueries")
    guest_actor_hash = str(post_report.get("guestActorHash") or "").strip()
    guest_login = post_report.get("guestLogin")
    if not guest_actor_hash or not isinstance(guest_login, Mapping):
        raise EnvironmentReleaseReadinessError(
            "post verification lacks fresh guest identity evidence"
        )
    queries_by_name = {
        str(row.get("name") or ""): row
        for row in feed_queries
        if isinstance(row, Mapping)
    }
    required_query_names = {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
    }
    if readiness_phase in {"research", "commercial"}:
        required_query_names.add("premium_stream")
    if set(queries_by_name) != required_query_names:
        raise EnvironmentReleaseReadinessError(
            "feedQueries do not match the declared readiness phase"
        )
    video_ids = {
        str(row.get("postId") or "")
        for row in bindings
        if isinstance(row, Mapping) and row.get("contentType") == "video"
    }
    typed_video_ids = set(queries_by_name.get("typed_video", {}).get("matchedPostIds") or [])
    discovery_ids = set(queries_by_name.get("discovery_work", {}).get("matchedPostIds") or [])
    premium_ids = set(queries_by_name.get("premium_stream", {}).get("matchedPostIds") or [])
    release_post_ids = set(post_ids)
    discovery_release_ids = discovery_ids & release_post_ids
    if not discovery_release_ids:
        raise EnvironmentReleaseReadinessError(
            "identity=work does not prove a release-bound discovery postId"
        )
    if not video_ids or not typed_video_ids or not typed_video_ids.issubset(video_ids):
        raise EnvironmentReleaseReadinessError(
            "identity=work&type=video does not prove a release-bound video postId"
        )
    if readiness_phase in {"research", "commercial"}:
        if not premium_ids or not premium_ids.issubset(release_post_ids):
            raise EnvironmentReleaseReadinessError(
                "premium_stream does not prove a release-bound postId"
            )
    verified_playable_video_ids = {
        str(row.get("postId") or "")
        for row in post_report.get("posts") or []
        if isinstance(row, Mapping)
        and row.get("contentType") == "video"
        and row.get("detailStatus") == 200
        and row.get("mediaReady") is True
        and int(row.get("mediaProbeCount") or 0) >= 2
    }
    premium_playable_video_ids = premium_ids & video_ids & verified_playable_video_ids
    if readiness_phase in {"research", "commercial"} and not premium_playable_video_ids:
        raise EnvironmentReleaseReadinessError(
            "premium_stream does not expose a release-bound video with a playable media probe"
        )

    app_uat_envelope = None
    if readiness_phase in {"research", "commercial"}:
        try:
            app_uat_envelope = build_app_uat_envelope(
                release_root=release_root,
                release_id=release_id,
                entity_refs=entity_refs,
                post_refs=post_refs,
                creator_ids=creator_ids,
                tag_refs=tag_refs,
                bindings=bindings,
                homepage_report=homepage_report,
                queries_by_name=queries_by_name,
                verified_playable_video_ids=verified_playable_video_ids,
                release_class=release_class,
                product_lifecycle_state=product_lifecycle_state,
            )
        except AppUatEnvelopeError as exc:
            raise EnvironmentReleaseReadinessError(str(exc)) from exc

    assets = media_manifest.get("assets")
    if not isinstance(assets, list):
        raise EnvironmentReleaseReadinessError("release media manifest assets must be an array")
    media_asset_ids = sorted(
        str(row.get("assetId") or "") for row in assets if isinstance(row, Mapping)
    )
    if not media_asset_ids or any(not item for item in media_asset_ids) or len(media_asset_ids) != len(set(media_asset_ids)):
        raise EnvironmentReleaseReadinessError("release media assetIds must be unique and non-empty")
    verified_image_asset_ids = {
        str(probe.get("assetId") or "")
        for row in post_report.get("posts") or []
        if isinstance(row, Mapping)
        for probe in row.get("mediaProbes") or []
        if isinstance(probe, Mapping)
        and probe.get("kind") == "image"
        and probe.get("status") == 200
        and str(probe.get("mimeType") or "").startswith("image/")
        and probe.get("hashVerified") is True
        and probe.get("sha256") == probe.get("expectedSha256")
        and probe.get("bytes") == probe.get("expectedBytes")
    }
    if (
        not verified_image_asset_ids
        or "" in verified_image_asset_ids
        or not verified_image_asset_ids.issubset(set(media_asset_ids))
    ):
        raise EnvironmentReleaseReadinessError(
            "release image delivery lacks hash-bound public evidence"
        )
    actual_payload_digest = payload_digest(release_root)
    if attestation.get("payloadSha256") != actual_payload_digest:
        raise EnvironmentReleaseReadinessError("attestation payloadSha256 drift")
    if import_report.get("manifestDigest") != actual_payload_digest:
        raise EnvironmentReleaseReadinessError(
            "content import manifestDigest drift from immutable payload"
        )
    media_manifest_digest = f"sha256:{hashlib.sha256(media_manifest_path.read_bytes()).hexdigest()}"

    document: dict[str, Any] = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": ReleaseKind.CONTENT,
        "sourceOwner": DataSourceOwner.QWQ_DATA,
        "releaseClass": release_class,
        "productLifecycleState": product_lifecycle_state,
        "containsUnverifiedAssets": bool(
            header.get("containsUnverifiedAssets")
        ),
        "rightsStatusCounts": dict(header.get("rightsStatusCounts") or {}),
        "authorizationRequiredAssetIds": list(
            header.get("authorizationRequiredAssetIds") or []
        ),
        "researchAcceptedCount": int(header.get("researchAcceptedCount") or 0),
        "commercialAcceptedCount": int(
            header.get("commercialAcceptedCount") or 0
        ),
        "readinessPhase": readiness_phase,
        "manifestDigest": actual_payload_digest,
        "mediaManifestDigest": media_manifest_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "guestActorHash": guest_actor_hash,
        "guestLogin": dict(guest_login),
        "counts": {
            "entities": len(entity_refs),
            "posts": len(post_ids),
            "creators": len(creator_ids),
            "avatarAssets": len(avatar_asset_ids),
            "imageAssets": len(verified_image_asset_ids),
            "tags": len(tag_refs),
            "mediaAssets": len(media_asset_ids),
            "discoveryPosts": len(discovery_release_ids),
            "premiumPlayableVideos": len(premium_playable_video_ids),
        },
        "entityRefs": entity_refs,
        "postIds": post_ids,
        "creatorIds": creator_ids,
        "tagRefs": tag_refs,
        "mediaAssetIds": media_asset_ids,
        "feedQueries": feed_queries,
        "contentImportReportRef": _relative(import_report_path, output_root=output_root, label="content import report"),
        "creatorAttributionRef": _relative(creator_import_report_path, output_root=output_root, label="creator attribution"),
        "tagAttributionRef": _relative(tag_consumer_verification_path, output_root=output_root, label="tag attribution"),
        "homepageApiVerificationRef": _relative(homepage_api_verification_path, output_root=output_root, label="homepage API verification"),
        "postApiVerificationRef": _relative(post_api_verification_path, output_root=output_root, label="post API verification"),
        "mediaManifestRef": _relative(media_manifest_path, output_root=output_root, label="media manifest"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
    }
    if app_uat_envelope is not None:
        document["appUatEnvelope"] = app_uat_envelope
    document["verificationChecksum"] = _checksum(document)
    try:
        assert_valid(
            document,
            "release",
            "environment_release_readiness",
            label="environment release readiness",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise EnvironmentReleaseReadinessError(str(exc)) from exc
    if output_path.exists():
        raise EnvironmentReleaseReadinessError(
            f"environment release readiness already exists: {output_path}"
        )
    write_json(output_path, document)
    return output_path


__all__ = [
    "EnvironmentReleaseReadinessError",
    "write_environment_release_readiness",
]
