"""stackctl `app-content-uat` 子命令域与 UAT dart 目标常量。

从 stackctl.py 逐字迁出;本模块保留 argparse 表面、编排主干与常量家族:

- `register_parser`:`app-content-uat` 子命令的 argparse 表面(帮助文案与
  参数集合逐字节保持不变);
- `command_app_content_uat`:runtime use lock 编排的 UAT 入口;
- `_command_app_content_uat`:Alpha/Beta/Gamma release-bound App 内容
  自动验收的顺序执行体;
- `_app_content_uat_requires_typed_actor`:typed actor 需求判定;
- UAT dart 目标常量家族(`VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET` /
  `HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET` / `DISCOVERY_FEED_UAT_TEST_TARGET` /
  `CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET` /
  `APP_CORE_READBACK_UAT_TEST_TARGET` / `IOS_DIRECT_FLUTTER_RUN_UAT` /
  `STARTUP_FIRST_FRAME_UAT` / `APP_CONTENT_UAT_ENVELOPE_ARGUMENTS`)与
  typed actor target 集合:`_ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS` 等
  frozenset 在模块加载期引用同模块常量,因此常量家族随本模块物理聚合
  (verify_profiles / verify_domain / app_preflight 经 stackctl 命名空间
  运行期消费)。`RELEASE_HOMEPAGE_UAT_TEST_TARGET` /
  `RUNTIME_RECOVERY_UAT_TEST_TARGET` / `GAMMA_CONTENT_UAT_TARGET` 仍由
  stackctl 拥有(content-acceptance / verify 域消费)。

test-live 运行时绑定与证据家族(`_app_content_patrol_evidence` /
`_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS` /
`_app_content_test_live_runtime_binding` /
`_app_content_test_live_actor_context` /
`_ios_direct_flutter_log_reader_retryable`)在
`commands/app_preflight_uat_binding.py`;本模块以薄 re-export 保持对
stackctl 的符号面零漂移。

data readiness 真相源家族在 `commands/app_preflight_shared.py` 与
`commands/app_preflight_readiness.py`;preflight 三命令在
`commands/app_preflight.py`。测试经 ``mock.patch.object(stackctl,
...)`` patch 本模块符号与协作符号,因此函数体内一律经函数内延迟导入
`_stackctl` 属性访问(含本模块符号互调),保持 monkeypatch 语义并避免
顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.model import TestDataContext

from quwoquan_ops.cli.commands.app_preflight_uat_binding import (
    _APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS,
    _app_content_patrol_evidence,
    _app_content_test_live_actor_context,
    _app_content_test_live_runtime_binding,
    _ios_direct_flutter_log_reader_retryable,
)

# 与 stackctl.ROOT 同源同值(仓库根);仅用于模块加载期常量绑定,
# 函数体内仍统一经 `_stackctl.ROOT` 访问。
_REPO_ROOT = Path(__file__).resolve().parents[3]


VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET = "test/user_acceptance/journeys/home_video_playback/video_playback_canary__user_acceptance_test.dart"
HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET = "test/user_acceptance/journeys/home_video_playback/home_video_playback__user_acceptance_test.dart"
DISCOVERY_FEED_UAT_TEST_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_load__user_acceptance_test.dart"
)
CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)
APP_CORE_READBACK_UAT_TEST_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "app_core_readback__user_acceptance_test.dart"
)
PROFILE_JOURNEY_UAT_TEST_TARGET = (
    "test/user_acceptance/journeys/profile/"
    "profile_journey__user_acceptance_test.dart"
)
IOS_DIRECT_FLUTTER_RUN_UAT = (
    _REPO_ROOT / "quwoquan_app/scripts/device/verify_ios_hot_restart.py"
)
STARTUP_FIRST_FRAME_UAT = (
    _REPO_ROOT / "quwoquan_app/scripts/device/verify_startup_first_frame.py"
)
APP_CONTENT_UAT_ENVELOPE_ARGUMENTS = (
    ("releaseId", "--data-release-id"),
    ("releaseClass", "--data-release-class"),
    ("productLifecycleState", "--product-lifecycle-state"),
    ("homepageId", "--data-release-homepage-id"),
    ("homepageTitle", "--data-release-homepage-title"),
    ("articleWorkId", "--data-release-article-work-id"),
    ("articleTitle", "--data-release-article-title"),
    ("imageWorkId", "--data-release-image-work-id"),
    ("imageTitle", "--data-release-image-title"),
    ("creatorName", "--data-release-creator-name"),
    ("creatorUserHandle", "--data-release-creator-user-handle"),
    ("creatorPersonaId", "--data-release-creator-persona-id"),
    (
        "creatorAvatarAssetId",
        "--data-release-creator-avatar-asset-id",
    ),
    ("tagLabel", "--data-release-tag-label"),
    ("videoAttribution", "--data-release-video-attribution"),
)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    app_content_uat_parser = subparsers.add_parser(
        "app-content-uat",
        help="顺序执行 Alpha/Beta/Gamma release-bound App 内容自动验收",
    )
    app_content_uat_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_content_uat_parser.add_argument(
        "--targets",
        default="alpha-local,beta-local,gamma-local",
    )
    app_content_uat_parser.add_argument(
        "--platform",
        choices=("ios-simulator", "android"),
        default="ios-simulator",
    )
    app_content_uat_parser.add_argument("--device-id", required=True)
    app_content_uat_parser.add_argument("--dry-run", action="store_true")


_ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS = frozenset(
    {
        DISCOVERY_FEED_UAT_TEST_TARGET,
        # 作者主页旅程含关注/取关真实往返，需要真实非生产身份。
        PROFILE_JOURNEY_UAT_TEST_TARGET,
        APP_CORE_READBACK_UAT_TEST_TARGET,
        HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
        VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
        CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    }
)
_BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS = frozenset(
    {
        PROFILE_JOURNEY_UAT_TEST_TARGET,
        APP_CORE_READBACK_UAT_TEST_TARGET,
        HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
    }
)


def _app_content_uat_requires_typed_actor(
    environment: str,
    patrol_target: str,
) -> bool:
    import quwoquan_ops.cli.stackctl as _stackctl

    if environment == "alpha":
        return patrol_target in _stackctl._ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS
    if environment in {"beta", "gamma"}:
        return patrol_target in _stackctl._BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS
    return False


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
                    runtime_mode="test_live",
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
        elif len(app_uat_envelopes) != 1 or "{}" in app_uat_envelopes:
            issues.append("Alpha/Beta/Gamma appUatEnvelope is not identical")
        elif len(app_uat_plans) != 1 or "{}" in app_uat_plans:
            issues.append("Alpha/Beta/Gamma appUatPlan is not identical")

    runs: list[dict[str, Any]] = []
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
            readiness_path = (
                _stackctl.output_root().expanduser().resolve()
                / str(preflight["readinessReceiptRef"])
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
                        "mediaChecks": dict(
                            app_uat_plan.get("mediaChecks") or {}
                        ),
                    }
                )
            else:
                try:
                    runs.append(
                        _stackctl._run_app_content_release_probe(
                            target=target,
                            readiness_path=readiness_path,
                            app_uat_plan=app_uat_plan,
                            report_dir=(
                                report_dir / target / "release-bound-readback"
                            ),
                        )
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    issues.append(f"{target}: {exc}")
                    break
            if args.platform == "ios-simulator":
                direct_command = [
                    sys.executable,
                    str(_stackctl.IOS_DIRECT_FLUTTER_RUN_UAT),
                    "--env",
                    environment,
                    "--device-id",
                    device_id,
                    "--launch-surface",
                    "direct_flutter_run",
                    "--output-dir",
                    str(report_dir / target / "direct-flutter-run"),
                ]
                if bool(getattr(args, "dry_run", False)):
                    direct_command.append("--preflight-only")
                direct_execution_lock = None
                try:
                    if not bool(getattr(args, "dry_run", False)):
                        direct_execution_lock = _stackctl.acquire_patrol_execution_lock(
                            env_name=target,
                            target=f"direct-flutter-run:{device_id}",
                        )
                    direct_result = _stackctl.run(
                        direct_command,
                        cwd=_stackctl.ROOT / "quwoquan_app",
                    )
                    try:
                        direct_evidence = json.loads(direct_result.stdout)
                    except json.JSONDecodeError:
                        direct_evidence = {}
                    direct_retry_reports: list[str] = []
                    if (
                        direct_result.returncode != 0
                        and isinstance(direct_evidence, dict)
                        and _stackctl._ios_direct_flutter_log_reader_retryable(
                            direct_evidence
                        )
                    ):
                        direct_retry_reports.append(
                            str(direct_evidence.get("reportPath") or "")
                        )
                        direct_result = _stackctl.run(
                            direct_command,
                            cwd=_stackctl.ROOT / "quwoquan_app",
                        )
                        try:
                            direct_evidence = json.loads(direct_result.stdout)
                        except json.JSONDecodeError:
                            direct_evidence = {}
                except RuntimeError as exc:
                    issues.append(f"{target}: {exc}")
                    break
                finally:
                    if direct_execution_lock is not None:
                        direct_execution_lock.close()
                direct_passed = (
                    direct_result.returncode == 0
                    and isinstance(direct_evidence, dict)
                    and direct_evidence.get("status") == "passed"
                    and direct_evidence.get("launchMode") == "direct_flutter_run"
                    and _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
                        str(direct_evidence.get("consumerLeaseId") or "")
                    )
                    is not None
                )
                runs.append(
                    {
                        "target": target,
                        "suite": "direct-flutter-run",
                        "exitCode": direct_result.returncode,
                        "reportRef": str(direct_evidence.get("reportPath") or ""),
                        "launchMode": direct_evidence.get("launchMode"),
                        "consumerLeaseId": direct_evidence.get("consumerLeaseId"),
                        "attempts": direct_evidence.get("attempts", []),
                        "retryCount": len(direct_retry_reports),
                        "supersededFailedReportRefs": direct_retry_reports,
                    }
                )
                if not direct_passed:
                    detail = (direct_result.stderr or direct_result.stdout).strip()
                    issues.append(
                        f"{target}: literal flutter run failed: "
                        + (detail[:800] if detail else "typed report is incomplete")
                    )
                    break
            raw_video_canaries = app_uat_plan.get("videoPlaybackCanaries")
            if not isinstance(raw_video_canaries, list) or not raw_video_canaries:
                issues.append(f"{target}: video playback canaries are missing")
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
                    "app-core-readback",
                    _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
                    True,
                    release_video_work_id,
                ),
                (
                    "home-video-playback",
                    _stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
                    True,
                    release_video_work_id,
                ),
            ]
            for raw_canary in raw_video_canaries:
                if not isinstance(raw_canary, Mapping):
                    issues.append(f"{target}: video playback canary is invalid")
                    break
                position = str(raw_canary.get("position") or "").strip()
                work_id = str(raw_canary.get("workId") or "").strip()
                if not position or not work_id:
                    issues.append(f"{target}: video playback canary is incomplete")
                    break
                suite_plan.append(
                    (
                        f"video-playback-{position}",
                        _stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
                        True,
                        work_id,
                    )
                )
            suite_plan.append(
                (
                    "controlled-edge-recovery",
                    _stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
                    False,
                    "",
                )
            )
            if issues:
                break
            typed_actor_context: TestDataContext | None = None
            if not bool(getattr(args, "dry_run", False)) and any(
                _stackctl._app_content_uat_requires_typed_actor(environment, patrol_target)
                for _suite_name, patrol_target, _bind_release, _work_id in suite_plan
            ):
                try:
                    typed_actor_context = _stackctl._app_content_test_live_actor_context(
                        preflight=preflight,
                        runtime_binding=next(
                            item
                            for item in runtime_bindings
                            if item.get("target") == target
                        ),
                        readiness_path=readiness_path,
                        report_dir=report_dir,
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
                    release_video_work_id=(
                        canary_work_id if bind_release else None
                    ),
                )
                if command is None:
                    issues.append(f"{target}: {suite_name} topology is incomplete")
                    break
                argv = list(command["argv"])
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
                if typed_actor_required:
                    execution_command.update(
                        {
                            "testDataActorCase": _stackctl.ProfileActorCaseId.APP_CONTENT_UAT,
                            "testDataActorRoles": (ActorRole.PRIMARY,),
                        }
                    )
                result = (
                    _stackctl.run(argv, cwd=command["cwd"], env=command.get("env"))
                    if bool(getattr(args, "dry_run", False))
                    else _stackctl._run_profile_command(
                        execution_command,
                        target_name=target,
                        actor_context=typed_actor_context,
                    )
                )
                run_payload = {
                    "target": target,
                    "suite": suite_name,
                    "exitCode": result.returncode,
                    "reportRef": str(command["reportPath"]),
                    "typedTestDataActor": typed_actor_required,
                    "evidence": _stackctl._app_content_patrol_evidence(
                        str(command["reportPath"])
                    ),
                }
                runs.append(run_payload)
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout).strip()
                    issues.append(
                        f"{target}: {suite_name} failed: "
                        + (detail[:800] if detail else f"exit={result.returncode}")
                    )
                    break
            if not issues and args.platform == "android":
                startup_command = [
                    sys.executable,
                    str(_stackctl.STARTUP_FIRST_FRAME_UAT),
                    "--android-device",
                    device_id,
                    "--runtime-env",
                    environment,
                    "--runtime-target",
                    target,
                    "--matrix-evidence-root",
                    str(report_dir / target / "startup-runtime"),
                    "--output-dir",
                    str(report_dir / target / "startup-first-frame"),
                    "--require-startup-sequence-events",
                    "--require-branded-visible",
                    "--require-no-native-recovery",
                    "--require-telemetry-ack",
                ]
                if bool(getattr(args, "dry_run", False)):
                    issues.append(
                        f"{target}: Android startup evidence cannot be dry-run"
                    )
                    break
                startup_result = _stackctl.run(startup_command, cwd=_stackctl.ROOT)
                try:
                    startup_evidence = json.loads(startup_result.stdout)
                except json.JSONDecodeError:
                    startup_evidence = {}
                startup_passed = (
                    startup_result.returncode == 0
                    and isinstance(startup_evidence, dict)
                    and startup_evidence.get("passed") is True
                    and any(
                        isinstance(item, dict)
                        and str(item.get("attemptId") or "").strip()
                        not in {"", "unknown"}
                        and item.get("telemetryAcknowledged") is True
                        and str(
                            item.get("effectiveLaunchManifestDigest") or ""
                        ).startswith("sha256:")
                        for item in startup_evidence.get("results") or []
                    )
                )
                runs.append(
                    {
                        "target": target,
                        "suite": "startup-first-frame",
                        "exitCode": startup_result.returncode,
                        "reportRef": str(
                            startup_evidence.get("outputDir") or ""
                        ),
                        "evidence": startup_evidence,
                    }
                )
                if not startup_passed:
                    detail = (
                        startup_result.stderr or startup_result.stdout
                    ).strip()
                    issues.append(
                        f"{target}: Android startup evidence failed: "
                        + (detail[:800] if detail else "typed report is incomplete")
                    )
            if issues:
                break

    dry_run = bool(getattr(args, "dry_run", False))
    status = "gate_block" if issues else ("planned" if dry_run else "passed")
    payload = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": status,
        "targets": targets,
        "platform": str(args.platform),
        "deviceId": device_id,
        "launchPolicy": "test_live",
        "packageBaseline": "",
        "runtimeBindings": {
            str(item["target"]): item for item in runtime_bindings
        },
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
        "releaseId": (
            str(preflights[0].get("releaseId") or "") if preflights else ""
        ),
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
        "appUatPlan": (
            preflights[0].get("appUatPlan", {}) if preflights else {}
        ),
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
            str(item.get("target") or ""): (
                (item.get("evidence") or {}).get("controlledEdgeFault") or {}
            )
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

