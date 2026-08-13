"""自描述 Provider Conformance 测试源的加载、发现与覆盖率检查。

可被测试 patch 的符号（ROOT、TEST_LAYER_ROOTS）一律经薄入口 `_pc`
在调用时读取。
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance as _pc

from .attestation import _digest_bytes
from .constants import (
    ADAPTER_PATTERN,
    ASSERTION_ID_PATTERN,
    CAPABILITY_PATTERN,
    ENVIRONMENTS,
    LAYERS,
    PUBLIC_ASSERTION_IDS,
    RELEASE_ENVIRONMENT,
    SOURCE_DYNAMIC_EXECUTOR_RE,
    SOURCE_METADATA_RE,
    SOURCE_STATIC_BLOCK_RE,
)
from .evidence_store import _issue
from .governance_bindings import (
    _is_non_empty_string,
    capability_assertion_id,
    network_boundary_for_layer,
)

def _source_spec_refs(raw_source: str, *, location: str) -> list[str]:
    refs = [
        match.group(1)
        for line in raw_source.splitlines()
        if (
            match := re.match(r"^\s*(?://|#)\s*spec_ref:\s*(\S+)\s*$", line)
        )
        is not None
    ]
    if not refs:
        raise ValueError(f"{location} must declare at least one spec_ref")
    return list(dict.fromkeys(refs))


def _source_metadata(raw_source: str, *, location: str) -> Mapping[str, Any]:
    declarations = [
        match.group(1)
        for line in raw_source.splitlines()
        if (match := SOURCE_METADATA_RE.match(line)) is not None
    ]
    if len(declarations) != 1:
        raise ValueError(
            f"{location} must declare exactly one provider_conformance JSON header"
        )
    try:
        metadata = json.loads(declarations[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{location} has invalid provider_conformance JSON: {exc}") from exc
    if not isinstance(metadata, Mapping):
        raise ValueError(f"{location} provider_conformance header must be an object")
    return metadata


def load_test_source(
    path: Path,
    *,
    capabilities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load a self-describing executable Provider Conformance source.

    The test source, instead of a registry/manifest, declares its identity,
    exact command and target. Its command must write a CaseResult document to
    ``QWQ_PROVIDER_CONFORMANCE_RESULT_PATH``.
    """
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(_pc.ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Provider Conformance test source must be inside the repository") from exc
    if not resolved.is_file() or resolved.suffix not in {".py", ".go"}:
        raise ValueError(f"{relative} is not a supported Provider Conformance test source")
    raw = resolved.read_text(encoding="utf-8")
    metadata = _source_metadata(raw, location=relative)
    required = {
        "adapterId",
        "capabilityId",
        "testLayer",
        "typedPort",
        "contractRef",
        "assertionIds",
        "command",
        "target",
        "networkBoundary",
    }
    if set(metadata) != required:
        raise ValueError(
            f"{relative} provider_conformance header fields must be exactly {sorted(required)}"
        )
    layer = metadata.get("testLayer")
    if layer not in LAYERS:
        raise ValueError(f"{relative} declares an unsupported testLayer")
    layer_root = _pc.TEST_LAYER_ROOTS[str(layer)].resolve()
    if layer_root not in resolved.parents:
        raise ValueError(f"{relative} must live under the declared {layer} test root")
    adapter_id = metadata.get("adapterId")
    capability_id = metadata.get("capabilityId")
    typed_port = metadata.get("typedPort")
    contract_ref = metadata.get("contractRef")
    target = metadata.get("target")
    command = metadata.get("command")
    assertion_ids = metadata.get("assertionIds")
    if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
        raise ValueError(f"{relative} declares an invalid adapterId")
    if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
        raise ValueError(f"{relative} declares an invalid capabilityId")
    if not all(_is_non_empty_string(value) for value in (typed_port, contract_ref, target)):
        raise ValueError(f"{relative} must declare typedPort, contractRef and target")
    if (
        not isinstance(command, list)
        or not command
        or not all(_is_non_empty_string(item) and "\n" not in item for item in command)
    ):
        raise ValueError(f"{relative} must declare a concrete argv command")
    if any(
        re.search(r"(?:--dry-run|\bdry[\s_-]*run\b)", item, re.IGNORECASE)
        for item in command
    ):
        raise ValueError(f"{relative} command must not declare a dry-run")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or not all(
            isinstance(assertion_id, str)
            and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        raise ValueError(f"{relative} must declare unique stable assertionIds")
    missing_public = PUBLIC_ASSERTION_IDS - set(assertion_ids)
    if missing_public:
        raise ValueError(
            f"{relative} omits mandatory public assertions {sorted(missing_public)}"
        )
    if capabilities is None:
        capabilities = {
            str(capability["capability_id"]): capability
            for capability in governance.load_registry().get("capabilities", [])
            if isinstance(capability, Mapping) and capability.get("capability_id")
        }
    capability = capabilities.get(str(capability_id))
    if capability is None:
        raise ValueError(f"{relative} declares an unknown capabilityId")
    expected_capability_assertion = capability_assertion_id(capability)
    if expected_capability_assertion not in assertion_ids:
        raise ValueError(
            f"{relative} omits capability assertion {expected_capability_assertion}"
        )
    if typed_port != capability.get("canonical_port"):
        raise ValueError(f"{relative} typedPort does not match the canonical capability Port")
    if contract_ref != capability.get("source"):
        raise ValueError(f"{relative} contractRef does not match the capability source")
    if metadata.get("networkBoundary") != network_boundary_for_layer(str(layer)):
        raise ValueError(f"{relative} networkBoundary conflicts with its testLayer")
    if "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH" not in raw:
        raise ValueError(
            f"{relative} must write command results to QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
        )
    if layer in {"api_integration", "user_acceptance"} and SOURCE_STATIC_BLOCK_RE.search(raw):
        raise ValueError(
            f"{relative} is a static should-block/GATE_BLOCK test and cannot prove remote evidence"
        )
    if SOURCE_DYNAMIC_EXECUTOR_RE.search(raw):
        raise ValueError(
            f"{relative} delegates to a runtime-selected executor and cannot prove "
            "the declared Adapter/target"
        )
    return {
        **dict(metadata),
        "testSource": relative,
        "testSourceDigest": _digest_bytes(raw.encode("utf-8")),
        "acceptanceRefs": _source_spec_refs(raw, location=relative),
    }


def discover_test_sources() -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[str]]:
    """Discover source-declared harnesses without a path or assertion registry."""
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: list[str] = []
    capabilities = {
        str(capability["capability_id"]): capability
        for capability in governance.load_registry().get("capabilities", [])
        if isinstance(capability, Mapping) and capability.get("capability_id")
    }
    for root in _pc.TEST_LAYER_ROOTS.values():
        if not root.is_dir():
            continue
        paths = [
            *root.rglob("*provider_conformance*.py"),
            *root.rglob("*provider_conformance*.go"),
        ]
        for path in sorted(paths):
            raw = path.read_text(encoding="utf-8")
            if not any(
                SOURCE_METADATA_RE.match(line) for line in raw.splitlines()
            ):
                continue
            try:
                source = load_test_source(path, capabilities=capabilities)
            except (OSError, ValueError) as exc:
                issues.append(str(exc))
                continue
            key = (
                str(source["capabilityId"]),
                str(source["adapterId"]),
                str(source["testLayer"]),
            )
            if key in sources:
                issues.append(
                    f"{source['testSource']} duplicates Provider Conformance source "
                    f"for capability/adapter/layer {key}"
                )
                continue
            sources[key] = source
    return sources, issues


def source_for_cell(
    *,
    capability_id: str,
    adapter_id: str,
    layer: str,
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> Mapping[str, Any] | None:
    catalog, _ = discover_test_sources() if sources is None else (sources, [])
    return catalog.get((capability_id, adapter_id, layer))


def source_coverage_issues(
    *,
    compiled: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return release-blocking gaps in the selected-Binding source catalog.

    One self-describing source may serve the same Adapter in more than one
    environment, so coverage is evaluated by the unique
    Capability/Adapter/layer key consumed by ``source_for_cell`` rather than
    by blindly counting all nine environment cells.
    """

    catalog, discovery_issues = (
        discover_test_sources() if sources is None else (dict(sources), [])
    )
    issues = list(discovery_issues)
    required: dict[str, set[tuple[str, str]]] = defaultdict(set)
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return [*issues, _issue("source_coverage", "compiled selected Bindings are unavailable")]
    for environment in ENVIRONMENTS:
        environment_bindings = selected_bindings.get(environment)
        if not isinstance(environment_bindings, Mapping):
            issues.append(
                _issue(
                    f"source_coverage.{environment}",
                    "compiled selected Bindings are unavailable",
                )
            )
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if not governance.requires_provider_conformance(binding):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{environment}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].update((adapter_id, layer) for layer in LAYERS)
    release_bindings = selected_bindings.get(RELEASE_ENVIRONMENT)
    if not isinstance(release_bindings, Mapping):
        issues.append(
            _issue(
                f"source_coverage.{RELEASE_ENVIRONMENT}",
                "compiled selected Bindings are unavailable",
            )
        )
    else:
        for capability_id, binding in release_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if not governance.requires_provider_conformance(binding):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{RELEASE_ENVIRONMENT}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].add((adapter_id, "user_acceptance"))
    for capability_id, cells in sorted(required.items()):
        missing = [
            f"{adapter_id}/{layer}"
            for adapter_id, layer in sorted(cells)
            if (capability_id, adapter_id, layer) not in catalog
        ]
        if missing:
            issues.append(
                _issue(
                    f"source_coverage.{capability_id}",
                    "missing self-describing executable sources for " + ", ".join(missing),
                )
            )
    return issues


def local_source_coverage_issues(
    *,
    compiled: Mapping[str, Any],
    environment: str,
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Check only this nonprod target's selected Adapter across all three layers."""
    if environment not in ENVIRONMENTS:
        return [
            _issue(
                "source_coverage",
                f"unsupported nonprod environment {environment}",
            )
        ]
    catalog, discovery_issues = (
        discover_test_sources() if sources is None else (dict(sources), [])
    )
    issues = list(discovery_issues)
    selected_bindings = compiled.get("selectedBindings")
    environment_bindings = (
        selected_bindings.get(environment)
        if isinstance(selected_bindings, Mapping)
        else None
    )
    if not isinstance(environment_bindings, Mapping):
        return [
            *issues,
            _issue(
                f"source_coverage.{environment}",
                "compiled selected Bindings are unavailable",
            ),
        ]
    for capability_id, binding in sorted(environment_bindings.items()):
        if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
            continue
        if not governance.requires_provider_conformance(binding):
            continue
        adapter_id = binding.get("adapter_id")
        if not isinstance(adapter_id, str):
            issues.append(
                _issue(
                    f"source_coverage.{environment}.{capability_id}",
                    "selected Binding has no Adapter ID",
                )
            )
            continue
        missing = [
            f"{adapter_id}/{layer}"
            for layer in LAYERS
            if (capability_id, adapter_id, layer) not in catalog
        ]
        if missing:
            issues.append(
                _issue(
                    f"source_coverage.{environment}.{capability_id}",
                    "missing self-describing executable sources for "
                    + ", ".join(missing),
                )
            )
    return issues
