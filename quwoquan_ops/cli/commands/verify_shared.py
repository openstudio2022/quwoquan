"""stackctl verify 域共享执行层（静态波次 / profile 调度 / test-data / 播放证据）。

从 stackctl.py 逐字迁出仅被 verify 域消费的执行期 helper：

- `_run_static_verify_wave`：只读静态门禁与 content readiness 的单波并行；
- `_run_profile_command` / `_is_patrol_profile_command` /
  `_run_profile_commands_parallel`：profile 命令的 typed Actor 作用域执行
  与 health→parallel→Patrol 安全波次调度；
- `_typed_profile_actor_context`：候选绑定的 profile 本地 Actor 上下文；
- `_run_test_data_profile` / `_validate_test_data_request_for_profile`：
  选中强类型 test-data request 的执行与 release 套件校验；
- `_data_readiness_path_from_verify_args`：release profile 的 canonical
  data readiness receipt 定位；
- `_current_commit_sha` / `_runtime_media_config_hash` / `_profile_step` /
  `_release_video_preflight_from_steps` / `_video_range_evidence_from_preflight` /
  `_video_ui_evidence_from_smoke` / `_runtime_media_playback_evidence`：
  release 验证的 runtime-media 播放证据聚合。

data readiness 真相源（`_load_test_data_release_readiness` /
`_data_release_readiness_path` / `_DATA_READINESS_DIGEST_RE`）、
`_verify_child_environment`、`_read_json_object` 与 `ProfileActorCaseId`
仍由 stackctl 命名空间拥有（留守域共用）。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与上述协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块
符号互调），保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.model import TestDataContext
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime


def _current_commit_sha() -> str:
    import quwoquan_ops.cli.stackctl as _stackctl

    configured = os.environ.get("GITHUB_SHA", "").strip()
    if configured:
        return configured
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_stackctl.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _runtime_media_config_hash(target_name: str) -> str:
    """将当前 target 的 topology 与 App runtime 配置绑定到播放证据。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    config_path = _stackctl.ROOT / "quwoquan_app" / "configs" / env_name / "app_runtime.yaml"
    digest = hashlib.sha256()
    digest.update(
        json.dumps(target, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    )
    if config_path.is_file():
        digest.update(config_path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _profile_step(steps: list[dict[str, Any]], name_fragment: str) -> dict[str, Any]:
    for step in steps:
        if name_fragment in str(step.get("name") or ""):
            return step
    return {}


def _release_video_preflight_from_steps(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Load the one typed release canary report from this playback execution."""
    import quwoquan_ops.cli.stackctl as _stackctl

    step = _stackctl._profile_step(steps, "release-video-canary-preflight")
    report = _stackctl._read_json_object(str(step.get("reportPath") or ""))
    if not report:
        try:
            parsed_stdout = json.loads(str(step.get("stdout") or ""))
        except json.JSONDecodeError:
            parsed_stdout = {}
        report = parsed_stdout if isinstance(parsed_stdout, dict) else {}
    if report:
        report["_reportPath"] = str(step.get("reportPath") or "")
        return report
    return {}


def _video_range_evidence_from_preflight(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project Range/MIME only from the typed release canary report."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report = _stackctl._release_video_preflight_from_steps(steps)
    delivery = report.get("delivery") if isinstance(report, dict) else None
    delivery = delivery if isinstance(delivery, dict) else {}
    return {
        "statusCode": delivery.get("rangeStatus"),
        "mimeType": delivery.get("mimeType"),
        "reportPath": str(report.get("_reportPath") or ""),
    }


def _video_ui_evidence_from_smoke(steps: list[dict[str, Any]]) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    step = _stackctl._profile_step(steps, "environment-page-smoke")
    report_path = str(step.get("reportPath") or "")
    report = _stackctl._read_json_object(report_path)
    runs = report.get("runs")
    if not isinstance(runs, list):
        runs = []
    successful_runs = [
        item
        for item in runs
        if isinstance(item, dict) and item.get("exitCode") == 0
    ]
    native_evidence_run: dict[str, Any] | None = None
    physical_ios_run: dict[str, Any] | None = None
    for run_item in successful_runs:
        device = run_item.get("device")
        evidence = run_item.get("evidence")
        if not isinstance(device, dict) or not isinstance(evidence, dict):
            continue
        platform = str(device.get("targetPlatform") or "").lower()
        if (
            platform.startswith("ios")
            and device.get("emulator") is False
            and physical_ios_run is None
        ):
            physical_ios_run = run_item
        if not platform.startswith("android"):
            continue
        playback = evidence.get("videoPlayback")
        if not isinstance(playback, dict):
            continue
        if (
            native_evidence_run is None
            and device.get("emulator") is False
            and playback.get("nativeFirstFrame") is True
            and playback.get("nativeSeekSettled") is True
        ):
            native_evidence_run = run_item
    selected_run = native_evidence_run or (
        successful_runs[0] if successful_runs else None
    )
    screenshot_path = ""
    selected_evidence = (
        selected_run.get("evidence") if isinstance(selected_run, dict) else None
    )
    if isinstance(selected_evidence, dict):
        evidence = selected_evidence
        screenshot = evidence.get("afterScreenshot")
        if isinstance(screenshot, dict):
            screenshot_path = str(screenshot.get("path") or "").strip()
    native_playback_raw_log_path = (
        str(selected_evidence.get("rawLogPath") or "").strip()
        if native_evidence_run is not None and isinstance(selected_evidence, dict)
        else ""
    )
    native_playback_log = Path(native_playback_raw_log_path)
    if native_playback_raw_log_path and not native_playback_log.is_absolute():
        native_playback_log = _stackctl.ROOT / native_playback_log
    native_playback = _stackctl.read_native_video_playback_evidence(native_playback_log)
    physical_android_native_evidence = (
        native_evidence_run is not None
        and native_playback.get("nativeFirstFrame") is True
        and native_playback.get("nativeSeekSettled") is True
    )
    passed = (
        str(report.get("status") or "").strip().lower() == "passed"
        and bool(successful_runs)
    )
    output_summaries = "\n".join(
        str(item.get("outputSummary") or "")
        for item in runs
        if isinstance(item, dict)
    )
    if passed:
        stage_rendered: bool | None = True
        player_ready = True
        player_error: bool | None = False
        player_state = "ready"
    elif "configured video canary stage should render" in output_summaries:
        stage_rendered = False
        player_ready = False
        player_error = None
        player_state = "stage-not-rendered"
    elif "native video player entered its explicit error state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = True
        player_state = "explicit-error"
    elif "native video player must reach ready state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = None
        player_state = "ready-timeout"
    else:
        stage_rendered = None
        player_ready = False
        player_error = None
        player_state = "unverified"
    return {
        "stageRendered": stage_rendered,
        "playerReady": player_ready,
        "playerError": player_error,
        "playerState": player_state,
        "reportPath": report_path,
        "screenshotPath": screenshot_path,
        "recordingPath": os.environ.get(
            "VIDEO_PLAYBACK_CANARY_RECORDING_PATH",
            "",
        ).strip(),
        "seekTargetsVerified": passed,
        "nativeFirstFrame": physical_android_native_evidence,
        "nativeSeekSettled": physical_android_native_evidence,
        "nativeEvidenceFromPhysicalAndroidDevice": physical_android_native_evidence,
        "nativeEvidenceDevicePlatform": (
            "android" if physical_android_native_evidence else ""
        ),
        "nativeEvidenceDeviceEmulator": (
            False if physical_android_native_evidence else None
        ),
        "nativePlaybackRawLogPath": native_playback_raw_log_path,
        "physicalIosPatrolPassed": physical_ios_run is not None,
        "seekEvidenceSource": (
            "native_settled"
            if physical_android_native_evidence
            else "unverified"
        ),
        "qoeReadbackPath": os.environ.get(
            "VIDEO_PLAYBACK_QOE_READBACK_PATH",
            "",
        ).strip(),
        "perfettoTracePath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_TRACE_PATH",
            "",
        ).strip(),
        "perfettoSummaryPath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_SUMMARY_PATH",
            "",
        ).strip(),
        "iosPerformanceTracePath": os.environ.get(
            "VIDEO_PLAYBACK_IOS_PERFORMANCE_TRACE_PATH",
            "",
        ).strip(),
        "iosPerformanceSummaryPath": os.environ.get(
            "VIDEO_PLAYBACK_IOS_PERFORMANCE_SUMMARY_PATH",
            "",
        ).strip(),
    }


def _runtime_media_playback_evidence(
    *,
    target_name: str,
    steps: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    public_bases = target.get("publicBases")
    public_bases = public_bases if isinstance(public_bases, dict) else {}
    preflight = _stackctl._release_video_preflight_from_steps(steps)
    release_identity = (
        dict(preflight.get("release"))
        if isinstance(preflight.get("release"), dict)
        else {}
    )
    video_identity = (
        dict(preflight.get("video"))
        if isinstance(preflight.get("video"), dict)
        else {}
    )
    service_evidence = {
        "videoRange": _stackctl._video_range_evidence_from_preflight(steps),
    }
    ui_evidence = _stackctl._video_ui_evidence_from_smoke(steps)
    media_identity = {
        "assetId": str(video_identity.get("assetId") or ""),
        "assetVersion": video_identity.get("assetVersion"),
        "probeHash": str(video_identity.get("expectedHash") or ""),
    }
    public_slice_key = str(video_identity.get("publicSliceKey") or "")
    post_id = str(video_identity.get("postId") or "")
    video_range = service_evidence["videoRange"]
    dry_run = os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    is_passed = (
        bool(public_slice_key)
        and bool(post_id)
        and preflight.get("schema")
        == "quwoquan_ops.release_video_delivery_evidence"
        and preflight.get("status") == "passed"
        and preflight.get("target") == target_name
        and release_identity.get("sourceOwner") == "qwq_data"
        and bool(release_identity.get("releaseId"))
        and bool(release_identity.get("importRunId"))
        and bool(release_identity.get("verifyRunId"))
        and bool(release_identity.get("readinessReceiptRef"))
        and _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
            str(release_identity.get("manifestDigest") or "")
        )
        is not None
        and _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
            str(release_identity.get("mediaManifestDigest") or "")
        )
        is not None
        and bool(media_identity.get("assetId"))
        and isinstance(media_identity.get("assetVersion"), int)
        and not isinstance(media_identity.get("assetVersion"), bool)
        and media_identity["assetVersion"] > 0
        and bool(media_identity.get("probeHash"))
        and not dry_run
        and video_range.get("statusCode") == 206
        and str(video_range.get("mimeType") or "").lower().startswith("video/")
        and ui_evidence["playerReady"] is True
        and ui_evidence["playerError"] is False
        and ui_evidence["nativeFirstFrame"] is True
        and ui_evidence["nativeSeekSettled"] is True
        and ui_evidence["nativeEvidenceFromPhysicalAndroidDevice"] is True
        and ui_evidence["physicalIosPatrolPassed"] is True
        and bool(ui_evidence["qoeReadbackPath"])
        and bool(ui_evidence["perfettoTracePath"])
        and bool(ui_evidence["perfettoSummaryPath"])
        and bool(ui_evidence["iosPerformanceTracePath"])
        and bool(ui_evidence["iosPerformanceSummaryPath"])
    )
    return {
        "schema": "runtime-media-video-playback-evidence-report",
        "scenario": "runtime_media.video_playback_evidence",
        "status": "passed" if is_passed else "failed",
        "dryRun": dry_run,
        "startedAt": started_at,
        "endedAt": ended_at,
        "environment": {
            "env": env_name,
            "target": target_name,
            "rolloutStage": (
                os.environ.get("PROD_ROLLOUT_STAGE", "").strip()
                if target_name == "prod-hosted"
                else "local"
            ),
            "mediaVideoBaseUrl": str(public_bases.get("mediaVideo") or "").rstrip("/"),
            "commitSha": _stackctl._current_commit_sha(),
            "configHash": _stackctl._runtime_media_config_hash(target_name),
        },
        "release": release_identity,
        "media": {
            "publicSliceKey": public_slice_key,
            **media_identity,
        },
        "post": {
            "postId": post_id,
        },
        "serviceEvidence": service_evidence,
        "uiEvidence": ui_evidence,
    }


def _run_test_data_profile(
    args: argparse.Namespace,
    *,
    profile: VerificationProfile,
    environment: str,
    target_name: str,
    report_dir: Path,
    prerequisites_passed: bool,
    static_gate_ms: int = 0,
    environment_start_ms: int = 0,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    result_dir = report_dir / "test-data"
    static_gate_started = time.monotonic()
    if not prerequisites_passed:
        result = {
            "schema": "qwq.case_result",
            "caseId": "alpha-beta-gamma-selected-test-data",
            "status": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target_name,
            "environment": environment,
            "environmentStartMs": 0,
            "environmentStartSource": "prestarted-environment",
            "staticGateMs": max(0, int(static_gate_ms)),
            "baselineEligible": False,
            "specRefs": [
                "specs/feature-tree/spec.md#uat-009",
                "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
                "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
            ],
            "issues": [
                "test-data mutation was not started because prerequisite gates failed"
            ],
        }
        _stackctl.write_json(result_dir / "case-result.json", result)
        return result

    try:
        active = _stackctl.active_deployment_candidate(target_name)
        if active is None:
            raise ValueError("active immutable deployment candidate is required")
        manifest = _stackctl.load_candidate_manifest(
            environment,
            target_name,
            active["baselineId"],
            require_full=True,
        )
        readiness, _ = _stackctl._load_test_data_release_readiness(
            environment=environment,
            release_id=str(getattr(args, "data_release_id", "") or ""),
            verify_run_id=str(getattr(args, "data_verify_run_id", "") or ""),
            manifest_digest=str(
                getattr(args, "data_manifest_digest", "") or ""
            ),
        )
        raw_request_path = str(getattr(args, "test_data_request", "") or "").strip()
        if not raw_request_path:
            raise ValueError("--test-data-request is required")
        request_path = Path(raw_request_path).expanduser()
        if not request_path.is_absolute():
            request_path = _stackctl.ROOT / request_path
        request_path = request_path.resolve()
        request_document = json.loads(request_path.read_text(encoding="utf-8"))
        _stackctl._validate_test_data_request_for_profile(profile, request_document)
        raw_evidence_path = str(getattr(args, "test_data_evidence", "") or "").strip()
        evidence_path: Path | None = None
        if raw_evidence_path:
            evidence_path = Path(raw_evidence_path).expanduser()
            if not evidence_path.is_absolute():
                evidence_path = _stackctl.ROOT / evidence_path
            evidence_path = evidence_path.resolve()
        raw_handoff_path = str(
            getattr(args, "test_data_handoff", "") or ""
        ).strip()
        if profile is VerificationProfile.RELEASE and not raw_handoff_path:
            raise ValueError("--test-data-handoff is required for release test-data")
        handoff_path: Path | None = None
        if raw_handoff_path:
            handoff_path = Path(raw_handoff_path).expanduser()
            if not handoff_path.is_absolute():
                handoff_path = _stackctl.ROOT / handoff_path
            handoff_path = handoff_path.resolve()
        evidence_root = _stackctl.output_root().expanduser().resolve()
        for label, path in (
            ("request", request_path),
            ("evidence", evidence_path),
            ("handoff", handoff_path),
        ):
            if path is None:
                continue
            try:
                path.relative_to(evidence_root)
            except ValueError as exc:
                raise ValueError(
                    f"test-data {label} must be below QWQ_OUTPUT_ROOT"
                ) from exc
        topology = _stackctl.load_environment_topology()
        target = _stackctl.get_target(topology, target_name)
        base_url = str((target.get("publicBases") or {}).get("api") or "").rstrip(
            "/"
        )
        if not base_url.startswith("https://"):
            raise ValueError("test-data control plane requires canonical HTTPS API")
        return _stackctl.run_test_data_verification(
            environment=environment,
            target=target_name,
            base_url=base_url,
            candidate_manifest=manifest,
            release_readiness=readiness,
            request_path=request_path,
            evidence_path=evidence_path,
            report_dir=result_dir,
            handoff_path=handoff_path,
            static_gate_ms=max(
                max(0, int(static_gate_ms)),
                round((time.monotonic() - static_gate_started) * 1000),
            ),
            environment_start_ms=max(0, int(environment_start_ms)),
            environment_start_source="stackctl-verify-pre-test-data",
            benchmark_policy=str(
                getattr(args, "test_data_benchmark_policy", "normal")
            ),
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result = {
            "schema": "qwq.case_result",
            "caseId": "alpha-beta-gamma-selected-test-data",
            "status": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target_name,
            "environment": environment,
            "environmentStartMs": 0,
            "environmentStartSource": "prestarted-environment",
            "staticGateMs": max(
                max(0, int(static_gate_ms)),
                round((time.monotonic() - static_gate_started) * 1000),
            ),
            "baselineEligible": False,
            "specRefs": [
                "specs/feature-tree/spec.md#uat-009",
                "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
                "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
            ],
            "issues": [str(exc)],
        }
        _stackctl.write_json(result_dir / "case-result.json", result)
        return result


def _validate_test_data_request_for_profile(
    profile: VerificationProfile,
    document: Mapping[str, Any],
) -> None:
    """Release runs use the governed critical Journey set; integration selects freely."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if profile is not VerificationProfile.RELEASE:
        return
    selected = _stackctl.load_case_requests(document)
    selected_case_ids = tuple(case.case_id for case in selected)
    canonical_case_ids = tuple(
        case.case_id for case in _stackctl.canonical_acceptance_suite()
    )
    if selected_case_ids != canonical_case_ids:
        raise ValueError(
            "release profile requires the canonical seven-domain test-data request"
        )


def _typed_profile_actor_context(
    args: argparse.Namespace,
    *,
    environment: str,
    target_name: str,
    report_dir: Path,
    runtime: TestDataRuntime,
) -> TestDataContext:
    """Build one candidate-bound context for profile-local Actor capabilities."""
    import quwoquan_ops.cli.stackctl as _stackctl

    active = _stackctl.active_deployment_candidate(target_name)
    if not isinstance(active, Mapping):
        raise RuntimeError("active immutable deployment candidate is required")
    manifest = _stackctl.load_candidate_manifest(
        environment,
        target_name,
        str(active.get("baselineId") or ""),
        require_full=True,
    )
    readiness, _ = _stackctl._load_test_data_release_readiness(
        environment=environment,
        release_id=str(getattr(args, "data_release_id", "") or ""),
        verify_run_id=str(getattr(args, "data_verify_run_id", "") or ""),
        manifest_digest=str(getattr(args, "data_manifest_digest", "") or ""),
    )
    candidate = _stackctl.build_candidate_binding(
        environment=environment,
        target=target_name,
        manifest=manifest,
        readiness=readiness,
    )
    raw_evidence_path = str(
        getattr(args, "test_data_evidence", "") or ""
    ).strip()
    evidence_path: Path | None = None
    if raw_evidence_path:
        evidence_path = Path(raw_evidence_path).expanduser()
        if not evidence_path.is_absolute():
            evidence_path = _stackctl.ROOT / evidence_path
        evidence_path = evidence_path.resolve()
    provider_evidence = _stackctl.load_provider_evidence(evidence_path, candidate)
    target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
    base_url = str((target.get("publicBases") or {}).get("api") or "").rstrip(
        "/"
    )
    return TestDataContext(
        candidate=candidate,
        base_url=base_url,
        output_root=report_dir / "profile-test-data",
        provider_evidence=provider_evidence,
        runtime=runtime,
    )


def _run_profile_command(
    profile_command: Mapping[str, Any],
    *,
    target_name: str,
    actor_context: TestDataContext | None,
) -> subprocess.CompletedProcess[str]:
    """Run one profile command inside its typed Actor scope when declared."""
    import quwoquan_ops.cli.stackctl as _stackctl

    case_id = profile_command.get("testDataActorCase")
    command_environment = dict(profile_command.get("env") or {})
    if case_id is None:
        return _stackctl.run(
            list(profile_command["argv"]),
            cwd=profile_command.get("cwd"),
            env=_stackctl._verify_child_environment(target_name, command_environment),
        )
    if not isinstance(case_id, _stackctl.ProfileActorCaseId) or actor_context is None:
        raise RuntimeError("typed profile Actor context is unavailable")
    for legacy_key in (
        "TEST_AUTH_TOKEN",
        "TEST_REFRESH_TOKEN",
        "APP_CURRENT_OWNER_ID",
        "APP_CURRENT_PERSONA_ID",
    ):
        command_environment.pop(legacy_key, None)
    runtime = actor_context.runtime
    if not isinstance(runtime, TestDataRuntime):
        raise TypeError("typed profile Actor runtime is unavailable")
    raw_roles = profile_command.get("testDataActorRoles") or (
        ActorRole.PRIMARY,
    )
    roles = tuple(raw_roles)
    if not roles or any(not isinstance(role, ActorRole) for role in roles):
        raise TypeError("typed profile Actor roles are invalid")
    request = _stackctl.AUTHENTICATED_ACTORS.bind(
        _stackctl.AuthenticatedActorsParams(roles=roles)
    )
    session = _stackctl.TestDataSession.for_case(case_id, context=actor_context)
    with session.provision(request) as provisioned:
        for role in roles:
            actor_handle = provisioned.value.require(role)
            actor = runtime.actor(actor_handle)
            prefix = "QWQ_TEST_DATA_" + role.value.upper()
            command_environment.update(
                {
                    prefix + "_ACCESS_TOKEN": actor.session.access_token,
                    prefix + "_REFRESH_TOKEN": actor.session.refresh_token,
                    prefix + "_OWNER_ID": actor.session.owner_id,
                    prefix + "_PERSONA_ID": actor.session.persona_id,
                }
            )
            if role is ActorRole.PRIMARY:
                command_environment.update(
                    {
                        "QWQ_TEST_DATA_ACCESS_TOKEN": actor.session.access_token,
                        "QWQ_TEST_DATA_REFRESH_TOKEN": actor.session.refresh_token,
                        "QWQ_TEST_DATA_OWNER_ID": actor.session.owner_id,
                        "QWQ_TEST_DATA_PERSONA_ID": actor.session.persona_id,
                    }
                )
        return _stackctl.run(
            list(profile_command["argv"]),
            cwd=profile_command.get("cwd"),
            env=_stackctl._verify_child_environment(target_name, command_environment),
        )


def _run_static_verify_wave(
    commands: Sequence[Sequence[str]],
    *,
    target_name: str,
    readiness_call: Callable[[], dict[str, Any]] | None = None,
    max_concurrency: int = 4,
) -> tuple[
    list[tuple[list[str], subprocess.CompletedProcess[str], int]],
    dict[str, Any] | None,
    int,
]:
    """Run independent read-only gates and candidate readiness in one wave."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if not 1 <= max_concurrency <= 8:
        raise ValueError("static verify concurrency must be within 1..8")
    normalized = [list(command) for command in commands]
    wave_started = time.monotonic()

    def execute(command: list[str]) -> tuple[subprocess.CompletedProcess[str], int]:
        started = time.monotonic()
        result = _stackctl.run(
            command,
            env=_stackctl._verify_child_environment(target_name),
        )
        return result, max(0, round((time.monotonic() - started) * 1000))

    task_count = len(normalized) + (1 if readiness_call is not None else 0)
    if task_count == 0:
        return [], None, 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_concurrency, task_count),
        thread_name_prefix="stackctl-static-verify",
    ) as pool:
        command_futures = [pool.submit(execute, command) for command in normalized]
        readiness_future = (
            pool.submit(readiness_call) if readiness_call is not None else None
        )
        # Preserve declared order in evidence while processes execute in
        # parallel; stable reports must not depend on completion order.
        command_results = [
            (command, *future.result())
            for command, future in zip(normalized, command_futures)
        ]
        readiness = readiness_future.result() if readiness_future is not None else None
    return (
        command_results,
        readiness,
        max(0, round((time.monotonic() - wave_started) * 1000)),
    )


def _is_patrol_profile_command(command: Mapping[str, Any]) -> bool:
    argv = " ".join(str(item) for item in command.get("argv", ()))
    return "run_environment_patrol_smoke.py" in argv or "patrol" in str(
        command.get("name") or ""
    ).lower()


def _run_profile_commands_parallel(
    commands: Sequence[Mapping[str, Any]],
    *,
    target_name: str,
    actor_context: TestDataContext | None,
    max_concurrency: int = 4,
) -> list[tuple[Mapping[str, Any], subprocess.CompletedProcess[str], int, bool]]:
    """Run profile gates by safe waves, keeping Flutter/Patrol work exclusive."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if not 1 <= max_concurrency <= 8:
        raise ValueError("profile verify concurrency must be within 1..8")
    indexed = list(enumerate(commands))
    health = [
        item
        for item in indexed
        if "health" in str(item[1].get("name") or "").lower()
    ]
    patrol = [
        item
        for item in indexed
        if item not in health and _stackctl._is_patrol_profile_command(item[1])
    ]
    parallel = [item for item in indexed if item not in health and item not in patrol]
    results: dict[
        int,
        tuple[Mapping[str, Any], subprocess.CompletedProcess[str], int, bool],
    ] = {}

    def execute(
        command: Mapping[str, Any],
    ) -> tuple[subprocess.CompletedProcess[str], int]:
        started = time.monotonic()
        try:
            result = _stackctl._run_profile_command(
                command,
                target_name=target_name,
                actor_context=actor_context,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                args=list(command["argv"]),
                returncode=2,
                stdout="",
                stderr=(
                    "typed profile Actor provision/test/cleanup failed: "
                    + str(exc)
                ),
            )
        return result, max(0, round((time.monotonic() - started) * 1000))

    health_blocked = False
    for index, command in health:
        result, duration_ms = execute(command)
        results[index] = (command, result, duration_ms, False)
        if result.returncode != 0 and bool(command.get("blocking", True)):
            health_blocked = True

    if health_blocked:
        for index, command in (*parallel, *patrol):
            skipped = subprocess.CompletedProcess(
                args=list(command["argv"]),
                returncode=2,
                stdout="",
                stderr="environment health prerequisite failed; profile node not started",
            )
            results[index] = (command, skipped, 0, True)
        return [results[index] for index, _ in indexed]

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_concurrency, len(parallel)),
            thread_name_prefix="stackctl-profile-verify",
        ) as pool:
            futures = [pool.submit(execute, command) for _, command in parallel]
            for (index, command), future in zip(parallel, futures):
                result, duration_ms = future.result()
                results[index] = (command, result, duration_ms, False)

    prerequisite_blocked = any(
        result.returncode != 0 and bool(command.get("blocking", True))
        for command, result, _duration_ms, _skipped in results.values()
    )
    for index, command in patrol:
        if prerequisite_blocked:
            skipped = subprocess.CompletedProcess(
                args=list(command["argv"]),
                returncode=2,
                stdout="",
                stderr="blocking profile prerequisite failed; Patrol node not started",
            )
            results[index] = (command, skipped, 0, True)
            continue
        result, duration_ms = execute(command)
        results[index] = (command, result, duration_ms, False)
        if result.returncode != 0 and bool(command.get("blocking", True)):
            prerequisite_blocked = True

    return [results[index] for index, _ in indexed]


def _data_readiness_path_from_verify_args(
    args: argparse.Namespace,
    *,
    environment: str,
    profile: VerificationProfile,
) -> Path | None:
    import quwoquan_ops.cli.stackctl as _stackctl

    if profile is not VerificationProfile.RELEASE:
        return None
    release_id = str(getattr(args, "data_release_id", "") or "").strip()
    verify_run_id = str(getattr(args, "data_verify_run_id", "") or "").strip()
    manifest_digest = str(
        getattr(args, "data_manifest_digest", "") or ""
    ).strip()
    if not release_id or not verify_run_id or not manifest_digest:
        return None
    return _stackctl._data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
