"""部署期环境身份与 platform-ops facts 的只读挂载材料。"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path



def _bind_artifact_identity_mount_material(
    environment: dict[str, str],
    *,
    source_root: Path | None = None,
) -> None:
    """按 DEC-005 物化部署期环境身份，不把环境身份写入镜像字节。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(environment.get("QWQ_LOCAL_RELEASE_ENV") or "").strip()
    if env_name not in {"alpha", "beta", "gamma", "prod"}:
        raise ValueError("artifact identity mount environment is unresolved")
    config_digest = str(environment.get("LOCAL_GAMMA_CONFIG_VERSION") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest) is None:
        raise ValueError("artifact identity mount configuration digest is unresolved")
    run_root = Path(str(environment.get("QWQ_RUN_ROOT") or "").strip())
    if not str(run_root) or str(run_root) == "." or not run_root.is_dir():
        raise ValueError("artifact identity mount run root is unavailable")
    identity_path = run_root / "artifact-identity.json"
    if identity_path.exists():
        identity_path.unlink()
    identity_path.write_text(
        json.dumps(
            {
                "schema": "qwq.environment-artifact-identity",
                "environment": env_name,
                "configDigest": config_digest,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    identity_path.chmod(0o444)
    environment["QWQ_COMPOSE_ARTIFACT_IDENTITY_FILE"] = str(identity_path)

    root = (source_root or _stackctl.ROOT).resolve()
    facts_root = run_root / "platform-ops-facts"
    if facts_root.exists():
        shutil.rmtree(facts_root)
    services_root = root / "quwoquan_service" / "services"
    for service_root in sorted(services_root.iterdir()):
        environment_root = service_root / "environments" / env_name
        if not environment_root.is_dir():
            continue
        target = facts_root / "quwoquan_service" / "services" / service_root.name
        shutil.copytree(service_root / "config", target / "config")
        shutil.copytree(environment_root, target / "environments" / env_name)
    platform_root = root / "quwoquan_service" / "control-plane" / "platform-ops"
    platform_target = (
        facts_root / "quwoquan_service" / "control-plane" / "platform-ops"
    )
    shutil.copytree(platform_root / "config", platform_target / "config")
    shutil.copytree(
        platform_root / "environments" / env_name,
        platform_target / "environments" / env_name,
    )
    shutil.copytree(
        root / "quwoquan_ops" / "environments" / env_name,
        facts_root / "quwoquan_ops" / "environments" / env_name,
    )
    environment["QWQ_COMPOSE_PLATFORM_OPS_FACTS_ROOT"] = str(facts_root)


__all__ = ["_bind_artifact_identity_mount_material"]
