"""stackctl verify 域 profile 命令表（对象级环境验证命令工厂）。

从 stackctl.py 逐字迁出 12 个 profile 命令工厂：五域 generated typed
Remote、ReliableTask、onboarding/AuthorImpact、search、assistant learning、
ProfileUpdateProposal 的 Gamma API integration 绑定；举报回流、媒体发布、
群聊生命周期三条对象级旅程 probe；release 阶段的媒体预检
（`_target_media_preflight_profile_command`）、环境页面 smoke / Patrol
（`_environment_page_smoke_profile_command`）与 account-enforcement GWT-003
CaseResult 聚合（`_account_enforcement_gamma_uat_profile_command`）。

命令选择器（`_selected_verify_commands` / `_selected_profile_commands`）
在 `commands/verify_domain.py`；执行调度与 typed Actor 作用域在
`commands/verify_shared.py`。UAT dart 目标常量、`ProfileActorCaseId`、
`_resolve_test_auth_token` 等仍由 stackctl 命名空间拥有（app-content
留守域共用）。测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块
符号与上述协作符号，因此函数体内一律经函数内延迟导入 `_stackctl`
属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole

# 与 stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET 同源同值；仅用于函数
# 默认参数（commands 模块加载早于 stackctl 常量定义），函数体内仍统一经
# `_stackctl.` 访问 stackctl 拥有的 UAT 目标常量。
_VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET = "test/user_acceptance/journeys/home_video_playback/video_playback_canary__user_acceptance_test.dart"


def _app_domain_remote_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind five-domain generated typed Remote cases to Gamma verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile
        not in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
    ):
        return None
    evidence_root = (
        report_dir / "app-domain-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "app-domain-api-integration"
        / target_name
    )
    return {
        "name": "gamma-local-app-domain-api-integration",
        "argv": [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "--output-format",
            "json",
            "--report-dir",
            str(evidence_root),
            "app-domain-api-integration",
            "--target",
            target_name,
        ],
        "cwd": _stackctl.ROOT,
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(evidence_root / "report.json"),
    }


def _reliabletask_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind the real Gamma Mongo/Redis ReliableTask suite to release verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "reliabletask-gamma-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "reliabletask-gamma-api-integration"
        / target_name
    )
    report_path = evidence_root / "reliabletask_api_integration_report.json"
    return {
        "name": "gamma-local-reliabletask-api-integration",
        "argv": [
            "bash",
            "quwoquan_ops/cli/gamma/run_reliabletask_gamma_api_integration.sh",
            "--reuse-stack",
        ],
        "cwd": _stackctl.ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "GAMMA_RELIABLETASK_API_INTEGRATION_REPORT": str(report_path),
        },
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }


def _onboarding_author_impact_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind production Remote onboarding/AuthorImpact API UAT to Gamma release."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "onboarding-author-impact-gamma-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "onboarding-author-impact-gamma-api-integration"
        / target_name
    )
    report_path = evidence_root / "onboarding_author_impact_api_uat_report.json"
    return {
        "name": "gamma-local-onboarding-author-impact-api-integration",
        "testDataActorCase": _stackctl.ProfileActorCaseId.GAMMA_ONBOARDING_AUTHOR_IMPACT,
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_onboarding_author_impact_api_uat.sh",
        ],
        "cwd": _stackctl.ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_ONBOARDING_AUTHOR_IMPACT_API_UAT_REPORT": str(
                report_path
            ),
        },
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }


def _search_remote_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
    *,
    data_readiness_path: Path | None = None,
) -> dict[str, Any] | None:
    """Bind Gamma search/query feedback Remote evidence to release verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "search-remote-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "search-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "search_remote_api_uat_report.json"
    return {
        "name": "gamma-local-search-remote-api-integration",
        "testDataActorCase": _stackctl.ProfileActorCaseId.GAMMA_SEARCH_REMOTE,
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/run_local_gamma_search_api_uat.sh",
        ],
        "cwd": _stackctl.ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_SEARCH_API_UAT_REPORT": str(report_path),
            "DATA_RELEASE_READINESS_RECEIPT": (
                str(data_readiness_path) if data_readiness_path is not None else ""
            ),
        },
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }


