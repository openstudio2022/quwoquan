#!/usr/bin/env python3
"""校验 runtime-media 视频播放 T4 非 dry-run 证据的最小商用合同。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.gate.runtime_media_t4_artifacts import validate_report_artifacts

REPORT_SCHEMA = "runtime-media-video-playback-t4-report"
MATRIX_SCHEMA = "runtime-media-video-playback-t4-matrix-report"
SCENARIO = "runtime_media.video_playback_t4"
MATRIX_SCENARIO = "runtime_media.video_playback_t4_matrix"
PRODUCTION_FORBIDDEN_TOKENS = frozenset({"fixture", "mock", "seed", "test"})
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_MATRIX_KEYS = frozenset(
    {
        ("alpha-local", "local"),
        ("beta-local", "local"),
        ("gamma-local", "local"),
        ("prod-hosted", "gray-initial"),
        ("prod-hosted", "carry-on"),
        ("prod-hosted", "full"),
    },
)


def _non_empty_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _require_string(
    value: dict[str, Any],
    field: str,
    issues: list[str],
    *,
    prefix: str,
) -> str:
    resolved = _non_empty_string(value.get(field))
    if not resolved:
        issues.append(f"{prefix}.{field} 必须为非空字符串")
    return resolved


def _validate_target(
    environment: dict[str, Any],
    issues: list[str],
    *,
    prefix: str,
) -> tuple[str, str]:
    target = _require_string(environment, "target", issues, prefix=prefix)
    env = _require_string(environment, "env", issues, prefix=prefix)
    stage = _require_string(environment, "rolloutStage", issues, prefix=prefix)
    expected_envs = {
        "alpha-local": "alpha",
        "beta-local": "beta",
        "gamma-local": "gamma",
        "prod-sim": "prod",
        "prod-hosted": "prod",
    }
    expected_env = expected_envs.get(target)
    if expected_env is None:
        issues.append(f"{prefix}.target 不是允许的视频播放 target: {target or '<empty>'}")
    elif env and env != expected_env:
        issues.append(
            f"{prefix}.env 与 target 不一致: target={target} expected={expected_env} got={env}",
        )
    if target == "prod-hosted" and stage not in {
        "gray-initial",
        "carry-on",
        "full",
    }:
        issues.append(
            f"{prefix}.rolloutStage 必须为 gray-initial|carry-on|full，当前为 {stage or '<empty>'}",
        )
    elif target and target != "prod-hosted" and stage not in {"local", "not-applicable"}:
        issues.append(
            f"{prefix}.rolloutStage 对本地 target 必须为 local 或 not-applicable，当前为 {stage or '<empty>'}",
        )
    return target, env


def _validate_single_report(
    report: object,
    *,
    index: int,
    check_artifacts: bool,
    artifact_root: Path,
) -> list[str]:
    issues: list[str] = []
    prefix = f"reports[{index}]"
    if not isinstance(report, dict):
        return [f"{prefix} 必须为对象"]

    if report.get("schema") != REPORT_SCHEMA:
        issues.append(
            f"{prefix}.schema 必须为 {REPORT_SCHEMA}，当前为 {report.get('schema')!r}",
        )
    if _non_empty_string(report.get("scenario")) != SCENARIO:
        issues.append(f"{prefix}.scenario 必须为 {SCENARIO}")
    if _non_empty_string(report.get("status")).lower() != "passed":
        issues.append(f"{prefix}.status 必须为 passed")
    if report.get("dryRun") is not False:
        issues.append(f"{prefix}.dryRun 必须显式为 false")
    _require_string(report, "startedAt", issues, prefix=prefix)
    _require_string(report, "endedAt", issues, prefix=prefix)

    environment = _mapping(report.get("environment"))
    target, env = _validate_target(
        environment,
        issues,
        prefix=f"{prefix}.environment",
    )
    media_authority = _require_string(
        environment,
        "mediaVideoBaseUrl",
        issues,
        prefix=f"{prefix}.environment",
    )
    if media_authority and not media_authority.startswith("https://"):
        issues.append(f"{prefix}.environment.mediaVideoBaseUrl 必须为 HTTPS authority")
    _require_string(environment, "commitSha", issues, prefix=f"{prefix}.environment")
    _require_string(environment, "configHash", issues, prefix=f"{prefix}.environment")

    release = _mapping(report.get("release"))
    release_prefix = f"{prefix}.release"
    release_id = _require_string(release, "releaseId", issues, prefix=release_prefix)
    if _require_string(release, "sourceOwner", issues, prefix=release_prefix) != "qwq_data":
        issues.append(f"{release_prefix}.sourceOwner 必须为 qwq_data")
    for digest_field in ("manifestDigest", "mediaManifestDigest"):
        digest = _require_string(release, digest_field, issues, prefix=release_prefix)
        if digest and SHA256_PATTERN.fullmatch(digest) is None:
            issues.append(f"{release_prefix}.{digest_field} 必须为 sha256 digest")
    _require_string(
        release,
        "importRunId",
        issues,
        prefix=release_prefix,
    )
    verify_run_id = _require_string(
        release,
        "verifyRunId",
        issues,
        prefix=release_prefix,
    )
    receipt_ref = _require_string(
        release,
        "readinessReceiptRef",
        issues,
        prefix=release_prefix,
    )
    if env and release_id and verify_run_id and receipt_ref:
        expected_receipt_ref = (
            f"env/{env}/runs/data-release/{release_id}/{verify_run_id}/"
            "release-readiness.json"
        )
        if receipt_ref != expected_receipt_ref:
            issues.append(
                f"{release_prefix}.readinessReceiptRef 不是当前环境的 canonical receipt"
            )

    media = _mapping(report.get("media"))
    public_slice_key = _require_string(media, "publicSliceKey", issues, prefix=f"{prefix}.media")
    _require_string(media, "assetId", issues, prefix=f"{prefix}.media")
    probe_hash = _require_string(media, "probeHash", issues, prefix=f"{prefix}.media")
    try:
        asset_version = int(media.get("assetVersion"))
    except (TypeError, ValueError):
        asset_version = 0
    if asset_version <= 0:
        issues.append(f"{prefix}.media.assetVersion 必须为正整数")
    if probe_hash and (
        not probe_hash.startswith("sha256:") or len(probe_hash) != len("sha256:") + 64
    ):
        issues.append(f"{prefix}.media.probeHash 必须为 sha256 digest")
    if public_slice_key and not public_slice_key.startswith("media/video/s/"):
        issues.append(f"{prefix}.media.publicSliceKey 必须是 canonical video public slice")
    if target == "prod-hosted" and public_slice_key:
        lowered = public_slice_key.lower()
        if any(token in lowered for token in PRODUCTION_FORBIDDEN_TOKENS):
            issues.append(
                f"{prefix}.media.publicSliceKey 不得引用 fixture/mock/seed/test production canary",
            )
    post = _mapping(report.get("post"))
    post_id = _require_string(post, "postId", issues, prefix=f"{prefix}.post")
    if target == "prod-hosted" and post_id:
        lowered_post_id = post_id.lower()
        if any(token in lowered_post_id for token in PRODUCTION_FORBIDDEN_TOKENS):
            issues.append(
                f"{prefix}.post.postId 不得引用 fixture/mock/seed/test production canary",
            )

    service = _mapping(report.get("serviceEvidence"))
    range_evidence = _mapping(service.get("videoRange"))
    try:
        range_status = int(range_evidence.get("statusCode"))
    except (TypeError, ValueError):
        range_status = 0
    if range_status != 206:
        issues.append(f"{prefix}.serviceEvidence.videoRange.statusCode 必须为 206")
    mime_type = _non_empty_string(range_evidence.get("mimeType")).lower()
    if not mime_type.startswith("video/"):
        issues.append(f"{prefix}.serviceEvidence.videoRange.mimeType 必须为 video/*")
    _require_string(
        range_evidence,
        "reportPath",
        issues,
        prefix=f"{prefix}.serviceEvidence.videoRange",
    )

    ui = _mapping(report.get("uiEvidence"))
    if ui.get("stageRendered") is not True:
        issues.append(f"{prefix}.uiEvidence.stageRendered 必须为 true")
    if ui.get("playerReady") is not True:
        issues.append(f"{prefix}.uiEvidence.playerReady 必须为 true")
    if ui.get("playerError") is not False:
        issues.append(f"{prefix}.uiEvidence.playerError 必须为 false")
    ui_prefix = f"{prefix}.uiEvidence"
    for artifact_field in (
        "reportPath",
        "screenshotPath",
        "recordingPath",
        "nativePlaybackRawLogPath",
        "qoeReadbackPath",
        "perfettoTracePath",
        "perfettoSummaryPath",
    ):
        _require_string(ui, artifact_field, issues, prefix=ui_prefix)
    if ui.get("seekTargetsVerified") is not True:
        issues.append(f"{prefix}.uiEvidence.seekTargetsVerified 必须为 true")
    if ui.get("nativeFirstFrame") is not True:
        issues.append(f"{prefix}.uiEvidence.nativeFirstFrame 必须为 true")
    if ui.get("nativeSeekSettled") is not True:
        issues.append(f"{prefix}.uiEvidence.nativeSeekSettled 必须为 true")
    if ui.get("nativeEvidenceFromPhysicalAndroidDevice") is not True:
        issues.append(
            f"{prefix}.uiEvidence.nativeEvidenceFromPhysicalAndroidDevice 必须为 true",
        )
    if _non_empty_string(ui.get("nativeEvidenceDevicePlatform")) != "android":
        issues.append(
            f"{prefix}.uiEvidence.nativeEvidenceDevicePlatform 必须为 android",
        )
    if ui.get("nativeEvidenceDeviceEmulator") is not False:
        issues.append(
            f"{prefix}.uiEvidence.nativeEvidenceDeviceEmulator 必须为 false",
        )
    if ui.get("physicalIosPatrolPassed") is not True:
        issues.append(f"{prefix}.uiEvidence.physicalIosPatrolPassed 必须为 true")
    if _non_empty_string(ui.get("seekEvidenceSource")) != "native_settled":
        issues.append(f"{prefix}.uiEvidence.seekEvidenceSource 必须为 native_settled")
    if check_artifacts:
        validate_report_artifacts(report, artifact_root, issues, prefix)
    return issues


def validate_evidence_document(
    document: object,
    *,
    require_matrix: bool = False,
    check_artifacts: bool = False,
    artifact_root: Path | None = None,
) -> list[str]:
    """返回所有违反 T4 视频证据合同的原因；空列表表示通过。"""

    if not isinstance(document, dict):
        return ["T4 evidence 根对象必须为 JSON object"]
    resolved_artifact_root = artifact_root or REPO_ROOT

    is_matrix = _non_empty_string(document.get("scenario")) == MATRIX_SCENARIO
    if require_matrix and not is_matrix:
        return [
            "发布级 T4 门禁必须提供四环境矩阵报告，单环境报告不能作为商用准入证据",
        ]

    if is_matrix:
        if document.get("schema") != MATRIX_SCHEMA:
            return [f"matrix.schema 必须为 {MATRIX_SCHEMA}"]
        reports = document.get("reports")
        if not isinstance(reports, list) or not reports:
            return ["matrix.reports 必须为非空列表"]
        issues: list[str] = []
        seen_keys: set[tuple[str, str]] = set()
        commits: set[str] = set()
        media_identities: set[tuple[str, int, str]] = set()
        release_identities: set[tuple[str, str, str, str]] = set()
        prod_config_hashes: set[str] = set()
        prod_post_ids: set[str] = set()
        for index, report in enumerate(reports):
            issues.extend(
                _validate_single_report(
                    report,
                    index=index,
                    check_artifacts=check_artifacts,
                    artifact_root=resolved_artifact_root,
                ),
            )
            if not isinstance(report, dict):
                continue
            environment = _mapping(report.get("environment"))
            key = (
                _non_empty_string(environment.get("target")),
                _non_empty_string(environment.get("rolloutStage")),
            )
            if key in seen_keys:
                issues.append(
                    f"matrix.reports 存在重复 target/stage: {key[0]}/{key[1]}",
                )
            seen_keys.add(key)
            commit = _non_empty_string(environment.get("commitSha"))
            if commit:
                commits.add(commit)
            config_hash = _non_empty_string(environment.get("configHash"))
            if key[0] == "prod-hosted" and config_hash:
                prod_config_hashes.add(config_hash)
            post_id = _non_empty_string(_mapping(report.get("post")).get("postId"))
            if key[0] == "prod-hosted" and post_id:
                prod_post_ids.add(post_id)
            media = _mapping(report.get("media"))
            try:
                version = int(media.get("assetVersion"))
            except (TypeError, ValueError):
                version = 0
            identity = (
                _non_empty_string(media.get("assetId")),
                version,
                _non_empty_string(media.get("probeHash")),
            )
            if all((identity[0], identity[2])) and identity[1] > 0:
                media_identities.add(identity)
            release = _mapping(report.get("release"))
            release_identity = (
                _non_empty_string(release.get("releaseId")),
                _non_empty_string(release.get("sourceOwner")),
                _non_empty_string(release.get("manifestDigest")),
                _non_empty_string(release.get("mediaManifestDigest")),
            )
            if all(release_identity):
                release_identities.add(release_identity)
        missing = REQUIRED_MATRIX_KEYS - seen_keys
        for target, stage in sorted(missing):
            issues.append(f"matrix.reports 缺少 {target}/{stage} 证据")
        unexpected = seen_keys - REQUIRED_MATRIX_KEYS
        for target, stage in sorted(unexpected):
            issues.append(f"matrix.reports 包含非准入 target/stage: {target}/{stage}")
        if len(commits) > 1:
            issues.append("matrix.reports 必须绑定同一 commitSha")
        if len(media_identities) > 1:
            issues.append("matrix.reports 必须绑定同一 assetId/assetVersion/probeHash")
        if len(release_identities) > 1:
            issues.append(
                "matrix.reports 必须绑定同一 releaseId/manifestDigest/"
                "mediaManifestDigest/sourceOwner"
            )
        if len(prod_config_hashes) > 1:
            issues.append("prod-hosted 三阶段必须绑定同一 production configHash")
        if len(prod_post_ids) > 1:
            issues.append("prod-hosted 三阶段必须绑定同一 postId")
        return issues

    return _validate_single_report(
        document,
        index=0,
        check_artifacts=check_artifacts,
        artifact_root=resolved_artifact_root,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="T4 JSON report 或 matrix manifest")
    parser.add_argument(
        "--require-matrix",
        action="store_true",
        help="发布级门禁要求 alpha/beta/gamma/prod 三阶段完整矩阵",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    path = Path(args.evidence).expanduser()
    if not path.is_file():
        print(f"[verify_runtime_media_t4_evidence] FAIL: evidence file not found: {path}")
        return 2
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[verify_runtime_media_t4_evidence] FAIL: unable to read JSON: {exc}")
        return 2

    issues = validate_evidence_document(
        document,
        require_matrix=args.require_matrix,
        check_artifacts=True,
        artifact_root=REPO_ROOT,
    )
    if issues:
        print("[verify_runtime_media_t4_evidence] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_runtime_media_t4_evidence] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
