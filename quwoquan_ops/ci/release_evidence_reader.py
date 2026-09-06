#!/usr/bin/env python3
"""Named read-only validators for frozen diagnostic snapshots and hosted readback.

ReleaseEvidenceManifest is retired from every promotable/formal path.  The two
public snapshot validators below are diagnostic-only: one accepts explicitly
non-promotable rehearsal snapshots and one accepts historical snapshots.  This
module has no writer, seal, verdict, admission, or generic validation alias.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.ci.render_release_application_package import validate_package
from quwoquan_ops.cli.lib.app_identity import supported_build_products
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_release_attestations,
)
from quwoquan_ops.cli.prod import hosted_release_ledger

SCHEMA = "release-evidence-manifest"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PRE_PROD_ENVIRONMENTS = ENVIRONMENTS[:-1]
STATUSES = frozenset(
    {
        "build-input",
        "component-ready",
        "candidate-ready",
        "deployable",
        "released",
        "rolled-back",
        "rollback-failed",
    }
)
APPLICATION_BUILD_PRODUCTS = supported_build_products()
APPLICATION_PACKAGES = tuple(
    product.build_product_id for product in APPLICATION_BUILD_PRODUCTS
)
if len(APPLICATION_PACKAGES) != 5 or len(set(APPLICATION_PACKAGES)) != 5:
    raise ValueError("ReleaseEvidence App baseline must contain exactly five products")
REQUIRED_RELEASE_EVIDENCE = ("contractGraph", "providerEvidence", "testEvidence")
OPTIONAL_RELEASE_EVIDENCE = ("publicWeb", "androidOfficialRelease")
DISTRIBUTION_EVIDENCE_PATHS = {
    "publicWeb": "evidence/distribution/public-web-manifest.json",
    "androidOfficialRelease": "evidence/distribution/android-release-manifest.json",
}
TEST_LAYERS = ("local_contract", "api_integration", "user_acceptance")
RELEASE_CLOSURE_PATHS = {
    "pilot-release": "evidence/release/pilot-release-attestation.json",
    "pilot-rollback": "evidence/release/pilot-rollback-attestation.json",
    "content-lifecycle-alpha": "evidence/release/lifecycle-exit-alpha.json",
    "content-lifecycle-beta": "evidence/release/lifecycle-exit-beta.json",
    "content-lifecycle-gamma": "evidence/release/lifecycle-exit-gamma.json",
    "green-matrix": "evidence/release/alpha-beta-gamma-green-matrix.json",
}
TEST_RELEASE_CLOSURE_LABELS = frozenset(RELEASE_CLOSURE_PATHS)
ENVIRONMENT_RECEIPT_SCHEMA = "release-environment-receipt"
ROLLOUT_RECEIPT_SCHEMA = "release-rollout-receipt"
ROLLBACK_RECEIPT_SCHEMA = "release-rollback-receipt"
ROOT_FIELDS = frozenset(
    {
        "schema", "releaseTrainId", "candidateId", "status", "generatedAt",
        "source", "artifactDigest", "environmentArtifacts", "applicationPackages",
        "publicWeb", "androidOfficialRelease", "opsPortal", "contractGraphDigest",
        "requiredEvidence", "testEvidence", "providerEvidence", "environmentReceipts",
        "rolloutReceipt", "rollbackReceipt", "blockers", "missingEvidence",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "artifactName", "contractVersion", "imageRepositories", "manifestDigest",
        "registryRevision", "releaseFileDigests", "releaseFiles", "requiredArtifacts",
        "requiredImages", "schemaVersion", "versions",
    }
)
RECEIPT_SOURCE_FIELDS = frozenset(
    {
        "schema", "environment", "status", "candidateId", "sourceGitSha",
        "sourceTreeDigest", "evidenceDigest", "evidence", "verifiedAt",
    }
)
RECEIPT_DESCRIPTOR_FIELDS = RECEIPT_SOURCE_FIELDS | {"path", "digest"}
APPLICATION_PACKAGE_SCHEMA = "release-application-package"
APPLICATION_PACKAGE_FIELDS = frozenset(
    {
        "schema", "buildProductId", "buildProfile", "platform", "sourceGitSha",
        "sourceTreeDigest", "packageDigest", "artifactManifest",
    }
)
APPLICATION_DESCRIPTOR_FIELDS = frozenset({"path", "digest", "packageDigest", "sourceRef"})
DISTRIBUTION_DESCRIPTOR_FIELDS = frozenset({"path", "digest"})
APPLICATION_SOURCE_DESCRIPTOR_FIELDS = APPLICATION_DESCRIPTOR_FIELDS | {"buildProductId"}
OPS_PORTAL_SCHEMA = "qwq.ops_portal_package"
OPS_PORTAL_SOURCE_DESCRIPTOR_FIELDS = APPLICATION_DESCRIPTOR_FIELDS | {"evidenceKey"}
OCI_DIGEST_REF_PATTERN = re.compile(
    r"oci://ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}"
)
TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
PREPROD_RELEASE_EVIDENCE = frozenset(
    {"pilot-release", "pilot-rollback", "content-lifecycle"}
)

HOSTED_AUTHORITY = hosted_release_ledger.AUTHORITY
HOSTED_READBACK_SCHEMA = hosted_release_ledger.READBACK_SCHEMA
HOSTED_RECEIPT_READBACK_SCHEMA = hosted_release_ledger.RECEIPT_READBACK_SCHEMA
HOSTED_RECEIPT_SCHEMA = hosted_release_ledger.RECEIPT_SCHEMA
HOSTED_STATE_SCHEMA = hosted_release_ledger.STATE_SCHEMA
HOSTED_SOAK_RECEIPT_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_SCHEMA
HOSTED_SOAK_READBACK_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_READBACK_SCHEMA
STAGES = ("canary", "5", "20", "50", "100")
RECEIPT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
HOSTED_RECEIPT_FIELDS = hosted_release_ledger.RECEIPT_FIELDS
HOSTED_STATE_FIELDS = hosted_release_ledger.STATE_FIELDS



def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    canonical = dict(payload)
    canonical.pop('artifactDigest', None)
    return _canonical_json_bytes(canonical)


def canonical_manifest_digest(payload: dict[str, Any]) -> str:
    return 'sha256:' + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _environment_artifact_projection(payload: dict[str, Any], environment: str) -> dict[str, Any]:
    artifacts = payload.get('environmentArtifacts')
    artifact = artifacts.get(environment) if isinstance(artifacts, dict) else None
    if not isinstance(artifact, dict) or artifact.get('environment') != environment:
        raise ValueError(f'environment artifact is incomplete: {environment}')
    images = artifact.get('images')
    configurations = artifact.get('configurationPackages')
    if not isinstance(images, dict) or not images:
        raise ValueError(f'environment image material is incomplete: {environment}')
    if not isinstance(configurations, dict) or not configurations:
        raise ValueError(f'environment configuration material is incomplete: {environment}')
    projected_images: dict[str, Any] = {}
    for owner, descriptor in sorted(images.items()):
        if not isinstance(descriptor, dict) or DIGEST_PATTERN.fullmatch(str(descriptor.get('digest') or '')) is None:
            raise ValueError(f'environment image material is not immutable: {environment}/{owner}')
        projected_images[owner] = {'digest': descriptor['digest']}
    projected_configurations = {service: {'digest': descriptor.get('digest')} for service, descriptor in sorted(configurations.items()) if isinstance(descriptor, dict)}
    if len(projected_configurations) != len(configurations):
        raise ValueError(f'environment configuration material is invalid: {environment}')
    return {'environment': environment, 'images': projected_images, 'configurationPackages': projected_configurations}


def canonical_environment_artifact_digest(payload: dict[str, Any], environment: str) -> str:
    projection = _environment_artifact_projection(payload, environment)
    return 'sha256:' + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def canonical_release_train_digest(payload: dict[str, Any]) -> str:
    source = payload.get('source')
    if not isinstance(source, dict):
        raise ValueError('release train source is incomplete')
    projection = {'schema': SCHEMA, 'source': {'gitSha': source.get('gitSha'), 'treeDigest': source.get('treeDigest'), 'repository': source.get('repository')}}
    return 'sha256:' + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def _candidate_projection(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get('source')
    artifacts = payload.get('environmentArtifacts')
    applications = payload.get('applicationPackages')
    distributions = {evidence_key: payload.get(evidence_key) for evidence_key in DISTRIBUTION_EVIDENCE_PATHS}
    provider = payload.get('providerEvidence')
    test = payload.get('testEvidence')
    contract_graph = payload.get('contractGraphDigest')
    release_train_id = payload.get('releaseTrainId')
    if not isinstance(source, dict) or not isinstance(artifacts, dict):
        raise ValueError('candidate source or environment artifacts are incomplete')
    if set(artifacts) != set(ENVIRONMENTS):
        raise ValueError('candidate environment artifact material is incomplete')
    if not isinstance(applications, dict) or set(applications) != set(APPLICATION_PACKAGES):
        raise ValueError('candidate App build product material is incomplete')
    if any((not isinstance(descriptor, dict) or DIGEST_PATTERN.fullmatch(str(descriptor.get('digest') or '')) is None for descriptor in distributions.values())):
        raise ValueError('candidate distribution evidence is incomplete')
    if not isinstance(provider, dict) or not isinstance(test, dict):
        raise ValueError('candidate qualification material is incomplete')
    if DIGEST_PATTERN.fullmatch(str(contract_graph or '')) is None:
        raise ValueError('candidate contract graph material is incomplete')
    if DIGEST_PATTERN.fullmatch(str(release_train_id or '')) is None:
        raise ValueError('candidate release train identity is incomplete')
    projected_artifacts: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        projection = _environment_artifact_projection(payload, environment)
        artifact = artifacts[environment]
        environment_digest = artifact.get('environmentArtifactDigest')
        if environment_digest != canonical_environment_artifact_digest(payload, environment):
            raise ValueError(f'environment artifact digest is incomplete: {environment}')
        projected_artifacts[environment] = {**projection, 'environmentArtifactDigest': environment_digest}
    projected_applications = {build_product_id: {'digest': descriptor.get('digest'), 'packageDigest': descriptor.get('packageDigest')} for build_product_id, descriptor in sorted(applications.items()) if isinstance(descriptor, dict)}
    if len(projected_applications) != len(APPLICATION_PACKAGES):
        raise ValueError('candidate App build product material is invalid')
    for build_product_id, descriptor in projected_applications.items():
        if any((DIGEST_PATTERN.fullmatch(str(descriptor.get(field) or '')) is None for field in ('digest', 'packageDigest'))):
            raise ValueError(f'candidate App build product material is not immutable: {build_product_id}')
    return {'schema': SCHEMA, 'releaseTrainId': release_train_id, 'source': {'gitSha': source.get('gitSha'), 'treeDigest': source.get('treeDigest'), 'repository': source.get('repository')}, 'environmentArtifacts': projected_artifacts, 'applicationPackages': projected_applications, 'distributionEvidence': {evidence_key: {'digest': descriptor['digest']} for evidence_key, descriptor in sorted(distributions.items())}, 'contractGraphDigest': contract_graph, 'providerEvidence': {'digest': provider.get('digest')}, 'testEvidence': {'digest': test.get('digest'), 'layers': test.get('layers')}}


def canonical_candidate_digest(payload: dict[str, Any]) -> str:
    projection = _candidate_projection(payload)
    return 'sha256:' + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return f'sha256:{digest.hexdigest()}'


def sha256_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f'application payload tree is missing or unsafe: {root}')
    entries = sorted(root.rglob('*'))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f'application payload tree contains symlink: {unsafe}')
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f'application payload tree is empty: {root}')
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode('utf-8')
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        digest.update(path.read_bytes())
    return f'sha256:{digest.hexdigest()}'


def sha256_ops_portal_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f'Ops Portal payload tree is missing or unsafe: {root}')
    entries = sorted(root.rglob('*'))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f'Ops Portal payload tree contains symlink: {unsafe}')
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f'Ops Portal payload tree is empty: {root}')
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode('utf-8'))
        digest.update(b'\x00')
        digest.update(sha256_file(path).encode('ascii'))
        digest.update(b'\x00')
    return f'sha256:{digest.hexdigest()}'


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path} must contain an object')
    return payload


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or (not all((isinstance(item, str) and item for item in value))):
        raise ValueError(f'{label} must be a non-empty string list')
    if len(value) != len(set(value)):
        raise ValueError(f'{label} must not contain duplicates')
    return value


def _validate_relative_path(value: Any, label: str) -> str:
    relative = str(value or '').strip()
    path = Path(relative)
    if not relative or path.is_absolute() or '..' in path.parts:
        raise ValueError(f'{label} path is unsafe')
    return path.as_posix()


def _bound_file(artifact_dir: Path, relative: str, label: str) -> Path:
    root = artifact_dir.resolve()
    candidate = artifact_dir / relative
    resolved = candidate.resolve()
    if root not in resolved.parents or candidate.is_symlink() or (not candidate.is_file()):
        raise ValueError(f'{label} is missing or escapes the release evidence root')
    return candidate


def _validate_required_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError('requiredEvidence must be an object')
    expected_fields = {'environmentArtifacts', 'configurationPackages', 'applicationPackages', 'opsPortal', 'contractGraphDigest', 'providerEvidence', 'testEvidence', 'environmentReceipts', 'rolloutReceipt', 'rollbackReceipt'}
    if set(value) != expected_fields:
        raise ValueError('requiredEvidence fields are not canonical')
    environment_artifacts = value['environmentArtifacts']
    if not isinstance(environment_artifacts, dict) or set(environment_artifacts) != set(ENVIRONMENTS):
        raise ValueError('requiredEvidence.environmentArtifacts is not four-environment')
    image_owners: list[str] | None = None
    for environment in ENVIRONMENTS:
        owners = _require_string_list(environment_artifacts[environment], f'requiredEvidence.environmentArtifacts.{environment}')
        if image_owners is None:
            image_owners = owners
        elif owners != image_owners:
            raise ValueError('requiredEvidence environment image owner sets differ')
    configuration_packages = value['configurationPackages']
    if not isinstance(configuration_packages, dict) or set(configuration_packages) != set(ENVIRONMENTS):
        raise ValueError('requiredEvidence.configurationPackages is not four-environment')
    for environment in ENVIRONMENTS:
        _require_string_list(configuration_packages[environment], f'requiredEvidence.configurationPackages.{environment}')
    applications = _require_string_list(value['applicationPackages'], 'requiredEvidence.applicationPackages')
    if tuple(applications) != APPLICATION_PACKAGES:
        raise ValueError('requiredEvidence.applicationPackages is not canonical')
    if value['opsPortal'] is not True:
        raise ValueError('requiredEvidence.opsPortal must be independently required')
    layers = _require_string_list(value['testEvidence'], 'requiredEvidence.testEvidence')
    if tuple(layers) != TEST_LAYERS:
        raise ValueError('requiredEvidence.testEvidence is not canonical')
    environments = _require_string_list(value['environmentReceipts'], 'requiredEvidence.environmentReceipts')
    if tuple(environments) != ENVIRONMENTS:
        raise ValueError('requiredEvidence.environmentReceipts is not canonical')
    if any((value[field] is not True for field in ('contractGraphDigest', 'providerEvidence', 'rolloutReceipt', 'rollbackReceipt'))):
        raise ValueError('requiredEvidence omits a mandatory release fact')
    return value


def _validate_packages(value: Any, *, expected: Iterable[str], label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'{label} set is not canonical')
    for key, descriptor in value.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {'path', 'digest'}:
            raise ValueError(f'{label}.{key} descriptor is not canonical')
        _validate_relative_path(descriptor.get('path'), f'{label}.{key}')
        if DIGEST_PATTERN.fullmatch(str(descriptor.get('digest') or '')) is None:
            raise ValueError(f'{label}.{key} digest is not immutable')
    return value


def _validate_content_descriptor(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != APPLICATION_DESCRIPTOR_FIELDS:
        raise ValueError(f'{label} descriptor is not canonical')
    _validate_relative_path(value.get('path'), label)
    for digest_key in ('digest', 'packageDigest'):
        if DIGEST_PATTERN.fullmatch(str(value.get(digest_key) or '')) is None:
            raise ValueError(f'{label}.{digest_key} is not immutable')
    source_ref = str(value.get('sourceRef') or '')
    if OCI_DIGEST_REF_PATTERN.fullmatch(source_ref) is None:
        raise ValueError(f'{label}.sourceRef is not an immutable OCI reference')
    return value


def _validate_application_packages(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(APPLICATION_PACKAGES):
        raise ValueError('applicationPackages must contain exactly five build products')
    for build_product_id, descriptor in value.items():
        _validate_content_descriptor(descriptor, label=f'applicationPackages.{build_product_id}')
    return value


def _validate_distribution_descriptors(manifest: dict[str, Any]) -> None:
    for evidence_key, canonical_path in DISTRIBUTION_EVIDENCE_PATHS.items():
        descriptor = manifest.get(evidence_key)
        if not isinstance(descriptor, dict) or set(descriptor) != DISTRIBUTION_DESCRIPTOR_FIELDS:
            raise ValueError(f'{evidence_key} descriptor is not canonical')
        if descriptor.get('path') != canonical_path:
            raise ValueError(f'{evidence_key} path is not canonical')
        if DIGEST_PATTERN.fullmatch(str(descriptor.get('digest') or '')) is None:
            raise ValueError(f'{evidence_key}.digest is not immutable')


def _validate_images(value: Any, *, required: list[str], status: str, environment: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f'environmentArtifacts.{environment}.images set is not canonical')
    transport_tags: set[str] = set()
    for owner, image in value.items():
        label = f'environmentArtifacts.{environment}.images.{owner}'
        if not isinstance(image, dict):
            raise ValueError(f'{label} must be an object')
        repository = str(image.get('repository') or '').strip()
        transport_ref = str(image.get('transportRef') or '').strip()
        trust_domain = 'prod' if environment == 'prod' else 'nonprod'
        if not repository.endswith(f'/{owner}-{trust_domain}'):
            raise ValueError(f'{label} repository is not trust-domain-bound')
        if not repository.startswith('ghcr.io/') or not transport_ref.startswith(repository + ':'):
            raise ValueError(f'{label} transport reference is invalid')
        if transport_ref.endswith(':latest'):
            raise ValueError(f'{label} transport reference must not use latest')
        transport_tags.add(transport_ref[len(repository) + 1:])
        if status == 'build-input':
            if set(image) != {'repository', 'transportRef'}:
                raise ValueError(f'{label} build input is not canonical')
            continue
        if set(image) != {'repository', 'transportRef', 'digest', 'ref', 'attestations'}:
            raise ValueError(f'{label} immutable descriptor is not canonical')
        digest = str(image.get('digest') or '')
        ref = str(image.get('ref') or '')
        if DIGEST_PATTERN.fullmatch(digest) is None or ref != f'{repository}@{digest}':
            raise ValueError(f'{label} digest reference is invalid')
        attestations = image.get('attestations')
        if not isinstance(attestations, dict) or set(attestations) != {'spdxSbom', 'slsaProvenance'}:
            raise ValueError(f'{label} attestations are incomplete')
        for kind in ('spdxSbom', 'slsaProvenance'):
            if attestations.get(kind) != f'oci://{ref}#{kind}':
                raise ValueError(f'{label} {kind} reference is invalid')
    if len(transport_tags) != 1:
        raise ValueError(f'{environment} images must use one common transport tag')
    return value


def _validate_environment_artifacts(value: Any, *, required_images: dict[str, list[str]], required_configurations: dict[str, list[str]], status: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(ENVIRONMENTS):
        raise ValueError('environmentArtifacts must contain alpha/beta/gamma/prod')
    nonprod_digests: dict[str, str] = {}
    prod_digests: dict[str, str] = {}
    for environment in ENVIRONMENTS:
        artifact = value[environment]
        if not isinstance(artifact, dict) or set(artifact) != {'environment', 'environmentArtifactDigest', 'images', 'configurationPackages'}:
            raise ValueError(f'environmentArtifacts.{environment} fields are not canonical')
        if artifact.get('environment') != environment:
            raise ValueError(f'environmentArtifacts.{environment} identity mismatch')
        images = _validate_images(artifact.get('images'), required=required_images[environment], status=status, environment=environment)
        _validate_packages(artifact.get('configurationPackages'), expected=required_configurations[environment], label=f'environmentArtifacts.{environment}.configurationPackages')
        declared = artifact.get('environmentArtifactDigest')
        if status == 'build-input':
            if declared is not None:
                raise ValueError(f'environmentArtifacts.{environment} digest must be absent before images are immutable')
        else:
            projection_artifact = dict(artifact)
            projection_artifact['environmentArtifactDigest'] = None
            expected_digest = canonical_environment_artifact_digest({'environmentArtifacts': {environment: projection_artifact}}, environment)
            if declared != expected_digest:
                raise ValueError(f'environmentArtifacts.{environment} digest mismatch')
        if status != 'build-input':
            for owner, image in images.items():
                digest = str(image['digest'])
                if environment == 'prod':
                    prod_digests[str(owner)] = digest
                else:
                    previous = nonprod_digests.setdefault(str(owner), digest)
                    if previous != digest:
                        raise ValueError(f'nonprod environmentArtifacts must share one image digest per owner: {owner} diverges at {environment}')
    for owner, digest in prod_digests.items():
        if nonprod_digests.get(owner) == digest:
            raise ValueError(f'prod environmentArtifacts must not reuse the nonprod trust-domain image digest: {owner}')
    return value


def _forbidden_field_paths(value: Any, prefix: str='') -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            if key in FORBIDDEN_FIELDS:
                paths.append(path)
            paths.extend(_forbidden_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_forbidden_field_paths(child, f'{prefix}[{index}]'))
    return paths


def _validate_candidate_evidence(manifest: dict[str, Any]) -> None:
    applications = _validate_application_packages(manifest.get('applicationPackages'))
    _validate_distribution_descriptors(manifest)
    _validate_content_descriptor(manifest.get('opsPortal'), label='opsPortal')
    application_evidence_refs = {descriptor['sourceRef'] for descriptor in applications.values()}
    if len(application_evidence_refs) != 1:
        raise ValueError('applicationPackages must use one application evidence OCI')
    if DIGEST_PATTERN.fullmatch(str(manifest.get('contractGraphDigest') or '')) is None:
        raise ValueError('contractGraphDigest is missing')
    provider = manifest.get('providerEvidence')
    if not isinstance(provider, dict) or set(provider) != {'path', 'digest', 'status', 'evidenceCount'} or provider.get('status') != 'passed' or (DIGEST_PATTERN.fullmatch(str(provider.get('digest') or '')) is None) or (not isinstance(provider.get('evidenceCount'), int)) or (provider['evidenceCount'] <= 0):
        raise ValueError('providerEvidence is not passed and immutable')
    _validate_relative_path(provider.get('path'), 'providerEvidence')
    test = manifest.get('testEvidence')
    if not isinstance(test, dict) or set(test) != {'path', 'digest', 'status', 'layers', 'evidence'} or test.get('status') != 'passed' or (DIGEST_PATTERN.fullmatch(str(test.get('digest') or '')) is None) or (not isinstance(test.get('evidence'), dict)) or (not test['evidence']):
        raise ValueError('testEvidence is not passed and immutable')
    _validate_relative_path(test.get('path'), 'testEvidence')
    layers = test.get('layers')
    if not isinstance(layers, dict) or set(layers) != set(TEST_LAYERS):
        raise ValueError('testEvidence layers are not canonical')
    for layer in TEST_LAYERS:
        item = layers.get(layer)
        if not isinstance(item, dict) or set(item) != {'status', 'artifactDigest'} or item.get('status') != 'passed' or (DIGEST_PATTERN.fullmatch(str(item.get('artifactDigest') or '')) is None):
            raise ValueError(f'testEvidence layer is not immutable: {layer}')
    evidence = test['evidence']
    files = evidence.get('files') if isinstance(evidence, dict) else None
    if not isinstance(files, dict) or set(files) != set(TEST_RELEASE_CLOSURE_LABELS):
        raise ValueError('testEvidence release closure file set is incomplete')
    for label, descriptor in files.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {'path', 'digest'} or descriptor.get('path') != RELEASE_CLOSURE_PATHS[label] or (DIGEST_PATTERN.fullmatch(str(descriptor.get('digest') or '')) is None):
            raise ValueError(f'testEvidence release closure descriptor is invalid: {label}')


def _validate_receipt_descriptor(descriptor: Any, *, manifest: dict[str, Any], kind: str, expected_environment: str) -> dict[str, Any]:
    if not isinstance(descriptor, dict) or set(descriptor) != RECEIPT_DESCRIPTOR_FIELDS:
        raise ValueError(f'{kind} receipt descriptor is not canonical')
    expected_schema = {'environment': ENVIRONMENT_RECEIPT_SCHEMA, 'rollout': ROLLOUT_RECEIPT_SCHEMA, 'rollback': ROLLBACK_RECEIPT_SCHEMA}[kind]
    if descriptor.get('schema') != expected_schema:
        raise ValueError(f'{kind} receipt schema mismatch')
    if descriptor.get('environment') != expected_environment:
        raise ValueError(f'{kind} receipt environment mismatch')
    if kind == 'rollback':
        allowed_statuses = {'ready', 'not_triggered', 'rolled_back', 'rollback_failed'}
    elif kind == 'rollout':
        allowed_statuses = {'passed', 'failed'}
    elif expected_environment == 'prod':
        allowed_statuses = {'passed', 'failed'}
    else:
        allowed_statuses = {'passed'}
    if descriptor.get('status') not in allowed_statuses:
        raise ValueError(f'{kind} receipt status is invalid')
    if descriptor.get('candidateId') != manifest.get('candidateId'):
        raise ValueError(f'{kind} receipt candidateId mismatch')
    source = manifest['source']
    if descriptor.get('sourceGitSha') != source['gitSha']:
        raise ValueError(f'{kind} receipt source git mismatch')
    if descriptor.get('sourceTreeDigest') != source['treeDigest']:
        raise ValueError(f'{kind} receipt source tree mismatch')
    for field in ('digest', 'evidenceDigest'):
        if DIGEST_PATTERN.fullmatch(str(descriptor.get(field) or '')) is None:
            raise ValueError(f'{kind} receipt {field} is not immutable')
    evidence = descriptor.get('evidence')
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError(f'{kind} receipt evidence projection is missing')
    expected_evidence_digest = 'sha256:' + hashlib.sha256(_canonical_json_bytes(evidence)).hexdigest()
    if descriptor.get('evidenceDigest') != expected_evidence_digest:
        raise ValueError(f'{kind} receipt evidence projection digest mismatch')
    _validate_relative_path(descriptor.get('path'), f'{kind} receipt')
    if not str(descriptor.get('verifiedAt') or '').strip():
        raise ValueError(f'{kind} receipt verifiedAt is missing')
    return descriptor


def _validate_receipts(manifest: dict[str, Any]) -> None:
    environment_receipts = manifest.get('environmentReceipts')
    if not isinstance(environment_receipts, dict) or not set(environment_receipts).issubset(ENVIRONMENTS):
        raise ValueError('environmentReceipts set is not canonical')
    for environment, descriptor in environment_receipts.items():
        _validate_receipt_descriptor(descriptor, manifest=manifest, kind='environment', expected_environment=environment)
    rollout = manifest.get('rolloutReceipt')
    if rollout is not None:
        _validate_receipt_descriptor(rollout, manifest=manifest, kind='rollout', expected_environment='prod')
    rollback = manifest.get('rollbackReceipt')
    if rollback is not None:
        _validate_receipt_descriptor(rollback, manifest=manifest, kind='rollback', expected_environment='prod')


def _derive_status(manifest: dict[str, Any]) -> str:
    artifacts = manifest['environmentArtifacts']
    immutable_images = all(('digest' in descriptor for artifact in artifacts.values() for descriptor in artifact['images'].values()))
    candidate_complete = manifest.get('candidateId') is not None
    if not immutable_images:
        return 'build-input'
    if not candidate_complete:
        return 'component-ready'
    environments = set(manifest['environmentReceipts'])
    rollback = manifest.get('rollbackReceipt')
    rollout = manifest.get('rolloutReceipt')
    rollback_status = rollback.get('status') if isinstance(rollback, dict) else None
    preprod_ready = set(PRE_PROD_ENVIRONMENTS).issubset(environments)
    rollback_outcomes = {'not_triggered', 'rolled_back', 'rollback_failed'}
    if 'prod' in environments or rollout is not None or rollback_status in rollback_outcomes:
        prod = manifest['environmentReceipts'].get('prod')
        if environments == set(ENVIRONMENTS) and isinstance(prod, dict) and isinstance(rollout, dict):
            terminal = {('passed', 'passed', 'not_triggered'): 'released', ('passed', 'failed', 'rolled_back'): 'rolled-back', ('failed', 'failed', 'rollback_failed'): 'rollback-failed'}.get((prod.get('status'), rollout.get('status'), rollback_status))
            if terminal is not None:
                return terminal
        raise ValueError('production receipts are incomplete or out of lifecycle order')
    if preprod_ready and rollback_status == 'ready':
        return 'deployable'
    return 'candidate-ready'


def _expected_gaps(manifest: dict[str, Any], status: str) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    if status == 'build-input':
        missing.extend((f'environmentArtifacts.{environment}.images.{owner}.digest' for environment in ENVIRONMENTS for owner in manifest['requiredEvidence']['environmentArtifacts'][environment] if 'digest' not in manifest['environmentArtifacts'][environment]['images'][owner]))
    if status in {'build-input', 'component-ready'}:
        missing.extend((f'applicationPackages.{build_product_id}' for build_product_id in APPLICATION_PACKAGES))
        missing.extend((*DISTRIBUTION_EVIDENCE_PATHS, 'opsPortal', 'contractGraphDigest', 'providerEvidence', 'testEvidence'))
    present_environments = set(manifest.get('environmentReceipts') or {})
    missing.extend((f'environmentReceipts.{environment}' for environment in ENVIRONMENTS if environment not in present_environments))
    rollback = manifest.get('rollbackReceipt')
    rollback_status = rollback.get('status') if isinstance(rollback, dict) else None
    if rollback_status not in {'ready', 'not_triggered', 'rolled_back', 'rollback_failed'}:
        missing.append('rollbackReceipt.ready')
    if manifest.get('rolloutReceipt') is None:
        missing.append('rolloutReceipt')
    if rollback_status not in {'not_triggered', 'rolled_back', 'rollback_failed'}:
        missing.append('rollbackReceipt.outcome')
    if status == 'released':
        blockers: list[str] = []
    elif status == 'rolled-back':
        blockers = ['candidate-rolled-back']
    elif status == 'rollback-failed':
        blockers = ['rollback-recovery-failed']
    elif status == 'deployable':
        blockers = ['prod-release-evidence-pending']
    elif status == 'candidate-ready':
        blockers = ['environment-qualification-evidence-pending']
    elif status == 'component-ready':
        blockers = ['whole-application-evidence-pending']
    else:
        blockers = ['immutable-image-evidence-pending', 'whole-application-evidence-pending']
    return (blockers, missing)


def _validate_frozen_diagnostic_snapshot(
    manifest: dict[str, Any],
    *,
    allowed_statuses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate retired snapshot bytes without granting any release authority."""
    forbidden_paths = sorted((path for path in _forbidden_field_paths(manifest) if path != 'configurationPackages' and (not (path.startswith('environmentArtifacts.') and path.endswith('.configurationPackages'))) and (not path.startswith('requiredEvidence.configurationPackages'))))
    if forbidden_paths:
        raise ValueError(f'release evidence manifest fields are forbidden: {forbidden_paths}')
    if set(manifest) != ROOT_FIELDS:
        missing = sorted(ROOT_FIELDS - set(manifest))
        extra = sorted(set(manifest) - ROOT_FIELDS)
        raise ValueError(f'release evidence manifest fields mismatch: missing={missing}, extra={extra}')
    if manifest.get('schema') != SCHEMA:
        raise ValueError('release evidence manifest schema mismatch')
    if 'images' in manifest or 'configurationPackages' in manifest:
        raise ValueError('retired flat release image/config fields are forbidden')
    status = str(manifest.get('status') or '')
    accepted = set(allowed_statuses or STATUSES)
    if status not in STATUSES or status not in accepted:
        raise ValueError(f'release evidence manifest status is invalid: {status!r}')
    source = manifest.get('source')
    if not isinstance(source, dict) or set(source) != {'gitSha', 'treeDigest', 'repository', 'workflowRunId', 'sourceArchiveDigest'}:
        raise ValueError('release evidence source is not canonical')
    if GIT_SHA_PATTERN.fullmatch(str(source.get('gitSha') or '')) is None:
        raise ValueError('release evidence source gitSha is invalid')
    if TREE_DIGEST_PATTERN.fullmatch(str(source.get('treeDigest') or '')) is None:
        raise ValueError('release evidence source treeDigest is invalid')
    if not str(source.get('repository') or '').strip() or not str(source.get('workflowRunId') or '').strip():
        raise ValueError('release evidence source repository or workflowRunId is missing')
    archive_digest = source.get('sourceArchiveDigest')
    if archive_digest is not None and DIGEST_PATTERN.fullmatch(str(archive_digest)) is None:
        raise ValueError('release evidence sourceArchiveDigest is invalid')
    if not str(manifest.get('generatedAt') or '').strip():
        raise ValueError('release evidence generatedAt is missing')
    if manifest.get('releaseTrainId') != canonical_release_train_digest(manifest):
        raise ValueError('release evidence releaseTrainId mismatch')
    required = _validate_required_evidence(manifest.get('requiredEvidence'))
    _validate_environment_artifacts(manifest.get('environmentArtifacts'), required_images=required['environmentArtifacts'], required_configurations=required['configurationPackages'], status=status)
    if status in {'build-input', 'component-ready'}:
        if manifest.get('applicationPackages') != {}:
            raise ValueError('applicationPackages must remain empty before candidate-ready')
        if any((manifest.get(key) is not None for key in DISTRIBUTION_EVIDENCE_PATHS)):
            raise ValueError('distribution evidence must remain absent before candidate-ready')
        if manifest.get('opsPortal') is not None:
            raise ValueError('opsPortal must remain absent before candidate-ready')
        if manifest.get('contractGraphDigest') is not None:
            raise ValueError('contractGraphDigest must remain empty before candidate-ready')
        if manifest.get('providerEvidence') != {} or manifest.get('testEvidence') != {}:
            raise ValueError('provider/test evidence must remain empty before candidate-ready')
    else:
        _validate_candidate_evidence(manifest)
    _validate_receipts(manifest)
    if status in {'build-input', 'component-ready'} and (manifest['environmentReceipts'] or manifest['rolloutReceipt'] is not None or manifest['rollbackReceipt'] is not None):
        raise ValueError('release receipts cannot precede candidate identity')
    derived_status = _derive_status(manifest)
    if status != derived_status:
        raise ValueError(f'release evidence lifecycle status mismatch: {status!r} != {derived_status!r}')
    blockers = manifest.get('blockers')
    missing_evidence = manifest.get('missingEvidence')
    if not isinstance(blockers, list) or not all((isinstance(item, str) for item in blockers)):
        raise ValueError('blockers must be a string list')
    if not isinstance(missing_evidence, list) or not all((isinstance(item, str) for item in missing_evidence)):
        raise ValueError('missingEvidence must be a string list')
    expected_blockers, expected_missing = _expected_gaps(manifest, status)
    if blockers != expected_blockers or missing_evidence != expected_missing:
        raise ValueError('release evidence blockers or missingEvidence do not match lifecycle')
    expected_candidate: str | None
    try:
        expected_candidate = canonical_candidate_digest(manifest)
    except ValueError:
        expected_candidate = None
    if manifest.get('candidateId') != expected_candidate:
        raise ValueError('release evidence candidate digest mismatch')
    digest = canonical_manifest_digest(manifest)
    if manifest.get('artifactDigest') != digest:
        raise ValueError('release evidence manifest digest mismatch')
    return manifest


