"""stackctl app 预检域 canonical Data release readiness / lifecycle Exit 回执装载。

从 commands/app_preflight_shared.py 逐字迁出(该模块保留 canonical schema
常量与校验原语,回执装载与身份绑定家族随本职责聚合到本模块):

- `_load_test_data_release_readiness`:从 canonical 回执生命周期选择严格
  校验器;
- `_load_data_release_readiness`:单一 Data-owned 环境回执的 fail-closed
  装载与校验;
- `_load_data_release_lifecycle_exit`:显式 rollback/replay 证明
  的装载与绑定重算。

schema 常量与 `_canonical_document_checksum` / `_validated_string_set` /
`_validate_data_activation_envelope` / `_validate_data_operation_evidence`
等校验原语在 `commands/app_preflight_shared.py`。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

def _validate_data_schema(value: Mapping[str, Any], name: str) -> None:
    """消费现役 Data authoring schema，不复制宽松的旧类别读轨。"""
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).resolve().parents[3] / "quwoquan_data/schema/release" / f"{name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: str(list(error.absolute_path)),
    )
    if errors:
        raise ValueError(f"Data {name} schema: {errors[0].message}")


def _resolve_data_prepared_import(
    readiness: Mapping[str, Any], *, evidence_root: Path,
) -> tuple[Path, str]:
    """从激活 result 精确回溯 prepared apply，不把 activation run 当导入目录。"""
    from quwoquan_ops.cli.lib.content_api_consumer_authority import (
        _load_authority, _ref_authority, _regular_bytes, _required_identity,
    )

    environment = str(readiness.get("environment") or "")
    if environment not in {"alpha", "beta", "gamma", "prod"}:
        raise ValueError("Data activation environment is invalid")
    release_id = _required_identity(readiness.get("releaseId"), label="releaseId")
    activation_id = _required_identity(readiness.get("importRunId"), label="activation runId")
    activation = readiness.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise ValueError("Data readiness activationEnvelope is missing")
    expected_identity = {
        "environment": environment, "releaseId": release_id,
        "manifestDigest": readiness.get("manifestDigest"),
    }
    if any(activation.get(key) != value for key, value in expected_identity.items()) or (
        activation.get("importRunId") != activation_id
        or activation.get("verifyRunId") != readiness.get("verifyRunId")
        or activation.get("importReportRef") != readiness.get("contentImportReportRef")
    ):
        raise ValueError("Data activation/import identity drift")
    prefix = f"env/{environment}/runs/data-release/{release_id}"

    def result(run_id: str, status: str) -> dict[str, Any]:
        ref = f"{prefix}/{run_id}/result.json"
        path = _ref_authority(ref, expected=ref, label="Data predecessor result", root=evidence_root)
        value = json.loads(_regular_bytes(path, label="Data predecessor result"))
        expected = {
            "schema": "quwoquan_data.environment_release_result",
            **expected_identity, "runId": run_id, "status": status,
        }
        if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
            raise ValueError("Data activation/prepared predecessor identity drift")
        return value

    activated = result(activation_id, "completed")
    prepared_id = _required_identity(activated.get("importRunId"), label="prepared apply runId")
    if prepared_id == activation_id:
        raise ValueError("Data activation cannot be its own prepared apply")
    prepared = result(prepared_id, "prepared")
    import_ref = f"{prefix}/{prepared_id}/import.json"
    if activation.get("importReportRef") != import_ref or prepared.get("contentImportReportRef") != import_ref:
        raise ValueError("Data importReportRef does not bind prepared apply")
    report = _load_authority(
        import_ref, str(activation.get("importReportDigest") or ""),
        label="Data prepared import report", root=evidence_root,
    )
    return report.path, prepared_id

def _load_test_data_release_readiness(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
) -> tuple[dict[str, Any], Path]:
    """Select the strict validator from the canonical receipt lifecycle."""
    import quwoquan_ops.cli.stackctl as _stackctl

    receipt_path = _stackctl._data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
    try:
        raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"canonical Data readiness receipt is missing: {_stackctl.relpath(receipt_path)}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"canonical Data readiness receipt is unreadable: {_stackctl.relpath(receipt_path)}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise ValueError("canonical Data readiness receipt must be a JSON object")
    return _stackctl._load_data_release_readiness(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
    )


def _load_data_release_readiness(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
) -> tuple[dict[str, Any], Path]:
    """Load and fail-closed validate the single Data-owned environment receipt."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(str(manifest_digest or "").strip()) is None:
        raise ValueError("manifestDigest must use canonical sha256:<64 lowercase hex>")
    receipt_path = _stackctl._data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
    try:
        raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"canonical Data readiness receipt is missing: {_stackctl.relpath(receipt_path)}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"canonical Data readiness receipt is unreadable: {_stackctl.relpath(receipt_path)}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("canonical Data readiness receipt must be a JSON object")
    receipt = dict(raw)
    _validate_data_schema(receipt, "environment_release_readiness")
    issues: list[str] = []
    expected_values = {
        "schema": _stackctl._DATA_READINESS_SCHEMA,
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "manifestDigest": manifest_digest,
        "verifyRunId": verify_run_id,
        "passed": True,
    }
    for key, expected in expected_values.items():
        if receipt.get(key) != expected:
            issues.append(
                f"Data readiness {key}={receipt.get(key)!r}, expected {expected!r}"
            )
    authorization_required_ids = receipt.get("authorizationRequiredAssetIds")
    contains_unverified = receipt.get("containsUnverifiedAssets")
    if (
        not isinstance(authorization_required_ids, list)
        or any(not str(item).strip() for item in authorization_required_ids)
        or len(authorization_required_ids) != len(set(authorization_required_ids))
        or not isinstance(contains_unverified, bool)
        or contains_unverified != bool(authorization_required_ids)
    ):
        issues.append("Data readiness authorization-required asset summary is invalid")
    rights_status_counts = receipt.get("rightsStatusCounts")
    if (
        not isinstance(rights_status_counts, dict)
        or set(rights_status_counts) != {"verified", "unverified", "restricted", "unknown"}
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in rights_status_counts.values()
        )
    ):
        issues.append("Data readiness rightsStatusCounts is invalid")
    if not isinstance(receipt.get("sourceIdentities"), list) or not receipt["sourceIdentities"]:
        issues.append("Data readiness sourceIdentities is missing or invalid")
    for digest_key in (
        "manifestDigest",
        "mediaManifestDigest",
        "sourceIdentitySetDigest",
        "activationEnvelopeDigest",
    ):
        if _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(str(receipt.get(digest_key) or "")) is None:
            issues.append(f"Data readiness {digest_key} is not a canonical digest")
    if not str(receipt.get("importRunId") or "").strip():
        issues.append("Data readiness importRunId is missing")
    observed_request_ids: set[str] = set()
    observed_trace_ids: set[str] = set()
    if _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
        str(receipt.get("guestActorHash") or "")
    ) is None:
        issues.append("Data readiness guestActorHash is not a canonical digest")
    request_id, trace_id = _stackctl._validate_data_operation_evidence(
        receipt.get("guestLogin"),
        label="guestLogin",
        expected_path="/auth/login/anonymous",
        expected_page_id="user.login.anonymous",
        expected_status=200,
        issues=issues,
    )
    if request_id:
        observed_request_ids.add(request_id)
    if trace_id:
        observed_trace_ids.add(trace_id)

    declared_checksum = str(receipt.get("verificationChecksum") or "")
    checksum_document = dict(receipt)
    checksum_document.pop("verificationChecksum", None)
    actual_checksum = _stackctl._canonical_document_checksum(checksum_document)
    if declared_checksum != actual_checksum:
        issues.append("Data readiness verificationChecksum does not match the receipt")

    collections = {
        "entities": _stackctl._validated_string_set(
            receipt.get("entityRefs"), label="entityRefs", issues=issues
        ),
        "posts": _stackctl._validated_string_set(
            receipt.get("postIds"), label="postIds", issues=issues
        ),
        "creators": _stackctl._validated_string_set(
            receipt.get("creatorIds"), label="creatorIds", issues=issues
        ),
        "tags": _stackctl._validated_string_set(
            receipt.get("tagRefs"), label="tagRefs", issues=issues
        ),
        "mediaAssets": _stackctl._validated_string_set(
            receipt.get("mediaAssetIds"), label="mediaAssetIds", issues=issues
        ),
    }
    counts = receipt.get("counts")
    if not isinstance(counts, dict):
        issues.append("Data readiness counts must be an object")
        counts = {}
    for count_name, identifiers in collections.items():
        count = counts.get(count_name)
        if not isinstance(count, int) or isinstance(count, bool) or count != len(identifiers):
            issues.append(
                f"Data readiness counts.{count_name} must equal {len(identifiers)}"
            )
    avatar_count = counts.get("avatarAssets")
    if (
        not isinstance(avatar_count, int)
        or isinstance(avatar_count, bool)
        or not 1 <= avatar_count <= len(collections["creators"])
    ):
        issues.append(
            "Data readiness counts.avatarAssets must be non-zero and release-bound"
        )
    image_count = counts.get("imageAssets")
    if (
        not isinstance(image_count, int)
        or isinstance(image_count, bool)
        or image_count < 1
        or image_count > len(collections["mediaAssets"])
    ):
        issues.append(
            "Data readiness counts.imageAssets must be non-zero and release-bound"
        )

    queries = receipt.get("feedQueries")
    queries_by_name: dict[str, dict[str, Any]] = {}
    if not isinstance(queries, list):
        issues.append("Data readiness feedQueries must be an array")
        queries = []
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            issues.append(f"Data readiness feedQueries[{index}] must be an object")
            continue
        name = str(item.get("name") or "")
        if not name or name in queries_by_name:
            issues.append(f"Data readiness feed query name is empty or duplicated: {name!r}")
            continue
        queries_by_name[name] = item
        matched = _stackctl._validated_string_set(
            item.get("matchedPostIds"),
            label=f"feedQueries.{name}.matchedPostIds",
            issues=issues,
        )
        if not matched.issubset(collections["posts"]):
            issues.append(f"Data readiness feed query {name} is not release-bound")
        if (
            item.get("path") != "/content/feed"
            or item.get("status") != 200
            or item.get("releaseBound") is not True
        ):
            issues.append(f"Data readiness feed query {name} lacks canonical 200 binding")
        requests = item.get("requests")
        if not isinstance(requests, list) or not requests:
            issues.append(f"Data readiness feed query {name} lacks request evidence")
            continue
        for request_index, request_evidence in enumerate(requests):
            request_id, trace_id = _stackctl._validate_data_operation_evidence(
                request_evidence,
                label=f"feedQueries.{name}.requests[{request_index}]",
                expected_path="/content/feed",
                expected_page_id="content.feed.list",
                expected_status=200,
                issues=issues,
            )
            if request_id in observed_request_ids:
                issues.append(
                    f"Data readiness feed query {name} reuses requestId {request_id!r}"
                )
            elif request_id:
                observed_request_ids.add(request_id)
            if trace_id in observed_trace_ids:
                issues.append(
                    f"Data readiness feed query {name} reuses traceId {trace_id!r}"
                )
            elif trace_id:
                observed_trace_ids.add(trace_id)
    from .app_preflight_shared import _DATA_READINESS_QUERY_NAMES

    expected_query_names = _DATA_READINESS_QUERY_NAMES
    if set(queries_by_name) != expected_query_names:
        issues.append(
            "Data readiness feedQueries do not match the required content queries"
        )
    expected_query_patterns = {
        "discovery_work": r"^identity=work&limit=[1-9][0-9]*$",
        "typed_video": r"^identity=work&type=video&limit=[1-9][0-9]*$",
        "homepage_recommend": (
            r"^sort=recommend&channelId=recommend&limit=[1-9][0-9]*$"
        ),
        # 视频书唯一消费 premium_stream；必须证明该池
        # release-bound 非空读回（typed_video 绿不代表视频书绿）。
        "premium_stream": (
            r"^sort=recommend&channelId=premium_stream&limit=[1-9][0-9]*$"
        ),
    }
    for name, pattern in expected_query_patterns.items():
        query = str(queries_by_name.get(name, {}).get("query") or "")
        if re.fullmatch(pattern, query) is None:
            issues.append(f"Data readiness {name} exact query is not canonical")
    discovery_ids = set(
        queries_by_name.get("discovery_work", {}).get("matchedPostIds") or []
    )
    video_ids = set(queries_by_name.get("typed_video", {}).get("matchedPostIds") or [])
    premium_ids = set(
        queries_by_name.get("premium_stream", {}).get("matchedPostIds") or []
    )
    premium_video_ids = premium_ids & video_ids
    if not discovery_ids:
        issues.append("Data readiness discovery exact query is empty")
    if not video_ids:
        issues.append("Data readiness video-book exact query is empty")
    if not premium_video_ids:
        issues.append("Data readiness premium_stream has no release-bound playable video")
    for count_name, expected_count in (("discoveryPosts", len(discovery_ids)),):
        value = counts.get(count_name)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            or value != expected_count
        ):
            issues.append(
                f"Data readiness counts.{count_name} must equal {expected_count} and be non-zero"
            )
    premium_count = counts.get("premiumPlayableVideos")
    if (
        not isinstance(premium_count, int)
        or isinstance(premium_count, bool)
        or premium_count != len(premium_video_ids)
        or premium_count < 1
    ):
        issues.append(
            "Data readiness counts.premiumPlayableVideos must match its release-bound playable videos"
        )

    evidence_root = _stackctl.output_root().expanduser().resolve()
    expected_media_ref = (
        Path("data") / "releases" / release_id / "payload" / "media_manifest.json"
    ).as_posix()
    if receipt.get("mediaManifestRef") != expected_media_ref:
        issues.append("Data readiness mediaManifestRef is not the canonical release payload")
    evidence_refs = (
        "contentImportReportRef",
        "creatorAttributionRef",
        "tagAttributionRef",
        "homepageApiVerificationRef",
        "postApiVerificationRef",
        "mediaManifestRef",
    )
    resolved_evidence: dict[str, Path] = {}
    for key in evidence_refs:
        ref = str(receipt.get(key) or "").strip()
        candidate = (evidence_root / ref).resolve()
        try:
            candidate.relative_to(evidence_root)
        except ValueError:
            issues.append(f"Data readiness {key} escapes QWQ_OUTPUT_ROOT")
            continue
        if not ref or not candidate.is_file():
            issues.append(f"Data readiness {key} evidence is missing: {ref or '<empty>'}")
            continue
        resolved_evidence[key] = candidate
    media_path = resolved_evidence.get("mediaManifestRef")
    if media_path is not None:
        actual_media_digest = f"sha256:{hashlib.sha256(media_path.read_bytes()).hexdigest()}"
        if actual_media_digest != receipt.get("mediaManifestDigest"):
            issues.append("Data readiness mediaManifestDigest does not match payload bytes")
    post_verification_path = resolved_evidence.get("postApiVerificationRef")
    if post_verification_path is not None:
        try:
            post_verification = json.loads(
                post_verification_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            issues.append("Data readiness postApiVerificationRef is unreadable")
        else:
            if not isinstance(post_verification, dict):
                issues.append("Data readiness post API verification must be an object")
            elif (
                post_verification.get("feedQueries") != receipt.get("feedQueries")
                or post_verification.get("guestActorHash") != receipt.get("guestActorHash")
                or post_verification.get("guestLogin") != receipt.get("guestLogin")
            ):
                issues.append(
                    "Data readiness identity/feed operation evidence drifts from post verification"
                )
            else:
                creator_evidence = [
                    row
                    for row in post_verification.get("creators") or []
                    if isinstance(row, dict)
                ]
                creator_refs = {
                    str(row.get("creatorRef") or "").strip()
                    for row in creator_evidence
                }
                ready_creator_evidence = [
                    row
                    for row in creator_evidence
                    if row.get("avatarMediaReady") is True
                ]
                default_avatar_evidence = [
                    row
                    for row in creator_evidence
                    if row.get("usesPlatformDefaultAvatar") is True
                ]
                avatar_asset_ids = {
                    str(row.get("avatarAssetId") or "").strip()
                    for row in ready_creator_evidence
                }
                ready_avatar_drift = any(
                    row.get("profileStatus") != 200
                    or row.get("avatarProbeCount") != 1
                    or not isinstance(row.get("avatarProbe"), dict)
                    or row["avatarProbe"].get("publicUrl") != row.get("avatarUrl")
                    or row["avatarProbe"].get("status") != 200
                    or not str(row["avatarProbe"].get("mimeType") or "").startswith("image/")
                    or not isinstance(row["avatarProbe"].get("bytes"), int)
                    or row["avatarProbe"].get("bytes", 0) <= 0
                    or _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
                        str(row["avatarProbe"].get("sha256") or "")
                    ) is None
                    or row["avatarProbe"].get("hashVerified") is not True
                    for row in ready_creator_evidence
                )
                if (
                    creator_refs != collections["creators"]
                    or len(avatar_asset_ids) != avatar_count
                    or "" in avatar_asset_ids
                    or ready_avatar_drift
                    or any(
                        row.get("profileStatus") != 200
                        or row.get("avatarAssetId") is not None
                        or row.get("avatarUrl") != ""
                        or row.get("avatarMediaReady") is not False
                        or row.get("avatarProbeCount") != 0
                        or row.get("avatarProbe") is not None
                        for row in default_avatar_evidence
                    )
                    or len(ready_creator_evidence)
                    + len(default_avatar_evidence)
                    != len(creator_evidence)
                ):
                    issues.append(
                        "Data readiness creator avatar evidence is not release-bound"
                    )
                image_asset_ids = {
                    str(probe.get("assetId") or "").strip()
                    for row in post_verification.get("posts") or []
                    if isinstance(row, dict)
                    for probe in row.get("mediaProbes") or []
                    if isinstance(probe, dict)
                    and probe.get("kind") == "image"
                    and probe.get("status") == 200
                    and str(probe.get("mimeType") or "").startswith("image/")
                    and probe.get("bytes") == probe.get("expectedBytes")
                    and probe.get("sha256") == probe.get("expectedSha256")
                    and probe.get("hashVerified") is True
                }
                if (
                    "" in image_asset_ids
                    or len(image_asset_ids) != image_count
                    or not image_asset_ids.issubset(collections["mediaAssets"])
                ):
                    issues.append(
                        "Data readiness image delivery evidence is not hash-bound"
                    )
                if any(
                    not isinstance(row, dict)
                    or not isinstance(row.get("mediaProbes"), list)
                    or row.get("mediaProbeCount")
                    != len(row.get("mediaProbes") or [])
                    for row in post_verification.get("posts") or []
                ):
                    issues.append(
                        "Data readiness mediaProbeCount drifts from typed probes"
                    )
    _stackctl._validate_data_activation_envelope(
        receipt,
        evidence_root=evidence_root,
        issues=issues,
    )
    try:
        _resolve_data_prepared_import(receipt, evidence_root=evidence_root)
    except (OSError, ValueError) as exc:
        issues.append(str(exc))

    attestation_path = (
        evidence_root / "data" / "releases" / release_id / "attestations" / "release.json"
    )
    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append(
            f"Data release attestation is missing or unreadable: {_stackctl.relpath(attestation_path)}"
        )
    else:
        expected_attestation = {
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "payloadSha256": manifest_digest,
        }
        expected_attestation["sourceIdentities"] = receipt.get("sourceIdentities")
        expected_attestation["sourceIdentitySetDigest"] = receipt.get("sourceIdentitySetDigest")
        if not isinstance(attestation, dict) or any(
            attestation.get(field) != expected
            for field, expected in expected_attestation.items()
        ):
            issues.append("Data release attestation does not bind the expected payload digest")

    if issues:
        raise ValueError("; ".join(issues))
    return receipt, receipt_path


