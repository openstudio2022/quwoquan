"""stackctl `store-distribution`：逐渠道分发回执的登记与查询。

deliver-deploy-prod-pipeline DEC-007：CI/CD release/distribution control
plane 拥有上传/审核/发布事实。本命令是渠道分发回执的唯一写入口：

- 写入前先过 `store-channels` 同一渠道准入门（凭据在位、Prod 正式 ID
  已登记），blocked 渠道不得伪造分发证据。
- 回执 schema/字段/约束单轨来自 `app_artifact_manifest.yaml` 的
  `app_distribution_receipt` 段，脚本不自持第二份字段集合。
- fan-out 不变量在写入时强制：同一 candidateId 下所有 android 渠道回执
  必须引用同一 release APK artifactDigest；非 uploaded 的 phase 要求同渠道
  同 candidate 已存在 uploaded 回执。
- 回执 append-only、内容寻址落盘（prod-hosted deployment target），
  不修改、不覆盖既有回执。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quwoquan_ops.cli.commands.store_channels import (  # noqa: E402
    _channel_row,
    _declared_channels,
)
from quwoquan_ops.cli.lib.app_identity import (  # noqa: E402
    ARTIFACT_METADATA_PATH,
    AppIdentityError,
)
from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    deployment_target_path,
)

_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_RECEIPT_SEGMENTS = ("receipts", "store-distribution")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "store-distribution",
        help=(
            "Record or list append-only per-channel app distribution "
            "receipts bound to one reviewed release candidate."
        ),
    )
    parser.add_argument("--channel", default="")
    parser.add_argument("--candidate-id", default="")
    parser.add_argument("--artifact-digest", default="")
    parser.add_argument("--display-version", default="")
    parser.add_argument("--build-number", default="")
    parser.add_argument("--phase", default="")
    parser.add_argument("--platform-record-id", default="")
    parser.add_argument(
        "--readback-evidence",
        default="",
        help=(
            "Path to the authoritative readback evidence file "
            "(store console export / API response); its sha256 becomes "
            "readbackDigest."
        ),
    )
    parser.add_argument(
        "--list",
        dest="list_receipts",
        action="store_true",
        help="List existing receipts (optionally filtered by --channel).",
    )


def _receipt_contract() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    contract = (document.get("schemas") or {}).get("app_distribution_receipt")
    if (
        not isinstance(contract, dict)
        or not isinstance(contract.get("required_fields"), list)
        or not isinstance(contract.get("fields"), dict)
    ):
        raise AppIdentityError("app_distribution_receipt contract is missing")
    return contract


def _allowed_values(contract: dict[str, Any], field: str) -> list[str]:
    values = (contract["fields"].get(field) or {}).get("allowed_values")
    if not isinstance(values, list) or not values:
        raise AppIdentityError(
            f"app_distribution_receipt {field} enum is not canonical"
        )
    return [str(value) for value in values]


def _receipt_root() -> Path:
    return deployment_target_path("prod-hosted", *_RECEIPT_SEGMENTS)


def _existing_receipts(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("schema") == "app-distribution-receipt"
        ):
            receipts.append(payload)
    return receipts


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def command_store_distribution(args: argparse.Namespace) -> dict[str, Any]:
    channel_id = str(getattr(args, "channel", "") or "").strip()
    if getattr(args, "list_receipts", False):
        return _list_receipts(channel_id)
    return _record_receipt(args, channel_id)


def _list_receipts(channel_id: str) -> dict[str, Any]:
    receipts = [
        receipt
        for receipt in _existing_receipts(_receipt_root())
        if not channel_id or receipt.get("channelId") == channel_id
    ]
    return {
        "exitCode": 0,
        "summary": f"{len(receipts)} distribution receipt(s)",
        "details": [
            f"{receipt['channelId']}/{receipt['phase']}: "
            f"{receipt['displayVersion']}+{receipt['buildNumber']} "
            f"candidate={str(receipt['candidateId'])[:19]}..."
            for receipt in receipts
        ],
        "receipts": receipts,
    }


def _record_receipt(
    args: argparse.Namespace, channel_id: str
) -> dict[str, Any]:
    try:
        contract = _receipt_contract()
        channels = _declared_channels()
    except AppIdentityError as error:
        return {
            "exitCode": 2,
            "summary": "distribution receipt metadata is invalid",
            "details": [str(error)],
        }
    allowed_channels = _allowed_values(contract, "channelId")
    allowed_phases = _allowed_values(contract, "phase")

    blockers: list[str] = []
    if channel_id not in allowed_channels:
        blockers.append(
            f"--channel must be one of: {', '.join(sorted(allowed_channels))}"
        )
    candidate_id = str(getattr(args, "candidate_id", "") or "").strip()
    artifact_digest = str(getattr(args, "artifact_digest", "") or "").strip()
    for label, value in (
        ("--candidate-id", candidate_id),
        ("--artifact-digest", artifact_digest),
    ):
        if _DIGEST_PATTERN.fullmatch(value) is None:
            blockers.append(f"{label} must be an immutable sha256 digest")
    display_version = str(getattr(args, "display_version", "") or "").strip()
    build_number = str(getattr(args, "build_number", "") or "").strip()
    phase = str(getattr(args, "phase", "") or "").strip()
    platform_record_id = str(
        getattr(args, "platform_record_id", "") or ""
    ).strip()
    if not display_version or not build_number:
        blockers.append("--display-version and --build-number are required")
    if phase not in allowed_phases:
        blockers.append(f"--phase must be one of: {', '.join(allowed_phases)}")
    if not platform_record_id:
        blockers.append(
            "--platform-record-id is required (redacted platform-side id)"
        )
    readback_evidence = str(
        getattr(args, "readback_evidence", "") or ""
    ).strip()
    evidence_path = Path(readback_evidence) if readback_evidence else None
    if evidence_path is None or not evidence_path.is_file():
        blockers.append(
            "--readback-evidence must point to the authoritative readback "
            "evidence file; distribution facts must not be fabricated"
        )
    if blockers:
        return {
            "exitCode": 2,
            "summary": f"store-distribution blocked for {channel_id or '?'}",
            "details": blockers,
        }

    declaration = channels.get(channel_id)
    if declaration is None:
        return {
            "exitCode": 2,
            "summary": f"unknown distribution channel: {channel_id}",
            "details": [f"declared channels: {', '.join(sorted(channels))}"],
        }
    row = _channel_row(channel_id, declaration)
    if row["status"] != "ready":
        return {
            "exitCode": 2,
            "summary": (
                f"distribution channel {channel_id} is GATE_BLOCK; "
                "distribution receipts must not be fabricated"
            ),
            "details": list(row["blockedReasons"]),
            "channel": row,
        }

    root = _receipt_root()
    existing = _existing_receipts(root)
    # fan-out 不变量：同一 candidate 的所有 android 渠道必须引用同一 APK。
    if row["platform"] == "android":
        conflicting = sorted(
            {
                str(receipt["channelId"])
                for receipt in existing
                if receipt.get("candidateId") == candidate_id
                and receipt.get("artifactDigest") != artifact_digest
                and str(
                    (channels.get(str(receipt.get("channelId"))) or {}).get(
                        "platform"
                    )
                )
                == "android"
            }
        )
        if conflicting:
            return {
                "exitCode": 2,
                "summary": (
                    "fan-out violation: android channels must reference one "
                    "reviewed release APK source digest per candidate"
                ),
                "details": [
                    f"candidate {candidate_id} already distributed with a "
                    f"different artifactDigest via: {', '.join(conflicting)}"
                ],
            }
    if phase != "uploaded" and not any(
        receipt.get("channelId") == channel_id
        and receipt.get("candidateId") == candidate_id
        and receipt.get("phase") == "uploaded"
        for receipt in existing
    ):
        return {
            "exitCode": 2,
            "summary": (
                f"phase={phase} requires an existing uploaded receipt for "
                f"{channel_id}/{candidate_id}"
            ),
            "details": [
                "the distribution state chain must trace back to one real "
                "upload; record phase=uploaded first"
            ],
        }

    receipt: dict[str, Any] = {
        "schema": "app-distribution-receipt",
        "channelId": channel_id,
        "candidateId": candidate_id,
        "artifactDigest": artifact_digest,
        "applicationId": row["applicationId"] or f"web.{channel_id}",
        "displayVersion": display_version,
        "buildNumber": build_number,
        "phase": phase,
        "platformRecordId": platform_record_id,
        "readbackMethod": row["readback"],
        "readbackDigest": _sha256_file(evidence_path),
        "recordedAt": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    required_fields = {str(field) for field in contract["required_fields"]}
    if set(receipt) != required_fields:
        return {
            "exitCode": 2,
            "summary": "distribution receipt fields drifted from metadata",
            "details": [
                f"missing={sorted(required_fields - set(receipt))}, "
                f"extra={sorted(set(receipt) - required_fields)}"
            ],
        }
    receipt_digest = (
        "sha256:" + hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    )
    receipt_path = (
        root / channel_id / (receipt_digest.removeprefix("sha256:") + ".json")
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.exists():
        return {
            "exitCode": 0,
            "summary": f"identical receipt already recorded for {channel_id}",
            "details": [str(receipt_path)],
            "receipt": receipt,
        }
    receipt_path.write_bytes(_canonical_bytes(receipt))
    return {
        "exitCode": 0,
        "summary": (
            f"distribution receipt recorded: {channel_id} {phase} "
            f"{display_version}+{build_number}"
        ),
        "details": [str(receipt_path)],
        "receipt": receipt,
        "receiptPath": str(receipt_path),
    }
