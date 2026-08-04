"""Compile Provider bindings with topology and capability-scoped secret bundles."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from .external_provider_governance import load_and_compile
from .output_paths import deployment_work_root
from .provider_endpoint_contract import load_provider_endpoint_environment


SCHEMA = "stackctl-provider-config"
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOCAL_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}


def project_provider_secret_bundles(
    *,
    environment: str,
    target: str,
    source: Mapping[str, str],
) -> dict[str, str]:
    """Project generated local secrets into capability-owned external bundles."""

    _validate_scope(environment, target)
    projected: dict[str, str] = {}
    for capability_id, binding in _owner_bindings(environment).items():
        for field in ("endpoint_envs", "secret_refs"):
            for key in _binding_keys(binding, field):
                value = str(source.get(key) or "")
                if not value:
                    continue
                path = _bundle_key_path(target, capability_id, key)
                _atomic_write(path, value.encode("utf-8"), mode=0o600)
                projected[f"{capability_id}:{key}"] = _value_digest(value)
    return projected


def compile_provider_config(
    *,
    action: str,
    environment: str,
    target: str,
) -> dict[str, Any]:
    if action not in {"validate", "render", "diff"}:
        raise ValueError(f"unsupported provider-config action: {action}")
    _validate_scope(environment, target)
    endpoint_environment = (
        load_provider_endpoint_environment()
        if environment in {"alpha", "beta", "gamma"}
        else {}
    )
    resolved: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    capability_digests: dict[str, str] = {}
    for capability_id, binding in _owner_bindings(environment).items():
        if str(binding.get("state") or "") != "enabled":
            continue
        adapter = str(binding.get("adapter_id") or "")
        if adapter == "ext.first_party.http_authority":
            continue
        material: dict[str, str] = {}
        for key in _binding_keys(binding, "endpoint_envs"):
            value = endpoint_environment.get(key)
            if value is None:
                value, issue = _read_bundle_key(target, capability_id, key)
                if issue:
                    (missing if issue == "missing" else invalid).append(
                        f"{capability_id}:{key}"
                    )
                    continue
            material[key] = value
            resolved[key] = value
        for key in _binding_keys(binding, "secret_refs"):
            value, issue = _read_bundle_key(target, capability_id, key)
            if issue:
                (missing if issue == "missing" else invalid).append(
                    f"{capability_id}:{key}"
                )
                continue
            material[key] = value
            resolved[key] = value
        capability_digests[capability_id] = _mapping_digest(material)

    aggregate_digest = _mapping_digest(capability_digests)
    current = {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        "configurationDigest": aggregate_digest,
        "capabilityDigests": capability_digests,
        "missingKeys": sorted(missing),
        "invalidKeys": sorted(invalid),
    }
    if action == "diff":
        previous = _load_active_receipt(target)
        previous_digest = str(previous.get("configurationDigest") or "")
        return {
            "exitCode": 0 if previous_digest == aggregate_digest and not missing and not invalid else 2,
            "summary": (
                "stackctl provider-config diff is clean"
                if previous_digest == aggregate_digest and not missing and not invalid
                else "stackctl provider-config diff detected material drift"
            ),
            "details": [
                f"configurationDigest={aggregate_digest}",
                f"previousDigest={previous_digest or 'missing'}",
                *[f"missing={key}" for key in sorted(missing)],
                *[f"invalid={key}" for key in sorted(invalid)],
            ],
            **current,
            "changed": previous_digest != aggregate_digest,
        }
    if missing or invalid:
        return {
            "exitCode": 2,
            "summary": f"stackctl provider-config {action} is GATE_BLOCK",
            "details": [
                f"configurationDigest={aggregate_digest}",
                *[f"missing={key}" for key in sorted(missing)],
                *[f"invalid={key}" for key in sorted(invalid)],
            ],
            **current,
        }
    if action == "render":
        _render_material(target, resolved, current)
    return {
        "exitCode": 0,
        "summary": f"stackctl provider-config {action} passed",
        "details": [f"configurationDigest={aggregate_digest}"],
        **current,
    }


def _owner_bindings(environment: str) -> dict[str, Mapping[str, Any]]:
    compiled, issues = load_and_compile()
    if issues:
        raise RuntimeError("; ".join(issue.render() for issue in issues))
    scope = (compiled.get("selectedBindings") or {}).get(environment)
    if not isinstance(scope, Mapping):
        raise RuntimeError(
            f"compiled Provider bindings have no environment {environment}"
        )
    return {
        str(capability_id): binding
        for capability_id, binding in scope.items()
        if isinstance(binding, Mapping)
    }


def _binding_keys(binding: Mapping[str, Any], field: str) -> list[str]:
    value = binding.get(field) or {}
    keys = value.values() if isinstance(value, Mapping) else value
    return sorted(str(key) for key in keys if KEY_RE.fullmatch(str(key)))


def _validate_scope(environment: str, target: str) -> None:
    expected = LOCAL_TARGET_BY_ENV.get(environment)
    if expected is None:
        raise ValueError(f"unsupported Provider environment: {environment}")
    if target != expected:
        raise ValueError(
            f"Provider target/environment mismatch: environment={environment} target={target}"
        )


def _bundle_key_path(target: str, capability_id: str, key: str) -> Path:
    if not CAPABILITY_RE.fullmatch(capability_id):
        raise ValueError(f"invalid capability identifier: {capability_id}")
    if not KEY_RE.fullmatch(key):
        raise ValueError(f"invalid Provider material key: {key}")
    return deployment_work_root(target) / "secrets" / capability_id / key


def _read_bundle_key(
    target: str,
    capability_id: str,
    key: str,
) -> tuple[str, str]:
    path = _bundle_key_path(target, capability_id, key)
    if not path.is_file() or path.is_symlink():
        return "", "missing"
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        return "", "invalid"
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "", "invalid"
    if not value:
        return "", "invalid"
    return value, ""


def _render_material(
    target: str,
    values: Mapping[str, str],
    receipt: Mapping[str, Any],
) -> None:
    root = deployment_work_root(target) / "provider-config"
    _atomic_write(
        root / "material.json",
        json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        mode=0o600,
    )
    _atomic_write(
        root / "active.json",
        json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        mode=0o600,
    )


def _load_active_receipt(target: str) -> dict[str, Any]:
    path = deployment_work_root(target) / "provider-config" / "active.json"
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _mapping_digest(values: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(values.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _value_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
