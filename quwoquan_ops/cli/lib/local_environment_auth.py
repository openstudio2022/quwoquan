from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import ssl
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from .output_paths import (
    active_deployment_candidate,
    deployment_target_path,
    deployment_target_path_in_work_root,
    env_runs_root,
)
from .local_target_handoff import target_for_hostname
from .public_domain_tls import root_certificate_path


_SECRET_KEYS = (
    "jwt_secret",
    "device_ticket_secret",
    "otp_code_ref_key_b64",
    "push_token_encryption_key_b64",
    "research_identity_attestation_key_b64",
    "account_closure_subject_hmac_secret",
    "rtc_media_api_key",
    "rtc_media_api_secret",
    "sms_substitute_provider_token",
    "sms_substitute_operator_token",
    "provider_substitute_operator_token",
    "sms_substitute_capture_key_b64",
)
_LOCAL_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    # prod-sim 使用 production 配置投影，但其认证材料仍限定在本机部署目录。
    "prod": "prod-sim",
}
_TEST_DATA_IDENTITY_SET_SCHEMA = "qwq.test_data_identity_set.v1"
_TEST_DATA_IDENTITY_SET_PATH_ENV = "QWQ_TEST_DATA_IDENTITY_SET_PATH"
_TEST_DATA_IDENTITY_SET_NAME = "test-data-identity-set.json"
_TEST_DATA_IDENTITY_SET_LOCK_NAME = "test-data-identity-set.lock"
_TEST_DATA_PHONE_PROFILES = frozenset({"nonroutable", "mainland_ui"})
_RESEARCH_IDENTITY_BINDING_SCHEMA = "qwq.local_research_identity_binding.v1"
_RESEARCH_IDENTITY_BINDING_NAME = "research-identity-binding.json"
_CROCKFORD_LOWER = "0123456789abcdefghjkmnpqrstvwxyz"
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LocalEnvironmentAuth:
    environment: dict[str, str]
    secret_path: Path


@dataclass(frozen=True)
class LocalAcceptanceSession:
    """Ephemeral bearer session for a local integration environment."""

    owner_id: str
    persona_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)

    def authorization_header(self) -> str:
        return "Bearer " + self.access_token


@dataclass(frozen=True)
class LocalAcceptanceActor:
    """Canonical non-production account created through public auth commands."""

    role: str
    session: LocalAcceptanceSession
    challenge_id: str
    account_state: str
    identity_origin: str


@dataclass(frozen=True)
class LocalEnvironmentHTTPError(RuntimeError):
    """Redacted local-environment HTTP failure with a machine-readable status."""

    method: str
    path: str
    status: int

    def __str__(self) -> str:
        return f"local environment request {self.method} {self.path} failed with HTTP {self.status}"


