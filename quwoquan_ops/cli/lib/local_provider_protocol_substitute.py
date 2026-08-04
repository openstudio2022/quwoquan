"""Materialize target-isolated TLS for the generic Provider protocol substitute."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .local_provider_substitute_tls import prepare_local_provider_substitute_tls
from .provider_endpoint_contract import load_provider_endpoint_environment


ROLE = "provider-protocol-substitute"


@dataclass(frozen=True)
class LocalProviderProtocolSubstitute:
    environment: dict[str, str]
    certificate_path: Path
    private_key_path: Path
    ca_path: Path


def prepare_local_provider_protocol_substitute(
    environment: str,
    target_name: str,
    *,
    port: int,
) -> LocalProviderProtocolSubstitute:
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("Provider protocol substitute is limited to Alpha/Beta/Gamma")
    if target_name != f"{environment}-local":
        raise ValueError("Provider protocol substitute target/environment mismatch")
    if not 1 <= int(port) <= 65535:
        raise ValueError("Provider protocol substitute port is invalid")
    tls = prepare_local_provider_substitute_tls(target_name, role=ROLE)
    endpoint_environment = load_provider_endpoint_environment()
    return LocalProviderProtocolSubstitute(
        environment={
            **endpoint_environment,
            "PROVIDER_SUBSTITUTE_TLS_CERT_FILE": (
                "/run/secrets/provider-protocol-substitute/server.crt"
            ),
            "PROVIDER_SUBSTITUTE_TLS_KEY_FILE": (
                "/run/secrets/provider-protocol-substitute/server.key"
            ),
            "PROVIDER_SUBSTITUTE_CA_FILE": (
                "/run/secrets/provider-protocol-substitute/ca.crt"
            ),
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_CERT_FILE": str(
                tls.certificate_path.resolve()
            ),
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_KEY_FILE": str(
                tls.private_key_path.resolve()
            ),
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_CA_FILE": str(tls.ca_path.resolve()),
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_PORT": str(port),
        },
        certificate_path=tls.certificate_path,
        private_key_path=tls.private_key_path,
        ca_path=tls.ca_path,
    )
