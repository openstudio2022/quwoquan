#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    app_artifact_policy,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_package_root,
    deployment_target_for_env,
    legal_static_deployment_package_dir,
    output_root,
    portal_deployment_package_dir,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)

_PRODUCT_TELEMETRY_SECRET_RUNTIME_VARIABLES = (
    "PRODUCT_OPS_ELASTICSEARCH_API_KEY",
)

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
RUNTIME_SHARED_FILES = frozenset(
    {
        "Caddyfile",
        "livekit.yaml",
        "module_catalog.yaml",
        "object-storage-lifecycle.json",
        "retention_policy.yaml",
    }
)
RUNTIME_SHARED_SOURCE_PREFIXES = {
    "Caddyfile": "quwoquan_ops/environments/",
    "livekit.yaml": "quwoquan_ops/external/livekit/",
    "module_catalog.yaml": "quwoquan_service/runtime/",
    "object-storage-lifecycle.json": "quwoquan_ops/environments/compose/",
    "retention_policy.yaml": "quwoquan_service/runtime/",
}
RUNTIME_SHARED_EXTRA_TOP_LEVEL = frozenset(
    {
        "compiled-provider-bindings",
        "oci-images.json",
        "observability-log-sink",
        "provider-runtime",
        "runtime-topology",
    }
)