def prepare_local_environment_auth(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> LocalEnvironmentAuth:
    """Create target-isolated auth material in the external deploy workspace."""
    _require_local_environment(environment, target_name)
    secret_path = _local_environment_secret_path(
        target_name,
        deployment_work_root=deployment_work_root,
    )
    values = _load_or_create_secrets(secret_path)
    research_identity = (
        materialize_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if environment in {"alpha", "beta", "gamma"}
        else None
    )
    return _local_environment_auth(
        environment,
        secret_path,
        values,
        research_identity=research_identity,
    )


def load_local_environment_auth(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> LocalEnvironmentAuth:
    """Load existing target auth material without creating or migrating it."""

    _require_local_environment(environment, target_name)
    secret_path = _local_environment_secret_path(
        target_name,
        deployment_work_root=deployment_work_root,
    )
    if not secret_path.is_file():
        raise RuntimeError(
            f"GATE_BLOCK: local environment auth material is unavailable: {secret_path}"
        )
    _require_mode(secret_path, 0o600)
    values = _read_secret_file(secret_path)
    missing = [key for key in _SECRET_KEYS if not values.get(key)]
    if missing:
        raise RuntimeError(
            "GATE_BLOCK: local environment auth secret file is incomplete: "
            + ", ".join(missing)
        )
    research_identity = (
        load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if environment in {"alpha", "beta", "gamma"}
        else None
    )
    return _local_environment_auth(
        environment,
        secret_path,
        values,
        research_identity=research_identity,
    )


def _local_environment_secret_path(
    target_name: str,
    *,
    deployment_work_root: str | Path | None,
) -> Path:
    return (
        deployment_target_path(target_name, "secrets", "auth.env")
        if deployment_work_root is None
        else deployment_target_path_in_work_root(
            deployment_work_root,
            target_name,
            "secrets",
            "auth.env",
        )
    )


def _local_environment_auth(
    environment: str,
    secret_path: Path,
    values: dict[str, str],
    *,
    research_identity: dict[str, str] | None,
) -> LocalEnvironmentAuth:
    key_version = f"local-{environment}-k1"
    runtime_environment = {
        "AUTH_JWT_SECRET": values["jwt_secret"],
            "AUTH_JWT_ISSUER": f"quwoquan.{environment}.local",
            "AUTH_JWT_AUDIENCE": "quwoquan-app",
            "AUTH_JWT_TOKEN_VERSION": "1",
            "AUTH_DEVICE_TICKET_SECRET": values["device_ticket_secret"],
            "AUTH_DEVICE_TICKET_ISSUER": f"quwoquan.{environment}.local.device",
            "AUTH_DEVICE_TICKET_AUDIENCE": "quwoquan-app-device",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION": "1",
            "OTP_CODE_REF_ACTIVE_KEY_VERSION": key_version,
            "OTP_CODE_REF_KEYS_JSON": json.dumps(
                {key_version: values["otp_code_ref_key_b64"]},
                separators=(",", ":"),
            ),
            "QWQ_PUSH_TOKEN_ENCRYPTION_KEY": values[
                "push_token_encryption_key_b64"
            ],
            # User signs and Content verifies the same short-lived Alpha
            # Research identity attestation.  Keep the shared authority in
            # the target-scoped external secret file; never derive it from
            # source or materialize two independent keys.
            "USER_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64": values[
                "research_identity_attestation_key_b64"
            ],
            "CONTENT_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64": values[
                "research_identity_attestation_key_b64"
            ],
            "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET": values[
                "account_closure_subject_hmac_secret"
            ],
            "RTC_MEDIA_API_KEY": values["rtc_media_api_key"],
            "RTC_MEDIA_API_SECRET": values["rtc_media_api_secret"],
            "INTEGRATION_SMS_TOKEN": values["sms_substitute_provider_token"],
            "SMS_SUBSTITUTE_PROVIDER_TOKEN": values[
                "sms_substitute_provider_token"
            ],
            "SMS_SUBSTITUTE_OPERATOR_TOKEN": values[
                "sms_substitute_operator_token"
            ],
            "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN": values[
                "provider_substitute_operator_token"
            ],
        "SMS_SUBSTITUTE_CAPTURE_KEY_B64": values[
            "sms_substitute_capture_key_b64"
        ],
    }
    if research_identity is not None:
        runtime_environment.update(
            {
                "USER_RESEARCH_IDENTITY_ACCOUNT_ID_ALLOWLIST_JSON": json.dumps(
                    [research_identity["accountId"]],
                    separators=(",", ":"),
                ),
                "USER_MANAGED_ACCEPTANCE_IDENTITY_JSON": json.dumps(
                    {
                        "phone": research_identity["phone"],
                        "accountId": research_identity["accountId"],
                        "subjectHash": research_identity["subjectHash"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        )
    return LocalEnvironmentAuth(
        environment=runtime_environment,
        secret_path=secret_path,
    )


def materialize_local_research_identity_binding(
    *,
    environment: str,
    target_name: str,
    deployment_work_root: str | Path | None = None,
) -> dict[str, str]:
    """Freeze the pre-runtime Research subject/account identity outside source.

    The phone is a target-scoped protected Provider input.  Its canonical
    account identity is deterministic, so User startup can fail closed before
    the first OTP login and the later live login can prove the same subject.
    """

    _require_nonprod_target(environment, target_name)
    secret_root = (
        _local_environment_secret_path(
            target_name,
            deployment_work_root=deployment_work_root,
        ).parent
    )
    secret_root.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_root, 0o700)
    target_slot = {"alpha-local": "1", "beta-local": "2", "gamma-local": "3"}[
        target_name
    ]
    identity_set_slot = int(
        hashlib.sha256(
            f"{target_name}\0research-identity".encode("utf-8")
        ).hexdigest()[:16],
        16,
    )
    phone = f"+86199{target_slot}{identity_set_slot % 10_000:04d}000"
    subject_hash = "sha256:" + hashlib.sha256(phone.encode("utf-8")).hexdigest()
    account_id = _deterministic_phone_owner_id(target_name, phone)
    payload = {
        "schema": _RESEARCH_IDENTITY_BINDING_SCHEMA,
        "environment": environment,
        "target": target_name,
        "phone": phone,
        "subjectHash": subject_hash,
        "accountId": account_id,
    }
    path = secret_root / _RESEARCH_IDENTITY_BINDING_NAME
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.exists():
        existing = load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if existing != payload:
            raise RuntimeError("GATE_BLOCK: research identity binding drift")
        return existing
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError:
        existing = load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if existing != payload:
            raise RuntimeError("GATE_BLOCK: research identity binding drift")
        return existing
    finally:
        os.close(fd)
        temporary.unlink(missing_ok=True)
    return payload


def load_local_research_identity_binding(
    *,
    environment: str,
    target_name: str,
    deployment_work_root: str | Path | None = None,
) -> dict[str, str]:
    _require_nonprod_target(environment, target_name)
    secret_root = (
        _local_environment_secret_path(
            target_name,
            deployment_work_root=deployment_work_root,
        ).parent
    )
    path = secret_root / _RESEARCH_IDENTITY_BINDING_NAME
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("GATE_BLOCK: research identity binding is unavailable")
    _require_mode(path, 0o600)
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema",
        "environment",
        "target",
        "phone",
        "subjectHash",
        "accountId",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload.get("schema") != _RESEARCH_IDENTITY_BINDING_SCHEMA
        or payload.get("environment") != environment
        or payload.get("target") != target_name
    ):
        raise RuntimeError("GATE_BLOCK: research identity binding identity mismatch")
    phone = str(payload.get("phone") or "").strip()
    if (
        re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) is None
        or payload.get("subjectHash")
        != "sha256:" + hashlib.sha256(phone.encode("utf-8")).hexdigest()
        or payload.get("accountId") != _deterministic_phone_owner_id(target_name, phone)
    ):
        raise RuntimeError("GATE_BLOCK: research identity binding is invalid")
    return {key: str(payload[key]) for key in expected_keys}


def _deterministic_phone_owner_id(target_name: str, phone: str) -> str:
    digest = hashlib.sha256(
        f"{target_name}\0research-acceptance\0{phone}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest, "big") >> (256 - 130)
    entropy = "".join(
        _CROCKFORD_LOWER[(value >> shift) & 31]
        for shift in range(125, -1, -5)
    )
    shard = _xxh64(("01|ph|" + entropy).encode("ascii")) % 16384
    return f"uo_01_ph_{shard:04x}_{entropy}"


def _xxh64(value: bytes) -> int:
    """Small canonical XXH64 implementation matching User identity routing."""

    mask = (1 << 64) - 1
    p1, p2, p3, p4, p5 = (
        11400714785074694791,
        14029467366897019727,
        1609587929392839161,
        9650029242287828579,
        2870177450012600261,
    )

    def rotl(number: int, bits: int) -> int:
        return ((number << bits) | (number >> (64 - bits))) & mask

    def round64(accumulator: int, lane: int) -> int:
        accumulator = (accumulator + lane * p2) & mask
        accumulator = rotl(accumulator, 31)
        return (accumulator * p1) & mask

    length = len(value)
    offset = 0
    if length >= 32:
        accumulators = [p1 + p2, p2, 0, (-p1) & mask]
        while offset <= length - 32:
            for index in range(4):
                lane = int.from_bytes(value[offset : offset + 8], "little")
                accumulators[index] = round64(accumulators[index], lane)
                offset += 8
        result = sum(
            rotl(accumulators[index], bits)
            for index, bits in enumerate((1, 7, 12, 18))
        ) & mask
        for accumulator in accumulators:
            mixed = round64(0, accumulator)
            result ^= mixed
            result = (result * p1 + p4) & mask
    else:
        result = p5
    result = (result + length) & mask
    while offset <= length - 8:
        lane = int.from_bytes(value[offset : offset + 8], "little")
        result ^= round64(0, lane)
        result = (rotl(result, 27) * p1 + p4) & mask
        offset += 8
    if offset <= length - 4:
        result ^= int.from_bytes(value[offset : offset + 4], "little") * p1
        result = (rotl(result, 23) * p2 + p3) & mask
        offset += 4
    while offset < length:
        result ^= value[offset] * p5
        result = (rotl(result, 11) * p1) & mask
        offset += 1
    result ^= result >> 33
    result = (result * p2) & mask
    result ^= result >> 29
    result = (result * p3) & mask
    return (result ^ (result >> 32)) & mask


def mint_local_filter_catalog_service_token(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> str:
    """Mint one 30-minute qwq-data token through the canonical Go signer."""

    auth = prepare_local_environment_auth(
        environment,
        target_name,
        deployment_work_root=deployment_work_root,
    )
    process_environment = {
        **os.environ,
        **auth.environment,
        "GOCACHE": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-build/local-service-credential"
        ),
        "GOTMPDIR": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-tmp/local-service-credential"
        ),
    }
    Path(process_environment["GOCACHE"]).mkdir(parents=True, exist_ok=True)
    Path(process_environment["GOTMPDIR"]).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["go", "run", "./cmd/local-filter-catalog-credential"],
        cwd=_REPO_ROOT / "quwoquan_service",
        env=process_environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or "\n" in token:
        raise RuntimeError(
            "local FilterCatalog service credential mint failed"
            + (f" (exit={result.returncode})" if result.returncode else "")
        )
    claims = _decode_local_jwt_claims(
        token,
        label="local FilterCatalog service credential",
    )
    if (
        claims.get("sub") != "service:qwq-data"
        or claims.get("roles") != ["service"]
        or "content.filter_catalog.manage"
        not in str(claims.get("scope") or "").split()
        or claims.get("iss") != auth.environment["AUTH_JWT_ISSUER"]
        or claims.get("aud") != auth.environment["AUTH_JWT_AUDIENCE"]
        or not isinstance(claims.get("iat"), int)
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] - claims["iat"] != 30 * 60
    ):
        raise RuntimeError(
            "local FilterCatalog service credential claims mismatch"
        )
    return token


def mint_local_product_ops_operator_token(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> str:
    """Mint one 15-minute Alpha/Beta/Gamma Product Ops operator credential.

    Prod and every non-local target must use the real RS256 OIDC path and are
    rejected before the canonical signer is invoked.
    """

    _require_local_environment(environment, target_name)
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "local Product Ops operator credential is limited to Alpha/Beta/Gamma"
        )
    auth = prepare_local_environment_auth(
        environment,
        target_name,
        deployment_work_root=deployment_work_root,
    )
    process_environment = {
        **os.environ,
        **auth.environment,
        "APP_ENV": environment,
        "GOCACHE": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-build/local-operator-credential"
        ),
        "GOTMPDIR": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-tmp/local-operator-credential"
        ),
    }
    Path(process_environment["GOCACHE"]).mkdir(parents=True, exist_ok=True)
    Path(process_environment["GOTMPDIR"]).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["go", "run", "./cmd/local-product-ops-operator-credential"],
        cwd=_REPO_ROOT / "quwoquan_service",
        env=process_environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or "\n" in token:
        raise RuntimeError(
            "local Product Ops operator credential mint failed"
            + (f" (exit={result.returncode})" if result.returncode else "")
        )
    claims = _decode_local_jwt_claims(
        token,
        label="local Product Ops operator credential",
    )
    expected_subject = f"operator:content-commercial:{environment}"
    if (
        claims.get("sub") != expected_subject
        or claims.get("roles") != ["operator"]
        or str(claims.get("scope") or "").split()
        != [
            "ops.experiment.read",
            "ops.experiment.write",
            "ops.reco.read",
            "ops.reco.write",
            "ops.telemetry.read",
        ]
        or claims.get("iss") != auth.environment["AUTH_JWT_ISSUER"]
        or claims.get("aud") != auth.environment["AUTH_JWT_AUDIENCE"]
        or not isinstance(claims.get("iat"), int)
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] - claims["iat"] != 15 * 60
    ):
        raise RuntimeError(
            "local Product Ops operator credential claims mismatch"
        )
    return token


