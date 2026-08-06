"""Run the SMS local-capture Adapter against its real HTTPS workload.

The Provider matrix owns the active-candidate/config preflight. This harness
only starts the exact Ops-owned protocol implementation with ephemeral,
target-isolated material and then executes the Integration Service Adapter
test over HTTPS. Secret values stay in child-process environments and the
temporary directory is removed on every exit.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
SUBSTITUTE_ROOT = ROOT / "quwoquan_ops/external/sms-provider-substitute"
ENDPOINT_CONTRACT = SUBSTITUTE_ROOT / "contract/endpoints.yaml"
PROTOCOL_TEST_PACKAGE = (
    "./services/integration-service/tests/api_integration/"
    "external_integration/external_interaction/provider_protocol"
)
PROTOCOL_TEST_NAME = "^TestSMSLocalCaptureAdapterAgainstManagedProtocol$"
_ALLOWED_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma"})


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _load_protocol_paths() -> tuple[str, str]:
    try:
        payload = yaml.safe_load(ENDPOINT_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeError("SMS local-capture endpoint contract is unreadable") from exc
    provider = (
        ((payload or {}).get("endpoints") or {})
        .get("INTEGRATION_SMS_ENDPOINT", {})
        .get("path")
    )
    protected = (
        ((payload or {}).get("protectedEndpoints") or {})
        .get("SMS_SUBSTITUTE_PROTECTED_OTP_READ", {})
        .get("path")
    )
    for value in (provider, protected):
        if (
            not isinstance(value, str)
            or not value.startswith("/")
            or "//" in value
            or ".." in value
            or "?" in value
            or "#" in value
        ):
            raise RuntimeError("SMS local-capture endpoint contract is invalid")
    return provider, protected


def _issue_ephemeral_tls(directory: Path) -> tuple[Path, Path, Path]:
    ca_key = directory / "ca.key"
    ca_certificate = directory / "ca.crt"
    server_key = directory / "server.key"
    server_request = directory / "server.csr"
    server_certificate = directory / "server.crt"
    extensions = directory / "server.ext"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n",
        encoding="utf-8",
    )
    commands = (
        (
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-days",
            "1",
            "-subj",
            "/CN=quwoquan-sms-conformance-ca",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_certificate),
        ),
        (
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(server_key),
            "-out",
            str(server_request),
        ),
        (
            "openssl",
            "x509",
            "-req",
            "-sha256",
            "-days",
            "1",
            "-in",
            str(server_request),
            "-CA",
            str(ca_certificate),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-extfile",
            str(extensions),
            "-out",
            str(server_certificate),
        ),
    )
    for command in commands:
        completed = subprocess.run(
            list(command),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            raise RuntimeError("SMS local-capture conformance TLS issuance failed")
    os.chmod(ca_key, 0o600)
    os.chmod(server_key, 0o600)
    return ca_certificate, server_certificate, server_key


def _wait_until_ready(
    *,
    process: subprocess.Popen[bytes],
    health_url: str,
    ca_path: Path,
    expected_environment: str,
    expected_config_digest: str,
) -> None:
    context = ssl.create_default_context(cafile=str(ca_path))
    deadline = time.monotonic() + 45.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "SMS local-capture conformance workload exited before readiness"
            )
        try:
            with urllib.request.urlopen(
                health_url,
                timeout=1.0,
                context=context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if (
                response.status == 200
                and payload.get("status") == "ready"
                and payload.get("adapterId") == "ext.sms.local_capture"
                and payload.get("environment") == expected_environment
                and payload.get("configurationDigest") == expected_config_digest
                and payload.get("nonPromotable") is True
            ):
                return
            last_error = RuntimeError("SMS local-capture readiness identity mismatch")
        except (
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError("SMS local-capture conformance workload is not ready") from last_error


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _build_substitute(binary_path: Path) -> None:
    completed = subprocess.run(
        [
            "go",
            "build",
            "-o",
            str(binary_path),
            "./cmd/sms-provider-substitute",
        ],
        cwd=SUBSTITUTE_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0 or not binary_path.is_file():
        raise RuntimeError("SMS local-capture conformance workload build failed")


def main() -> int:
    environment = _required("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise ValueError(
            "SMS local-capture api_integration is limited to Alpha/Beta/Gamma"
        )
    if _required("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID") != "ext.sms.local_capture":
        raise ValueError("SMS local-capture harness Adapter identity mismatch")
    config_digest = _required("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest) is None:
        raise ValueError("SMS local-capture harness config digest is invalid")

    with tempfile.TemporaryDirectory(prefix="qwq-sms-conformance-") as temporary:
        temporary_root = Path(temporary)
        ca_path, certificate_path, private_key_path = _issue_ephemeral_tls(
            temporary_root
        )
        binary_path = temporary_root / "sms-provider-substitute"
        _build_substitute(binary_path)
        port = _reserve_port()
        provider_path, protected_read_path = _load_protocol_paths()
        endpoint = f"https://localhost:{port}{provider_path}"
        health_url = f"https://localhost:{port}/healthz"
        provider_token = secrets.token_urlsafe(32)
        operator_token = secrets.token_urlsafe(32)
        capture_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        substitute_environment = {
            **os.environ,
            "APP_ENV": environment,
            "SMS_SUBSTITUTE_CONFIGURATION_DIGEST": config_digest,
            "SMS_SUBSTITUTE_ADDR": f"127.0.0.1:{port}",
            "SMS_SUBSTITUTE_PROVIDER_TOKEN": provider_token,
            "SMS_SUBSTITUTE_OPERATOR_TOKEN": operator_token,
            "SMS_SUBSTITUTE_CAPTURE_KEY_B64": capture_key,
            "SMS_SUBSTITUTE_TLS_CERT_FILE": str(certificate_path),
            "SMS_SUBSTITUTE_TLS_KEY_FILE": str(private_key_path),
            "SMS_SUBSTITUTE_SCENARIO": "success",
        }
        process = subprocess.Popen(
            [str(binary_path)],
            cwd=SUBSTITUTE_ROOT,
            env=substitute_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_until_ready(
                process=process,
                health_url=health_url,
                ca_path=ca_path,
                expected_environment=environment,
                expected_config_digest=config_digest,
            )
            test_environment = {
                **os.environ,
                "QWQ_SMS_LOCAL_CAPTURE_ENVIRONMENT": environment,
                "QWQ_SMS_LOCAL_CAPTURE_ENDPOINT": endpoint,
                "QWQ_SMS_LOCAL_CAPTURE_CA_FILE": str(ca_path),
                "QWQ_SMS_LOCAL_CAPTURE_PROVIDER_TOKEN": provider_token,
                "QWQ_SMS_LOCAL_CAPTURE_OPERATOR_TOKEN": operator_token,
                "QWQ_SMS_LOCAL_CAPTURE_CONFIG_DIGEST": config_digest,
                "QWQ_SMS_LOCAL_CAPTURE_PROVIDER_PATH": provider_path,
                "QWQ_SMS_LOCAL_CAPTURE_PROTECTED_READ_PATH": protected_read_path,
            }
            completed = subprocess.run(
                [
                    "go",
                    "test",
                    "-tags",
                    "provider_conformance",
                    PROTOCOL_TEST_PACKAGE,
                    "-run",
                    PROTOCOL_TEST_NAME,
                    "-count=1",
                ],
                cwd=ROOT / "quwoquan_service",
                env=test_environment,
                check=False,
            )
            return int(completed.returncode)
        finally:
            _terminate(process)


if __name__ == "__main__":
    raise SystemExit(main())
