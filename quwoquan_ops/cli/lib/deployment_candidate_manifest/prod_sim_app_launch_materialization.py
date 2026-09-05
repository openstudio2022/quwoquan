"""Materialize the exact prod-sim App launch closure into a candidate."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

def _canonical_file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_prod_sim_app_launch_bundle_impl(
    *,
    candidate_root: Path,
    package_snapshot: Mapping[str, object],
    materialized_release_evidence: Mapping[str, str],
    source_root: Path,
) -> dict[str, Any]:
    """Copy one exact Android Prod Release launch closure into the candidate."""

    artifact_root_value = os.environ.get("QWQ_PROD_RELEASE_ARTIFACT_ROOT", "").strip()
    if not artifact_root_value:
        raise FileNotFoundError("prod-sim release artifact root is required")
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = source_root / artifact_root
    artifact_root = artifact_root.resolve()
    release_manifest_path = artifact_root / "manifest.json"
    if release_manifest_path.is_symlink() or not release_manifest_path.is_file():
        raise FileNotFoundError("prod-sim release artifact manifest is missing or unsafe")
    from quwoquan_ops.cli import stackctl as _stackctl

    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    _stackctl.finalize_mainline_release_artifact.validate_manifest(
        release_manifest,
        allowed_statuses={"main-admitted", "released"},
    )
    _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
        artifact_root,
        release_manifest,
    )
    source = release_manifest.get("source")
    release_source = {
        "releaseCompositionId": str(release_manifest.get("releaseCompositionId") or ""),
        "artifactDigest": str(release_manifest.get("artifactDigest") or ""),
        "sourceGitSha": str(source.get("gitSha") or "") if isinstance(source, Mapping) else "",
        "sourceTreeDigest": str(source.get("treeDigest") or "") if isinstance(source, Mapping) else "",
    }
    if dict(materialized_release_evidence) != release_source:
        raise ValueError("prod-sim release evidence identity drifted during package")
    applications = release_manifest.get("applicationPackages")
    descriptor = (
        applications.get("android-prod-apk")
        if isinstance(applications, Mapping)
        else None
    )
    if not isinstance(descriptor, Mapping):
        raise ValueError("prod-sim android-prod-apk release package is missing")
    evidence_path = artifact_root / str(descriptor.get("path") or "")
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise ValueError("prod-sim android-prod-apk evidence is missing or unsafe")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    manifest_payload = evidence.get("artifactManifest") if isinstance(evidence, Mapping) else None
    if not isinstance(manifest_payload, dict):
        raise ValueError("prod-sim android-prod-apk artifact manifest is missing")
    if (
        evidence.get("sourceGitSha") != release_source["sourceGitSha"]
        or evidence.get("sourceTreeDigest") != release_source["sourceTreeDigest"]
        or manifest_payload.get("sourceGitSha") != release_source["sourceGitSha"]
        or manifest_payload.get("sourceTreeDigest") != release_source["sourceTreeDigest"]
    ):
        raise ValueError("prod-sim App evidence source identity drifted")
    payload_root = artifact_root / "packages/applications/android-prod-apk"
    build_receipt_source = payload_root / "build-receipt.json"
    artifact_manifest_source = payload_root / "manifest.json"
    if not artifact_manifest_source.is_file():
        artifact_manifest_source = payload_root / "artifact-manifest.json"
    if not build_receipt_source.is_file() or not artifact_manifest_source.is_file():
        raise ValueError("prod-sim App package lacks canonical build receipt or manifest")
    observed_manifest = json.loads(artifact_manifest_source.read_text(encoding="utf-8"))
    if observed_manifest != manifest_payload:
        raise ValueError("prod-sim App payload manifest differs from release evidence")
    receipt = json.loads(build_receipt_source.read_text(encoding="utf-8"))
    artifact_source = payload_root / Path(str(receipt.get("artifactPath") or "")).name
    if not artifact_source.is_file():
        candidates = [
            path
            for path in payload_root.iterdir()
            if path.is_file() and path.suffix == ".apk"
        ]
        if len(candidates) != 1:
            raise ValueError("prod-sim App package exact APK is missing or ambiguous")
        artifact_source = candidates[0]
    launch_root = candidate_root / "packages/app/prod-sim-launch"
    if launch_root.exists() or launch_root.is_symlink():
        raise ValueError("prod-sim App launch bundle already exists")
    launch_root.mkdir(parents=True)
    artifact_manifest_path = launch_root / "manifest.json"
    build_receipt_path = launch_root / "build-receipt.json"
    artifact_path = launch_root / "app-release.apk"
    launcher_handoff_path = launch_root / "launcher-handoff.json"
    shutil.copyfile(artifact_manifest_source, artifact_manifest_path)
    shutil.copyfile(artifact_source, artifact_path)
    copied_receipt = dict(receipt)
    copied_receipt["manifestPath"] = str(artifact_manifest_path)
    copied_receipt["artifactPath"] = str(artifact_path)
    copied_receipt["manifestDigest"] = _canonical_file_digest(artifact_manifest_path)
    copied_receipt["artifactDigest"] = _canonical_file_digest(artifact_path)
    dependency_refs = (
        "dependencyProjectionExpectationRef",
        "dependencyProjectionPrebuildReadbackRef",
        "dependencyProjectionPostbuildReadbackRef",
    )
    for field in dependency_refs:
        source_value = Path(str(receipt.get(field) or ""))
        source_path = source_value if source_value.is_absolute() else payload_root / source_value
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError(f"prod-sim App package {field} is missing or unsafe")
        destination = launch_root / source_path.name
        shutil.copyfile(source_path, destination)
        os.chmod(destination, 0o600)
        copied_receipt[field] = str(destination)
    build_receipt_path.write_text(
        json.dumps(copied_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    handoff_source = payload_root / "launcher-handoff.json"
    if not handoff_source.is_file():
        raise ValueError("prod-sim App package canonical launcher handoff is missing")
    shutil.copyfile(handoff_source, launcher_handoff_path)
    handoff = json.loads(launcher_handoff_path.read_text(encoding="utf-8"))
    runtime_package = handoff.get("runtimeConfigPackage")
    if (
        handoff.get("environment") != "prod"
        or handoff.get("target") != "prod-sim"
        or not isinstance(runtime_package, Mapping)
        or runtime_package.get("sourceGitSha") != release_source["sourceGitSha"]
        or runtime_package.get("sourceTreeDigest") != release_source["sourceTreeDigest"]
    ):
        raise ValueError("prod-sim launcher handoff source identity drifted")
    refs = {
        "artifactManifestRef": artifact_manifest_path,
        "buildReceiptRef": build_receipt_path,
        "artifactRef": artifact_path,
        "launcherHandoffRef": launcher_handoff_path,
    }
    return {
        "schema": "stackctl-prod-sim-app-launch-bundle.v1",
        "candidateDigest": "",
        "baselineId": str(package_snapshot.get("baselineId") or ""),
        "sourceGitSha": release_source["sourceGitSha"],
        "sourceTreeDigest": release_source["sourceTreeDigest"],
        "sourceStatusDigest": str(package_snapshot.get("workspaceStatusDigest") or ""),
        **{
            field: path.relative_to(candidate_root).as_posix()
            for field, path in refs.items()
        },
        "artifactManifestDigest": _canonical_file_digest(artifact_manifest_path),
        "buildReceiptDigest": _canonical_file_digest(build_receipt_path),
        "artifactDigest": _canonical_file_digest(artifact_path),
        "launcherHandoffDigest": _canonical_file_digest(launcher_handoff_path),
    }


