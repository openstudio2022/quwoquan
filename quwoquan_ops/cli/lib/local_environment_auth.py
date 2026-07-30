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
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from .output_paths import (
    deployment_target_path,
    deployment_target_path_in_work_root,
)


_SECRET_KEYS = (
    "jwt_secret",
    "device_ticket_secret",
    "otp_code_ref_key_b64",
    "push_token_encryption_key_b64",
    "account_closure_subject_hmac_secret",
)
_LOCAL_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    # prod-sim 使用 production 配置投影，但其认证材料仍限定在本机部署目录。
    "prod": "prod-sim",
}
_REPORT_ACCOUNT_BACKFILL_KIND = "content.reporter_account_backfill"


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
class LocalEnvironmentHTTPError(RuntimeError):
    """Redacted local-environment HTTP failure with a machine-readable status."""

    method: str
    path: str
    status: int

    def __str__(self) -> str:
        return f"local environment request {self.method} {self.path} failed with HTTP {self.status}"


def resolve_running_local_deployment_work_root(target_name: str) -> Path | None:
    """Resolve the non-secret workspace mounted by a running local user service.

    A local stack may intentionally use a workspace other than the caller's
    default ``QWQ_DEPLOY_WORK_ROOT``. The mounted config root is the runtime
    truth for the JWT material used by that stack. This helper returns only the
    validated parent workspace and never reads or exposes a secret value.
    """

    normalized_target = str(target_name).strip()
    if normalized_target not in set(_LOCAL_TARGETS.values()):
        raise ValueError(f"unsupported local environment target: {target_name}")

    for engine in ("docker", "podman"):
        for container_name in (
            "quwoquan_service-user-service-1",
            "quwoquan_service_user-service_1",
        ):
            try:
                result = subprocess.run(
                    [engine, "inspect", container_name],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=3.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode != 0:
                continue
            try:
                inspected = json.loads(result.stdout)
            except json.JSONDecodeError:
                continue
            if not isinstance(inspected, list) or not inspected:
                continue
            container = inspected[0]
            if not isinstance(container, dict):
                continue
            mounts = container.get("Mounts")
            if not isinstance(mounts, list):
                continue
            for mount in mounts:
                if not isinstance(mount, dict):
                    continue
                if mount.get("Destination") != "/etc/qwq-config":
                    continue
                source = mount.get("Source")
                if not isinstance(source, str) or not source.strip():
                    continue
                config_root = Path(source).expanduser().resolve()
                if (
                    config_root.name != "config-root"
                    or config_root.parent.name != "rendered"
                    or config_root.parent.parent.name != normalized_target
                ):
                    continue
                work_root = config_root.parents[2]
                try:
                    deployment_target_path_in_work_root(
                        work_root,
                        normalized_target,
                        "secrets",
                        "auth.env",
                    )
                except ValueError:
                    continue
                return work_root
    return None


def prepare_local_environment_auth(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> LocalEnvironmentAuth:
    """Create target-isolated auth material in the external deploy workspace."""
    _require_local_environment(environment, target_name)
    secret_path = (
        deployment_target_path(target_name, "secrets", "auth.env")
        if deployment_work_root is None
        else deployment_target_path_in_work_root(
            deployment_work_root,
            target_name,
            "secrets",
            "auth.env",
        )
    )
    values = _load_or_create_secrets(secret_path)
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
        },
        secret_path=secret_path,
    )