def expected_services() -> list[str]:
    services = [
        path.name
        for path in (ROOT / "quwoquan_service/services").iterdir()
        if path.is_dir()
    ]
    if (ROOT / "quwoquan_service/control-plane/platform-ops/config/schema.yaml").is_file():
        services.append("platform-ops-service")
    return sorted(services)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_tree(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def validate_provenance(report: dict[str, object], package_dir: Path) -> list[str]:
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return ["missing provenance"]
    revision = str(provenance.get("gitRevision") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return ["invalid provenance gitRevision"]
    files = provenance.get("files")
    if not isinstance(files, dict) or not files:
        return ["missing provenance files"]
    issues: list[str] = []
    for label, expected in files.items():
        if not isinstance(label, str) or not isinstance(expected, str):
            issues.append("invalid provenance file entry")
            continue
        candidates = {
            "defaultAppRuntime": package_dir / "default_app_runtime.yaml",
            "appRuntime": package_dir / "app_runtime.yaml",
            "defaultConfig": package_dir / "default_config.yaml",
            "environmentConfig": package_dir / "config.yaml",
            "environmentRuntime": package_dir / "environment_runtime.yaml",
            "targetUrlResolution": package_dir / "target-url-resolution.json",
        }
        path = candidates.get(label)
        if path is None or not path.is_file():
            issues.append(f"unknown or missing provenance file {label}")
        elif _sha256(path) != expected:
            issues.append(f"provenance digest mismatch for {label}")
    if "releaseFiles" in provenance:
        issues.append("legacy releaseFiles provenance is forbidden")
    return issues


def package_output_boundary_issues(
    package_dir: Path,
    package_root: Path,
) -> list[str]:
    """确保发布 payload 只位于本 target 的仓外 packages 根。"""
    try:
        package_dir.resolve().relative_to(package_root.resolve())
    except ValueError:
        return [
            f"package escapes deployment package root: "
            f"{_display(package_dir)}"
        ]
    disposable_root = output_root()
    try:
        package_dir.resolve().relative_to(disposable_root.resolve())
    except ValueError:
        return []
    return [f"package must not reside under disposable output: {_display(package_dir)}"]


def validate_runtime_shared_package(
    package_dir: Path,
    environment: str,
    target: str,
) -> list[str]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["missing runtime-shared manifest"]
    try:
        manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid runtime-shared manifest: {error}"]
    issues: list[str] = []
    if manifest.get("schema") != "qwq.runtime_shared_package":
        issues.append("invalid runtime-shared package schema")
    if manifest.get("environment") != environment:
        issues.append("runtime-shared package environment mismatch")
    provenance = manifest.get("provenance")
    files = provenance.get("files") if isinstance(provenance, dict) else None
    if not isinstance(files, dict) or set(files) != RUNTIME_SHARED_FILES:
        return [*issues, "runtime-shared package provenance files mismatch"]
    required_files = {*RUNTIME_SHARED_FILES, "manifest.json"}
    actual_files = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file()
    }
    allowed_files = set(required_files)
    for extra in RUNTIME_SHARED_EXTRA_TOP_LEVEL:
        extra_path = package_dir / extra
        if extra_path.is_file():
            allowed_files.add(extra)
        elif extra_path.is_dir():
            allowed_files.update(
                path.relative_to(package_dir).as_posix()
                for path in extra_path.rglob("*")
                if path.is_file()
            )
    if not required_files.issubset(actual_files) or not actual_files.issubset(
        allowed_files
    ):
        issues.append("runtime-shared package structure contains unexpected or missing files")
    for name in sorted(RUNTIME_SHARED_FILES):
        entry = files.get(name)
        path = package_dir / name
        if not isinstance(entry, dict):
            issues.append(f"runtime-shared provenance missing for {name}")
            continue
        source = entry.get("source")
        expected = entry.get("sha256")
        prefix = RUNTIME_SHARED_SOURCE_PREFIXES[name]
        normalized = str(source or "").replace("\\", "/")
        if not isinstance(source, str) or (
            not normalized.startswith(prefix) and f"/repo/{prefix}" not in normalized
        ):
            issues.append(f"runtime-shared provenance source invalid for {name}")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            issues.append(f"runtime-shared provenance digest invalid for {name}")
        elif not path.is_file():
            issues.append(f"runtime-shared payload missing for {name}")
        elif _sha256(path) != expected:
            issues.append(f"runtime-shared provenance digest mismatch for {name}")
    oci_path = package_dir / "oci-images.json"
    if oci_path.is_file():
        try:
            oci = load_json(oci_path)
        except (OSError, json.JSONDecodeError) as error:
            issues.append(f"invalid package OCI image manifest: {error}")
        else:
            required = {
                "schema",
                "environment",
                "target",
                "configurationDigest",
                "buildInputDigest",
                "imageDigest",
                "images",
            }
            if set(oci) != required:
                issues.append("package OCI image manifest fields mismatch")
            if oci.get("schema") != "stackctl-package-oci-images":
                issues.append("package OCI image manifest schema mismatch")
            if oci.get("environment") != environment or oci.get("target") != target:
                issues.append("package OCI image manifest target identity mismatch")
            for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
                if SHA256_RE.fullmatch(str(oci.get(field) or "")) is None:
                    issues.append(f"package OCI image manifest {field} is invalid")
            images = oci.get("images")
            if not isinstance(images, dict) or not images:
                issues.append("package OCI image manifest images are missing")
            else:
                for service, descriptor in images.items():
                    descriptor_keys = (
                        set(descriptor) if isinstance(descriptor, dict) else set()
                    )
                    if (
                        not isinstance(service, str)
                        or not service
                        or not isinstance(descriptor, dict)
                        or not {"ref", "imageDigest"}.issubset(descriptor_keys)
                        or not descriptor_keys.issubset(
                            {"ref", "imageDigest", "buildInputDigest"}
                        )
                        or not str(descriptor.get("ref") or "").strip()
                        or SHA256_RE.fullmatch(
                            str(descriptor.get("imageDigest") or "")
                        )
                        is None
                        or (
                            "buildInputDigest" in descriptor
                            and SHA256_RE.fullmatch(
                                str(descriptor.get("buildInputDigest") or "")
                            )
                            is None
                        )
                    ):
                        issues.append(
                            f"package OCI image identity is invalid for {service}"
                        )
                expected_image_digest = "sha256:" + hashlib.sha256(
                    json.dumps(
                        images,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                if oci.get("imageDigest") != expected_image_digest:
                    issues.append("package OCI image set digest mismatch")
    return issues


def _current_package_dir(package_root: Path, label: str) -> tuple[Path | None, list[str]]:
    current = package_root / "current"
    if not current.exists() and not current.is_symlink():
        return None, [f"missing {label} current package pointer"]
    resolved = current.resolve()
    try:
        resolved.relative_to(package_root.resolve())
    except ValueError:
        return None, [f"{label} current package pointer escapes package root"]
    if not resolved.is_dir():
        return None, [f"{label} current package pointer is not a directory"]
    return resolved, []


def validate_legal_static_package(package_root: Path, environment: str) -> list[str]:
    package_dir, issues = _current_package_dir(package_root, "legal-static")
    if package_dir is None:
        return issues
    release_path = package_dir / "release_metadata.json"
    checksums_path = package_dir / "checksums.json"
    public_manifest = package_dir / "public" / "legal" / "manifest.json"
    for required in (release_path, checksums_path, public_manifest):
        if not required.is_file():
            issues.append(f"missing legal-static package artifact: {required.name}")
    if issues:
        return issues
    try:
        release = load_json(release_path)
        checksums = load_json(checksums_path)
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid legal-static package metadata: {error}"]
    if release.get("packageKind") != "legal-static":
        issues.append("legal-static packageKind mismatch")
    if release.get("env") != environment:
        issues.append("legal-static package environment mismatch")
    if not isinstance(checksums, dict) or not checksums:
        return [*issues, "legal-static package checksums missing"]
    actual_files = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file() and path.name != "checksums.json"
    }
    if set(checksums) != actual_files:
        issues.append("legal-static checksum structure does not match package files")
    for relative, expected in checksums.items():
        path = package_dir / str(relative)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            issues.append(f"legal-static digest invalid for {relative}")
        elif not path.is_file():
            issues.append(f"legal-static checksum target missing: {relative}")
        elif _sha256(path) != expected:
            issues.append(f"legal-static digest mismatch for {relative}")
    return issues


def validate_ops_portal_package(
    package_root: Path,
    environment: str,
    *,
    target: str = "",
) -> list[str]:
    package_dir, issues = _current_package_dir(package_root, "ops-portal")
    if package_dir is None:
        return issues
    manifest_path = package_dir / "manifest.json"
    provenance_path = package_dir / "provenance.json"
    dist_dir = package_dir / "dist"
    for required in (manifest_path, provenance_path):
        if not required.is_file():
            issues.append(f"missing ops-portal package artifact: {required.name}")
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        issues.append("ops-portal package dist/index.html missing")
    if issues:
        return issues
    try:
        manifest = load_json(manifest_path)
        provenance = load_json(provenance_path)
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid ops-portal package metadata: {error}"]
    package_digest = str(manifest.get("packageDigest") or "")
    if (
        not SHA256_RE.fullmatch(package_digest)
        or package_dir.name != package_digest.removeprefix("sha256:")
    ):
        issues.append("ops-portal package digest mismatch")
    elif _sha256_tree(dist_dir) != package_digest:
        issues.append("ops-portal packageDigest does not match dist content")
    if manifest.get("schema") != "qwq.ops_portal_application":
        issues.append("invalid ops-portal application schema")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("sourceGitSha") or "")):
        issues.append("ops-portal manifest sourceGitSha invalid")
    if not re.fullmatch(
        r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})",
        str(manifest.get("sourceTreeDigest") or ""),
    ):
        issues.append("ops-portal manifest sourceTreeDigest invalid")
    for key in (
        "schema",
        "sourceGitSha",
        "sourceTreeDigest",
        "opsBaseUrl",
        "contentBaseUrl",
        "entityBaseUrl",
        "oidcIssuer",
        "oidcClientId",
    ):
        if not str(manifest.get(key) or "").strip():
            issues.append(f"ops-portal manifest missing {key}")
    if provenance.get("schema") != "qwq.ops_portal_package":
        issues.append("invalid ops-portal provenance schema")
    if provenance.get("packageKind") != "ops-portal":
        issues.append("ops-portal provenance packageKind mismatch")
    if provenance.get("environment") != environment:
        issues.append("ops-portal provenance environment mismatch")
    if target and provenance.get("target") != target:
        issues.append("ops-portal provenance target mismatch")
    if provenance.get("packageDigest") != package_digest:
        issues.append("ops-portal provenance package digest mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("gitRevision") or "")):
        issues.append("ops-portal provenance gitRevision invalid")
    elif provenance.get("gitRevision") != manifest.get("sourceGitSha"):
        issues.append("ops-portal provenance source Git mismatch")
    digests = provenance.get("digests")
    if not isinstance(digests, dict):
        return [*issues, "ops-portal provenance digests missing"]
    for label, path, actual in (
        ("manifest", manifest_path, _sha256(manifest_path)),
        ("distTree", dist_dir, _sha256_tree(dist_dir)),
    ):
        expected = digests.get(label)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            issues.append(f"ops-portal provenance digest invalid for {label}")
        elif actual != expected:
            issues.append(f"ops-portal provenance digest mismatch for {label}")
    return issues


def validate_service_provenance(
    provenance: dict[str, object], package_dir: Path, service: str, environment: str
) -> list[str]:
    issues: list[str] = []
    if provenance.get("schema") != "qwq.service_package":
        issues.append("invalid service package schema")
    if provenance.get("service") != service or provenance.get("environment") != environment:
        issues.append("service package identity mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("gitRevision") or "")):
        issues.append("invalid provenance gitRevision")
    digests = provenance.get("digests")
    if not isinstance(digests, dict):
        issues.append("missing service package digests")
        return issues
    candidates = {
        "imageLock": package_dir / "image.lock",
        "config": package_dir / "config/config.yaml",
        "manifests": package_dir / "manifests/all.yaml",
    }
    for label, path in candidates.items():
        expected = str(digests.get(label) or "")
        if not path.is_file():
            issues.append(f"missing {label} artifact")
        elif _sha256(path) != expected:
            issues.append(f"service package digest mismatch for {label}")
    for label in ("resources", "sourceTree"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digests.get(label) or "")):
            issues.append(f"invalid service package digest for {label}")
    return issues


def validate_product_telemetry_secret_package(package_dir: Path) -> list[str]:
    """Require the Elasticsearch credential to remain deployment-injected."""
    issues: list[str] = []
    for path in sorted(candidate for candidate in package_dir.rglob("*") if candidate.is_file()):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, 1):
            for variable in _PRODUCT_TELEMETRY_SECRET_RUNTIME_VARIABLES:
                match = re.match(
                    rf"^\s*{re.escape(variable)}\s*[:=]\s*(?P<value>.+?)\s*$",
                    line,
                )
                if match and not _secret_package_value_is_unresolved(
                    variable,
                    match.group("value"),
                ):
                    issues.append(_secret_package_value_issue(path, line_number, variable))
                    continue
                if not re.match(
                    rf"^\s*-\s+name:\s*{re.escape(variable)}\s*$",
                    line,
                ):
                    continue
                for nested_line_number, nested_line in enumerate(
                    lines[line_number : line_number + 5],
                    line_number + 1,
                ):
                    if re.match(r"^\s*-\s+name:\s*", nested_line):
                        break
                    value_match = re.match(r"^\s*value:\s*(?P<value>.+?)\s*$", nested_line)
                    if value_match and not _secret_package_value_is_unresolved(
                        variable,
                        value_match.group("value"),
                    ):
                        issues.append(
                            _secret_package_value_issue(
                                path,
                                nested_line_number,
                                variable,
                            )
                        )
                    break
    return issues


