"""消费 canonical metadata 派生的 App 包身份矩阵。

Release 按信任域，Debug/Profile 按明确环境；只读取 codegen 投影并校验
当前 authoring/输出摘要，不复制生成器的身份拼接算法或环境映射。
"""

from __future__ import annotations

import sys
import hashlib
import json
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
    environment: str | None = None
    promotable: bool = False

    @property
    def flavor(self) -> str:
        return self.environment if self.environment is not None else self.build_profile

    @property
    def configuration(self) -> str:
        return f"{self.build_mode.title()}-{self.flavor}"


@dataclass(frozen=True)
class AppBuildProduct:
    """canonical App Pipeline 基线产品声明。"""

    build_product_id: str
    platform: str
    build_profile: str
    build_mode: str
    artifact_format: str
    distribution_class: str
    android_runtime: str | None


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
    # 包身份只读 canonical codegen 投影，不在 Python 复制 Go 生成器的 suffix 算法。
    projection_path = _ROOT / "quwoquan_app/android/app/app_identity.generated.json"
    try:
        projection_bytes = projection_path.read_bytes()
        projection = json.loads(projection_bytes)
        manifest = json.loads((_ROOT / "quwoquan_app/tool/app_identity_codegen/generated_manifest.json").read_bytes())
    except (OSError, ValueError) as error:
        raise AppIdentityError("canonical App identity projection is unavailable") from error
    source_digest = "sha256:" + hashlib.sha256(ARTIFACT_METADATA_PATH.read_bytes()).hexdigest()
    outputs = [item for item in manifest.get("outputs", [])
               if item.get("path") == "android/app/app_identity.generated.json"]
    if (manifest.get("sourceSha256") != source_digest or len(outputs) != 1
            or outputs[0].get("sha256") != "sha256:" + hashlib.sha256(projection_bytes).hexdigest()):
        raise AppIdentityError("canonical App identity projection digest mismatch")
    if (projection.get("schema") != "qwq.app-identity-generated"
            or projection.get("source") != "_shared/app_artifact_manifest.yaml"
            or projection.get("sourceSha256") != source_digest):
        raise AppIdentityError("canonical App identity projection is stale or invalid")

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
    if (projection.get("environmentProfiles") != environment_profiles
            or set(projection.get("buildProfiles", [])) != set(normalized_profiles)):
        raise AppIdentityError("canonical App identity projection profile mapping mismatch")

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
        runtime_profile = raw_product.get("android_runtime")
        if product["platform"] == "android":
            if runtime_profile != "aosp_no_gms":
                raise AppIdentityError(
                    f"build_products.{product_id}.android_runtime must be aosp_no_gms"
                )
            product["android_runtime"] = str(runtime_profile)
        elif runtime_profile is not None:
            raise AppIdentityError(
                f"build_products.{product_id}.android_runtime is Android-only"
            )
        normalized_products[product_id.strip()] = product

    return {
        "identity": identity,
        "projection": projection,
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
            android_runtime=product.get("android_runtime"),
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
    return tuple(_artifact_contract()["projection"]["buildModes"])


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

    if build_mode != "release" and environment is None:
        raise AppIdentityError("Debug/Profile identity requires explicit environment")
    selector = resolved_profile if build_mode == "release" else environment
    projection = _artifact_contract()["projection"]
    value = projection.get("identities", {}).get(platform, {}).get(f"{selector}/{build_mode}")
    if not isinstance(value, dict):
        raise AppIdentityError(f"unsupported App identity: {platform}/{selector}/{build_mode}")
    if (value.get("buildProfile") != resolved_profile
            or value.get("buildMode") != build_mode
            or value.get("environment") != (None if build_mode == "release" else environment)):
        raise AppIdentityError("canonical App identity dimensions mismatch")
    return AppIdentity(
        platform=platform, build_profile=resolved_profile, build_mode=build_mode,
        application_id=value["applicationId"], display_name=value["displayName"],
        registered=value["registered"], environment=value.get("environment"),
        promotable=value["promotable"],
    )


def resolve_ios_configuration(configuration: str) -> AppIdentity:
    """配置名只接受 canonical 投影中的身份，不提供旧配置别名。"""
    for key, value in _artifact_contract()["projection"]["identities"]["ios"].items():
        selector, mode = key.split("/")
        if configuration == f"{mode.title()}-{selector}":
            return resolve_app_identity(platform="ios", build_mode=mode,
                                        build_profile=value["buildProfile"],
                                        environment=value.get("environment"))
    raise AppIdentityError(f"unsupported iOS configuration: {configuration!r}")


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
