"""stackctl `package --kind app-artifact`：App 制品身份与渠道边界的 canonical 入口。

deliver-deploy-prod-pipeline DEC-004：打包/安装单轨显式接收
env / platform / build-mode / distribution-class / device，按 canonical metadata
`app_artifact_manifest.yaml` 裁决合法性并推导包身份：

- (distributionClass, buildMode) 组合必须满足 distribution_classes 声明；
  真 Debug 只允许 dev_direct / simulator / registered_device。
- applicationId / 显示名由 application_identity 映射推导，四环境 ×
  BuildMode 互不覆盖。
- store 渠道要求平台 Prod 正式 ID 已登记外部事实（registered=true），
  否则 GATE_BLOCK（由 OPEN 承接，不得用占位 ID 上架）。
- registered_device 分发必须显式给出 --device。

提供 --artifact-path 时计算制品 sha256 并把身份裁决写入
`<package_dir>/app_artifact_identity.json`，供后续签名校验、安装与
install receipt 绑定消费。
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

# 需要真实设备身份才能形成 install receipt 的分发类。
_DEVICE_BOUND_CLASSES = frozenset({"registered_device"})
# 身份映射当前只拥有可安装双端；web/macos 制品身份由各自 release 工具拥有。
_IDENTITY_PLATFORMS = frozenset({"android", "ios"})


def _distribution_classes() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    classes = document.get("distribution_classes")
    if not isinstance(classes, dict) or not classes:
        raise AppIdentityError("distribution_classes metadata is missing")
    return classes


def command_package_app_artifact(args: argparse.Namespace) -> dict[str, Any]:
    env_name = str(getattr(args, "env", "") or "").strip()
    platform = str(getattr(args, "app_platform", "") or "").strip()
    build_mode = str(getattr(args, "app_build_mode", "") or "").strip()
    distribution_class = str(getattr(args, "distribution_class", "") or "").strip()
    device = str(getattr(args, "device", "") or "").strip()
    artifact_path = str(getattr(args, "artifact_path", "") or "").strip()

    blockers: list[str] = []
    if platform not in _IDENTITY_PLATFORMS:
        blockers.append(
            "--app-platform must be android|ios for installable app artifacts"
        )
    classes = _distribution_classes()
    declaration = classes.get(distribution_class)
    if not isinstance(declaration, dict):
        blockers.append(
            f"--distribution-class must be one of: {', '.join(sorted(classes))}"
        )
        declaration = None
    if declaration is not None and build_mode not in (
        declaration.get("build_modes") or []
    ):
        blockers.append(
            f"buildMode={build_mode} is not allowed for "
            f"distributionClass={distribution_class}; true Debug artifacts are "
            "limited to dev_direct/simulator/registered_device"
        )
    if distribution_class in _DEVICE_BOUND_CLASSES and not device:
        blockers.append(
            "--device is required for registered_device distribution"
        )

    identity = None
    if platform in _IDENTITY_PLATFORMS:
        try:
            identity = resolve_app_identity(
                platform=platform, environment=env_name, build_mode=build_mode
            )
        except AppIdentityError as error:
            blockers.append(str(error))
    if (
        identity is not None
        and distribution_class == "store"
        and not identity.registered
    ):
        blockers.append(
            f"{platform} store distribution requires a registered production "
            "application id; the current base id is not a registered external "
            "fact (tracked as OPEN), refusing a placeholder store upload"
        )

    promotable = (
        bool(declaration.get("promotable"))
        and build_mode == "release"
        and not blockers
        if declaration is not None
        else False
    )
    decision: dict[str, Any] = {
        "schema": "app-artifact-identity-decision",
        "environment": env_name,
        "platform": platform,
        "buildMode": build_mode,
        "distributionClass": distribution_class,
        "device": device,
        "applicationId": identity.application_id if identity else "",
        "displayName": identity.display_name if identity else "",
        "promotable": promotable,
        "blockers": blockers,
    }

    if blockers:
        return {
            "exitCode": 2,
            "summary": (
                f"stackctl app artifact identity blocked for {env_name}/"
                f"{platform}/{build_mode}/{distribution_class}"
            ),
            "details": blockers,
            "decision": decision,
        }

    details = [
        f"applicationId: {decision['applicationId']}",
        f"displayName: {decision['displayName']}",
        f"promotable: {decision['promotable']}",
    ]
    if artifact_path:
        artifact = Path(artifact_path)
        if not artifact.is_file():
            return {
                "exitCode": 2,
                "summary": f"stackctl app artifact identity blocked for {env_name}",
                "details": [f"--artifact-path does not exist: {artifact}"],
                "decision": decision,
            }
        digest = hashlib.sha256()
        with artifact.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        decision["artifactDigest"] = f"sha256:{digest.hexdigest()}"
        import quwoquan_ops.cli.stackctl as _stackctl

        target_name = str(getattr(args, "target", "") or "").strip() or (
            _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
        )
        package_dir = _stackctl.app_deployment_package_dir(
            env_name, target=target_name
        )
        package_dir.mkdir(parents=True, exist_ok=True)
        identity_path = package_dir / "app_artifact_identity.json"
        identity_path.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        details.append(f"artifactDigest: {decision['artifactDigest']}")
        details.append(f"identity: {identity_path}")

    return {
        "exitCode": 0,
        "summary": (
            f"stackctl app artifact identity resolved for {env_name}/"
            f"{platform}/{build_mode}/{distribution_class}"
        ),
        "details": details,
        "decision": decision,
    }
