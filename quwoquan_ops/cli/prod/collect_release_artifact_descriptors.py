#!/usr/bin/env python3
"""Collect immutable whole-application and qualification evidence without fabrication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    ENVIRONMENTS,
    OCI_DIGEST_REF_PATTERN,
    RELEASE_CLOSURE_PATHS,
    TEST_RELEASE_CLOSURE_LABELS,
    application_package_digest,
    sha256_tree,
    validate_application_package_payload,
    validate_manifest,
    validate_manifest_files,
)
from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)

EVIDENCE_SOURCE_SCHEMAS = {
    "publicWeb": "qwq.public-web.release",
    "androidOfficialRelease": "qwq.android.official-release",
    "opsPortal": "qwq.ops_portal_package",
    "contractGraph": "qwq.contract-graph",
    "providerEvidence": "provider-conformance-readiness",
    "testEvidence": "qwq.three-layer-case-results",
}
APPLICATION_SOURCE_TARGETS = {
    "publicWeb": ("prod", "web"),
    "androidOfficialRelease": ("prod", "android"),
    "opsPortal": ("prod", "opsPortal"),
}
GENERIC_APPLICATION_SCHEMA = "release-application-package"
GENERIC_APPLICATION_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "surface",
        "sourceGitSha",
        "sourceTreeDigest",
        "packageDigest",
    }
)
ALL_APPLICATION_KEYS = frozenset(
    (environment, surface)
    for environment in ENVIRONMENTS
    for surface in APPLICATION_PACKAGES[environment]
)
GENERIC_APPLICATION_KEYS = ALL_APPLICATION_KEYS - frozenset(
    APPLICATION_SOURCE_TARGETS.values()
)
EVIDENCE_DESTINATIONS = {
    "publicWeb": "packages/applications/prod/web/manifest.json",
    "androidOfficialRelease": "packages/applications/prod/android/manifest.json",
    "opsPortal": "packages/applications/prod/opsPortal/provenance.json",
    "contractGraph": "evidence/contractGraph.json",
    "providerEvidence": "evidence/providerEvidence.json",
    "testEvidence": "evidence/testEvidence.json",
}

DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--descriptors-dir", required=True, type=Path)
    parser.add_argument("--application-packages-dir", required=True, type=Path)
    parser.add_argument(
        "--application-package-payloads-dir", required=True, type=Path
    )
    parser.add_argument("--public-web-manifest", required=True, type=Path)
    parser.add_argument("--android-release-manifest", required=True, type=Path)
    parser.add_argument("--ops-portal-provenance", required=True, type=Path)
    parser.add_argument("--contract-graph", required=True, type=Path)
    parser.add_argument("--provider-evidence", required=True, type=Path)
    parser.add_argument("--provider-raw-dir", required=True, type=Path)
    parser.add_argument("--test-evidence", required=True, type=Path)
    parser.add_argument("--application-evidence-ref", required=True)
    return parser.parse_args()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable UTF-8 JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_source(artifact_id: str, payload: dict[str, Any]) -> None:
    expected_schema = EVIDENCE_SOURCE_SCHEMAS[artifact_id]
    if payload.get("schema") != expected_schema:
        raise ValueError(
            f"{artifact_id} schema mismatch: {payload.get('schema')!r} != "
            f"{expected_schema!r}"
        )
    if artifact_id == "contractGraph":
        required = {"sources", "documents", "objects", "operations", "projections"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"contractGraph missing canonical collections: {missing}")
        return
    if artifact_id == "testEvidence":
        if payload.get("status") != "passed":
            raise ValueError("testEvidence status must be passed")
        layers = payload.get("layers")
        required_layers = {"local_contract", "api_integration", "user_acceptance"}
        if not isinstance(layers, dict) or set(layers) != required_layers:
            raise ValueError("testEvidence must contain exactly the three canonical layers")
        for layer in sorted(required_layers):
            item = layers.get(layer)
            if (
                not isinstance(item, dict)
                or item.get("status") != "passed"
                or DIGEST_PATTERN.fullmatch(str(item.get("artifactDigest") or "")) is None
            ):
                raise ValueError(f"testEvidence layer is not passed and immutable: {layer}")
        evidence = payload.get("evidence")
        files = evidence.get("files") if isinstance(evidence, dict) else None
        if not isinstance(files, dict) or set(files) != set(
            TEST_RELEASE_CLOSURE_LABELS
        ):
            raise ValueError("testEvidence release closure file set is incomplete")
        for label, descriptor in files.items():
            if (
                not isinstance(descriptor, dict)
                or set(descriptor) != {"path", "digest"}
                or descriptor.get("path") != RELEASE_CLOSURE_PATHS[label]
                or DIGEST_PATTERN.fullmatch(str(descriptor.get("digest") or ""))
                is None
            ):
                raise ValueError(
                    f"testEvidence release closure descriptor is invalid: {label}"
                )


def _resolve_test_evidence_files(
    *,
    payload: dict[str, Any],
    source_path: Path,
) -> dict[str, tuple[Path, str]]:
    source_path = source_path.expanduser()
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("testEvidence source is missing or unsafe")
    source_root = source_path.resolve(strict=True).parent
    files = payload["evidence"]["files"]
    resolved: dict[str, tuple[Path, str]] = {}
    for label, descriptor in sorted(files.items()):
        relative = Path(str(descriptor["path"]))
        if (
            relative.is_absolute()
            or "." in relative.parts
            or ".." in relative.parts
        ):
            raise ValueError(
                f"testEvidence release closure path is unsafe: {label}"
            )
        candidate = source_root / relative
        if candidate.is_symlink():
            raise ValueError(
                f"testEvidence release closure is a symbolic link: {label}"
            )
        source = candidate.resolve(strict=True)
        try:
            source.relative_to(source_root)
        except ValueError as error:
            raise ValueError(
                f"testEvidence release closure escapes its source root: {label}"
            ) from error
        if not source.is_file() or _sha256(source) != descriptor["digest"]:
            raise ValueError(
                f"testEvidence release closure digest mismatch: {label}"
            )
        resolved[label] = (source, relative.as_posix())
    return resolved


def _validate_provider_evidence(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    contract_graph_digest: str,
    provider_raw_dir: Path,
) -> None:
    if set(payload) != {
        "schema",
        "status",
        "generatedAt",
        "source",
        "candidateMaterial",
        "sourceEvidence",
        "evidenceCount",
        "sourceCoverageIssues",
        "readiness",
        "issues",
    }:
        raise ValueError("providerEvidence fields are not canonical")
    if payload.get("schema") != EVIDENCE_SOURCE_SCHEMAS["providerEvidence"]:
        raise ValueError("providerEvidence schema mismatch")
    if payload.get("status") != "passed":
        raise ValueError("providerEvidence status must be passed")
    if not isinstance(payload.get("generatedAt"), str) or not payload["generatedAt"]:
        raise ValueError("providerEvidence generatedAt is missing")
    if payload.get("issues") != [] or payload.get("sourceCoverageIssues") != []:
        raise ValueError("providerEvidence readiness issues must be empty")
    expected_evidence_count = expected_required_cell_count_from_readiness(
        payload.get("readiness")
    )
    if payload.get("evidenceCount") != expected_evidence_count:
        raise ValueError(
            "providerEvidence evidenceCount must equal the readiness-derived "
            f"required cell count {expected_evidence_count}"
        )
    source = payload.get("source")
    manifest_source = manifest["source"]
    expected_source = {
        key: manifest_source[key]
        for key in ("gitSha", "treeDigest", "repository", "workflowRunId")
    }
    if source != expected_source:
        raise ValueError("providerEvidence source binding mismatch")
    source_evidence = payload.get("sourceEvidence")
    if (
        not isinstance(source_evidence, dict)
        or set(source_evidence) != {"ref", "digest", "files"}
        or OCI_DIGEST_REF_PATTERN.fullmatch(
            str(source_evidence.get("ref") or "")
        )
        is None
        or source_evidence.get("ref")
        != str(source_evidence.get("ref") or "").rsplit("@", 1)[0]
        + "@"
        + str(source_evidence.get("digest") or "")
        or not isinstance(source_evidence.get("files"), dict)
        or len(source_evidence["files"]) != payload["evidenceCount"]
    ):
        raise ValueError("providerEvidence sourceEvidence is not canonical")
    raw_root = provider_raw_dir.expanduser().resolve()
    for archive_path, digest in source_evidence["files"].items():
        prefix = "evidence/raw/provider/"
        if (
            not isinstance(archive_path, str)
            or not archive_path.startswith(prefix)
            or DIGEST_PATTERN.fullmatch(str(digest or "")) is None
        ):
            raise ValueError("providerEvidence raw file descriptor is invalid")
        relative = Path(archive_path.removeprefix(prefix))
        source_path = (raw_root / relative).resolve()
        try:
            source_path.relative_to(raw_root)
        except ValueError as error:
            raise ValueError("providerEvidence raw file escapes its source root") from error
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError(f"providerEvidence raw file is missing: {relative}")
        if _sha256(source_path) != digest:
            raise ValueError(f"providerEvidence raw file digest mismatch: {relative}")
    material = payload.get("candidateMaterial")
    expected_images = {
        service: descriptor["digest"]
        for service, descriptor in sorted(manifest["images"].items())
    }
    if material != {
        "images": expected_images,
        "contractGraphDigest": contract_graph_digest,
    }:
        raise ValueError("providerEvidence candidate material binding mismatch")
def _validate_user_acceptance_candidate_material(
    *,
    test_evidence: dict[str, Any],
    manifest: dict[str, Any],
    contract_graph_path: Path,
    source_payloads: dict[str, dict[str, Any]],
    generic_payloads: dict[tuple[str, str], dict[str, Any]],
) -> None:
    layers = test_evidence.get("layers")
    user_acceptance = (
        layers.get("user_acceptance") if isinstance(layers, dict) else None
    )
    material = (
        user_acceptance.get("candidateMaterial")
        if isinstance(user_acceptance, dict)
        else None
    )
    if not isinstance(material, dict):
        raise ValueError("user_acceptance candidate material is missing")
    images = manifest.get("images")
    configurations = manifest.get("configurationPackages")
    if not isinstance(images, dict) or not isinstance(configurations, dict):
        raise ValueError("component manifest candidate material is incomplete")
    expected_images = {
        service: str(descriptor.get("digest") or "")
        for service, descriptor in sorted(images.items())
        if isinstance(descriptor, dict)
    }
    expected_configurations = {
        environment: {
            service: str(descriptor.get("digest") or "")
            for service, descriptor in sorted(packages.items())
            if isinstance(descriptor, dict)
        }
        for environment, packages in sorted(configurations.items())
        if isinstance(packages, dict)
    }
    expected_applications: dict[str, dict[str, str]] = {
        environment: {} for environment in ENVIRONMENTS
    }
    for environment, surface in sorted(ALL_APPLICATION_KEYS):
        special_source = next(
            (
                artifact_id
                for artifact_id, target in APPLICATION_SOURCE_TARGETS.items()
                if target == (environment, surface)
            ),
            None,
        )
        payload = (
            source_payloads[special_source]
            if special_source is not None
            else generic_payloads[(environment, surface)]
        )
        expected_applications[environment][surface] = application_package_digest(
            payload,
            environment=environment,
            surface=surface,
        )
    expected = {
        "images": expected_images,
        "configurationPackages": expected_configurations,
        "applicationPackages": expected_applications,
        "contractGraphDigest": _sha256(contract_graph_path),
    }
    if material != expected:
        raise ValueError(
            "user_acceptance is not bound to the exact image/config/App/ContractGraph candidate material"
        )


def _validate_generic_application_source(
    payload: dict[str, Any],
    *,
    expected_key: tuple[str, str],
    manifest: dict[str, Any],
) -> None:
    if set(payload) != GENERIC_APPLICATION_FIELDS:
        raise ValueError(f"generic application evidence fields are not canonical: {expected_key}")
    environment, surface = expected_key
    if payload.get("schema") != GENERIC_APPLICATION_SCHEMA:
        raise ValueError(f"generic application evidence schema mismatch: {expected_key}")
    if payload.get("environment") != environment or payload.get("surface") != surface:
        raise ValueError(f"generic application evidence target mismatch: {expected_key}")
    source = manifest["source"]
    if payload.get("sourceGitSha") != source["gitSha"]:
        raise ValueError(f"generic application evidence git mismatch: {expected_key}")
    if payload.get("sourceTreeDigest") != source["treeDigest"]:
        raise ValueError(f"generic application evidence tree mismatch: {expected_key}")
    if DIGEST_PATTERN.fullmatch(str(payload.get("packageDigest") or "")) is None:
        raise ValueError(f"generic application package digest is invalid: {expected_key}")


def load_application_package_sources(directory: Path) -> dict[tuple[str, str], Path]:
    sources: dict[tuple[str, str], Path] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, f"application package {path.name}")
        key = (str(payload.get("environment") or ""), str(payload.get("surface") or ""))
        if key in sources:
            raise ValueError(f"duplicate application package evidence: {key}")
        sources[key] = path
    missing = sorted(GENERIC_APPLICATION_KEYS - set(sources))
    extra = sorted(set(sources) - GENERIC_APPLICATION_KEYS)
    if missing or extra:
        raise ValueError(
            f"generic application package set mismatch: missing={missing}, extra={extra}"
        )
    return sources


def load_application_package_payloads(
    directory: Path,
) -> dict[tuple[str, str], Path]:
    root = directory.expanduser().resolve()
    if directory.is_symlink() or not root.is_dir():
        raise ValueError("application package payload root is missing or unsafe")
    expected_environments = set(ENVIRONMENTS)
    actual_environments = {path.name for path in root.iterdir()}
    if actual_environments != expected_environments or any(
        not path.is_dir() or path.is_symlink() for path in root.iterdir()
    ):
        raise ValueError(
            "application package payload environment set mismatch: "
            f"missing={sorted(expected_environments - actual_environments)}, "
            f"extra={sorted(actual_environments - expected_environments)}"
        )

    payloads: dict[tuple[str, str], Path] = {}
    for environment in ENVIRONMENTS:
        environment_root = root / environment
        expected_surfaces = set(APPLICATION_PACKAGES[environment])
        children = list(environment_root.iterdir())
        actual_surfaces = {path.name for path in children}
        if actual_surfaces != expected_surfaces or any(
            not path.is_dir() or path.is_symlink() for path in children
        ):
            raise ValueError(
                f"application package payload set mismatch for {environment}: "
                f"missing={sorted(expected_surfaces - actual_surfaces)}, "
                f"extra={sorted(actual_surfaces - expected_surfaces)}"
            )
        for surface in APPLICATION_PACKAGES[environment]:
            payload = environment_root / surface
            sha256_tree(payload)
            payloads[(environment, surface)] = payload
    return payloads


def _copy_immutable(source: Path, destination: Path, label: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != source.read_bytes():
            raise ValueError(f"immutable release artifact already differs: {label}")
    else:
        shutil.copyfile(source, destination)
    return _sha256(destination)


def _write_descriptor(path: Path, descriptor: dict[str, Any], label: str) -> None:
    encoded = (
        json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.exists() and path.read_bytes() != encoded:
        raise ValueError(f"immutable release descriptor already differs: {label}")
    path.write_bytes(encoded)


def collect(
    *,
    artifact_dir: Path,
    descriptors_dir: Path,
    sources: dict[str, Path],
    application_package_sources: dict[tuple[str, str], Path],
    application_package_payloads: dict[tuple[str, str], Path],
    application_evidence_ref: str,
    provider_raw_dir: Path,
) -> dict[str, dict[str, Any]]:
    artifact_dir = artifact_dir.expanduser().resolve()
    descriptors_dir = descriptors_dir.expanduser().resolve()
    if set(sources) != set(EVIDENCE_SOURCE_SCHEMAS):
        missing = sorted(set(EVIDENCE_SOURCE_SCHEMAS) - set(sources))
        extra = sorted(set(sources) - set(EVIDENCE_SOURCE_SCHEMAS))
        raise ValueError(
            f"release artifact source set mismatch: missing={missing}, extra={extra}"
        )
    if set(application_package_sources) != GENERIC_APPLICATION_KEYS:
        missing = sorted(GENERIC_APPLICATION_KEYS - set(application_package_sources))
        extra = sorted(set(application_package_sources) - GENERIC_APPLICATION_KEYS)
        raise ValueError(
            f"generic application package set mismatch: missing={missing}, extra={extra}"
        )
    if set(application_package_payloads) != ALL_APPLICATION_KEYS:
        missing = sorted(ALL_APPLICATION_KEYS - set(application_package_payloads))
        extra = sorted(set(application_package_payloads) - ALL_APPLICATION_KEYS)
        raise ValueError(
            f"application package payload set mismatch: missing={missing}, extra={extra}"
        )
    manifest = _load_json(artifact_dir / "manifest.json", "service component manifest")
    validate_manifest(manifest, allowed_statuses={"component-ready"})
    validate_manifest_files(artifact_dir, manifest)
    if OCI_DIGEST_REF_PATTERN.fullmatch(application_evidence_ref) is None:
        raise ValueError("application evidence ref is not an immutable OCI digest ref")

    source_payloads: dict[str, dict[str, Any]] = {}
    for artifact_id, source_value in sources.items():
        payload = _load_json(source_value.expanduser().resolve(), artifact_id)
        _validate_source(artifact_id, payload)
        source_payloads[artifact_id] = payload
    _validate_provider_evidence(
        source_payloads["providerEvidence"],
        manifest=manifest,
        contract_graph_digest=_sha256(sources["contractGraph"].expanduser().resolve()),
        provider_raw_dir=provider_raw_dir,
    )
    test_evidence_files = _resolve_test_evidence_files(
        payload=source_payloads["testEvidence"],
        source_path=sources["testEvidence"],
    )
    generic_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    for key, source_value in application_package_sources.items():
        payload = _load_json(
            source_value.expanduser().resolve(),
            f"application package {key[0]}/{key[1]}",
        )
        _validate_generic_application_source(payload, expected_key=key, manifest=manifest)
        generic_payloads[key] = payload
    _validate_user_acceptance_candidate_material(
        test_evidence=source_payloads["testEvidence"],
        manifest=manifest,
        contract_graph_path=sources["contractGraph"].expanduser().resolve(),
        source_payloads=source_payloads,
        generic_payloads=generic_payloads,
    )
    for key, payload_root in application_package_payloads.items():
        special_source = next(
            (
                artifact_id
                for artifact_id, target in APPLICATION_SOURCE_TARGETS.items()
                if target == key
            ),
            None,
        )
        payload = (
            source_payloads[special_source]
            if special_source is not None
            else generic_payloads[key]
        )
        validate_application_package_payload(
            payload,
            payload_root=payload_root.expanduser().resolve(),
            manifest=manifest,
            environment=key[0],
            surface=key[1],
        )

    descriptors_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, Any]] = {}
    for artifact_id, source_value in sources.items():
        source = source_value.expanduser().resolve()
        destination = artifact_dir / EVIDENCE_DESTINATIONS[artifact_id]
        digest = _copy_immutable(source, destination, artifact_id)
        relative = destination.relative_to(artifact_dir).as_posix()
        if artifact_id in APPLICATION_SOURCE_TARGETS:
            environment, surface = APPLICATION_SOURCE_TARGETS[artifact_id]
            descriptor = {
                "applicationEnvironment": environment,
                "applicationSurface": surface,
                "path": relative,
                "digest": digest,
                "packageDigest": application_package_digest(
                    source_payloads[artifact_id],
                    environment=environment,
                    surface=surface,
                ),
                "sourceRef": application_evidence_ref,
            }
            descriptor_name = f"application--{environment}--{surface}.json"
            result[f"{environment}/{surface}"] = descriptor
        else:
            descriptor = {
                "evidenceKey": artifact_id,
                "path": relative,
                "digest": digest,
            }
            descriptor_name = f"{artifact_id}.json"
            result[artifact_id] = descriptor
        _write_descriptor(descriptors_dir / descriptor_name, descriptor, artifact_id)

    provider_files = source_payloads["providerEvidence"]["sourceEvidence"]["files"]
    provider_root = provider_raw_dir.expanduser().resolve()
    for archive_path, digest in sorted(provider_files.items()):
        relative = Path(str(archive_path).removeprefix("evidence/raw/provider/"))
        source = provider_root / relative
        destination = artifact_dir / str(archive_path)
        copied_digest = _copy_immutable(source, destination, "provider raw evidence")
        if copied_digest != digest:
            raise ValueError(f"provider raw evidence digest drift: {relative}")

    for label, (source, archive_path) in sorted(test_evidence_files.items()):
        destination = artifact_dir / archive_path
        copied_digest = _copy_immutable(
            source,
            destination,
            f"test evidence release closure {label}",
        )
        expected_digest = source_payloads["testEvidence"]["evidence"]["files"][
            label
        ]["digest"]
        if copied_digest != expected_digest:
            raise ValueError(
                f"test evidence release closure digest drift: {label}"
            )

    for key, source_value in sorted(application_package_sources.items()):
        environment, surface = key
        source = source_value.expanduser().resolve()
        destination = (
            artifact_dir
            / "packages/applications"
            / environment
            / surface
            / "evidence.json"
        )
        digest = _copy_immutable(source, destination, f"{environment}/{surface}")
        descriptor = {
            "applicationEnvironment": environment,
            "applicationSurface": surface,
            "path": destination.relative_to(artifact_dir).as_posix(),
            "digest": digest,
            "packageDigest": application_package_digest(
                generic_payloads[key],
                environment=environment,
                surface=surface,
            ),
            "sourceRef": application_evidence_ref,
        }
        _write_descriptor(
            descriptors_dir / f"application--{environment}--{surface}.json",
            descriptor,
            f"{environment}/{surface}",
        )
        result[f"{environment}/{surface}"] = descriptor

    application_keys = {
        (item["applicationEnvironment"], item["applicationSurface"])
        for item in result.values()
        if "applicationEnvironment" in item
    }
    if application_keys != ALL_APPLICATION_KEYS:
        raise ValueError("collected application package set is not four-environment")
    return result


def main() -> int:
    args = parse_args()
    try:
        result = collect(
            artifact_dir=args.artifact_dir,
            descriptors_dir=args.descriptors_dir,
            sources={
                "publicWeb": args.public_web_manifest,
                "androidOfficialRelease": args.android_release_manifest,
                "opsPortal": args.ops_portal_provenance,
                "contractGraph": args.contract_graph,
                "providerEvidence": args.provider_evidence,
                "testEvidence": args.test_evidence,
            },
            application_package_sources=load_application_package_sources(
                args.application_packages_dir.expanduser().resolve()
            ),
            application_package_payloads=load_application_package_payloads(
                args.application_package_payloads_dir
            ),
            application_evidence_ref=args.application_evidence_ref,
            provider_raw_dir=args.provider_raw_dir,
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 2
    print(json.dumps({"evidence": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
