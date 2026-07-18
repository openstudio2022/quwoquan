#!/usr/bin/env python3
"""校验 runtime-media 视频播放 T4 非 dry-run 证据的最小商用合同。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_SCHEMA = "runtime-media-video-playback-t4-report"
MATRIX_SCHEMA = "runtime-media-video-playback-t4-matrix-report"
SCENARIO = "runtime_media.video_playback_t4"
MATRIX_SCENARIO = "runtime_media.video_playback_t4_matrix"
PRODUCTION_FORBIDDEN_TOKENS = frozenset({"fixture", "mock", "seed", "test"})


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
    if target == "prod-hosted" and stage != "gray-initial":
        issues.append(
            f"{prefix}.rolloutStage 必须为 gray-initial，当前为 {stage or '<empty>'}",
        )
    elif target and target != "prod-hosted" and stage not in {"local", "not-applicable"}:
        issues.append(
            f"{prefix}.rolloutStage 对本地 target 必须为 local 或 not-applicable，当前为 {stage or '<empty>'}",
        )
    return target, env


def _validate_single_report(report: object, *, index: int) -> list[str]:
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
    target, _ = _validate_target(environment, issues, prefix=f"{prefix}.environment")
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

    media = _mapping(report.get("media"))
    public_slice_key = _require_string(media, "publicSliceKey", issues, prefix=f"{prefix}.media")
    if public_slice_key and not public_slice_key.startswith("media/video/s/"):
        issues.append(f"{prefix}.media.publicSliceKey 必须是 canonical video public slice")
    if target == "prod-hosted" and public_slice_key:
        lowered = public_slice_key.lower()
        if any(token in lowered for token in PRODUCTION_FORBIDDEN_TOKENS):
            issues.append(
                f"{prefix}.media.publicSliceKey 不得引用 fixture/mock/seed/test production canary",
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

    ui = _mapping(report.get("uiEvidence"))
    if ui.get("stageRendered") is not True:
        issues.append(f"{prefix}.uiEvidence.stageRendered 必须为 true")
    if ui.get("playerReady") is not True:
        issues.append(f"{prefix}.uiEvidence.playerReady 必须为 true")
    if ui.get("playerError") is not False:
        issues.append(f"{prefix}.uiEvidence.playerError 必须为 false")
    _require_string(ui, "reportPath", issues, prefix=f"{prefix}.uiEvidence")
    _require_string(ui, "screenshotPath", issues, prefix=f"{prefix}.uiEvidence")
    return issues


def validate_evidence_document(document: object) -> list[str]:
    """返回所有违反 T4 视频证据合同的原因；空列表表示通过。"""

    if not isinstance(document, dict):
        return ["T4 evidence 根对象必须为 JSON object"]

    if _non_empty_string(document.get("scenario")) == MATRIX_SCENARIO:
        if document.get("schema") != MATRIX_SCHEMA:
            return [f"matrix.schema 必须为 {MATRIX_SCHEMA}"]
        reports = document.get("reports")
        if not isinstance(reports, list) or not reports:
            return ["matrix.reports 必须为非空列表"]
        issues: list[str] = []
        for index, report in enumerate(reports):
            issues.extend(_validate_single_report(report, index=index))
        return issues

    return _validate_single_report(document, index=0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="T4 JSON report 或 matrix manifest")
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

    issues = validate_evidence_document(document)
    if issues:
        print("[verify_runtime_media_t4_evidence] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_runtime_media_t4_evidence] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