def _assistant_learning_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind generated Assistant learning Remote evidence to Gamma verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile
        not in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
    ):
        return None

    evidence_root = (
        report_dir / "assistant-learning-remote-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "assistant-learning-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "assistant_learning_remote_api_uat_report.json"
    return {
        "name": "gamma-local-assistant-learning-remote-api-integration",
        "testDataActorCase": _stackctl.ProfileActorCaseId.GAMMA_ASSISTANT_LEARNING,
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_assistant_learning_api_uat.sh",
        ],
        "cwd": _stackctl.ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_ASSISTANT_LEARNING_API_UAT_REPORT": str(
                report_path,
            ),
        },
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }


def _profile_proposal_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind generated ProfileUpdateProposal Remote evidence to Gamma verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile
        not in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
    ):
        return None

    evidence_root = (
        report_dir / "profile-proposal-remote-api-integration"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "profile-proposal-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "profile_proposal_remote_api_uat_report.json"
    return {
        "name": "gamma-local-profile-proposal-remote-api-integration",
        "testDataActorCase": _stackctl.ProfileActorCaseId.GAMMA_PROFILE_PROPOSAL,
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_profile_proposal_api_uat.sh",
        ],
        "cwd": _stackctl.ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_PROFILE_PROPOSAL_API_UAT_REPORT": str(report_path),
        },
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }


def _report_feedback_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """为本地可变更环境和只读生产环境绑定同一对象级旅程证据。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    mode = ""
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mode = "lifecycle"
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mode = "lifecycle"
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # 生产证据只能验证举报人的私有可读状态；写入、运营裁决和
        # 负反馈补偿均不得在真实生产环境由自动化触发。
        mode = "read-only"
    if not mode:
        return None

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for report-feedback lifecycle probe"
        )
    probe_report = (
        report_dir / "report-feedback-lifecycle.json"
        if report_dir is not None
        else _stackctl.env_runs_root(env_name)
        / "report-feedback-lifecycle"
        / target_name
        / "report-feedback-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "content-service/smoke/run_report_feedback_lifecycle_probe.py",
        "--env",
        env_name,
        "--base-url",
        api_base_url,
        "--mode",
        mode,
        "--report",
        str(probe_report),
    ]
    command: dict[str, Any] = {
        "name": f"{target_name}-report-feedback-lifecycle",
        "argv": argv,
        "cwd": _stackctl.ROOT,
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(probe_report),
    }
    if target_name in {"beta-local", "gamma-local"}:
        command["testDataActorCase"] = (
            _stackctl.ProfileActorCaseId.BETA_REPORT_FEEDBACK
            if target_name == "beta-local"
            else _stackctl.ProfileActorCaseId.GAMMA_REPORT_FEEDBACK
        )
        command["testDataActorRoles"] = (
            ActorRole.PRIMARY,
            ActorRole.MEMBER,
        )
    return command


def _media_publication_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """将真实媒体上传、处理和发布闭环绑定到适用环境验证。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    mode = ""
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mode = "lifecycle"
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mode = "lifecycle"
    elif target_name == "prod-sim" and profile is VerificationProfile.INTEGRATION:
        # prod-sim 是唯一允许受控可变 canary 的生产镜像演练目标。
        mode = "lifecycle"
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # hosted production 不允许由默认验证链写入，只做显式凭据的只读探测。
        mode = "read-only"
    if not mode:
        return None

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for media publication lifecycle probe"
        )
    moderation_base_url = ""
    if mode == "lifecycle":
        origins = target.get("origins") or {}
        moderation_base_url = str(origins.get("contentService") or "").strip()
        if not moderation_base_url:
            raise ValueError(
                f"{target_name} lacks origins.contentService for media moderation lifecycle"
            )
    probe_report = (
        report_dir / "media-publication-lifecycle.json"
        if report_dir is not None
        else _stackctl.env_runs_root(env_name)
        / "media-publication-lifecycle"
        / target_name
        / "media-publication-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "content-service/smoke/run_media_publication_lifecycle_probe.py",
        "--env",
        env_name,
        "--target-name",
        target_name,
        "--base-url",
        api_base_url,
        "--mode",
        mode,
        "--report",
        str(probe_report),
    ]
    if moderation_base_url:
        argv.extend(["--moderation-base-url", moderation_base_url])
    command = {
        "name": f"{target_name}-media-publication-lifecycle",
        "argv": argv,
        "cwd": _stackctl.ROOT,
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(probe_report),
    }
    if target_name in {"beta-local", "gamma-local"}:
        command["testDataActorCase"] = (
            _stackctl.ProfileActorCaseId.BETA_MEDIA_PUBLICATION
            if target_name == "beta-local"
            else _stackctl.ProfileActorCaseId.GAMMA_MEDIA_PUBLICATION
        )
        command["testDataActorRoles"] = (
            ActorRole.PRIMARY,
            ActorRole.MEMBER,
        )
    return command


