#!/usr/bin/env python3
"""Issue and verify an IntegrationQualificationFact for the exact dev1.0 head."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

from quwoquan_ops.ci.environment_scheduler import (  # noqa: E402
    ACCEPTANCE_SCHEMA,
    canonical_json_bytes,
    dsse_pae,
    exact_file_digest,
    validate_environment_acceptance_fact,
)

SCHEMA = "quwoquan_ops.integration_qualification_fact.v1"
PAYLOAD_TYPE = "application/vnd.quwoquan.integration-qualification-fact.v1+json"
_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENVIRONMENTS = ("alpha", "beta", "gamma")
_REQUIRED_KEYS = {
    "schema",
    "qualificationId",
    "decision",
    "devRef",
    "devHead",
    "devTree",
    "candidate",
    "publishResult",
    "publishAdmission",
    "environmentChain",
    "impactPlanDigest",
    "issuedAt",
    "expiresAt",
    "signer",
}


class IntegrationQualificationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def hmac_sha256_signer(key: bytes) -> Callable[[bytes], str]:
    """Build the repository HMAC signer with an algorithm-bound encoding."""

    if not isinstance(key, bytes) or not key:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNER_UNAVAILABLE",
            "HMAC signing key is unavailable",
        )
    signing_key = bytes(key)

    def sign(payload: bytes) -> str:
        return (
            "hmac-sha256:" + hmac.new(signing_key, payload, hashlib.sha256).hexdigest()
        )

    return sign


def hmac_sha256_verifier(key: bytes) -> Callable[[bytes, str], bool]:
    """Build the repository HMAC verifier using constant-time comparison."""

    signer = hmac_sha256_signer(key)

    def verify(payload: bytes, signature: str) -> bool:
        if not isinstance(signature, str):
            return False
        return hmac.compare_digest(signer(payload), signature)

    return verify


def hmac_sha256_environment_verifier(
    trust_keys: Mapping[str, bytes],
) -> Callable[[str, bytes, str], bool]:
    """Build a fail-closed signer-identity trust provider for EAF DSSE."""

    if not isinstance(trust_keys, Mapping) or not trust_keys:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
            "environment signer trust is unavailable",
        )
    verifiers: dict[str, Callable[[bytes, str], bool]] = {}
    for identity, key in trust_keys.items():
        normalized_identity = _text(identity, "environmentSignerIdentity")
        verifiers[normalized_identity] = hmac_sha256_verifier(key)

    def verify(identity: str, payload: bytes, signature: str) -> bool:
        verifier = verifiers.get(identity)
        return verifier is not None and verifier(payload, signature) is True

    return verify


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} is invalid"
        )
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA.fullmatch(text) is None:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID",
            f"{field} must be an exact Git object id",
        )
    return text


def _digest(value: object, field: str) -> str:
    text = _text(value, field)
    if _DIGEST.fullmatch(text) is None:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} must be an exact digest"
        )
    return text


def _timestamp(value: object, field: str) -> tuple[str, datetime]:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} must be RFC3339"
        ) from exc
    if parsed.tzinfo is None:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} needs timezone"
        )
    return text, parsed


def _normalized_ref(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} must contain ref and digest"
        )
    ref = _text(value.get("ref"), f"{field}.ref")
    posix = PurePosixPath(ref)
    if (
        posix.is_absolute()
        or posix.as_posix() != ref
        or any(part in {"", ".", ".."} for part in posix.parts)
        or "\\" in ref
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field}.ref is unsafe"
        )
    return {"ref": ref, "digest": _digest(value.get("digest"), f"{field}.digest")}


def _exact_ref(
    root: Path, value: object, field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    normalized = _normalized_ref(value, field)
    path = root.joinpath(*PurePosixPath(normalized["ref"]).parts)
    current = root
    for part in PurePosixPath(normalized["ref"]).parts:
        current = current / part
        if current.is_symlink():
            raise IntegrationQualificationError(
                "INTEGRATION_QUALIFICATION.INVALID", f"{field}.ref traverses symlink"
            )
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.MISSING", f"{field} is missing"
        )
    if exact_file_digest(path) != normalized["digest"]:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.STALE", f"{field} bytes drifted"
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} is not an object"
        )
    if raw != canonical_json_bytes(payload) + b"\n":
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", f"{field} bytes are not canonical"
        )
    return payload, normalized


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repository, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.GIT_UNAVAILABLE",
            " ".join(completed.stderr.split()),
        )
    return completed.stdout.strip()


def _write_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_json_bytes(dict(payload)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise IntegrationQualificationError(
                "INTEGRATION_QUALIFICATION.CREATE_CONFLICT", path.name
            ) from exc
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _expected_environment_signers(
    value: Mapping[str, str],
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(_ENVIRONMENTS):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
            "expected environment signer identities must cover Alpha/Beta/Gamma",
        )
    return {
        environment: _text(value.get(environment), f"{environment}SignerIdentity")
        for environment in _ENVIRONMENTS
    }


def _load_acceptance(
    root: Path,
    exact: Mapping[str, str],
    environment: str,
    *,
    accepted_at: datetime,
    signature_verifier: Callable[[str, bytes, str], bool],
    expected_signer_identity: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not callable(signature_verifier):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
            "environment signature verifier is unavailable",
        )
    fact, normalized = _exact_ref(root, exact, f"{environment}Acceptance")
    if fact.get("schema") != ACCEPTANCE_SCHEMA:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            f"{environment} schema drifted",
        )
    try:
        fact = validate_environment_acceptance_fact(
            fact,
            store_root=root,
            verify_references=True,
            accepted_at=accepted_at,
            signature_verifier=signature_verifier,
            expected_signer_identity=expected_signer_identity,
        )
    except ValueError as exc:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID", str(exc)
        ) from exc
    if fact.get("environment") != environment:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID", f"expected {environment}"
        )
    return fact, normalized


def _load_environment_chain(
    *,
    root: Path,
    environment_refs: Mapping[str, Mapping[str, str]],
    accepted_at: datetime,
    signature_verifier: Callable[[str, bytes, str], bool],
    expected_signer_identities: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    if not isinstance(environment_refs, Mapping) or set(environment_refs) != set(
        _ENVIRONMENTS
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            "environment chain is incomplete",
        )
    expected_signers = _expected_environment_signers(expected_signer_identities)
    facts: dict[str, dict[str, Any]] = {}
    exacts: dict[str, dict[str, str]] = {}
    for environment in _ENVIRONMENTS:
        facts[environment], exacts[environment] = _load_acceptance(
            root,
            environment_refs[environment],
            environment,
            accepted_at=accepted_at,
            signature_verifier=signature_verifier,
            expected_signer_identity=expected_signers[environment],
        )
    if (
        facts["alpha"].get("predecessor") is not None
        or facts["beta"].get("predecessor") != exacts["alpha"]
        or facts["gamma"].get("predecessor") != exacts["beta"]
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            "Alpha/Beta/Gamma predecessor chain drifted",
        )
    return facts, exacts


def validate_integration_qualification(
    *,
    repository: Path,
    store_root: Path,
    qualification_ref: Mapping[str, str],
    expected_dev_head: str,
    expected_dev_tree: str,
    verified_at: str,
    signature_verifier: Callable[[bytes, str], bool],
    expected_signer_identity: str | None = None,
    environment_signature_verifier: Callable[[str, bytes, str], bool] | None = None,
    expected_environment_signer_identities: Mapping[str, str] | None = None,
    dev_ref: str = "refs/heads/dev1.0",
) -> tuple[dict[str, Any], dict[str, str]]:
    """Verify qualification DSSE, Git identity, TTL, and its exact EAF chain."""
    repository = repository.resolve()
    root = store_root.resolve()
    head = _sha(expected_dev_head, "expectedDevHead")
    tree = _sha(expected_dev_tree, "expectedDevTree")
    _, verified_time = _timestamp(verified_at, "verifiedAt")
    fact, normalized = _exact_ref(root, qualification_ref, "qualification")
    if set(fact) != _REQUIRED_KEYS or fact.get("schema") != SCHEMA:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "qualification shape or schema drifted"
        )
    if fact.get("decision") != "qualified" or fact.get("devRef") != dev_ref:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "qualification decision or ref drifted"
        )
    if fact.get("devHead") != head or fact.get("devTree") != tree:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT",
            "qualification does not bind the expected dev identity",
        )
    if _git(repository, "rev-parse", dev_ref) != head:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT", "dev ref readback drifted"
        )
    if _git(repository, "show", "-s", "--format=%T", head) != tree:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT", "dev tree readback drifted"
        )
    candidate = fact.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or set(candidate) != {"candidateId", "commit", "tree"}
        or _digest(candidate.get("candidateId"), "candidate.candidateId")
        != candidate.get("candidateId")
        or candidate.get("commit") != head
        or candidate.get("tree") != tree
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "candidate identity drifted"
        )
    _normalized_ref(fact.get("publishResult"), "publishResult")
    _normalized_ref(fact.get("publishAdmission"), "publishAdmission")
    chain = fact.get("environmentChain")
    if not isinstance(chain, Mapping) or set(chain) != {"alpha", "beta", "gamma"}:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "environment chain is incomplete"
        )
    normalized_chain = {
        environment: _normalized_ref(
            chain.get(environment), f"environmentChain.{environment}"
        )
        for environment in _ENVIRONMENTS
    }
    impact_digest = _digest(fact.get("impactPlanDigest"), "impactPlanDigest")
    _, issued_time = _timestamp(fact.get("issuedAt"), "issuedAt")
    _, expires_time = _timestamp(fact.get("expiresAt"), "expiresAt")
    if issued_time > verified_time:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.NOT_YET_VALID",
            "qualification was issued after verification time",
        )
    if verified_time >= expires_time:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.EXPIRED", "qualification expired"
        )
    signer = fact.get("signer")
    if not isinstance(signer, Mapping) or set(signer) != {
        "identity",
        "payloadType",
        "payload",
        "signature",
    }:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID", "signer envelope drifted"
        )
    identity = _text(signer.get("identity"), "signer.identity")
    if expected_signer_identity is None:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.VERIFIER_UNAVAILABLE",
            "expected qualification signer identity is required",
        )
    expected_qualification_signer = _text(
        expected_signer_identity, "expectedSignerIdentity"
    )
    if identity != expected_qualification_signer:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID", "signer identity drifted"
        )
    if signer.get("payloadType") != PAYLOAD_TYPE:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID", "payload type drifted"
        )
    try:
        signed_payload = base64.b64decode(str(signer.get("payload")), validate=True)
    except (ValueError, TypeError) as exc:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID",
            "payload is not canonical base64",
        ) from exc
    unsigned = dict(fact)
    unsigned.pop("qualificationId")
    unsigned.pop("signer")
    if signed_payload != canonical_json_bytes(unsigned):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID",
            "signed payload does not match qualification bytes",
        )
    signature = _text(signer.get("signature"), "signer.signature")
    try:
        verified = signature_verifier(dsse_pae(PAYLOAD_TYPE, signed_payload), signature)
    except Exception as exc:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID", "signature verifier failed"
        ) from exc
    if verified is not True:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.SIGNATURE_INVALID", "signature did not verify"
        )
    identity_body = dict(fact)
    qualification_id = _digest(identity_body.pop("qualificationId"), "qualificationId")
    expected_id = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(identity_body)).hexdigest()
    )
    if qualification_id != expected_id:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "qualificationId drifted"
        )
    if environment_signature_verifier is None or (
        expected_environment_signer_identities is None
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
            "environment acceptance verifier and signer identities are required",
        )
    expected_environment_signers = _expected_environment_signers(
        expected_environment_signer_identities
    )
    if expected_qualification_signer in set(expected_environment_signers.values()):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.KEY_PURPOSE_CONFLICT",
            "qualification and environment signer identities must differ",
        )
    environment_facts, _ = _load_environment_chain(
        root=root,
        environment_refs=normalized_chain,
        accepted_at=verified_time,
        signature_verifier=environment_signature_verifier,
        expected_signer_identities=expected_environment_signers,
    )
    if any(
        environment_facts[environment].get("candidate") != candidate
        or environment_facts[environment].get("impactPlanDigest") != impact_digest
        for environment in _ENVIRONMENTS
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            "environment chain identity drifted",
        )
    if environment_facts["gamma"].get("status") != "passed":
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID", "Gamma must pass"
        )
    return fact, normalized


def issue_integration_qualification(
    *,
    repository: Path,
    store_root: Path,
    publish_result_ref: Mapping[str, str],
    gamma_acceptance_ref: Mapping[str, str],
    signer_identity: str,
    signer: Callable[[bytes], str],
    environment_signature_verifier: Callable[[str, bytes, str], bool],
    expected_environment_signer_identities: Mapping[str, str],
    issued_at: str,
    expires_at: str,
    dev_ref: str = "refs/heads/dev1.0",
) -> Path:
    """Validate A/B/G and publisher readback, then seal the current dev head."""
    root = store_root.resolve()
    repository = repository.resolve()
    qualification_signer = _text(signer_identity, "signerIdentity")
    expected_environment_signers = _expected_environment_signers(
        expected_environment_signer_identities
    )
    if qualification_signer in set(expected_environment_signers.values()):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.KEY_PURPOSE_CONFLICT",
            "qualification and environment signer identities must differ",
        )
    issued_text, issued_time = _timestamp(issued_at, "issuedAt")
    expires_text, expires_time = _timestamp(expires_at, "expiresAt")
    if expires_time <= issued_time:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID", "expiresAt must follow issuedAt"
        )
    current_head = _sha(_git(repository, "rev-parse", dev_ref), "devHead")
    current_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", current_head), "devTree"
    )

    publish_result, publish_exact = _exact_ref(
        root, publish_result_ref, "publishResult"
    )
    if (
        publish_result.get("schema") != "quwoquan_ops.integration_publish_result.v1"
        or publish_result.get("terminal") != "published"
        or publish_result.get("targetRef") != dev_ref
        or publish_result.get("afterOid") != current_head
        or publish_result.get("readbackOid") != current_head
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT",
            "publisher result does not bind current dev head",
        )
    admission, admission_exact = _exact_ref(
        root, publish_result.get("admission"), "publishAdmission"
    )
    if (
        admission.get("schema") != "quwoquan_ops.integration_publish_admission.v1"
        or admission.get("decision") != "admitted"
        or admission.get("commit") != current_head
        or admission.get("tree") != current_tree
    ):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT",
            "publish admission differs from current dev head",
        )

    environment_refs = admission.get("environmentFacts")
    if not isinstance(environment_refs, Mapping) or set(environment_refs) != {
        "alpha",
        "beta",
    }:
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            "publish admission lacks Alpha/Beta",
        )
    environment_facts, environment_exacts = _load_environment_chain(
        root=root,
        environment_refs={
            "alpha": environment_refs["alpha"],
            "beta": environment_refs["beta"],
            "gamma": gamma_acceptance_ref,
        },
        accepted_at=issued_time,
        signature_verifier=environment_signature_verifier,
        expected_signer_identities=expected_environment_signers,
    )
    alpha = environment_facts["alpha"]
    beta = environment_facts["beta"]
    gamma = environment_facts["gamma"]
    alpha_exact = environment_exacts["alpha"]
    beta_exact = environment_exacts["beta"]
    gamma_exact = environment_exacts["gamma"]
    candidate = {
        "candidateId": admission.get("candidateId"),
        "commit": current_head,
        "tree": current_tree,
    }
    _digest(candidate["candidateId"], "candidate.candidateId")
    if any(fact.get("candidate") != candidate for fact in (alpha, beta, gamma)):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID",
            "environment candidate identity drifted",
        )
    if gamma.get("status") != "passed":
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.ENVIRONMENT_INVALID", "Gamma must pass"
        )

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "decision": "qualified",
        "devRef": dev_ref,
        "devHead": current_head,
        "devTree": current_tree,
        "candidate": candidate,
        "publishResult": publish_exact,
        "publishAdmission": admission_exact,
        "environmentChain": {
            "alpha": alpha_exact,
            "beta": beta_exact,
            "gamma": gamma_exact,
        },
        "impactPlanDigest": gamma["impactPlanDigest"],
        "issuedAt": issued_text,
        "expiresAt": expires_text,
    }
    payload = canonical_json_bytes(body)
    body["signer"] = {
        "identity": qualification_signer,
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signature": _text(signer(dsse_pae(PAYLOAD_TYPE, payload)), "signature"),
    }
    body["qualificationId"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    )
    return _write_once(
        root
        / "integration-qualification"
        / current_head
        / f"{body['qualificationId']}.json",
        body,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--store-root", required=True, type=Path)
    parser.add_argument("--qualification-ref", required=True)
    parser.add_argument("--qualification-digest", required=True)
    parser.add_argument("--expected-dev-head", required=True)
    parser.add_argument("--expected-dev-tree", required=True)
    parser.add_argument("--verified-at", required=True)
    parser.add_argument("--qualification-verification-key-env", required=True)
    parser.add_argument("--expected-qualification-signer-identity", required=True)
    parser.add_argument("--environment-verification-key-env", required=True)
    for environment in _ENVIRONMENTS:
        parser.add_argument(f"--expected-{environment}-signer-identity", required=True)
    return parser


def _environment_key(name: str, *, code: str) -> bytes:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise IntegrationQualificationError(
            "INTEGRATION_QUALIFICATION.INVALID",
            "verification key environment name is invalid",
        )
    value = os.environ.get(name, "")
    if not value:
        raise IntegrationQualificationError(code, f"{name} is missing")
    return value.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if (
            args.qualification_verification_key_env
            == args.environment_verification_key_env
        ):
            raise IntegrationQualificationError(
                "INTEGRATION_QUALIFICATION.KEY_PURPOSE_CONFLICT",
                "qualification and environment verification key sources must differ",
            )
        qualification_key = _environment_key(
            args.qualification_verification_key_env,
            code="INTEGRATION_QUALIFICATION.VERIFIER_UNAVAILABLE",
        )
        environment_key = _environment_key(
            args.environment_verification_key_env,
            code="INTEGRATION_QUALIFICATION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
        )
        if hmac.compare_digest(qualification_key, environment_key):
            raise IntegrationQualificationError(
                "INTEGRATION_QUALIFICATION.KEY_PURPOSE_CONFLICT",
                "qualification and environment verification keys must differ",
            )
        expected_environment_signers = {
            environment: getattr(args, f"expected_{environment}_signer_identity")
            for environment in _ENVIRONMENTS
        }
        environment_verifier = hmac_sha256_environment_verifier(
            {
                identity: environment_key
                for identity in expected_environment_signers.values()
            }
        )
        fact, exact = validate_integration_qualification(
            repository=args.repository,
            store_root=args.store_root,
            qualification_ref={
                "ref": args.qualification_ref,
                "digest": args.qualification_digest,
            },
            expected_dev_head=args.expected_dev_head,
            expected_dev_tree=args.expected_dev_tree,
            verified_at=args.verified_at,
            signature_verifier=hmac_sha256_verifier(qualification_key),
            expected_signer_identity=(args.expected_qualification_signer_identity),
            environment_signature_verifier=environment_verifier,
            expected_environment_signer_identities=expected_environment_signers,
        )
    except (OSError, IntegrationQualificationError) as error:
        code = (
            error.code
            if isinstance(error, IntegrationQualificationError)
            else "INTEGRATION_QUALIFICATION.IO_ERROR"
        )
        print(
            json.dumps(
                {"terminal": "GATE_BLOCK", "code": code, "detail": str(error)},
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "terminal": "qualified",
                "qualificationId": fact["qualificationId"],
                "ref": exact["ref"],
                "digest": exact["digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
