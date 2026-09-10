#!/usr/bin/env python3
"""Debug-nonprod 构建期自供给：签发 Alpha 离线文档并物化为可嵌入的激活请求。

iOS `Debug-nonprod` 与 Android debug/nonprod 的构建阶段在无外部 canonical handoff
时调用本脚本（spec: environment-topology-and-packaging REQ-003 build_time_self_supply）。
它不自持第二套逻辑：package/trust/manifest 全部经 `build_launcher_handoff.build_handoff`
与 `app_launch_manifest_contract.build_runtime_config_activation_request` 产出，与
canonical launcher 写入私有容器的请求同构；区别只在 `expectedActiveDigest` 留空，
由原生 gate 在冷启动以当前 active digest 作 CAS 前值。

输出两份文件（均须位于源码树外的调用方私有目录）：
- `--trust-output`：nonprod trust envelope（既有 embed 脚本消费）。
- `--request-output`：`runtime_config_activation_request`，嵌入制品 `qwq_runtime/`。
stdout 打印 JSON 摘要（digest 与 provenance），供构建日志与契约测试消费。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.dont_write_bytecode = True

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from build_launcher_handoff import APP_DIR, build_handoff  # noqa: E402
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (  # noqa: E402
    LaunchManifestContractError,
    build_runtime_config_activation_request,
    load_launch_manifest_contract,
    runtime_config_activation_request_digest,
)

SELF_SUPPLY_ENVIRONMENT = "alpha"
SELF_SUPPLY_TARGET = "alpha-local"
SELF_SUPPLY_LAUNCH_POLICY = "test_live"
SELF_SUPPLY_LAUNCH_PROVENANCE = "workspace_ide_debug"
SELF_SUPPLY_MODE = "build_time_self_supply"
SELF_SUPPLY_BUILD_PROFILE = "nonprod"
SELF_SUPPLY_REQUEST_FILE_NAME = "runtime-config-self-supply-request.json"


class SelfSupplyError(RuntimeError):
    """自供给材料无法签发；调用方以 trust blocker fail-closed。"""


def _outside_source_tree(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise SelfSupplyError(f"{label} must be an absolute path")
    resolved_parent = path.parent.resolve()
    repo_root = _REPO_ROOT.resolve()
    if resolved_parent == repo_root or repo_root in resolved_parent.parents:
        raise SelfSupplyError(f"{label} must stay outside the source tree")
    if not resolved_parent.is_dir() or resolved_parent.is_symlink():
        raise SelfSupplyError(f"{label} parent must be a regular directory")
    return path


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _handoff_arguments(trust_output: Path) -> SimpleNamespace:
    return SimpleNamespace(
        env=SELF_SUPPLY_ENVIRONMENT,
        target=SELF_SUPPLY_TARGET,
        launch_provenance=SELF_SUPPLY_LAUNCH_PROVENANCE,
        launch_policy=SELF_SUPPLY_LAUNCH_POLICY,
        gateway_base_url="",
        legal_base_url="",
        media_avatar_base_url="",
        media_image_base_url="",
        media_video_base_url="",
        media_upload_base_url="",
        rtc_media_connection_url="",
        source_git_sha="",
        source_tree_digest="",
        source_capsule_manifest="",
        transport_required=False,
        reverse_expected_ports="",
        reverse_actual_ports="",
        reverse_receipt_digest="",
        consumer_lease_id="",
        runtime_config_trust_output=str(trust_output),
        runtime_config_supply_mode=SELF_SUPPLY_MODE,
    )


def build_self_supply_request(
    *,
    trust_output: Path,
    request_output: Path,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_contract = contract or load_launch_manifest_contract()
    if SELF_SUPPLY_MODE not in selected_contract["runtime_config_supply_modes"]:
        raise SelfSupplyError(
            f"{SELF_SUPPLY_MODE} is absent from the canonical supply mode closed set"
        )
    trust_path = _outside_source_tree(trust_output, "self supply trust output")
    request_path = _outside_source_tree(request_output, "self supply request output")
    try:
        handoff = build_handoff(_handoff_arguments(trust_path))
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SelfSupplyError(f"canonical handoff issuance failed: {exc}") from exc
    if (handoff.get("buildProfile") != SELF_SUPPLY_BUILD_PROFILE
        or handoff.get("contentSource") != "bundled_snapshot"
        or handoff.get("requiresLocalTransport") is not False):
        raise SelfSupplyError("self supply must resolve to the nonprod offline document")
    request = build_runtime_config_activation_request(
        handoff, expected_active_digest="", contract=selected_contract
    )
    request_digest = runtime_config_activation_request_digest(request, selected_contract)
    _atomic_write(
        request_path,
        json.dumps(
            request, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8"),
    )
    return {
        "schema": "qwq.app-runtime-config-self-supply-summary",
        "runtimeConfigSupplyMode": SELF_SUPPLY_MODE,
        "launchProvenance": SELF_SUPPLY_LAUNCH_PROVENANCE,
        "environment": SELF_SUPPLY_ENVIRONMENT,
        "target": SELF_SUPPLY_TARGET,
        "buildProfile": SELF_SUPPLY_BUILD_PROFILE,
        "requestDigest": request_digest,
        "packageDigest": handoff["runtimeConfigPackageDigest"],
        "trustEnvelopeDigest": handoff["runtimeConfigTrustEnvelopeDigest"],
        "effectiveLaunchManifestDigest": handoff["effectiveLaunchManifestDigest"],
        "appDir": str(APP_DIR),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trust-output", required=True)
    parser.add_argument("--request-output", required=True)
    arguments = parser.parse_args(argv[1:])
    try:
        summary = build_self_supply_request(
            trust_output=Path(arguments.trust_output).expanduser(),
            request_output=Path(arguments.request_output).expanduser(),
        )
    except (SelfSupplyError, LaunchManifestContractError, ValueError) as exc:
        print(f"GATE_BLOCK: APP.LAUNCH.runtime_config_trust_missing: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