def load_image_descriptors(directory: Path) -> dict[str, dict[str, dict[str, Any]]]:
    descriptors: dict[str, dict[str, dict[str, Any]]] = {environment: {} for environment in ENVIRONMENTS}
    for path in sorted(directory.glob('*/*.json')):
        descriptor = load_json(path)
        environment = str(descriptor.get('environment') or '').strip()
        owner = str(descriptor.get('runtimeImageOwner') or '').strip()
        if environment not in ENVIRONMENTS or not owner:
            raise ValueError(f'{path} missing environment/runtimeImageOwner')
        if path.parent.name != environment:
            raise ValueError(f'{path} descriptor path environment mismatch')
        if owner in descriptors[environment]:
            raise ValueError(f'duplicate image descriptor for {environment}/{owner}')
        descriptors[environment][owner] = descriptor
    return descriptors


def validate_descriptor(environment: str, owner: str, descriptor: dict[str, Any], *, expected_repository: str, expected_transport_ref: str) -> dict[str, Any]:
    label = f'{environment}/{owner}'
    if set(descriptor) != {'environment', 'runtimeImageOwner', 'repository', 'transportRef', 'digest', 'ref', 'attestations'}:
        raise ValueError(f'{label} image descriptor fields are not canonical')
    if descriptor.get('environment') != environment or descriptor.get('runtimeImageOwner') != owner:
        raise ValueError(f'{label} image descriptor identity mismatch')
    repository = str(descriptor.get('repository') or '').strip()
    transport_ref = str(descriptor.get('transportRef') or '').strip()
    digest = str(descriptor.get('digest') or '').strip()
    if repository != expected_repository:
        raise ValueError(f'{label} repository mismatch: {repository!r} != {expected_repository!r}')
    if transport_ref != expected_transport_ref:
        raise ValueError(f'{label} transport ref mismatch')
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError(f'{label} missing immutable OCI digest')
    expected_ref = f'{repository}@{digest}'
    if str(descriptor.get('ref') or '') != expected_ref:
        raise ValueError(f'{label} digest ref mismatch')
    attestations = descriptor.get('attestations')
    if not isinstance(attestations, dict):
        raise ValueError(f'{label} missing attestations')
    for attestation_type in ('spdxSbom', 'slsaProvenance'):
        value = str(attestations.get(attestation_type) or '').strip()
        if value != f'oci://{expected_ref}#{attestation_type}':
            raise ValueError(f'{label} missing {attestation_type} attestation reference')
    return {'repository': repository, 'transportRef': transport_ref, 'digest': digest, 'ref': expected_ref, 'attestations': {'spdxSbom': str(attestations['spdxSbom']), 'slsaProvenance': str(attestations['slsaProvenance'])}}


