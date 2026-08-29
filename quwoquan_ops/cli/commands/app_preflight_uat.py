"""stackctl `app-content-uat` immutable candidate 页面 UAT 编排。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_binding import (
    _APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS,
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    _app_content_launch_binding,
    _app_content_page_artifact_binding,
    _app_content_patrol_evidence,
    _app_content_readiness_path,
    _app_content_test_live_actor_context,
    _app_content_test_live_runtime_binding,
    _controlled_edge_recovery_evidence_issue,
    _ios_direct_flutter_log_reader_retryable,
    _run_app_content_message_home_command,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
    FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
    FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    materialize_app_content_launch_projection,
    verify_app_content_launch_projection,
    write_app_content_launch_control,
)
from quwoquan_ops.cli.commands.app_preflight_uat_patrol_dependency import (
    PatrolDependencyFailure,
    execute_patrol_with_dependency_cas,
    patrol_dependency_failure,
)
from quwoquan_ops.cli.commands.app_preflight_uat_platform import (
    execute_canonical_platform_launch,
)
from quwoquan_ops.cli.commands.app_preflight_uat_support import (
    _ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS,
    _BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS,
    APP_CONTENT_UAT_ENVELOPE_ARGUMENTS,
    APP_CORE_READBACK_UAT_TEST_TARGET,
    CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    DISCOVERY_FEED_UAT_TEST_TARGET,
    HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
    IOS_DIRECT_FLUTTER_RUN_UAT,
    MESSAGE_HOME_UAT_TEST_TARGET,
    PROFILE_JOURNEY_UAT_TEST_TARGET,
    STARTUP_FIRST_FRAME_UAT,
    VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
    _app_content_android_launch_command,
    _app_content_experience_screenshot_digests,
    _app_content_uat_requires_typed_actor,
    register_parser,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.model import TestDataContext
from quwoquan_ops.cli.smoke.environment_patrol_smoke.constants import (
    APP_CONTENT_VIDEO_PAGE_COUNT_ENV,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver import (
    EXTERNAL_AUT_CANONICAL_BINDING_ENV,
    encode_external_aut_canonical_binding,
)

__all__ = [
    "APP_CONTENT_UAT_ENVELOPE_ARGUMENTS",
    "APP_CORE_READBACK_UAT_TEST_TARGET",
    "CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET",
    "DISCOVERY_FEED_UAT_TEST_TARGET",
    "HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET",
    "IOS_DIRECT_FLUTTER_RUN_UAT",
    "MESSAGE_HOME_UAT_TEST_TARGET",
    "PROFILE_JOURNEY_UAT_TEST_TARGET",
    "STARTUP_FIRST_FRAME_UAT",
    "VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET",
    "_ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS",
    "_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS",
    "_BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS",
    "_app_content_experience_screenshot_digests",
    "_app_content_patrol_evidence",
    "_app_content_test_live_actor_context",
    "_app_content_test_live_runtime_binding",
    "_app_content_uat_requires_typed_actor",
    "_command_app_content_uat",
    "_ios_direct_flutter_log_reader_retryable",
    "_run_app_content_message_home_command",
    "command_app_content_uat",
    "register_parser",
]


def _command_app_content_uat(
    args: argparse.Namespace,
    *,
    initial_issues: Sequence[str] = (),
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    allowed_targets = {"alpha-local", "beta-local", "gamma-local"}
    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else _stackctl.repo_run_dir("app-content-uat", target="nonprod-local")
    )
    canonical_output_root = Path(_stackctl.output_root()).expanduser().resolve()
    issues = list(initial_issues)
    if not targets or len(targets) != len(set(targets)):
        issues.append("--targets must contain unique non-empty targets")
    unsupported = sorted(set(targets) - allowed_targets)
    if unsupported:
        issues.append("unsupported App content UAT targets: " + ", ".join(unsupported))
    device_id = str(getattr(args, "device_id", "") or "").strip()
    if not device_id:
        issues.append("--device-id is required")

    preflights: list[dict[str, Any]] = []
    runtime_bindings: list[dict[str, Any]] = []
    if not issues:
        for target in targets:
            result = _stackctl.command_app_debug_preflight(
                argparse.Namespace(
                    target=target,
                    report_dir=str(report_dir / target / "preflight"),
                    purpose="content_live",
                    runtime_mode="immutable_candidate",
                )
            )
            preflights.append(result)
            if int(result.get("exitCode", 2)) != 0:
                issues.append(
                    f"{target}: "
                    + str((result.get("details") or [result.get("summary")])[0])
                )
                break
            try:
                runtime_bindings.append(
                    _stackctl._app_content_test_live_runtime_binding(result)
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                issues.append(f"{target}: {exc}")
                break
    if not issues and preflights:
        releases = {str(item.get("releaseId") or "") for item in preflights}
        digests = {str(item.get("manifestDigest") or "") for item in preflights}
        release_trains = {
            str(item.get("releaseTrainId") or "") for item in runtime_bindings
        }
        app_uat_envelopes = {
            json.dumps(
                item.get("appUatEnvelope") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in preflights
        }
        app_uat_plans = {
            json.dumps(
                item.get("appUatPlan") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in preflights
        }
        if len(releases) != 1 or "" in releases:
            issues.append("Alpha/Beta/Gamma active releaseId is not identical")
        elif len(digests) != 1 or "" in digests:
            issues.append("Alpha/Beta/Gamma manifest digest is not identical")
        elif len(release_trains) != 1 or "" in release_trains:
            issues.append("Alpha/Beta/Gamma releaseTrainId is not identical")
        elif len(app_uat_envelopes) != 1 or "{}" in app_uat_envelopes:
            issues.append("Alpha/Beta/Gamma appUatEnvelope is not identical")
        elif len(app_uat_plans) != 1 or "{}" in app_uat_plans:
            issues.append("Alpha/Beta/Gamma appUatPlan is not identical")

    runs: list[dict[str, Any]] = []
    launch_bindings: dict[str, dict[str, str]] = {}
    launch_projections: dict[str, dict[str, str]] = {}
    experience_screenshot_digests: dict[str, dict[str, str]] = {}
    if not issues:
        for preflight in preflights:
            target = str(preflight["target"])
            environment = str(preflight["environment"])
            envelope = preflight.get("appUatEnvelope")
            if not isinstance(envelope, dict):
                issues.append(f"{target}: canonical App UAT envelope is missing")
                break
            app_uat_plan = preflight.get("appUatPlan")
            if not isinstance(app_uat_plan, dict):
                issues.append(f"{target}: canonical App UAT plan is missing")
                break
            release_video_work_id = str(envelope.get("videoWorkId") or "").strip()
            if not release_video_work_id:
                issues.append(f"{target}: canonical App UAT video workId is missing")
                break
            video_pagination = app_uat_plan.get("videoPagination")
            expected_video_work_ids = (
                video_pagination.get("expectedWorkIds")
                if isinstance(video_pagination, Mapping)
                else None
            )
            if (
                not isinstance(expected_video_work_ids, list)
                or not expected_video_work_ids
                or any(not str(item).strip() for item in expected_video_work_ids)
            ):
                issues.append(f"{target}: canonical App UAT video page is empty")
                break
            release_video_page_count = len(expected_video_work_ids)
            try:
                readiness_path = _app_content_readiness_path(preflight)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                issues.append(f"{target}: {exc}")
                break
            runtime_binding = next(
                item for item in runtime_bindings if item.get("target") == target
            )
            if bool(getattr(args, "dry_run", False)):
                runs.append(
                    {
                        "target": target,
                        "suite": "release-bound-search-and-video-page",
                        "exitCode": 0,
                        "reportRef": "",
                        "status": "planned",
                        "searchCanaries": list(
                            app_uat_plan.get("searchCanaries") or []
                        ),
                        "videoPagination": dict(
                            app_uat_plan.get("videoPagination") or {}
                        ),
                        "mediaChecks": dict(app_uat_plan.get("mediaChecks") or {}),
                    }
                )
            else:
                try:
                    runs.append(
                        _stackctl._run_app_content_release_probe(
                            target=target,
                            readiness_path=readiness_path,
                            app_uat_plan=app_uat_plan,
                            report_dir=(report_dir / target / "release-bound-readback"),
                        )
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
            launch_attempt_path = (
                report_dir / target / "canonical-launch" / "attempt-1" / "attempt.json"
            )
            launch_report_path = launch_attempt_path.with_name("report.json")
            launch_terminal_path = launch_attempt_path.with_name(
                "startup-terminal.json"
            )
            launch_projection: dict[str, Any] = {}
            launch_control: dict[str, Any] = {}
            build_projection_policy_id = (
                FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID
                if args.platform == "android"
                else FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
            )
            if not bool(getattr(args, "dry_run", False)):
                try:
                    launch_projection = materialize_app_content_launch_projection(
                        runtime_binding=runtime_binding,
                        output_root=canonical_output_root,
                        projection_root=(
                            report_dir
                            / target
                            / "canonical-launch"
                            / "source-projection"
                        ),
                        evidence_path=(
                            report_dir
                            / target
                            / "canonical-launch"
                            / "source-projection.json"
                        ),
                    )
                    launch_control = write_app_content_launch_control(
                        runtime_binding=runtime_binding,
                        projection=launch_projection,
                        output_root=canonical_output_root,
                        control_path=launch_attempt_path.with_name("control.json"),
                        attempt_path=launch_attempt_path,
                        report_path=launch_report_path,
                        terminal_receipt_path=launch_terminal_path,
                        platform=str(args.platform),
                        device_id=device_id,
                        build_projection_policy_id=build_projection_policy_id,
                        build_projection_seal_path=launch_attempt_path.with_name(
                            "build-projection-seal.json"
                        ),
                        expected_build_projection_digest=None,
                    )
                    launch_projections[target] = launch_projection
                except (OSError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
            launch_app_root = (
                Path(launch_projection["sourceProjectionRoot"]) / "quwoquan_app"
                if launch_projection
                else _stackctl.ROOT / "quwoquan_app"
            )
            if launch_projection:
                try:
                    verify_app_content_launch_projection(
                        projection_root=Path(launch_projection["sourceProjectionRoot"]),
                        evidence_path=Path(
                            launch_projection["sourceProjectionEvidenceRef"]
                        ),
                        reject_unmanifested=True,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
            if not execute_canonical_platform_launch(
                args=args,
                stackctl=_stackctl,
                environment=environment,
                target=target,
                device_id=device_id,
                launch_attempt_path=launch_attempt_path,
                launch_report_path=launch_report_path,
                launch_control=launch_control,
                canonical_output_root=canonical_output_root,
                launch_app_root=launch_app_root,
                runtime_binding=runtime_binding,
                launch_projection=launch_projection,
                build_projection_policy_id=build_projection_policy_id,
                report_dir=report_dir,
                issues=issues,
                runs=runs,
                launch_bindings=launch_bindings,
                android_launch_command=_app_content_android_launch_command,
                launch_binding_reader=_app_content_launch_binding,
                write_launch_control=write_app_content_launch_control,
            ):
                break
            suite_plan: list[tuple[str, str, bool, str]] = [
                ("homepage-feed", _stackctl.DISCOVERY_FEED_UAT_TEST_TARGET, False, ""),
                # 作者主页旅程：他人主页「记录」列表必须真实解码渲染（回归
                # ListUserPosts 契约漂移导致的「共有 0 条记录」+错误态事故）。
                (
                    "profile-journey",
                    PROFILE_JOURNEY_UAT_TEST_TARGET,
                    False,
                    "",
                ),
                (
                    "message-home",
                    MESSAGE_HOME_UAT_TEST_TARGET,
                    False,
                    "",
                ),
                # 先固定首帧与真实进度证据；视频书若缺第二个 release-bound
                # 页面仍由后续 app-core fail-closed，但不能短路独立视频验收。
                (
                    "home-video-playback",
                    _stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
                    True,
                    release_video_work_id,
                ),
                (
                    "app-core-readback",
                    _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
                    True,
                    release_video_work_id,
                ),
            ]
            # Every target owns its own controlled-fault evidence after the
            # positive homepage readback. The Patrol host resolves only the
            # current receipt-bound Compose project and exact API Edge
            # containers, restores them in its existing finally path, regains
            # health, then retries in the same installation.
            suite_plan.insert(
                1,
                (
                    "controlled-edge-recovery",
                    _stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
                    False,
                    "",
                ),
            )
            typed_actor_context: TestDataContext | None = None
            if not bool(getattr(args, "dry_run", False)) and any(
                _stackctl._app_content_uat_requires_typed_actor(
                    environment, patrol_target
                )
                for _suite_name, patrol_target, _bind_release, _work_id in suite_plan
            ):
                try:
                    typed_actor_context = (
                        _stackctl._app_content_test_live_actor_context(
                            preflight=preflight,
                            runtime_binding=runtime_binding,
                            readiness_path=readiness_path,
                            report_dir=report_dir,
                        )
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
            for suite_name, patrol_target, bind_release, canary_work_id in suite_plan:
                command = _stackctl._environment_page_smoke_profile_command(
                    environment,
                    target,
                    report_dir / target,
                    suite_name=f"app-content-{suite_name}",
                    patrol_target=patrol_target,
                    data_readiness_path=(readiness_path if bind_release else None),
                    release_video_work_id=(canary_work_id if bind_release else None),
                )
                if command is None:
                    issues.append(f"{target}: {suite_name} topology is incomplete")
                    break
                argv = list(command["argv"])
                if patrol_target == _stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET:
                    argv.extend(
                        (
                            "--data-release-id",
                            str(envelope.get("releaseId") or ""),
                        )
                    )
                if patrol_target == _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET:
                    for field, flag in _stackctl.APP_CONTENT_UAT_ENVELOPE_ARGUMENTS:
                        argv.extend((flag, str(envelope.get(field) or "")))
                if patrol_target == _stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET:
                    argv.append("--stackctl-controlled-edge-fault")
                argv.extend(
                    [
                        "--platform",
                        "ios" if args.platform == "ios-simulator" else "android",
                        "--device-id",
                        device_id,
                    ]
                )
                if bool(getattr(args, "dry_run", False)):
                    argv.append("--dry-run")
                typed_actor_required = _stackctl._app_content_uat_requires_typed_actor(
                    environment,
                    patrol_target,
                )
                execution_command = {**command, "argv": argv}
                if suite_name == "homepage-feed" and not bool(
                    getattr(args, "dry_run", False)
                ):
                    recorded_launch = launch_bindings.get(target)
                    if not isinstance(recorded_launch, Mapping):
                        issues.append(
                            f"{target}: external production AUT launch binding is missing"
                        )
                        break
                    execution_command["env"] = {
                        **dict(command.get("env") or {}),
                        EXTERNAL_AUT_CANONICAL_BINDING_ENV: (
                            encode_external_aut_canonical_binding(recorded_launch)
                        ),
                    }
                if patrol_target == _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET:
                    execution_command["env"] = {
                        **dict(command.get("env") or {}),
                        APP_CONTENT_VIDEO_PAGE_COUNT_ENV: str(release_video_page_count),
                    }
                if patrol_target == _stackctl.PROFILE_JOURNEY_UAT_TEST_TARGET:
                    execution_command["env"] = {
                        **dict(command.get("env") or {}),
                        "QWQ_APP_CONTENT_PROFILE_P0_ONLY": "true",
                    }
                if typed_actor_required:
                    execution_command.update(
                        {
                            "testDataActorCase": _stackctl.ProfileActorCaseId.APP_CONTENT_UAT,
                            "testDataActorRoles": (ActorRole.PRIMARY,),
                            "linkTestDataPreparationToPageReport": True,
                        }
                    )
                test_data_scope: dict[str, Any] | None = None
                patrol_dependency_readback: dict[str, Any] = {}
                if bool(getattr(args, "dry_run", False)):
                    result = _stackctl.run(
                        argv,
                        cwd=command["cwd"],
                        env=execution_command.get("env"),
                    )
                    if patrol_target == _stackctl.MESSAGE_HOME_UAT_TEST_TARGET:
                        test_data_scope = {
                            "status": "planned",
                            "baselineEligible": False,
                        }
                else:
                    recorded_launch = launch_bindings.get(target)
                    if not isinstance(recorded_launch, Mapping):
                        issues.append(
                            f"{target}: Patrol launch dependency binding is missing"
                        )
                        break
                    try:
                        result, test_data_scope, patrol_dependency_readback = (
                            execute_patrol_with_dependency_cas(
                                stackctl=_stackctl,
                                profile_command=execution_command,
                                target_name=target,
                                actor_context=typed_actor_context,
                                message_home=(
                                    patrol_target
                                    == _stackctl.MESSAGE_HOME_UAT_TEST_TARGET
                                ),
                                launch_projection=launch_projections[target],
                                launch_binding=recorded_launch,
                                platform=str(args.platform),
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - safe typed projection
                        failure = (
                            exc
                            if isinstance(exc, PatrolDependencyFailure)
                            else patrol_dependency_failure(exc, stage="command")
                        )
                        error_code = failure.error_code
                        safe_failure = failure.as_dict()
                        safe_detail = str(failure)
                        runs.append(
                            {
                                "target": target,
                                "suite": suite_name,
                                "exitCode": 2,
                                "errorCode": error_code,
                                "typedBlocker": {
                                    **safe_failure,
                                    "sourceOperationId": "app_content_uat.patrol_dependency_projection",
                                    "httpStatus": None,
                                },
                            }
                        )
                        issues.append(
                            f"{target}: {suite_name} dependency projection failed: "
                            f"{safe_detail}"
                        )
                        break
                    if (
                        typed_actor_required
                        and patrol_target != _stackctl.MESSAGE_HOME_UAT_TEST_TARGET
                    ):
                        page_report = _stackctl._read_json_object(
                            str(command["reportPath"])
                        )
                        preparation = page_report.get("testDataPreparation")
                        if isinstance(preparation, Mapping):
                            test_data_scope = {
                                **preparation,
                                "pageCaseResult": {
                                    "reportRef": str(command["reportPath"]),
                                    "status": str(page_report.get("status") or ""),
                                },
                            }
                patrol_evidence = _stackctl._app_content_patrol_evidence(
                    str(command["reportPath"])
                )
                controlled_edge_evidence_issue = ""
                if (
                    patrol_target == _stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET
                    and result.returncode == 0
                    and not bool(getattr(args, "dry_run", False))
                ):
                    try:
                        gateway_option = argv.index("--gateway-base-url")
                        expected_health_url = (
                            str(argv[gateway_option + 1]).rstrip("/") + "/healthz"
                        )
                    except (IndexError, ValueError):
                        controlled_edge_evidence_issue = (
                            "controlled edge recovery command lacks canonical API Edge"
                        )
                    else:
                        controlled_edge_evidence_issue = (
                            _controlled_edge_recovery_evidence_issue(
                                patrol_evidence,
                                target=target,
                                environment=environment,
                                runtime_binding=runtime_binding,
                                expected_health_url=expected_health_url,
                            )
                        )
                page_artifact_binding: dict[str, Any] = {}
                page_artifact_binding_issue = ""
                reported_page_binding = patrol_evidence.get("testedAppArtifactBinding")
                patrol_typed_blocker = patrol_evidence.get("typedBlocker")
                artifact_binding_blocker = patrol_evidence.get("artifactBindingBlocker")
                first_child_blocker = (
                    patrol_typed_blocker
                    if isinstance(patrol_typed_blocker, Mapping)
                    and str(patrol_typed_blocker.get("errorCode") or "")
                    else artifact_binding_blocker
                    if isinstance(artifact_binding_blocker, Mapping)
                    and str(artifact_binding_blocker.get("errorCode") or "")
                    else {}
                )
                first_child_error_code = str(first_child_blocker.get("errorCode") or "")
                if (
                    result.returncode == 0
                    or (
                        isinstance(reported_page_binding, Mapping)
                        and bool(reported_page_binding)
                    )
                ) and not bool(getattr(args, "dry_run", False)):
                    recorded_launch = launch_bindings.get(target)
                    if not isinstance(recorded_launch, Mapping):
                        page_artifact_binding_issue = (
                            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
                            "canonical launch binding is missing"
                        )
                    else:
                        try:
                            page_artifact_binding = _app_content_page_artifact_binding(
                                page_evidence=patrol_evidence,
                                launch_binding=recorded_launch,
                                expected_patrol_target=patrol_target,
                                expected_environment_alias=(
                                    "local-gamma" if target == "gamma-local" else target
                                ),
                                expected_platform=str(
                                    recorded_launch.get("platform") or ""
                                ),
                                expected_device_id=str(
                                    recorded_launch.get("deviceId") or ""
                                ),
                            )
                        except (TypeError, ValueError) as exc:
                            page_artifact_binding_issue = str(exc)
                run_payload = {
                    "target": target,
                    "suite": suite_name,
                    "exitCode": (
                        result.returncode
                        if result.returncode != 0
                        else 2
                        if first_child_error_code or page_artifact_binding_issue
                        else 1
                        if controlled_edge_evidence_issue
                        else result.returncode
                    ),
                    "reportRef": str(command["reportPath"]),
                    "typedTestDataActor": typed_actor_required,
                    "typedTestDataConversation": (
                        patrol_target == _stackctl.MESSAGE_HOME_UAT_TEST_TARGET
                    ),
                    "evidence": patrol_evidence,
                }
                if page_artifact_binding:
                    run_payload["pageArtifactBinding"] = page_artifact_binding
                if page_artifact_binding_issue:
                    run_payload["pageArtifactBinding"] = {
                        "status": "gate_block",
                        "errorCode": APP_PAGE_ARTIFACT_BINDING_BLOCKER,
                        "detail": page_artifact_binding_issue,
                    }
                if patrol_dependency_readback:
                    run_payload["dependencyProjectionReadback"] = (
                        patrol_dependency_readback
                    )
                if first_child_error_code:
                    run_payload["errorCode"] = first_child_error_code
                    run_payload["typedBlocker"] = dict(first_child_blocker)
                elif page_artifact_binding_issue and result.returncode == 0:
                    run_payload["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
                # 聚合回执的 consumerLeaseIds 从 run 顶层同一个键收集。Patrol 分支
                # 原先只把 lease 留在 evidence 里，于是该数组恒为空，device_bound
                # 层的 lease 子集判定永远不成立——不是 lease 没拿到，是没被读到。
                patrol_lease = patrol_evidence.get("consumerLease")
                patrol_lease_id = (
                    str(patrol_lease.get("leaseId") or "").strip()
                    if isinstance(patrol_lease, Mapping)
                    else ""
                )
                if patrol_lease_id:
                    run_payload["consumerLeaseId"] = patrol_lease_id
                if test_data_scope is not None:
                    run_payload["testDataScope"] = test_data_scope
                runs.append(run_payload)
                if result.returncode != 0:
                    detail = (
                        page_artifact_binding_issue
                        if first_child_error_code == APP_PAGE_ARTIFACT_BINDING_BLOCKER
                        else (result.stderr or result.stdout).strip()
                        or first_child_error_code
                    )
                    issues.append(
                        f"{target}: {suite_name} failed: "
                        + (detail[:800] if detail else f"exit={result.returncode}")
                    )
                    break
                if first_child_error_code:
                    issues.append(
                        f"{target}: {suite_name} failed: {first_child_error_code}"
                    )
                    break
                if controlled_edge_evidence_issue:
                    issues.append(
                        f"{target}: {suite_name} failed: "
                        + controlled_edge_evidence_issue
                    )
                    break
                if page_artifact_binding_issue:
                    issues.append(
                        f"{target}: {suite_name} failed: " + page_artifact_binding_issue
                    )
                    break
            if not issues and not bool(getattr(args, "dry_run", False)):
                try:
                    experience_screenshot_digests[target] = (
                        _stackctl._app_content_experience_screenshot_digests(
                            runs,
                            target=target,
                        )
                    )
                except (StopIteration, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
            if not issues and not bool(getattr(args, "dry_run", False)):
                recorded_launch = launch_bindings.get(target)
                if not isinstance(recorded_launch, Mapping):
                    issues.append(f"{target}: canonical launch binding is missing")
                else:
                    try:
                        current_runtime_binding = (
                            _stackctl._app_content_test_live_runtime_binding(preflight)
                        )
                        if current_runtime_binding != runtime_binding:
                            raise ValueError(
                                "active candidate/package binding changed during UAT"
                            )
                        current_launch = _app_content_launch_binding(
                            runtime_binding=current_runtime_binding,
                            report_ref=str(recorded_launch["launchReportRef"]),
                            attempt_ref=str(recorded_launch["launchAttemptRef"]),
                            platform=str(args.platform),
                            device_id=device_id,
                            launch_provenance=(
                                "workspace_flutter_run"
                                if args.platform == "ios-simulator"
                                else "canonical_launcher"
                            ),
                            launch_projection=launch_projections[target],
                        )
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        issues.append(f"{target}: {exc}")
                    else:
                        if current_launch != recorded_launch:
                            issues.append(
                                f"{target}: canonical launch binding changed during UAT"
                            )
            if issues:
                break

    dry_run = bool(getattr(args, "dry_run", False))
    if not issues and not dry_run and set(launch_bindings) != set(targets):
        issues.append("canonical launch bindings are incomplete for requested targets")
    status = "gate_block" if issues else ("planned" if dry_run else "passed")
    payload = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": status,
        "targets": targets,
        "platform": str(args.platform),
        "deviceId": device_id,
        "launchPolicy": "immutable_candidate",
        "nonPromotable": True,
        "packageBaselines": {
            str(item.get("target") or ""): str(item.get("candidateDigest") or "")
            for item in runtime_bindings
            if str(item.get("target") or "")
        },
        "releaseTrainId": (
            str(runtime_bindings[0].get("releaseTrainId") or "")
            if runtime_bindings
            and len(
                {str(item.get("releaseTrainId") or "") for item in runtime_bindings}
            )
            == 1
            else ""
        ),
        "runtimeBindings": {str(item["target"]): item for item in runtime_bindings},
        "runtimeBindingDigests": {
            str(item["target"]): "sha256:"
            + hashlib.sha256(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for item in runtime_bindings
        },
        "launchBindings": launch_bindings,
        "firstBlocker": (
            next(
                (
                    str(item.get("errorCode") or "")
                    for item in runs
                    if str(item.get("errorCode") or "")
                ),
                "",
            )
        ),
        "launchBindingDigests": {
            target: _stackctl._canonical_document_checksum(binding)
            for target, binding in launch_bindings.items()
        },
        "releaseId": (str(preflights[0].get("releaseId") or "") if preflights else ""),
        "manifestDigest": (
            str(preflights[0].get("manifestDigest") or "") if preflights else ""
        ),
        "appUatEnvelope": (
            preflights[0].get("appUatEnvelope", {}) if preflights else {}
        ),
        "appUatEnvelopeDigest": (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    preflights[0].get("appUatEnvelope") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if preflights and preflights[0].get("appUatEnvelope")
            else ""
        ),
        "appUatPlan": (preflights[0].get("appUatPlan", {}) if preflights else {}),
        "appUatPlanDigest": (
            _stackctl._canonical_document_checksum(
                dict(preflights[0].get("appUatPlan") or {})
            )
            if preflights and preflights[0].get("appUatPlan")
            else ""
        ),
        "configurationDigests": sorted(
            {
                str(item.get("configurationDigest") or "")
                for item in preflights
                if str(item.get("configurationDigest") or "")
            }
        ),
        "readinessReceiptDigests": sorted(
            {
                str(item.get("readinessReceiptDigest") or "")
                for item in preflights
                if str(item.get("readinessReceiptDigest") or "")
            }
        ),
        "consumerLeaseIds": sorted(
            {
                str(item.get("consumerLeaseId") or "")
                for item in runs
                if str(item.get("consumerLeaseId") or "")
            }
        ),
        "screenshotDigests": sorted(
            {
                str((item.get("evidence") or {}).get("screenshotDigest") or "")
                for item in runs
                if isinstance(item.get("evidence"), dict)
                and str((item.get("evidence") or {}).get("screenshotDigest") or "")
            }
        ),
        "experienceScreenshotDigests": experience_screenshot_digests,
        "visibleCardCounts": {
            str(item.get("target") or ""): int(
                ((item.get("evidence") or {}).get("feedContent") or {}).get(
                    "visibleCardCount", 0
                )
            )
            for item in runs
            if item.get("suite") == "homepage-feed"
            and isinstance(item.get("evidence"), dict)
        },
        "controlledEdgeRecoveries": {
            str(item.get("target") or ""): {
                "evidence": (
                    (item.get("evidence") or {}).get("controlledEdgeFault") or {}
                ),
                "receipt": (
                    (item.get("evidence") or {}).get("controlledEdgeFaultReceipt") or {}
                ),
            }
            for item in runs
            if item.get("suite") == "controlled-edge-recovery"
            and isinstance(item.get("evidence"), dict)
        },
        "preflights": preflights,
        "runs": runs,
        "executed": 0 if dry_run else len(runs),
        "executedSamples": (
            0
            if dry_run
            else sum(int(item.get("executedSampleCount") or 0) for item in runs)
        ),
        "sampleExecutionDigests": sorted(
            {
                str(item.get("sampleExecutionDigest") or "")
                for item in runs
                if str(item.get("sampleExecutionDigest") or "")
            }
        ),
        "skipped": 0,
        "details": issues
        or [
            (
                "dry-run planned all App content UAT suites; no runtime evidence was claimed"
                if dry_run
                else "all requested App content UAT suites passed"
            )
        ],
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    return {
        **payload,
        "exitCode": 0 if not issues else 2,
        "summary": (
            "App content UAT dry-run planned"
            if not issues and dry_run
            else "App content UAT passed"
            if not issues
            else "App content UAT is GATE_BLOCK"
        ),
        "reportDir": _stackctl.relpath(report_dir),
    }


def command_app_content_uat(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    device_id = str(getattr(args, "device_id", "") or "").strip()
    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run or not targets or not device_id:
        return _stackctl._command_app_content_uat(args)
    try:
        runtime_use_lock = _stackctl.acquire_local_runtime_use_lock(
            target=",".join(targets),
            purpose=f"app-content-uat:{args.platform}:{device_id}",
        )
    except RuntimeError as error:
        return _stackctl._command_app_content_uat(args, initial_issues=(str(error),))
    try:
        return _stackctl._command_app_content_uat(args)
    finally:
        runtime_use_lock.close()
