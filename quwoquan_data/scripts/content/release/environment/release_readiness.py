"""Build the single Data-owned receipt consumed by environment readiness gates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.release_header import validate_release_header
from content.release.environment.activation_envelope import (
    EnvironmentActivationEnvelopeError,
    build_release_activation_envelope,
    document_digest,
    file_digest,
)
from content.release.environment.activation_predecessor import (
    previous_environment_activation_for_release,
)
from content.release.environment.app_uat_envelope import (
    AppUatEnvelopeError,
    build_app_uat_envelope,
)
from content.release.environment.release_readiness_closure import (
    ReleaseReadinessClosureError,
    validate_readiness_closure,
)
from content.release.environment.research_isolation_verification import (
    ResearchIsolationVerificationError,
    load_research_isolation_verification,
    research_isolation_file_digest,
)
from content.release.model import DataSourceOwner, ReleaseKind
from core.io import read_json, write_json
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from verify.release_publishability import (
    phase_lifecycle_alignment_issue,
    readiness_phase_issue,
)


class EnvironmentReleaseReadinessError(ValueError):
    """Release/environment evidence cannot support a commercial readiness claim."""


def _release_source_identity_fields(header: Mapping[str, Any]) -> tuple[str, ...]:
    if "sourceIdentities" in header or "sourceIdentitySetDigest" in header:
        return ("sourceIdentities", "sourceIdentitySetDigest")
    return ("sourceRevision", "sourceDigest", "entityCatalogDigest")


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
    research_isolation_verification_path: Path | None = None,
    previous_environment_readiness_path: Path | None = None,
    readiness_phase: str = "commercial",
) -> Path:
    """Write append-only, release-bound proof for Ops readiness composition."""
    phase_issue = readiness_phase_issue(readiness_phase)
    if phase_issue is not None:
        raise EnvironmentReleaseReadinessError(phase_issue)

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
            if schema_name == "release_header":
                validate_release_header(document, label=label)
            else:
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
    actual_payload_digest = payload_digest(release_root)
    if header.get("releaseKind") != ReleaseKind.CONTENT:
        raise EnvironmentReleaseReadinessError("readiness receipt requires a content release")
    release_class = str(header.get("releaseClass") or "")
    product_lifecycle_state = str(header.get("productLifecycleState") or "")
    alignment_issue = phase_lifecycle_alignment_issue(
        readiness_phase, release_class, product_lifecycle_state
    )
    if alignment_issue is not None:
        raise EnvironmentReleaseReadinessError(
            f"readiness phase drifts from immutable release lifecycle: {alignment_issue}"
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
    source_identity_fields = _release_source_identity_fields(header)
    if any(
        document.get(field) != header.get(field)
        for document in (attestation, asset_admission)
        for field in lifecycle_fields
    ) or any(
        attestation.get(field) != header.get(field)
        for field in source_identity_fields
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
    research_isolation: dict[str, Any] | None = None
    if readiness_phase == "research":
        if research_isolation_verification_path is None:
            raise EnvironmentReleaseReadinessError(
                "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE: research readiness "
                "requires canonical isolation verification"
            )
        try:
            research_isolation = load_research_isolation_verification(
                research_isolation_verification_path,
                environment=environment,
                release_id=release_id,
                verify_run_id=verify_run_id,
                manifest_digest=actual_payload_digest,
                require_pass=True,
            )
        except ResearchIsolationVerificationError as exc:
            raise EnvironmentReleaseReadinessError(str(exc)) from exc
    elif research_isolation_verification_path is not None:
        raise EnvironmentReleaseReadinessError(
            "research isolation verification is research-only"
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
    search_queries = post_report.get("searchQueries")
    if not isinstance(search_queries, list):
        raise EnvironmentReleaseReadinessError("post verification lacks searchQueries")
    searchable_post_ids = sorted(
        str(row.get("targetId") or "")
        for row in search_queries
        if isinstance(row, Mapping) and row.get("targetType") == "post"
    )
    searchable_author_ids = sorted(
        str(row.get("targetId") or "")
        for row in search_queries
        if isinstance(row, Mapping) and row.get("targetType") == "author"
    )
    expected_author_ids = sorted(
        str(row.get("personaId") or "")
        for row in post_report.get("creators") or []
        if isinstance(row, Mapping)
    )
    if searchable_post_ids != post_ids or searchable_author_ids != expected_author_ids:
        raise EnvironmentReleaseReadinessError(
            "Search projection does not exactly match imported Posts and Personas"
        )
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
    feed_queries = post_report.get("feedQueries")
    if not isinstance(feed_queries, list):
        raise EnvironmentReleaseReadinessError("post verification lacks feedQueries")
    guest_actor_hash = str(post_report.get("guestActorHash") or "").strip()
    guest_login = post_report.get("guestLogin")
    if research_isolation is not None and post_report.get(
        "internalSubjectHash"
    ) != research_isolation.get("subjectHash"):
        raise EnvironmentReleaseReadinessError(
            "research post readback subject drifts from isolation identity"
        )
    if readiness_phase != "research" and (
        not guest_actor_hash or not isinstance(guest_login, Mapping)
    ):
        raise EnvironmentReleaseReadinessError(
            "post verification lacks fresh guest identity evidence"
        )
    queries_by_name = {
        str(row.get("name") or ""): row
        for row in feed_queries
        if isinstance(row, Mapping)
    }
    # App 视频书唯一消费 premium_stream 池：全部 readiness phase 都必须携带并
    # 证明 premium_stream 读回（对齐 environment-topology-and-packaging spec；
    # typed_video 绿不代表视频书绿）。
    required_query_names = {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
        "premium_stream",
    }
    if set(queries_by_name) != required_query_names:
        raise EnvironmentReleaseReadinessError(
            "feedQueries do not match the declared readiness phase"
        )
    try:
        closure = validate_readiness_closure(
            release_root=release_root,
            header=header,
            desired={
                "entities": entity_refs,
                "posts": post_refs,
                "creators": creator_ids,
                "tags": tag_refs,
            },
            attestation=attestation,
            asset_admission=asset_admission,
            media_manifest=media_manifest,
            import_report=import_report,
            creator_report=creator_report,
            homepage_report=homepage_report,
            post_report=post_report,
        )
    except ReleaseReadinessClosureError as exc:
        raise EnvironmentReleaseReadinessError(str(exc)) from exc
    avatar_asset_ids = sorted(closure["avatarAssetIds"])
    verified_image_asset_ids = set(closure["imageAssetIds"])
    verified_playable_video_ids = set(closure["playableVideoIds"])
    media_asset_ids = sorted(closure["mediaAssetIds"])
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
    if not premium_ids or not premium_ids.issubset(release_post_ids):
        raise EnvironmentReleaseReadinessError(
            "premium_stream does not prove a release-bound postId"
        )
    premium_playable_video_ids = premium_ids & video_ids & verified_playable_video_ids
    if not premium_playable_video_ids:
        raise EnvironmentReleaseReadinessError(
            "premium_stream does not expose a release-bound video with a playable media probe"
        )

    video_query_name = (
        "typed_video" if readiness_phase == "consumer" else "premium_stream"
    )
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
            video_query_name=video_query_name,
            verified_playable_video_ids=verified_playable_video_ids,
            illustrated_article_ids=set(closure["illustratedArticleIds"]),
            verified_image_work_ids=set(closure["verifiedImageWorkIds"]),
            release_class=release_class,
            product_lifecycle_state=product_lifecycle_state,
        )
    except AppUatEnvelopeError as exc:
        raise EnvironmentReleaseReadinessError(str(exc)) from exc

    if attestation.get("payloadSha256") != actual_payload_digest:
        raise EnvironmentReleaseReadinessError("attestation payloadSha256 drift")
    if import_report.get("manifestDigest") != actual_payload_digest:
        raise EnvironmentReleaseReadinessError(
            "content import manifestDigest drift from immutable payload"
        )
    media_manifest_digest = f"sha256:{hashlib.sha256(media_manifest_path.read_bytes()).hexdigest()}"
    if research_isolation is not None:
        readback = research_isolation.get("positiveReadback")
        if not isinstance(readback, Mapping) or any(
            (
                readback.get("releaseId") != release_id,
                readback.get("entityRefs") != entity_refs,
                readback.get("postIds") != post_ids,
                readback.get("mediaAssetIds") != media_asset_ids,
            )
        ):
            raise EnvironmentReleaseReadinessError(
                "research isolation exact release readback drifts from release closure"
            )

    content_import_report_ref = _relative(
        import_report_path,
        output_root=output_root,
        label="content import report",
    )
    research_isolation_verification_ref = ""
    research_isolation_verification_digest = ""
    if research_isolation is not None:
        assert research_isolation_verification_path is not None
        research_isolation_verification_ref = _relative(
            research_isolation_verification_path,
            output_root=output_root,
            label="research isolation verification",
        )
        research_isolation_verification_digest = research_isolation_file_digest(
            research_isolation_verification_path
        )
    try:
        previous_environment_activation = (
            previous_environment_activation_for_release(
                header=header,
                environment=environment,
                readiness_path=previous_environment_readiness_path,
                release_id=release_id,
                manifest_digest=actual_payload_digest,
                output_root=output_root,
            )
        )
        activation_envelope = build_release_activation_envelope(
            header=header,
            environment=environment,
            release_id=release_id,
            manifest_digest=actual_payload_digest,
            release_class=release_class,
            product_lifecycle_state=product_lifecycle_state,
            readiness_phase=readiness_phase,
            import_run_id=import_run_id,
            verify_run_id=verify_run_id,
            import_report_ref=content_import_report_ref,
            import_report_digest=file_digest(import_report_path),
            app_uat_envelope=app_uat_envelope,
            research_isolation=research_isolation,
            research_isolation_verification_ref=(
                research_isolation_verification_ref
            ),
            research_isolation_verification_digest=(
                research_isolation_verification_digest
            ),
            previous_environment_activation=previous_environment_activation,
        )
    except EnvironmentActivationEnvelopeError as exc:
        raise EnvironmentReleaseReadinessError(str(exc)) from exc

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
        "contentImportReportRef": content_import_report_ref,
        "creatorAttributionRef": _relative(creator_import_report_path, output_root=output_root, label="creator attribution"),
        "tagAttributionRef": _relative(tag_consumer_verification_path, output_root=output_root, label="tag attribution"),
        "homepageApiVerificationRef": _relative(homepage_api_verification_path, output_root=output_root, label="homepage API verification"),
        "postApiVerificationRef": _relative(post_api_verification_path, output_root=output_root, label="post API verification"),
        "mediaManifestRef": _relative(media_manifest_path, output_root=output_root, label="media manifest"),
        "appUatEnvelope": app_uat_envelope,
        "appUatEnvelopeDigest": document_digest(app_uat_envelope),
        "activationEnvelope": activation_envelope,
        "activationEnvelopeDigest": document_digest(activation_envelope),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
    }
    for field in source_identity_fields:
        document[field] = header[field]
    if research_isolation is not None:
        document["internalSubjectHash"] = research_isolation["subjectHash"]
        document["researchIsolationVerificationRef"] = (
            research_isolation_verification_ref
        )
        document["researchIsolationVerificationDigest"] = (
            research_isolation_verification_digest
        )
    else:
        document["guestActorHash"] = guest_actor_hash
        document["guestLogin"] = dict(guest_login)
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
