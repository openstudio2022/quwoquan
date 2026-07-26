"""Prod-hosted 管理 SSH endpoint 的唯一解析入口。

该 endpoint 只属于运维访问隔离层，绝不能进入 ``runtime.yaml`` 或任何 App
runtime package。调用方仍可用 ``PROD_SSH_HOST`` 临时覆盖，用于 break-glass
或受控巡检；覆盖值同样只被当作 SSH host 使用。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
_SSH_HOST = re.compile(r"[A-Za-z0-9.-]+")


def prod_management_ssh_host(*, override: str | None = None) -> str:
    """Return the SSH-only management endpoint without reading runtime topology."""
    host = str(override or os.environ.get("PROD_SSH_HOST", "")).strip()
    if not host:
        try:
            payload = yaml.safe_load(ACCESS_MANIFEST.read_text(encoding="utf-8")) or {}
        except OSError as error:
            raise RuntimeError(f"cannot read prod access isolation manifest: {error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("prod access isolation manifest must be an object")
        management = payload.get("management") or {}
        if not isinstance(management, dict):
            raise RuntimeError("prod access isolation manifest management must be an object")
        host = str(management.get("sshHost") or "").strip()
    if not _SSH_HOST.fullmatch(host):
        raise RuntimeError("prod management SSH host must be a bare hostname or IP address")
    return host
