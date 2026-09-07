"""EnvironmentAcceptanceFact / IntegrationQualificationFact 的证据签名信任根。

模型：Ed25519 非对称。私钥只在本地 Environment Ops / integration scheduler 持有
（仓外、0600，默认 `~/.cache/quwoquan/keys/evidence-signing/<identity>.ed25519.pem`），
公钥按 signer identity 登记进仓内版本化 keyring
`quwoquan_ops/policies/evidence_signing_keyring.yaml`。hosted Delivery Gate 只用仓内公钥验签，
不持有任何可签名的材料，因此不需要 repository secret。

签名编码固定为 `ed25519:<base64 raw 64-byte signature>`，签名对象仍是 DSSE PAE 字节。
同一 identity 至多一个 `active` key；`retired` 只保留审计，不再参与验签。
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .ed25519_openssl import (
    Ed25519Error,
    RAW_PUBLIC_KEY_SIZE,
    SIGNATURE_SIZE,
    derive_public_key,
    generate_private_key_pem,
    sign as ed25519_sign,
    verify as ed25519_verify,
)
from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3

ROOT = Path(__file__).resolve().parents[3]
KEYRING_SCHEMA = "quwoquan_ops.evidence_signing_keyring.v1"
KEYRING_RELATIVE_PATH = "quwoquan_ops/policies/evidence_signing_keyring.yaml"
DEFAULT_KEYRING_PATH = ROOT / KEYRING_RELATIVE_PATH
KEY_ROOT_ENV = "QWQ_EVIDENCE_SIGNING_KEY_ROOT"
DEFAULT_KEY_ROOT = Path.home() / ".cache/quwoquan/keys/evidence-signing"
SIGNATURE_PREFIX = "ed25519:"
SIGNATURE_ENCODING = "ed25519:<base64 raw 64-byte signature over DSSE PAE>"
ENVIRONMENT_OPS_IDENTITY = "quwoquan-environment-ops-local"
INTEGRATION_SCHEDULER_IDENTITY = "quwoquan-integration-scheduler-local"
SIGNER_PURPOSES: Mapping[str, str] = {
    ENVIRONMENT_OPS_IDENTITY: "environment_acceptance",
    INTEGRATION_SCHEDULER_IDENTITY: "integration_qualification",
}
KEY_STATUSES = ("active", "retired")
_IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_KEY_ID_RE = re.compile(r"^ed25519-[0-9a-f]{16}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEADER = (
    "# 证据签名公钥 keyring（authoring source）。私钥永不进仓；条目只能由\n"
    "# `make evidence-signing-bootstrap`（quwoquan_ops/cli/evidence_signing_bootstrap.py）写入。\n"
    "# hosted Delivery Gate 只用这里的 active 公钥验签 EAF / IQF，不需要任何 repository secret。\n"
)


class EvidenceSigningError(ValueError):
    """Typed, stable failure for signer/verifier/keyring boundaries."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


_OPENSSL: OpenSSL3Executable | None = None


def _openssl() -> OpenSSL3Executable:
    global _OPENSSL
    if _OPENSSL is None:
        _OPENSSL = resolve_openssl3()
    return _OPENSSL


def key_id_for(public_key: bytes) -> str:
    return "ed25519-" + hashlib.sha256(public_key).hexdigest()[:16]


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", f"{field} is invalid")
    return value


@dataclass(frozen=True)
class KeyringKey:
    key_id: str
    public_key: bytes
    status: str
    registered_at: str
    retired_at: str | None

    def to_payload(self) -> dict[str, str]:
        payload = {
            "keyId": self.key_id,
            "publicKey": base64.b64encode(self.public_key).decode("ascii"),
            "status": self.status,
            "registeredAt": self.registered_at,
        }
        if self.retired_at is not None:
            payload["retiredAt"] = self.retired_at
        return payload


@dataclass(frozen=True)
class KeyringSigner:
    identity: str
    purpose: str
    keys: tuple[KeyringKey, ...]

    @property
    def active(self) -> KeyringKey | None:
        for key in self.keys:
            if key.status == "active":
                return key
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "purpose": self.purpose,
            "keys": [key.to_payload() for key in self.keys],
        }