def open_local_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    profile: str = "",
    subject: str | None = None,
    timeout_seconds: float = 30.0,
    deployment_work_root: str | Path | None = None,
) -> LocalAcceptanceSession:
    """Issue a local-only session with the user-service canonical JWT signer.

    The seeded acceptance identity is declared by the shared acceptance fixture. The
    signing secret and resulting bearer token stay in subprocess memory and are
    never placed in argv, reports, or logs.
    """

    _require_local_environment(environment, target_name)
    normalized_base = base_url.rstrip("/") + "/"
    parsed = urlparse(normalized_base)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("local environment auth base URL must be an absolute HTTPS URL")
    if subject is None:
        owner_id, persona_id = _local_acceptance_principal(
            environment,
            target_name,
        )
    else:
        canonical_subject = subject.strip()
        allowed = frozenset(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        )
        if (
            not canonical_subject
            or len(canonical_subject) > 128
            or any(character not in allowed for character in canonical_subject)
        ):
            raise ValueError("local environment acceptance subject is invalid")
        owner_id = canonical_subject
        persona_id = canonical_subject
    profile_value = _canonical_acceptance_profile(profile)
    auth = prepare_local_environment_auth(
        environment,
        target_name,
        deployment_work_root=deployment_work_root,
    )
    process_env = os.environ.copy()
    process_env.update(auth.environment)
    process_env.update(
        {
            "APP_ENV": environment,
            "QWQ_LOCAL_ACCEPTANCE_TARGET": target_name,
            "QWQ_ACCEPTANCE_OWNER_ID": owner_id,
            "QWQ_ACCEPTANCE_PERSONA_ID": persona_id,
            "QWQ_ACCEPTANCE_PROFILE": profile_value,
        }
    )
    result = subprocess.run(
        ["go", "run", "./services/user-service/cmd/acceptance-session"],
        cwd=Path(__file__).resolve().parents[3] / "quwoquan_service",
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1.0, timeout_seconds),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("local environment acceptance token issuer failed")
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("local environment acceptance token issuer returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise RuntimeError("local environment acceptance token issuer returned non-object JSON")
    return LocalAcceptanceSession(
        owner_id=_required_string(body, "ownerId", "acceptance token response"),
        persona_id=_required_string(body, "personaId", "acceptance token response"),
        access_token=_required_string(body, "accessToken", "acceptance token response"),
    )


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


def _required_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} missing required {field}")
    return value.strip()


def _local_acceptance_principal(
    environment: str,
    target_name: str,
) -> tuple[str, str]:
    """Return a technical UAT identity independent of business release data."""

    digest = hashlib.sha256(
        f"{environment}\0{target_name}".encode("utf-8")
    ).hexdigest()[:16]
    prefix = f"uat_{environment}_{digest}"
    return f"{prefix}_owner", f"{prefix}_persona"


def _canonical_acceptance_profile(value: str) -> str:
    profile = value.strip()
    allowed = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
    )
    if any(character not in allowed for character in profile):
        raise ValueError("local environment acceptance profile is invalid")
    return profile


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
        }
        if missing and set(missing).issubset(generated_keys):
            with path.open("a", encoding="utf-8") as handle:
                for key in missing:
                    if key == "account_closure_subject_hmac_secret":
                        values[key] = secrets.token_urlsafe(48)
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


def write_local_report_account_backfill(
    environment: str,
    target_name: str,
    output_path: Path,
    *,
    include_acceptance_principal: bool = True,
) -> dict[str, object]:
    """Create a target-local, reviewed Report ownership mapping.

    The only populated local mapping is derived from the canonical acceptance
    fixture. Production deployment never synthesizes a mapping: unresolved
    ownerless rows stay fail-closed until an operator provides a verified export.
    """

    _require_local_environment(environment, target_name)
    entries: list[dict[str, str]] = []
    if include_acceptance_principal:
        owner_id, persona_id = _local_acceptance_principal(
            environment,
            target_name,
        )
        entries.append({"reporterId": persona_id, "accountId": owner_id})
    payload: dict[str, object] = {
        "kind": _REPORT_ACCOUNT_BACKFILL_KIND,
        "entries": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(output_path)
    return payload


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--shell":
        _print_shell_environment(sys.argv[2], sys.argv[3])
    elif (
        len(sys.argv) in {5, 6}
        and sys.argv[1] == "--write-report-account-backfill"
        and (len(sys.argv) == 5 or sys.argv[5] == "--empty")
    ):
        result = write_local_report_account_backfill(
            sys.argv[2],
            sys.argv[3],
            Path(sys.argv[4]),
            include_acceptance_principal=len(sys.argv) == 5,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "entryCount": len(result["entries"]),
                },
                ensure_ascii=False,
            )
        )
    else:
        raise SystemExit(
            "usage: python -m quwoquan_ops.cli.lib.local_environment_auth "
            "--shell <alpha|beta|gamma> <alpha-local|beta-local|gamma-local>\n"
            "   or: python -m quwoquan_ops.cli.lib.local_environment_auth "
            "--write-report-account-backfill <alpha|beta|gamma> "
            "<alpha-local|beta-local|gamma-local> <output-path> [--empty]"
        )
