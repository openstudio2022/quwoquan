"""verify 复用近期成功 package，避免矩阵内重复打包。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    service_deployment_package_dir,
)


FINGERPRINT_NAME = "package-fingerprint.json"


def fingerprint_path(env_name: str, target_name: str) -> Path:
    return app_deployment_package_dir(env_name, target=target_name) / FINGERPRINT_NAME


def write_package_fingerprint(
    env_name: str,
    target_name: str,
    *,
    report_dir: str,
    include_services: bool,
    details: list[str],
) -> Path:
    path = fingerprint_path(env_name, target_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "stackctl-package-fingerprint",
        "env": env_name,
        "target": target_name,
        "includeServices": include_services,
        "reportDir": report_dir,
        "details": details[:20],
        "appPackageDir": str(app_deployment_package_dir(env_name, target=target_name)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def can_reuse_package(
    env_name: str,
    target_name: str,
    *,
    include_services: bool = True,
    required_services: list[str] | None = None,
) -> tuple[bool, str]:
    path = fingerprint_path(env_name, target_name)
    if not path.is_file():
        return False, f"missing fingerprint: {path}"
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable fingerprint: {exc}"
    app_dir = app_deployment_package_dir(env_name, target=target_name)
    if not app_dir.is_dir():
        return False, f"app package dir missing: {app_dir}"
    if include_services:
        services = required_services or ["content-service", "user-service"]
        for service in services:
            svc_dir = service_deployment_package_dir(
                env_name, service, target=target_name
            )
            if not svc_dir.is_dir():
                return False, f"service package dir missing: {svc_dir}"
    return True, f"reuse ok fingerprint={path} reportDir={payload.get('reportDir', '')}"