def _chat_group_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """将群候选、建群、mention 与 Inbox 闭环绑定到统一环境验证链。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    mutating = False
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mutating = True
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mutating = True
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # 真实生产只能读取受控验收账号的既有来源；Probe 本身会拒绝 prod 写入。
        mutating = False
    else:
        return None

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for chat group lifecycle probe"
        )
    probe_report = (
        report_dir / "chat-group-lifecycle.json"
        if report_dir is not None
        else _stackctl.env_runs_root(env_name)
        / "chat-group-lifecycle"
        / target_name
        / "chat-group-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "chat-service/smoke/run_chat_group_lifecycle_probe.py",
        "--env",
        env_name,
        "--base-url",
        api_base_url,
        "--require-nonempty-sources",
        "--report",
        str(probe_report),
    ]
    if mutating:
        argv.append("--mutating")
    command = {
        "name": f"{target_name}-chat-group-lifecycle",
        "argv": argv,
        "cwd": _stackctl.ROOT,
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(probe_report),
    }
    if target_name in {"beta-local", "gamma-local"}:
        command["testDataActorCase"] = (
            _stackctl.ProfileActorCaseId.BETA_CHAT_GROUP
            if target_name == "beta-local"
            else _stackctl.ProfileActorCaseId.GAMMA_CHAT_GROUP
        )
        command["testDataActorRoles"] = (ActorRole.PRIMARY,)
    return command


def _target_media_preflight_profile_command(
    target_name: str,
    report_dir: Path | None,
    *,
    data_readiness_path: Path | None = None,
) -> dict[str, Any] | None:
    """在设备 Patrol 之前验证 canonical media 的 Range/MIME。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    if target_name not in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
        "prod-hosted",
    }:
        return None
    health_report_path = (
        report_dir / "video-range-mime-preflight" / "report.json"
        if report_dir is not None
        else _stackctl.env_runs_root(
            str(_stackctl.get_target(_stackctl.load_environment_topology(), target_name)["env"]),
        )
        / "device-matrix"
        / "video-range-mime-preflight"
        / target_name
        / "report.json"
    )
    return {
        "name": f"{target_name}-release-video-canary-preflight",
        "argv": [
            "python3",
            "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
            "--target",
            target_name,
            "--release-readiness",
            str(data_readiness_path) if data_readiness_path is not None else "",
            "--report",
            str(health_report_path),
        ],
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(health_report_path),
    }


