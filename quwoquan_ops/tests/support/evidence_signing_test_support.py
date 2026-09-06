"""测试用临时证据签名信任根：临时私钥根 + 临时 keyring，不触碰真实 ~/.cache 与仓内 keyring。"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from quwoquan_ops.cli.lib.evidence_signing import (
    ENVIRONMENT_OPS_IDENTITY,
    INTEGRATION_SCHEDULER_IDENTITY,
    KEY_ROOT_ENV,
    SIGNER_PURPOSES,
    Keyring,
    ed25519_environment_verifier,
    ed25519_signer,
    ed25519_verifier,
    ensure_private_key,
    load_keyring,
    public_key_of,
    register_public_key,
)

REGISTERED_AT = "2026-09-05T10:00:00Z"


@dataclass(frozen=True)
class TemporarySigning:
    key_root: Path
    keyring_path: Path

    def environment(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        return {**(dict(base) if base is not None else os.environ), KEY_ROOT_ENV: str(self.key_root)}

    def keyring(self) -> Keyring:
        return load_keyring(self.keyring_path)

    def signer(self, identity: str) -> Callable[[bytes], str]:
        return ed25519_signer(identity, root=self.key_root, keyring=self.keyring())

    def verifier(self, identity: str) -> Callable[[bytes, str], bool]:
        return ed25519_verifier(self.keyring(), identity)

    def environment_verifier(self, identities: Iterable[str] = (ENVIRONMENT_OPS_IDENTITY,)) -> Callable[[str, bytes, str], bool]:
        return ed25519_environment_verifier(self.keyring(), identities)


def create_temporary_signing(
    root: Path,
    *,
    identities: Iterable[str] = (ENVIRONMENT_OPS_IDENTITY, INTEGRATION_SCHEDULER_IDENTITY),
) -> TemporarySigning:
    """在 root 下生成私钥根与 keyring；重复调用幂等（私钥复用、公钥不变）。"""

    key_root = root / "evidence-signing-keys"
    keyring_path = root / "evidence_signing_keyring.yaml"
    for identity in identities:
        if identity not in SIGNER_PURPOSES:
            raise ValueError(f"{identity} is not a declared evidence signer")
        pem = ensure_private_key(identity, root=key_root, create=True)
        register_public_key(
            keyring_path=keyring_path, identity=identity, public_key=public_key_of(pem),
            registered_at=REGISTERED_AT,
        )
    return TemporarySigning(key_root=key_root, keyring_path=keyring_path)
