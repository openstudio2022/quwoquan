from __future__ import annotations

import base64
import ipaddress
import json
import os
import secrets
import shlex
import socket
import ssl
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urljoin, urlparse

from .output_paths import deployment_work_root


_SECRET_KEYS = ("jwt_secret", "device_ticket_secret", "otp_code_ref_key_b64")


@dataclass(frozen=True)
class LocalGammaAuth:
    environment: dict[str, str]
    secret_path: Path


@dataclass(frozen=True)
class LocalGammaAcceptanceSession:
    """Ephemeral bearer session for the seeded local-Gamma acceptance persona."""

    owner_id: str
    persona_id: str
    access_token: str = field(repr=False)
    def authorization_header(self) -> str:
        return "Bearer " + self.access_token


@dataclass(frozen=True)
class LocalGammaHTTPError(RuntimeError):
    """Redacted local-Gamma HTTP failure with a machine-readable status."""

    method: str
    path: str
    status: int

    def __str__(self) -> str:
        return f"local Gamma request {self.method} {self.path} failed with HTTP {self.status}"


def prepare_local_gamma_auth() -> LocalGammaAuth:
    """Create stable local Gamma auth material in the external deploy workspace."""
    secret_path = deployment_work_root("gamma-local") / "secrets" / "auth.env"
    values = _load_or_create_secrets(secret_path)
    return LocalGammaAuth(
        environment={
            "AUTH_JWT_SECRET": values["jwt_secret"],
            "AUTH_JWT_ISSUER": "quwoquan.gamma.local",
            "AUTH_JWT_AUDIENCE": "quwoquan-app",
            "AUTH_JWT_TOKEN_VERSION": "1",
            "AUTH_DEVICE_TICKET_SECRET": values["device_ticket_secret"],
            "AUTH_DEVICE_TICKET_ISSUER": "quwoquan.gamma.local.device",
            "AUTH_DEVICE_TICKET_AUDIENCE": "quwoquan-app-device",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION": "1",
            "OTP_CODE_REF_ACTIVE_KEY_VERSION": "local-gamma-k1",
            "OTP_CODE_REF_KEYS_JSON": json.dumps(
                {"local-gamma-k1": values["otp_code_ref_key_b64"]},
                separators=(",", ":"),
            ),
        },
        secret_path=secret_path,
    )


