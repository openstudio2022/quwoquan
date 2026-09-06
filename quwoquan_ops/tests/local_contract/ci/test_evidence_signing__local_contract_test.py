# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t5
"""证据签名信任根：Ed25519 私钥仅本地、公钥在仓内 keyring、hosted 只验签。"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from quwoquan_ops.cli.lib.evidence_signing import (
    DEFAULT_KEYRING_PATH,
    ENVIRONMENT_OPS_IDENTITY,
    INTEGRATION_SCHEDULER_IDENTITY,
    KEY_ROOT_ENV,
    SIGNER_PURPOSES,
    EvidenceSigningError,
    assert_distinct_active_keys,
    decode_signature,
    ed25519_environment_verifier,
    ed25519_signer,
    ed25519_verifier,
    ensure_private_key,
    key_id_for,
    key_root,
    load_keyring,
    public_key_of,
    register_public_key,
)
from quwoquan_ops.tests.support.evidence_signing_test_support import (
    REGISTERED_AT,
    create_temporary_signing,
)

ROOT = Path(__file__).resolve().parents[4]
BOOTSTRAP = ROOT / "quwoquan_ops/cli/evidence_signing_bootstrap.py"
PAYLOAD = b"DSSEv1 4 test 5 hello"


def test_repository_keyring_declares_both_canonical_signers_with_distinct_active_keys() -> None:
    keyring = load_keyring(DEFAULT_KEYRING_PATH)
    assert set(keyring.signers) == set(SIGNER_PURPOSES)
    for identity in SIGNER_PURPOSES:
        assert keyring.signers[identity].active is not None
    assert_distinct_active_keys(keyring, INTEGRATION_SCHEDULER_IDENTITY, ENVIRONMENT_OPS_IDENTITY)
    text = DEFAULT_KEYRING_PATH.read_text(encoding="utf-8")
    assert "PRIVATE KEY" not in text


def test_sign_and_verify_round_trip_uses_ed25519_encoding(tmp_path: Path) -> None:
    signing = create_temporary_signing(tmp_path)
    signature = signing.signer(ENVIRONMENT_OPS_IDENTITY)(PAYLOAD)
    assert signature.startswith("ed25519:")
    raw = decode_signature(signature)
    assert raw is not None and len(raw) == 64
    verify = signing.verifier(ENVIRONMENT_OPS_IDENTITY)
    assert verify(PAYLOAD, signature) is True
    assert verify(PAYLOAD + b"x", signature) is False
    assert verify(PAYLOAD, "hmac-sha256:" + "0" * 64) is False
    assert verify(PAYLOAD, "ed25519:" + base64.b64encode(b"\0" * 64).decode("ascii")) is False
    # 非 canonical base64（无 padding）与错误长度都按验签失败处理，不抛异常。
    assert verify(PAYLOAD, signature.rstrip("=")) is False
    assert verify(PAYLOAD, "ed25519:AAAA") is False


def test_environment_verifier_dispatches_by_identity_and_rejects_other_keys(tmp_path: Path) -> None:
    signing = create_temporary_signing(tmp_path / "a")
    other = create_temporary_signing(tmp_path / "b")
    signature = signing.signer(ENVIRONMENT_OPS_IDENTITY)(PAYLOAD)
    verify = signing.environment_verifier((ENVIRONMENT_OPS_IDENTITY,))
    assert verify(ENVIRONMENT_OPS_IDENTITY, PAYLOAD, signature) is True
    assert verify(INTEGRATION_SCHEDULER_IDENTITY, PAYLOAD, signature) is False
    assert verify("spiffe://unknown", PAYLOAD, signature) is False
    assert other.environment_verifier((ENVIRONMENT_OPS_IDENTITY,))(ENVIRONMENT_OPS_IDENTITY, PAYLOAD, signature) is False
    scheduler_only = create_temporary_signing(tmp_path / "c", identities=(INTEGRATION_SCHEDULER_IDENTITY,))
    with pytest.raises(EvidenceSigningError, match="SIGNER_UNREGISTERED"):
        ed25519_environment_verifier(scheduler_only.keyring(), (ENVIRONMENT_OPS_IDENTITY,))


def test_signer_requires_private_key_matching_active_public_key(tmp_path: Path) -> None:
    signing = create_temporary_signing(tmp_path / "a")
    other = create_temporary_signing(tmp_path / "b")
    with pytest.raises(EvidenceSigningError, match="KEY_MISMATCH"):
        ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=other.key_root, keyring=signing.keyring())
    with pytest.raises(EvidenceSigningError, match="PRIVATE_KEY_UNAVAILABLE"):
        ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=tmp_path / "missing", keyring=signing.keyring())
    private = signing.key_root / f"{ENVIRONMENT_OPS_IDENTITY}.ed25519.pem"
    private.chmod(0o644)
    with pytest.raises(EvidenceSigningError, match="permissions must be 0600"):
        ensure_private_key(ENVIRONMENT_OPS_IDENTITY, root=signing.key_root, create=False)
    private.chmod(0o600)


def test_key_root_must_be_absolute_and_outside_repository(tmp_path: Path) -> None:
    assert key_root({KEY_ROOT_ENV: str(tmp_path)}.get) == Path(os.path.abspath(tmp_path))
    with pytest.raises(EvidenceSigningError, match="KEY_ROOT_INVALID"):
        key_root({KEY_ROOT_ENV: "relative/keys"}.get)
    for inside in (ROOT / "quwoquan_ops/keys", ROOT / ".qwq_output/env/repo/local/keys"):
        with pytest.raises(EvidenceSigningError, match="outside the repository"):
            key_root({KEY_ROOT_ENV: str(inside)}.get)


def test_register_is_idempotent_requires_rotate_and_never_reactivates_retired(tmp_path: Path) -> None:
    keyring_path = tmp_path / "keyring.yaml"
    first = ensure_private_key(ENVIRONMENT_OPS_IDENTITY, root=tmp_path / "k1", create=True)
    second = ensure_private_key(ENVIRONMENT_OPS_IDENTITY, root=tmp_path / "k2", create=True)
    first_public, second_public = public_key_of(first), public_key_of(second)
    assert register_public_key(keyring_path=keyring_path, identity=ENVIRONMENT_OPS_IDENTITY, public_key=first_public, registered_at=REGISTERED_AT)["action"] == "registered"
    assert register_public_key(keyring_path=keyring_path, identity=ENVIRONMENT_OPS_IDENTITY, public_key=first_public, registered_at=REGISTERED_AT)["action"] == "unchanged"
    with pytest.raises(EvidenceSigningError, match="KEY_CONFLICT"):
        register_public_key(keyring_path=keyring_path, identity=ENVIRONMENT_OPS_IDENTITY, public_key=second_public, registered_at=REGISTERED_AT)
    rotated = register_public_key(keyring_path=keyring_path, identity=ENVIRONMENT_OPS_IDENTITY, public_key=second_public, registered_at="2026-09-06T00:00:00Z", rotate=True)
    assert rotated["action"] == "rotated" and rotated["keyId"] == key_id_for(second_public)
    keyring = load_keyring(keyring_path)
    signer = keyring.signers[ENVIRONMENT_OPS_IDENTITY]
    assert [key.status for key in signer.keys] == ["retired", "active"]
    assert signer.keys[0].retired_at == "2026-09-06T00:00:00Z"
    # retired key 不再参与验签
    old_signature = ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=tmp_path / "k2", keyring=keyring)(PAYLOAD)
    assert ed25519_verifier(keyring, ENVIRONMENT_OPS_IDENTITY)(PAYLOAD, old_signature) is True
    with pytest.raises(EvidenceSigningError, match="KEY_MISMATCH"):
        ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=tmp_path / "k1", keyring=keyring)
    with pytest.raises(EvidenceSigningError, match="KEY_RETIRED"):
        register_public_key(keyring_path=keyring_path, identity=ENVIRONMENT_OPS_IDENTITY, public_key=first_public, registered_at=REGISTERED_AT, rotate=True)
    with pytest.raises(EvidenceSigningError, match="SIGNER_UNKNOWN"):
        register_public_key(keyring_path=keyring_path, identity="spiffe://unknown", public_key=first_public, registered_at=REGISTERED_AT)


def test_keyring_loader_rejects_drift(tmp_path: Path) -> None:
    signing = create_temporary_signing(tmp_path)
    original = yaml.safe_load(signing.keyring_path.read_text(encoding="utf-8"))

    def mutated(mutate) -> Path:
        payload = json.loads(json.dumps(original))
        mutate(payload)
        path = tmp_path / "mutated.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    def two_active(payload: dict) -> None:
        key = dict(payload["signers"][0]["keys"][0])
        key["publicKey"] = base64.b64encode(b"\1" * 32).decode("ascii")
        key["keyId"] = key_id_for(b"\1" * 32)
        payload["signers"][0]["keys"].append(key)

    def wrong_key_id(payload: dict) -> None:
        payload["signers"][0]["keys"][0]["keyId"] = "ed25519-" + "0" * 16

    def wrong_purpose(payload: dict) -> None:
        payload["signers"][0]["purpose"] = "integration_qualification"

    def duplicate_signer(payload: dict) -> None:
        payload["signers"].append(json.loads(json.dumps(payload["signers"][0])))

    def unknown_status(payload: dict) -> None:
        payload["signers"][0]["keys"][0]["status"] = "pending"

    def extra_root_field(payload: dict) -> None:
        payload["privateKey"] = "never"

    for label, mutate in (
        ("two active keys", two_active),
        ("keyId drift", wrong_key_id),
        ("purpose drift", wrong_purpose),
        ("duplicate signer", duplicate_signer),
        ("unknown status", unknown_status),
        ("extra root field", extra_root_field),
    ):
        with pytest.raises(EvidenceSigningError, match="KEYRING_INVALID"):
            load_keyring(mutated(mutate))
        assert label
    with pytest.raises(EvidenceSigningError, match="KEYRING_UNAVAILABLE"):
        load_keyring(tmp_path / "absent.yaml")


def test_bootstrap_cli_is_idempotent_and_keeps_private_keys_outside_repository(tmp_path: Path) -> None:
    keyring_path = tmp_path / "keyring.yaml"
    environment = {**os.environ, KEY_ROOT_ENV: str(tmp_path / "keys"), "PYTHONDONTWRITEBYTECODE": "1"}
    argv = [sys.executable, "-B", str(BOOTSTRAP), "--keyring", str(keyring_path), "--registered-at", REGISTERED_AT]
    first = subprocess.run(argv, cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    payload = json.loads(first.stdout.strip().splitlines()[-1])
    assert payload["terminal"] == "bootstrapped"
    assert {item["action"] for item in payload["signers"]} == {"registered"}
    for item in payload["signers"]:
        private = Path(item["privateKeyPath"])
        assert private.is_file() and (private.stat().st_mode & 0o777) == 0o600
        assert not private.resolve().is_relative_to(ROOT.resolve())
    assert "PRIVATE KEY" not in first.stdout
    second = subprocess.run(argv, cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert {item["action"] for item in json.loads(second.stdout.strip().splitlines()[-1])["signers"]} == {"unchanged"}
    inside = subprocess.run(
        argv, cwd=ROOT, env={**environment, KEY_ROOT_ENV: str(ROOT / ".qwq_output/keys")},
        text=True, capture_output=True, check=False,
    )
    assert inside.returncode == 2
    assert json.loads(inside.stdout)["code"] == "EVIDENCE_SIGNING.KEY_ROOT_INVALID"
