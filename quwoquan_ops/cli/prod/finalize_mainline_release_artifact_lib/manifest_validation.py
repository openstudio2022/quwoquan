"""ReleaseEvidenceManifest 结构、生命周期与收据描述符校验（逐字搬移自入口）。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_DESCRIPTOR_FIELDS,
    APPLICATION_PACKAGES,
    DIGEST_PATTERN,
    ENVIRONMENT_RECEIPT_SCHEMA,
    ENVIRONMENTS,
    FORBIDDEN_FIELDS,
    GIT_SHA_PATTERN,
    OCI_DIGEST_REF_PATTERN,
    PRE_PROD_ENVIRONMENTS,
    RECEIPT_DESCRIPTOR_FIELDS,
    RELEASE_CLOSURE_PATHS,
    ROLLBACK_RECEIPT_SCHEMA,
    ROLLOUT_RECEIPT_SCHEMA,
    ROOT_FIELDS,
    SCHEMA,
    STATUSES,
    TEST_LAYERS,
    TEST_RELEASE_CLOSURE_LABELS,
    TREE_DIGEST_PATTERN,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
    _canonical_json_bytes,
    canonical_candidate_digest,
    canonical_manifest_digest,
)


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{label} must be a non-empty string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def _validate_relative_path(value: Any, label: str) -> str:
    relative = str(value or "").strip()
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path is unsafe")
    return path.as_posix()


def _bound_file(artifact_dir: Path, relative: str, label: str) -> Path:
    root = artifact_dir.resolve()
    candidate = artifact_dir / relative
    resolved = candidate.resolve()
    if root not in resolved.parents or candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} is missing or escapes the release evidence root")
    return candidate


def _validate_required_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("requiredEvidence must be an object")
    expected_fields = {
        "environmentArtifacts",
        "configurationPackages",
        "applicationPackages",
        "opsPortal",
        "contractGraphDigest",
        "providerEvidence",
        "testEvidence",
        "environmentReceipts",
        "rolloutReceipt",
        "rollbackReceipt",
    }
    if set(value) != expected_fields:
        raise ValueError("requiredEvidence fields are not canonical")
    environment_artifacts = value["environmentArtifacts"]
    if not isinstance(environment_artifacts, dict) or set(
        environment_artifacts
    ) != set(ENVIRONMENTS):
        raise ValueError("requiredEvidence.environmentArtifacts is not four-environment")
    image_owners: list[str] | None = None
    for environment in ENVIRONMENTS:
        owners = _require_string_list(
            environment_artifacts[environment],
            f"requiredEvidence.environmentArtifacts.{environment}",
        )
        if image_owners is None:
            image_owners = owners
        elif owners != image_owners:
            raise ValueError("requiredEvidence environment image owner sets differ")
    configuration_packages = value["configurationPackages"]
    if not isinstance(configuration_packages, dict) or set(
        configuration_packages
    ) != set(ENVIRONMENTS):
        raise ValueError("requiredEvidence.configurationPackages is not four-environment")
    for environment in ENVIRONMENTS:
        _require_string_list(
            configuration_packages[environment],
            f"requiredEvidence.configurationPackages.{environment}",
        )
    applications = _require_string_list(
        value["applicationPackages"], "requiredEvidence.applicationPackages"
    )
    if tuple(applications) != APPLICATION_PACKAGES:
        raise ValueError("requiredEvidence.applicationPackages is not canonical")
    if value["opsPortal"] is not True:
        raise ValueError("requiredEvidence.opsPortal must be independently required")
    layers = _require_string_list(value["testEvidence"], "requiredEvidence.testEvidence")
    if tuple(layers) != TEST_LAYERS:
        raise ValueError("requiredEvidence.testEvidence is not canonical")
    environments = _require_string_list(
        value["environmentReceipts"], "requiredEvidence.environmentReceipts"
    )
    if tuple(environments) != ENVIRONMENTS:
        raise ValueError("requiredEvidence.environmentReceipts is not canonical")
    if any(
        value[field] is not True
        for field in (
            "contractGraphDigest",
            "providerEvidence",
            "rolloutReceipt",
            "rollbackReceipt",
        )
    ):
        raise ValueError("requiredEvidence omits a mandatory release fact")
    return value


def _validate_packages(
    value: Any,
    *,
    expected: Iterable[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} set is not canonical")
    for key, descriptor in value.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "digest"}:
            raise ValueError(f"{label}.{key} descriptor is not canonical")
        _validate_relative_path(descriptor.get("path"), f"{label}.{key}")
        if DIGEST_PATTERN.fullmatch(str(descriptor.get("digest") or "")) is None:
            raise ValueError(f"{label}.{key} digest is not immutable")
    return value


def _validate_content_descriptor(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != APPLICATION_DESCRIPTOR_FIELDS:
        raise ValueError(f"{label} descriptor is not canonical")
    _validate_relative_path(value.get("path"), label)
    for digest_key in ("digest", "packageDigest"):
        if DIGEST_PATTERN.fullmatch(str(value.get(digest_key) or "")) is None:
            raise ValueError(f"{label}.{digest_key} is not immutable")
    source_ref = str(value.get("sourceRef") or "")
    if OCI_DIGEST_REF_PATTERN.fullmatch(source_ref) is None:
        raise ValueError(f"{label}.sourceRef is not an immutable OCI reference")
    return value


def _validate_application_packages(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(APPLICATION_PACKAGES):
        raise ValueError("applicationPackages must contain exactly five build products")
    for build_product_id, descriptor in value.items():
        _validate_content_descriptor(
            descriptor,
            label=f"applicationPackages.{build_product_id}",
        )
    return value


def _validate_images(
    value: Any,
    *,
    required: list[str],
    status: str,
    environment: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"environmentArtifacts.{environment}.images set is not canonical")
    transport_tags: set[str] = set()
    for owner, image in value.items():
        label = f"environmentArtifacts.{environment}.images.{owner}"
        if not isinstance(image, dict):
            raise ValueError(f"{label} must be an object")
        repository = str(image.get("repository") or "").strip()
        transport_ref = str(image.get("transportRef") or "").strip()
        trust_domain = "prod" if environment == "prod" else "nonprod"
        if not repository.endswith(f"/{owner}-{trust_domain}"):
            raise ValueError(f"{label} repository is not trust-domain-bound")
        if not repository.startswith("ghcr.io/") or not transport_ref.startswith(
            repository + ":"
        ):
            raise ValueError(f"{label} transport reference is invalid")
        if transport_ref.endswith(":latest"):
            raise ValueError(f"{label} transport reference must not use latest")
        transport_tags.add(transport_ref[len(repository) + 1 :])
        if status == "build-input":
            if set(image) != {"repository", "transportRef"}:
                raise ValueError(f"{label} build input is not canonical")
            continue
        if set(image) != {
            "repository",
            "transportRef",
            "digest",
            "ref",
            "attestations",
        }:
            raise ValueError(f"{label} immutable descriptor is not canonical")
        digest = str(image.get("digest") or "")
        ref = str(image.get("ref") or "")
        if DIGEST_PATTERN.fullmatch(digest) is None or ref != f"{repository}@{digest}":
            raise ValueError(f"{label} digest reference is invalid")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or set(attestations) != {
            "spdxSbom",
            "slsaProvenance",
        }:
            raise ValueError(f"{label} attestations are incomplete")
        for kind in ("spdxSbom", "slsaProvenance"):
            if attestations.get(kind) != f"oci://{ref}#{kind}":
                raise ValueError(f"{label} {kind} reference is invalid")
    if len(transport_tags) != 1:
        raise ValueError(f"{environment} images must use one common transport tag")
    return value


def _validate_environment_artifacts(
    value: Any,
    *,
    required_images: dict[str, list[str]],
    required_configurations: dict[str, list[str]],
    status: str,
) -> dict[str, dict[str, Any]]:
    from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
        canonical_environment_artifact_digest,
    )

    if not isinstance(value, dict) or set(value) != set(ENVIRONMENTS):
        raise ValueError("environmentArtifacts must contain alpha/beta/gamma/prod")
    # DEC-005 信任域裁决：alpha/beta/gamma 同 owner 必须共享同一 nonprod digest，
    # prod 属于独立信任域（编译期 Provider binding 不同），digest 必须分叉。
    nonprod_digests: dict[str, str] = {}
    prod_digests: dict[str, str] = {}
    for environment in ENVIRONMENTS:
        artifact = value[environment]
        if not isinstance(artifact, dict) or set(artifact) != {
            "environment",
            "environmentArtifactDigest",
            "images",
            "configurationPackages",
        }:
            raise ValueError(f"environmentArtifacts.{environment} fields are not canonical")
        if artifact.get("environment") != environment:
            raise ValueError(f"environmentArtifacts.{environment} identity mismatch")
        images = _validate_images(
            artifact.get("images"),
            required=required_images[environment],
            status=status,
            environment=environment,
        )
        _validate_packages(
            artifact.get("configurationPackages"),
            expected=required_configurations[environment],
            label=f"environmentArtifacts.{environment}.configurationPackages",
        )
        declared = artifact.get("environmentArtifactDigest")
        if status == "build-input":
            # build-input 阶段镜像尚未 immutable，组合身份只由内容摘要构成
            # （DEC-006），因此环境摘要必须缺席，不得由 transport locator 预先合成。
            if declared is not None:
                raise ValueError(
                    f"environmentArtifacts.{environment} digest must be absent "
                    "before images are immutable"
                )
        else:
            projection_artifact = dict(artifact)
            projection_artifact["environmentArtifactDigest"] = None
            expected_digest = canonical_environment_artifact_digest(
                {"environmentArtifacts": {environment: projection_artifact}},
                environment,
            )
            if declared != expected_digest:
                raise ValueError(
                    f"environmentArtifacts.{environment} digest mismatch"
                )
        if status != "build-input":
            for owner, image in images.items():
                digest = str(image["digest"])
                if environment == "prod":
                    prod_digests[str(owner)] = digest
                else:
                    previous = nonprod_digests.setdefault(str(owner), digest)
                    if previous != digest:
                        raise ValueError(
                            "nonprod environmentArtifacts must share one image "
                            f"digest per owner: {owner} diverges at {environment}"
                        )
    for owner, digest in prod_digests.items():
        if nonprod_digests.get(owner) == digest:
            raise ValueError(
                "prod environmentArtifacts must not reuse the nonprod "
                f"trust-domain image digest: {owner}"
            )
    return value


def _forbidden_field_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_FIELDS:
                paths.append(path)
            paths.extend(_forbidden_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_forbidden_field_paths(child, f"{prefix}[{index}]"))
    return paths


def _validate_candidate_evidence(manifest: dict[str, Any]) -> None:
    applications = _validate_application_packages(manifest.get("applicationPackages"))
    _validate_content_descriptor(manifest.get("opsPortal"), label="opsPortal")
    application_evidence_refs = {
        descriptor["sourceRef"] for descriptor in applications.values()
    }
    if len(application_evidence_refs) != 1:
        raise ValueError("applicationPackages must use one application evidence OCI")
    if DIGEST_PATTERN.fullmatch(str(manifest.get("contractGraphDigest") or "")) is None:
        raise ValueError("contractGraphDigest is missing")
    provider = manifest.get("providerEvidence")
    if (
        not isinstance(provider, dict)
        or set(provider)
        != {"path", "digest", "status", "evidenceCount"}
        or provider.get("status") != "passed"
        or DIGEST_PATTERN.fullmatch(str(provider.get("digest") or "")) is None
        or not isinstance(provider.get("evidenceCount"), int)
        or provider["evidenceCount"] <= 0
    ):
        raise ValueError("providerEvidence is not passed and immutable")
    _validate_relative_path(provider.get("path"), "providerEvidence")
    test = manifest.get("testEvidence")
    if (
        not isinstance(test, dict)
            or set(test) != {"path", "digest", "status", "layers", "evidence"}
        or test.get("status") != "passed"
        or DIGEST_PATTERN.fullmatch(str(test.get("digest") or "")) is None
            or not isinstance(test.get("evidence"), dict)
            or not test["evidence"]
    ):
        raise ValueError("testEvidence is not passed and immutable")
    _validate_relative_path(test.get("path"), "testEvidence")
    layers = test.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(TEST_LAYERS):
        raise ValueError("testEvidence layers are not canonical")
    for layer in TEST_LAYERS:
        item = layers.get(layer)
        if (
            not isinstance(item, dict)
            or set(item) != {"status", "artifactDigest"}
            or item.get("status") != "passed"
            or DIGEST_PATTERN.fullmatch(str(item.get("artifactDigest") or "")) is None
        ):
            raise ValueError(f"testEvidence layer is not immutable: {layer}")
    evidence = test["evidence"]
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


def _validate_receipt_descriptor(
    descriptor: Any,
    *,
    manifest: dict[str, Any],
    kind: str,
    expected_environment: str,
) -> dict[str, Any]:
    if not isinstance(descriptor, dict) or set(descriptor) != RECEIPT_DESCRIPTOR_FIELDS:
        raise ValueError(f"{kind} receipt descriptor is not canonical")
    expected_schema = {
        "environment": ENVIRONMENT_RECEIPT_SCHEMA,
        "rollout": ROLLOUT_RECEIPT_SCHEMA,
        "rollback": ROLLBACK_RECEIPT_SCHEMA,
    }[kind]
    if descriptor.get("schema") != expected_schema:
        raise ValueError(f"{kind} receipt schema mismatch")
    if descriptor.get("environment") != expected_environment:
        raise ValueError(f"{kind} receipt environment mismatch")
    if kind == "rollback":
        allowed_statuses = {
            "ready",
            "not_triggered",
            "rolled_back",
            "rollback_failed",
        }
    elif kind == "rollout":
        allowed_statuses = {"passed", "failed"}
    elif expected_environment == "prod":
        allowed_statuses = {"passed", "failed"}
    else:
        allowed_statuses = {"passed"}
    if descriptor.get("status") not in allowed_statuses:
        raise ValueError(f"{kind} receipt status is invalid")
    if descriptor.get("candidateId") != manifest.get("candidateId"):
        raise ValueError(f"{kind} receipt candidateId mismatch")
    source = manifest["source"]
    if descriptor.get("sourceGitSha") != source["gitSha"]:
        raise ValueError(f"{kind} receipt source git mismatch")
    if descriptor.get("sourceTreeDigest") != source["treeDigest"]:
        raise ValueError(f"{kind} receipt source tree mismatch")
    for field in ("digest", "evidenceDigest"):
        if DIGEST_PATTERN.fullmatch(str(descriptor.get(field) or "")) is None:
            raise ValueError(f"{kind} receipt {field} is not immutable")
    evidence = descriptor.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError(f"{kind} receipt evidence projection is missing")
    expected_evidence_digest = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(evidence)
    ).hexdigest()
    if descriptor.get("evidenceDigest") != expected_evidence_digest:
        raise ValueError(f"{kind} receipt evidence projection digest mismatch")
    _validate_relative_path(descriptor.get("path"), f"{kind} receipt")
    if not str(descriptor.get("verifiedAt") or "").strip():
        raise ValueError(f"{kind} receipt verifiedAt is missing")
    return descriptor


def _validate_receipts(manifest: dict[str, Any]) -> None:
    environment_receipts = manifest.get("environmentReceipts")
    if not isinstance(environment_receipts, dict) or not set(
        environment_receipts
    ).issubset(ENVIRONMENTS):
        raise ValueError("environmentReceipts set is not canonical")
    for environment, descriptor in environment_receipts.items():
        _validate_receipt_descriptor(
            descriptor,
            manifest=manifest,
            kind="environment",
            expected_environment=environment,
        )
    rollout = manifest.get("rolloutReceipt")
    if rollout is not None:
        _validate_receipt_descriptor(
            rollout,
            manifest=manifest,
            kind="rollout",
            expected_environment="prod",
        )
    rollback = manifest.get("rollbackReceipt")
    if rollback is not None:
        _validate_receipt_descriptor(
            rollback,
            manifest=manifest,
            kind="rollback",
            expected_environment="prod",
        )


def _derive_status(manifest: dict[str, Any]) -> str:
    artifacts = manifest["environmentArtifacts"]
    immutable_images = all(
        "digest" in descriptor
        for artifact in artifacts.values()
        for descriptor in artifact["images"].values()
    )
    candidate_complete = manifest.get("candidateId") is not None
    if not immutable_images:
        return "build-input"
    if not candidate_complete:
        return "component-ready"

    environments = set(manifest["environmentReceipts"])
    rollback = manifest.get("rollbackReceipt")
    rollout = manifest.get("rolloutReceipt")
    rollback_status = rollback.get("status") if isinstance(rollback, dict) else None
    preprod_ready = set(PRE_PROD_ENVIRONMENTS).issubset(environments)
    rollback_outcomes = {"not_triggered", "rolled_back", "rollback_failed"}
    if "prod" in environments or rollout is not None or rollback_status in rollback_outcomes:
        prod = manifest["environmentReceipts"].get("prod")
        if environments == set(ENVIRONMENTS) and isinstance(
            prod, dict
        ) and isinstance(rollout, dict):
            terminal = {
                ("passed", "passed", "not_triggered"): "released",
                ("passed", "failed", "rolled_back"): "rolled-back",
                ("failed", "failed", "rollback_failed"): "rollback-failed",
            }.get((prod.get("status"), rollout.get("status"), rollback_status))
            if terminal is not None:
                return terminal
        raise ValueError("production receipts are incomplete or out of lifecycle order")
    if preprod_ready and rollback_status == "ready":
        return "deployable"
    return "candidate-ready"


def _expected_gaps(manifest: dict[str, Any], status: str) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    if status == "build-input":
        missing.extend(
            f"environmentArtifacts.{environment}.images.{owner}.digest"
            for environment in ENVIRONMENTS
            for owner in manifest["requiredEvidence"]["environmentArtifacts"][environment]
            if "digest"
            not in manifest["environmentArtifacts"][environment]["images"][owner]
        )
    if status in {"build-input", "component-ready"}:
        missing.extend(
            f"applicationPackages.{build_product_id}"
            for build_product_id in APPLICATION_PACKAGES
        )
        missing.extend(
            ("opsPortal", "contractGraphDigest", "providerEvidence", "testEvidence")
        )
    present_environments = set(manifest.get("environmentReceipts") or {})
    missing.extend(
        f"environmentReceipts.{environment}"
        for environment in ENVIRONMENTS
        if environment not in present_environments
    )
    rollback = manifest.get("rollbackReceipt")
    rollback_status = rollback.get("status") if isinstance(rollback, dict) else None
    if rollback_status not in {
        "ready",
        "not_triggered",
        "rolled_back",
        "rollback_failed",
    }:
        missing.append("rollbackReceipt.ready")
    if manifest.get("rolloutReceipt") is None:
        missing.append("rolloutReceipt")
    if rollback_status not in {"not_triggered", "rolled_back", "rollback_failed"}:
        missing.append("rollbackReceipt.outcome")

    if status == "released":
        blockers: list[str] = []
    elif status == "rolled-back":
        blockers = ["candidate-rolled-back"]
    elif status == "rollback-failed":
        blockers = ["rollback-recovery-failed"]
    elif status == "deployable":
        blockers = ["prod-release-evidence-pending"]
    elif status == "candidate-ready":
        blockers = ["environment-qualification-evidence-pending"]
    elif status == "component-ready":
        blockers = ["whole-application-evidence-pending"]
    else:
        blockers = [
            "immutable-image-evidence-pending",
            "whole-application-evidence-pending",
        ]
    return blockers, missing


def validate_manifest(
    manifest: dict[str, Any],
    *,
    allowed_statuses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate the one canonical online contract and reject forbidden fields."""

    forbidden_paths = sorted(
        path
        for path in _forbidden_field_paths(manifest)
        if path != "configurationPackages"
        and not (
            path.startswith("environmentArtifacts.")
            and path.endswith(".configurationPackages")
        )
        and not path.startswith("requiredEvidence.configurationPackages")
    )
    if forbidden_paths:
        raise ValueError(
            f"release evidence manifest fields are forbidden: {forbidden_paths}"
        )
    if set(manifest) != ROOT_FIELDS:
        missing = sorted(ROOT_FIELDS - set(manifest))
        extra = sorted(set(manifest) - ROOT_FIELDS)
        raise ValueError(
            f"release evidence manifest fields mismatch: missing={missing}, extra={extra}"
        )
    if manifest.get("schema") != SCHEMA:
        raise ValueError("release evidence manifest schema mismatch")
    if "images" in manifest or "configurationPackages" in manifest:
        raise ValueError("retired flat release image/config fields are forbidden")
    status = str(manifest.get("status") or "")
    accepted = set(allowed_statuses or STATUSES)
    if status not in STATUSES or status not in accepted:
        raise ValueError(f"release evidence manifest status is invalid: {status!r}")

    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "gitSha",
        "treeDigest",
        "repository",
        "workflowRunId",
        "sourceArchiveDigest",
    }:
        raise ValueError("release evidence source is not canonical")
    if GIT_SHA_PATTERN.fullmatch(str(source.get("gitSha") or "")) is None:
        raise ValueError("release evidence source gitSha is invalid")
    if TREE_DIGEST_PATTERN.fullmatch(str(source.get("treeDigest") or "")) is None:
        raise ValueError("release evidence source treeDigest is invalid")
    if not str(source.get("repository") or "").strip() or not str(
        source.get("workflowRunId") or ""
    ).strip():
        raise ValueError("release evidence source repository or workflowRunId is missing")
    archive_digest = source.get("sourceArchiveDigest")
    if archive_digest is not None and DIGEST_PATTERN.fullmatch(
        str(archive_digest)
    ) is None:
        raise ValueError("release evidence sourceArchiveDigest is invalid")
    if not str(manifest.get("generatedAt") or "").strip():
        raise ValueError("release evidence generatedAt is missing")
    from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
        canonical_release_train_digest,
    )

    if manifest.get("releaseTrainId") != canonical_release_train_digest(manifest):
        raise ValueError("release evidence releaseTrainId mismatch")

    required = _validate_required_evidence(manifest.get("requiredEvidence"))
    _validate_environment_artifacts(
        manifest.get("environmentArtifacts"),
        required_images=required["environmentArtifacts"],
        required_configurations=required["configurationPackages"],
        status=status,
    )

    if status in {"build-input", "component-ready"}:
        if manifest.get("applicationPackages") != {}:
            raise ValueError("applicationPackages must remain empty before candidate-ready")
        if manifest.get("opsPortal") is not None:
            raise ValueError("opsPortal must remain absent before candidate-ready")
        if manifest.get("contractGraphDigest") is not None:
            raise ValueError("contractGraphDigest must remain empty before candidate-ready")
        if manifest.get("providerEvidence") != {} or manifest.get("testEvidence") != {}:
            raise ValueError("provider/test evidence must remain empty before candidate-ready")
    else:
        _validate_candidate_evidence(manifest)

    _validate_receipts(manifest)
    if status in {"build-input", "component-ready"} and (
        manifest["environmentReceipts"]
        or manifest["rolloutReceipt"] is not None
        or manifest["rollbackReceipt"] is not None
    ):
        raise ValueError("release receipts cannot precede candidate identity")

    derived_status = _derive_status(manifest)
    if status != derived_status:
        raise ValueError(
            f"release evidence lifecycle status mismatch: {status!r} != {derived_status!r}"
        )
    blockers = manifest.get("blockers")
    missing_evidence = manifest.get("missingEvidence")
    if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
        raise ValueError("blockers must be a string list")
    if not isinstance(missing_evidence, list) or not all(
        isinstance(item, str) for item in missing_evidence
    ):
        raise ValueError("missingEvidence must be a string list")
    expected_blockers, expected_missing = _expected_gaps(manifest, status)
    if blockers != expected_blockers or missing_evidence != expected_missing:
        raise ValueError("release evidence blockers or missingEvidence do not match lifecycle")

    expected_candidate: str | None
    try:
        expected_candidate = canonical_candidate_digest(manifest)
    except ValueError:
        expected_candidate = None
    if manifest.get("candidateId") != expected_candidate:
        raise ValueError("release evidence candidate digest mismatch")
    digest = canonical_manifest_digest(manifest)
    if manifest.get("artifactDigest") != digest:
        raise ValueError("release evidence manifest digest mismatch")
    return manifest
