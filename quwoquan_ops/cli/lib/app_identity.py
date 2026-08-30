"""BuildProfile × BuildMode 的 App 包身份推导。

唯一真相源是 canonical metadata `app_artifact_manifest.yaml` 的
`build_profiles` 与 `application_identity`；运行环境先映射到信任域 profile，
再推导原生身份，禁止任何消费者复制 environment→profile 映射。
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
    """一个 (platform, buildProfile, buildMode) 组合的完整包身份。"""

    platform: str
    build_profile: str
    build_mode: str
    application_id: str
    display_name: str
    # Prod 正式 ID 是否已取得已登记外部事实；False 时 store 渠道必须阻断。
    registered: bool


@dataclass(frozen=True)
class AppBuildProduct:
    """canonical App Pipeline 基线产品声明。"""

    build_product_id: str
    platform: str
    build_profile: str
    build_mode: str
    artifact_format: str
    distribution_class: str


@lru_cache(maxsize=1)
def _artifact_contract() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    if not isinstance(document, dict):
        raise AppIdentityError(f"invalid artifact metadata: {ARTIFACT_METADATA_PATH}")
    identity = document.get("application_identity")
    profiles = document.get("build_profiles")
    build_products = document.get("build_products")
    distribution_classes = document.get("distribution_classes")
    environments = document.get("environments")
    web_application_id = document.get("web_application_id")
    if not isinstance(identity, dict):
        raise AppIdentityError("application_identity section is missing")
    if not isinstance(profiles, dict) or not profiles:
        raise AppIdentityError("build_profiles section is missing")
    if not isinstance(build_products, dict) or not build_products:
        raise AppIdentityError("build_products section is missing")
    if not isinstance(distribution_classes, dict) or not distribution_classes:
        raise AppIdentityError("distribution_classes section is missing")
    if not isinstance(environments, list) or not environments:
        raise AppIdentityError("environments metadata is missing")
    if not isinstance(web_application_id, str) or not web_application_id.strip():
        raise AppIdentityError("web_application_id metadata is missing")
    for key in (
        "display_name_base",
        "base_application_ids",
        "build_profile_suffixes",
        "build_profile_display_marks",
        "build_mode_suffixes",
        "build_mode_display_marks",
    ):
        if key not in identity:
            raise AppIdentityError(f"application_identity.{key} is missing")

    canonical_environments = tuple(str(value) for value in environments)
    environment_profiles: dict[str, str] = {}
    normalized_profiles: dict[str, dict[str, Any]] = {}
    for build_profile, declaration in profiles.items():
        if not isinstance(declaration, dict):
            raise AppIdentityError(
                f"build_profiles.{build_profile} must be a mapping"
            )
        profile_environments = declaration.get("environments")
        launch_policy = declaration.get("launch_policy")
        if not isinstance(profile_environments, list) or not profile_environments:
            raise AppIdentityError(
                f"build_profiles.{build_profile}.environments is missing"
            )
        if not isinstance(launch_policy, str) or not launch_policy.strip():
            raise AppIdentityError(
                f"build_profiles.{build_profile}.launch_policy is missing"
            )
        normalized_profiles[str(build_profile)] = declaration
        for environment in profile_environments:
            name = str(environment)
            if name not in canonical_environments:
                raise AppIdentityError(
                    f"build_profiles.{build_profile} references unknown environment {name!r}"
                )
            if name in environment_profiles:
                raise AppIdentityError(
                    f"environment {name!r} belongs to multiple build profiles"
                )
            environment_profiles[name] = str(build_profile)
    if set(environment_profiles) != set(canonical_environments):
        raise AppIdentityError(
            "build_profiles must own every canonical environment exactly once"
        )
    if set(identity["build_profile_suffixes"]) != set(normalized_profiles):
        raise AppIdentityError(
            "application_identity.build_profile_suffixes must match build_profiles"
        )
    if set(identity["build_profile_display_marks"]) != set(normalized_profiles):
        raise AppIdentityError(
            "application_identity.build_profile_display_marks must match build_profiles"
        )

    known_distribution_classes = set(distribution_classes)
    normalized_products: dict[str, dict[str, str]] = {}
    required_product_fields = (
        "platform",
        "build_profile",
        "build_mode",
        "artifact_format",
        "distribution_class",
    )
    for product_id, raw_product in build_products.items():
        if not isinstance(product_id, str) or not product_id.strip():
            raise AppIdentityError("build_products keys must be non-empty strings")
        if not isinstance(raw_product, dict):
            raise AppIdentityError(f"build_products.{product_id} must be an object")
        product: dict[str, str] = {}
        for field in required_product_fields:
            value = raw_product.get(field)
            if not isinstance(value, str) or not value.strip():
                raise AppIdentityError(
                    f"build_products.{product_id}.{field} must be a non-empty string"
                )
            product[field] = value.strip()
        profile = product["build_profile"]
        if profile != "shared" and profile not in normalized_profiles:
            raise AppIdentityError(
                f"build_products.{product_id}.build_profile references unknown profile {profile!r}"
            )
        if product["distribution_class"] not in known_distribution_classes:
            raise AppIdentityError(
                f"build_products.{product_id}.distribution_class is not canonical"
            )
        normalized_products[product_id.strip()] = product

    return {
        "identity": identity,
        "profiles": normalized_profiles,
        "build_products": normalized_products,
        "environments": canonical_environments,
        "environment_profiles": environment_profiles,
        "web_application_id": web_application_id.strip(),
    }


def _identity_contract() -> dict[str, Any]:
    return _artifact_contract()["identity"]


def supported_identity_platforms() -> tuple[str, ...]:
    return tuple(sorted(_identity_contract()["base_application_ids"]))


def supported_environments() -> tuple[str, ...]:
    return _artifact_contract()["environments"]


def supported_build_products() -> tuple[AppBuildProduct, ...]:
    """返回 metadata 顺序稳定的 App build product 基线。"""

    products = _artifact_contract()["build_products"]
    return tuple(
        AppBuildProduct(
            build_product_id=product_id,
            platform=product["platform"],
            build_profile=product["build_profile"],
            build_mode=product["build_mode"],
            artifact_format=product["artifact_format"],
            distribution_class=product["distribution_class"],
        )
        for product_id, product in products.items()
    )


def resolve_build_product(build_product_id: str) -> AppBuildProduct:
    """按 canonical product ID 解析一个基线产品。"""

    normalized = build_product_id.strip()
    for product in supported_build_products():
        if product.build_product_id == normalized:
            return product
    raise AppIdentityError(f"unsupported build product: {build_product_id}")


def build_product_for(
    *,
    platform: str,
    build_profile: str,
    artifact_format: str | None = None,
) -> AppBuildProduct:
    """按平台、信任域和可选格式解析唯一基线产品。"""

    matches = [
        product
        for product in supported_build_products()
        if product.platform == platform
        and product.build_profile == build_profile
        and (artifact_format is None or product.artifact_format == artifact_format)
    ]
    if len(matches) != 1:
        raise AppIdentityError(
            "build product must resolve uniquely for "
            f"platform={platform}, build_profile={build_profile}, "
            f"artifact_format={artifact_format}"
        )
    return matches[0]


def application_id_for_build_product(build_product_id: str) -> str:
    """返回产品稳定应用身份；Web 使用独立 canonical ID。"""

    product = resolve_build_product(build_product_id)
    if product.platform == "web":
        return _artifact_contract()["web_application_id"]
    return resolve_app_identity(
        platform=product.platform,
        build_profile=product.build_profile,
        build_mode=product.build_mode,
    ).application_id


def supported_build_profiles() -> tuple[str, ...]:
    return tuple(sorted(_artifact_contract()["profiles"]))


def supported_build_modes() -> tuple[str, ...]:
    return tuple(_identity_contract()["build_mode_suffixes"])


def build_profile_for_environment(environment: str) -> str:
    profile = _artifact_contract()["environment_profiles"].get(environment)
    if profile is None:
        raise AppIdentityError(f"unsupported environment: {environment!r}")
    return str(profile)


def allowed_environments_for_build_profile(build_profile: str) -> tuple[str, ...]:
    declaration = _artifact_contract()["profiles"].get(build_profile)
    if not isinstance(declaration, dict):
        raise AppIdentityError(f"unsupported build profile: {build_profile!r}")
    environments = declaration.get("environments")
    if not isinstance(environments, list) or not environments:
        raise AppIdentityError(
            f"build_profiles.{build_profile}.environments is missing"
        )
    return tuple(str(value) for value in environments)


def launch_policy_for_build_profile(build_profile: str) -> str:
    declaration = _artifact_contract()["profiles"].get(build_profile)
    if not isinstance(declaration, dict):
        raise AppIdentityError(f"unsupported build profile: {build_profile!r}")
    policy = declaration.get("launch_policy")
    if not isinstance(policy, str) or not policy.strip():
        raise AppIdentityError(f"build_profiles.{build_profile}.launch_policy is missing")
    return policy.strip()


def resolve_app_identity(
    *,
    platform: str,
    build_mode: str,
    environment: str | None = None,
    build_profile: str | None = None,
) -> AppIdentity:
    """按 canonical 规则推导包身份；环境与 profile 冲突时 fail closed。"""

    if environment is None and build_profile is None:
        raise AppIdentityError("environment or build_profile is required")
    resolved_profile = build_profile
    if environment is not None:
        environment_profile = build_profile_for_environment(environment)
        if resolved_profile is not None and resolved_profile != environment_profile:
            raise AppIdentityError(
                "environment/build profile mismatch: "
                f"environment={environment!r} build_profile={resolved_profile!r}"
            )
        resolved_profile = environment_profile
    if resolved_profile not in supported_build_profiles():
        raise AppIdentityError(f"unsupported build profile: {resolved_profile!r}")

    contract = _identity_contract()
    bases = contract["base_application_ids"]
    if platform not in bases:
        raise AppIdentityError(f"unsupported identity platform: {platform!r}")
    mode_suffixes = contract["build_mode_suffixes"]
    if build_mode not in mode_suffixes:
        raise AppIdentityError(f"unsupported build mode: {build_mode!r}")

    base = bases[platform]
    base_id = base.get("value") if isinstance(base, dict) else None
    registered = bool(base.get("registered")) if isinstance(base, dict) else False
    if not isinstance(base_id, str) or not base_id:
        raise AppIdentityError(f"base application id missing for {platform!r}")

    profile_suffixes = contract["build_profile_suffixes"]
    profile_marks = contract["build_profile_display_marks"]
    application_id = (
        f"{base_id}{profile_suffixes[resolved_profile]}{mode_suffixes[build_mode]}"
    )
    display_name = (
        f"{contract['display_name_base']}"
        f"{profile_marks[resolved_profile]}"
        f"{contract['build_mode_display_marks'][build_mode]}"
    )
    return AppIdentity(
        platform=platform,
        build_profile=resolved_profile,
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
