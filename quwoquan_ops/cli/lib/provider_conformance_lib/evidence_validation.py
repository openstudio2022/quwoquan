"""Provider Conformance 证据集的逐条完整性与一致性校验。"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib.output_paths import output_root

from .attestation import (
    _current_adapter_digest,
    _current_contract_graph_digest,
    _digest_bytes,
)
from .candidate import (
    active_candidate_receipt_issues,
    binding_config_digest,
    candidate_image_digest,
)
from .case_results import (
    _observability_refs_valid,
    _release_readiness_valid,
    _validate_execution_report,
    load_case_results,
)
from .constants import (
    ADAPTER_PATTERN,
    ALLOWED_FIELDS,
    ASSERTION_ID_PATTERN,
    CAPABILITY_PATTERN,
    COMMIT_PATTERN,
    ENVIRONMENTS,
    MAX_EVIDENCE_AGE,
    PUBLIC_ASSERTION_IDS,
    RELEASE_ASSERTION_IDS,
    REQUIRED_FIELDS,
    SHA256_PATTERN,
    execution_profile_for,
    requires_release_readiness,
)
from .evidence_store import _issue, _output_path
from .governance_bindings import (
    _binding_root_ids,
    _is_non_empty_string,
    _root_id_list,
    _selected_binding,
    _valid_receipt_ref,
    compiled_capability_binding_roots,
    required_metric_refs,
)
from .sources import discover_test_sources, source_for_cell

def validate_evidence(
    evidence: Iterable[Mapping[str, Any]],
    *,
    registry: Mapping[str, Any],
    root: Path | None = None,
    current_commit: str | None = None,
    compiled: Mapping[str, Any] | None = None,
    source_catalog: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
    expected_image_digest: str | None = None,
) -> list[str]:
    issues: list[str] = []
    compiled_governance = compiled
    if compiled_governance is None:
        compiled_governance, _ = governance.compile_governance(
            registry,
            governance.load_bindings(),
            governance.load_conformance_manifest(),
        )
    discovered_sources, source_issues = (
        discover_test_sources() if source_catalog is None else (dict(source_catalog), [])
    )
    issues.extend(source_issues)
    configured_expected_image = (
        expected_image_digest
        if expected_image_digest is not None
        else os.environ.get("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", "")
    )
    adapter_by_id = {
        str(adapter.get("adapter_id")): adapter
        for adapter in registry.get("adapters", [])
        if isinstance(adapter, Mapping)
    }
    capability_by_id = {
        str(capability.get("capability_id")): capability
        for capability in registry.get("capabilities", [])
        if isinstance(capability, Mapping)
    }
    configured_root = Path(root) if root is not None else output_root()
    duplicate_cells: set[tuple[str, str, str]] = set()
    artifact_refs: set[str] = set()
    for index, item in enumerate(evidence):
        location = str(item.get("_source") or f"evidence[{index}]")
        fields = set(item) - {"_source"}
        missing = REQUIRED_FIELDS - fields
        unknown = fields - ALLOWED_FIELDS
        if missing:
            issues.append(_issue(location, f"missing required fields {sorted(missing)}"))
            continue
        if unknown:
            issues.append(_issue(location, f"contains unknown fields {sorted(unknown)}"))
            continue
        if item.get("schema") != "provider-conformance-evidence":
            issues.append(_issue(location, "has unsupported evidence schema"))
        if not isinstance(item.get("nonPromotable"), bool):
            issues.append(_issue(location, "nonPromotable must be a boolean"))
        if item.get("sourceTreeState") not in {"clean", "dirty"}:
            issues.append(_issue(location, "sourceTreeState must be clean or dirty"))
        if item.get("commitReview") not in {"reviewed", "unreviewed"}:
            issues.append(_issue(location, "commitReview must be reviewed or unreviewed"))
        if item.get("candidateStatus") not in {"active_immutable", "unverified"}:
            issues.append(
                _issue(
                    location,
                    "candidateStatus must be active_immutable or unverified",
                )
            )
        candidate_receipt_ref = item.get("candidateReceiptRef")
        candidate_receipt_digest = item.get("candidateReceiptDigest")
        if item.get("candidateStatus") == "active_immutable":
            if (
                not isinstance(candidate_receipt_ref, str)
                or not candidate_receipt_ref.startswith(
                    f".qwq_output/env/{item.get('environment')}/"
                )
                or not isinstance(candidate_receipt_digest, str)
                or SHA256_PATTERN.fullmatch(candidate_receipt_digest) is None
            ):
                issues.append(
                    _issue(
                        location,
                        "active candidate requires a canonical receipt ref and digest",
                    )
                )
        elif candidate_receipt_ref != "" or candidate_receipt_digest != "":
            issues.append(
                _issue(
                    location,
                    "unverified candidate must not claim a candidate receipt",
                )
            )
        if item.get("attestationAuthority") not in {"ci", "local"}:
            issues.append(_issue(location, "attestationAuthority must be ci or local"))
        if (
            item.get("sourceTreeState") == "dirty"
            or item.get("commitReview") != "reviewed"
            or item.get("candidateStatus") != "active_immutable"
            or item.get("attestationAuthority") != "ci"
        ) and item.get("nonPromotable") is not True:
            issues.append(
                _issue(
                    location,
                    "dirty/unreviewed/non-CI/unverified evidence must fail closed "
                    "with nonPromotable=true",
                )
            )
        supplied_attestation = item.get("artifactAttestation")
        if (
            item.get("attestationAuthority") == "local"
            and isinstance(supplied_attestation, str)
            and not supplied_attestation.startswith("local-sha256:")
        ):
            issues.append(
                _issue(
                    location,
                    "local attestation authority must use a local-sha256 checksum",
                )
            )
        if (
            item.get("attestationAuthority") == "ci"
            and isinstance(supplied_attestation, str)
            and not supplied_attestation.startswith("hmac-sha256:")
        ):
            issues.append(
                _issue(
                    location,
                    "CI attestation authority must use an HMAC-SHA256 attestation",
                )
            )
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
            issues.append(_issue(location, "adapterId must be a stable Adapter ID"))
            continue
        adapter = adapter_by_id.get(adapter_id)
        if adapter is None:
            issues.append(_issue(location, "adapterId is not registered"))
            continue
        capability = (
            capability_by_id.get(capability_id)
            if isinstance(capability_id, str)
            else None
        )
        if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
            issues.append(_issue(location, "capabilityId must be a stable Capability ID"))
        elif adapter.get("capability_id") != capability_id:
            issues.append(_issue(location, "capabilityId does not match adapterId"))
        elif not _is_non_empty_string(
            (capability_by_id.get(capability_id) or {}).get("canonical_port")
        ):
            issues.append(
                _issue(
                    location,
                    "capabilityId does not resolve to a registered canonical typed Port",
                )
            )
        elif item.get("typedPort") != capability.get("canonical_port"):
            issues.append(
                _issue(location, "typedPort does not match the capability canonical typed Port")
            )
        elif item.get("contractRef") != capability.get("source"):
            issues.append(
                _issue(location, "contractRef does not match the capability contract source")
            )
        evidence_root_ids = _root_id_list(item.get("bindingRoots"))
        if evidence_root_ids is None:
            issues.append(
                _issue(location, "bindingRoots must be a non-empty unique ordered root_id list")
            )
        elif not isinstance(capability, Mapping):
            issues.append(
                _issue(location, "bindingRoots cannot resolve an evidence capability")
            )
        else:
            registry_root_ids = _binding_root_ids(capability.get("binding_roots"))
            try:
                compiled_roots = compiled_capability_binding_roots(
                    compiled_governance,
                    capability_id=capability_id,
                )
            except ValueError as exc:
                issues.append(_issue(location, str(exc)))
            else:
                compiled_root_ids = _binding_root_ids(compiled_roots)
                if registry_root_ids is None or compiled_root_ids is None:
                    issues.append(
                        _issue(
                            location,
                            "registry/compiled capability binding roots must be non-empty and unique",
                        )
                    )
                elif registry_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "registry and compiled capability binding roots diverge",
                        )
                    )
                elif evidence_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "bindingRoots must strictly match registry/compiled capability roots",
                        )
                    )
        environment = item.get("environment")
        layer = item.get("testLayer")
        expected_source: Mapping[str, Any] | None = None
        selected_binding: Mapping[str, Any] | None = None
        compiled_roots: list[dict[str, Any]] | None = None
        expected_profile = (
            execution_profile_for(environment, layer)
            if isinstance(environment, str) and isinstance(layer, str)
            else None
        )
        if expected_profile is None:
            issues.append(_issue(location, "environment/testLayer is not a required conformance cell"))
        elif item.get("executionProfile") != expected_profile:
            issues.append(_issue(location, "executionProfile does not match the nine-cell contract"))
        else:
            selected_binding = _selected_binding(
                compiled_governance,
                capability_id=capability_id,
                environment=environment,
            )
            selected_adapter_id = (
                selected_binding.get("adapter_id")
                if isinstance(selected_binding, Mapping)
                else None
            )
            if not isinstance(selected_adapter_id, str):
                issues.append(
                    _issue(
                        location,
                        "capability has no selected Binding adapter in this evidence environment",
                    )
                )
            elif not governance.requires_provider_conformance(selected_binding):
                issues.append(
                    _issue(
                        location,
                        "first-party authority Bindings are not Provider Conformance cells",
                    )
                )
            elif adapter_id != selected_adapter_id:
                issues.append(
                    _issue(
                        location,
                        "adapterId does not match the environment-selected Binding adapter",
                    )
                )
            expected_source = source_for_cell(
                capability_id=str(capability_id),
                adapter_id=adapter_id,
                layer=layer,
                sources=discovered_sources,
            )
            if expected_source is None:
                issues.append(
                    _issue(
                        location,
                        "no self-describing executable Provider Conformance source exists "
                        "for the selected capability/adapter/layer",
                    )
                )
            else:
                if item.get("testSource") != expected_source.get("testSource"):
                    issues.append(
                        _issue(location, "testSource does not match the discovered source contract")
                    )
                if item.get("testSourceDigest") != expected_source.get("testSourceDigest"):
                    issues.append(
                        _issue(location, "testSourceDigest does not match current source bytes")
                    )
                if item.get("testTarget") != expected_source.get("target"):
                    issues.append(
                        _issue(location, "testTarget does not match the discovered source contract")
                    )
                if item.get("typedPort") != expected_source.get("typedPort"):
                    issues.append(
                        _issue(location, "typedPort does not match the discovered source contract")
                    )
                if item.get("contractRef") != expected_source.get("contractRef"):
                    issues.append(
                        _issue(location, "contractRef does not match the discovered source contract")
                    )
                if item.get("networkBoundary") != expected_source.get("networkBoundary"):
                    issues.append(
                        _issue(location, "networkBoundary does not match the discovered source contract")
                    )
                if item.get("acceptanceRefs") != expected_source.get("acceptanceRefs"):
                    issues.append(
                        _issue(location, "acceptanceRefs must exactly match source spec_ref values")
                    )
            if isinstance(selected_binding, Mapping):
                try:
                    compiled_roots = compiled_capability_binding_roots(
                        compiled_governance,
                        capability_id=str(capability_id),
                    )
                except ValueError:
                    compiled_roots = None
            implementation_status = adapter.get("implementation_status")
            accepted_statuses = (
                governance.READY_IMPLEMENTATION_STATUSES
                if environment in governance.RELEASE_ADAPTER_ENVIRONMENTS
                else {
                    *governance.READY_IMPLEMENTATION_STATUSES,
                    "sandbox",
                }
            )
            if implementation_status not in accepted_statuses:
                issues.append(
                    _issue(
                        location,
                        "adapterId implementation is not eligible for this environment evidence",
                    )
                )
        cell = (str(capability_id), str(environment), str(layer))
        if cell in duplicate_cells:
            issues.append(_issue(location, "duplicates a Capability/environment/layer cell"))
        duplicate_cells.add(cell)
        if item.get("status") != "passed":
            issues.append(
                _issue(
                    location,
                    "blocked/failed/dry-run reports are not Provider Conformance evidence",
                )
            )
        parsed_time: datetime | None = None
        try:
            parsed_time = datetime.fromisoformat(str(item["executedAt"]).replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("missing timezone")
            if parsed_time > datetime.now(timezone.utc):
                issues.append(_issue(location, "executedAt cannot be in the future"))
            elif current_commit is not None and datetime.now(timezone.utc) - parsed_time > MAX_EVIDENCE_AGE:
                issues.append(_issue(location, "executedAt exceeds the 24-hour readiness window"))
        except (TypeError, ValueError):
            issues.append(_issue(location, "executedAt must be an ISO-8601 timestamp with timezone"))
        artifact_path: Path | None = None
        test_artifact_path: Path | None = None
        for field, destination in (
            ("artifactRef", "execution"),
            ("testArtifactRef", "test"),
        ):
            reference = item.get(field)
            if not isinstance(reference, str) or not reference.startswith(
                f".qwq_output/env/{environment}/runs/"
            ):
                issues.append(
                    _issue(location, f"{field} must remain inside its environment run root")
                )
                continue
            path = _output_path(reference, root=configured_root)
            if path is None or not path.exists():
                issues.append(_issue(location, f"{field} must resolve to an existing output artifact"))
            elif configured_root.resolve() not in path.parents and path != configured_root:
                issues.append(_issue(location, f"{field} escapes configured output root"))
            elif reference in artifact_refs:
                issues.append(_issue(location, f"{field} must identify one conformance cell only"))
            artifact_refs.add(reference)
            if destination == "execution":
                artifact_path = path
            else:
                test_artifact_path = path
        for field in (
            "artifactDigest",
            "testArtifactDigest",
            "testSourceDigest",
            "imageDigest",
            "configDigest",
            "contractGraphDigest",
            "adapterDigest",
        ):
            if not isinstance(item.get(field), str) or not SHA256_PATTERN.fullmatch(str(item[field])):
                issues.append(_issue(location, f"{field} must be a sha256 digest"))
        if artifact_path is not None and artifact_path.exists():
            issues.extend(
                _validate_execution_report(
                    artifact_path=artifact_path,
                    evidence=item,
                    expected_source=expected_source,
                )
            )
        if test_artifact_path is not None and test_artifact_path.exists():
            expected_test_artifact_digest = _digest_bytes(test_artifact_path.read_bytes())
            if item.get("testArtifactDigest") != expected_test_artifact_digest:
                issues.append(
                    _issue(
                        location,
                        "testArtifactDigest does not match the test-owned CaseResult artifact",
                    )
                )
            if expected_source is not None and isinstance(environment, str):
                _, case_result_issues = load_case_results(
                    test_artifact_path,
                    source=expected_source,
                    environment=environment,
                    config_digest=str(item.get("configDigest") or ""),
                )
                issues.extend(case_result_issues)
        if not isinstance(item.get("commit"), str) or not COMMIT_PATTERN.fullmatch(str(item["commit"])):
            issues.append(_issue(location, "commit must be a git commit digest"))
        elif current_commit is not None and item["commit"] != current_commit:
            issues.append(_issue(location, "commit does not match the current source revision"))
        expected_image = configured_expected_image
        if expected_image_digest is None and environment in ENVIRONMENTS:
            try:
                expected_image = candidate_image_digest(
                    str(environment),
                    registry=registry,
                )
            except ValueError as exc:
                issues.append(_issue(location, str(exc)))
                expected_image = ""
        if not isinstance(expected_image, str) or not SHA256_PATTERN.fullmatch(expected_image):
            issues.append(
                _issue(
                    location,
                    "active immutable candidate image digest is unavailable",
                )
            )
        elif item.get("imageDigest") != expected_image:
            issues.append(_issue(location, "imageDigest does not match the active immutable image"))
        for candidate_issue in active_candidate_receipt_issues(
            item,
            registry=registry,
            root=configured_root,
        ):
            issues.append(_issue(location, candidate_issue))
        if isinstance(selected_binding, Mapping) and compiled_roots is not None:
            current_config_digest = binding_config_digest(selected_binding, compiled_roots)
            if item.get("configDigest") != current_config_digest:
                issues.append(
                    _issue(location, "configDigest does not match the current selected Binding")
                )
        current_contract_graph_digest = _current_contract_graph_digest()
        if current_contract_graph_digest is None:
            issues.append(_issue(location, "current ContractGraph digest is unavailable"))
        elif item.get("contractGraphDigest") != current_contract_graph_digest:
            issues.append(_issue(location, "contractGraphDigest is stale"))
        current_adapter_digest = _current_adapter_digest(adapter)
        if current_adapter_digest is None:
            issues.append(_issue(location, "current Adapter digest is unavailable"))
        elif item.get("adapterDigest") != current_adapter_digest:
            issues.append(_issue(location, "adapterDigest is stale"))
        if not isinstance(item.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(str(item["dataDigest"])):
            issues.append(_issue(location, "dataDigest must be a sha256 digest"))
        if not isinstance(item.get("assertionCount"), int) or item["assertionCount"] <= 0:
            issues.append(_issue(location, "assertionCount must be greater than zero"))
        assertion_ids = item.get("assertionIds")
        if (
            not isinstance(assertion_ids, list)
            or not assertion_ids
            or not all(
                isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
                for assertion_id in assertion_ids
            )
            or len(assertion_ids) != len(set(assertion_ids))
        ):
            issues.append(_issue(location, "assertionIds must be a non-empty unique stable list"))
        else:
            if not PUBLIC_ASSERTION_IDS.issubset(set(assertion_ids)):
                issues.append(
                    _issue(
                        location,
                        "assertionIds omit mandatory public Provider scenarios",
                    )
                )
            if expected_source is not None and tuple(sorted(assertion_ids)) != tuple(
                sorted(expected_source.get("assertionIds", []))
            ):
                issues.append(
                    _issue(
                        location,
                        "assertionIds must exactly match the discovered source assertion set",
                    )
                )
            if item.get("assertionCount") != len(assertion_ids):
                issues.append(_issue(location, "assertionCount must equal assertionIds length"))
        if item.get("networkBoundary") not in {
            "offline_harness",
            "remote_protocol",
            "user_journey",
        }:
            issues.append(_issue(location, "networkBoundary is invalid"))
        elif layer == "local_contract" and item["networkBoundary"] != "offline_harness":
            issues.append(_issue(location, "local_contract must use offline_harness"))
        elif layer == "api_integration" and item["networkBoundary"] != "remote_protocol":
            issues.append(_issue(location, "api_integration must use remote_protocol"))
        elif layer == "user_acceptance" and item["networkBoundary"] != "user_journey":
            issues.append(_issue(location, "user_acceptance must use user_journey"))
        if not _valid_receipt_ref(item.get("cleanupReceipt")):
            issues.append(
                _issue(location, "cleanupReceipt must be a non-sensitive receipt reference")
            )
        acceptance_refs = item.get("acceptanceRefs")
        if not isinstance(acceptance_refs, list) or not acceptance_refs or not all(
            isinstance(ref, str) and ref.startswith("specs/feature-tree/") for ref in acceptance_refs
        ):
            issues.append(
                _issue(location, "acceptanceRefs must be non-empty feature-tree references")
            )
        if (
            expected_source is not None
            and acceptance_refs != expected_source.get("acceptanceRefs")
        ):
            issues.append(
                _issue(location, "acceptanceRefs must exactly match source spec_ref values")
            )
        observability_refs = item.get("observabilityRefs")
        if not _observability_refs_valid(observability_refs):
            issues.append(
                _issue(location, "observabilityRefs must contain non-empty logs/traces/metrics lists")
            )
        else:
            required_metric_refs_for_capability = required_metric_refs(
                capability_id if isinstance(capability_id, str) else ""
            )
            if not set(required_metric_refs_for_capability).issubset(
                set(observability_refs["metrics"])
            ):
                issues.append(
                    _issue(
                        location,
                        "runtime.message.transport metrics must include fixed non-sensitive "
                        "pending_lag/dead_letter/publish_p95/consume_p95 references",
                    )
                )
        if item["status"] == "passed" and "failure" in item:
            issues.append(_issue(location, "passed evidence must not contain failure"))
        if expected_source is not None and item.get("testCommand") != shlex.join(
            list(expected_source["command"])
        ):
            issues.append(
                _issue(location, "testCommand does not match the source-declared executable argv")
            )
        is_release_cell = requires_release_readiness(str(environment), str(layer))
        if is_release_cell and not _release_readiness_valid(item):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance requires adapter-health, "
                    "switch and rollback receipt references",
                )
            )
        if is_release_cell and not RELEASE_ASSERTION_IDS.issubset(
            set(assertion_ids) if isinstance(assertion_ids, list) else set()
        ):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance must execute "
                    "adapter health/switch/rollback assertions",
                )
            )
        elif not is_release_cell and "releaseReadiness" in item:
            issues.append(
                _issue(
                    location,
                    "releaseReadiness is reserved for Gamma/Prod release "
                    "user_acceptance cells",
                )
            )
    return issues
