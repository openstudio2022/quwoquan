#!/usr/bin/env python3
"""Render and validate immutable App build-product evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quwoquan_ops.cli.lib.app_identity import (  # noqa: E402
    AppBuildProduct,
    application_id_for_build_product,
    resolve_build_product,
    supported_build_products,
)
from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402

_ARTIFACT_METADATA_PATH = (
    _ROOT / "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
)


def _load_release_package_contract() -> dict[str, Any]:
    """从 canonical metadata 读取五产品包证据契约。"""

    document = load_json_yaml(_ARTIFACT_METADATA_PATH)
    if not isinstance(document, dict):
        raise ValueError(f"invalid artifact metadata: {_ARTIFACT_METADATA_PATH}")
    schemas = document.get("schemas")
    contract = schemas.get("release_application_package") if isinstance(schemas, dict) else None
    artifact_contract = schemas.get("app_artifact_manifest") if isinstance(schemas, dict) else None
    distribution_classes = document.get("distribution_classes")
    if (
        not isinstance(contract, dict)
        or not isinstance(contract.get("schema_value"), str)
        or not isinstance(contract.get("required_fields"), list)
        or not isinstance(contract.get("fields"), dict)
    ):
        raise ValueError("release_application_package contract is not canonical")
    if (
        not isinstance(artifact_contract, dict)
        or not isinstance(artifact_contract.get("schema_value"), str)
        or not isinstance(artifact_contract.get("required_fields"), list)
        or not isinstance(artifact_contract.get("fields"), dict)
        or not isinstance(distribution_classes, dict)
    ):
        raise ValueError("app_artifact_manifest contract is not canonical")
    products = supported_build_products()
    if len(products) != 5 or len({item.build_product_id for item in products}) != 5:
        raise ValueError("baseline App build product set must contain exactly five products")
    return {
        "schema": contract["schema_value"],
        "fields": frozenset(str(field) for field in contract["required_fields"]),
        "products": products,
        "artifactSchema": artifact_contract["schema_value"],
        "artifactRequiredFields": frozenset(
            str(field) for field in artifact_contract["required_fields"]
        ),
        "artifactFields": frozenset(
            str(field) for field in artifact_contract["fields"]
        ),
        "distributionClasses": distribution_classes,
    }


_CONTRACT = _load_release_package_contract()
SCHEMA = _CONTRACT["schema"]
BUILD_PRODUCTS: tuple[AppBuildProduct, ...] = _CONTRACT["products"]
BUILD_PRODUCT_IDS = tuple(product.build_product_id for product in BUILD_PRODUCTS)
GENERIC_PACKAGES = BUILD_PRODUCT_IDS
GENERIC_FIELDS = _CONTRACT["fields"]
ARTIFACT_SCHEMA = _CONTRACT["artifactSchema"]
ARTIFACT_REQUIRED_FIELDS = _CONTRACT["artifactRequiredFields"]
ARTIFACT_FIELDS = _CONTRACT["artifactFields"]
_DISTRIBUTION_CLASSES = _CONTRACT["distributionClasses"]
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
PAYLOAD_NAMES = {
    "android-nonprod-apk": "app-release.apk",
    "android-prod-apk": "app-release.apk",
    "ios-nonprod-app": "quwoquan.app",
    "ios-prod-app": "quwoquan.app",
    "web-shared": "public-web",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--build-product-id", choices=BUILD_PRODUCT_IDS, required=True)
    render_parser.add_argument("--package", required=True, type=Path)
    render_parser.add_argument("--source-git-sha", required=True)
    render_parser.add_argument("--source-tree-digest", required=True)
    render_parser.add_argument("--artifact-manifest", required=True, type=Path)
    render_parser.add_argument("--output", required=True, type=Path)

    validate = subparsers.add_parser("validate-bundle")
    validate.add_argument("--bundle-dir", required=True, type=Path)
    validate.add_argument("--source-git-sha", required=True)
    validate.add_argument("--source-tree-digest", required=True)
    return parser


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"package directory is missing or unsafe: {root}")
    entries = sorted(root.rglob("*"))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f"package tree contains a symlink: {unsafe}")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f"package directory is empty: {root}")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _package_digest(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.exists():
        raise ValueError(f"package is missing or is a symlink: {path}")
    if resolved.is_file():
        if resolved.stat().st_size <= 0:
            raise ValueError(f"package file is empty: {path}")
        return _sha256_file(resolved)
    if resolved.is_dir():
        return _sha256_tree(resolved)
    raise ValueError(f"package is not a regular file or directory: {path}")


def _generic_package_digest(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError(
            "application package must be the canonical payload directory: " f"{path}"
        )
    return _sha256_tree(resolved)


def _validate_source(source_git_sha: str, source_tree_digest: str) -> tuple[str, str]:
    git_sha = source_git_sha.strip().lower()
    tree_digest = source_tree_digest.strip().lower()
    if GIT_SHA_PATTERN.fullmatch(git_sha) is None:
        raise ValueError("sourceGitSha is not a full immutable Git SHA")
    if TREE_DIGEST_PATTERN.fullmatch(tree_digest) is None:
        raise ValueError("sourceTreeDigest is not an immutable Git tree digest")
    return git_sha, tree_digest


def _git_identity() -> tuple[str, str]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prefix = "sha1" if len(tree) == 40 else "sha256" if len(tree) == 64 else ""
    if not prefix:
        raise ValueError("current Git tree identity is not canonical")
    return revision, f"{prefix}:{tree}"


def _require_checkout(source_git_sha: str, source_tree_digest: str) -> None:
    expected = _validate_source(source_git_sha, source_tree_digest)
    actual = _git_identity()
    if actual != expected:
        raise ValueError(
            "checked-out source identity differs from requested candidate: "
            f"actual={actual}, expected={expected}"
        )


def _expected_promotable(product: AppBuildProduct) -> bool:
    declaration = _DISTRIBUTION_CLASSES.get(product.distribution_class)
    return bool(
        isinstance(declaration, dict)
        and declaration.get("promotable")
        and product.build_mode == "release"
    )


def _validate_artifact_manifest(
    payload: Any,
    *,
    build_product_id: str,
    source_git_sha: str,
    source_tree_digest: str,
) -> dict[str, Any]:
    product = resolve_build_product(build_product_id)
    label = product.build_product_id
    if not isinstance(payload, dict):
        raise ValueError(f"{label} AppArtifactManifest fields are not canonical")
    payload_fields = set(payload)
    if (
        not ARTIFACT_REQUIRED_FIELDS.issubset(payload_fields)
        or not payload_fields.issubset(ARTIFACT_FIELDS)
    ):
        raise ValueError(f"{label} AppArtifactManifest fields are not canonical")
    trust_digest = payload.get("runtimeConfigTrustEnvelopeDigest")
    if product.platform in {"android", "ios"}:
        if DIGEST_PATTERN.fullmatch(str(trust_digest or "")) is None:
            raise ValueError(
                f"{label} AppArtifactManifest runtimeConfigTrustEnvelopeDigest is invalid"
            )
    elif "runtimeConfigTrustEnvelopeDigest" in payload_fields:
        raise ValueError(
            f"{label} Web AppArtifactManifest cannot bind a mobile trust envelope"
        )
    if payload.get("schema") != ARTIFACT_SCHEMA:
        raise ValueError(f"{label} AppArtifactManifest schema mismatch")
    expected_identity = {
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "distributionClass": product.distribution_class,
        "artifactFormat": product.artifact_format,
        "applicationId": application_id_for_build_product(product.build_product_id),
    }
    mismatches = [
        field for field, expected in expected_identity.items() if payload.get(field) != expected
    ]
    if mismatches:
        raise ValueError(
            f"{label} AppArtifactManifest identity mismatch: {', '.join(mismatches)}"
        )
    if (
        payload.get("sourceGitSha") != source_git_sha
        or payload.get("sourceTreeDigest") != source_tree_digest
    ):
        raise ValueError(f"{label} AppArtifactManifest source mismatch")
    for field in (
        "signingIdentityDigest",
        "buildProvenanceDigest",
        "artifactDigest",
    ):
        if DIGEST_PATTERN.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"{label} AppArtifactManifest {field} is invalid")
    declaration = _DISTRIBUTION_CLASSES.get(product.distribution_class)
    if not isinstance(declaration, dict):
        raise ValueError(f"{label} AppArtifactManifest distributionClass is invalid")
    platform_modes = declaration.get("platform_build_modes") or {}
    allowed_modes = (
        platform_modes.get(product.platform)
        if isinstance(platform_modes, dict)
        else None
    ) or declaration.get("build_modes") or []
    if (
        product.platform not in (declaration.get("platforms") or [])
        or product.build_mode not in allowed_modes
    ):
        raise ValueError(f"{label} AppArtifactManifest distribution/build mismatch")
    if payload.get("promotable") is not _expected_promotable(product):
        raise ValueError(f"{label} AppArtifactManifest promotability mismatch")
    return dict(payload)


def render(
    *,
    build_product_id: str,
    package: Path,
    source_git_sha: str,
    source_tree_digest: str,
    artifact_manifest: dict[str, Any],
) -> dict[str, Any]:
    _require_checkout(source_git_sha, source_tree_digest)
    product = resolve_build_product(build_product_id)
    git_sha, tree_digest = _validate_source(source_git_sha, source_tree_digest)
    normalized_artifact = _validate_artifact_manifest(
        artifact_manifest,
        build_product_id=product.build_product_id,
        source_git_sha=git_sha,
        source_tree_digest=tree_digest,
    )
    payload = {
        "schema": SCHEMA,
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "packageDigest": _generic_package_digest(package),
        "artifactManifest": normalized_artifact,
    }
    validate_package(payload, build_product_id=product.build_product_id)
    return payload


def validate_package(
    payload: Any,
    *,
    build_product_id: str,
    source_git_sha: str | None = None,
    source_tree_digest: str | None = None,
) -> dict[str, Any]:
    product = resolve_build_product(build_product_id)
    label = product.build_product_id
    if not isinstance(payload, dict) or set(payload) != GENERIC_FIELDS:
        raise ValueError(f"{label} application package fields are not canonical")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"{label} application package schema mismatch")
    if (
        payload.get("buildProductId") != product.build_product_id
        or payload.get("buildProfile") != product.build_profile
        or payload.get("platform") != product.platform
    ):
        raise ValueError(f"{label} application package identity mismatch")
    git_sha, tree_digest = _validate_source(
        str(payload.get("sourceGitSha") or ""),
        str(payload.get("sourceTreeDigest") or ""),
    )
    if source_git_sha is not None and git_sha != source_git_sha:
        raise ValueError(f"{label} sourceGitSha mismatch")
    if source_tree_digest is not None and tree_digest != source_tree_digest:
        raise ValueError(f"{label} sourceTreeDigest mismatch")
    if DIGEST_PATTERN.fullmatch(str(payload.get("packageDigest") or "")) is None:
        raise ValueError(f"{label} packageDigest is not immutable")
    _validate_artifact_manifest(
        payload.get("artifactManifest"),
        build_product_id=product.build_product_id,
        source_git_sha=git_sha,
        source_tree_digest=tree_digest,
    )
    return dict(payload)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON evidence {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return payload


def validate_bundle(
    *, bundle_dir: Path, source_git_sha: str, source_tree_digest: str
) -> None:
    git_sha, tree_digest = _validate_source(source_git_sha, source_tree_digest)
    applications = bundle_dir / "application-packages"
    actual_files = {path.name for path in applications.glob("*.json") if path.is_file()}
    expected_files = {f"{product_id}.json" for product_id in BUILD_PRODUCT_IDS}
    if actual_files != expected_files:
        raise ValueError(
            "App build product package set mismatch: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    expected_payloads = set(BUILD_PRODUCT_IDS)
    payload_root = bundle_dir / "payloads"
    actual_payloads = (
        {path.name for path in payload_root.iterdir() if path.is_dir()}
        if payload_root.is_dir()
        else set()
    )
    if actual_payloads != expected_payloads:
        raise ValueError(
            "App build product payload set mismatch: "
            f"missing={sorted(expected_payloads - actual_payloads)}, "
            f"extra={sorted(actual_payloads - expected_payloads)}"
        )
    for product_id in BUILD_PRODUCT_IDS:
        payload = validate_package(
            _load_json(applications / f"{product_id}.json"),
            build_product_id=product_id,
            source_git_sha=git_sha,
            source_tree_digest=tree_digest,
        )
        product_root = payload_root / product_id
        artifact = product_root / PAYLOAD_NAMES[product_id]
        if not artifact.exists() or _sha256_tree(product_root) != payload["packageDigest"]:
            raise ValueError(f"{product_id} hosted payload digest mismatch")
        if _package_digest(artifact) != payload["artifactManifest"]["artifactDigest"]:
            raise ValueError(f"{product_id} AppArtifactManifest artifact digest mismatch")


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "render":
            payload = render(
                build_product_id=args.build_product_id,
                package=args.package,
                source_git_sha=args.source_git_sha,
                source_tree_digest=args.source_tree_digest,
                artifact_manifest=_load_json(args.artifact_manifest),
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(_canonical_json(payload), encoding="utf-8")
        else:
            validate_bundle(
                bundle_dir=args.bundle_dir,
                source_git_sha=args.source_git_sha.strip().lower(),
                source_tree_digest=args.source_tree_digest.strip().lower(),
            )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"GATE_BLOCK: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
