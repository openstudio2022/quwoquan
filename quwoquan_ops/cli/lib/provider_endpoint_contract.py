"""Resolve non-production Provider endpoints from workload-owned contracts."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from .common import ROOT
from .port_manifest import internal_role_base_url, load_port_manifest


CONTRACT_ROOT = ROOT / "quwoquan_ops" / "external"
ENVIRONMENT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_provider_endpoint_environment(
    *,
    contract_root: Path | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, str]:
    root = contract_root or CONTRACT_ROOT
    port_manifest = manifest or load_port_manifest()
    environment: dict[str, str] = {}
    for path in sorted(root.glob("*/contract/endpoints.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path}: endpoint contract must be a mapping")
        if payload.get("schema") != "provider-endpoint-contract":
            raise RuntimeError(f"{path}: unsupported endpoint contract schema")
        role = str(payload.get("role") or "").strip()
        base_url = internal_role_base_url(port_manifest, role)
        endpoints = payload.get("endpoints")
        if not isinstance(endpoints, dict) or not endpoints:
            raise RuntimeError(f"{path}: endpoints must be a non-empty mapping")
        for environment_key, descriptor in endpoints.items():
            key = str(environment_key)
            if not ENVIRONMENT_KEY_RE.fullmatch(key):
                raise RuntimeError(f"{path}: invalid endpoint environment key {key!r}")
            if key in environment:
                raise RuntimeError(f"{path}: duplicate endpoint environment key {key}")
            if not isinstance(descriptor, dict):
                raise RuntimeError(f"{path}: {key} endpoint must be a mapping")
            suffix = str(descriptor.get("path") or "")
            if suffix and (
                not suffix.startswith("/")
                or "//" in suffix
                or ".." in suffix
                or "?" in suffix
                or "#" in suffix
            ):
                raise RuntimeError(f"{path}: {key} has an unsafe endpoint path")
            environment[key] = base_url + suffix
    return environment