def load_release_evidence(artifact_dir: Path, descriptors_dir: Path) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    application_packages: dict[str, dict[str, str]] = {}
    ops_portal: dict[str, str] | None = None
    for descriptor_path in sorted(descriptors_dir.glob('*.json')):
        descriptor = load_json(descriptor_path)
        if set(descriptor) == APPLICATION_SOURCE_DESCRIPTOR_FIELDS:
            build_product_id = str(descriptor.get('buildProductId') or '')
            if build_product_id not in APPLICATION_PACKAGES:
                raise ValueError(f'unsupported App build product descriptor: {build_product_id}')
            if build_product_id in application_packages:
                raise ValueError(f'duplicate App build product descriptor: {build_product_id}')
            relative = _validate_relative_path(descriptor['path'], f'application package {build_product_id}')
            artifact_path = _bound_file(artifact_dir, relative, f'application package {build_product_id}')
            actual_digest = sha256_file(artifact_path)
            if descriptor['digest'] != actual_digest:
                raise ValueError(f'application package {build_product_id} digest mismatch')
            application_packages[build_product_id] = {'path': relative, 'digest': actual_digest, 'packageDigest': descriptor['packageDigest'], 'sourceRef': descriptor['sourceRef']}
            continue
        key = str(descriptor.get('evidenceKey') or '').strip()
        if key == 'opsPortal':
            if set(descriptor) != OPS_PORTAL_SOURCE_DESCRIPTOR_FIELDS:
                raise ValueError('opsPortal evidence descriptor is not canonical')
            if ops_portal is not None:
                raise ValueError('duplicate opsPortal evidence descriptor')
            relative = _validate_relative_path(descriptor['path'], 'opsPortal evidence')
            artifact_path = _bound_file(artifact_dir, relative, 'opsPortal evidence')
            actual_digest = sha256_file(artifact_path)
            if descriptor['digest'] != actual_digest:
                raise ValueError('opsPortal evidence digest mismatch')
            ops_portal = {'path': relative, 'digest': actual_digest, 'packageDigest': descriptor['packageDigest'], 'sourceRef': descriptor['sourceRef']}
            continue
        if set(descriptor) != {'evidenceKey', 'path', 'digest'}:
            raise ValueError(f'{descriptor_path} release evidence descriptor is not canonical')
        relative = _validate_relative_path(descriptor.get('path'), f"release evidence {key or '<missing>'}")
        declared_digest = str(descriptor.get('digest') or '').strip()
        if key not in (*REQUIRED_RELEASE_EVIDENCE, *OPTIONAL_RELEASE_EVIDENCE):
            raise ValueError(f'unsupported release evidence key: {key!r}')
        if key in evidence:
            raise ValueError(f'duplicate release evidence descriptor: {key}')
        artifact_path = _bound_file(artifact_dir, relative, f'release evidence {key}')
        actual_digest = sha256_file(artifact_path)
        if declared_digest != actual_digest:
            raise ValueError(f'release evidence {key} digest mismatch')
        evidence[key] = {'path': relative, 'digest': actual_digest, 'payload': load_json(artifact_path)}
    missing = sorted(set(REQUIRED_RELEASE_EVIDENCE) - set(evidence))
    extra = sorted(set(evidence) - set(REQUIRED_RELEASE_EVIDENCE) - set(OPTIONAL_RELEASE_EVIDENCE))
    if missing or extra:
        raise ValueError(f'release evidence descriptor set mismatch: missing={missing}, extra={extra}')
    if set(application_packages) != set(APPLICATION_PACKAGES):
        missing = sorted(set(APPLICATION_PACKAGES) - set(application_packages))
        extra = sorted(set(application_packages) - set(APPLICATION_PACKAGES))
        raise ValueError(f'App build product descriptor set mismatch: missing={missing}, extra={extra}')
    if ops_portal is None:
        raise ValueError('opsPortal evidence descriptor is missing')
    evidence['applicationPackages'] = application_packages
    evidence['opsPortal'] = ops_portal
    return evidence


