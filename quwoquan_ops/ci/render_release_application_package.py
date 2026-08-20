#!/usr/bin/env python3
"""Render and validate immutable App package evidence for ReleaseEvidenceManifest."""

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

from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402

_ARTIFACT_METADATA_PATH = (
    _ROOT / "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
)


def _load_release_package_contract() -> dict[str, Any]:
    """从 canonical app_artifact_manifest metadata 读取包证据契约。

    schema 名、字段集合、环境与 surface 枚举都以 metadata 为唯一真相源；
    本脚本不自持第二份字段集合。
    """

    document = load_json_yaml(_ARTIFACT_METADATA_PATH)
    if not isinstance(document, dict):
        raise ValueError(f"invalid artifact metadata: {_ARTIFACT_METADATA_PATH}")
    contract = (document.get("schemas") or {}).get("release_application_package")
    if not isinstance(contract, dict):
        raise ValueError("release_application_package contract is missing")
    schema_value = contract.get("schema_value")
    required_fields = contract.get("required_fields")
    fields = contract.get("fields")
    if (
        not isinstance(schema_value, str)
        or not isinstance(required_fields, list)
        or not isinstance(fields, dict)
    ):
        raise ValueError("release_application_package contract is not canonical")
    environments = fields.get("environment", {}).get("allowed_values")
    surfaces = fields.get("surface", {}).get("allowed_values")
    artifact_contract = (document.get("schemas") or {}).get(
        "app_artifact_manifest"
    )
    distribution_classes = document.get("distribution_classes")
    if not isinstance(environments, list) or not isinstance(surfaces, list):
        raise ValueError("release_application_package enums are not canonical")
    if (
        not isinstance(artifact_contract, dict)
        or not isinstance(artifact_contract.get("required_fields"), list)
        or not isinstance(distribution_classes, dict)
    ):
        raise ValueError("app_artifact_manifest contract is not canonical")
    return {
        "schema": schema_value,
        "fields": frozenset(str(field) for field in required_fields),
        "environments": tuple(str(value) for value in environments),
        "surfaces": tuple(str(value) for value in surfaces),
        "artifactSchema": str(artifact_contract.get("schema_value") or ""),
        "artifactFields": frozenset(
            str(field) for field in artifact_contract["required_fields"]
        ),
        "distributionClasses": distribution_classes,
    }


