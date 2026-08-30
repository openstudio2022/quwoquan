"""编译 candidate/package 使用的单环境 Provider Binding 派生物。"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .compilation import compile_governance
from .constants import ENVIRONMENTS
from .derived_sources import (
    load_conformance_manifest,
    load_environment_bindings,
    load_registry,
)
from .go_descriptors import _descriptor_roots, render_single_environment_go_bindings


SINGLE_ENVIRONMENT_SCHEMA = "compiled-external-provider-bindings.single-environment"
SINGLE_ENVIRONMENT_MANIFEST_SCHEMA = (
    "compiled-external-provider-binding-manifest.single-environment"
)


def compile_single_environment_bindings(
    *,
    environment: str,
    target: str,
    source_root: Path,
) -> dict[str, Any]:
    """从一个只读 source capsule 返回当前环境的 descriptor/source/manifest。"""
    _validate_scope(environment, target)
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError(f"external Provider source_root is not a directory: {source_root}")
    registry = load_registry(source_root=root)
    environment_scope = load_environment_bindings(
        environment,
        source_root=root,
    )
    compiled, issues = compile_governance(
        registry,
        {
            "schema": "service-local-external-provider-bindings",
            "environments": {environment: environment_scope},
        },
        load_conformance_manifest(source_root=root),
        source_root=root,
        environments=(environment,),
    )
    if issues:
        raise RuntimeError("; ".join(issue.render() for issue in issues))
    selected = compiled.get("selectedBindings")
    selected_roots = compiled.get("selectedRootBindings")
    readiness = compiled.get("readiness")
    environment_bindings = (
        selected.get(environment) if isinstance(selected, Mapping) else None
    )
    environment_roots = (
        selected_roots.get(environment)
        if isinstance(selected_roots, Mapping)
        else None
    )
    environment_readiness = (
        readiness.get(environment) if isinstance(readiness, Mapping) else None
    )
    if not isinstance(environment_bindings, Mapping) or not environment_bindings:
        raise ValueError(f"compiled Provider Bindings have no environment {environment}")
    if not isinstance(environment_roots, Mapping) or not isinstance(
        environment_readiness, Mapping
    ):
        raise ValueError("compiled Provider Bindings are incomplete")

    descriptors: list[dict[str, Any]] = []
    go_sources: list[dict[str, str]] = []
    for descriptor_root in _descriptor_roots(registry):
        root_id = descriptor_root["root_id"]
        owner = descriptor_root["descriptor_owner"]
        scope = environment_roots.get(root_id)
        descriptor = {
            "rootId": root_id,
            "owner": owner,
            "bindings": _canonical_mapping(scope),
        }
        source = render_single_environment_go_bindings(
            environment_roots,
            environment=environment,
            descriptor_owner=owner,
            descriptor_root_id=root_id,
        )
        descriptors.append(descriptor)
        go_sources.append(
            {
                "rootId": root_id,
                "owner": owner,
                "outputPath": descriptor_root["descriptor_output"],
                "sourceDigest": _sha256_bytes(source.encode("utf-8")),
                "source": source,
            }
        )

    descriptor_digest = _digest(descriptors)
    go_source_digest = _digest(
        [
            {
                "rootId": item["rootId"],
                "owner": item["owner"],
                "outputPath": item["outputPath"],
                "sourceDigest": item["sourceDigest"],
            }
            for item in go_sources
        ]
    )
    binding_digest = _digest(_canonical_mapping(environment_bindings))
    readiness_digest = _digest(_canonical_mapping(environment_readiness))
    manifest_core = {
        "schema": SINGLE_ENVIRONMENT_MANIFEST_SCHEMA,
        "environment": environment,
        "target": target,
        "bindingDigest": binding_digest,
        "readinessDigest": readiness_digest,
        "descriptorDigest": descriptor_digest,
        "goSourceDigest": go_source_digest,
        "descriptorCount": len(descriptors),
    }
    return {
        "schema": SINGLE_ENVIRONMENT_SCHEMA,
        "environment": environment,
        "target": target,
        "bindings": _canonical_mapping(environment_bindings),
        "readiness": _canonical_mapping(environment_readiness),
        "descriptors": descriptors,
        "goSources": go_sources,
        "manifest": {
            **manifest_core,
            "manifestDigest": _digest(manifest_core),
        },
    }


def _validate_scope(environment: str, target: str) -> None:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported Provider environment: {environment}")
    expected_targets = (
        {f"{environment}-local"}
        if environment != "prod"
        else {"prod-sim", "prod-hosted"}
    )
    if target not in expected_targets:
        raise ValueError(
            "Provider target/environment mismatch: "
            f"environment={environment} target={target}"
        )


def _canonical_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)
