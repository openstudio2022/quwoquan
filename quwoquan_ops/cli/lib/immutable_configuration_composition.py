"""Canonical runtime-configuration identity derived from service packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir


SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def immutable_configuration_digest(configurations: Mapping[str, str]) -> str:
    """Derive one digest from the exact service-to-config digest bindings."""

    if not configurations:
        raise ValueError("configuration composition must not be empty")
    canonical: dict[str, str] = {}
    for service, digest in sorted(configurations.items()):
        service_name = str(service).strip()
        config_digest = str(digest).strip()
        if not service_name or SHA256_PATTERN.fullmatch(config_digest) is None:
            raise ValueError(
                f"invalid configuration composition binding: {service_name or '<empty>'}"
            )
        canonical[service_name] = config_digest
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def packaged_service_configuration_digests(
    environment: str,
    *,
    target: str = "",
    services: Sequence[str] | None = None,
) -> dict[str, str]:
    """Validate packages and return their canonical rendered config identities."""

    bindings: dict[str, str] = {}
    for service in tuple(services or first_party_service_names()):
        package = service_deployment_package_dir(
            environment,
            service,
            target=target,
        )
        config_path = package / "config/config.yaml"
        provenance_path = package / "provenance.json"
        if not config_path.is_file() or not provenance_path.is_file():
            raise FileNotFoundError(
                f"service configuration package missing: {package}"
            )
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"service package provenance is unreadable: {provenance_path}: {exc}"
            ) from exc
        if not isinstance(provenance, dict):
            raise ValueError(
                f"service package provenance must be an object: {provenance_path}"
            )
        if (
            provenance.get("service") != service
            or provenance.get("environment") != environment
        ):
            raise ValueError(
                f"service package provenance identity mismatch: {provenance_path}"
            )
        config_version = str(provenance.get("configVersion") or "").strip()
        if SHA256_PATTERN.fullmatch(config_version) is None:
            raise ValueError(
                f"service package configVersion is not a sha256 digest: {provenance_path}"
            )
        packaged_digest = str(
            ((provenance.get("digests") or {}).get("config") or "")
        ).strip()
        actual_digest = _sha256_file(config_path)
        if packaged_digest != actual_digest:
            raise ValueError(f"service package config digest mismatch: {config_path}")
        bindings[service] = config_version
    return bindings


def packaged_configuration_digest(
    environment: str,
    *,
    target: str = "",
    services: Sequence[str] | None = None,
) -> str:
    """Return the one runtime identity for all first-party service configs."""

    return immutable_configuration_digest(
        packaged_service_configuration_digests(
            environment,
            target=target,
            services=services,
        )
    )