@dataclass(frozen=True)
class Keyring:
    path: Path
    digest: str
    signers: Mapping[str, KeyringSigner]

    def active_public_key(self, identity: str) -> bytes:
        signer = self.signers.get(identity)
        active = signer.active if signer is not None else None
        if active is None:
            raise EvidenceSigningError(
                "EVIDENCE_SIGNING.SIGNER_UNREGISTERED",
                f"{identity} has no active Ed25519 public key in {self.path.name}; "
                "run `make evidence-signing-bootstrap` and commit the keyring",
            )
        return active.public_key


def _decode_public_key(value: Any) -> bytes:
    encoded = _text(value, "publicKey")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "publicKey is not strict base64") from exc
    if len(raw) != RAW_PUBLIC_KEY_SIZE or base64.b64encode(raw).decode("ascii") != encoded:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "publicKey is not a canonical Ed25519 key")
    return raw


def _parse_key(raw: Any) -> KeyringKey:
    if not isinstance(raw, Mapping):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "key entry must be a mapping")
    allowed = {"keyId", "publicKey", "status", "registeredAt", "retiredAt"}
    if not set(raw) <= allowed or not {"keyId", "publicKey", "status", "registeredAt"} <= set(raw):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "key entry fields drifted")
    public_key = _decode_public_key(raw["publicKey"])
    key_id = _text(raw["keyId"], "keyId")
    if _KEY_ID_RE.fullmatch(key_id) is None or key_id != key_id_for(public_key):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyId does not derive from publicKey")
    status = _text(raw["status"], "status")
    if status not in KEY_STATUSES:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "key status is unknown")
    registered_at = _text(raw["registeredAt"], "registeredAt")
    if _TIMESTAMP_RE.fullmatch(registered_at) is None:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "registeredAt must be RFC3339 UTC")
    retired_at = raw.get("retiredAt")
    if (status == "retired") != (retired_at is not None):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "retiredAt must accompany retired status only")
    if retired_at is not None and _TIMESTAMP_RE.fullmatch(_text(retired_at, "retiredAt")) is None:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "retiredAt must be RFC3339 UTC")
    return KeyringKey(key_id, public_key, status, registered_at, retired_at)


def _parse_signer(raw: Any) -> KeyringSigner:
    if not isinstance(raw, Mapping) or set(raw) != {"identity", "purpose", "keys"}:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "signer entry fields drifted")
    identity = _text(raw["identity"], "identity")
    if _IDENTITY_RE.fullmatch(identity) is None:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "signer identity is invalid")
    purpose = _text(raw["purpose"], "purpose")
    if SIGNER_PURPOSES.get(identity) != purpose:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", f"{identity} purpose is not canonical")
    keys_raw = raw["keys"]
    if not isinstance(keys_raw, list):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "signer keys must be a list")
    keys = tuple(_parse_key(item) for item in keys_raw)
    if sum(1 for key in keys if key.status == "active") > 1:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", f"{identity} has more than one active key")
    return KeyringSigner(identity, purpose, keys)


def _parse_keyring(payload: Any, *, path: Path, digest: str) -> Keyring:
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema", "authoringSource", "algorithm", "signatureEncoding", "signers",
    }:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyring root fields drifted")
    if payload["schema"] != KEYRING_SCHEMA:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyring schema is not canonical")
    if payload["authoringSource"] != KEYRING_RELATIVE_PATH:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyring authoringSource drifted")
    if payload["algorithm"] != "ed25519" or payload["signatureEncoding"] != SIGNATURE_ENCODING:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyring algorithm or encoding drifted")
    if not isinstance(payload["signers"], list):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "signers must be a list")
    signers: dict[str, KeyringSigner] = {}
    seen_keys: set[str] = set()
    for raw in payload["signers"]:
        signer = _parse_signer(raw)
        if signer.identity in signers:
            raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", f"duplicate signer {signer.identity}")
        for key in signer.keys:
            if key.key_id in seen_keys:
                raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", f"duplicate keyId {key.key_id}")
            seen_keys.add(key.key_id)
        signers[signer.identity] = signer
    return Keyring(path=path, digest=digest, signers=signers)


def load_keyring(path: Path = DEFAULT_KEYRING_PATH) -> Keyring:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_UNAVAILABLE", f"{path} is unreadable") from exc
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEYRING_INVALID", "keyring is not valid YAML") from exc
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return _parse_keyring(payload, path=path, digest=digest)


def _empty_payload() -> dict[str, Any]:
    return {
        "schema": KEYRING_SCHEMA,
        "authoringSource": KEYRING_RELATIVE_PATH,
        "algorithm": "ed25519",
        "signatureEncoding": SIGNATURE_ENCODING,
        "signers": [],
    }