def open_local_gamma_acceptance_session(
    base_url: str,
    *,
    subject: str | None = None,
    resolve_host: str = "127.0.0.1",
    timeout_seconds: float = 30.0,
) -> LocalGammaAcceptanceSession:
    """Issue a local-only session with the user-service canonical JWT signer.

    The seeded acceptance identity is declared by the Gamma fixture manifest. The
    signing secret and resulting bearer token stay in subprocess memory and are
    never placed in argv, reports, or logs.
    """

    _require_loopback(resolve_host)
    normalized_base = base_url.rstrip("/") + "/"
    parsed = urlparse(normalized_base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("local Gamma auth base URL must be an absolute HTTP(S) URL")
    if subject is None:
        owner_id, persona_id = _load_acceptance_principal()
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
            raise ValueError("local Gamma acceptance subject is invalid")
        owner_id = canonical_subject
        persona_id = canonical_subject
    auth = prepare_local_gamma_auth()
    process_env = os.environ.copy()
    process_env.update(auth.environment)
    process_env.update(
        {
            "APP_ENV": "gamma",
            "QWQ_LOCAL_ACCEPTANCE_TARGET": "gamma-local",
            "QWQ_ACCEPTANCE_OWNER_ID": owner_id,
            "QWQ_ACCEPTANCE_PERSONA_ID": persona_id,
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
        raise RuntimeError("local Gamma acceptance token issuer failed")
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("local Gamma acceptance token issuer returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise RuntimeError("local Gamma acceptance token issuer returned non-object JSON")
    return LocalGammaAcceptanceSession(
        owner_id=_required_string(body, "ownerId", "acceptance token response"),
        persona_id=_required_string(body, "personaId", "acceptance token response"),
        access_token=_required_string(body, "accessToken", "acceptance token response"),
    )


def request_local_gamma_json(
    base_url: str,
    *,
    path: str,
    session: LocalGammaAcceptanceSession,
    resolve_host: str = "127.0.0.1",
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Call a local Gamma JSON endpoint using a bearer session without logging it."""

    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    headers = {
        "Accept": "application/json",
        "Authorization": session.authorization_header(),
        "X-Client-Session-Id": "local-gamma-" + session.owner_id[-12:],
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    status, response = _loopback_json_request(
        method=method,
        url=urljoin(base_url.rstrip("/") + "/", normalized_path.lstrip("/")),
        resolve_host=resolve_host,
        body=payload,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    if status < 200 or status >= 300:
        raise LocalGammaHTTPError(method=method, path=normalized_path, status=status)
    return response


def _loopback_json_request(
    *,
    method: str,
    url: str,
    resolve_host: str,
    body: bytes | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    _require_loopback(resolve_host)
    target_host = urlparse(url).hostname
    if not target_host:
        raise ValueError("local Gamma request URL has no hostname")
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == target_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    req = request.Request(url, data=body, headers=headers, method=method)
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=ssl._create_unverified_context()),
    )
    socket.getaddrinfo = getaddrinfo
    try:
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
        raise RuntimeError(f"local Gamma request transport failed: {type(exc).__name__}") from exc
    finally:
        socket.getaddrinfo = original_getaddrinfo
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"local Gamma request {method} returned non-JSON HTTP {status}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"local Gamma request {method} returned non-object JSON HTTP {status}")
    return status, parsed


def _require_loopback(resolve_host: str) -> None:
    try:
        address = ipaddress.ip_address(resolve_host)
    except ValueError as exc:
        raise ValueError("local Gamma resolve host must be an IP address") from exc
    if not address.is_loopback:
        raise ValueError("local Gamma auth only permits a loopback resolve host")


def _required_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} missing required {field}")
    return value.strip()


def _load_acceptance_principal() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[3]
    manifest_path = (
        root
        / "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    principal = payload.get("acceptancePrincipal")
    if not isinstance(principal, dict):
        raise RuntimeError("Gamma fixture manifest missing acceptancePrincipal")
    return (
        _required_string(principal, "ownerId", "Gamma acceptance principal"),
        _required_string(principal, "personaId", "Gamma acceptance principal"),
    )


def _load_or_create_secrets(path: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_file():
        _require_mode(path, 0o600)
        values = _read_secret_file(path)
        missing = [key for key in _SECRET_KEYS if not values.get(key)]
        if missing == ["otp_code_ref_key_b64"]:
            values["otp_code_ref_key_b64"] = base64.b64encode(
                secrets.token_bytes(32)
            ).decode("ascii")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "otp_code_ref_key_b64="
                    + values["otp_code_ref_key_b64"]
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            return values
        if missing:
            raise RuntimeError("local Gamma auth secret file is incomplete: " + ", ".join(missing))
        return values
    if path.exists():
        raise RuntimeError(f"local Gamma auth secret path is not a file: {path}")
    values = {
        "jwt_secret": secrets.token_urlsafe(48),
        "device_ticket_secret": secrets.token_urlsafe(48),
        "otp_code_ref_key_b64": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
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
            raise RuntimeError(f"invalid local Gamma auth secret file: {path}")
        values[key] = value
    return values


def _require_mode(path: Path, expected: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"local Gamma auth secret file must use mode {expected:04o}: {path}")


def _print_shell_environment() -> None:
    auth = prepare_local_gamma_auth()
    for key, value in sorted(auth.environment.items()):
        print(f"export {key}={shlex.quote(value)}")


if __name__ == "__main__":
    if sys.argv[1:] != ["--shell"]:
        raise SystemExit("usage: python -m quwoquan_ops.cli.lib.local_gamma_auth --shell")
    _print_shell_environment()