def _environment_page_smoke_profile_command(
    env_name: str,
    target_name: str,
    report_dir: Path | None,
    *,
    suite_name: str = "environment-page-smoke",
    patrol_target: str = _VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
    remote_api_evidence_report: Path | None = None,
    data_readiness_path: Path | None = None,
    release_video_work_id: str | None = None,
    persisted_device_session: bool = False,
) -> dict[str, Any] | None:
    import quwoquan_ops.cli.stackctl as _stackctl

    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        return None
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    required_bases = {
        "api",
        "productOps",
        "mediaAvatar",
        "mediaImage",
        "mediaVideo",
        "mediaUpload",
    }
    if not required_bases.issubset(public_bases):
        return None
    runtime_env = str(target.get("env") or env_name or "alpha")
    if target_name in {"prod-sim", "prod-hosted"}:
        runtime_env = "prod"
    playback_canary = target.get("playbackCanary")
    configured_canary_work_id = (
        str(playback_canary.get("workId") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    )
    canary_work_id_env = (
        str(playback_canary.get("workIdEnv") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    ) or "VIDEO_PLAYBACK_CANARY_WORK_ID"
    video_playback_canary_work_id = (
        configured_canary_work_id
        or os.environ.get(canary_work_id_env, "").strip()
    )
    if release_video_work_id is not None:
        # app-content-uat already validated this identity against the exact
        # Data appUatEnvelope. Preserve that single binding instead of
        # reinterpreting the receipt through an older canary query shape.
        video_playback_canary_work_id = str(release_video_work_id).strip()
    elif data_readiness_path is not None:
        try:
            release_binding = _stackctl.load_release_video_binding(
                data_readiness_path,
                expected_environment=runtime_env,
            )
        except _stackctl.ReleaseVideoDeliveryError:
            # The preceding release-video-canary preflight owns the typed
            # GATE_BLOCK. Never fall back to an environment identity here.
            video_playback_canary_work_id = ""
        else:
            video_playback_canary_work_id = str(release_binding["workId"])
    token = "" if target_name == "gamma-local" else _stackctl._resolve_test_auth_token(runtime_env)
    smoke_report = (
        report_dir / suite_name / "report.json"
        if report_dir is not None
        else _stackctl.env_runs_root(env_name)
        / "device-matrix"
        / suite_name
        / f"{target_name}.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--report",
        str(smoke_report),
        "--env-name",
        "local-gamma" if target_name == "gamma-local" else target_name,
        "--runtime-env",
        runtime_env,
        "--api-contract-env",
        runtime_env,
        "--gateway-base-url",
        str(public_bases["api"]),
        "--product-ops-base-url",
        str(public_bases["productOps"]),
        "--media-avatar-base-url",
        str(public_bases["mediaAvatar"]),
        "--media-image-base-url",
        str(public_bases["mediaImage"]),
        "--media-video-base-url",
        str(public_bases["mediaVideo"]),
        "--media-upload-base-url",
        str(public_bases["mediaUpload"]),
        "--rtc-media-connection-url",
        str(public_bases["rtc"]),
        "--target",
        patrol_target,
    ]
    if remote_api_evidence_report is not None:
        argv.extend(
            (
                "--remote-api-evidence-report",
                str(remote_api_evidence_report),
            )
        )
    if patrol_target in {
        _stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
        _stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
        _stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
    }:
        argv.extend(
            (
                "--video-playback-canary-work-id",
                video_playback_canary_work_id,
            )
        )
    if persisted_device_session:
        if patrol_target != _stackctl.RUNTIME_RECOVERY_UAT_TEST_TARGET:
            raise ValueError(
                "persisted device session is only valid for runtime recovery UAT"
            )
        argv.append("--persisted-device-session")
    platform = os.environ.get("STACKCTL_PAGE_SMOKE_PLATFORM", "").strip()
    if platform:
        argv.extend(["--platform", platform])
    device_id = os.environ.get("STACKCTL_PAGE_SMOKE_DEVICE_ID", "").strip()
    if device_id:
        argv.extend(["--device-id", device_id])
    if os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip() in {"1", "true", "yes"}:
        argv.append("--dry-run")
    command_env: dict[str, str] = {}
    if target_name != "gamma-local" and not persisted_device_session:
        if token:
            command_env["TEST_AUTH_TOKEN"] = token
        for key in (
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_PERSONA_ID",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                command_env[key] = value
    command = {
        "name": f"{target_name}-{suite_name}",
        "argv": argv,
        "cwd": _stackctl.ROOT,
        "blocking": True,
        "reportPath": _stackctl.relpath(smoke_report),
    }
    if command_env:
        command["env"] = command_env
    return command


def _account_enforcement_gamma_uat_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind the immutable GWT-003 CaseResult to Gamma release verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None
    evidence_root = (
        report_dir / "account-enforcement-gamma-uat"
        if report_dir is not None
        else _stackctl.env_runs_root("gamma")
        / "account-enforcement-gamma-uat"
        / target_name
    )
    report_path = evidence_root / "case-result.json"
    return {
        "name": "gamma-local-account-enforcement-uat",
        "argv": [
            "python3",
            _stackctl.ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR,
            "--manifest",
            _stackctl.ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
            "--report",
            str(report_path),
        ],
        "cwd": _stackctl.ROOT,
        "stopOnFailure": True,
        "reportPath": _stackctl.relpath(report_path),
    }
