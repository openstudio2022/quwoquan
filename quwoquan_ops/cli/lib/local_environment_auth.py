from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


_SECRET_KEYS = (
    "jwt_secret",
    "device_ticket_secret",
    "otp_code_ref_key_b64",
    "push_token_encryption_key_b64",
    "account_closure_subject_hmac_secret",
    "rtc_media_api_key",
    "rtc_media_api_secret",
    "sms_substitute_provider_token",
    "sms_substitute_operator_token",
    "sms_substitute_capture_key_b64",
)
_LOCAL_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    # prod-sim 使用 production 配置投影，但其认证材料仍限定在本机部署目录。
    "prod": "prod-sim",
}
_NONPROD_IDENTITY_POOL_SCHEMA = "qwq.nonprod_acceptance_identity_pool"
_NONPROD_IDENTITY_POOL_PATH_ENV = "QWQ_NONPROD_ACCEPTANCE_IDENTITY_POOL"
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
    return _local_environment_auth(environment, secret_path, values)


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
    return _local_environment_auth(environment, secret_path, values)


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
) -> LocalEnvironmentAuth:
    key_version = f"local-{environment}-k1"
    return LocalEnvironmentAuth(
        environment={
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
            "SMS_SUBSTITUTE_CAPTURE_KEY_B64": values[
                "sms_substitute_capture_key_b64"
            ],
        },
        secret_path=secret_path,
    )


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
    dataset_epoch: str,
    dataset_id: str,
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
    canonical_epoch = _canonical_dataset_epoch(dataset_epoch)
    canonical_dataset_id = _canonical_actor_role(dataset_id)
    canonical_role = _canonical_actor_role(actor_role)
    if actor_index < 0 or actor_index > 999:
        raise ValueError("local acceptance actor index must be between 0 and 999")

    actor_digest = hashlib.sha256(
        f"{target_name}\0{canonical_epoch}\0{canonical_role}\0{actor_index}".encode(
            "utf-8"
        )
    ).hexdigest()
    phone = _nonprod_acceptance_phone(
        target_name=target_name,
        dataset_id=canonical_dataset_id,
        actor_index=actor_index,
    )
    device_id = f"acceptance-{environment}-{actor_digest[:16]}"
    common = {
        "deviceId": device_id,
        "platform": "acceptance",
        "appVersion": "1.0.0",
    }
    otp = request_local_environment_public_json(
        base_url,
        path="/auth/otp/send",
        method="POST",
        body={
            "phone": phone,
            **common,
            "sourceOperation": "NonprodAcceptanceProvision",
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


def open_reference_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    actor_index: int = 0,
    timeout_seconds: float = 30.0,
) -> LocalAcceptanceSession:
    """Restore an active candidate-bound acceptance account via public auth.

    This is the only supported business-UAT session source. It fails closed
    when no active candidate or matching identity receipt exists.
    """

    _require_nonprod_target(environment, target_name)
    active = active_deployment_candidate(target_name)
    if not isinstance(active, dict):
        raise RuntimeError("GATE_BLOCK: active immutable candidate is required")
    baseline_id = str(active.get("baselineId") or "").strip()
    candidate_manifest_path = Path(str(active.get("candidateDir") or "")) / "manifest.json"
    try:
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("active candidate manifest is unreadable") from exc
    if (
        not isinstance(candidate_manifest, dict)
        or candidate_manifest.get("baselineId") != baseline_id
    ):
        raise RuntimeError("active candidate manifest identity mismatch")
    package_digest = str(candidate_manifest.get("packageDigest") or "").strip()
    if not package_digest:
        raise RuntimeError("active candidate manifest packageDigest is missing")
    receipt_root = env_runs_root(environment) / "nonprod-data"
    matches: list[dict[str, Any]] = []
    for path in sorted(receipt_root.glob("*/nonprod_reference_identity.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema") == "qwq.nonprod_acceptance_dataset_receipt"
            and payload.get("target") == target_name
            and payload.get("baselineId") == baseline_id
            and payload.get("packageDigest") == package_digest
            and payload.get("datasetId") == "nonprod_reference_identity"
            and payload.get("status") == "passed"
            and payload.get("cleanupState") == "retained"
        ):
            matches.append(payload)
    if len(matches) != 1:
        raise RuntimeError(
            "GATE_BLOCK: exactly one active candidate-bound identity receipt is required"
        )
    receipt = matches[0]
    expires_at_raw = str(receipt.get("expiresAt") or "").strip()
    try:
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("active identity receipt expiresAt is invalid") from exc
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise RuntimeError("GATE_BLOCK: active identity receipt is expired")
    epoch = str(receipt.get("datasetEpoch") or "").strip()
    actors = receipt.get("actorReceiptRefs")
    if not isinstance(actors, list) or actor_index < 0 or actor_index >= len(actors):
        raise RuntimeError("active identity receipt actor closure is incomplete")
    row = actors[actor_index]
    if not isinstance(row, dict):
        raise RuntimeError("active identity receipt actor row is invalid")
    actor = open_local_phone_acceptance_session(
        base_url,
        environment=environment,
        target_name=target_name,
        dataset_epoch=epoch,
        dataset_id="nonprod_reference_identity",
        actor_role=str(row.get("role") or ""),
        actor_index=actor_index,
        timeout_seconds=timeout_seconds,
    )
    if (
        actor.session.owner_id != row.get("ownerId")
        or actor.account_state != row.get("accountState")
        or actor.identity_origin != row.get("identityOrigin")
    ):
        raise RuntimeError("active identity receipt live account drift")
    return actor.session


def _nonprod_acceptance_phone(
    *,
    target_name: str,
    dataset_id: str,
    actor_index: int,
) -> str:
    raw_path = os.environ.get(_NONPROD_IDENTITY_POOL_PATH_ENV, "").strip()
    if not raw_path:
        raise RuntimeError(
            f"GATE_BLOCK: {_NONPROD_IDENTITY_POOL_PATH_ENV} is required"
        )
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise RuntimeError("nonprod acceptance identity pool path must be absolute")
    path = path.resolve()
    secret_root = deployment_target_path(target_name, "secrets").resolve()
    try:
        path.relative_to(secret_root)
    except ValueError as exc:
        raise RuntimeError(
            "nonprod acceptance identity pool must be target-scoped under the deploy secret root"
        ) from exc
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("nonprod acceptance identity pool must be a regular file")
    _require_mode(path, 0o600)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("nonprod acceptance identity pool is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != _NONPROD_IDENTITY_POOL_SCHEMA
        or payload.get("target") != target_name
        or set(payload) != {"schema", "target", "datasetPhones"}
    ):
        raise RuntimeError("nonprod acceptance identity pool identity mismatch")
    datasets = payload.get("datasetPhones")
    phones = datasets.get(dataset_id) if isinstance(datasets, dict) else None
    if not isinstance(phones, list) or actor_index >= len(phones):
        raise RuntimeError(
            f"nonprod acceptance identity pool is incomplete for {dataset_id}"
        )
    phone = str(phones[actor_index]).strip()
    if (
        not phone.startswith("+")
        or len(phone) < 8
        or len(phone) > 18
        or not phone[1:].isdigit()
    ):
        raise RuntimeError("nonprod acceptance identity pool contains invalid E.164 phone")
    all_phones = [
        str(value).strip()
        for values in datasets.values()
        if isinstance(values, list)
        for value in values
    ]
    if len(all_phones) != len(set(all_phones)):
        raise RuntimeError("nonprod acceptance identity pool contains duplicate phones")
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
    req = request.Request(url, data=body, headers=headers, method=method)
    opener = request.build_opener(
        request.ProxyHandler({}),
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


def _canonical_dataset_epoch(value: str) -> str:
    epoch = value.strip()
    if len(epoch) != 64 or any(character not in "0123456789abcdef" for character in epoch):
        raise ValueError("dataset epoch must be a lowercase sha256 hex digest")
    return epoch


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
            "account_closure_subject_hmac_secret",
            "rtc_media_api_key",
            "rtc_media_api_secret",
            "sms_substitute_provider_token",
            "sms_substitute_operator_token",
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
        "account_closure_subject_hmac_secret": secrets.token_urlsafe(48),
        "rtc_media_api_key": secrets.token_urlsafe(32),
        "rtc_media_api_secret": secrets.token_urlsafe(32),
        "sms_substitute_provider_token": secrets.token_urlsafe(32),
        "sms_substitute_operator_token": secrets.token_urlsafe(32),
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