def _verify_configuration_packages(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    for environment, artifact in manifest['environmentArtifacts'].items():
        packages = artifact['configurationPackages']
        for service, descriptor in packages.items():
            relative = _validate_relative_path(descriptor.get('path'), f'environmentArtifacts.{environment}.configurationPackages.{service}')
            path = _bound_file(artifact_dir, relative, f'{environment} release config for {service}')
            if descriptor.get('digest') != sha256_file(path):
                raise ValueError(f'{environment} release config digest mismatch for {service}')


def _verify_receipt_file(artifact_dir: Path, descriptor: dict[str, Any], label: str) -> None:
    path = _bound_file(artifact_dir, _validate_relative_path(descriptor['path'], label), label)
    if sha256_file(path) != descriptor['digest']:
        raise ValueError(f'{label} digest mismatch')
    payload = load_json(path)
    if payload != {key: descriptor[key] for key in RECEIPT_SOURCE_FIELDS}:
        raise ValueError(f'{label} payload binding mismatch')


def _verify_receipt_evidence_files(artifact_dir: Path, descriptor: dict[str, Any], label: str) -> None:
    """Recompute every raw file binding embedded in a canonical receipt."""
    found = 0

    def visit(value: Any, breadcrumb: str) -> None:
        nonlocal found
        if isinstance(value, dict):
            if 'path' in value or 'digest' in value:
                if not {'path', 'digest'}.issubset(value):
                    raise ValueError(f'{breadcrumb} raw evidence binding is incomplete')
                relative = _validate_relative_path(value['path'], breadcrumb)
                path = _bound_file(artifact_dir, relative, breadcrumb)
                if sha256_file(path) != value['digest']:
                    raise ValueError(f'{breadcrumb} raw evidence digest mismatch')
                found += 1
            for key, child in value.items():
                visit(child, f'{breadcrumb}.{key}')
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f'{breadcrumb}[{index}]')
    evidence = descriptor.get('evidence')
    if evidence is None and isinstance(descriptor.get('path'), str):
        relative = _validate_relative_path(descriptor['path'], label)
        payload = load_json(_bound_file(artifact_dir, relative, label))
        evidence = payload.get('evidence')
    visit(evidence, f'{label}.evidence')
    if found == 0:
        raise ValueError(f'{label} has no replayable raw evidence file binding')


