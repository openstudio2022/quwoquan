"""local release composition 的公网 Web hosting 物化。

immutable Web 包（`stackctl package --kind web`）按契约不携带
`runtime-config-trust.json` / `runtime-config-package.json`（配置外置，
见 `web_official_release._verify_runtime_config_is_external`），而 gamma-proxy
的 Caddy 从 `/srv/web` 直接 serve 这两个文件。本模块在启动装配时把
immutable 包复制到 target-scoped hosting 根并物化 runtime config——与
dev-session 可变轨、prod-hosted render 走同一条 `materialize_web_runtime_config`
单轨；nonprod 环境的 launch policy 与 dev-session 相同（test_live 单轨）。

角色：lib。由 `quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh` 消费。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from quwoquan_ops.cli.lib.dev_session_web_runtime_config import (
    materialize_dev_session_web_runtime_config,
)
from quwoquan_ops.cli.lib.output_paths import deployment_target_path


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def materialize_local_release_web_hosting(
    *,
    repo_root: Path,
    environment: str,
    target: str,
) -> tuple[Path, str]:
    """物化一个 release composition 可挂载的 Web hosting 根。

    返回 (hosting public 根, ``sha256:`` 前缀的内容摘要)。hosting 根按
    releaseId 定位并每次重建，与 immutable 包本体分离；包缺失时抛 ValueError。
    """

    package_root = deployment_target_path(
        target, "standalone-packages", "web", "packages", "public-web"
    )
    release_root = package_root / "current"
    manifest_path = release_root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "immutable public Web package is unavailable; "
            f"run stackctl package --env {environment} --kind web"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release_id = str(manifest.get("releaseId") or "").strip()
    content_digest = str(manifest.get("contentSHA256") or "").strip()
    if not release_id or not content_digest:
        raise ValueError("immutable public Web package manifest is invalid")

    revision = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or len(source_revision) != 40:
        raise ValueError("local release Web hosting source revision is unavailable")

    hosting_root = deployment_target_path(
        target, "standalone-packages", "web", "hosting", release_id
    )
    if hosting_root.exists():
        shutil.rmtree(hosting_root)
    materialize_dev_session_web_runtime_config(
        repo_root=repo_root,
        environment=environment,
        target=target,
        artifact_root=release_root / "public",
        hosting_root=hosting_root,
        source_revision=source_revision,
        run_command=_run,
    )
    return hosting_root, "sha256:" + content_digest


__all__ = ["materialize_local_release_web_hosting"]
