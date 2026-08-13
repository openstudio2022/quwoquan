"""证据驱动的 readiness 派生、聚合报告与 CLI main。

可被测试 patch 的符号（ci_attestation_authority_available、
_binding_preflight_ready、_current_commit）一律经薄入口 `_pc` 在调用时读取。
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance as _pc

from .attestation import _commit_digest, _digest, evidence_is_promotable
from .case_results import _release_readiness_valid
from .constants import (
    ASSERTION_ID_PATTERN,
    ENVIRONMENTS,
    LAYERS,
    READINESS_ENVIRONMENTS,
    RELEASE_ASSERTION_IDS,
    RELEASE_ENVIRONMENT,
    execution_profile_for,
)
from .evidence_store import _issue, load_evidence, load_evidence_paths
from .evidence_validation import validate_evidence
from .governance_bindings import (
    _selected_adapter_id,
    _selected_binding,
    provider_conformance_capability_ids,
)
from .sources import (
    discover_test_sources,
    local_source_coverage_issues,
    source_coverage_issues,
)

def _assertion_semantics(cell: Mapping[str, Any]) -> tuple[str, ...] | None:
    assertion_ids = cell.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or not all(
            isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        return None
    return tuple(
        sorted(
            assertion_id
            for assertion_id in assertion_ids
            if assertion_id not in RELEASE_ASSERTION_IDS
        )
    )


def _cells_share_release(
    cells: Iterable[Mapping[str, Any] | None],
    *,
    expected_environments: Iterable[str],
    require_adapter_digest: bool,
) -> bool:
    evidence_cells = list(cells)
    if not evidence_cells or any(
        cell is None or cell.get("status") != "passed" for cell in evidence_cells
    ):
        return False
    concrete_cells = [cell for cell in evidence_cells if cell is not None]
    if any(
        not evidence_is_promotable(
            cell,
            require_runtime_authority=False,
        )
        for cell in concrete_cells
    ):
        return False
    release_digests = {
        (
            _commit_digest(cell.get("commit")),
            _digest(cell.get("imageDigest")),
            _digest(cell.get("contractGraphDigest")),
        )
        for cell in concrete_cells
    }
    if len(release_digests) != 1 or any(None in digest for digest in release_digests):
        return False
    release_commit = next(iter(release_digests))[0]
    if not isinstance(release_commit, str) or not _pc.ci_attestation_authority_available(
        commit=release_commit
    ):
        return False
    if len({_assertion_semantics(cell) for cell in concrete_cells}) != 1:
        return False
    if any(_assertion_semantics(cell) is None for cell in concrete_cells):
        return False
    if (
        len({cell.get("typedPort") for cell in concrete_cells}) != 1
        or len({cell.get("contractRef") for cell in concrete_cells}) != 1
    ):
        return False
    for environment in expected_environments:
        environment_cells = [
            cell for cell in concrete_cells if cell.get("environment") == environment
        ]
        if not environment_cells or len(
            {_digest(cell.get("configDigest")) for cell in environment_cells}
        ) != 1:
            return False
        if _digest(environment_cells[0].get("configDigest")) is None:
            return False
    if require_adapter_digest:
        adapter_digests = {_digest(cell.get("adapterDigest")) for cell in concrete_cells}
        if len(adapter_digests) != 1 or None in adapter_digests:
            return False
    return True


def _cells_share_local_candidate(
    cells: Iterable[Mapping[str, Any] | None],
    *,
    environment: str,
) -> bool:
    """Prove one capability's three layers share one active local candidate.

    Local authority is intentionally accepted here, but it remains explicitly
    non-promotable.  This predicate never participates in release readiness.
    """
    evidence_cells = list(cells)
    if len(evidence_cells) != len(LAYERS) or any(
        cell is None
        or cell.get("status") != "passed"
        or cell.get("environment") != environment
        or cell.get("candidateStatus") != "active_immutable"
        for cell in evidence_cells
    ):
        return False
    concrete_cells = [cell for cell in evidence_cells if cell is not None]
    for cell in concrete_cells:
        authority = cell.get("attestationAuthority")
        attestation = cell.get("artifactAttestation")
        if authority == "local":
            if (
                cell.get("nonPromotable") is not True
                or not isinstance(attestation, str)
                or not attestation.startswith("local-sha256:")
            ):
                return False
        elif authority == "ci":
            if (
                not evidence_is_promotable(
                    cell,
                    require_runtime_authority=False,
                )
                or not isinstance(attestation, str)
                or not attestation.startswith("hmac-sha256:")
            ):
                return False
        else:
            return False
    candidate_identities = {
        (
            _commit_digest(cell.get("commit")),
            _digest(cell.get("imageDigest")),
            _digest(cell.get("contractGraphDigest")),
            cell.get("candidateReceiptRef"),
            _digest(cell.get("candidateReceiptDigest")),
        )
        for cell in concrete_cells
    }
    if len(candidate_identities) != 1 or any(
        value is None or not value
        for value in next(iter(candidate_identities), ())
    ):
        return False
    if (
        len({cell.get("adapterId") for cell in concrete_cells}) != 1
        or len({_digest(cell.get("adapterDigest")) for cell in concrete_cells}) != 1
        or len({_digest(cell.get("configDigest")) for cell in concrete_cells}) != 1
        or len({cell.get("typedPort") for cell in concrete_cells}) != 1
        or len({cell.get("contractRef") for cell in concrete_cells}) != 1
        or len({_assertion_semantics(cell) for cell in concrete_cells}) != 1
        or any(_assertion_semantics(cell) is None for cell in concrete_cells)
    ):
        return False
    return all(
        _digest(cell.get("adapterDigest")) is not None
        and _digest(cell.get("configDigest")) is not None
        for cell in concrete_cells
    )


def local_functional_readiness_issues(
    *,
    compiled: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
    environment: str,
) -> list[str]:
    """Validate one nonprod environment's compiled cells without release claims."""
    if environment not in ENVIRONMENTS:
        return [
            _issue(
                "local_functional_readiness",
                f"unsupported nonprod environment {environment}",
            )
        ]
    capability_ids = provider_conformance_capability_ids(compiled)
    expected = {
        (capability_id, environment, layer)
        for capability_id in capability_ids
        for layer in LAYERS
    }
    evidence_cells = list(evidence)
    observed = [
        (
            str(item.get("capabilityId") or ""),
            str(item.get("environment") or ""),
            str(item.get("testLayer") or ""),
        )
        for item in evidence_cells
    ]
    observed_set = set(observed)
    issues: list[str] = []
    duplicate = sorted(cell for cell in observed_set if observed.count(cell) > 1)
    missing = sorted(expected - observed_set)
    extra = sorted(observed_set - expected)
    expected_count = len(capability_ids) * len(LAYERS)
    if not capability_ids or len(expected) != expected_count:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "generated Bindings must derive a non-empty unique capability/cell set",
            )
        )
    if duplicate:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                f"current invocation contains duplicate cells: {duplicate}",
            )
        )
    if missing or extra or len(observed) != len(expected):
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "current invocation must contain exactly the environment's "
                f"{expected_count} compiled cells: observed={len(observed)}, "
                f"missing={missing}, extra={extra}",
            )
        )
    candidate_identities = {
        (
            _commit_digest(item.get("commit")),
            _digest(item.get("imageDigest")),
            _digest(item.get("contractGraphDigest")),
            item.get("candidateReceiptRef"),
            _digest(item.get("candidateReceiptDigest")),
        )
        for item in evidence_cells
    }
    if not evidence_cells or len(candidate_identities) != 1 or any(
        value is None or not value
        for value in next(iter(candidate_identities), ())
    ):
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "all cells must bind one active immutable candidate identity",
            )
        )
    by_key = {
        (
            str(item.get("capabilityId") or ""),
            str(item.get("testLayer") or ""),
        ): item
        for item in evidence_cells
        if item.get("environment") == environment
    }
    for capability_id in sorted(capability_ids):
        binding = _selected_binding(
            compiled,
            capability_id=capability_id,
            environment=environment,
        )
        selected_adapter = (
            binding.get("adapter_id") if isinstance(binding, Mapping) else None
        )
        cells = [by_key.get((capability_id, layer)) for layer in LAYERS]
        if (
            not isinstance(binding, Mapping)
            or binding.get("state") != "enabled"
            or not governance.requires_provider_conformance(binding)
            or not isinstance(selected_adapter, str)
            or any(
                cell is not None and cell.get("adapterId") != selected_adapter
                for cell in cells
            )
            or not _pc._binding_preflight_ready(
                compiled,
                capability_id=capability_id,
                environment=environment,
            )
            or not _cells_share_local_candidate(cells, environment=environment)
        ):
            issues.append(
                _issue(
                    f"local_functional_readiness.{environment}.{capability_id}",
                    "selected Adapter lacks a candidate-bound three-layer local closure",
                )
            )
    return issues