def validate_application_package_evidence(payload: dict[str, Any], *, manifest: dict[str, Any], build_product_id: str) -> str:
    source = manifest['source']
    validate_package(payload, build_product_id=build_product_id, source_git_sha=str(source['gitSha']), source_tree_digest=str(source['treeDigest']))
    return application_package_digest(payload)


def validate_application_package_payload(payload: dict[str, Any], *, payload_root: Path, manifest: dict[str, Any], build_product_id: str) -> None:
    declared_digest = validate_application_package_evidence(payload, manifest=manifest, build_product_id=build_product_id)
    if sha256_tree(payload_root) != declared_digest:
        raise ValueError(f'application package payload digest mismatch: {build_product_id}')


def application_package_digest(payload: dict[str, Any]) -> str:
    digest = str(payload.get('packageDigest') or '')
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError('application package digest is not immutable')
    return digest


def _validate_frozen_diagnostic_snapshot_files(
    artifact_dir: Path,
    manifest: dict[str, Any],
    *,
    allowed_statuses: Iterable[str] | None = None,
) -> None:
    """Verify each exact file bound by one retired diagnostic snapshot."""
    _validate_frozen_diagnostic_snapshot(manifest, allowed_statuses=allowed_statuses)
    _verify_configuration_packages(artifact_dir, manifest)
    if manifest['status'] in {'build-input', 'component-ready'}:
        return
    for build_product_id, descriptor in manifest['applicationPackages'].items():
        relative = _validate_relative_path(descriptor.get('path'), f'applicationPackages.{build_product_id}')
        path = _bound_file(artifact_dir, relative, f'application package {build_product_id}')
        if sha256_file(path) != descriptor.get('digest'):
            raise ValueError(f'application package digest mismatch for {build_product_id}')
        package_digest = validate_application_package_evidence(load_json(path), manifest=manifest, build_product_id=build_product_id)
        if package_digest != descriptor.get('packageDigest'):
            raise ValueError(f'application package content binding mismatch for {build_product_id}')
    for evidence_key, canonical_path in DISTRIBUTION_EVIDENCE_PATHS.items():
        descriptor = manifest[evidence_key]
        path = _bound_file(artifact_dir, canonical_path, evidence_key)
        if descriptor.get('path') != canonical_path:
            raise ValueError(f'{evidence_key} path is not canonical')
        if sha256_file(path) != descriptor.get('digest'):
            raise ValueError(f'{evidence_key} digest mismatch')
    ops_portal = manifest['opsPortal']
    relative = _validate_relative_path(ops_portal.get('path'), 'opsPortal')
    path = _bound_file(artifact_dir, relative, 'opsPortal')
    if sha256_file(path) != ops_portal.get('digest'):
        raise ValueError('opsPortal evidence digest mismatch')
    payload = load_json(path)
    if payload.get('packageDigest') != ops_portal.get('packageDigest'):
        raise ValueError('opsPortal package digest mismatch')
    contract_graph = artifact_dir / 'evidence/contractGraph.json'
    if contract_graph.is_symlink() or not contract_graph.is_file() or sha256_file(contract_graph) != manifest['contractGraphDigest']:
        raise ValueError('contract graph digest mismatch')
    evidence_payloads: dict[str, dict[str, Any]] = {}
    for key in ('providerEvidence', 'testEvidence'):
        descriptor = manifest[key]
        relative = _validate_relative_path(descriptor.get('path'), key)
        path = _bound_file(artifact_dir, relative, key)
        if sha256_file(path) != descriptor.get('digest'):
            raise ValueError(f'{key} digest mismatch')
        evidence_payloads[key] = load_json(path)
    _verify_provider_raw_evidence(artifact_dir, evidence_payloads['providerEvidence'], expected_count=manifest['providerEvidence']['evidenceCount'])
    _verify_receipt_evidence_files(artifact_dir, manifest['testEvidence'], 'test evidence')
    for environment, descriptor in manifest['environmentReceipts'].items():
        _verify_receipt_file(artifact_dir, descriptor, f'environment receipt {environment}')
        _verify_receipt_evidence_files(artifact_dir, descriptor, f'environment receipt {environment}')
    if manifest['rolloutReceipt'] is not None:
        _verify_receipt_file(artifact_dir, manifest['rolloutReceipt'], 'rollout receipt')
        _verify_receipt_evidence_files(artifact_dir, manifest['rolloutReceipt'], 'rollout receipt')
    if manifest['rollbackReceipt'] is not None:
        _verify_receipt_file(artifact_dir, manifest['rollbackReceipt'], 'rollback receipt')
        _verify_receipt_evidence_files(artifact_dir, manifest['rollbackReceipt'], 'rollback receipt')