_CONTRACT = _load_release_package_contract()
SCHEMA = _CONTRACT["schema"]
ENVIRONMENTS = _CONTRACT["environments"]
SURFACES = _CONTRACT["surfaces"]
GENERIC_PACKAGES = tuple(
    (environment, surface)
    for environment in ENVIRONMENTS
    for surface in SURFACES
    if (environment, surface) not in {("prod", "android"), ("prod", "web")}
)
GENERIC_FIELDS = _CONTRACT["fields"]
ARTIFACT_SCHEMA = _CONTRACT["artifactSchema"]
ARTIFACT_FIELDS = _CONTRACT["artifactFields"]
_DISTRIBUTION_CLASSES = _CONTRACT["distributionClasses"]
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
SPECIAL_SCHEMAS = {
    "publicWeb": "client-app.web.official-release",
    "android": "client-app.android.official-release",
    "opsPortal": "qwq.ops_portal_package",
}
PAYLOAD_NAMES = {
    "android": "app-release.apk",
    "ios": "quwoquan.app",
    "web": "public-web",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render")
    render.add_argument("--environment", choices=ENVIRONMENTS, required=True)
    render.add_argument("--surface", choices=SURFACES, required=True)
    render.add_argument("--package", required=True, type=Path)
    render.add_argument("--source-git-sha", required=True)
    render.add_argument("--source-tree-digest", required=True)
    render.add_argument("--artifact-manifest", required=True, type=Path)
    render.add_argument("--output", required=True, type=Path)

    bind = subparsers.add_parser("bind-special")
    bind.add_argument("--kind", choices=tuple(SPECIAL_SCHEMAS), required=True)
    bind.add_argument("--manifest", required=True, type=Path)
    bind.add_argument("--source-git-sha", required=True)
    bind.add_argument("--source-tree-digest", required=True)
    bind.add_argument("--output", required=True, type=Path)

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
    """Hash the complete payload directory consumed by the release finalizer."""

    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError(
            "generic application package must be the canonical payload directory: "
            f"{path}"
        )
    return _sha256_tree(resolved)


def _public_web_tree_digest(root: Path) -> str:
    """Match the canonical public Web producer's contentSHA256 algorithm."""

    digest = hashlib.sha256()
    files = sorted(item for item in root.rglob("*") if item.is_file())
    if not files:
        raise ValueError(f"public Web package directory is empty: {root}")
    for path in files:
        if path.is_symlink():
            raise ValueError(f"public Web package contains a symlink: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _ops_portal_tree_digest(root: Path) -> str:
    """Match stackctl's path-sensitive Ops Portal dist digest."""

    digest = hashlib.sha256()
    files = sorted(item for item in root.rglob("*") if item.is_file())
    if not files:
        raise ValueError(f"Ops Portal dist directory is empty: {root}")
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Ops Portal dist contains a symlink: {path}")
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


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
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
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


def render(
    *,
    environment: str,
    surface: str,
    package: Path,
    source_git_sha: str,
    source_tree_digest: str,
    artifact_manifest: dict[str, Any],
) -> dict[str, Any]:
    _require_checkout(source_git_sha, source_tree_digest)
    normalized_artifact = _validate_artifact_manifest(
        artifact_manifest,
        environment=environment,
        surface=surface,
        source_git_sha=source_git_sha.strip().lower(),
        source_tree_digest=source_tree_digest.strip().lower(),
    )
    payload = {
        "schema": SCHEMA,
        "environment": environment,
        "surface": surface,
        "sourceGitSha": source_git_sha.strip().lower(),
        "sourceTreeDigest": source_tree_digest.strip().lower(),
        "packageDigest": _generic_package_digest(package),
        "artifactManifest": normalized_artifact,
    }
    validate_generic(payload, environment=environment, surface=surface)
    return payload


def _validate_artifact_manifest(
    payload: Any,
    *,
    environment: str,
    surface: str,
    source_git_sha: str,
    source_tree_digest: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != ARTIFACT_FIELDS:
        raise ValueError(
            f"{environment}/{surface} AppArtifactManifest fields are not canonical"
        )
    if payload.get("schema") != ARTIFACT_SCHEMA:
        raise ValueError(f"{environment}/{surface} AppArtifactManifest schema mismatch")
    if payload.get("environment") != environment or payload.get("platform") != surface:
        raise ValueError(f"{environment}/{surface} AppArtifactManifest identity mismatch")
    if (
        payload.get("sourceGitSha") != source_git_sha
        or payload.get("sourceTreeDigest") != source_tree_digest
    ):
        raise ValueError(f"{environment}/{surface} AppArtifactManifest source mismatch")
    for field in (
        "signingIdentityDigest",
        "artifactDigest",
        "launchManifestDigest",
    ):
        if DIGEST_PATTERN.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(
                f"{environment}/{surface} AppArtifactManifest {field} is invalid"
            )
    distribution_class = str(payload.get("distributionClass") or "")
    declaration = _DISTRIBUTION_CLASSES.get(distribution_class)
    build_mode = str(payload.get("buildMode") or "")
    if not isinstance(declaration, dict):
        raise ValueError(
            f"{environment}/{surface} AppArtifactManifest distributionClass is invalid"
        )
    platform_modes = declaration.get("platform_build_modes") or {}
    allowed_modes = (
        platform_modes.get(surface)
        if isinstance(platform_modes, dict)
        else None
    ) or declaration.get("build_modes") or []
    if surface not in (declaration.get("platforms") or []) or build_mode not in allowed_modes:
        raise ValueError(
            f"{environment}/{surface} AppArtifactManifest distribution/build mismatch"
        )
    expected_promotable = bool(declaration.get("promotable") and build_mode == "release")
    if payload.get("promotable") is not expected_promotable:
        raise ValueError(
            f"{environment}/{surface} AppArtifactManifest promotability mismatch"
        )
    return dict(payload)


def validate_generic(
    payload: Any,
    *,
    environment: str,
    surface: str,
    source_git_sha: str | None = None,
    source_tree_digest: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != GENERIC_FIELDS:
        raise ValueError(
            f"{environment}/{surface} application package fields are not canonical"
        )
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"{environment}/{surface} application package schema mismatch")
    if payload.get("environment") != environment or payload.get("surface") != surface:
        raise ValueError(f"{environment}/{surface} application package identity mismatch")
    git_sha, tree_digest = _validate_source(
        str(payload.get("sourceGitSha") or ""),
        str(payload.get("sourceTreeDigest") or ""),
    )
    if source_git_sha is not None and git_sha != source_git_sha:
        raise ValueError(f"{environment}/{surface} sourceGitSha mismatch")
    if source_tree_digest is not None and tree_digest != source_tree_digest:
        raise ValueError(f"{environment}/{surface} sourceTreeDigest mismatch")
    if DIGEST_PATTERN.fullmatch(str(payload.get("packageDigest") or "")) is None:
        raise ValueError(f"{environment}/{surface} packageDigest is not immutable")
    _validate_artifact_manifest(
        payload.get("artifactManifest"),
        environment=environment,
        surface=surface,
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


def bind_special(
    *,
    kind: str,
    manifest_path: Path,
    source_git_sha: str,
    source_tree_digest: str,
) -> dict[str, Any]:
    _require_checkout(source_git_sha, source_tree_digest)
    payload = _load_json(manifest_path)
    if payload.get("schema") != SPECIAL_SCHEMAS[kind]:
        raise ValueError(f"{kind} package schema mismatch")
    if kind == "publicWeb":
        if payload.get("environment") != "prod":
            raise ValueError("public Web package is not bound to prod")
        content_digest = str(payload.get("contentSHA256") or "")
        if re.fullmatch(r"[0-9a-f]{64}", content_digest) is None:
            raise ValueError("public Web content digest is invalid")
        public = manifest_path.parent / "public"
        if _public_web_tree_digest(public) != f"sha256:{content_digest}":
            raise ValueError("public Web content digest does not match its payload")
    elif kind == "android":
        if payload.get("platform") != "android":
            raise ValueError("Android package platform mismatch")
        artifact = manifest_path.parent / str(payload.get("packagedAPK") or "")
        if _package_digest(artifact) != f"sha256:{payload.get('apkSHA256') or ''}":
            raise ValueError("Android package digest does not match its payload")
    else:
        if payload.get("environment") != "prod" or payload.get("target") != "prod-hosted":
            raise ValueError("Ops Portal package is not bound to prod/prod-hosted")
        if payload.get("gitRevision") != source_git_sha:
            raise ValueError("Ops Portal package Git revision mismatch")
        digests = payload.get("digests")
        if not isinstance(digests, dict) or any(
            DIGEST_PATTERN.fullmatch(str(value or "")) is None
            for value in digests.values()
        ):
            raise ValueError("Ops Portal package digests are incomplete")
        if payload.get("packageDigest") != digests.get("distTree"):
            raise ValueError("Ops Portal packageDigest does not match its dist evidence")
    payload["sourceGitSha"] = source_git_sha.strip().lower()
    payload["sourceTreeDigest"] = source_tree_digest.strip().lower()
    return payload


def validate_bundle(
    *, bundle_dir: Path, source_git_sha: str, source_tree_digest: str
) -> None:
    git_sha, tree_digest = _validate_source(source_git_sha, source_tree_digest)
    applications = bundle_dir / "application-packages"
    actual_files = {
        path.name for path in applications.glob("*.json") if path.is_file()
    }
    expected_files = {
        f"{environment}--{surface}.json"
        for environment, surface in GENERIC_PACKAGES
    }
    if actual_files != expected_files:
        raise ValueError(
            "generic application package set mismatch: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    for environment, surface in GENERIC_PACKAGES:
        payload = validate_generic(
            _load_json(applications / f"{environment}--{surface}.json"),
            environment=environment,
            surface=surface,
            source_git_sha=git_sha,
            source_tree_digest=tree_digest,
        )
        package = bundle_dir / "payloads" / environment / surface / PAYLOAD_NAMES[surface]
        if not package.exists() or _package_digest(package.parent) != payload["packageDigest"]:
            raise ValueError(
                f"{environment}/{surface} hosted payload digest mismatch"
            )
        if _package_digest(package) != payload["artifactManifest"]["artifactDigest"]:
            raise ValueError(
                f"{environment}/{surface} AppArtifactManifest artifact digest mismatch"
            )
    public_web = _load_json(bundle_dir / "public-web-manifest.json")
    android = _load_json(bundle_dir / "android-release-manifest.json")
    portal = _load_json(bundle_dir / "ops-portal-provenance.json")
    for label, payload, schema in (
        ("prod/web", public_web, SPECIAL_SCHEMAS["publicWeb"]),
        ("prod/android", android, SPECIAL_SCHEMAS["android"]),
        ("prod/opsPortal", portal, SPECIAL_SCHEMAS["opsPortal"]),
    ):
        if (
            payload.get("schema") != schema
            or payload.get("sourceGitSha") != git_sha
            or payload.get("sourceTreeDigest") != tree_digest
        ):
            raise ValueError(f"{label} special package source binding mismatch")

    web_payload = bundle_dir / "payloads/prod/web"
    web_digest = _sha256_tree(web_payload)
    if web_digest != "sha256:" + str(public_web.get("contentSHA256") or ""):
        raise ValueError("prod/web special payload digest mismatch")
    web_artifact = _validate_artifact_manifest(
        public_web.get("artifactManifest"),
        environment="prod",
        surface="web",
        source_git_sha=git_sha,
        source_tree_digest=tree_digest,
    )
    if web_artifact["artifactDigest"] != web_digest:
        raise ValueError("prod/web AppArtifactManifest artifact digest mismatch")

    android_payload = bundle_dir / "payloads/prod/android"
    packaged_apk = android_payload / str(android.get("packagedAPK") or "")
    android_digest = _package_digest(packaged_apk)
    if android_digest != "sha256:" + str(android.get("apkSHA256") or ""):
        raise ValueError("prod/android special payload digest mismatch")
    android_artifact = _validate_artifact_manifest(
        android.get("artifactManifest"),
        environment="prod",
        surface="android",
        source_git_sha=git_sha,
        source_tree_digest=tree_digest,
    )
    if android_artifact["artifactDigest"] != android_digest:
        raise ValueError("prod/android AppArtifactManifest artifact digest mismatch")

    portal_payload = bundle_dir / "payloads/prod/opsPortal"
    portal_digests = portal.get("digests")
    if (
        not isinstance(portal_digests, dict)
        or _sha256_file(portal_payload / "manifest.json")
        != portal_digests.get("manifest")
        or _ops_portal_tree_digest(portal_payload / "dist")
        != portal_digests.get("distTree")
        or portal.get("packageDigest") != portal_digests.get("distTree")
    ):
        raise ValueError("prod/opsPortal special payload digest mismatch")

    expected_payload_surfaces = {
        environment: set(SURFACES) for environment in ENVIRONMENTS
    }
    expected_payload_surfaces["prod"].add("opsPortal")
    for environment, expected_surfaces in expected_payload_surfaces.items():
        environment_root = bundle_dir / "payloads" / environment
        actual = {
            path.name for path in environment_root.iterdir() if path.is_dir()
        } if environment_root.is_dir() else set()
        if actual != expected_surfaces:
            raise ValueError(
                f"{environment} App payload surface set mismatch: "
                f"missing={sorted(expected_surfaces - actual)}, "
                f"extra={sorted(actual - expected_surfaces)}"
            )


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "render":
            payload = render(
                environment=args.environment,
                surface=args.surface,
                package=args.package,
                source_git_sha=args.source_git_sha,
                source_tree_digest=args.source_tree_digest,
                artifact_manifest=_load_json(args.artifact_manifest),
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(_canonical_json(payload), encoding="utf-8")
        elif args.command == "bind-special":
            payload = bind_special(
                kind=args.kind,
                manifest_path=args.manifest,
                source_git_sha=args.source_git_sha,
                source_tree_digest=args.source_tree_digest,
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