def load_validate_local_functional_readiness(
    paths: Iterable[Path],
    *,
    environment: str,
    compiled: Mapping[str, Any],
    registry: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]],
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate only the evidence emitted by one stackctl environment attempt."""
    evidence, load_issues = load_evidence_paths(paths, root=root)
    current_commit = _pc._current_commit()
    issues = [*load_issues]
    if evidence and current_commit is None:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "cannot determine the current git revision",
            )
        )
    issues.extend(
        local_source_coverage_issues(
            compiled=compiled,
            environment=environment,
            sources=sources,
        )
    )
    issues.extend(
        validate_evidence(
            evidence,
            registry=registry,
            root=root,
            current_commit=current_commit,
            compiled=compiled,
            source_catalog=sources,
        )
    )
    issues.extend(
        local_functional_readiness_issues(
            compiled=compiled,
            evidence=evidence,
            environment=environment,
        )
    )
    return evidence, list(dict.fromkeys(issues))


def derive_readiness(
    *,
    compiled: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    by_cell: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    conformance_capability_ids = provider_conformance_capability_ids(compiled)
    for item in evidence:
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        environment = item.get("environment")
        layer = item.get("testLayer")
        if all(isinstance(value, str) for value in (adapter_id, capability_id, environment, layer)):
            if (
                _selected_adapter_id(
                    compiled,
                    capability_id=capability_id,
                    environment=environment,
                )
                == adapter_id
                and execution_profile_for(environment, layer) is not None
            ):
                by_cell[(capability_id, environment, layer)] = item

    selected_adapter_environments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for environment in ENVIRONMENTS:
        selected_bindings = compiled.get("selectedBindings", {})
        environment_bindings = (
            selected_bindings.get(environment)
            if isinstance(selected_bindings, Mapping)
            else None
        )
        if not isinstance(environment_bindings, Mapping):
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if capability_id not in conformance_capability_ids:
                continue
            adapter_id = binding.get("adapter_id")
            if isinstance(adapter_id, str):
                selected_adapter_environments[(capability_id, adapter_id)].add(environment)

    adapter_ready: dict[tuple[str, str], bool] = {}
    for (capability_id, adapter_id), selected_environments in selected_adapter_environments.items():
        expected_cells = [
            by_cell.get((capability_id, environment, layer))
            for environment in sorted(selected_environments)
            for layer in LAYERS
        ]
        adapter_evidence_ready = _cells_share_release(
            expected_cells,
            expected_environments=selected_environments,
            require_adapter_digest=True,
        )
        preflight_ready = all(
            _pc._binding_preflight_ready(
                compiled,
                capability_id=capability_id,
                environment=environment,
            )
            for environment in selected_environments
        )
        adapter_ready[(capability_id, adapter_id)] = (
            adapter_evidence_ready and preflight_ready
        )

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for environment, capabilities in compiled.get("readiness", {}).items():
        environment_result: dict[str, dict[str, Any]] = {}
        for capability_id, baseline in capabilities.items():
            item = dict(baseline)
            adapter_id = item.get("adapter_id")
            provider_conformance_required = (
                capability_id in conformance_capability_ids
            )
            item["provider_conformance_required"] = provider_conformance_required
            if not provider_conformance_required:
                preflight_ready = bool(item.get("adapter_preflight_ready"))
                item["evidence_ready"] = False
                item["adapter_ready"] = preflight_ready
                item["matrix_selected_adapters_ready"] = True
                if environment == RELEASE_ENVIRONMENT:
                    item["prod_remote_release_ready"] = False
                item["capability_ready"] = (
                    item.get("state") == "enabled" and preflight_ready
                )
                environment_result[capability_id] = item
                continue
            expected_cells = [
                by_cell.get((capability_id, evidence_environment, layer))
                for evidence_environment in ENVIRONMENTS
                for layer in LAYERS
            ]
            capability_matrix_ready = _cells_share_release(
                expected_cells,
                expected_environments=ENVIRONMENTS,
                require_adapter_digest=False,
            )
            prod_remote_release_cell = by_cell.get(
                (capability_id, RELEASE_ENVIRONMENT, "user_acceptance")
            )
            prod_remote_release_ready = (
                prod_remote_release_cell is not None
                and prod_remote_release_cell.get("status") == "passed"
                and _release_readiness_valid(prod_remote_release_cell)
            )
            matrix_selected_adapters_ready = all(
                adapter_ready.get(
                    (
                        capability_id,
                        _selected_adapter_id(
                            compiled,
                            capability_id=capability_id,
                            environment=evidence_environment,
                        ),
                    ),
                    False,
                )
                for evidence_environment in ENVIRONMENTS
            )
            selected_adapter_ready = (
                adapter_ready.get((capability_id, adapter_id), False)
                if isinstance(adapter_id, str)
                else False
            )
            item["evidence_ready"] = capability_matrix_ready
            item["adapter_ready"] = selected_adapter_ready
            item["matrix_selected_adapters_ready"] = matrix_selected_adapters_ready
            if environment == RELEASE_ENVIRONMENT:
                item["prod_remote_release_ready"] = prod_remote_release_ready
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
                    and prod_remote_release_ready
                )
            else:
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and selected_adapter_ready
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
                )
            environment_result[capability_id] = item
        result[environment] = environment_result
    return result


def load_validate_and_derive(
    *, root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    compiled, governance_issues = governance.load_and_compile()
    evidence, evidence_load_issues = load_evidence(root)
    current_commit = _pc._current_commit()
    current_commit_issues = (
        ["cannot determine the current git revision for evidence validation"]
        if evidence and current_commit is None
        else []
    )
    executable_sources, source_discovery_issues = discover_test_sources()
    evidence_issues = validate_evidence(
        evidence,
        registry=governance.load_registry(),
        root=root,
        current_commit=current_commit,
        compiled=compiled,
        source_catalog=executable_sources,
    )
    readiness = derive_readiness(compiled=compiled, evidence=evidence)
    coverage_issues = source_coverage_issues(
        compiled=compiled,
        sources=executable_sources,
    )
    report = {
        "schema": "provider-conformance-readiness",
        "evidenceCount": len(evidence),
        "executableSourceCount": len(executable_sources),
        "sourceCoverageIssues": coverage_issues,
        "readiness": readiness,
        "issues": [
            *(issue.render() for issue in governance_issues),
            *evidence_load_issues,
            *current_commit_issues,
            *source_discovery_issues,
            *coverage_issues,
            *evidence_issues,
        ],
    }
    return report, report["issues"]


def readiness_issues(
    report: Mapping[str, Any],
    *,
    environment: str,
) -> list[str]:
    if environment not in READINESS_ENVIRONMENTS:
        return [_issue("readiness", f"unsupported readiness environment {environment}")]
    issues: list[str] = []
    if not _pc.ci_attestation_authority_available():
        issues.append(
            _issue(
                f"readiness.{environment}",
                "promotable evidence requires a clean reviewed commit and "
                "CI attestation authority",
            )
        )
    source_coverage = report.get("sourceCoverageIssues")
    if isinstance(source_coverage, list):
        issues.extend(str(issue) for issue in source_coverage)
    evidence_count = report.get("evidenceCount")
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        return [
            *issues,
            _issue(
                f"readiness.{environment}",
                "zero Provider Conformance evidence artifacts cannot satisfy release readiness",
            )
        ]
    readiness_by_environment = report.get("readiness")
    readiness = (
        readiness_by_environment.get(environment)
        if isinstance(readiness_by_environment, Mapping)
        else None
    )
    if not isinstance(readiness, Mapping):
        return [_issue(f"readiness.{environment}", "is unavailable")]
    for capability_id, capability_readiness in readiness.items():
        if not isinstance(capability_readiness, Mapping):
            continue
        if capability_readiness.get("required") and not capability_readiness.get(
            "capability_ready"
        ):
            issues.append(
                _issue(
                    f"readiness.{environment}.{capability_id}",
                    "required capability lacks current selected-Binding release evidence",
                )
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Provider Conformance evidence and calculate readiness."
    )
    parser.add_argument("--require-ready", choices=READINESS_ENVIRONMENTS)
    args = parser.parse_args()
    report, issues = load_validate_and_derive()
    if args.require_ready:
        issues.extend(readiness_issues(report, environment=args.require_ready))
        report["issues"] = issues
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0