def validate_frozen_diagnostic_snapshot(
    manifest: dict[str, Any],
    *,
    artifact_dir: Path | None = None,
    allowed_statuses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Read an explicitly non-promotable rehearsal snapshot.

    The caller chooses this API by name; the result cannot be forwarded to a
    formal command because no formal stackctl surface accepts this object.
    """

    validated = _validate_frozen_diagnostic_snapshot(
        manifest, allowed_statuses=allowed_statuses
    )
    if artifact_dir is not None:
        _validate_frozen_diagnostic_snapshot_files(
            artifact_dir, validated, allowed_statuses=allowed_statuses
        )
    return validated


def validate_historical_release_snapshot(
    manifest: dict[str, Any],
    *,
    artifact_dir: Path | None = None,
    allowed_statuses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Read a historical release snapshot for diagnostics only."""

    validated = _validate_frozen_diagnostic_snapshot(
        manifest, allowed_statuses=allowed_statuses
    )
    if artifact_dir is not None:
        _validate_frozen_diagnostic_snapshot_files(
            artifact_dir, validated, allowed_statuses=allowed_statuses
        )
    return validated

def _verify_provider_raw_evidence(artifact_dir: Path, provider_payload: dict[str, Any], *, expected_count: int) -> None:
    readiness_count = expected_required_cell_count_from_readiness(provider_payload.get('readiness'))
    if expected_count != readiness_count or provider_payload.get('evidenceCount') != readiness_count:
        raise ValueError('providerEvidence manifest count does not match its dynamically validated required cell set')
    source = provider_payload.get('sourceEvidence')
    if not isinstance(source, dict) or set(source) != {'ref', 'digest', 'files'}:
        raise ValueError('providerEvidence sourceEvidence is not canonical')
    ref = str(source.get('ref') or '')
    digest = str(source.get('digest') or '')
    files = source.get('files')
    if OCI_DIGEST_REF_PATTERN.fullmatch(ref) is None or DIGEST_PATTERN.fullmatch(digest) is None or ref != ref.rsplit('@', 1)[0] + '@' + digest or (not isinstance(files, dict)) or (len(files) != expected_count) or (not files):
        raise ValueError('providerEvidence sourceEvidence is not immutable')
    expected_paths: set[str] = set()
    prefix = 'evidence/raw/provider/'
    for raw_path, raw_digest in files.items():
        if not isinstance(raw_path, str) or not raw_path.startswith(prefix) or DIGEST_PATTERN.fullmatch(str(raw_digest or '')) is None:
            raise ValueError('providerEvidence raw file descriptor is invalid')
        relative = _validate_relative_path(raw_path, 'providerEvidence raw file')
        path = _bound_file(artifact_dir, relative, 'providerEvidence raw file')
        if sha256_file(path) != raw_digest:
            raise ValueError(f'providerEvidence raw file digest mismatch: {raw_path}')
        expected_paths.add(relative)
    raw_root = artifact_dir / 'evidence/raw/provider'
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise ValueError('providerEvidence raw evidence root is missing or unsafe')
    actual_paths: set[str] = set()
    for path in raw_root.rglob('*'):
        if path.is_symlink():
            raise ValueError('providerEvidence raw evidence contains a symlink')
        if path.is_file():
            actual_paths.add(path.relative_to(artifact_dir).as_posix())
    if actual_paths != expected_paths:
        raise ValueError('providerEvidence raw evidence file set mismatch')


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'environment evidence is not a regular file: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return 'sha256:' + digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{label} evidence must be a JSON object')
    return payload


