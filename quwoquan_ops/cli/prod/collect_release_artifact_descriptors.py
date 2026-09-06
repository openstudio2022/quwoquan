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

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.release_evidence_reader import (
    APPLICATION_PACKAGES,
    DISTRIBUTION_EVIDENCE_PATHS,
    OCI_DIGEST_REF_PATTERN,
    OPS_PORTAL_SCHEMA,
    RELEASE_CLOSURE_PATHS,
    TEST_RELEASE_CLOSURE_LABELS,
    application_package_digest,
    sha256_ops_portal_tree,
    sha256_tree,
    validate_application_package_payload,
    validate_historical_release_snapshot,
)
from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.ci.render_release_application_package import (
    GENERIC_FIELDS as GENERIC_APPLICATION_FIELDS,
    SCHEMA as GENERIC_APPLICATION_SCHEMA,
    validate_package as validate_release_application_package,
)

EVIDENCE_SOURCE_SCHEMAS = {
    "publicWeb": "client-app.web.official-release",
    "androidOfficialRelease": "client-app.android.official-release",
    "opsPortal": OPS_PORTAL_SCHEMA,
    "contractGraph": "qwq.contract-graph",
    "providerEvidence": "provider-conformance-readiness",
    "testEvidence": "qwq.three-layer-case-results",
}
APPLICATION_SOURCE_TARGETS: dict[str, str] = {}
APPLICATION_PACKAGE_KEYS = frozenset(APPLICATION_PACKAGES)
GENERIC_APPLICATION_KEYS = APPLICATION_PACKAGE_KEYS
EVIDENCE_DESTINATIONS = {
    **DISTRIBUTION_EVIDENCE_PATHS,
    "opsPortal": "packages/opsPortal/provenance.json",
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
    expected_environment_artifacts = {
        environment: {
            "environmentArtifactDigest": artifact["environmentArtifactDigest"],
            "images": {
                owner: descriptor["digest"]
                for owner, descriptor in sorted(artifact["images"].items())
            },
        }
        for environment, artifact in sorted(
            manifest["environmentArtifacts"].items()
        )
    }
    if material != {
        "environmentArtifacts": expected_environment_artifacts,
        "contractGraphDigest": contract_graph_digest,
    }:
        raise ValueError("providerEvidence candidate material binding mismatch")
def _validate_user_acceptance_candidate_material(
    *,
    test_evidence: dict[str, Any],
    manifest: dict[str, Any],
    contract_graph_path: Path,
    ops_portal_digest: str,
    generic_payloads: dict[str, dict[str, Any]],
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
    artifacts = manifest.get("environmentArtifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("component manifest environment artifact material is incomplete")
    expected_environment_artifacts = {
        environment: {
            "environmentArtifactDigest": artifact.get("environmentArtifactDigest"),
            "images": {
                owner: str(descriptor.get("digest") or "")
                for owner, descriptor in sorted(images.items())
                if isinstance(descriptor, dict)
            },
            "configurationPackages": {
                service: str(descriptor.get("digest") or "")
                for service, descriptor in sorted(configurations.items())
                if isinstance(descriptor, dict)
            },
        }
        for environment, artifact in sorted(artifacts.items())
        if isinstance(artifact, dict)
        for images, configurations in [
            (artifact.get("images"), artifact.get("configurationPackages"))
        ]
        if isinstance(images, dict) and isinstance(configurations, dict)
    }
    if len(expected_environment_artifacts) != len(artifacts):
        raise ValueError("component manifest environment artifact material is invalid")
    expected_applications = {
        build_product_id: application_package_digest(payload)
        for build_product_id, payload in sorted(generic_payloads.items())
    }
    expected = {
        "environmentArtifacts": expected_environment_artifacts,
        "applicationPackages": expected_applications,
        "opsPortal": ops_portal_digest,
        "contractGraphDigest": _sha256(contract_graph_path),
    }
    if material != expected:
        raise ValueError(
            "user_acceptance is not bound to the exact image/config/App/ContractGraph candidate material"
        )


def _validate_generic_application_source(
    payload: dict[str, Any],
    *,
    expected_key: str,
    manifest: dict[str, Any],
) -> None:
    if set(payload) != GENERIC_APPLICATION_FIELDS:
        raise ValueError(f"application evidence fields are not canonical: {expected_key}")
    source = manifest["source"]
    validate_release_application_package(
        payload,
        build_product_id=expected_key,
        source_git_sha=str(source["gitSha"]),
        source_tree_digest=str(source["treeDigest"]),
    )


def load_application_package_sources(directory: Path) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, f"application package {path.name}")
        key = str(payload.get("buildProductId") or "")
        if key in sources:
            raise ValueError(f"duplicate application package evidence: {key}")
        sources[key] = path
    missing = sorted(GENERIC_APPLICATION_KEYS - set(sources))
    extra = sorted(set(sources) - GENERIC_APPLICATION_KEYS)
    if missing or extra:
        raise ValueError(
            f"App build product package set mismatch: missing={missing}, extra={extra}"
        )
    return sources


def load_application_package_payloads(directory: Path) -> dict[str, Path]:
    root = directory.expanduser().resolve()
    if directory.is_symlink() or not root.is_dir():
        raise ValueError("application package payload root is missing or unsafe")
    children = list(root.iterdir())
    actual_products = {path.name for path in children}
    expected_entries = APPLICATION_PACKAGE_KEYS | {"opsPortal"}
    if actual_products != expected_entries or any(
        not path.is_dir() or path.is_symlink() for path in children
    ):
        raise ValueError(
            "App/opsPortal payload set mismatch: "
            f"missing={sorted(expected_entries - actual_products)}, "
            f"extra={sorted(actual_products - expected_entries)}"
        )
    payloads: dict[str, Path] = {}
    for build_product_id in APPLICATION_PACKAGES:
        payload = root / build_product_id
        sha256_tree(payload)
        payloads[build_product_id] = payload
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
    application_package_sources: dict[str, Path],
    application_package_payloads: dict[str, Path],
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
            f"App build product package set mismatch: missing={missing}, extra={extra}"
        )
    if set(application_package_payloads) != APPLICATION_PACKAGE_KEYS:
        missing = sorted(APPLICATION_PACKAGE_KEYS - set(application_package_payloads))
        extra = sorted(set(application_package_payloads) - APPLICATION_PACKAGE_KEYS)
        raise ValueError(
            f"App build product payload set mismatch: missing={missing}, extra={extra}"
        )
    manifest = _load_json(artifact_dir / "manifest.json", "service component manifest")
    validate_historical_release_snapshot(
        manifest,
        artifact_dir=artifact_dir,
        allowed_statuses={"component-ready"},
    )
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
    generic_payloads: dict[str, dict[str, Any]] = {}
    for build_product_id, source_value in application_package_sources.items():
        payload = _load_json(
            source_value.expanduser().resolve(),
            f"application package {build_product_id}",
        )
        _validate_generic_application_source(
            payload,
            expected_key=build_product_id,
            manifest=manifest,
        )
        generic_payloads[build_product_id] = payload
    for build_product_id, payload_root in application_package_payloads.items():
        validate_application_package_payload(
            generic_payloads[build_product_id],
            payload_root=payload_root.expanduser().resolve(),
            manifest=manifest,
            build_product_id=build_product_id,
        )

    ops_portal_payload_root = (
        next(iter(application_package_payloads.values())).parent / "opsPortal"
    )
    if ops_portal_payload_root.is_symlink() or not ops_portal_payload_root.is_dir():
        raise ValueError("opsPortal payload root is missing or unsafe")
    ops_portal_digest = application_package_digest(source_payloads["opsPortal"])
    manifest_path = ops_portal_payload_root / "manifest.json"
    dist = ops_portal_payload_root / "dist"
    digests = source_payloads["opsPortal"].get("digests")
    if (
        not isinstance(digests, dict)
        or _sha256(manifest_path) != digests.get("manifest")
        or sha256_ops_portal_tree(dist) != digests.get("distTree")
        or ops_portal_digest != digests.get("distTree")
    ):
        raise ValueError("opsPortal payload digest mismatch")
    _validate_user_acceptance_candidate_material(
        test_evidence=source_payloads["testEvidence"],
        manifest=manifest,
        contract_graph_path=sources["contractGraph"].expanduser().resolve(),
        ops_portal_digest=ops_portal_digest,
        generic_payloads=generic_payloads,
    )

    descriptors_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, Any]] = {}
    for artifact_id, source_value in sources.items():
        source = source_value.expanduser().resolve()
        destination = artifact_dir / EVIDENCE_DESTINATIONS[artifact_id]
        digest = _copy_immutable(source, destination, artifact_id)
        relative = destination.relative_to(artifact_dir).as_posix()
        if artifact_id == "opsPortal":
            descriptor = {
                "evidenceKey": "opsPortal",
                "path": relative,
                "digest": digest,
                "packageDigest": ops_portal_digest,
                "sourceRef": application_evidence_ref,
            }
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
            raise ValueError(f"test evidence release closure digest drift: {label}")

    for build_product_id, source_value in sorted(application_package_sources.items()):
        source = source_value.expanduser().resolve()
        destination = (
            artifact_dir
            / "packages/applications"
            / build_product_id
            / "evidence.json"
        )
        digest = _copy_immutable(source, destination, build_product_id)
        descriptor = {
            "buildProductId": build_product_id,
            "path": destination.relative_to(artifact_dir).as_posix(),
            "digest": digest,
            "packageDigest": application_package_digest(generic_payloads[build_product_id]),
            "sourceRef": application_evidence_ref,
        }
        _write_descriptor(
            descriptors_dir / f"application--{build_product_id}.json",
            descriptor,
            build_product_id,
        )
        result[build_product_id] = descriptor

    application_keys = {
        str(item["buildProductId"])
        for item in result.values()
        if "buildProductId" in item
    }
    if application_keys != APPLICATION_PACKAGE_KEYS:
        raise ValueError("collected App build product set is not canonical")
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