def _decode_local_jwt_claims(token: str, *, label: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError(f"{label} is not a JWT")
    try:
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(
            base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        )
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} claims are invalid") from exc
    if not isinstance(claims, dict):
        raise RuntimeError(f"{label} claims are invalid")
    return claims


def request_local_environment_json(
    base_url: str,
    *,
    path: str,
    session: LocalAcceptanceSession,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Call a local environment JSON endpoint using bearer auth without logging it."""

    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request_headers = {
        "Accept": "application/json",
        "Authorization": session.authorization_header(),
        "X-Client-Session-Id": "local-acceptance-" + session.owner_id[-12:],
    }
    for name, value in (headers or {}).items():
        if name.lower() == "authorization":
            raise ValueError("local environment request headers cannot override Authorization")
        request_headers[name] = value
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    status, response = _trusted_json_request(
        method=method,
        url=base_url.rstrip("/") + normalized_path,
        body=payload,
        headers=request_headers,
        timeout_seconds=timeout_seconds,
    )
    if status < 200 or status >= 300:
        raise LocalEnvironmentHTTPError(method=method, path=normalized_path, status=status)
    return response


def open_local_phone_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    test_data_instance_id: str,
    identity_set_id: str,
    actor_role: str,
    actor_index: int,
    timeout_seconds: float = 30.0,
) -> LocalAcceptanceActor:
    """Create or restore a real nonprod account via OTP and phone login.

    Phone numbers come from a target-scoped protected identity pool and the OTP
    is consumed once from the target-isolated capture control plane. Neither
    value is returned in receipts.
    Prod is rejected by ``_require_nonprod_target``.
    """

    _require_nonprod_target(environment, target_name)
    canonical_instance = _canonical_test_data_instance_id(test_data_instance_id)
    canonical_identity_set_id = _canonical_actor_role(identity_set_id)
    canonical_role = _canonical_actor_role(actor_role)
    if actor_index < 0 or actor_index > 999:
        raise ValueError("local acceptance actor index must be between 0 and 999")

    actor_digest = hashlib.sha256(
        f"{target_name}\0{canonical_instance}\0{canonical_role}\0{actor_index}".encode(
            "utf-8"
        )
    ).hexdigest()
    if canonical_identity_set_id == "research-identity" and actor_index == 0:
        research_identity = load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
        )
        phone = research_identity["phone"]
        expected_owner_id = research_identity["accountId"]
    else:
        phone = _test_data_actor_phone(
            target_name=target_name,
            identity_set_id=canonical_identity_set_id,
            actor_index=actor_index,
        )
        expected_owner_id = ""
    _clear_local_otp_send_throttle(target_name=target_name, phone=phone)
    device_id = f"acceptance-{environment}-{actor_digest[:16]}"
    common = {
        "deviceId": device_id,
        "platform": "acceptance",
        "appVersion": "1.0.0",
    }
    send_otp_idempotency_key = hashlib.sha256(
        (
            target_name
            + "/"
            + canonical_instance
            + "/user.acceptance.authenticated_actors/"
            + canonical_role
            + "/user.authentication_challenge.SendOtp/send-otp-"
            + f"{actor_index:03d}"
        ).encode("utf-8")
    ).hexdigest()
    otp = request_local_environment_public_json(
        base_url,
        path="/auth/otp/send",
        method="POST",
        headers={"Idempotency-Key": send_otp_idempotency_key},
        body={
            "phone": phone,
            **common,
            "sourceOperation": "TestDataActorProvision",
        },
        timeout_seconds=timeout_seconds,
    )
    challenge_id = _required_string(otp, "challengeId", "OTP response")
    # Lazy import avoids a module cycle: the capture client loads the target's
    # protected auth material only after this module is fully initialized.
    from .local_sms_provider_debug import read_latest_debug_otp

    protected_otp = read_latest_debug_otp(
        environment=environment,
        target_name=target_name,
        recipient=phone,
        timeout_seconds=timeout_seconds,
    )
    otp_code = protected_otp.code
    login = request_local_environment_public_json(
        base_url,
        path="/auth/login/phone",
        method="POST",
        body={
            "phone": phone,
            "otpCode": otp_code,
            **common,
            "agreementVersion": "2026-06",
            "privacyVersion": "2026-06",
        },
        timeout_seconds=timeout_seconds,
    )
    protected_otp = None
    active_persona = login.get("activePersona")
    if not isinstance(active_persona, dict):
        raise RuntimeError("phone login response missing activePersona")
    session = LocalAcceptanceSession(
        owner_id=_required_string(login, "ownerId", "phone login response"),
        persona_id=_required_string(
            active_persona, "personaId", "phone login activePersona"
        ),
        access_token=_required_string(login, "accessToken", "phone login response"),
        refresh_token=_required_string(
            login, "refreshToken", "phone login response"
        ),
    )
    if expected_owner_id and session.owner_id != expected_owner_id:
        raise RuntimeError(
            "phone login owner does not match managed acceptance identity"
        )
    me = request_local_environment_json(
        base_url,
        path="/me",
        session=session,
        timeout_seconds=timeout_seconds,
    )
    me_owner = str(me.get("ownerId") or me.get("id") or "").strip()
    if me_owner and me_owner != session.owner_id:
        raise RuntimeError("authenticated /me owner does not match phone login")
    return LocalAcceptanceActor(
        role=canonical_role,
        session=session,
        challenge_id=challenge_id,
        account_state=str(login.get("accountState") or "").strip(),
        identity_origin=str(login.get("identityOrigin") or "").strip(),
    )


def open_test_data_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    test_data_instance_id: str,
    actor_role: str,
    actor_index: int,
    timeout_seconds: float = 30.0,
) -> LocalAcceptanceActor:
    """Open an isolated typed test-data actor without exposing legacy identity terms.

    The protected identity-set adapter derives a deterministic internal
    identity scope, while request graphs and receipts use only
    ``testDataInstanceId``.  This adapter can therefore be retired with the
    legacy test-live path without coupling typed capabilities to its schema.
    """

    canonical_instance = str(test_data_instance_id).strip()
    if not canonical_instance or "/" in canonical_instance:
        raise ValueError("testDataInstanceId must be non-empty and slash-free")
    identity_scope = hashlib.sha256(canonical_instance.encode("utf-8")).hexdigest()
    # Bind the protected phone identities to the test-data instance as well as
    # the bearer/session derivation.  Reopening the same instance therefore
    # remains idempotent, while a new CaseResult cannot silently reuse another
    # case's UserAccount or Persona through a fixed pool slot.
    identity_set_id = f"typed-{identity_scope[:40]}"
    materialize_test_data_identity_set(
        environment=environment,
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_count=actor_index + 1,
    )
    return open_local_phone_acceptance_session(
        base_url,
        environment=environment,
        target_name=target_name,
        test_data_instance_id=identity_scope,
        identity_set_id=identity_set_id,
        actor_role=actor_role,
        actor_index=actor_index,
        timeout_seconds=timeout_seconds,
    )


def close_test_data_acceptance_actor(
    base_url: str,
    *,
    actor: LocalAcceptanceActor,
    test_data_instance_id: str,
    timeout_seconds: float = 30.0,
) -> None:
    """Close one isolated test-data account through its public contract.

    This narrow harness helper is for runtime preflights that exercise the real
    OTP path outside a full ``TestDataSession``. Business acceptance cases use
    the User Provider, which records the same operation in its receipt journal.
    """

    canonical_instance = str(test_data_instance_id).strip()
    if not canonical_instance or "/" in canonical_instance:
        raise ValueError("testDataInstanceId must be non-empty and slash-free")
    # Lazy import avoids the local_environment_auth -> operations module cycle.
    from .test_data.operations import ContractOperationCatalog

    operation = ContractOperationCatalog().require(
        "user.user_account.CloseAccount"
    )
    close_request_id = hashlib.sha256(
        (canonical_instance + "\0close-account").encode("utf-8")
    ).hexdigest()[:32]
    request_local_environment_json(
        base_url,
        path=operation.path(),
        session=actor.session,
        method=operation.method,
        body={"clientRequestId": close_request_id},
        # CloseAccount is an idempotent write command.  The operation guard
        # enforces the canonical header before the handler can consume the
        # equivalent body replay identity.
        headers={"Idempotency-Key": close_request_id},
        timeout_seconds=timeout_seconds,
    )



def _clear_local_otp_send_throttle(*, target_name: str, phone: str) -> None:
    """Best-effort clear of local Redis OTP cooldown/quota for retained restore.

    Retained candidate-bound identity already proved account creation. Health and
    debug-preflight only need one live session; leftover otp:resend / otp:quota
    keys must not force GATE_BLOCK via HTTP 429.
    """

    if not phone.startswith("+") or not phone[1:].isdigit():
        return
    try:
        from .environment_topology import get_target, load_environment_topology
        from .port_manifest import load_port_manifest, profile_ports

        target = get_target(load_environment_topology(), target_name)
        profile = str(target.get("portProfile") or "").strip()
        if not profile:
            return
        redis_port = profile_ports(load_port_manifest(), profile).get("redis")
        if not isinstance(redis_port, int) or redis_port <= 0:
            return
        phone_digest = hashlib.sha256(phone.strip().encode("utf-8")).hexdigest()
        subprocess.run(
            [
                "redis-cli",
                "-p",
                str(redis_port),
                "DEL",
                f"otp:resend:{phone_digest}",
                f"otp:quota:{phone_digest}",
                f"otp:quota-deadline:{phone_digest}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        return



def materialize_test_data_identity_set(
    *,
    environment: str,
    target_name: str,
    identity_set_id: str,
    actor_count: int,
    phone_profile: str = "nonroutable",
) -> Path:
    """Materialize protected OTP inputs for one isolated test-data identity set.

    These values are transport credentials for the local SMS capture Provider,
    not reusable business accounts. The file is target-scoped, mode 0600 and
    contains no access or refresh token.
    """

    _require_nonprod_target(environment, target_name)
    canonical_identity_set_id = _canonical_actor_role(identity_set_id)
    if phone_profile not in _TEST_DATA_PHONE_PROFILES:
        raise ValueError("unsupported test-data phone profile")
    if (
        isinstance(actor_count, bool)
        or not isinstance(actor_count, int)
        or actor_count <= 0
        or actor_count > 1000
    ):
        raise ValueError("test-data actor count must be within 1..1000")

    secret_root, path = _test_data_identity_set_path(target_name)
    secret_root.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_root, 0o700)
    lock_path = secret_root / _TEST_DATA_IDENTITY_SET_LOCK_NAME
    lock_flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        lock_flags |= os.O_NOFOLLOW
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    try:
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise RuntimeError("test-data identity set lock is not regular")
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        existing_identity: tuple[int, int] | None = None
        if path.exists() or path.is_symlink():
            payload, existing_identity = _read_test_data_identity_set(
                path,
                target_name=target_name,
            )
        else:
            payload = {
                "schema": _TEST_DATA_IDENTITY_SET_SCHEMA,
                "target": target_name,
                "identitySetPhones": {},
            }
        identity_sets = payload["identitySetPhones"]
        target_slot = {
            "alpha-local": "1",
            "beta-local": "2",
            "gamma-local": "3",
        }[target_name]
        identity_set_slot = int(
            hashlib.sha256(
                f"{target_name}\0{canonical_identity_set_id}".encode("utf-8")
            ).hexdigest()[:16],
            16,
        )
        existing_phones = identity_sets.get(canonical_identity_set_id)
        phone_count = max(
            actor_count,
            len(existing_phones) if isinstance(existing_phones, list) else 0,
        )
        if phone_profile == "mainland_ui":
            canonical_phones = [
                f"+86199{target_slot}{identity_set_slot % 10_000:04d}{index:03d}"
                for index in range(phone_count)
            ]
        else:
            canonical_phones = [
                f"+999{target_slot}{identity_set_slot % 100_000_000:08d}{index:03d}"
                for index in range(phone_count)
            ]
        if existing_phones is not None:
            phones = existing_phones
            if phones != canonical_phones[: len(phones)]:
                raise RuntimeError(
                    "test-data identity set is incomplete or does not match "
                    f"the canonical prefix for {canonical_identity_set_id}"
                )
            if len(phones) >= actor_count:
                return path
        updated = {
            "schema": _TEST_DATA_IDENTITY_SET_SCHEMA,
            "target": target_name,
            "identitySetPhones": {
                **identity_sets,
                canonical_identity_set_id: canonical_phones[:actor_count],
            },
        }
        _validate_test_data_identity_set(
            updated,
            target_name=target_name,
        )
        _atomic_write_test_data_identity_set(
            path,
            updated,
            existing_identity=existing_identity,
        )
        return path
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def materialize_local_capture_ui_acceptance_phone(
    *,
    environment: str,
    target_name: str,
    actor_index: int = 0,
) -> str:
    """Return one protected +86 identity for local-capture App UAT only.

    The phone shape matches the App's fixed +86 input, while the selected
    Provider remains the non-promotable local capture substitute.  The value
    is stored only in the target-scoped mode-0600 identity pool.
    """

    if (
        isinstance(actor_index, bool)
        or not isinstance(actor_index, int)
        or actor_index < 0
        or actor_index >= 1000
    ):
        raise ValueError("local-capture UI actor index must be within 0..999")
    identity_set_id = "provider-ui-sms"
    materialize_test_data_identity_set(
        environment=environment,
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_count=actor_index + 1,
        phone_profile="mainland_ui",
    )
    return _test_data_actor_phone(
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_index=actor_index,
    )


def _test_data_identity_set_path(
    target_name: str,
) -> tuple[Path, Path]:
    secret_root = deployment_target_path(target_name, "secrets").resolve()
    raw_path = os.environ.get(_TEST_DATA_IDENTITY_SET_PATH_ENV, "").strip()
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise RuntimeError("test-data identity set path must be absolute")
        path = path.parent.resolve() / path.name
    else:
        path = secret_root / _TEST_DATA_IDENTITY_SET_NAME
    try:
        path.parent.resolve().relative_to(secret_root)
    except ValueError as exc:
        raise RuntimeError(
            "test-data identity set parent must remain under the target secret root"
        ) from exc
    try:
        path.relative_to(secret_root)
    except ValueError as exc:
        raise RuntimeError(
            "test-data identity set must be target-scoped under the deploy secret root"
        ) from exc
    return secret_root, path


def _validate_test_data_identity_set(
    payload: object,
    *,
    target_name: str,
) -> dict[str, list[str]]:
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != _TEST_DATA_IDENTITY_SET_SCHEMA
        or payload.get("target") != target_name
        or set(payload) != {"schema", "target", "identitySetPhones"}
    ):
        raise RuntimeError("test-data identity set identity mismatch")
    raw_identity_sets = payload.get("identitySetPhones")
    if not isinstance(raw_identity_sets, dict):
        raise RuntimeError("test-data identity sets are invalid")
    identity_sets: dict[str, list[str]] = {}
    all_phones: list[str] = []
    for raw_identity_set_id, raw_phones in raw_identity_sets.items():
        identity_set_id = _canonical_actor_role(str(raw_identity_set_id))
        if identity_set_id != raw_identity_set_id or not isinstance(raw_phones, list):
            raise RuntimeError("test-data identity set entry is invalid")
        phones = [str(value).strip() for value in raw_phones]
        if any(
            re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) is None
            for phone in phones
        ):
            raise RuntimeError(
                "test-data identity set contains invalid E.164 phone"
            )
        identity_sets[identity_set_id] = phones
        all_phones.extend(phones)
    if len(all_phones) != len(set(all_phones)):
        raise RuntimeError("test-data identity set contains duplicate phones")
    return identity_sets


def _read_test_data_identity_set(
    path: Path,
    *,
    target_name: str,
) -> tuple[dict[str, Any], tuple[int, int]]:
    if path.is_symlink():
        raise RuntimeError("test-data identity set cannot be a symlink")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("test-data identity set cannot be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("test-data identity set must use mode 0600")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "test-data identity set is invalid JSON"
                ) from exc
        identity_sets = _validate_test_data_identity_set(
            payload,
            target_name=target_name,
        )
        payload["identitySetPhones"] = identity_sets
        return payload, (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(fd)


def _atomic_write_test_data_identity_set(
    path: Path,
    payload: dict[str, Any],
    *,
    existing_identity: tuple[int, int] | None,
) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            destination_stat = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            destination_identity = None
        else:
            if not stat.S_ISREG(destination_stat.st_mode):
                raise RuntimeError("test-data identity set destination is unsafe")
            destination_identity = (
                destination_stat.st_dev,
                destination_stat.st_ino,
            )
        if destination_identity != existing_identity:
            raise RuntimeError("test-data identity set changed during materialization")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _test_data_actor_phone(
    *,
    target_name: str,
    identity_set_id: str,
    actor_index: int,
) -> str:
    _secret_root, path = _test_data_identity_set_path(target_name)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(
            "GATE_BLOCK: test-data identity set is missing under the target "
            f"secret root (set {_TEST_DATA_IDENTITY_SET_PATH_ENV} or materialize "
            "secrets/test-data-identity-set.json)"
        )
    payload, _identity = _read_test_data_identity_set(
        path,
        target_name=target_name,
    )
    identity_sets = payload["identitySetPhones"]
    phones = identity_sets.get(identity_set_id)
    if not isinstance(phones, list) or actor_index >= len(phones):
        raise RuntimeError(
            f"test-data identity set is incomplete for {identity_set_id}"
        )
    phone = str(phones[actor_index]).strip()
    return phone


def request_local_environment_public_json(
    base_url: str,
    *,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Call a public local-environment JSON endpoint without forged identity."""

    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request_headers = {"Accept": "application/json"}
    for name, value in (headers or {}).items():
        if name.lower() in {"authorization", "x-client-user-id"}:
            raise ValueError("public local environment request cannot inject identity")
        request_headers[name] = value
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    status, response = _trusted_json_request(
        method=method,
        url=base_url.rstrip("/") + normalized_path,
        body=payload,
        headers=request_headers,
        timeout_seconds=timeout_seconds,
    )
    if status < 200 or status >= 300:
        raise LocalEnvironmentHTTPError(
            method=method, path=normalized_path, status=status
        )
    return response


def _trusted_json_request(
    *,
    method: str,
    url: str,
    body: bytes | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    target_host = urlparse(url).hostname
    if not target_host:
        raise ValueError("local environment request URL has no hostname")
    target_name = target_for_hostname(target_host)
    if target_name is None:
        raise ValueError("local environment request URL is not a canonical local target")
    ca_file = root_certificate_path(target_name)
    if not ca_file.is_file() or ca_file.is_symlink():
        raise RuntimeError("local environment request root certificate is unavailable")
    context = ssl.create_default_context(cafile=str(ca_file))
    req = request.Request(url, data=body, headers=headers, method=method)
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=context),
    )
    try:
        with opener.open(
            req,
            timeout=max(1.0, timeout_seconds),
        ) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"local environment request transport failed: {type(exc).__name__}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"local environment request {method} returned non-JSON HTTP {status}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"local environment request {method} returned non-object JSON HTTP {status}")
    return status, parsed