def _write_keyring(path: Path, signers: Iterable[KeyringSigner]) -> None:
    payload = _empty_payload()
    payload["signers"] = [signer.to_payload() for signer in signers]
    body = _HEADER + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False)
    _parse_keyring(yaml.safe_load(body), path=path, digest="sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest())
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".keyring.", suffix=".tmp", delete=False) as handle:
        handle.write(body)
        staged = Path(handle.name)
    os.replace(staged, path)


def register_public_key(
    *,
    keyring_path: Path,
    identity: str,
    public_key: bytes,
    registered_at: str,
    rotate: bool = False,
) -> dict[str, str]:
    """把 identity 的公钥登记为 active。已有相同 active 公钥幂等；不同 active 公钥必须显式 rotate。"""

    if identity not in SIGNER_PURPOSES:
        raise EvidenceSigningError("EVIDENCE_SIGNING.SIGNER_UNKNOWN", f"{identity} is not a declared evidence signer")
    if _TIMESTAMP_RE.fullmatch(registered_at) is None:
        raise EvidenceSigningError("EVIDENCE_SIGNING.INVALID_ARGUMENT", "registeredAt must be RFC3339 UTC")
    if len(public_key) != RAW_PUBLIC_KEY_SIZE:
        raise EvidenceSigningError("EVIDENCE_SIGNING.INVALID_ARGUMENT", "public key is not Ed25519")
    if keyring_path.exists():
        keyring = load_keyring(keyring_path)
        signers = dict(keyring.signers)
    else:
        signers = {}
    signer = signers.get(identity, KeyringSigner(identity, SIGNER_PURPOSES[identity], ()))
    new_key_id = key_id_for(public_key)
    if any(key.key_id == new_key_id and key.status == "retired" for key in signer.keys):
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEY_RETIRED", f"{new_key_id} was retired and cannot be re-activated")
    active = signer.active
    if active is not None and active.public_key == public_key:
        return {"identity": identity, "keyId": new_key_id, "action": "unchanged"}
    keys = list(signer.keys)
    action = "registered"
    if active is not None:
        if not rotate:
            raise EvidenceSigningError(
                "EVIDENCE_SIGNING.KEY_CONFLICT",
                f"{identity} already has active key {active.key_id}; pass rotate to retire it",
            )
        keys = [
            KeyringKey(key.key_id, key.public_key, "retired", key.registered_at, registered_at)
            if key.key_id == active.key_id else key
            for key in keys
        ]
        action = "rotated"
    keys.append(KeyringKey(new_key_id, public_key, "active", registered_at, None))
    signers[identity] = KeyringSigner(identity, SIGNER_PURPOSES[identity], tuple(keys))
    ordered = [signers[name] for name in SIGNER_PURPOSES if name in signers]
    _write_keyring(keyring_path, ordered)
    return {"identity": identity, "keyId": new_key_id, "action": action}


def key_root(getenv: Callable[[str], str | None] = os.getenv, *, repo_root: Path = ROOT) -> Path:
    """私钥根目录：绝对路径且在仓库与 .qwq_output 之外。"""

    configured = str(getenv(KEY_ROOT_ENV) or "").strip()
    root = Path(configured).expanduser() if configured else DEFAULT_KEY_ROOT
    if not root.is_absolute():
        raise EvidenceSigningError("EVIDENCE_SIGNING.KEY_ROOT_INVALID", f"{KEY_ROOT_ENV} must be an absolute path")
    resolved = Path(os.path.abspath(root))
    for forbidden in (repo_root.resolve(), (repo_root / ".qwq_output").resolve()):
        try:
            resolved.resolve().relative_to(forbidden)
        except ValueError:
            continue
        raise EvidenceSigningError(
            "EVIDENCE_SIGNING.KEY_ROOT_INVALID", "private keys must stay outside the repository and .qwq_output",
        )
    return resolved


def private_key_path(identity: str, root: Path) -> Path:
    if identity not in SIGNER_PURPOSES:
        raise EvidenceSigningError("EVIDENCE_SIGNING.SIGNER_UNKNOWN", f"{identity} is not a declared evidence signer")
    return root / f"{identity}.ed25519.pem"


