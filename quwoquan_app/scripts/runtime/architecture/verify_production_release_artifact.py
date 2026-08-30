#!/usr/bin/env python3
"""Fail closed on test-only provenance or payloads in a production App artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

ROOT = REPO_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

FORBIDDEN_MARKERS = (
    b"quwoquan_cloud_mock",
    b"MockContentRepository",
    b"CONTRACT_FIXTURE_PROFILE",
    b"test_fixtures/",
    b"runners/alpha/",
    b"alpha_cloud_composition",
    b"patrol",
    b"integration_test",
    b"PatrolJUnitRunner",
    b"RunnerUITests",
    b"XCTest",
)
MAX_ENTRY_BYTES = 128 * 1024 * 1024
MACHO_MAGICS = {
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_artifact_entries(path: Path) -> Iterable[tuple[str, bytes]]:
    if path.is_dir():
        for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
            relative = file_path.relative_to(path).as_posix()
            if file_path.stat().st_size > MAX_ENTRY_BYTES:
                raise ValueError(f"artifact entry exceeds scan limit: {relative}")
            yield relative, file_path.read_bytes()
        return

    if not zipfile.is_zipfile(path):
        raise ValueError(f"production artifact must be a directory or ZIP container: {path}")
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                raise ValueError(
                    f"artifact entry exceeds scan limit: {info.filename} ({info.file_size} bytes)"
                )
            yield info.filename, archive.read(info)


def artifact_contains(path: Path, marker: bytes) -> bool:
    return any(marker in payload for _, payload in iter_artifact_entries(path))


def missing_ios_rpath_dependencies(app_path: Path) -> list[str]:
    """Resolve every Mach-O @rpath payload against the final .app bundle."""

    findings: set[str] = set()
    for binary in sorted(item for item in app_path.rglob("*") if item.is_file()):
        try:
            with binary.open("rb") as source:
                if source.read(4) not in MACHO_MAGICS:
                    continue
            result = subprocess.run(
                ["otool", "-L", str(binary)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        for raw_line in result.stdout.splitlines()[1:]:
            dependency = raw_line.strip().split(" (", 1)[0]
            if not dependency.startswith("@rpath/"):
                continue
            relative = dependency.removeprefix("@rpath/")
            candidates = (app_path / relative, app_path / "Frameworks" / relative)
            if not any(candidate.is_file() for candidate in candidates):
                findings.add(
                    f"{binary.relative_to(app_path).as_posix()} -> {dependency}"
                )
    return sorted(findings)


def scan_artifact(path: Path, platform: str) -> tuple[list[str], dict[str, object]]:
    findings: list[str] = []
    scanned_entries: list[dict[str, object]] = []
    for name, payload in iter_artifact_entries(path):
        normalized_name = name.replace("\\", "/")
        scanned_entries.append(
            {
                "path": normalized_name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "sizeBytes": len(payload),
            }
        )
        searchable = normalized_name.encode("utf-8", errors="replace") + b"\n" + payload
        for marker in FORBIDDEN_MARKERS:
            if marker in searchable:
                findings.append(
                    f"{path}: production {platform} artifact contains forbidden marker "
                    f"{marker.decode('ascii')} in {normalized_name}"
                )
    if platform == "ios" and path.is_dir():
        findings.extend(
            f"{path}: production ios artifact has unresolved runtime dependency {item}"
            for item in missing_ios_rpath_dependencies(path)
        )
    public_web_base = str(
        get_target(load_environment_topology(), "prod-hosted")["publicBases"][
            "publicWeb"
        ]
    ).rstrip("/")
    return findings, {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "name": f"quwoquan-{platform}-production-artifact",
        "dataLicense": "CC0-1.0",
        "documentNamespace": (
            f"{public_web_base}/sbom/"
            + sha256_file(path)
            if path.is_file()
            else f"{public_web_base}/sbom/{platform}-directory"
        ),
        "files": scanned_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("android", "ios", "web"), required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--launcher-handoff", default="")
    args = parser.parse_args()

    artifact = Path(args.artifact).resolve()
    report_path = Path(args.report)
    findings: list[str] = []
    if not artifact.exists():
        findings.append(f"production artifact is missing: {artifact}")
        sbom: dict[str, object] = {}
    else:
        try:
            findings, sbom = scan_artifact(artifact, args.platform)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            findings.append(str(error))
            sbom = {}

    handoff_path = Path(args.launcher_handoff).resolve() if args.launcher_handoff else None
    handoff: dict[str, object] = {}
    if handoff_path is not None:
        try:
            decoded = json.loads(handoff_path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict):
                raise TypeError("launcher handoff must be an object")
            handoff = decoded
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            findings.append(f"launcher handoff is invalid: {error}")
        else:
            if (
                handoff.get("schema") != "app-launcher-handoff"
                or handoff.get("environment") != "prod"
                or handoff.get("target") != "prod-hosted"
                or handoff.get("entrypoint") != "lib/main_prod.dart"
            ):
                findings.append(
                    "production artifact launcher handoff must bind "
                    "prod/prod-hosted/lib/main_prod.dart"
                )
            transport = handoff.get("transport")
            if not isinstance(transport, dict) or transport.get("required") is not False:
                findings.append(
                    "production artifact launcher handoff must explicitly disable local transport"
                )
            elif any(
                value
                for key, value in transport.items()
                if key != "required"
            ):
                findings.append(
                    "production artifact launcher handoff contains local transport evidence"
                )
            effective_manifest = handoff.get("effectiveLaunchManifest")
            effective_digest = str(
                handoff.get("effectiveLaunchManifestDigest") or ""
            )
            if not isinstance(effective_manifest, dict):
                findings.append(
                    "production artifact effective launch manifest is missing"
                )
            else:
                encoded = json.dumps(
                    effective_manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                expected_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
                if effective_digest != expected_digest:
                    findings.append(
                        "production artifact effective launch manifest digest mismatches"
                    )
                for key in (
                    "environment",
                    "buildProfile",
                    "target",
                    "entrypoint",
                    "launchProvenance",
                    "runtimeConfigSupplyMode",
                    "launchPolicy",
                    "runtimeConfigPackageDigest",
                    "runtimeConfigTrustEnvelopeDigest",
                    "requiresLocalTransport",
                    "transport",
                ):
                    if handoff.get(key) != effective_manifest.get(key):
                        findings.append(
                            f"launcher handoff disagrees with effective manifest: {key}"
                        )
                if (
                    artifact.exists()
                    and effective_digest
                    and not artifact_contains(
                        artifact,
                        effective_digest.encode("ascii"),
                    )
                ):
                    findings.append(
                        "production artifact does not embed its effective launch manifest digest"
                    )
    provenance = {
        "sourceRevision": os.environ.get("GITHUB_SHA", "").strip() or "local",
        "runtimeEnvironment": os.environ.get("QWQ_APP_RUNTIME_ENV", "").strip(),
        "platform": args.platform,
        "artifact": str(artifact),
        "artifactSha256": sha256_file(artifact) if artifact.is_file() else "",
        "launcherHandoffSha256": (
            f"sha256:{sha256_file(handoff_path)}"
            if handoff_path is not None and handoff_path.is_file()
            else ""
        ),
        "launchTarget": str(handoff.get("target") or ""),
        "runtimeConfigPackageDigest": str(
            handoff.get("runtimeConfigPackageDigest") or ""
        ),
        "effectiveLaunchManifestDigest": str(
            handoff.get("effectiveLaunchManifestDigest") or ""
        ),
    }
    if provenance["runtimeEnvironment"] != "prod":
        findings.append("production artifact verification requires QWQ_APP_RUNTIME_ENV=prod")

    report = {
        "status": "passed" if not findings else "failed",
        "platform": args.platform,
        "artifact": str(artifact),
        "provenance": provenance,
        "sbom": sbom,
        "findings": findings,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
