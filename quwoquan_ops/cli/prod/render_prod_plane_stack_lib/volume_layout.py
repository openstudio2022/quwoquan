"""compose 卷与运行时凭据挂载重写（从 render_prod_plane_stack.py 逐字搬移）。"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

def _persistent_media_sync_command(source: Path, plane_name: str, remote_root: str) -> str:
    """同步只创建所属账号的持久媒体目录；不打包状态、不 chown 他人目录。"""
    from .package_inputs import _plane_spec

    plane = _plane_spec(plane_name)
    report = json.loads((source / "provenance.json").read_text(encoding="utf-8"))
    instance, replica = report.get("instance", ""), report.get("replicaId", "")
    if instance not in {"prevalidate", "gray", "prod"} or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", replica):
        raise SystemExit("GATE_BLOCK: invalid persistent media instance/replica")
    base = Path(plane["composeProjectRoot"])
    ref = Path(plane["rootlessRuntimeLayout"]["mediaStateRef"])
    if not base.is_absolute() or ref.is_absolute() or ".." in ref.parts:
        raise SystemExit("GATE_BLOCK: unsafe persistent media manifest path")
    expected_root = base / "instances" / instance / replica
    media = base / "state" / instance / replica / ref
    if (
        report.get("plane") != plane_name or remote_root != str(expected_root)
        or report.get("remoteRoot") != str(expected_root) or report.get("mediaRoot") != str(media)
    ):
        raise SystemExit("GATE_BLOCK: persistent media owner/root identity mismatch")
    script = """import os, pathlib, stat, sys
base, target = map(pathlib.Path, sys.argv[1:])
for parent in reversed((target, *target.parents)):
    if parent.is_symlink():
        raise SystemExit('GATE_BLOCK: persistent media symlink')
    if parent == base or base in parent.parents:
        parent.mkdir(mode=0o750, exist_ok=True)
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise SystemExit('GATE_BLOCK: persistent media owner mismatch')
os.chmod(target, 0o750)
"""
    return "python3 -c " + shlex.quote(script) + " " + shlex.quote(str(base)) + " " + shlex.quote(str(media))


def _rewrite_volume(raw: str) -> str:
    return raw


def _compose_bind_source(path_value: str) -> str:
    value = str(path_value).strip()
    if not value:
        raise SystemExit("FAIL: compose bind source path is empty")
    if value.startswith("/"):
        return value
    if value.startswith("./"):
        return value
    return f"./{value}"


# DEC-005：环境身份与 platform-ops facts 树由部署面（渲染期）材料化后只读挂载，
# 不烤入镜像；两者都落在 render 输出的 runtime/ 下随 sync 一起到达远端。
ARTIFACT_IDENTITY_MOUNT_TARGET = "/etc/quwoquan/artifact-identity.json"
ARTIFACT_IDENTITY_RENDER_REF = "./runtime/artifact-identity.json"
PLATFORM_OPS_FACTS_MOUNT_TARGET = "/app"
PLATFORM_OPS_FACTS_RENDER_REF = "./runtime/platform-ops-facts"


def _mount_target_matches(raw: str, target: str) -> bool:
    """按精确 mount target 匹配（`src:target` 或 `src:target:opts`），不做子串匹配。"""
    return raw.endswith(f":{target}") or f":{target}:" in raw


def _rewrite_volume_with_layout(
    raw: str,
    *,
    config_root: str,
    media_root: str,
    legal_root: str,
    portal_root: str,
    caddyfile_path: str,
    model_cache_root: str,
) -> str:
    for target, source in (
        (ARTIFACT_IDENTITY_MOUNT_TARGET, ARTIFACT_IDENTITY_RENDER_REF),
        (PLATFORM_OPS_FACTS_MOUNT_TARGET, PLATFORM_OPS_FACTS_RENDER_REF),
    ):
        if _mount_target_matches(raw, target):
            return f"{source}{raw[raw.index(':' + target):]}"
    mount_sources = {
        "/etc/qwq-config": config_root,
        "/srv/media": media_root,
        "/var/lib/quwoquan/chat-media": media_root,
        "/srv/legal": legal_root,
        "/srv/portal": portal_root,
        "/etc/caddy/Caddyfile": caddyfile_path,
        "/app/cache": model_cache_root,
    }
    for target, source in mount_sources.items():
        marker = f":{target}"
        if marker in raw:
            return f"{_compose_bind_source(source)}{raw[raw.index(marker):]}"
    return raw


_DEFAULTED_VOLUME_REF = re.compile(r"^\$\{[A-Z][A-Z0-9_]*:-([A-Za-z0-9][A-Za-z0-9_.-]*)\}$")


def _named_volume_source(raw: str) -> str | None:
    if ":" not in raw:
        return None
    # `${VAR:-name}:/target` 形态的命名卷：渲染面不注入 VAR，插值结果就是默认名，
    # 顶层 volumes 必须保留该默认名，否则 compose 报 undefined volume。
    defaulted = _DEFAULTED_VOLUME_REF.match(raw.rsplit(":/", 1)[0] if ":/" in raw else raw)
    if defaulted is not None:
        return defaulted.group(1)
    source = raw.split(":", 1)[0]
    if source.startswith(".") or source.startswith("/") or source.startswith("${"):
        return None
    return source

def _runtime_credential_source(
    credentials_root: str,
    relative_source: Any,
    *,
    label: str,
) -> str:
    normalized = str(relative_source or "").strip()
    relative = Path(normalized)
    if not normalized or relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(
            f"FAIL: {label} must be a non-empty credentialsPath-relative path"
        )
    return str(Path(credentials_root) / relative)


def _filter_top_level_volumes(services: dict[str, Any], top_level: dict[str, Any]) -> dict[str, Any]:
    referenced: set[str] = set()
    for spec in services.values():
        for item in spec.get("volumes") or []:
            if not isinstance(item, str):
                continue
            source = _named_volume_source(item)
            if source:
                referenced.add(source)
    return {name: value for name, value in top_level.items() if name in referenced}
