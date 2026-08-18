"""四环境 × BuildMode 的 App 包身份推导（deliver-deploy-prod-pipeline DEC-004）。

唯一真相源是 canonical metadata `app_artifact_manifest.yaml` 的
`application_identity` 段；本模块只做纯函数推导，供 stackctl、巡检脚本与
local_contract 测试共同消费，禁止任何脚本再自持 applicationId 字面值。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402

ARTIFACT_METADATA_PATH = (
    _ROOT / "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
)


class AppIdentityError(ValueError):
    """application_identity metadata 缺失或不合法。"""


@dataclass(frozen=True)
class AppIdentity:
    """一个 (platform, environment, buildMode) 组合的完整包身份。"""

    platform: str
    environment: str
    build_mode: str
    application_id: str
    display_name: str
    # Prod 正式 ID 是否已取得已登记外部事实；False 时 store 渠道必须阻断。
    registered: bool


@lru_cache(maxsize=1)
def _identity_contract() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    if not isinstance(document, dict):
        raise AppIdentityError(f"invalid artifact metadata: {ARTIFACT_METADATA_PATH}")
    contract = document.get("application_identity")
    if not isinstance(contract, dict):
        raise AppIdentityError("application_identity section is missing")
    for key in (
        "display_name_base",
        "base_application_ids",
        "environment_suffixes",
        "environment_display_marks",
        "build_mode_suffixes",
        "build_mode_display_marks",
    ):
        if key not in contract:
            raise AppIdentityError(f"application_identity.{key} is missing")
    return contract


def supported_identity_platforms() -> tuple[str, ...]:
    return tuple(sorted(_identity_contract()["base_application_ids"]))


def supported_environments() -> tuple[str, ...]:
    return tuple(_identity_contract()["environment_suffixes"])


def supported_build_modes() -> tuple[str, ...]:
    return tuple(_identity_contract()["build_mode_suffixes"])


def resolve_app_identity(
    *,
    platform: str,
    environment: str,
    build_mode: str,
) -> AppIdentity:
    """按 canonical 规则推导包身份；未知维度值一律失败，不猜测。"""

    contract = _identity_contract()
    bases = contract["base_application_ids"]
    if platform not in bases:
        raise AppIdentityError(f"unsupported identity platform: {platform!r}")
    env_suffixes = contract["environment_suffixes"]
    if environment not in env_suffixes:
        raise AppIdentityError(f"unsupported environment: {environment!r}")
    mode_suffixes = contract["build_mode_suffixes"]
    if build_mode not in mode_suffixes:
        raise AppIdentityError(f"unsupported build mode: {build_mode!r}")

    base = bases[platform]
    base_id = base.get("value") if isinstance(base, dict) else None
    registered = bool(base.get("registered")) if isinstance(base, dict) else False
    if not isinstance(base_id, str) or not base_id:
        raise AppIdentityError(f"base application id missing for {platform!r}")

    application_id = (
        f"{base_id}{env_suffixes[environment]}{mode_suffixes[build_mode]}"
    )
    display_name = (
        f"{contract['display_name_base']}"
        f"{contract['environment_display_marks'][environment]}"
        f"{contract['build_mode_display_marks'][build_mode]}"
    )
    return AppIdentity(
        platform=platform,
        environment=environment,
        build_mode=build_mode,
        application_id=application_id,
        display_name=display_name,
        registered=registered,
    )


def application_id_for(platform: str, environment: str, build_mode: str) -> str:
    return resolve_app_identity(
        platform=platform, environment=environment, build_mode=build_mode
    ).application_id


@dataclass(frozen=True)
class InstallLaunchPath:
    """一条有效安装启动路径（矩阵成员，由 canonical metadata 推导）。"""

    environment: str
    platform: str
    build_mode: str
    distribution_class: str
    launch_provenance: str
    promotable: bool


def enumerate_valid_install_launch_paths() -> tuple[InstallLaunchPath, ...]:
    """推导所有有效安装启动路径。

    矩阵 = environments × distribution_classes 各自声明的
    platforms × build_modes × launch_provenances；消费方（UAT 计划、
    准出矩阵、评审证据）只消费本推导，不得自持第二份组合表。
    """
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    environments = document.get("environments")
    classes = document.get("distribution_classes")
    provenances = set(document.get("launch_provenances") or [])
    if not isinstance(environments, list) or not environments:
        raise AppIdentityError("environments metadata is missing")
    if not isinstance(classes, dict) or not classes:
        raise AppIdentityError("distribution_classes metadata is missing")
    if not provenances:
        raise AppIdentityError("launch_provenances metadata is missing")

    paths: list[InstallLaunchPath] = []
    for class_name, declaration in classes.items():
        if not isinstance(declaration, dict):
            raise AppIdentityError(
                f"distribution class {class_name} declaration must be a mapping"
            )
        class_platforms = declaration.get("platforms")
        class_modes = declaration.get("build_modes")
        class_provenances = declaration.get("launch_provenances")
        if not class_platforms or not class_modes or not class_provenances:
            raise AppIdentityError(
                f"distribution class {class_name} must declare platforms, "
                "build_modes and launch_provenances"
            )
        unknown = set(class_provenances) - provenances
        if unknown:
            raise AppIdentityError(
                f"distribution class {class_name} declares unknown launch "
                f"provenances: {', '.join(sorted(unknown))}"
            )
        for environment in environments:
            for platform in class_platforms:
                for build_mode in class_modes:
                    for provenance in class_provenances:
                        paths.append(
                            InstallLaunchPath(
                                environment=str(environment),
                                platform=str(platform),
                                build_mode=str(build_mode),
                                distribution_class=str(class_name),
                                launch_provenance=str(provenance),
                                promotable=bool(declaration.get("promotable"))
                                and str(build_mode) == "release",
                            )
                        )
    return tuple(paths)
