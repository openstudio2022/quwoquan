"""FilterCatalogRelease canonical artifact、派生副本与环境输入。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from content.filter_catalog.codec import (
    canonical_json_bytes,
    load_json_decimal,
    pretty_json_text,
)
from content.filter_catalog.contract import (
    ADJUSTMENT_FIELD_NAMES,
    CatalogContractError,
    canonical_digest_for_payload,
    normalize_release,
)


ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
CATALOG_ROOT_REF = Path("quwoquan_data/reference/filter_catalog")
BINDING_REF = CATALOG_ROOT_REF / "bootstrap_binding.json"
DIGEST_VECTOR_REF = CATALOG_ROOT_REF / "digest_test_vector.json"
APP_BOOTSTRAP_REF = Path("quwoquan_app/assets/filters/filter_presets.json")
METADATA_OBJECT_REF = Path(
    "quwoquan_service/services/content-service/contracts/media/filter_catalog_release"
)
OBJECT_ID = "content.filter_catalog_release"
REQUIRED_OPERATION_NAMES = {
    "stage": "StageFilterCatalogRelease",
    "activate": "ActivateFilterCatalogRelease",
    "rollback": "RollbackFilterCatalogRelease",
    "read": "GetActiveFilterCatalog",
}


@dataclass(frozen=True)
class CatalogLayout:
    repo_root: Path
    release_id: str

    @property
    def release_ref(self) -> Path:
        return (
            CATALOG_ROOT_REF
            / "releases"
            / self.release_id
            / "filter_catalog_release.json"
        )

    @property
    def release_path(self) -> Path:
        return self.repo_root / self.release_ref

    def environment_ref(self, environment: str) -> Path:
        return (
            self.release_ref.parent
            / "environments"
            / f"{environment}.import.json"
        )

    def environment_path(self, environment: str) -> Path:
        return self.repo_root / self.environment_ref(environment)


def materialize_release(
    *,
    repo_root: Path,
    release_id: str,
) -> dict[str, object]:
    """从 canonical release 生成 App bootstrap 与四环境输入。"""
    layout = CatalogLayout(repo_root=repo_root, release_id=release_id)
    _assert_metadata_contract(repo_root)
    release = _load_release(layout.release_path)
    operations = _metadata_operations(repo_root)
    bootstrap = _bootstrap_payload(release)
    environment_manifests = {
        environment: _environment_manifest(
            layout=layout,
            release=release,
            environment=environment,
            operations=operations,
        )
        for environment in ENVIRONMENTS
    }
    binding = _binding_payload(layout)
    vector = digest_test_vector()

    _write_json_atomic(repo_root / APP_BOOTSTRAP_REF, bootstrap)
    for environment, manifest in environment_manifests.items():
        _write_json_atomic(layout.environment_path(environment), manifest)
    _write_json_atomic(repo_root / BINDING_REF, binding)
    _write_json_atomic(repo_root / DIGEST_VECTOR_REF, vector)
    report = validate_repository(repo_root)
    if not report["passed"]:
        raise CatalogContractError(
            "materialize 后校验失败：" + "; ".join(report["issues"])
        )
    return report


def validate_repository(repo_root: Path) -> dict[str, object]:
    issues: list[str] = []
    stats: dict[str, object] = {}
    try:
        stats = _validate_repository(repo_root)
    except (
        CatalogContractError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        yaml.YAMLError,
    ) as exc:
        issues.append(str(exc))
    return {
        "schema": "quwoquan_data.filter_catalog_validation",
        "passed": not issues,
        "issues": issues,
        "stats": stats,
    }


def digest_test_vector() -> dict[str, object]:
    zero = {name: Decimal(0) for name in ADJUSTMENT_FIELD_NAMES}
    cinema = dict(zero)
    cinema["temperature"] = Decimal("-12.5")
    cinema["contrast"] = Decimal("8.25")
    cinema["grain"] = Decimal("0.0000001")
    cinema["fade"] = Decimal("-0.000")
    categories = [
        {
            "categoryId": "camera_photo",
            "displayNameZhHans": "拍照",
            "displayNameEn": None,
            "sort": 1,
            "enabled": True,
        }
    ]
    presets = [
        {
            "presetId": "original",
            "categoryId": "camera_photo",
            "displayNameZhHans": "原图",
            "displayNameEn": None,
            "sort": 1,
            "enabled": True,
            "defaultStrength": Decimal(0),
            "adjustments": zero,
        },
        {
            "presetId": "cinema",
            "categoryId": "camera_photo",
            "displayNameZhHans": "电影",
            "displayNameEn": "Cinema",
            "sort": 2,
            "enabled": True,
            "defaultStrength": Decimal("80.500"),
            "adjustments": cinema,
        },
    ]
    payload = {
        "categories": categories,
        "presets": presets,
        "recommendedFallbackPresetIds": ["cinema"],
    }
    canonical_json = canonical_json_bytes(payload).decode("utf-8")
    digest = canonical_digest_for_payload(
        categories=categories,
        presets=presets,
        recommended_fallback_preset_ids=["cinema"],
    )
    return {
        "algorithm": "sha256:qwq-filter-catalog-canonical-json",
        "canonicalPayload": payload,
        "canonicalJsonUtf8": canonical_json,
        "sha256": digest,
    }


def _validate_repository(repo_root: Path) -> dict[str, object]:
    _assert_metadata_contract(repo_root)
    binding_path = repo_root / BINDING_REF
    binding = _load_mapping(binding_path)
    expected_binding_keys = {
        "schema",
        "canonicalArtifactRef",
        "bootstrapReplicaRef",
        "environmentManifestRefs",
    }
    _require_exact_keys(binding, expected_binding_keys, str(BINDING_REF))
    if binding["schema"] != "quwoquan_data.filter_catalog_bootstrap_binding":
        raise CatalogContractError("bootstrap binding schema 非法")

    release_ref = _ref_value(
        binding["canonicalArtifactRef"],
        "canonicalArtifactRef",
    )
    release_path = _resolve_repo_ref(repo_root, release_ref)
    release_id = release_path.parent.name
    layout = CatalogLayout(repo_root=repo_root, release_id=release_id)
    if release_ref != layout.release_ref.as_posix():
        raise CatalogContractError(
            f"canonicalArtifactRef 不在标准 release 路径：{release_ref}"
        )
    release = _load_release(release_path)

    bootstrap_ref = _ref_value(
        binding["bootstrapReplicaRef"],
        "bootstrapReplicaRef",
    )
    if bootstrap_ref != APP_BOOTSTRAP_REF.as_posix():
        raise CatalogContractError("bootstrapReplicaRef 必须指向唯一 App asset")
    bootstrap = _load_mapping(_resolve_repo_ref(repo_root, bootstrap_ref))
    _require_same_payload(
        bootstrap,
        _bootstrap_payload(release),
        "App bootstrap replica 与 canonical release 不同源",
    )

    environment_refs = binding["environmentManifestRefs"]
    if not isinstance(environment_refs, dict):
        raise CatalogContractError("environmentManifestRefs 必须为 object")
    if set(environment_refs) != set(ENVIRONMENTS):
        raise CatalogContractError(
            "environmentManifestRefs 必须完整覆盖 alpha/beta/gamma/prod"
        )
    operations = _metadata_operations(repo_root)
    for environment in ENVIRONMENTS:
        manifest_ref = _ref_value(
            environment_refs[environment],
            f"environmentManifestRefs.{environment}",
        )
        if manifest_ref != layout.environment_ref(environment).as_posix():
            raise CatalogContractError(
                f"{environment} environment manifest 路径不规范"
            )
        actual = _load_mapping(_resolve_repo_ref(repo_root, manifest_ref))
        expected = _environment_manifest(
            layout=layout,
            release=release,
            environment=environment,
            operations=operations,
        )
        _require_same_payload(
            actual,
            expected,
            f"{environment} environment manifest 与 canonical release 漂移",
        )

    vector = _load_mapping(repo_root / DIGEST_VECTOR_REF)
    _require_same_payload(
        vector,
        digest_test_vector(),
        "digest test vector 漂移",
    )
    if (
        vector["canonicalJsonUtf8"]
        != canonical_json_bytes(vector["canonicalPayload"]).decode("utf-8")
    ):
        raise CatalogContractError("digest test vector canonicalJsonUtf8 漂移")
    vector_payload = vector["canonicalPayload"]
    if not isinstance(vector_payload, dict):
        raise CatalogContractError("digest test vector payload 非法")
    vector_digest = canonical_digest_for_payload(
        categories=vector_payload["categories"],
        presets=vector_payload["presets"],
        recommended_fallback_preset_ids=vector_payload[
            "recommendedFallbackPresetIds"
        ],
    )
    if vector_digest != vector["sha256"]:
        raise CatalogContractError("digest test vector SHA-256 不匹配")

    return {
        "releaseId": release["releaseId"],
        "canonicalDigest": release["canonicalDigest"],
        "sourceOwner": release["sourceOwner"],
        "categoryCount": len(release["categories"]),
        "presetCount": len(release["presets"]),
        "environmentCount": len(ENVIRONMENTS),
        "adjustmentFieldCount": len(ADJUSTMENT_FIELD_NAMES),
    }


def _bootstrap_payload(release: dict[str, object]) -> dict[str, object]:
    categories = release["categories"]
    presets = release["presets"]
    if not isinstance(categories, list) or not isinstance(presets, list):
        raise CatalogContractError("normalized release members 非法")
    return {
        "releaseId": release["releaseId"],
        "canonicalDigest": release["canonicalDigest"],
        # bootstrap 是 canonical release 的可验证只读复制品，不是 UI 私有 DTO。
        # 保留完整字段才能让 App 以同一算法重算 canonicalDigest；禁止降格为
        # id/label/name 或删掉 displayNameEn 后再依赖仓库门禁“代替运行时校验”。
        "categories": categories,
        "presets": presets,
        "recommendedFallbackPresetIds": release[
            "recommendedFallbackPresetIds"
        ],
    }


def _environment_manifest(
    *,
    layout: CatalogLayout,
    release: dict[str, object],
    environment: str,
    operations: dict[str, str],
) -> dict[str, object]:
    if environment not in ENVIRONMENTS:
        raise CatalogContractError(f"未知 environment：{environment}")
    return {
        "schema": "quwoquan_data.filter_catalog_environment_import",
        "environment": environment,
        "deliveryMode": "immutable_release",
        "canonicalArtifactRef": layout.release_ref.as_posix(),
        "releaseId": release["releaseId"],
        "sourceOwner": release["sourceOwner"],
        "canonicalDigest": release["canonicalDigest"],
        "expectedCategoryCount": len(release["categories"]),
        "expectedPresetCount": len(release["presets"]),
        "idempotencyKey": f"filter-catalog:{release['canonicalDigest']}",
        "operations": operations,
        "activationPolicy": (
            "stage_then_gray_activate"
            if environment == "prod"
            else "stage_then_activate"
        ),
    }


def _binding_payload(layout: CatalogLayout) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.filter_catalog_bootstrap_binding",
        "canonicalArtifactRef": layout.release_ref.as_posix(),
        "bootstrapReplicaRef": APP_BOOTSTRAP_REF.as_posix(),
        "environmentManifestRefs": {
            environment: layout.environment_ref(environment).as_posix()
            for environment in ENVIRONMENTS
        },
    }


def _assert_metadata_contract(repo_root: Path) -> None:
    fields_path = repo_root / METADATA_OBJECT_REF / "fields.yaml"
    fields_document = yaml.safe_load(fields_path.read_text(encoding="utf-8"))
    try:
        adjustment_fields = fields_document["members"]["FilterAdjustmentValues"][
            "fields"
        ]
        metadata_names = tuple(item["name"] for item in adjustment_fields)
    except (KeyError, TypeError) as exc:
        raise CatalogContractError(
            "metadata FilterAdjustmentValues fields 无法读取"
        ) from exc
    if metadata_names != ADJUSTMENT_FIELD_NAMES:
        raise CatalogContractError(
            "Python 强类型 adjustments 与 metadata 字段顺序/集合不一致："
            f"metadata={metadata_names} python={ADJUSTMENT_FIELD_NAMES}"
        )
    _metadata_operations(repo_root)


def _metadata_operations(repo_root: Path) -> dict[str, str]:
    operations_path = repo_root / METADATA_OBJECT_REF / "operations.yaml"
    operations_document = yaml.safe_load(operations_path.read_text(encoding="utf-8"))
    routes = operations_document.get("api_routes")
    if not isinstance(routes, list):
        raise CatalogContractError("metadata operations.yaml api_routes 非法")
    operation_names = {
        route.get("operation")
        for route in routes
        if isinstance(route, dict)
    }
    missing = sorted(set(REQUIRED_OPERATION_NAMES.values()) - operation_names)
    if missing:
        raise CatalogContractError(
            f"metadata 缺少 FilterCatalogRelease operations：{missing}"
        )
    return {
        role: f"{OBJECT_ID}.{operation}"
        for role, operation in REQUIRED_OPERATION_NAMES.items()
    }


def _load_release(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"canonical release 不存在：{path}")
    payload = load_json_decimal(path.read_text(encoding="utf-8"))
    return normalize_release(payload)


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"manifest 不存在：{path}")
    payload = load_json_decimal(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CatalogContractError(f"{path} 必须为 object")
    return payload


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = pretty_json_text(payload)
    temporary = ""
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = handle.name
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _resolve_repo_ref(repo_root: Path, value: str) -> Path:
    ref = Path(value)
    if ref.is_absolute() or ".." in ref.parts:
        raise CatalogContractError(f"仓库引用必须为安全相对路径：{value}")
    path = (repo_root / ref).resolve()
    root = repo_root.resolve()
    if path != root and root not in path.parents:
        raise CatalogContractError(f"仓库引用越界：{value}")
    return path


def _ref_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CatalogContractError(f"{label} 必须为非空相对路径")
    return value


def _require_exact_keys(
    payload: dict[str, object],
    expected: set[str],
    label: str,
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        raise CatalogContractError(
            f"{label} 字段不合法：missing={missing} unknown={unknown}"
        )


def _require_same_payload(
    actual: object,
    expected: object,
    message: str,
) -> None:
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise CatalogContractError(message)
