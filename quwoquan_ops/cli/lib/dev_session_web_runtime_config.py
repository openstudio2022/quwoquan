"""可变 Web hosting 的 runtime config 物化。

test_live Web bootstrap 与 App 走同一条 runtime config 单轨：本模块从当前工作树
派生 source identity、用本地 nonprod 签发域签出 runtime 文档与 trust envelope，
再物化到 target-scoped 的可变 hosting 根。文档类型只由 content_source_policy
派生：Alpha 必须是 bundled_snapshot 离线文档，Beta/Gamma/Prod 才签发 Remote
在线 package。

prod-sim 只走显式的本地 rehearsal 分支：使用 target-scoped 的本地签发域，
构造合法 prod/prod_release runtime package，并将 nonPromotable 标识留在
hosting materialization projection，不污染 schema-locked 的签名 package。

角色：lib。由 dev-session 与 local release composition 消费。
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
    load_launch_manifest_contract,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import decode_keyring
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
    prepare_local_prod_sim_rehearsal_runtime_config_signing,
)
from quwoquan_ops.cli.lib.output_paths import app_deployment_package_dir
from quwoquan_ops.cli.lib.web_official_release import materialize_web_runtime_config

_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
_PROD_SIM_REHEARSAL_PAIR = ("prod", "prod-sim")
_RUNTIME_PUBLIC_BASES = {
    "gatewayBaseUrl": "api",
    "legalBaseUrl": "legal",
    "publicWebBaseUrl": "publicWeb",
    "appDownloadBaseUrl": "appDownload",
    "realtimeBaseUrl": "realtime",
    "mediaAvatarCdnBaseUrl": "mediaAvatar",
    "mediaImageCdnBaseUrl": "mediaImage",
    "mediaVideoCdnBaseUrl": "mediaVideo",
    "mediaUploadBaseUrl": "mediaUpload",
    "rtcMediaConnectionUrl": "rtc",
}


def _load_runtime_package_builder(repo_root: Path) -> Any:
    """加载 App 侧唯一的 runtime package 构造实现，避免在 Ops 复制第二份。"""

    script = repo_root / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"
    specification = importlib.util.spec_from_file_location(
        "_qwq_web_runtime_package_builder", script
    )
    if specification is None or specification.loader is None:
        raise ValueError("mutable Web runtime package builder is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _source_tree_digest(
    *,
    repo_root: Path,
    source_revision: str,
    run_command: Callable[..., Any],
) -> str:
    if _REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ValueError("mutable Web runtime package source revision is invalid")
    tree_result = run_command(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_root)
    tree_revision = tree_result.stdout.strip()
    if tree_result.returncode != 0 or _REVISION_PATTERN.fullmatch(tree_revision) is None:
        raise ValueError("mutable Web runtime package source tree is invalid")
    return "sha1:" + tree_revision


def _hosting_runtime_document(
    *,
    builder: Any,
    environment: str,
    target: str,
    source_revision: str,
    source_tree_digest: str,
    signing: Any,
) -> dict[str, Any]:
    """按 content_source_policy 签发唯一 Web hosting 文档，禁止环境开关覆盖。"""

    content_source = load_launch_manifest_contract()["content_source_policy"].get(
        environment
    )
    identity = {
        "environment": environment,
        "target": target,
        "launch_policy": "test_live",
        "source_git_sha": source_revision,
        "source_tree_digest": source_tree_digest,
        "signing": signing,
    }
    if content_source == "bundled_snapshot":
        return builder.build_offline_bootstrap_document(**identity)
    if content_source == "remote":
        return builder.build_runtime_config_package(
            values=builder.test_live_runtime_values(environment, target),
            **identity,
        )
    raise ValueError(
        f"Web hosting has no content source policy for environment {environment}"
    )


def _prod_sim_local_rehearsal_runtime_values(
    *,
    repo_root: Path,
    environment: str,
    target: str,
    builder: Any,
) -> dict[str, str]:
    if (environment, target) != _PROD_SIM_REHEARSAL_PAIR:
        raise ValueError("local Web rehearsal runtime config only supports prod/prod-sim")
    package_root = app_deployment_package_dir(environment, target=target)
    config_path = package_root / "app_runtime.yaml"
    report_path = package_root / "report.json"
    if not config_path.is_file() or not report_path.is_file():
        raise ValueError(
            "prod-sim packaged app runtime config is unavailable; run stackctl package first"
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("prod-sim packaged app runtime report is unreadable") from exc
    if (
        report.get("status") != "packaged"
        or report.get("env") != environment
        or report.get("target") != target
    ):
        raise ValueError("prod-sim packaged app runtime identity is invalid")
    values = builder.parse_runtime_yaml(config_path)
    topology = load_environment_topology(repo_root / "quwoquan_ops" / "environments")
    target_contract = get_target(topology, target)
    public_bases = target_contract.get("publicBases")
    if target_contract.get("env") != environment or not isinstance(public_bases, dict):
        raise ValueError("prod-sim runtime topology selection is invalid")
    expected = {
        key: str(public_bases.get(role) or "").rstrip("/")
        for key, role in _RUNTIME_PUBLIC_BASES.items()
    }
    actual = {key: str(values.get(key) or "").rstrip("/") for key in expected}
    if values.get("appRuntimeEnv") != environment or actual != expected:
        raise ValueError("prod-sim packaged app runtime does not match its topology")
    return {"appRuntimeEnv": environment, **actual}


def materialize_dev_session_web_runtime_config(
    *,
    repo_root: Path,
    environment: str,
    target: str,
    artifact_root: Path,
    hosting_root: Path,
    source_revision: str,
    run_command: Callable[..., Any],
) -> dict[str, object]:
    """物化非生产 dev-session 的 test_live Web runtime config。"""

    shutil.copytree(artifact_root, hosting_root)
    builder = _load_runtime_package_builder(repo_root)
    source_tree_digest = _source_tree_digest(
        repo_root=repo_root,
        source_revision=source_revision,
        run_command=run_command,
    )
    signing = prepare_local_app_runtime_config_signing(repo_root)
    runtime_package = _hosting_runtime_document(
        builder=builder,
        environment=environment,
        target=target,
        source_revision=source_revision,
        source_tree_digest=source_tree_digest,
        signing=signing,
    )
    trust_envelope = build_runtime_config_trust_envelope(
        "nonprod",
        decode_keyring(signing.trusted_public_keys_path.read_bytes()),
    )
    return materialize_web_runtime_config(
        hosting_root=hosting_root,
        trust_envelope=trust_envelope,
        runtime_package=runtime_package,
        expected_environment=environment,
        expected_target=target,
    )


def materialize_prod_sim_local_rehearsal_web_runtime_config(
    *,
    repo_root: Path,
    environment: str,
    target: str,
    artifact_root: Path,
    hosting_root: Path,
    source_revision: str,
    run_command: Callable[..., Any],
) -> dict[str, object]:
    """物化唯一 non-promotable prod-sim local rehearsal Web runtime config."""

    if (environment, target) != _PROD_SIM_REHEARSAL_PAIR:
        raise ValueError("local Web rehearsal runtime config only supports prod/prod-sim")
    shutil.copytree(artifact_root, hosting_root)
    builder = _load_runtime_package_builder(repo_root)
    source_tree_digest = _source_tree_digest(
        repo_root=repo_root,
        source_revision=source_revision,
        run_command=run_command,
    )
    signing = prepare_local_prod_sim_rehearsal_runtime_config_signing(
        repo_root,
        environment=environment,
        target=target,
    )
    runtime_package = builder.build_runtime_config_package(
        environment=environment,
        target=target,
        launch_policy="prod_release",
        values=_prod_sim_local_rehearsal_runtime_values(
            repo_root=repo_root,
            environment=environment,
            target=target,
            builder=builder,
        ),
        source_git_sha=source_revision,
        source_tree_digest=source_tree_digest,
        signing=signing,
    )
    trust_envelope = build_runtime_config_trust_envelope(
        "prod",
        decode_keyring(signing.trusted_public_keys_path.read_bytes()),
    )
    materialized = materialize_web_runtime_config(
        hosting_root=hosting_root,
        trust_envelope=trust_envelope,
        runtime_package=runtime_package,
        expected_environment=environment,
        expected_target=target,
    )
    return {
        **materialized,
        "nonPromotable": True,
        "runtimeScope": "local_rehearsal",
    }


__all__ = [
    "materialize_dev_session_web_runtime_config",
    "materialize_prod_sim_local_rehearsal_web_runtime_config",
]
