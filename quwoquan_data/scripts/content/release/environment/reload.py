"""Authenticated entity homepage reload boundary for environment releases."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

from core.io import write_json
from core.paths import OUTPUT_ROOT
from core.runtime_policy import active_runtime_policy
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import DeploymentEnvironment
from quwoquan_ops.cli.lib.local_environment_auth import open_local_acceptance_session


_ENTITY_RELOAD_PATH = "/homepages:reload"
_ENTITY_RELOAD_TIMEOUT_SECONDS = active_runtime_policy().entity_reload_timeout_seconds


def authorization_header_for_target(target: EnvironmentReleaseTarget) -> str:
    if target.mode is EnvironmentReleaseMode.LOCAL_IMPORT:
        session = open_local_acceptance_session(
            target.api_base_url,
            environment=target.environment.value,
            target_name=target.target_name,
            subject="data-release-operator",
        )
        return session.authorization_header()
    if target.mode is EnvironmentReleaseMode.HOSTED_IMPORT and target.auth_token:
        return "Bearer " + target.auth_token
    raise RuntimeError(
        f"environment release authorization unavailable: {target.environment.value}"
    )


def trigger_entity_reload(
    reload_url: str,
    *,
    authorization_header: str,
    release_id: str,
    run: Path | None = None,
) -> Path:
    """POST the reload operation without exposing the bearer in argv or evidence."""
    endpoint = f"{reload_url.rstrip('/')}{_ENTITY_RELOAD_PATH}"
    if not authorization_header.startswith("Bearer "):
        raise ValueError("entity-service reload requires an ephemeral bearer authorization header")
    process = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            "-o",
            "-",
            "-w",
            "\n%{http_code}",
            "--max-time",
            str(_ENTITY_RELOAD_TIMEOUT_SECONDS),
            "--header",
            "@-",
            endpoint,
        ],
        input=("Authorization: " + authorization_header + "\n").encode("utf-8"),
        capture_output=True,
        check=False,
    )
    raw = (process.stdout or b"").decode("utf-8", errors="replace").strip()
    body, _, code = raw.rpartition("\n")
    ok = process.returncode == 0 and code == str(HTTPStatus.OK.value)
    report_root = run or (
        OUTPUT_ROOT
        / "env"
        / DeploymentEnvironment.ALPHA
        / "runs"
        / "data-release"
        / release_id
        / f"reload-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    report_path = report_root / "entity-reload.json"
    write_json(
        report_path,
        {
            "schema": "quwoquan_data.entity_reload_report",
            "releaseId": release_id,
            "endpoint": endpoint,
            "httpStatus": code or None,
            "ok": ok,
            "response": body[:2000],
            "triggeredAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    if ok:
        print(f"[ship] entity-service reload ok: {endpoint} -> {body[:200]}")
    else:
        print(
            f"[ship] WARNING: entity-service reload failed "
            f"({endpoint}, http={code or 'n/a'}); 服务重启后导入仍生效",
            file=sys.stderr,
        )
    return report_path


__all__ = ["authorization_header_for_target", "trigger_entity_reload"]
