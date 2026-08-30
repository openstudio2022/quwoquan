#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import load_json_yaml, relpath, utc_now, write_json
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    get_environment,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_for_env,
    legal_static_deployment_package_dir,
    remove_deployment_tree,
)

DEFAULT_MANIFEST = ROOT / "quwoquan_service" / "static" / "legal" / "manifest.yaml"
LEGAL_STATIC_SOURCE_SCHEMA = "legal-static"
REQUIRED_DOCUMENTS = {
    "user-agreement",
    "privacy-policy",
    "permissions",
    "third-party-sdk-list",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CHECKSUM_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
EXTERNAL_ATTR_RE = re.compile(
    r"""\b(?P<attr>src|href)\s*=\s*["'](?P<url>https?://[^"']+)["']""",
    re.IGNORECASE,
)
EVENT_HANDLER_RE = re.compile(r"""\son[a-z]+\s*=""", re.IGNORECASE)
UTF8_META_RE = re.compile(
    r"""<meta\b[^>]*\bcharset\s*=\s*["']?\s*utf-8\s*["']?[^>]*>""",
    re.IGNORECASE,
)
PLACEHOLDER_TOKENS = (
    "待法务",
    "待备案",
    "待确认",
    "待接入确认",
    "占位",
    "TODO",
    "TBD",
    "{{",
    "}}",
)


def _resolve_package_root(
    env_name: str,
    *,
    output_root: Path | None,
    target: str = "",
) -> Path:
    target_name = deployment_target_for_env(env_name, target=target)
    expected = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if output_root is not None and output_root.expanduser().resolve() != expected:
        raise ValueError(
            "legal-static output must resolve to the target-scoped active package candidate: "
            f"expected {expected}, got {output_root.expanduser().resolve()}"
        )
    return expected


@contextmanager
def _package_lock(package_root: Path, *, exclusive: bool) -> Any:
    lock_root = package_root / ".locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / "package.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            import fcntl  # type: ignore

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ModuleNotFoundError:
            yield


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_manifest(path: Path) -> dict[str, Any]:
    loaded = load_json_yaml(path)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{relpath(path)} must be a mapping")
    return loaded


def _documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    docs = manifest.get("documents")
    if not isinstance(docs, list):
        return []
    return [doc for doc in docs if isinstance(doc, dict)]


def _legal_base_url(env_name: str, manifest: dict[str, Any]) -> str:
    del manifest
    topology = load_environment_topology()
    public_bases = get_environment(topology, env_name).get("publicBases") or {}
    return str(public_bases.get("legal") or "").strip().rstrip("/")


def _validate_owner(manifest: dict[str, Any], *, env_name: str) -> list[str]:
    issues: list[str] = []
    owner = manifest.get("owner")
    if not isinstance(owner, dict):
        return ["owner must be a mapping"]
    required = (
        "appName",
        "appId",
        "operatorName",
        "registeredAddress",
        "personalInfoProtectionContact",
        "customerSupportEmail",
        "customerSupportPhone",
        "icpFilingNumber",
    )
    for key in required:
        value = str(owner.get(key) or "").strip()
        if not value:
            issues.append(f"owner.{key} is required")
        if env_name == "prod" and _has_placeholder(value):
            issues.append(f"owner.{key} contains placeholder text")
    return issues


def _has_placeholder(text: str) -> bool:
    upper = text.upper()
    return any(token.upper() in upper for token in PLACEHOLDER_TOKENS)


def _validate_html(
    path: Path,
    *,
    doc_slug: str,
    version: str,
    allowlist: list[str],
    env_name: str,
) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{relpath(path)} must be UTF-8 encoded"]
    lower = text.lower()
    if UTF8_META_RE.search(text) is None:
        issues.append(f"{relpath(path)} missing UTF-8 charset meta")
    if "<script" in lower or "</script" in lower:
        issues.append(f"{relpath(path)} must not include script tags")
    if "javascript:" in lower:
        issues.append(f"{relpath(path)} must not include javascript: URLs")
    if EVENT_HANDLER_RE.search(text):
        issues.append(f"{relpath(path)} must not include inline event handlers")
    if f'content="{doc_slug}"' not in text:
        issues.append(f"{relpath(path)} missing legal document id meta for {doc_slug}")
    if f'content="{version}"' not in text:
        issues.append(f"{relpath(path)} missing legal version meta for {version}")
    for match in EXTERNAL_ATTR_RE.finditer(text):
        attr = match.group("attr").lower()
        url = match.group("url")
        if attr == "src":
            issues.append(f"{relpath(path)} must not load external src resource: {url}")
            continue
        if allowlist and not any(url.startswith(prefix) for prefix in allowlist):
            issues.append(f"{relpath(path)} external href is not allowlisted: {url}")
    if env_name == "prod" and _has_placeholder(text):
        issues.append(f"{relpath(path)} contains placeholder text")
    return issues


def validate_manifest(
    env_name: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> tuple[dict[str, Any], list[str]]:
    manifest = _load_manifest(manifest_path)
    issues: list[str] = []
    if manifest.get("schema") != LEGAL_STATIC_SOURCE_SCHEMA:
        issues.append(f"schema must be {LEGAL_STATIC_SOURCE_SCHEMA}")
    if manifest.get("packageKind") != "legal-static":
        issues.append("packageKind must be legal-static")
    current_version = str(manifest.get("currentVersion") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", current_version):
        issues.append("currentVersion must use YYYY-MM")
    issues.extend(_validate_owner(manifest, env_name=env_name))
    docs = _documents(manifest)
    slugs = [str(doc.get("slug") or "").strip() for doc in docs]
    missing_docs = sorted(REQUIRED_DOCUMENTS.difference(slugs))
    if missing_docs:
        issues.append(f"missing required documents: {', '.join(missing_docs)}")
    if len(slugs) != len(set(slugs)):
        issues.append("document slugs must be unique")
    allowlist = [
        str(item).strip().rstrip("/")
        for item in manifest.get("externalResourceAllowlist") or []
        if str(item).strip()
    ]
    manifest_root = manifest_path.parent
    for doc in docs:
        slug = str(doc.get("slug") or "").strip()
        if not SLUG_RE.match(slug):
            issues.append(f"invalid document slug: {slug}")
        version = str(doc.get("version") or "").strip()
        if version != current_version:
            issues.append(f"{slug}: version must match currentVersion {current_version}")
        source = str(doc.get("source") or "").strip()
        source_path = (manifest_root / source).resolve()
        if not source_path.is_file():
            issues.append(f"{slug}: source file not found: {source}")
            continue
        expected_checksum = str(doc.get("checksumSha256") or "").strip().lower()
        actual_checksum = _sha256_file(source_path)
        if not CHECKSUM_RE.match(expected_checksum):
            issues.append(f"{slug}: checksumSha256 must be sha256:<64 hex>")
        elif expected_checksum != actual_checksum:
            issues.append(
                f"{slug}: checksum mismatch, expected {expected_checksum}, got {actual_checksum}"
            )
        stable_path = str(doc.get("stablePath") or "").strip()
        version_path = str(doc.get("versionPath") or "").strip()
        if stable_path != f"/legal/{slug}":
            issues.append(f"{slug}: stablePath must be /legal/{slug}")
        if version_path != f"/legal/{version}/{slug}":
            issues.append(f"{slug}: versionPath must be /legal/{version}/{slug}")
        issues.extend(
            _validate_html(
                source_path,
                doc_slug=slug,
                version=version,
                allowlist=allowlist,
                env_name=env_name,
            )
        )
    return manifest, issues


def _legal_static_root(package_root: Path, env_name: str) -> Path:
    return package_root


def _refresh_current_pointer(
    env_root: Path,
    package_dir: Path,
    *,
    target_name: str,
) -> str:
    current = env_root / "current"
    if current.is_symlink() or current.is_file():
        current.unlink()
    elif current.exists():
        remove_deployment_tree(target_name, "packages", "legal-static", "current")
    shutil.copytree(package_dir, current)
    return relpath(current)


def build_package(
    env_name: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_root: Path | None = None,
    target: str = "",
) -> dict[str, Any]:
    manifest, issues = validate_manifest(env_name, manifest_path=manifest_path)
    if issues:
        return {
            "status": "failed",
            "env": env_name,
            "issues": issues,
            "exitCode": 1,
        }
    version = str(manifest["currentVersion"])
    target_name = deployment_target_for_env(env_name, target=target)
    package_root = _resolve_package_root(
        env_name,
        output_root=output_root,
        target=target,
    )
    with _package_lock(package_root, exclusive=True):
        package_dir = package_root / version
        if package_dir.exists():
            remove_deployment_tree(
                target_name,
                "packages",
                "legal-static",
                version,
            )
        public_root = package_dir / "public"
        public_legal_root = public_root / "legal"
        public_legal_root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(manifest_path, package_dir / "manifest.yaml")

        legal_base_url = _legal_base_url(env_name, manifest)
        docs_payload: list[dict[str, Any]] = []
        source_root = manifest_path.parent
        for doc in _documents(manifest):
            slug = str(doc["slug"])
            source_path = source_root / str(doc["source"])
            source_bytes = source_path.read_bytes()
            stable_targets = [
                public_legal_root / slug,
                public_legal_root / f"{slug}.html",
            ]
            versioned_dir = public_legal_root / version
            versioned_targets = [
                versioned_dir / slug,
                versioned_dir / f"{slug}.html",
            ]
            for target in stable_targets + versioned_targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_bytes)
            checksum = _sha256_bytes(source_bytes)
            docs_payload.append(
                {
                    "slug": slug,
                    "title": doc.get("title", ""),
                    "version": version,
                    "stablePath": doc["stablePath"],
                    "stableHtmlPath": f"{doc['stablePath']}.html",
                    "versionPath": doc["versionPath"],
                    "versionHtmlPath": f"{doc['versionPath']}.html",
                    "stableUrl": f"{legal_base_url}/{slug}",
                    "versionUrl": f"{legal_base_url}/{version}/{slug}",
                    "checksumSha256": checksum,
                }
            )

        public_manifest = {
            "schema": "legal-static-public",
            "packageKind": "legal-static",
            "env": env_name,
            "currentVersion": version,
            "legalBaseUrl": legal_base_url,
            "documents": docs_payload,
            "generatedAt": utc_now(),
        }
        write_json(package_dir / "manifest.json", public_manifest)
        write_json(public_legal_root / "manifest.json", public_manifest)

        release_metadata = {
            "schema": "legal-static-release",
            "packageKind": "legal-static",
            "env": env_name,
            "version": version,
            "currentVersion": version,
            "legalBaseUrl": legal_base_url,
            "artifactRoot": relpath(_legal_static_root(package_root, env_name)),
            "packageDir": relpath(package_dir),
            "stableUrls": {doc["slug"]: doc["stableUrl"] for doc in docs_payload},
            "versionedUrls": {doc["slug"]: doc["versionUrl"] for doc in docs_payload},
            "prodRequiresGammaProbe": bool(
                (manifest.get("releasePolicy") or {}).get("prodRequiresGammaProbe")
            ),
            "generatedAt": utc_now(),
        }
        write_json(package_dir / "release_metadata.json", release_metadata)

        checksums: dict[str, str] = {}
        for path in sorted(package_dir.rglob("*")):
            if path.is_file() and path.name != "checksums.json":
                checksums[str(path.relative_to(package_dir))] = _sha256_file(path)
        write_json(package_dir / "checksums.json", checksums)
        current_pointer = _refresh_current_pointer(
            _legal_static_root(package_root, env_name),
            package_dir,
            target_name=target_name,
        )
    return {
        "status": "ok",
        "env": env_name,
        "version": version,
        "packageDir": relpath(package_dir),
        "currentPointer": current_pointer,
        "legalBaseUrl": legal_base_url,
        "documents": docs_payload,
        "exitCode": 0,
    }


def verify_package(
    env_name: str,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_root: Path | None = None,
    package_root: Path | None = None,
    target: str = "",
) -> dict[str, Any]:
    manifest, issues = validate_manifest(env_name, manifest_path=manifest_path)
    version = str(manifest.get("currentVersion") or "")
    resolved_package_root = _resolve_package_root(
        env_name,
        output_root=output_root,
        target=target,
    )
    target_name = deployment_target_for_env(env_name, target=target)
    with _package_lock(resolved_package_root, exclusive=False):
        expected_package_dir = resolved_package_root / version
        if package_root is not None and package_root.expanduser().resolve() != expected_package_dir:
            raise ValueError(
                "legal-static package root must resolve to its target-scoped "
                f"workspace: expected {expected_package_dir}"
            )
        package_dir = package_root or expected_package_dir
        return _verify_package_locked(
            env_name,
            manifest=manifest,
            issues=issues,
            version=version,
            package_dir=package_dir,
        )


def _verify_current_snapshot(
    package_dir: Path,
    *,
    issues: list[str],
) -> None:
    """Require ``current/`` to be a full physical byte-exact copy of the version."""
    current = package_dir.parent / "current"
    if current.is_symlink():
        issues.append(
            f"legal-static current must be a physical directory, not a symlink: "
            f"{relpath(current)}"
        )
        return
    if not current.is_dir():
        issues.append(f"missing legal-static current snapshot: {relpath(current)}")
        return

    version_files = {
        path.relative_to(package_dir).as_posix(): path
        for path in package_dir.rglob("*")
        if path.is_file()
    }
    current_files = {
        path.relative_to(current).as_posix(): path
        for path in current.rglob("*")
        if path.is_file()
    }
    for relative in sorted(set(version_files) | set(current_files)):
        version_path = version_files.get(relative)
        current_path = current_files.get(relative)
        if version_path is None:
            issues.append(f"current snapshot has unexpected file: {relative}")
            continue
        if current_path is None:
            issues.append(f"current snapshot missing file: {relative}")
            continue
        if current_path.is_symlink() or not current_path.is_file():
            issues.append(
                f"current snapshot path is unsafe or not a regular file: {relative}"
            )
            continue
        if _sha256_file(version_path) != _sha256_file(current_path):
            issues.append(
                f"current snapshot digest drift for {relative}: "
                f"{_sha256_file(current_path)} != {_sha256_file(version_path)}"
            )


def _verify_package_locked(
    env_name: str,
    *,
    manifest: dict[str, Any],
    issues: list[str],
    version: str,
    package_dir: Path,
) -> dict[str, Any]:
    if not package_dir.is_dir():
        issues.append(f"missing legal-static package: {relpath(package_dir)}")
        return {"status": "failed", "env": env_name, "issues": issues, "exitCode": 1}

    checksums_path = package_dir / "checksums.json"
    release_path = package_dir / "release_metadata.json"
    public_manifest_path = package_dir / "public" / "legal" / "manifest.json"
    for required in (checksums_path, release_path, public_manifest_path):
        if not required.is_file():
            issues.append(f"missing package file: {relpath(required)}")
    if checksums_path.is_file():
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        if not isinstance(checksums, dict):
            issues.append(f"{relpath(checksums_path)} must be a mapping")
        else:
            for rel, expected in checksums.items():
                path = package_dir / str(rel)
                if not path.is_file():
                    issues.append(f"checksum target missing: {rel}")
                    continue
                actual = _sha256_file(path)
                if actual != expected:
                    issues.append(f"checksum mismatch for {rel}: {actual} != {expected}")
    if release_path.is_file():
        release = json.loads(release_path.read_text(encoding="utf-8"))
        if release.get("env") != env_name:
            issues.append("release_metadata env mismatch")
        if release.get("currentVersion") != version:
            issues.append("release_metadata currentVersion mismatch")
        if release.get("packageKind") != "legal-static":
            issues.append("release_metadata packageKind mismatch")

    for doc in _documents(manifest):
        slug = str(doc["slug"])
        stable = package_dir / "public" / "legal" / slug
        stable_html = package_dir / "public" / "legal" / f"{slug}.html"
        versioned = package_dir / "public" / "legal" / version / slug
        versioned_html = package_dir / "public" / "legal" / version / f"{slug}.html"
        for path in (stable, stable_html, versioned, versioned_html):
            if not path.is_file():
                issues.append(f"missing published document: {relpath(path)}")
        existing = [path for path in (stable, stable_html, versioned, versioned_html) if path.is_file()]
        if existing and len({_sha256_file(path) for path in existing}) != 1:
            issues.append(f"{slug}: stable and versioned published files differ")
        if stable.is_file():
            try:
                stable_text = stable.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(f"{slug}: published document is not UTF-8 encoded")
            else:
                title = str(doc.get("title") or "").strip()
                if title and title not in stable_text:
                    issues.append(f"{slug}: published document is missing its title")
    _verify_current_snapshot(package_dir, issues=issues)
    return {
        "status": "ok" if not issues else "failed",
        "env": env_name,
        "version": version,
        "packageDir": relpath(package_dir),
        "issues": issues,
        "exitCode": 0 if not issues else 1,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and verify legal-static packages.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("package", "verify-package", "validate"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--env", choices=ENVIRONMENTS, required=True)
        sub.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
        sub.add_argument(
            "--output-root",
            default="",
            help="external legal-static package root; defaults to QWQ_DEPLOY_WORK_ROOT",
        )
        sub.add_argument("--target", default="")
        sub.add_argument("--package-root", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    output_root = Path(args.output_root) if args.output_root else None
    package_root = Path(args.package_root) if args.package_root else None

    if args.command == "package":
        payload = build_package(
            args.env,
            manifest_path=manifest_path,
            output_root=output_root,
            target=args.target,
        )
    elif args.command == "verify-package":
        payload = verify_package(
            args.env,
            manifest_path=manifest_path,
            output_root=output_root,
            package_root=package_root,
            target=args.target,
        )
    else:
        manifest, issues = validate_manifest(args.env, manifest_path=manifest_path)
        payload = {
            "status": "ok" if not issues else "failed",
            "env": args.env,
            "version": manifest.get("currentVersion", ""),
            "issues": issues,
            "exitCode": 0 if not issues else 1,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return int(payload.get("exitCode", 1))


if __name__ == "__main__":
    raise SystemExit(main())
