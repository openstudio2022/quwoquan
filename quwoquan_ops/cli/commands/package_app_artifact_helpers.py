"""Canonical digest, provenance, and receipt validation for App artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)
from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
    artifact_filesystem_identity,
    read_runtime_config_trust_envelope,
    signing_digest,
)
from quwoquan_ops.cli.lib.app_identity import (
    ARTIFACT_METADATA_PATH,
    AppIdentityError,
    application_id_for_build_product,
    resolve_build_product,
)
from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.package_reuse import workspace_snapshot
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_readback,
    load_historical_dependency_projection_cas_evidence,
)

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_TREE_DIGEST = re.compile(r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_FLUTTER_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_BUILD_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "attemptId",
        "buildProductId",
        "sourceCapsuleDigest",
        "sourceStatusDigest",
        "manifestPath",
        "manifestDigest",
        "artifactPath",
        "artifactDigest",
        "buildProvenanceDigest",
        "flutterVersion",
        "commandResolutionDigest",
        "dependencyProjectionExpectationRef",
        "dependencyProjectionExpectationDigest",
        "dependencyProjectionPrebuildReadbackRef",
        "dependencyProjectionPrebuildReadbackDigest",
        "dependencyProjectionPostbuildReadbackRef",
        "dependencyProjectionPostbuildReadbackDigest",
    }
)
_DEPENDENCY_PROJECTION_EVIDENCE_FIELDS = (
    "dependencyProjectionExpectationRef",
    "dependencyProjectionExpectationDigest",
    "dependencyProjectionPrebuildReadbackRef",
    "dependencyProjectionPrebuildReadbackDigest",
    "dependencyProjectionPostbuildReadbackRef",
    "dependencyProjectionPostbuildReadbackDigest",
)
_DEPENDENCY_PROJECTION_EVIDENCE_FILES = {
    "dependencyProjectionExpectationRef": "dependency-projection-expectation.json",
    "dependencyProjectionPrebuildReadbackRef": (
        "dependency-projection-prebuild-readback.json"
    ),
    "dependencyProjectionPostbuildReadbackRef": (
        "dependency-projection-postbuild-readback.json"
    ),
}
_DEPENDENCY_COMPONENT_IDENTITY_FIELDS = {
    "pub": (
        "manifestDigest",
        "treeDigest",
        "entryCount",
        "directoryCount",
        "lockDigest",
    ),
    "iosPods": ("treeDigest", "entryCount", "lockDigest"),
    "androidGradle": ("manifestDigest", "treeDigest", "entryCount"),
}
_DEPENDENCY_COMPONENT_KINDS = {
    "productionPub": "pub",
    "patrolPub": "pub",
    "productionIosPods": "iosPods",
    "patrolIosPods": "iosPods",
    "androidGradle": "androidGradle",
}


@dataclass(frozen=True)
class ValidatedAppArtifactBuildReceipt:
    attempt_dir: Path
    receipt_path: Path
    receipt: dict[str, Any]
    manifest_path: Path
    manifest: dict[str, Any]
    artifact_path: Path
    dependency_evidence: tuple[Path, Path, Path]


def artifact_digest(path: Path) -> str:
    """Hash one stable regular file or directory with the producer algorithm."""

    path = Path(path)
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    if not path.is_dir():
        raise AppArtifactBuildError(f"APP.PACKAGE.artifact_missing: {path}")
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(child.stat().st_size.to_bytes(8, "big"))
        with child.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_provenance_digest(
    *,
    build_product_id: str,
    source_git_sha: str,
    source_tree_digest: str,
    source_capsule_digest: str,
    artifact_digest: str,
    signing_identity_digest: str,
) -> str:
    return _canonical_digest(
        {
            "schema": "app-build-provenance",
            "buildProductId": build_product_id,
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "sourceCapsuleDigest": source_capsule_digest,
            "artifactDigest": artifact_digest,
            "signingIdentityDigest": signing_identity_digest,
        }
    )


def _current_build_input_identity() -> dict[str, str]:
    """Read the source closure and pinned Flutter identity used by the producer."""

    try:
        source = workspace_snapshot(deployment_roots=app_source_capsule_roots())
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=Path(__file__).resolve().parents[3],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        flutter = resolved_flutter_identity(dict(os.environ))
        pubspec = load_json_yaml(
            Path(__file__).resolve().parents[3] / "quwoquan_app/pubspec.yaml"
        )
        version = str(pubspec.get("version") or "")
        display_version, separator, build_number = version.partition("+")
    except (
        FacadeError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            f"current App build input identity is unavailable: {error}"
        ) from error
    return {
        "sourceGitSha": str(source.get("sourceRevision") or ""),
        "sourceTreeDigest": "sha1:" + tree,
        "sourceCapsuleDigest": str(source.get("deploymentInputDigest") or ""),
        "sourceStatusDigest": str(source.get("workspaceStatusDigest") or ""),
        "flutterVersion": str(flutter.get("flutterVersion") or ""),
        "commandResolutionDigest": str(flutter.get("commandResolutionDigest") or ""),
        "displayVersion": display_version,
        "buildNumber": build_number if separator else "1",
    }


def _expected_manifest_identity(build_product_id: str) -> dict[str, object]:
    try:
        product = resolve_build_product(build_product_id)
        metadata = load_json_yaml(ARTIFACT_METADATA_PATH)
        classes = metadata.get("distribution_classes")
        declaration = (
            classes.get(product.distribution_class)
            if isinstance(classes, Mapping)
            else None
        )
        if not isinstance(declaration, Mapping):
            raise TypeError("distribution class declaration is missing")
        application_id = application_id_for_build_product(build_product_id)
    except (AppIdentityError, OSError, TypeError, ValueError) as error:
        raise ValueError(
            f"AppArtifactManifest identity cannot be resolved: {error}"
        ) from error
    return {
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "distributionClass": product.distribution_class,
        "artifactFormat": product.artifact_format,
        "applicationId": application_id,
        "promotable": bool(declaration.get("promotable"))
        and product.build_mode == "release",
    }


def _artifact_semantic_identity(
    *,
    attempt_dir: Path,
    artifact_path: Path,
    manifest: Mapping[str, Any],
    observed_artifact_digest: str,
) -> tuple[str, str]:
    """Read signing and embedded trust identities from the final artifact."""

    platform = str(manifest.get("platform") or "")
    signing_identity = str(manifest.get("signingIdentityDigest") or "")
    if platform == "web":
        observed_signing = signing_digest(platform, artifact_path)
        return observed_signing, ""
    trust_identity = str(manifest.get("runtimeConfigTrustEnvelopeDigest") or "")
    try:
        readback = read_runtime_config_trust_envelope(
            artifact_root=attempt_dir,
            artifact=artifact_path,
            platform=platform,
            artifact_format=str(manifest.get("artifactFormat") or ""),
            build_profile=str(manifest.get("buildProfile") or ""),
            expected_build_input_digest=trust_identity,
            expected_artifact_digest=observed_artifact_digest,
            expected_artifact_filesystem_identity=artifact_filesystem_identity(
                artifact_path
            ),
            expected_signing_identity_digest=signing_identity,
        )
    except AppArtifactBuildError as error:
        raise ValueError(f"App artifact semantic readback failed: {error}") from error
    return (
        readback.signing_identity_digest,
        readback.runtime_config_trust_envelope_digest,
    )


def _regular_file(path: Path, *, label: str, private: bool = False) -> Path:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(f"{label} is not a single-link regular file")
    if private and stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError(f"{label} is not canonical private evidence")
    return path


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    _regular_file(path, label=label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be a JSON object")
    return payload


def _validate_artifact_path_safety(path: Path) -> None:
    try:
        root = path.lstat()
    except OSError as error:
        raise ValueError("artifactPath is unavailable") from error
    if stat.S_ISREG(root.st_mode):
        if root.st_nlink != 1:
            raise ValueError("artifactPath is a linked file")
        return
    if not stat.S_ISDIR(root.st_mode):
        raise ValueError("artifactPath is linked or not a regular artifact")
    for child in path.rglob("*"):
        metadata = child.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("artifactPath contains a linked or special entry")


def _attempt_scoped_path(
    value: object,
    *,
    field: str,
    attempt_dir: Path,
    expected_name: str | None = None,
) -> Path:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} is missing or invalid")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} is not absolute")
    path = Path(path.absolute())
    if path.parent != attempt_dir or (
        expected_name is not None and path.name != expected_name
    ):
        raise ValueError(f"{field} is not bound to the build attempt")
    return path


def _dependency_evidence_path(
    value: object,
    *,
    field: str,
    attempt_dir: Path,
) -> Path:
    path = _attempt_scoped_path(
        value,
        field=field,
        attempt_dir=attempt_dir,
        expected_name=_DEPENDENCY_PROJECTION_EVIDENCE_FILES[field],
    )
    return _regular_file(path, label=field, private=True)


def _expected_dependency_components(
    components: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for name, raw in components.items():
        component = str(name)
        if not isinstance(raw, Mapping):
            raise TypeError(f"dependency component {component} is invalid")
        kind = str(raw.get("kind") or "")
        fields = _DEPENDENCY_COMPONENT_IDENTITY_FIELDS.get(kind)
        if fields is None or _DEPENDENCY_COMPONENT_KINDS.get(component) != kind:
            raise ValueError(f"dependency component {component} kind is invalid")
        identity = {field: raw.get(field) for field in fields}
        for field, value in identity.items():
            if field.endswith("Digest"):
                if _DIGEST.fullmatch(str(value or "")) is None:
                    raise ValueError(
                        f"dependency component {component} {field} is invalid"
                    )
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"dependency component {component} {field} is invalid")
        expected[component] = identity
    return expected


def validate_dependency_projection_receipt(
    receipt: Mapping[str, Any],
    attempt_dir: Path,
    *,
    expected_source_capsule_digest: str | None = None,
) -> tuple[Path, Path, Path]:
    """Fail closed unless one receipt binds a canonical historical CAS triplet."""

    values = {
        field: receipt.get(field) for field in _DEPENDENCY_PROJECTION_EVIDENCE_FIELDS
    }
    invalid = [
        field
        for field, value in values.items()
        if (
            not isinstance(value, str)
            or not value
            or value.strip() != value
            or (field.endswith("Digest") and _DIGEST.fullmatch(value) is None)
        )
    ]
    if invalid:
        raise ValueError(
            "dependency projection receipt fields are missing or invalid: "
            + ", ".join(invalid)
        )
    paths = {
        field: _dependency_evidence_path(
            values[field],
            field=field,
            attempt_dir=attempt_dir,
        )
        for field in _DEPENDENCY_PROJECTION_EVIDENCE_FILES
    }
    if len(set(paths.values())) != len(paths):
        raise ValueError("dependency projection evidence references overlap")
    try:
        expectation = load_historical_dependency_projection_cas_evidence(
            evidence_path=paths["dependencyProjectionExpectationRef"],
            expected_digest=values["dependencyProjectionExpectationDigest"],
        )
        prebuild = load_dependency_projection_cas_readback(
            evidence_path=paths["dependencyProjectionPrebuildReadbackRef"],
            expected_digest=values["dependencyProjectionPrebuildReadbackDigest"],
            expected_expectation_digest=expectation.evidence_digest,
        )
        postbuild = load_dependency_projection_cas_readback(
            evidence_path=paths["dependencyProjectionPostbuildReadbackRef"],
            expected_digest=values["dependencyProjectionPostbuildReadbackDigest"],
            expected_expectation_digest=expectation.evidence_digest,
        )
        source = expectation.manifest.get("source")
        components = expectation.manifest.get("components")
        projection_root = expectation.manifest.get("projectionRoot")
        if (
            not isinstance(projection_root, str)
            or not Path(projection_root).is_absolute()
            or not isinstance(source, Mapping)
            or not isinstance(components, Mapping)
        ):
            raise ValueError("dependency expectation identity is invalid")
        source_manifest_digest = str(source.get("manifestDigest") or "")
        source_input_digest = str(source.get("inputDigest") or "")
        if (
            _DIGEST.fullmatch(source_manifest_digest) is None
            or _DIGEST.fullmatch(source_input_digest) is None
        ):
            raise ValueError("dependency expectation source identity is invalid")
        if (
            expected_source_capsule_digest is not None
            and source_input_digest != expected_source_capsule_digest
        ):
            raise ValueError("dependency expectation source capsule identity drifted")
        expected_readback_identity = {
            "projectionRoot": projection_root,
            "sourceManifestDigest": source_manifest_digest,
            "components": _expected_dependency_components(components),
        }
        for phase, readback in (("prebuild", prebuild), ("postbuild", postbuild)):
            actual = {
                field: readback.manifest.get(field)
                for field in expected_readback_identity
            }
            if actual != expected_readback_identity:
                raise ValueError(f"dependency {phase} readback identity drifted")
        if prebuild.manifest != postbuild.manifest:
            raise ValueError("dependency pre/post readback identity drifted")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        detail = str(error) or type(error).__name__
        raise ValueError(f"dependency projection evidence invalid: {detail}") from error
    return (
        paths["dependencyProjectionExpectationRef"],
        paths["dependencyProjectionPrebuildReadbackRef"],
        paths["dependencyProjectionPostbuildReadbackRef"],
    )


def validate_app_artifact_build_receipt(
    *,
    attempt_dir: Path,
    expected_build_product_id: str,
    expected_manifest: Mapping[str, Any],
) -> ValidatedAppArtifactBuildReceipt:
    """Bind one producer attempt, manifest, artifact, SDK, source, and CAS exactly."""

    attempt_dir = Path(attempt_dir).expanduser()
    if not attempt_dir.is_absolute():
        raise ValueError("stackctl App build attempt path is not absolute")
    attempt_dir = Path(attempt_dir.absolute())
    try:
        attempt_metadata = attempt_dir.lstat()
    except OSError as error:
        raise ValueError("stackctl App build attempt is unavailable") from error
    if not stat.S_ISDIR(attempt_metadata.st_mode):
        raise ValueError("stackctl App build attempt is linked or invalid")

    receipt_path = _regular_file(
        attempt_dir / "build-receipt.json",
        label="App build receipt",
    )
    receipt = _read_json_object(receipt_path, label="App build receipt")
    missing = sorted(_BUILD_RECEIPT_FIELDS - set(receipt))
    extra = sorted(set(receipt) - _BUILD_RECEIPT_FIELDS)
    if missing or extra:
        raise ValueError(
            "App build receipt fields are not canonical: "
            f"missing={missing}, extra={extra}"
        )
    if receipt.get("schema") != "app-artifact-build-receipt":
        raise ValueError("App build receipt schema mismatch")
    attempt_id = str(receipt.get("attemptId") or "")
    if _UUID.fullmatch(attempt_id) is None or attempt_dir.name != attempt_id:
        raise ValueError(
            "App build receipt attemptId does not bind its attempt directory"
        )
    if (
        receipt.get("buildProductId") != expected_build_product_id
        or attempt_dir.parent.name != expected_build_product_id
    ):
        raise ValueError("App build receipt buildProductId does not bind its attempt")

    manifest_path = _attempt_scoped_path(
        receipt["manifestPath"],
        field="manifestPath",
        attempt_dir=attempt_dir,
        expected_name="manifest.json",
    )
    manifest = _read_json_object(manifest_path, label="AppArtifactManifest")
    if manifest != dict(expected_manifest):
        raise ValueError(
            "App build receipt manifest does not match the stackctl result"
        )
    manifest_digest = artifact_digest(manifest_path)
    if receipt.get("manifestDigest") != manifest_digest:
        raise ValueError(
            "App build receipt manifestDigest does not bind current manifest bytes"
        )
    if (
        manifest.get("schema") != "app-artifact-manifest"
        or manifest.get("buildProductId") != expected_build_product_id
    ):
        raise ValueError("AppArtifactManifest identity does not bind the build receipt")
    expected_identity = _expected_manifest_identity(expected_build_product_id)
    drifted_manifest_identity = [
        field
        for field, expected in expected_identity.items()
        if manifest.get(field) != expected
    ]
    if drifted_manifest_identity:
        raise ValueError(
            "AppArtifactManifest product identity drifted: "
            + ", ".join(drifted_manifest_identity)
        )

    artifact_path = _attempt_scoped_path(
        receipt["artifactPath"],
        field="artifactPath",
        attempt_dir=attempt_dir,
    )
    _validate_artifact_path_safety(artifact_path)
    observed_artifact_digest = artifact_digest(artifact_path)
    if (
        receipt.get("artifactDigest") != observed_artifact_digest
        or manifest.get("artifactDigest") != observed_artifact_digest
    ):
        raise ValueError(
            "App build receipt artifactDigest does not bind current artifact"
        )

    digest_fields = (
        "sourceCapsuleDigest",
        "sourceStatusDigest",
        "manifestDigest",
        "artifactDigest",
        "buildProvenanceDigest",
        "commandResolutionDigest",
    )
    invalid_digests = [
        field
        for field in digest_fields
        if _DIGEST.fullmatch(str(receipt.get(field) or "")) is None
    ]
    if invalid_digests:
        raise ValueError(
            "App build receipt digests are invalid: " + ", ".join(invalid_digests)
        )
    if _GIT_SHA.fullmatch(str(manifest.get("sourceGitSha") or "")) is None or (
        _TREE_DIGEST.fullmatch(str(manifest.get("sourceTreeDigest") or "")) is None
    ):
        raise ValueError("App build receipt source identity is invalid")
    flutter_version = str(receipt.get("flutterVersion") or "")
    if _FLUTTER_VERSION.fullmatch(flutter_version) is None:
        raise ValueError("App build receipt Flutter SDK identity is invalid")
    signing_digest = str(manifest.get("signingIdentityDigest") or "")
    if _DIGEST.fullmatch(signing_digest) is None:
        raise ValueError("AppArtifactManifest signing identity is invalid")
    platform = str(manifest.get("platform") or "")
    trust_digest = str(manifest.get("runtimeConfigTrustEnvelopeDigest") or "")
    if platform in {"android", "ios"}:
        if _DIGEST.fullmatch(trust_digest) is None:
            raise ValueError("AppArtifactManifest runtime trust identity is invalid")
    elif platform == "web":
        if "runtimeConfigTrustEnvelopeDigest" in manifest:
            raise ValueError(
                "Web AppArtifactManifest must not claim embedded runtime trust"
            )
    else:
        raise ValueError("AppArtifactManifest platform is invalid")

    current = _current_build_input_identity()
    claimed_inputs = {
        "sourceGitSha": str(manifest.get("sourceGitSha") or ""),
        "sourceTreeDigest": str(manifest.get("sourceTreeDigest") or ""),
        "sourceCapsuleDigest": str(receipt.get("sourceCapsuleDigest") or ""),
        "sourceStatusDigest": str(receipt.get("sourceStatusDigest") or ""),
        "flutterVersion": flutter_version,
        "commandResolutionDigest": str(receipt.get("commandResolutionDigest") or ""),
        "displayVersion": str(manifest.get("displayVersion") or ""),
        "buildNumber": str(manifest.get("buildNumber") or ""),
    }
    drifted_inputs = [
        field
        for field, claimed in claimed_inputs.items()
        if current.get(field) != claimed
    ]
    if drifted_inputs:
        raise ValueError(
            "App build receipt source/toolchain identity drifted: "
            + ", ".join(drifted_inputs)
        )

    observed_signing, observed_trust = _artifact_semantic_identity(
        attempt_dir=attempt_dir,
        artifact_path=artifact_path,
        manifest=manifest,
        observed_artifact_digest=observed_artifact_digest,
    )
    if observed_signing != signing_digest:
        raise ValueError("AppArtifactManifest signing identity does not bind artifact")
    if platform in {"android", "ios"} and observed_trust != trust_digest:
        raise ValueError("AppArtifactManifest runtime trust does not bind artifact")
    provenance = build_provenance_digest(
        build_product_id=expected_build_product_id,
        source_git_sha=str(manifest["sourceGitSha"]),
        source_tree_digest=str(manifest["sourceTreeDigest"]),
        source_capsule_digest=str(receipt["sourceCapsuleDigest"]),
        artifact_digest=observed_artifact_digest,
        signing_identity_digest=signing_digest,
    )
    if (
        receipt.get("buildProvenanceDigest") != provenance
        or manifest.get("buildProvenanceDigest") != provenance
    ):
        raise ValueError(
            "App build receipt provenance does not bind source and artifact"
        )
    dependency_evidence = validate_dependency_projection_receipt(
        receipt,
        attempt_dir,
        expected_source_capsule_digest=str(receipt["sourceCapsuleDigest"]),
    )
    return ValidatedAppArtifactBuildReceipt(
        attempt_dir=attempt_dir,
        receipt_path=receipt_path,
        receipt=receipt,
        manifest_path=manifest_path,
        manifest=manifest,
        artifact_path=artifact_path,
        dependency_evidence=dependency_evidence,
    )
