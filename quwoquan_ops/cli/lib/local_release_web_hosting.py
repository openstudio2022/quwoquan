"""local release composition 的公网 Web hosting 物化。

immutable Web 包由 `stackctl package --kind web` 写入其唯一 target-scoped
standalone root。reader 通过同一个 `web_deployment_package_dir` 解析它，绝不
通过 runtime candidate 或复制到第二个 package 位置。prod-sim 有唯一的 local
rehearsal runtime config 分支；prod-hosted 不可由本地 release hosting 物化。

角色：lib。由 `quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh` 消费。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from quwoquan_ops.cli.lib.dev_session_web_runtime_config import (
    materialize_dev_session_web_runtime_config,
    materialize_prod_sim_local_rehearsal_web_runtime_config,
)
from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_path,
    web_deployment_package_dir,
)


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

    if environment == "prod" and target != "prod-sim":
        raise ValueError("local release Web hosting only supports prod/prod-sim")

    package_root = web_deployment_package_dir(environment, target=target)
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
    materializer = (
        materialize_prod_sim_local_rehearsal_web_runtime_config
        if (environment, target) == ("prod", "prod-sim")
        else materialize_dev_session_web_runtime_config
    )
    materialized = materializer(
        repo_root=repo_root,
        environment=environment,
        target=target,
        artifact_root=release_root / "public",
        hosting_root=hosting_root,
        source_revision=source_revision,
        run_command=_run,
    )
    if (environment, target) == ("prod", "prod-sim") and (
        materialized.get("nonPromotable") is not True
        or materialized.get("runtimeScope") != "local_rehearsal"
    ):
        raise ValueError("prod-sim Web hosting materialization must be non-promotable")
    return hosting_root, "sha256:" + content_digest


__all__ = ["materialize_local_release_web_hosting"]
