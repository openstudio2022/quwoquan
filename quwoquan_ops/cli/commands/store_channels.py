"""stackctl `store-channels`：市场/官网分发渠道矩阵的 canonical 查询与准入裁决。

deliver-deploy-prod-pipeline DEC-004：渠道矩阵只从
`app_artifact_manifest.yaml` 的 `distribution_channels` 生成，逐渠道声明
platform、uploadFormat、signing custodian、readback、automation tier 与
凭据 owner；一个渠道的回执不得替代另一渠道。

凭据值/文件一律不入仓库：每渠道 `credential_env` 指向凭据文件路径的
环境变量名。凭据缺失、或平台 Prod 正式 ID 未登记外部事实时，该渠道
保持 GATE_BLOCK（由 OPEN 承接），不得用 side-load 冒充市场安装证据。

- 无 --channel：列出全矩阵与逐渠道就绪状态（查询语义，exitCode 0）。
- 有 --channel：作为该渠道上传/回读 runner 的准入门；blocked 即
  exitCode 2，阻止伪造市场分发。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quwoquan_ops.cli.lib.app_identity import (  # noqa: E402
    ARTIFACT_METADATA_PATH,
    AppIdentityError,
    resolve_app_identity,
)
from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402

_CHANNEL_REQUIRED_FIELDS = (
    "platform",
    "upload_format",
    "distribution_class",
    "store_signing_custodian",
    "readback",
    "automation_tier",
    "credential_owner",
    "credential_env",
)


def register_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "store-channels",
        help=(
            "Resolve the canonical distribution channel matrix and per-channel "
            "readiness (credentials, registered production id)."
        ),
    )
    parser.add_argument(
        "--app-platform",
        choices=("android", "ios", "all"),
        default="all",
    )
    parser.add_argument(
        "--channel",
        default="",
        help=(
            "Gate one channel for upload/readback; a blocked channel exits 2 "
            "instead of pretending store evidence exists."
        ),
    )


def _declared_channels() -> dict[str, dict[str, Any]]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    channels = document.get("distribution_channels")
    if not isinstance(channels, dict) or not channels:
        raise AppIdentityError("distribution_channels metadata is missing")
    resolved: dict[str, dict[str, Any]] = {}
    for channel_id, declaration in channels.items():
        if not isinstance(declaration, dict):
            raise AppIdentityError(
                f"distribution channel {channel_id} declaration must be a mapping"
            )
        missing = [
            field
            for field in _CHANNEL_REQUIRED_FIELDS
            if not str(declaration.get(field) or "").strip()
        ]
        if missing:
            raise AppIdentityError(
                f"distribution channel {channel_id} is missing required "
                f"fields: {', '.join(missing)}"
            )
        resolved[str(channel_id)] = declaration
    return resolved


def _credential_status(credential_env: str) -> tuple[str, str]:
    """凭据只以环境变量指向的本地文件存在；返回 (status, reason)。"""
    value = os.environ.get(credential_env, "").strip()
    if not value:
        return (
            "missing",
            f"credential environment variable {credential_env} is not set",
        )
    if not Path(value).is_file():
        return (
            "missing",
            f"{credential_env} points to a non-existent credential file",
        )
    return ("ready", "")


def _channel_row(channel_id: str, declaration: dict[str, Any]) -> dict[str, Any]:
    platform = str(declaration["platform"])
    blocked_reasons: list[str] = []

    application_id = ""
    registered = False
    try:
        identity = resolve_app_identity(
            platform=platform, environment="prod", build_mode="release"
        )
        application_id = identity.application_id
        registered = identity.registered
    except AppIdentityError as error:
        blocked_reasons.append(str(error))
    if application_id and not registered and (
        str(declaration["distribution_class"]) == "store"
    ):
        blocked_reasons.append(
            f"{platform} production application id is not a registered "
            "external fact (tracked as OPEN); store upload is blocked"
        )

    credential_env = str(declaration["credential_env"])
    credential_status, credential_reason = _credential_status(credential_env)
    if credential_status != "ready":
        blocked_reasons.append(credential_reason)

    return {
        "channelId": channel_id,
        "platform": platform,
        "uploadFormat": str(declaration["upload_format"]),
        "distributionClass": str(declaration["distribution_class"]),
        "storeSigningCustodian": str(declaration["store_signing_custodian"]),
        "readback": str(declaration["readback"]),
        "automationTier": str(declaration["automation_tier"]),
        "credentialOwner": str(declaration["credential_owner"]),
        "credentialEnv": credential_env,
        "credentialStatus": credential_status,
        "applicationId": application_id,
        "registeredProductionId": registered,
        "status": "blocked" if blocked_reasons else "ready",
        "blockedReasons": blocked_reasons,
    }


def command_store_channels(args: argparse.Namespace) -> dict[str, Any]:
    platform_filter = str(getattr(args, "app_platform", "all") or "all").strip()
    requested_channel = str(getattr(args, "channel", "") or "").strip()

    try:
        channels = _declared_channels()
    except AppIdentityError as error:
        return {
            "exitCode": 2,
            "summary": "distribution channel matrix metadata is invalid",
            "details": [str(error)],
        }

    if requested_channel:
        declaration = channels.get(requested_channel)
        if declaration is None:
            return {
                "exitCode": 2,
                "summary": f"unknown distribution channel: {requested_channel}",
                "details": [f"declared channels: {', '.join(sorted(channels))}"],
            }
        row = _channel_row(requested_channel, declaration)
        if row["status"] != "ready":
            return {
                "exitCode": 2,
                "summary": (
                    f"distribution channel {requested_channel} is GATE_BLOCK; "
                    "store evidence must not be fabricated"
                ),
                "details": list(row["blockedReasons"]),
                "channel": row,
            }
        return {
            "exitCode": 0,
            "summary": f"distribution channel {requested_channel} is ready",
            "details": [
                f"platform: {row['platform']}",
                f"uploadFormat: {row['uploadFormat']}",
                f"readback: {row['readback']}",
                f"applicationId: {row['applicationId']}",
            ],
            "channel": row,
        }

    rows = [
        _channel_row(channel_id, declaration)
        for channel_id, declaration in sorted(channels.items())
        if platform_filter == "all" or declaration["platform"] == platform_filter
    ]
    ready = sorted(row["channelId"] for row in rows if row["status"] == "ready")
    blocked = sorted(row["channelId"] for row in rows if row["status"] == "blocked")
    return {
        "exitCode": 0,
        "summary": (
            f"distribution channel matrix: {len(ready)} ready, "
            f"{len(blocked)} blocked"
        ),
        "details": [
            f"ready: {', '.join(ready) or 'none'}",
            f"blocked: {', '.join(blocked) or 'none'}",
        ],
        "channels": rows,
        "readyChannels": ready,
        "blockedChannels": blocked,
    }
