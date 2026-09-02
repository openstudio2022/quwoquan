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
from quwoquan_ops.cli.commands.app_preflight_uat_blockers import (
    app_content_uat_cli_profile,
    first_canonical_app_blocker,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
    FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
    FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    materialize_app_content_launch_projection,
    verify_app_content_launch_projection,
    write_app_content_launch_control,
)
from quwoquan_ops.cli.commands.app_preflight_uat_lock import (
    command_app_content_uat,
)
from quwoquan_ops.cli.commands.app_preflight_uat_page_evidence import (
    collect_app_uat_case_execution_reports,
    emit_app_uat_raw_results,
)
from quwoquan_ops.cli.commands.app_preflight_uat_patrol_dependency import (
    PatrolDependencyFailure,
    execute_patrol_with_dependency_cas,
    patrol_dependency_failure,
)
from quwoquan_ops.cli.commands.app_preflight_uat_platform import (
    execute_canonical_platform_launch,
)
from quwoquan_ops.cli.commands.app_preflight_uat_receipt import (
    build_app_content_uat_receipt,
    project_app_content_uat_raw_authority,
)
from quwoquan_ops.cli.commands.app_preflight_uat_raw_results import (
    AppUatRawResultError,
    expected_app_uat_raw_coverage,
)
from quwoquan_ops.cli.commands.app_preflight_uat_orchestration import (
    app_content_uat_suite_plan,
    build_app_uat_patrol_authority,
    finalize_app_content_uat,
    prepare_app_content_uat_context,
)
from quwoquan_ops.cli.commands.app_preflight_uat_target_binding import (
    _target_uat_binding_for_execution,
)
from quwoquan_ops.cli.commands.app_preflight_uat_support import (
    _ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS,
    _BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS,
    APP_CORE_READBACK_UAT_TEST_TARGET,
    CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    DISCOVERY_FEED_UAT_TEST_TARGET,
    HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
    IOS_DIRECT_FLUTTER_RUN_UAT,
    MESSAGE_HOME_UAT_TEST_TARGET,
    PROFILE_JOURNEY_UAT_TEST_TARGET,
    RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET,
    STARTUP_FIRST_FRAME_UAT,
    VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
    _app_content_canonical_launch_command,
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
    "APP_CORE_READBACK_UAT_TEST_TARGET",
    "CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET",
    "DISCOVERY_FEED_UAT_TEST_TARGET",
    "HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET",
    "IOS_DIRECT_FLUTTER_RUN_UAT",
    "MESSAGE_HOME_UAT_TEST_TARGET",
    "PROFILE_JOURNEY_UAT_TEST_TARGET",
    "RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET",
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

    (
        targets,
        report_dir,
        canonical_output_root,
        issues,
        unsupported,
        device_id,
        uat_profile,
    ) = prepare_app_content_uat_context(
        args=args,
        stackctl=_stackctl,
        resolve_uat_profile=app_content_uat_cli_profile,
        initial_issues=initial_issues,
    )

    if unsupported:
        return {
            "schema": "quwoquan_ops.app_content_uat_receipt",
            "status": "gate_block",
            "targets": targets,
            "firstBlocker": "APP.LAUNCH.receipt_invalid",
            "details": list(issues),
            "exitCode": 2,
            "summary": "App content UAT is GATE_BLOCK",
            "reportDir": "",
        }

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
        release_identities = {
            json.dumps(
                (item.get("appUatPlan") or {}).get("releaseIdentity") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in preflights
        }
        sample_plan_digests = {
            str(item.get("releaseUatSamplePlanDigest") or "")
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
        elif len(release_identities) != 1 or "{}" in release_identities:
            issues.append("Alpha/Beta/Gamma release identity is not identical")
        elif len(sample_plan_digests) != 1 or "" in sample_plan_digests:
            issues.append(
                "Alpha/Beta/Gamma ReleaseUatSamplePlan exact digest is not identical"
            )
        elif len(app_uat_plans) != 1 or "{}" in app_uat_plans:
            issues.append("Alpha/Beta/Gamma appUatPlan is not identical")

    runs: list[dict[str, Any]] = []
    target_uat_bindings: dict[str, dict[str, Any]] = {}
    target_uat_binding_refs: dict[str, dict[str, str]] = {}
    raw_results: dict[str, list[dict[str, Any]]] = {}
    expected_raw_coverage: dict[str, int] = {}
    case_execution_reports: dict[str, dict[tuple[str, str, str], dict[str, str]]] = {}
    launch_bindings: dict[str, dict[str, str]] = {}
    launch_projections: dict[str, dict[str, str]] = {}
    experience_screenshot_digests: dict[str, dict[str, str]] = {}
    if not issues:
        for preflight in preflights:
            target = str(preflight["target"])
            environment = str(preflight["environment"])
            app_uat_plan = preflight.get("appUatPlan")
            if not isinstance(app_uat_plan, dict):
                issues.append(f"{target}: canonical App UAT plan is missing")
                break
            carrier_identities = app_uat_plan.get("carrierIdentities")
            release_video_work_id = (
                str(carrier_identities.get("video") or "").strip()
                if isinstance(carrier_identities, Mapping)
                else ""
            )
            sample_plan = preflight.get("releaseUatSamplePlan")
            if not isinstance(sample_plan, Mapping):
                issues.append(f"{target}: ReleaseUatSamplePlan is missing")
                break
            try:
                expected_raw_coverage[target] = expected_app_uat_raw_coverage(sample_plan)
            except AppUatRawResultError as exc:
                issues.append(f"{target}: {exc}")
                break
            case_execution_reports[target] = {}
            if not release_video_work_id:
                issues.append(f"{target}: ReleaseUatSamplePlan video identity is missing")
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
            release_probe_run: dict[str, Any] = {}
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
                    release_probe_run = _stackctl._run_app_content_release_probe(
                        target=target,
                        readiness_path=readiness_path,
                        app_uat_plan=app_uat_plan,
                        report_dir=(report_dir / target / "release-bound-readback"),
                    )
                    runs.append(release_probe_run)
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
                if str(args.platform).startswith("android")
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
                canonical_launch_command=_app_content_canonical_launch_command,
                launch_binding_reader=_app_content_launch_binding,
                write_launch_control=write_app_content_launch_control,
            ):
                break
            suite_plan = app_content_uat_suite_plan(
                stackctl=_stackctl,
                release_video_work_id=release_video_work_id,
            )
            if not bool(getattr(args, "dry_run", False)):
                recorded_launch = launch_bindings.get(target)
                if not isinstance(recorded_launch, Mapping):
                    issues.append(f"{target}: canonical launch binding is missing")
                    break
                try:
                    binding, binding_ref = _target_uat_binding_for_execution(
                        stackctl=_stackctl,
                        evidence_root=canonical_output_root,
                        preflight=preflight,
                        runtime_binding=runtime_binding,
                        launch_binding=recorded_launch,
                        uat_profile=uat_profile,
                        device_id=device_id,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
                target_uat_bindings[target] = binding
                target_uat_binding_refs[target] = binding_ref
            app_uat_authority: dict[str, str] | None = None
            if not bool(getattr(args, "dry_run", False)):
                try:
                    app_uat_authority, sample_plan_path = (
                        build_app_uat_patrol_authority(
                        preflight=preflight,
                        sample_plan=sample_plan,
                        launch_binding=launch_bindings.get(target),
                        target_uat_binding_ref=target_uat_binding_refs.get(target),
                        runtime_binding=runtime_binding,
                            output_root=canonical_output_root,
                        )
                    )
                except (OSError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
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
                    app_uat_authority=(
                        app_uat_authority
                        if patrol_target == RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET
                        else None
                    ),
                )
                if command is None:
                    issues.append(f"{target}: {suite_name} topology is incomplete")
                    break
                argv = list(command["argv"])
                if (
                    patrol_target == RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET
                    and not bool(getattr(args, "dry_run", False))
                ):
                    sample_execution = release_probe_run.get("sampleExecution")
                    if not isinstance(sample_execution, Mapping):
                        issues.append(f"{target}: release sample runtime binding is missing")
                        break
                    runtime_samples = sample_execution.get("samples")
                    if not isinstance(runtime_samples, list) or not runtime_samples:
                        issues.append(f"{target}: release sample runtime rows are missing")
                        break
                    runtime_binding_bytes = (
                        json.dumps(
                            {
                                "schema": "quwoquan_ops.app_uat_sample_runtime_binding.v1",
                                "releaseId": str(preflight.get("releaseId") or ""),
                                "samples": [
                                    {
                                        "sampleId": str(item.get("sampleId") or ""),
                                        "carrier": str(item.get("carrier") or ""),
                                        "sourceObjectId": str(item.get("sourceObjectId") or ""),
                                        "readObjectId": str(item.get("readObjectId") or ""),
                                    }
                                    for item in runtime_samples
                                    if isinstance(item, Mapping)
                                ],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    sample_plan_bytes = sample_plan_path.read_bytes()
                    if (
                        "sha256:" + hashlib.sha256(sample_plan_bytes).hexdigest()
                        != str(preflight.get("releaseUatSamplePlanDigest") or "")
                    ):
                        issues.append(f"{target}: ReleaseUatSamplePlan exact bytes drifted")
                        break
                    argv.extend(
                        (
                            "--app-uat-sample-plan-b64",
                            __import__("base64").b64encode(sample_plan_bytes).decode("ascii"),
                            "--app-uat-runtime-binding-b64",
                            __import__("base64").b64encode(runtime_binding_bytes).decode("ascii"),
                        )
                    )
                if patrol_target == _stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET:
                    argv.extend(
                        (
                            "--data-release-id",
                            str(preflight.get("releaseId") or ""),
                        )
                    )
                if patrol_target == _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET:
                    release_identity = app_uat_plan.get("releaseIdentity")
                    if not isinstance(release_identity, Mapping):
                        issues.append(f"{target}: release identity is missing")
                        break
                    argv.extend(
                        (
                            "--data-release-id",
                            str(release_identity.get("releaseId") or ""),
                        )
                    )
                if patrol_target == _stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET:
                    argv.append("--stackctl-controlled-edge-fault")
                argv.extend(
                    [
                        "--platform",
                        "ios" if str(args.platform).startswith("ios") else "android",
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
                recorded_launch = launch_bindings.get(target)
                if bool(getattr(args, "dry_run", False)):
                    patrol_evidence = {}
                elif not isinstance(recorded_launch, Mapping):
                    issues.append(f"{target}: canonical launch binding is missing")
                    break
                else:
                    patrol_evidence = _stackctl._app_content_patrol_evidence(
                        str(command["reportPath"]),
                        contract_graph_binding=recorded_launch,
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
                    and isinstance(patrol_typed_blocker.get("errorCode"), str)
                    and patrol_typed_blocker.get("errorCode")
                    else artifact_binding_blocker
                    if isinstance(artifact_binding_blocker, Mapping)
                    and isinstance(artifact_binding_blocker.get("errorCode"), str)
                    and artifact_binding_blocker.get("errorCode")
                    else {}
                )
                raw_child_error_code = first_child_blocker.get("errorCode")
                first_child_error_code = (
                    raw_child_error_code
                    if isinstance(raw_child_error_code, str)
                    and raw_child_error_code
                    and raw_child_error_code == raw_child_error_code.strip()
                    else ""
                )
                if (
                    result.returncode == 0
                    or (
                        isinstance(reported_page_binding, Mapping)
                        and bool(reported_page_binding)
                    )
                ) and not bool(getattr(args, "dry_run", False)):
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
                    "contractGraphDigest": patrol_evidence.get(
                        "contractGraphDigest", ""
                    ),
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
                if (
                    not bool(getattr(args, "dry_run", False))
                    and patrol_target == RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET
                ):
                    binding_ref = target_uat_binding_refs.get(target)
                    binding = target_uat_bindings.get(target)
                    if not isinstance(binding_ref, Mapping) or not isinstance(
                        binding, Mapping
                    ):
                        issues.append(f"{target}: TargetUatBinding is missing")
                        break
                    try:
                        reports = collect_app_uat_case_execution_reports(
                            evidence_root=canonical_output_root,
                            report_ref=str(command["reportPath"]),
                            expected_target_uat_binding_digest=str(
                                binding_ref.get("digest") or ""
                            ),
                        )
                    except (OSError, TypeError, ValueError) as exc:
                        if result.returncode == 0:
                            issues.append(f"{target}: {suite_name} {exc}")
                            break
                        reports = []
                    target_reports = case_execution_reports[target]
                    for source in reports:
                        receipt = _stackctl._read_json_object(
                            str(canonical_output_root / source["receiptRef"])
                        )
                        key = (
                            str(receipt.get("sampleId") or ""),
                            str(receipt.get("entrySurface") or ""),
                            str(receipt.get("carrier") or ""),
                        )
                        if key in target_reports:
                            issues.append(
                                f"{target}: duplicate App UAT case execution receipt {key}"
                            )
                            break
                        target_reports[key] = source
                    if issues:
                        break
                if result.returncode != 0:
                    detail = (
                        first_child_error_code
                        or page_artifact_binding_issue
                        or (result.stderr or result.stdout).strip()
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
                binding = target_uat_bindings.get(target)
                sample_plan = preflight.get("releaseUatSamplePlan")
                if not isinstance(binding, Mapping) or not isinstance(
                    sample_plan, Mapping
                ):
                    issues.append(f"{target}: raw authority inputs are incomplete")
                else:
                    try:
                        raw_results[target] = emit_app_uat_raw_results(
                            evidence_root=canonical_output_root,
                            target_binding=binding,
                            sample_plan=sample_plan,
                            case_execution_reports=list(
                                case_execution_reports[target].values()
                            ),
                        )
                    except (AppUatRawResultError, OSError, TypeError, ValueError) as exc:
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
                            launch_provenance="canonical_launcher",
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

    return finalize_app_content_uat(
        args=args,
        stackctl=_stackctl,
        report_dir=report_dir,
        output_root=canonical_output_root,
        targets=targets,
        uat_profile=uat_profile,
        runtime_bindings=runtime_bindings,
        launch_bindings=launch_bindings,
        target_uat_binding_refs=target_uat_binding_refs,
        raw_results=raw_results,
        expected_raw_coverage=expected_raw_coverage,
        preflights=preflights,
        runs=runs,
        experience_screenshot_digests=experience_screenshot_digests,
        issues=issues,
        expected_raw_coverage_for_plan=expected_app_uat_raw_coverage,
        project_raw_authority=project_app_content_uat_raw_authority,
        build_receipt=build_app_content_uat_receipt,
        select_first_blocker=first_canonical_app_blocker,
    )
