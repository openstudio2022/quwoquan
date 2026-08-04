"""Materialize target-isolated TLS for the non-promotable SMS Debug Provider."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .output_paths import deployment_target_path
from .provider_endpoint_contract import load_provider_endpoint_environment
from .public_domain_tls import PublicDomainTlsError, root_certificate_path


@dataclass(frozen=True)
class LocalSMSProviderSubstitute:
    environment: dict[str, str]
    certificate_path: Path
    private_key_path: Path
    ca_path: Path


def prepare_local_sms_provider_substitute(
    environment: str,
    target_name: str,
    *,
    port: int,
) -> LocalSMSProviderSubstitute:
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("SMS Debug Provider is limited to Alpha/Beta/Gamma")
    if target_name != f"{environment}-local":
        raise ValueError("SMS Debug Provider target/environment mismatch")
    if not 1 <= int(port) <= 65535:
        raise ValueError("SMS Debug Provider port is invalid")
    if shutil.which("openssl") is None:
        raise RuntimeError("GATE_BLOCK: openssl is required for SMS substitute TLS")

    ca_path = root_certificate_path(target_name)
    ca_key_path = ca_path.with_name("root.key")
    if not ca_key_path.is_file() or ca_key_path.stat().st_mode & 0o077:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: protected local-managed root key is unavailable for {target_name}"
        )
    tls_dir = deployment_target_path(
        target_name,
        "secrets",
        "sms-provider-substitute",
    )
    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)
    certificate_path = tls_dir / "server.crt"
    private_key_path = tls_dir / "server.key"
    if not _certificate_is_ready(
        certificate_path,
        private_key_path,
        ca_path,
    ):
        _issue_certificate(
            target_name=target_name,
            tls_dir=tls_dir,
            ca_path=ca_path,
            ca_key_path=ca_key_path,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
        )
    return LocalSMSProviderSubstitute(
        environment={
            "QWQ_RUNTIME_TARGET": target_name,
            "INTEGRATION_SMS_ENDPOINT": load_provider_endpoint_environment()[
                "INTEGRATION_SMS_ENDPOINT"
            ],
            "INTEGRATION_SMS_SUBSTITUTE_CA_FILE": (
                "/run/secrets/sms-provider-substitute/ca.crt"
            ),
            "SMS_SUBSTITUTE_TLS_CERT_FILE": (
                "/run/secrets/sms-provider-substitute/server.crt"
            ),
            "SMS_SUBSTITUTE_TLS_KEY_FILE": (
                "/run/secrets/sms-provider-substitute/server.key"
            ),
            "QWQ_COMPOSE_SMS_SUBSTITUTE_CA_FILE": str(ca_path.resolve()),
            "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_CERT_FILE": str(
                certificate_path.resolve()
            ),
            "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_KEY_FILE": str(
                private_key_path.resolve()
            ),
            "QWQ_COMPOSE_SMS_SUBSTITUTE_PORT": str(port),
        },
        certificate_path=certificate_path,
        private_key_path=private_key_path,
        ca_path=ca_path,
    )


def _certificate_is_ready(certificate: Path, key: Path, ca: Path) -> bool:
    if not certificate.is_file() or not key.is_file():
        return False
    if key.stat().st_mode & 0o077:
        return False
    commands = (
        ["openssl", "x509", "-in", str(certificate), "-checkend", "86400", "-noout"],
        ["openssl", "verify", "-CAfile", str(ca), str(certificate)],
        ["openssl", "x509", "-in", str(certificate), "-noout", "-checkhost", "sms-provider-substitute"],
    )
    if not all(
        subprocess.run(command, capture_output=True, check=False).returncode == 0
        for command in commands
    ):
        return False
    certificate_public_key = subprocess.run(
        ["openssl", "x509", "-in", str(certificate), "-noout", "-pubkey"],
        capture_output=True,
        check=False,
    )
    private_public_key = subprocess.run(
        ["openssl", "pkey", "-in", str(key), "-pubout"],
        capture_output=True,
        check=False,
    )
    return (
        certificate_public_key.returncode == 0
        and private_public_key.returncode == 0
        and certificate_public_key.stdout == private_public_key.stdout
    )


def _issue_certificate(
    *,
    target_name: str,
    tls_dir: Path,
    ca_path: Path,
    ca_key_path: Path,
    certificate_path: Path,
    private_key_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(dir=tls_dir) as temporary:
        temp = Path(temporary)
        next_key = temp / "server.key"
        request_path = temp / "server.csr"
        next_certificate = temp / "server.crt"
        extensions = temp / "server.ext"
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            "subjectAltName=DNS:sms-provider-substitute,DNS:localhost,IP:127.0.0.1\n",
            encoding="utf-8",
        )
        commands = (
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(next_key),
            ],
            [
                "openssl",
                "req",
                "-new",
                "-key",
                str(next_key),
                "-out",
                str(request_path),
                "-subj",
                f"/CN=sms-provider-substitute ({target_name})",
            ],
            [
                "openssl",
                "x509",
                "-req",
                "-sha256",
                "-days",
                "30",
                "-in",
                str(request_path),
                "-CA",
                str(ca_path),
                "-CAkey",
                str(ca_key_path),
                "-set_serial",
                "0x" + secrets.token_hex(16),
                "-extfile",
                str(extensions),
                "-out",
                str(next_certificate),
            ],
        )
        for command in commands:
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(
                    "GATE_BLOCK: SMS substitute TLS issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        os.chmod(next_key, 0o600)
        os.chmod(next_certificate, 0o600)
        next_key.replace(private_key_path)
        next_certificate.replace(certificate_path)
