"""External runtime configuration for the hosted authority adapter."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .client import ExternalDependencyBlocker, HostedAuthorityConfig, TokenProvider
from .signing import decode_public_keyring
from .wire import HostedAuthorityWireError, load_hosted_authority_wire

BASE_URL_ENV = "QWQ_HOSTED_AUTHORITY_BASE_URL"
OIDC_ISSUER_ENV = "QWQ_HOSTED_AUTHORITY_OIDC_ISSUER"
TOKEN_ENV = "QWQ_HOSTED_AUTHORITY_BEARER_TOKEN"
TRUSTED_KEYS_FILE_ENV = "QWQ_HOSTED_AUTHORITY_TRUSTED_PUBLIC_KEYS_FILE"
RELEASE_POLICY_ENV = "QWQ_HOSTED_AUTHORITY_RELEASE_EVIDENCE_POLICY"


@dataclass(frozen=True, slots=True)
class HostedAuthorityRuntime:
    config: HostedAuthorityConfig
    token_provider: TokenProvider
    trusted_public_keys: dict[str, bytes]


class EnvironmentTokenProvider:
    """Injected token source; the client never reads ambient credentials itself."""

    def __init__(self, getenv: Callable[[str], str | None] = os.getenv) -> None:
        self._getenv = getenv

    def __call__(self) -> str:
        return str(self._getenv(TOKEN_ENV) or "")


def _external_keyring(path_value: str, repo_root: Path) -> dict[str, bytes]:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        raise ExternalDependencyBlocker("hosted authority signing keyring must be an absolute external path")
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ExternalDependencyBlocker("hosted authority signing keyring is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ExternalDependencyBlocker("hosted authority signing keyring must be a regular non-symlink file")
    for forbidden in (repo_root.resolve(), (repo_root / ".qwq_output").resolve()):
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            continue
        raise ExternalDependencyBlocker("hosted authority signing keyring must stay outside repository outputs")
    if info.st_mode & 0o022:
        raise ExternalDependencyBlocker("hosted authority signing keyring permissions are unsafe")
    return decode_public_keyring(path.read_bytes())


def runtime_from_env(
    repo_root: Path,
    *,
    token_provider: TokenProvider,
    getenv: Callable[[str], str | None] = os.getenv,
) -> HostedAuthorityRuntime:
    """Resolve all real external dependencies into one fail-closed blocker domain."""
    base_url = str(getenv(BASE_URL_ENV) or "").strip()
    issuer = str(getenv(OIDC_ISSUER_ENV) or "").strip()
    keyring_path = str(getenv(TRUSTED_KEYS_FILE_ENV) or "").strip()
    missing = [
        name
        for name, value in (
            (BASE_URL_ENV, base_url),
            (OIDC_ISSUER_ENV, issuer),
            (TRUSTED_KEYS_FILE_ENV, keyring_path),
        )
        if not value
    ]
    try:
        token = token_provider().strip()
    except Exception as error:
        raise ExternalDependencyBlocker("hosted authority OIDC token provider failed") from error
    if not token:
        missing.append(TOKEN_ENV)
    if missing:
        raise ExternalDependencyBlocker("missing hosted authority configuration: " + ",".join(sorted(missing)))
    policy = str(getenv(RELEASE_POLICY_ENV) or "").strip()
    if policy not in {"", "allow"}:
        raise ExternalDependencyBlocker("hosted authority release evidence policy must be 'allow' or unset")
    try:
        wire = load_hosted_authority_wire(repo_root)
    except HostedAuthorityWireError as error:
        raise ExternalDependencyBlocker(str(error)) from error
    config = HostedAuthorityConfig(
        base_url=base_url,
        expected_issuer=issuer,
        wire=wire,
        explicit_release_policy=policy == "allow",
    )
    config.normalized_base_url()
    keys = _external_keyring(keyring_path, repo_root)
    return HostedAuthorityRuntime(config=config, token_provider=token_provider, trusted_public_keys=keys)
