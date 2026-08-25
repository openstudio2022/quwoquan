"""Semantic verification for one bound Data environment readiness receipt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.activation_envelope import (
    EnvironmentActivationEnvelopeError,
    build_environment_activation_envelope,
    document_digest,
    file_digest,
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
from core.io import read_json
from core.release_layout import payload_file
from verify.release_publishability import phase_lifecycle_alignment_issue


def _read_object(path: Path, *, label: str, issues: list[str]) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"{path}: invalid {label}: {exc}")
        return {}
    if not isinstance(value, Mapping):
        issues.append(f"{path}: {label} must be an object")
        return {}
    return dict(value)


def environment_release_readiness_issues(
    readiness: Mapping[str, Any],
    *,
    homepage_verification: Mapping[str, Any],
    post_verification: Mapping[str, Any],
    release: Path,
    output_root: Path,
    import_run: Path,
    verify_run: Path,
    attestation: Mapping[str, Any],
    desired_refs: Mapping[str, list[str]],
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
) -> list[str]:
    """Recompute receipt identity, digests, IDs and non-empty feed counts."""

    issues: list[str] = []
    path = verify_run / "release-readiness.json"
    if readiness.get("environment") != environment:
        issues.append(f"{path}: environment does not match run")
    if readiness.get("releaseId") != release_id:
        issues.append(f"{path}: releaseId does not match run")
    if readiness.get("sourceOwner") != "qwq_data":
        issues.append(f"{path}: sourceOwner must be qwq_data")
    if readiness.get("importRunId") != import_run_id:
        issues.append(f"{path}: importRunId drift")
    if readiness.get("verifyRunId") != verify_run_id:
        issues.append(f"{path}: verifyRunId drift")
    if readiness.get("manifestDigest") != attestation.get("payloadSha256"):
        issues.append(f"{path}: manifestDigest drift from immutable payload")
    release_header = _read_object(
        payload_file(release, "release.json"),
        label="release header",
        issues=issues,
    )
    for field in (
        "releaseClass",
        "productLifecycleState",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    ):
        if readiness.get(field) != release_header.get(field):
            issues.append(f"{path}: {field} drifts from immutable release closure")
    if readiness.get("guestActorHash") != post_verification.get("guestActorHash"):
        issues.append(f"{path}: guestActorHash drift from post verification")
    if readiness.get("guestLogin") != post_verification.get("guestLogin"):
        issues.append(f"{path}: guestLogin drift from post verification")
    if readiness.get("feedQueries") != post_verification.get("feedQueries"):
        issues.append(f"{path}: feedQueries drift from post verification")
    readiness_phase = str(readiness.get("readinessPhase") or "")
    alignment_issue = phase_lifecycle_alignment_issue(
        readiness_phase,
        str(readiness.get("releaseClass") or ""),
        str(readiness.get("productLifecycleState") or ""),
    )
    if alignment_issue is not None:
        issues.append(f"{path}: {alignment_issue}")
    isolation_fields = (
        "internalSubjectHash",
        "researchIsolationVerificationRef",
        "researchIsolationVerificationDigest",
    )
    isolation: dict[str, Any] | None = None
    if readiness_phase == "research":
        isolation_ref = str(
            readiness.get("researchIsolationVerificationRef") or ""
        )
        isolation_path = output_root / isolation_ref
        expected_isolation_path = verify_run / "research-isolation-verification.json"
        if not isolation_ref or isolation_path.resolve() != expected_isolation_path.resolve():
            issues.append(f"{path}: research isolation ref is not the canonical run proof")
        else:
            try:
                isolation = load_research_isolation_verification(
                    isolation_path,
                    environment=environment,
                    release_id=release_id,
                    verify_run_id=verify_run_id,
                    manifest_digest=str(readiness.get("manifestDigest") or ""),
                    require_pass=True,
                )
                isolation_digest = research_isolation_file_digest(isolation_path)
            except (OSError, ResearchIsolationVerificationError) as exc:
                issues.append(f"{path}: research isolation proof is invalid: {exc}")
            else:
                if (
                    readiness.get("internalSubjectHash")
                    != isolation.get("subjectHash")
                    or readiness.get("researchIsolationVerificationDigest")
                    != isolation_digest
                ):
                    issues.append(
                        f"{path}: research isolation identity/digest drift"
                    )
    elif any(field in readiness for field in isolation_fields):
        issues.append(f"{path}: research isolation evidence is research-only")

    media_manifest_path = payload_file(release, "media_manifest.json")
    try:
        media_bytes = media_manifest_path.read_bytes()
        media_manifest_digest = "sha256:" + hashlib.sha256(media_bytes).hexdigest()
        media_manifest_ref = media_manifest_path.relative_to(output_root).as_posix()
    except (OSError, ValueError) as exc:
        issues.append(f"{media_manifest_path}: cannot bind release media manifest: {exc}")
    else:
        if readiness.get("mediaManifestDigest") != media_manifest_digest:
            issues.append(f"{path}: mediaManifestDigest drift")
        if readiness.get("mediaManifestRef") != media_manifest_ref:
            issues.append(f"{path}: mediaManifestRef drift")

    content_import = _read_object(
        import_run / "import.json",
        label="content import report",
        issues=issues,
    )
    if content_import.get("manifestDigest") != attestation.get("payloadSha256"):
        issues.append(f"{import_run / 'import.json'}: manifestDigest drift from immutable payload")
    bindings = [
        row
        for row in content_import.get("postBindings") or []
        if isinstance(row, Mapping)
    ]
    expected_ids = sorted(str(row.get("postId") or "") for row in bindings)
    if readiness.get("postIds") != expected_ids:
        issues.append(f"{path}: postIds drift from import receipt")
    for field, kind in (
        ("entityRefs", "entities"),
        ("creatorIds", "creators"),
        ("tagRefs", "tags"),
    ):
        if readiness.get(field) != desired_refs[kind]:
            issues.append(f"{path}: {field} drift from desired state")

    media_manifest = _read_object(
        media_manifest_path,
        label="release media manifest",
        issues=issues,
    )
    asset_admission = _read_object(
        payload_file(release, "asset_admission.json"),
        label="release asset admission",
        issues=issues,
    )
    creator_import = _read_object(
        import_run / "creator-import.json",
        label="creator import report",
        issues=issues,
    )
    closure: dict[str, set[str]] | None = None
    try:
        closure = validate_readiness_closure(
            release_root=release,
            header=release_header,
            desired=desired_refs,
            attestation=attestation,
            asset_admission=asset_admission,
            media_manifest=media_manifest,
            import_report=content_import,
            creator_report=creator_import,
            homepage_report=homepage_verification,
            post_report=post_verification,
        )
    except ReleaseReadinessClosureError as exc:
        issues.append(f"{path}: immutable release/readback closure invalid: {exc}")
    media_asset_ids = sorted(
        str(row.get("assetId") or "")
        for row in media_manifest.get("assets") or []
        if isinstance(row, Mapping)
    )
    if readiness.get("mediaAssetIds") != media_asset_ids:
        issues.append(f"{path}: mediaAssetIds drift")
    feed_queries = {
        str(row.get("name") or ""): row
        for row in readiness.get("feedQueries") or []
        if isinstance(row, Mapping)
    }
    release_post_ids = set(expected_ids)
    discovery_ids = set(
        feed_queries.get("discovery_work", {}).get("matchedPostIds") or []
    ) & release_post_ids
    premium_ids = set(
        feed_queries.get("premium_stream", {}).get("matchedPostIds") or []
    ) & release_post_ids
    video_ids = {
        str(row.get("postId") or "")
        for row in bindings
        if row.get("contentType") == "video"
    }
    verified_image_work_ids = {
        str(row.get("postId") or "")
        for row in post_verification.get("posts") or []
        if isinstance(row, Mapping)
        and row.get("contentType") == "image"
        and row.get("detailStatus") == 200
        and row.get("mediaReady") is True
        and any(
            isinstance(probe, Mapping)
            and probe.get("kind") == "image"
            and probe.get("status") == 200
            and probe.get("hashVerified") is True
            for probe in row.get("mediaProbes") or []
        )
    }
    illustrated_article_ids = {
        str(row.get("postId") or "")
        for row in post_verification.get("posts") or []
        if isinstance(row, Mapping)
        and row.get("contentType") == "article"
        and row.get("detailStatus") == 200
        and row.get("mediaReady") is True
        and sum(
            isinstance(probe, Mapping)
            and probe.get("kind") == "image"
            and probe.get("status") == 200
            and probe.get("hashVerified") is True
            for probe in row.get("mediaProbes") or []
        )
        >= 2
    }
    verified_playable_video_ids = {
        str(row.get("postId") or "")
        for row in post_verification.get("posts") or []
        if isinstance(row, Mapping)
        and row.get("contentType") == "video"
        and row.get("detailStatus") == 200
        and row.get("mediaReady") is True
        and any(
            isinstance(probe, Mapping)
            and probe.get("kind") == "video"
            and probe.get("status") == 206
            and str(probe.get("mimeType") or "").startswith("video/")
            for probe in row.get("mediaProbes") or []
        )
        and any(
            isinstance(probe, Mapping)
            and probe.get("kind") == "image"
            and probe.get("status") == 200
            and probe.get("hashVerified") is True
            for probe in row.get("mediaProbes") or []
        )
    }
    verified_avatar_asset_ids = {
        str(row.get("avatarAssetId") or "")
        for row in post_verification.get("creators") or []
        if isinstance(row, Mapping)
        and row.get("creatorRef") in desired_refs["creators"]
        and row.get("profileStatus") == 200
        and row.get("avatarMediaReady") is True
        and row.get("avatarProbeCount") == 1
    }
    verified_image_asset_ids = {
        str(probe.get("assetId") or "")
        for row in post_verification.get("posts") or []
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
    if closure is not None:
        verified_image_work_ids = set(closure["verifiedImageWorkIds"])
        illustrated_article_ids = set(closure["illustratedArticleIds"])
        verified_playable_video_ids = set(closure["playableVideoIds"])
        verified_avatar_asset_ids = set(closure["avatarAssetIds"])
        verified_image_asset_ids = set(closure["imageAssetIds"])
    expected_counts = {
        "entities": len(desired_refs["entities"]),
        "posts": len(expected_ids),
        "creators": len(desired_refs["creators"]),
        "avatarAssets": len(verified_avatar_asset_ids),
        "imageAssets": len(verified_image_asset_ids),
        "tags": len(desired_refs["tags"]),
        "mediaAssets": len(media_asset_ids),
        "discoveryPosts": len(discovery_ids),
        "premiumPlayableVideos": len(
            premium_ids & video_ids & verified_playable_video_ids
        ),
    }
    if readiness.get("counts") != expected_counts:
        issues.append(f"{path}: counts drift from bound evidence")

    readiness_phase = str(readiness.get("readinessPhase") or "")
    video_query_name = (
        "typed_video" if readiness_phase == "consumer" else "premium_stream"
    )
    try:
        expected_app_uat_envelope = build_app_uat_envelope(
            release_root=release,
            release_id=release_id,
            entity_refs=desired_refs["entities"],
            post_refs=desired_refs["posts"],
            creator_ids=desired_refs["creators"],
            tag_refs=desired_refs["tags"],
            bindings=list(bindings),
            homepage_report=homepage_verification,
            queries_by_name=feed_queries,
            video_query_name=video_query_name,
            verified_playable_video_ids=verified_playable_video_ids,
            illustrated_article_ids=illustrated_article_ids,
            verified_image_work_ids=verified_image_work_ids,
            release_class=str(release_header.get("releaseClass") or ""),
            product_lifecycle_state=str(
                release_header.get("productLifecycleState") or ""
            ),
        )
    except AppUatEnvelopeError as exc:
        issues.append(f"{path}: cannot project appUatEnvelope: {exc}")
    else:
        if readiness.get("appUatEnvelope") != expected_app_uat_envelope:
            issues.append(
                f"{path}: appUatEnvelope drifts from immutable release closure"
            )
        expected_app_uat_digest = document_digest(expected_app_uat_envelope)
        if readiness.get("appUatEnvelopeDigest") != expected_app_uat_digest:
            issues.append(f"{path}: appUatEnvelopeDigest drift")
        try:
            import_report_ref = (
                (import_run / "import.json").relative_to(output_root).as_posix()
            )
            expected_activation_envelope = build_environment_activation_envelope(
                environment=environment,
                release_id=release_id,
                manifest_digest=str(attestation.get("payloadSha256") or ""),
                source_revision=str(release_header.get("sourceRevision") or ""),
                source_digest=str(release_header.get("sourceDigest") or ""),
                entity_catalog_digest=str(
                    release_header.get("entityCatalogDigest") or ""
                ),
                release_class=str(release_header.get("releaseClass") or ""),
                product_lifecycle_state=str(
                    release_header.get("productLifecycleState") or ""
                ),
                readiness_phase=readiness_phase,
                import_run_id=import_run_id,
                verify_run_id=verify_run_id,
                import_report_ref=import_report_ref,
                import_report_digest=file_digest(import_run / "import.json"),
                app_uat_envelope=expected_app_uat_envelope,
                research_isolation=isolation,
                research_isolation_verification_ref=str(
                    readiness.get("researchIsolationVerificationRef") or ""
                ),
                research_isolation_verification_digest=str(
                    readiness.get("researchIsolationVerificationDigest") or ""
                ),
            )
        except (ValueError, EnvironmentActivationEnvelopeError) as exc:
            issues.append(f"{path}: cannot project activationEnvelope: {exc}")
        else:
            if readiness.get("activationEnvelope") != expected_activation_envelope:
                issues.append(
                    f"{path}: activationEnvelope drifts from release/import/readback"
                )
            expected_activation_digest = document_digest(
                expected_activation_envelope
            )
            if (
                readiness.get("activationEnvelopeDigest")
                != expected_activation_digest
            ):
                issues.append(f"{path}: activationEnvelopeDigest drift")

    unsigned = dict(readiness)
    declared_checksum = str(unsigned.pop("verificationChecksum", ""))
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_checksum = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    if declared_checksum != actual_checksum:
        issues.append(f"{path}: verificationChecksum drift")
    return issues


__all__ = ["environment_release_readiness_issues"]