def _load_data_release_lifecycle_exit(
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
    readiness: dict[str, Any],
    lifecycle_exit_ref: str,
) -> tuple[dict[str, Any], Path]:
    """Load the explicit rollback/replay proof and recompute its bindings."""
    import quwoquan_ops.cli.stackctl as _stackctl

    ref = str(lifecycle_exit_ref or "").strip()
    if not ref:
        raise ValueError(
            "explicit lifecycle verification requires canonical data lifecycleExitRef"
        )
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("data lifecycleExitRef must stay below QWQ_OUTPUT_ROOT")
    expected_prefix = (
        "env",
        environment,
        "runs",
        "release-lifecycle-exit",
        release_id,
    )
    if (
        len(relative.parts) != 7
        or tuple(relative.parts[:5]) != expected_prefix
        or relative.parts[-1] != "lifecycle-exit.json"
    ):
        raise ValueError(
            "data lifecycleExitRef must bind environment/release/exitRunId"
        )
    exit_run_id = _stackctl._data_readiness_segment(
        relative.parts[5],
        label="lifecycle exitRunId",
    )
    evidence_root = _stackctl.output_root().expanduser().resolve()
    path = (evidence_root / relative).resolve()
    try:
        path.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError("data lifecycleExitRef escapes QWQ_OUTPUT_ROOT") from exc
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"data lifecycle Exit receipt is missing: {ref}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"data lifecycle Exit receipt is unreadable: {ref}") from exc
    if not isinstance(raw, dict):
        raise ValueError("data lifecycle Exit receipt must be a JSON object")
    receipt = dict(raw)
    _validate_data_schema(receipt, "environment_release_lifecycle_exit")
    expected_keys = {
        "schema",
        "environment",
        "sourceOwner",
        "exitRunId",
        "originalReleaseId",
        "originalManifestDigest",
        "originalImportRunId",
        "originalVerifyRunId",
        "originalImportResultRef",
        "originalVerifyResultRef",
        "rollbackToReleaseId",
        "rollbackToManifestDigest",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "rollbackResultRef",
        "rollbackVerifyResultRef",
        "replayImportRunId",
        "replayVerifyRunId",
        "replayManifestDigest",
        "replayImportResultRef",
        "replayVerifyResultRef",
        "recordedAt",
        "verificationChecksum",
        "passed",
    }
    issues: list[str] = []
    if set(receipt) != expected_keys:
        issues.append("data lifecycle Exit receipt fields drift from canonical schema")
    readiness_pair = (readiness.get("importRunId"), readiness.get("verifyRunId"))
    if not all(readiness_pair) or readiness_pair not in {
        (receipt.get("originalImportRunId"), receipt.get("originalVerifyRunId")),
        (receipt.get("replayImportRunId"), receipt.get("replayVerifyRunId")),
    }:
        issues.append("data lifecycle Exit does not bind the exact readiness import/verify pair")
    expected_values = {
        "schema": _stackctl._DATA_LIFECYCLE_EXIT_SCHEMA,
        "environment": environment,
        "sourceOwner": "qwq_data",
        "exitRunId": exit_run_id,
        "originalReleaseId": release_id,
        "originalManifestDigest": manifest_digest,
        "replayManifestDigest": manifest_digest,
        "passed": True,
    }
    for field, expected in expected_values.items():
        if receipt.get(field) != expected:
            issues.append(
                f"data lifecycle Exit {field}={receipt.get(field)!r}, expected {expected!r}"
            )
    rollback_release_id = str(receipt.get("rollbackToReleaseId") or "").strip()
    if not rollback_release_id or rollback_release_id == release_id:
        issues.append(
            "data lifecycle Exit rollbackToReleaseId must name another release"
        )
    for field in (
        "originalManifestDigest",
        "rollbackToManifestDigest",
        "replayManifestDigest",
    ):
        if _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(str(receipt.get(field) or "")) is None:
            issues.append(f"data lifecycle Exit {field} is not a canonical digest")
    declared_checksum = str(receipt.get("verificationChecksum") or "")
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum", None)
    if declared_checksum != _stackctl._canonical_document_checksum(unsigned):
        issues.append("data lifecycle Exit verificationChecksum drift")

    run_ids = [
        str(receipt.get(field) or "").strip()
        for field in (
            "originalImportRunId",
            "originalVerifyRunId",
            "rollbackRunId",
            "rollbackVerifyRunId",
            "replayImportRunId",
            "replayVerifyRunId",
        )
    ]
    if any(not value for value in run_ids) or len(set(run_ids)) != len(run_ids):
        issues.append("data lifecycle Exit run IDs must be non-empty and distinct")

    def result_ref(bound_release_id: str, run_id_field: str) -> str:
        return (
            Path("env")
            / environment
            / "runs"
            / "data-release"
            / bound_release_id
            / str(receipt.get(run_id_field) or "")
            / "result.json"
        ).as_posix()

    expected_refs = {
        "originalImportResultRef": result_ref(release_id, "originalImportRunId"),
        "originalVerifyResultRef": result_ref(release_id, "originalVerifyRunId"),
        "rollbackResultRef": result_ref(rollback_release_id, "rollbackRunId"),
        "rollbackVerifyResultRef": result_ref(
            rollback_release_id,
            "rollbackVerifyRunId",
        ),
        "replayImportResultRef": result_ref(release_id, "replayImportRunId"),
        "replayVerifyResultRef": result_ref(release_id, "replayVerifyRunId"),
    }
    for field, expected in expected_refs.items():
        if receipt.get(field) != expected:
            issues.append(f"data lifecycle Exit {field} is not canonical")
            continue
        if not (evidence_root / expected).is_file():
            issues.append(f"data lifecycle Exit evidence is missing: {expected}")

    for bound_release_id, digest in (
        (release_id, manifest_digest),
        (rollback_release_id, str(receipt.get("rollbackToManifestDigest") or "")),
    ):
        attestation_path = (
            evidence_root
            / "data"
            / "releases"
            / bound_release_id
            / "attestations"
            / "release.json"
        )
        try:
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(
                "data lifecycle Exit release attestation is missing or unreadable: "
                + _stackctl.relpath(attestation_path)
            )
            continue
        if (
            not isinstance(attestation, dict)
            or attestation.get("releaseId") != bound_release_id
            or attestation.get("sourceOwner") != "qwq_data"
            or attestation.get("payloadSha256") != digest
        ):
            issues.append(
                f"data lifecycle Exit attestation drift for {bound_release_id}"
            )
    if issues:
        raise ValueError("; ".join(issues))
    return receipt, path
