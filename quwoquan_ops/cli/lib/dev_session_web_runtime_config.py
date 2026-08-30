"""dev-session 可变 Web hosting 的 runtime config 物化。

test_live Web bootstrap 与 App 走同一条 runtime config 单轨：本模块从当前工作树
派生 source identity、用本地 nonprod 签发域签出 runtime package 与 trust envelope，
再物化到 target-scoped 的可变 hosting 根。

角色：lib。由 `quwoquan_ops/cli/commands/dev_session_runtime.py` 消费。
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import decode_keyring
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
)
from quwoquan_ops.cli.lib.web_official_release import materialize_web_runtime_config

_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


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
    """把 artifact Web bundle 复制到可变 hosting 根并物化 runtime config。

    `hosting_root` 必须尚不存在：可变 render 每轮重建，不做增量覆盖。
    返回 trust envelope 与 runtime package 的摘要投影。
    """
    shutil.copytree(artifact_root, hosting_root)
    builder = _load_runtime_package_builder(repo_root)

    if _REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ValueError("mutable Web runtime package source revision is invalid")
    tree_result = run_command(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_root)
    tree_revision = tree_result.stdout.strip()
    if (
        tree_result.returncode != 0
        or _REVISION_PATTERN.fullmatch(tree_revision) is None
    ):
        raise ValueError("mutable Web runtime package source tree is invalid")

    signing = prepare_local_app_runtime_config_signing(repo_root)
    runtime_package = builder.build_runtime_config_package(
        environment=environment,
        target=target,
        launch_policy="test_live",
        values=builder.test_live_runtime_values(environment, target),
        source_git_sha=source_revision,
        source_tree_digest="sha1:" + tree_revision,
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
