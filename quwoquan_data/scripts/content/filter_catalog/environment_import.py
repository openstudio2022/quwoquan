"""FilterCatalogRelease 环境发布输入解析。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from content.filter_catalog import artifact
from content.filter_catalog.contract import CatalogContractError


@dataclass(frozen=True)
class FilterCatalogEnvironmentImport:
    """已与仓库 canonical binding 对齐的一次环境发布输入。"""

    environment: str
    manifest_ref: str
    canonical_artifact_ref: str
    release: dict[str, object]
    idempotency_key: str
    activation_policy: str
    operation_paths: dict[str, str]

    @property
    def release_id(self) -> str:
        return str(self.release["releaseId"])

    @property
    def canonical_digest(self) -> str:
        return str(self.release["canonicalDigest"])

    @property
    def category_count(self) -> int:
        categories = self.release["categories"]
        if not isinstance(categories, list):
            raise CatalogContractError("canonical release categories 非法")
        return len(categories)

    @property
    def preset_count(self) -> int:
        presets = self.release["presets"]
        if not isinstance(presets, list):
            raise CatalogContractError("canonical release presets 非法")
        return len(presets)

    def stage_payload(self) -> dict[str, object]:
        return {
            "releaseId": self.release_id,
            "sourceOwner": self.release["sourceOwner"],
            "canonicalDigest": self.canonical_digest,
            "categories": self.release["categories"],
            "presets": self.release["presets"],
            "recommendedFallbackPresetIds": self.release[
                "recommendedFallbackPresetIds"
            ],
        }


def load_environment_import(
    *,
    repo_root: Path,
    environment: str,
) -> FilterCatalogEnvironmentImport:
    """读取已通过仓库同源验证的环境发布输入。"""
    if environment not in artifact.ENVIRONMENTS:
        raise CatalogContractError(f"未知 FilterCatalogRelease 环境：{environment}")
    report = artifact.validate_repository(repo_root)
    if not report["passed"]:
        raise CatalogContractError(
            "FilterCatalogRelease 仓库输入未通过校验："
            + "; ".join(str(item) for item in report["issues"])
        )
    binding = artifact._load_mapping(repo_root / artifact.BINDING_REF)
    manifest_refs = binding["environmentManifestRefs"]
    if not isinstance(manifest_refs, dict):
        raise CatalogContractError("bootstrap binding environmentManifestRefs 非法")
    manifest_ref = artifact._ref_value(
        manifest_refs.get(environment),
        f"environmentManifestRefs.{environment}",
    )
    manifest = artifact._load_mapping(
        artifact._resolve_repo_ref(repo_root, manifest_ref)
    )
    canonical_artifact_ref = artifact._ref_value(
        manifest.get("canonicalArtifactRef"),
        "canonicalArtifactRef",
    )
    release = artifact._load_release(
        artifact._resolve_repo_ref(repo_root, canonical_artifact_ref),
    )
    return FilterCatalogEnvironmentImport(
        environment=environment,
        manifest_ref=manifest_ref,
        canonical_artifact_ref=canonical_artifact_ref,
        release=release,
        idempotency_key=str(manifest["idempotencyKey"]),
        activation_policy=str(manifest["activationPolicy"]),
        operation_paths=_metadata_operation_paths(repo_root),
    )


def _metadata_operation_paths(repo_root: Path) -> dict[str, str]:
    operations_path = repo_root / artifact.METADATA_OBJECT_REF / "operations.yaml"
    operations_document = yaml.safe_load(operations_path.read_text(encoding="utf-8"))
    routes = operations_document.get("api_routes")
    if not isinstance(routes, list):
        raise CatalogContractError("metadata operations.yaml api_routes 非法")
    by_operation = {
        route.get("operation"): route
        for route in routes
        if isinstance(route, dict)
    }
    paths: dict[str, str] = {}
    for role, operation in artifact.REQUIRED_OPERATION_NAMES.items():
        route = by_operation.get(operation)
        if not isinstance(route, dict):
            raise CatalogContractError(
                f"metadata 缺少 FilterCatalogRelease operation path：{operation}"
            )
        path = route.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            raise CatalogContractError(
                f"metadata FilterCatalogRelease operation path 非法：{operation}"
            )
        paths[role] = path
    return paths