def _require_local_environment(environment: str, target_name: str) -> None:
    expected_target = _LOCAL_TARGETS.get(environment)
    if expected_target != target_name:
        raise ValueError(
            f"unsupported local environment target: environment={environment} target={target_name}"
        )


def _require_nonprod_target(environment: str, target_name: str) -> None:
    _require_local_environment(environment, target_name)
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("nonprod acceptance identity is forbidden for Prod")


def _canonical_test_data_instance_id(value: str) -> str:
    instance_id = value.strip()
    if len(instance_id) != 64 or any(
        character not in "0123456789abcdef" for character in instance_id
    ):
        raise ValueError(
            "testDataInstanceId transport scope must be a lowercase SHA-256 hex digest"
        )
    return instance_id


def _canonical_actor_role(value: str) -> str:
    role = value.strip()
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not role or len(role) > 64 or any(character not in allowed for character in role):
        raise ValueError("local acceptance actor role is invalid")
    return role


def _required_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} missing required {field}")
    return value.strip()


def _load_or_create_secrets(path: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_file():
        _require_mode(path, 0o600)
        values = _read_secret_file(path)
        missing = [key for key in _SECRET_KEYS if not values.get(key)]
        generated_keys = {
            "otp_code_ref_key_b64",
            "push_token_encryption_key_b64",
            "research_identity_attestation_key_b64",
            "account_closure_subject_hmac_secret",
            "rtc_media_api_key",
            "rtc_media_api_secret",
            "sms_substitute_provider_token",
            "sms_substitute_operator_token",
            "provider_substitute_operator_token",
            "sms_substitute_capture_key_b64",
        }
        if missing and set(missing).issubset(generated_keys):
            with path.open("a", encoding="utf-8") as handle:
                for key in missing:
                    if key == "account_closure_subject_hmac_secret":
                        values[key] = secrets.token_urlsafe(48)
                    elif key in {
                        "rtc_media_api_key",
                        "rtc_media_api_secret",
                        "sms_substitute_provider_token",
                        "sms_substitute_operator_token",
                        "provider_substitute_operator_token",
                    }:
                        values[key] = secrets.token_urlsafe(32)
                    else:
                        values[key] = base64.b64encode(
                            secrets.token_bytes(32)
                        ).decode("ascii")
                    handle.write(f"{key}={values[key]}\n")
                handle.flush()
                os.fsync(handle.fileno())
            return values
        if missing:
            raise RuntimeError("local environment auth secret file is incomplete: " + ", ".join(missing))
        return values
    if path.exists():
        raise RuntimeError(f"local environment auth secret path is not a file: {path}")
    values = {
        "jwt_secret": secrets.token_urlsafe(48),
        "device_ticket_secret": secrets.token_urlsafe(48),
        "otp_code_ref_key_b64": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        "push_token_encryption_key_b64": base64.b64encode(
            secrets.token_bytes(32)
        ).decode("ascii"),
        "research_identity_attestation_key_b64": base64.b64encode(
            secrets.token_bytes(32)
        ).decode("ascii"),
        "account_closure_subject_hmac_secret": secrets.token_urlsafe(48),
        "rtc_media_api_key": secrets.token_urlsafe(32),
        "rtc_media_api_secret": secrets.token_urlsafe(32),
        "sms_substitute_provider_token": secrets.token_urlsafe(32),
        "sms_substitute_operator_token": secrets.token_urlsafe(32),
        "provider_substitute_operator_token": secrets.token_urlsafe(32),
        "sms_substitute_capture_key_b64": base64.b64encode(
            secrets.token_bytes(32)
        ).decode("ascii"),
    }
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key in _SECRET_KEYS:
                handle.write(f"{key}={values[key]}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return values


def _read_secret_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or not value:
            raise RuntimeError(f"invalid local environment auth secret file: {path}")
        values[key] = value
    return values


def _require_mode(path: Path, expected: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"local environment auth secret file must use mode {expected:04o}: {path}")


def _print_shell_environment(environment: str, target_name: str) -> None:
    auth = prepare_local_environment_auth(environment, target_name)
    for key, value in sorted(auth.environment.items()):
        print(f"export {key}={shlex.quote(value)}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--shell":
        _print_shell_environment(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(
            "usage: python -m quwoquan_ops.cli.lib.local_environment_auth "
            "--shell <alpha|beta|gamma> <alpha-local|beta-local|gamma-local>"
        )