def ensure_private_key(identity: str, *, root: Path, create: bool) -> bytes:
    """读取（或在 create=True 时生成）identity 的私钥 PEM；权限必须为 0600 的普通文件。"""

    path = private_key_path(identity, root)
    if not path.exists() and not path.is_symlink():
        if not create:
            raise EvidenceSigningError(
                "EVIDENCE_SIGNING.PRIVATE_KEY_UNAVAILABLE",
                f"{path} is missing; run `make evidence-signing-bootstrap`",
            )
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        try:
            pem = generate_private_key_pem(openssl=_openssl())
        except Ed25519Error as exc:
            raise EvidenceSigningError("EVIDENCE_SIGNING.KEYGEN_FAILED", str(exc)) from exc
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(pem)
        return pem
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise EvidenceSigningError("EVIDENCE_SIGNING.PRIVATE_KEY_INVALID", f"{path} must be a regular non-symlink file")
    if info.st_mode & 0o077:
        raise EvidenceSigningError("EVIDENCE_SIGNING.PRIVATE_KEY_INVALID", f"{path} permissions must be 0600")
    return path.read_bytes()


def public_key_of(private_pem: bytes) -> bytes:
    try:
        return derive_public_key(private_pem, openssl=_openssl())
    except Ed25519Error as exc:
        raise EvidenceSigningError("EVIDENCE_SIGNING.PRIVATE_KEY_INVALID", str(exc)) from exc


def ed25519_signer(identity: str, *, root: Path, keyring: Keyring) -> Callable[[bytes], str]:
    """签名前校验本地私钥派生的公钥就是 keyring 中该 identity 的 active 公钥。"""

    expected = keyring.active_public_key(identity)
    private_pem = ensure_private_key(identity, root=root, create=False)
    if public_key_of(private_pem) != expected:
        raise EvidenceSigningError(
            "EVIDENCE_SIGNING.KEY_MISMATCH",
            f"local private key for {identity} does not match the active keyring public key",
        )
    openssl = _openssl()

    def sign(payload: bytes) -> str:
        try:
            signature = ed25519_sign(private_pem, payload, openssl=openssl)
        except Ed25519Error as exc:
            raise EvidenceSigningError("EVIDENCE_SIGNING.SIGN_FAILED", str(exc)) from exc
        return SIGNATURE_PREFIX + base64.b64encode(signature).decode("ascii")

    return sign


def decode_signature(text: Any) -> bytes | None:
    """`ed25519:<canonical base64>` → 64 字节；任何编码偏差都返回 None（验签按失败处理）。"""

    if not isinstance(text, str) or not text.startswith(SIGNATURE_PREFIX):
        return None
    encoded = text[len(SIGNATURE_PREFIX):]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None
    if len(raw) != SIGNATURE_SIZE or base64.b64encode(raw).decode("ascii") != encoded:
        return None
    return raw


def ed25519_verifier(keyring: Keyring, identity: str) -> Callable[[bytes, str], bool]:
    public_key = keyring.active_public_key(identity)
    openssl = _openssl()

    def verify(payload: bytes, signature: str) -> bool:
        raw = decode_signature(signature)
        if raw is None:
            return False
        try:
            return ed25519_verify(public_key, payload, raw, openssl=openssl)
        except Ed25519Error:
            return False

    return verify


def ed25519_environment_verifier(
    keyring: Keyring, identities: Iterable[str],
) -> Callable[[str, bytes, str], bool]:
    """按 signer identity 分派的 fail-closed 验签器；未登记 identity 在构造期即阻断。"""

    verifiers = {identity: ed25519_verifier(keyring, identity) for identity in set(identities)}
    if not verifiers:
        raise EvidenceSigningError("EVIDENCE_SIGNING.INVALID_ARGUMENT", "at least one signer identity is required")

    def verify(identity: str, payload: bytes, signature: str) -> bool:
        verifier = verifiers.get(identity)
        return verifier is not None and verifier(payload, signature) is True

    return verify


def assert_distinct_active_keys(keyring: Keyring, first: str, second: str) -> None:
    """qualification 与 environment 两条链的 active 公钥不得相同（保留原 KEY_PURPOSE_CONFLICT 语义）。"""

    if first == second or keyring.active_public_key(first) == keyring.active_public_key(second):
        raise EvidenceSigningError(
            "EVIDENCE_SIGNING.KEY_PURPOSE_CONFLICT",
            "qualification and environment signer identities must use distinct active keys",
        )
