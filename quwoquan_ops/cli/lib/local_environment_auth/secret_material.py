"""target 级 auth 秘密材料的创建、加载与 runtime 环境投影（逐字搬移）。

``deployment_target_path`` / ``deployment_target_path_in_work_root`` 与
``materialize_local_research_identity_binding`` /
``load_local_research_identity_binding`` 是测试 patch 锚点或跨模块依赖，
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import shlex
from pathlib import Path

import quwoquan_ops.cli.lib.local_environment_auth as _pkg

from .constants import _SECRET_KEYS
from .guards import _require_local_environment, _require_mode
from .models import LocalEnvironmentAuth


def prepare_local_environment_auth(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> LocalEnvironmentAuth:
    """Create target-isolated auth material in the external deploy workspace."""
    _require_local_environment(environment, target_name)
    secret_path = _pkg._local_environment_secret_path(
        target_name,
        deployment_work_root=deployment_work_root,
    )
    values = _load_or_create_secrets(secret_path)
    research_identity = (
        _pkg.materialize_local_research_identity_binding(
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
    secret_path = _pkg._local_environment_secret_path(
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
        _pkg.load_local_research_identity_binding(
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
        _pkg.deployment_target_path(target_name, "secrets", "auth.env")
        if deployment_work_root is None
        else _pkg.deployment_target_path_in_work_root(
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


def _print_shell_environment(environment: str, target_name: str) -> None:
    auth = _pkg.prepare_local_environment_auth(environment, target_name)
    for key, value in sorted(auth.environment.items()):
        print(f"export {key}={shlex.quote(value)}")