def _passed(payload: dict[str, Any]) -> bool:
    status = str(payload.get('status') or '').strip().lower()
    if status:
        return status in {'ok', 'passed', 'success'}
    command = payload.get('command')
    if command == 'health':
        checks = payload.get('checks')
        findings = payload.get('findings')
        return isinstance(checks, list) and bool(checks) and all((isinstance(item, dict) and item.get('ok') is True for item in checks)) and (findings is None or findings == [])
    if command == 'up':
        steps = payload.get('steps')
        return isinstance(steps, list) and bool(steps) and all((isinstance(item, dict) and item.get('exitCode') == 0 for item in steps))
    if command == 'deploy' and payload.get('target') == 'prod-hosted':
        release_state = payload.get('releaseState')
        rollback = payload.get('rollback')
        return payload.get('exitCode') == 0 and payload.get('dryRun') is False and (payload.get('rolloutDecision') == 'continue') and bool(payload.get('releaseReceiptId')) and bool(payload.get('releaseReceiptRef')) and isinstance(release_state, dict) and bool(release_state) and (payload.get('postDeployFailures') in (None, [])) and isinstance(rollback, dict) and (rollback.get('triggered') is False)
    return False


def _timestamp(payload: dict[str, Any], label: str) -> tuple[datetime, str]:
    value = payload.get('endedAt') or payload.get('verifiedAt') or payload.get('generatedAt') or payload.get('recordedAt')
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label} evidence has no authoritative completion timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError(f'{label} completion timestamp is invalid') from error
    return (parsed, value)


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return 'sha256:' + hashlib.sha256(encoded).hexdigest()


def _validate_lifecycle_exit(payload: dict[str, Any], *, environment: str, candidate: dict[str, str], rollback: dict[str, str]) -> None:
    if payload.get('schema') != 'quwoquan_data.environment_release_lifecycle_exit' or payload.get('passed') is not True or payload.get('sourceOwner') != 'qwq_data':
        raise ValueError(f'{environment} content lifecycle Exit is not passed')
    if payload.get('environment') != environment:
        raise ValueError(f'{environment} content lifecycle environment mismatch')
    expected = {'originalReleaseId': candidate['releaseId'], 'originalManifestDigest': candidate['releaseDigest'], 'replayManifestDigest': candidate['releaseDigest'], 'rollbackToReleaseId': rollback['releaseId'], 'rollbackToManifestDigest': rollback['releaseDigest']}
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f'{environment} content lifecycle {field} release binding mismatch')
    unsigned = dict(payload)
    declared_checksum = unsigned.pop('verificationChecksum', None)
    if declared_checksum != _canonical_digest(unsigned):
        raise ValueError(f'{environment} content lifecycle checksum mismatch')


def validate_release_closure_sources(*, pilot_release_attestation: Path, pilot_rollback_attestation: Path, lifecycle_exits: dict[str, Path], green_matrix: Path | None=None) -> dict[str, dict[str, Any]]:
    """Validate the exact producer files before any receipt can reference them."""
    for label, path in {'pilot release': pilot_release_attestation, 'pilot rollback': pilot_rollback_attestation, **{f'{environment} content lifecycle': path for environment, path in lifecycle_exits.items()}, **({'Green Matrix': green_matrix} if green_matrix is not None else {})}.items():
        if path is None or path.is_symlink() or (not path.is_file()):
            raise ValueError(f'{label} evidence is not a regular file')
    bindings = validate_release_attestations(str(pilot_release_attestation), str(pilot_rollback_attestation))
    candidate = bindings['candidate']
    rollback = bindings['rollback']
    if candidate['releaseId'] == rollback['releaseId'] or candidate['releaseDigest'] == rollback['releaseDigest']:
        raise ValueError('pilot release and rollback identities must be distinct')
    payloads = {'pilot-release': _load_json(pilot_release_attestation, 'pilot release attestation'), 'pilot-rollback': _load_json(pilot_rollback_attestation, 'pilot rollback attestation')}
    if set(lifecycle_exits) - {'alpha', 'beta', 'gamma'}:
        raise ValueError('content lifecycle environment set is not canonical')
    for environment, path in sorted(lifecycle_exits.items()):
        payload = _load_json(path, f'{environment} content lifecycle')
        _validate_lifecycle_exit(payload, environment=environment, candidate=candidate, rollback=rollback)
        payloads[f'content-lifecycle-{environment}'] = payload
    if green_matrix is not None:
        if set(lifecycle_exits) != {'alpha', 'beta', 'gamma'}:
            raise ValueError('Green Matrix closure requires all three lifecycle Exit receipts')
        matrix = _load_json(green_matrix, 'Green Matrix')
        phases = matrix.get('phases')
        if not (matrix.get('schema') == 'quwoquan.test.case-result' and matrix.get('caseId') == 'stackctl.local-env-gate.alpha-beta-gamma' and (matrix.get('status') == 'passed') and (matrix.get('claim') == 'ALPHA_BETA_GAMMA_LOCAL_GREEN') and (matrix.get('executionClass') == 'live') and (matrix.get('targets') == ['alpha-local', 'beta-local', 'gamma-local']) and isinstance(matrix.get('executed'), int) and (matrix['executed'] > 0) and (matrix.get('skipped') == 0) and (matrix.get('failureCategory') in {'', None}) and (DIGEST_PATTERN.fullmatch(str(matrix.get('baselineId') or '')) is not None) and (matrix.get('releaseId') == candidate['releaseId']) and (matrix.get('releaseDigest') == candidate['releaseDigest']) and isinstance(phases, list) and bool(phases) and all((isinstance(phase, dict) and phase.get('status') == 'passed' for phase in phases))):
            raise ValueError('Green Matrix is not the live pilot release result')
        environments = matrix.get('environments')
        expected_environments = {TARGETS[environment] for environment in ('alpha', 'beta', 'gamma')}
        if not isinstance(environments, dict) or set(environments) != expected_environments:
            raise ValueError('Green Matrix environment set is not canonical')
        for environment in ('alpha', 'beta', 'gamma'):
            target = TARGETS[environment]
            block = environments[target]
            release = block.get('release') if isinstance(block, dict) else None
            rollback_release = block.get('rollbackRelease') if isinstance(block, dict) else None
            if not isinstance(block, dict) or block.get('environment') != environment or block.get('target') != target or (not isinstance(release, dict)) or (release.get('releaseId') != candidate['releaseId']) or (release.get('releaseDigest') != candidate['releaseDigest']) or (not isinstance(rollback_release, dict)) or (rollback_release.get('releaseId') != rollback['releaseId']) or (rollback_release.get('releaseDigest') != rollback['releaseDigest']):
                raise ValueError(f'Green Matrix {environment} release binding mismatch')
        payloads['green-matrix'] = matrix
    return payloads


def _safe_relative_path(value: str, label: str) -> Path:
    relative = Path(value)
    if not value or relative.is_absolute() or '.' in relative.parts or ('..' in relative.parts):
        raise ValueError(f'{label} artifact-relative path is unsafe')
    return relative


def archive_exact_files(*, archive_root: Path, files: dict[str, tuple[Path, str]]) -> dict[str, dict[str, str]]:
    """Copy exact bytes to fixed artifact-relative paths without overwrite drift."""
    if archive_root.is_symlink():
        raise ValueError('evidence archive root cannot be a symbolic link')
    archive_root.mkdir(parents=True, exist_ok=True)
    resolved_root = archive_root.resolve(strict=True)
    descriptors: dict[str, dict[str, str]] = {}
    destinations: set[Path] = set()
    for label, (source_value, relative_value) in sorted(files.items()):
        source = source_value.expanduser()
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'{label} evidence is not a regular file')
        source = source.resolve(strict=True)
        relative = _safe_relative_path(relative_value, label)
        destination = resolved_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = destination.parent.resolve(strict=True)
        try:
            resolved_parent.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError(f'{label} evidence archive escapes its root') from error
        if destination in destinations:
            raise ValueError(f'duplicate evidence archive destination: {relative}')
        destinations.add(destination)
        if destination.is_symlink():
            raise ValueError(f'{label} evidence archive is a symbolic link')
        if source != destination:
            if destination.exists():
                if destination.read_bytes() != source.read_bytes():
                    raise ValueError(f'immutable evidence archive already differs: {relative}')
            else:
                shutil.copyfile(source, destination)
        digest = _sha256(destination)
        source_digest = _sha256(source)
        if digest != source_digest:
            raise ValueError(f'{label} evidence archive digest mismatch')
        descriptors[label] = {'path': relative.as_posix(), 'digest': digest}
    return descriptors


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def _receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop('receiptId', None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _validate_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label} timestamp is missing')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError(f'{label} timestamp is invalid') from error
    if parsed.tzinfo is None:
        raise ValueError(f'{label} timestamp has no timezone')
    return value