def _secret_package_value_is_unresolved(variable: str, raw_value: str) -> bool:
    value = raw_value.strip().strip("\"'")
    return value in {f"${{{variable}}}", f"${{{variable}:-}}", ""}


def _secret_package_value_issue(path: Path, line_number: int, variable: str) -> str:
    return (
        f"{_display(path)}:{line_number} embeds {variable}; "
        "Elasticsearch credentials must be injected at deployment time"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    parser.add_argument("--target", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_environment_topology()
    issues: list[str] = []
    envs = [args.env] if args.env else list(ENVIRONMENTS)

    for env_name in envs:
        try:
            target_name = deployment_target_for_env(env_name, target=args.target)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        try:
            app_dir = app_deployment_package_dir(env_name, target=target_name)
            package_root = deployment_package_root(env_name, target=target_name)
        except ValueError as exc:
            issues.append(
                f"{env_name}/{target_name} active deployment candidate rejected: {exc}"
            )
            continue
        report_path = app_dir / "report.json"
        cfg_path = app_dir / "app_runtime.yaml"
        if not report_path.is_file():
            issues.append(f"missing app package report: {_display(report_path)}")
            continue
        if not cfg_path.is_file():
            issues.append(f"missing app package runtime: {_display(cfg_path)}")
            continue
        report = load_json(report_path)
        policy = app_artifact_policy(manifest, env_name)
        if report.get("env") != env_name:
            issues.append(f"{_display(report_path)} env mismatch")
        if report.get("runtimeEnv") != policy.get("runtimeEnv"):
            issues.append(f"{_display(report_path)} runtimeEnv mismatch")
        if report.get("composition") != "production_remote":
            issues.append(f"{_display(report_path)} composition mismatch")
        for issue in validate_provenance(report, app_dir):
            issues.append(f"{_display(report_path)} {issue}")
        for issue in package_output_boundary_issues(app_dir, package_root):
            issues.append(f"{_display(app_dir)} {issue}")

        runtime_shared_dir = runtime_shared_deployment_package_dir(
            env_name,
            target=target_name,
        )
        for issue in validate_runtime_shared_package(
            runtime_shared_dir,
            env_name,
            target_name,
        ):
            issues.append(f"{_display(runtime_shared_dir)} {issue}")
        for issue in package_output_boundary_issues(runtime_shared_dir, package_root):
            issues.append(f"{_display(runtime_shared_dir)} {issue}")

        legal_root = legal_static_deployment_package_dir(env_name, target=target_name)
        if legal_root.exists() or legal_root.is_symlink():
            for issue in validate_legal_static_package(legal_root, env_name):
                issues.append(f"{_display(legal_root)} {issue}")
            for issue in package_output_boundary_issues(legal_root, package_root):
                issues.append(f"{_display(legal_root)} {issue}")

        portal_root = portal_deployment_package_dir(env_name, target=target_name)
        if portal_root.exists() or portal_root.is_symlink():
            for issue in validate_ops_portal_package(
                portal_root,
                env_name,
                target=target_name,
            ):
                issues.append(f"{_display(portal_root)} {issue}")
            for issue in package_output_boundary_issues(portal_root, package_root):
                issues.append(f"{_display(portal_root)} {issue}")

    services = expected_services()
    for service in services:
        for env_name in envs:
            try:
                target_name = deployment_target_for_env(env_name, target=args.target)
            except ValueError:
                continue
            package_root = deployment_package_root(
                env_name,
                target=target_name,
            )
            service_dir = service_deployment_package_dir(
                env_name,
                service,
                target=target_name,
            )
            report_path = service_dir / "provenance.json"
            cfg_path = service_dir / "config/config.yaml"
            manifest_path = service_dir / "manifests/all.yaml"
            image_lock_path = service_dir / "image.lock"
            if not report_path.is_file():
                issues.append(
                    f"missing service package provenance: {_display(report_path)}"
                )
                continue
            if not cfg_path.is_file() or not manifest_path.is_file() or not image_lock_path.is_file():
                issues.append(
                    f"incomplete autonomous service package: {_display(service_dir)}"
                )
                continue
            report = load_json(report_path)
            for issue in validate_service_provenance(report, service_dir, service, env_name):
                issues.append(f"{_display(report_path)} {issue}")
            if service == "product-ops-service":
                issues.extend(validate_product_telemetry_secret_package(service_dir))
            for issue in package_output_boundary_issues(service_dir, package_root):
                issues.append(f"{_display(service_dir)} {issue}")

    if issues:
        print("[verify_environment_packaging_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_environment_packaging_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
