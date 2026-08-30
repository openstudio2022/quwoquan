"""Hosted human authority HTTP, signature, runtime, and wire adapters."""
from .client import (
    EXTERNAL_BLOCKER_CODE,
    PROTOCOL_BLOCKER_CODE,
    UNKNOWN_OUTCOME_CODE,
    PROVIDER_KIND,
    AuthorityAbsent,
    CommandOutcomeUnknown,
    ExternalDependencyBlocker,
    HostedAuthorityConfig,
    HostedAuthorityError,
    HostedAuthorityHttpClient,
    HostedAuthorityResponse,
    ProtocolUnavailableBlocker,
    SignatureEnvelope,
)
from .runtime import EnvironmentTokenProvider, HostedAuthorityRuntime, runtime_from_env
from .signing import decode_public_keyring, signature_message, verify_ed25519
from .wire import (
    CANONICAL_OPERATIONS_RELATIVE_PATH,
    HostedAuthorityWire,
    HostedAuthorityWireError,
    load_hosted_authority_wire,
)

__all__ = [
    "CANONICAL_OPERATIONS_RELATIVE_PATH", "EXTERNAL_BLOCKER_CODE",
    "PROTOCOL_BLOCKER_CODE", "UNKNOWN_OUTCOME_CODE", "PROVIDER_KIND",
    "AuthorityAbsent", "CommandOutcomeUnknown", "EnvironmentTokenProvider",
    "ExternalDependencyBlocker", "HostedAuthorityConfig", "HostedAuthorityError",
    "HostedAuthorityHttpClient", "HostedAuthorityResponse", "HostedAuthorityRuntime",
    "HostedAuthorityWire", "HostedAuthorityWireError", "ProtocolUnavailableBlocker",
    "SignatureEnvelope", "decode_public_keyring", "load_hosted_authority_wire",
    "runtime_from_env", "signature_message", "verify_ed25519",
]