def _window_seconds(value: object) -> int:
    match = re.fullmatch('([1-9][0-9]*)([smh])', str(value or '').strip())
    if match is None:
        raise ValueError('SLO soak window is invalid')
    multiplier = {'s': 1, 'm': 60, 'h': 3600}[match.group(2)]
    return int(match.group(1)) * multiplier


def _validate_hosted_receipt(value: Any, *, service: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != HOSTED_RECEIPT_FIELDS:
        raise ValueError('hosted release receipt shape is not canonical')
    receipt_id = str(value.get('receiptId') or '')
    if value.get('schema') != HOSTED_RECEIPT_SCHEMA or value.get('authority') != HOSTED_AUTHORITY or value.get('service') != service or (RECEIPT_ID_PATTERN.fullmatch(receipt_id) is None) or (_receipt_id(value) != receipt_id):
        raise ValueError('hosted release receipt identity is invalid')
    for field in ('fromCandidateDigest', 'toCandidateDigest', 'artifactDigest', 'imageDigest', 'configDigest', 'contractGraphDigest', 'adapterDigest'):
        if DIGEST_PATTERN.fullmatch(str(value.get(field) or '')) is None:
            raise ValueError(f'hosted release receipt {field} is not immutable')
    if value.get('stage') not in STAGES:
        raise ValueError('hosted release receipt stage is invalid')
    if value.get('triggerStage') not in STAGES:
        raise ValueError('hosted release receipt triggerStage is invalid')
    for field in ('fromReleaseEvidenceRef', 'toReleaseEvidenceRef'):
        ref = str(value.get(field) or '')
        if re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}', ref) is None:
            raise ValueError(f'hosted release receipt {field} is not exact OCI')
    for field in ('fromImageTransportTag', 'toImageTransportTag'):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f'hosted release receipt {field} is missing')
    if value.get('decision') not in {'continue', 'pause', 'rolled_back', 'rollback_failed'}:
        raise ValueError('hosted release receipt decision is invalid')
    if value.get('rollbackOutcome') not in {'not_triggered', 'rolled_back', 'rollback_failed'}:
        raise ValueError('hosted release receipt rollback outcome is invalid')
    if not isinstance(value.get('expectedGeneration'), int) or not isinstance(value.get('committedGeneration'), int) or value['expectedGeneration'] < 0 or (value['committedGeneration'] != value['expectedGeneration'] + 1) or (not isinstance(value.get('sloReadback'), dict)):
        raise ValueError('hosted release receipt generation or SLO evidence is invalid')
    if service == 'prod-stack' and value.get('decision') == 'continue':
        hosted_release_ledger.validate_promotion_evidence(value['sloReadback'].get('promotionEvidence'), candidate_id=value.get('toCandidateDigest'), artifact_digest=value.get('artifactDigest'), stage=value.get('triggerStage'))
    post_checks = value.get('postChecks')
    if not isinstance(post_checks, list) or not all((isinstance(item, dict) and set(item) == {'name', 'status', 'receiptDigest'} and isinstance(item.get('name'), str) and bool(item['name']) and (item.get('status') in {'passed', 'failed'}) and (DIGEST_PATTERN.fullmatch(str(item.get('receiptDigest') or '')) is not None) for item in post_checks)):
        raise ValueError('hosted release receipt post-check evidence is invalid')
    _validate_timestamp(value.get('verifiedAt'), 'hosted release receipt')
    return value

def _validate_receipt_readback(payload: dict[str, Any], *, service: str) -> dict[str, Any]:
    if set(payload) != {'schema', 'authority', 'receipt', 'receiptRef'} or payload.get('schema') != HOSTED_RECEIPT_READBACK_SCHEMA or payload.get('authority') != HOSTED_AUTHORITY:
        raise ValueError('hosted receipt readback shape is invalid')
    receipt = _validate_hosted_receipt(payload.get('receipt'), service=service)
    if payload.get('receiptRef') != f"receipt:hosted:{receipt['receiptId']}":
        raise ValueError('hosted receipt readback reference is invalid')
    return receipt


def _validate_soak_readback(payload: dict[str, Any], *, service: str) -> dict[str, Any]:
    if set(payload) != {'schema', 'authority', 'receipt', 'receiptRef'} or payload.get('schema') != HOSTED_SOAK_READBACK_SCHEMA or payload.get('authority') != HOSTED_AUTHORITY:
        raise ValueError('hosted prod soak readback shape is invalid')
    receipt = payload.get('receipt')
    if not isinstance(receipt, dict) or set(receipt) != hosted_release_ledger.SOAK_RECEIPT_FIELDS or receipt.get('schema') != HOSTED_SOAK_RECEIPT_SCHEMA or (receipt.get('authority') != HOSTED_AUTHORITY) or (receipt.get('service') != service) or (RECEIPT_ID_PATTERN.fullmatch(str(receipt.get('receiptId') or '')) is None) or (_receipt_id(receipt) != receipt.get('receiptId')) or (payload.get('receiptRef') != f"receipt:hosted-soak:{receipt.get('receiptId')}"):
        raise ValueError('hosted prod soak receipt identity is invalid')
    request = {field: receipt[field] for field in hosted_release_ledger.SOAK_REQUEST_FIELDS if field != 'schema'}
    request['schema'] = hosted_release_ledger.SOAK_REQUEST_SCHEMA
    hosted_release_ledger._validate_soak_request(request)
    started_at = dt.datetime.fromisoformat(_validate_timestamp(receipt.get('soakStartedAt'), 'prod soak start').replace('Z', '+00:00'))
    ended_at = dt.datetime.fromisoformat(_validate_timestamp(receipt.get('soakEndedAt'), 'prod soak end').replace('Z', '+00:00'))
    verified_at = dt.datetime.fromisoformat(_validate_timestamp(receipt.get('verifiedAt'), 'prod soak receipt').replace('Z', '+00:00'))
    duration = receipt.get('soakDurationSeconds')
    if not isinstance(duration, int) or isinstance(duration, bool) or duration != int((ended_at - started_at).total_seconds()) or (duration < receipt['requiredSoakSeconds']) or (ended_at > verified_at):
        raise ValueError('hosted prod soak receipt duration is invalid')
    return receipt


def _validate_ledger_readback(payload: dict[str, Any], *, service: str) -> dict[str, Any]:
    if set(payload) != {'schema', 'authority', 'state', 'receipt', 'receiptRef'} or payload.get('schema') != HOSTED_READBACK_SCHEMA or payload.get('authority') != HOSTED_AUTHORITY or (not isinstance(payload.get('state'), dict)):
        raise ValueError('hosted ledger readback shape is invalid')
    state = payload['state']
    receipt = _validate_hosted_receipt(payload.get('receipt'), service=service)
    history_is_invalid = any((not isinstance(state.get(field), str) or (bool(state.get(field)) and RECEIPT_ID_PATTERN.fullmatch(str(state[field])) is None) for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values()))
    active_history_field = hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(str(state.get('trigger_stage') or ''))
    if set(state) != HOSTED_STATE_FIELDS or state.get('schema') != HOSTED_STATE_SCHEMA or state.get('authority') != HOSTED_AUTHORITY or (state.get('service') != service) or (state.get('receipt_id') != receipt['receiptId']) or (payload.get('receiptRef') != f"receipt:hosted:{receipt['receiptId']}") or (str(receipt['committedGeneration']) != state.get('generation')) or (receipt['fromCandidateDigest'] != state.get('from_candidate_digest')) or (receipt['toCandidateDigest'] != state.get('to_candidate_digest')) or (receipt['artifactDigest'] != state.get('artifact_digest')) or (receipt['rollbackOutcome'] != state.get('rollback_outcome')) or (receipt['triggerStage'] != state.get('trigger_stage')) or (receipt['fromReleaseEvidenceRef'] != state.get('from_release_evidence_ref')) or (receipt['toReleaseEvidenceRef'] != state.get('to_release_evidence_ref')) or (receipt['fromImageTransportTag'] != state.get('from_image_transport_tag')) or (receipt['toImageTransportTag'] != state.get('to_image_transport_tag')) or (receipt['lastGoodCandidateDigest'] != state.get('last_good_candidate_digest')) or history_is_invalid or (active_history_field is None) or (state.get(active_history_field) != receipt['receiptId']):
        raise ValueError('hosted ledger state and receipt binding is invalid')
    return receipt
