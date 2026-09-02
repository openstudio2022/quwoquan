"""stackctl `verify` 命令选择器（静态命令组与 profile 命令表的组装）。

从 `commands/verify_domain.py` 迁出（该模块被后续功能增量推过 1000 行硬顶）：

- `_selected_verify_commands`：按 kind/profile 选择静态验证命令组
  （命令组真相源 `VERIFY_COMMAND_GROUPS` 仍由 stackctl 拥有）；
- `_selected_profile_commands`：按环境/target/profile 组合 profile 命令表
  （工厂本体在 `commands/verify_profiles.py`）。

测试经 ``mock.patch.object(stackctl, ...)`` patch 这两个符号；消费点
（`command_verify` 与 `verify_kinds`）一律经 `_stackctl.` 属性访问，
函数体内亦经函数内延迟导入 `_stackctl`，与 verify_domain 同一模式。
"""

from __future__ import annotations

from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile


def _selected_verify_commands(
    kind: str,
    env_name: str = "",
    *,
    target_name: str = "",
    profile: VerificationProfile,
) -> list[list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    packaging_commands = [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"]
        + (["--env", env_name] if env_name in _stackctl.ENVIRONMENTS else []),
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"]
        + (["--env", env_name] if env_name in _stackctl.ENVIRONMENTS else []),
        [
            "python3",
            "quwoquan_app/scripts/env/verify_prod_package_purity.py",
            "--target",
            target_name
            if env_name == "prod" and target_name
            else _stackctl.DEFAULT_TARGET_BY_ENV["prod"],
        ],
    ]
    if target_name:
        packaging_commands[0].extend(["--target", target_name])
        packaging_commands[1].extend(["--target", target_name])
    if kind == "all":
        commands: list[list[str]] = []
        group_names = ("topology", "config")
        if profile is not VerificationProfile.BASELINE:
            group_names = (*group_names, "packaging")
        for group_name in group_names:
            if group_name == "packaging":
                commands.extend(packaging_commands)
                continue
            for command in _stackctl.VERIFY_COMMAND_GROUPS[group_name]:
                selected = list(command)
                if (
                    group_name == "config"
                    and selected
                    and selected[-1].endswith("verify_media_delivery_contract.py")
                ):
                    if profile is VerificationProfile.BASELINE:
                        for component_environment in ("alpha", "beta", "gamma"):
                            selected.extend(
                                ["--component-environment", component_environment]
                            )
                    elif env_name in _stackctl.ENVIRONMENTS:
                        selected.extend(["--env", env_name])
                commands.append(selected)
        return commands
    if kind == "packaging":
        return packaging_commands
    commands = [list(command) for command in _stackctl.VERIFY_COMMAND_GROUPS[kind]]
    if kind == "config":
        for command in commands:
            if command and command[-1].endswith("verify_media_delivery_contract.py"):
                if profile is VerificationProfile.BASELINE:
                    for component_environment in ("alpha", "beta", "gamma"):
                        command.extend(
                            ["--component-environment", component_environment]
                        )
                elif env_name in _stackctl.ENVIRONMENTS:
                    command.extend(["--env", env_name])
    return commands


def _selected_profile_commands(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None = None,
    service: str = "",
    data_readiness_path: Path | None = None,
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    commands: list[dict[str, Any]] = []
    if profile.requires_environment and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
    }:
        # verify is read-only with respect to package/build/deployment selection.
        # A missing or unhealthy runtime must block instead of triggering nested up.
        # Follow the active workload health scope: content-release must not be
        # forced through full commercial service probes.
        health_scope = _stackctl._current_runtime_health_scope(target_name)
        commands.append(
            {
                "name": f"{target_name}-health-preflight",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "health",
                    "--target",
                    target_name,
                    "--scope",
                    health_scope,
                ],
                "cwd": _stackctl.ROOT,
            }
        )
    domain_remote_api_command = (
        _stackctl._app_domain_remote_api_integration_profile_command(
            target_name,
            profile,
            report_dir,
        )
        if not service
        else None
    )
    if domain_remote_api_command is not None:
        commands.append(domain_remote_api_command)
    if service:
        if (
            service == "assistant-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _stackctl._assistant_learning_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        if (
            service == "user-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _stackctl._profile_proposal_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        return commands
    if profile is VerificationProfile.SMOKE:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "test/local_contract/service/content_service/media/media_asset/content_media_url__local_contract_test.dart",
                        "test/local_contract/service/chat_service/chat/conversation/chat_avatar_url_resolution__local_contract_test.dart",
                    ],
                    "cwd": _stackctl.ROOT,
                },
            ]
        )
    if (
        profile in {VerificationProfile.INTEGRATION, VerificationProfile.RELEASE}
        and target_name in {"beta-local", "gamma-local", "prod-hosted"}
    ):
        commands.append(
            {
                "name": "filter-catalog-active-release",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "filter-catalog",
                    "--target",
                    target_name,
                    "--action",
                    "verify",
                ],
                "cwd": _stackctl.ROOT,
            }
        )
    report_feedback_command = _stackctl._report_feedback_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        report_feedback_command is not None
        and _stackctl._current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
    ):
        # content-release 不启 notification/product-ops；举报回流依赖
        # /app-messages，只能在 full workload 上证明。
        commands.append(report_feedback_command)
    media_publication_command = _stackctl._media_publication_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if media_publication_command is not None:
        commands.append(media_publication_command)
    chat_group_lifecycle_command = _stackctl._chat_group_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        chat_group_lifecycle_command is not None
        and _stackctl._current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
    ):
        # content-release 不启 chat-service；建群到 inbox 旅程仅 full workload 证明。
        commands.append(chat_group_lifecycle_command)
    onboarding_author_impact_command = (
        _stackctl._onboarding_author_impact_gamma_api_integration_profile_command(
            target_name,
            profile,
            report_dir,
        )
    )
    if onboarding_author_impact_command is not None:
        commands.append(onboarding_author_impact_command)
    search_remote_api_command = _stackctl._search_remote_api_integration_profile_command(
        target_name,
        profile,
        report_dir,
        data_readiness_path=data_readiness_path,
    )
    if search_remote_api_command is not None:
        commands.append(search_remote_api_command)
    if profile is VerificationProfile.RELEASE:
        if target_name == "prod-hosted":
            target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "prod-public-health",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "--output-format",
                        "json",
                        "health",
                        "--target",
                        "prod-hosted",
                        "--scope",
                        "full",
                    ],
                    "env": {"CLOUD_GATEWAY_BASE_URL": str(public_bases["api"])},
                }
            )
        media_preflight_command = _stackctl._target_media_preflight_profile_command(
            target_name,
            report_dir,
            data_readiness_path=data_readiness_path,
        )
        if media_preflight_command is not None:
            commands.append(media_preflight_command)
        smoke_command = _stackctl._environment_page_smoke_profile_command(
            env_name,
            target_name,
            report_dir,
            data_readiness_path=data_readiness_path,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        if env_name in {"beta", "gamma"} and target_name in {
            "beta-local",
            "gamma-local",
        }:
            runtime_recovery_command = _stackctl._environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="runtime-recovery-patrol",
                patrol_target=_stackctl.RUNTIME_RECOVERY_UAT_TEST_TARGET,
                persisted_device_session=True,
            )
            if runtime_recovery_command is not None:
                commands.append(runtime_recovery_command)
        if env_name == "gamma" and target_name == "gamma-local":
            account_enforcement_command = (
                _stackctl._account_enforcement_gamma_uat_profile_command(
                    target_name,
                    profile,
                    report_dir,
                )
            )
            if account_enforcement_command is not None:
                commands.append(account_enforcement_command)
            search_api_report = (
                report_dir
                / "search-remote-api-integration"
                / "search_remote_api_uat_report.json"
                if report_dir is not None
                else _stackctl.env_runs_root("gamma")
                / "search-remote-api-integration"
                / target_name
                / "search_remote_api_uat_report.json"
            )
            search_smoke_command = _stackctl._environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="search-remote-patrol",
                patrol_target=(
                    "test/user_acceptance/journeys/cross_domain_search/"
                    "cross_domain_search_journey__user_acceptance_test.dart"
                ),
                remote_api_evidence_report=search_api_report,
            )
            if search_smoke_command is not None:
                commands.append(search_smoke_command)
    return commands

