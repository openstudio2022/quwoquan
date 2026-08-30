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


def _target_uat_binding_for_execution(
    *,
    stackctl: Any,
    evidence_root: Path,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    uat_profile: Mapping[str, Any],
    device_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    from quwoquan_ops.cli.lib.target_uat_binding import (
        build_target_uat_binding,
        canonical_target_uat_binding_bytes,
        target_uat_binding_digest,
        write_create_once_target_uat_binding,
    )

    target = str(runtime_binding["target"])
    release_id = str(runtime_binding["releaseId"])
    activation = preflight.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise ValueError("canonical Data activation envelope is missing")
    def evidence_ref(value: object, *, label: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError(f"{label} exact-byte reference is missing")
        candidate = Path(raw).expanduser()
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (evidence_root / candidate).resolve()
        )
        try:
            relative = resolved.relative_to(evidence_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
        if resolved.is_symlink() or not resolved.is_file():
            raise ValueError(f"{label} exact bytes are missing or unsafe")
        return relative

    def verify_file_digest(ref: str, digest: str, *, label: str) -> None:
        if not digest:
            raise ValueError(f"{label} exact-byte digest is missing")
        observed = "sha256:" + hashlib.sha256((evidence_root / ref).read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"{label} exact-byte digest drifted")

    activation_ref = evidence_ref(
        activation.get("importReportRef"), label="active CAS"
    )
    activation_digest = str(activation.get("importReportDigest") or "")
    readback_ref = evidence_ref(
        preflight.get("readinessReceiptRef"), label="readback"
    )
    readback_digest = str(preflight.get("readinessReceiptDigest") or "")
    provider_ref = evidence_ref(
        launch_binding.get("contractGraphRef"), label="Provider ContractGraph"
    )
    provider_digest = str(launch_binding.get("contractGraphDigest") or "")
    for ref, digest, label in (
        (activation_ref, activation_digest, "active CAS"),
        (provider_ref, provider_digest, "Provider ContractGraph"),
    ):
        verify_file_digest(ref, digest, label=label)
    if not readback_digest:
        raise ValueError("readback exact-byte digest is missing")
    readback_payload = stackctl._read_json_object(str(evidence_root / readback_ref))
    if stackctl._canonical_document_checksum(readback_payload) != readback_digest:
        raise ValueError("readback canonical digest drifted")
    runner_source_paths = (
        "quwoquan_ops/cli/commands/app_preflight_uat.py",
        "quwoquan_ops/cli/smoke/environment_patrol_smoke/app_uat_case_execution.py",
        "quwoquan_ops/cli/smoke/environment_patrol_smoke/evidence.py",
        "quwoquan_app/test/user_acceptance/journeys/release_bound_sample_matrix/"
        "release_bound_sample_matrix__user_acceptance_test.dart",
        "quwoquan_app/test/support/runtime/patrol/release_uat_sample_plan.dart",
        "quwoquan_app/test/support/runtime/patrol/patrol_app_uat_case_evidence.dart",
    )
    runner_source_path = runner_source_paths[3]
    runner_hasher = hashlib.sha256()
    for source_path in runner_source_paths:
        encoded_path = source_path.encode("utf-8")
        encoded_source = (stackctl.ROOT / source_path).read_bytes()
        runner_hasher.update(len(encoded_path).to_bytes(4, "big"))
        runner_hasher.update(encoded_path)
        runner_hasher.update(len(encoded_source).to_bytes(8, "big"))
        runner_hasher.update(encoded_source)
    runner_digest = "sha256:" + runner_hasher.hexdigest()
    profile = str(uat_profile.get("profile") or "")
    registered = profile in {"promotable", "production"}
    binding = build_target_uat_binding(
        runtime_binding,
        launch_binding,
        {
            "releaseId": release_id,
            "releaseUatSamplePlanRef": str(
                preflight.get("releaseUatSamplePlanRef") or ""
            ),
            "releaseUatSamplePlanDigest": str(
                preflight.get("releaseUatSamplePlanDigest") or ""
            ),
        },
        active_cas={"ref": activation_ref, "digest": activation_digest},
        readback={"ref": readback_ref, "digest": readback_digest},
        artifact_class="production_behavior",
        build_mode="debug",
        build_profile="nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": registered,
            "conformanceEvidence": {
                "ref": provider_ref,
                "digest": provider_digest,
            },
        },
        device={
            "identity": device_id,
            "class": str(uat_profile.get("deviceClass") or ""),
            "registered": bool(uat_profile.get("deviceRegistered")),
        },
        runner={
            "identity": "app-content-uat",
            "sourcePath": runner_source_path,
            "digest": runner_digest,
            "registered": registered,
        },
        profile=profile,
        non_promotable=bool(uat_profile.get("nonPromotable")),
        created_at=str(
            (
                stackctl._read_json_object(str(launch_binding["launchAttemptRef"]))
                .get("transitions", [{}])[0]
                .get("at")
            )
            or ""
        ),
    )
    written = write_create_once_target_uat_binding(
        output_root=evidence_root,
        binding=binding,
    )
    if (
        written.digest != target_uat_binding_digest(binding)
        or written.path.read_bytes() != canonical_target_uat_binding_bytes(binding)
    ):
        raise ValueError("TargetUatBinding exact bytes drifted after create-once write")
    return binding, {"ref": written.ref, "digest": written.digest}


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
    uat_profile: dict[str, Any] = {}
    if device_id:
        try:
            uat_profile = app_content_uat_cli_profile(
                platform=str(getattr(args, "platform", "") or ""),
                device_id=device_id,
                device_registration_ref=str(
                    getattr(args, "device_registration_ref", "") or ""
                ),
            )
        except ValueError as exc:
            issues.append(str(exc))

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
            suite_plan: list[tuple[str, str, bool, str]] = [
                (
                    "release-sample-matrix",
                    RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET,
                    False,
                    "",
                ),
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
                sample_plan_selection = sample_plan.get("selectionEvidence")
                recorded_launch = launch_bindings.get(target)
                binding_ref = target_uat_binding_refs.get(target)
                if (
                    not isinstance(sample_plan_selection, Mapping)
                    or not isinstance(recorded_launch, Mapping)
                    or not isinstance(binding_ref, Mapping)
                ):
                    issues.append(
                        f"{target}: App UAT Patrol authority inputs are incomplete"
                    )
                    break
                sample_plan_ref = str(preflight.get("releaseUatSamplePlanRef") or "")
                header_ref = Path(
                    str(preflight.get("releaseHeaderRef") or "")
                ).expanduser()
                sample_plan_path = (
                    Path(sample_plan_ref).expanduser()
                    if Path(sample_plan_ref).expanduser().is_absolute()
                    else header_ref.parent / sample_plan_ref
                )
                if not sample_plan_path.is_file():
                    sample_plan_path = header_ref.parent / "uat" / "sample_plan.json"
                try:
                    sample_plan_authority_ref = sample_plan_path.resolve().relative_to(
                        canonical_output_root
                    ).as_posix()
                    binding_authority_ref = str(binding_ref.get("ref") or "")
                    candidate_manifest_path = (
                        Path(str(runtime_binding["sourceCapsuleManifestRef"]))
                        .parent.parent
                        / "manifest.json"
                    )
                    candidate_manifest_sha256 = hashlib.sha256(
                        candidate_manifest_path.read_bytes()
                    ).hexdigest()
                    graph_path = Path(str(recorded_launch["contractGraphRef"]))
                    contract_graph_source_hash = hashlib.sha256(
                        graph_path.read_bytes()
                    ).hexdigest()
                    app_uat_authority = {
                        "releaseId": str(preflight.get("releaseId") or ""),
                        "samplePlanRef": sample_plan_authority_ref,
                        "samplePlanSha256": str(
                            preflight.get("releaseUatSamplePlanDigest") or ""
                        ),
                        "targetUatBindingRef": binding_authority_ref,
                        "targetUatBindingSha256": str(binding_ref.get("digest") or ""),
                        "targetUatBindingDigest": str(binding_ref.get("digest") or ""),
                        "releaseDigest": str(sample_plan.get("releaseDigest") or ""),
                        "sourceIdentitySetDigest": str(
                            sample_plan_selection.get("sourceIdentitySetDigest") or ""
                        ),
                        "commitSha": str(runtime_binding.get("sourceRevision") or ""),
                        "contractGraphSourceHash": contract_graph_source_hash,
                        "candidateManifestSha256": candidate_manifest_sha256,
                    }
                except (KeyError, OSError, ValueError) as exc:
                    issues.append(
                        f"{target}: App UAT Patrol authority binding failed: {exc}"
                    )
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
    if dry_run:
        for preflight in preflights:
            target = str(preflight.get("target") or "")
            sample_plan = preflight.get("releaseUatSamplePlan")
            if target and isinstance(sample_plan, Mapping):
                try:
                    expected_raw_coverage[target] = expected_app_uat_raw_coverage(
                        sample_plan
                    )
                except AppUatRawResultError as exc:
                    issues.append(f"{target}: {exc}")
    try:
        raw_authority_projection, raw_projection_issues = (
            project_app_content_uat_raw_authority(
                evidence_root=canonical_output_root,
                targets=targets,
                raw_results=raw_results,
                expected_raw_coverage=expected_raw_coverage,
                dry_run=dry_run,
            )
        )
    except (OSError, TypeError, ValueError) as exc:
        raw_authority_projection = {
            "rawResultRefs": {target: [] for target in targets},
            "rawResultDigests": {target: [] for target in targets},
            "rawCoverage": {
                target: {
                    "expected": int(expected_raw_coverage.get(target) or 0),
                    "present": 0,
                    "missing": int(expected_raw_coverage.get(target) or 0),
                }
                for target in targets
            },
            "rawGaps": {target: [str(exc)] for target in targets},
        }
        raw_projection_issues = [str(exc)]
    issues.extend(
        item for item in raw_projection_issues if item not in issues
    )
    status = "gate_block" if issues else ("planned" if dry_run else "complete")
    payload = build_app_content_uat_receipt(
        status=status,
        targets=targets,
        platform=str(args.platform),
        device_id=device_id,
        uat_profile=uat_profile,
        runtime_bindings=runtime_bindings,
        launch_bindings=launch_bindings,
        target_uat_binding_refs=target_uat_binding_refs,
        raw_authority_projection=raw_authority_projection,
        preflights=preflights,
        runs=runs,
        experience_screenshot_digests=experience_screenshot_digests,
        issues=issues,
        dry_run=dry_run,
        canonical_checksum=_stackctl._canonical_document_checksum,
    )
    first_blocker, first_blocker_audit = first_canonical_app_blocker(
        status=status,
        preflights=preflights,
        runs=runs,
    )
    payload["firstBlocker"] = first_blocker
    if first_blocker_audit.get("fallback") is True and not payload["details"]:
        payload["details"].append(
            "APP.LAUNCH.receipt_invalid: parent gate_block lacked a canonical "
            "child blocker; inspect retained preflights/runs evidence for the "
            "original cause"
        )
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    return {
        **payload,
        "exitCode": 0 if not issues else 2,
        "summary": (
            "App content UAT dry-run planned"
            if not issues and dry_run
            else "App content UAT raw authority projection complete"
            if not issues
            else "App content UAT is GATE_BLOCK"
        ),
        "reportDir": _stackctl.relpath(report_dir),
    }
