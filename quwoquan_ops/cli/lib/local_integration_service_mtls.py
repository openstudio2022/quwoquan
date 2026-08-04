"""Materialize local non-production integration-service mTLS client PEMs.

user-service always constructs ``NewIntegrationServiceMTLSClient`` on the full
workload. Compose mounts host PEMs into ``/run/quwoquan/integration-mtls/*``.
Missing or empty host files become empty container mounts and fail closed with
``integration service mTLS CA contains no certificate``.

Local Alpha/Beta/Gamma material is issued from the target-scoped local-managed
root under ``QWQ_DEPLOY_WORK_ROOT/<target>/secrets/integration-service-mtls/``.
It is never committed and never reuses production Secret Manager material.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from .output_paths import deployment_target_path
from .public_domain_tls import PublicDomainTlsError, root_certificate_path


ROLE = "integration-service-mtls"
CLIENT_CN = "user-service"


@dataclass(frozen=True)
class LocalIntegrationServiceMTLS:
    environment: dict[str, str]
    ca_path: Path
    client_cert_path: Path
    client_key_path: Path


def _openssl_bin() -> str:
    """Prefer Homebrew OpenSSL when PATH still resolves to LibreSSL.

    macOS ``/usr/bin/openssl`` (LibreSSL) rejects ``-checkhost`` and breaks
    readiness even when PEMs are valid. Local bootstrap must stay portable.
    """

    candidates = (
        os.environ.get("QWQ_OPENSSL_BIN", "").strip(),
        "/opt/homebrew/opt/openssl@3/bin/openssl",
        "/opt/homebrew/bin/openssl",
        "/usr/local/opt/openssl@3/bin/openssl",
        "/usr/local/bin/openssl",
        shutil.which("openssl") or "",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "GATE_BLOCK: openssl is required for integration-service mTLS"
    )


def prepare_local_integration_service_mtls(
    environment: str,
    target_name: str,
) -> LocalIntegrationServiceMTLS:
    """Issue or reuse target-isolated client PEMs for integration-service mTLS."""

    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "integration-service mTLS bootstrap is limited to Alpha/Beta/Gamma"
        )
    if target_name != f"{environment}-local":
        raise ValueError(
            "integration-service mTLS target/environment mismatch: "
            f"environment={environment} target={target_name}"
        )
    openssl = _openssl_bin()

    ca_path = root_certificate_path(target_name)
    ca_key_path = ca_path.with_name("root.key")
    if not ca_key_path.is_file() or ca_key_path.stat().st_mode & 0o077:
        raise PublicDomainTlsError(
            "GATE_BLOCK: protected local-managed root key is unavailable for "
            f"{target_name}"
        )

    tls_dir = deployment_target_path(target_name, "secrets", ROLE)
    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)
    client_cert_path = tls_dir / "client.crt"
    client_key_path = tls_dir / "client.key"
    if not _material_is_ready(openssl, ca_path, client_cert_path, client_key_path):
        _issue_client_certificate(
            openssl=openssl,
            target_name=target_name,
            tls_dir=tls_dir,
            ca_path=ca_path,
            ca_key_path=ca_key_path,
            client_cert_path=client_cert_path,
            client_key_path=client_key_path,
        )
    if not _material_is_ready(openssl, ca_path, client_cert_path, client_key_path):
        raise RuntimeError(
            "GATE_BLOCK: integration-service mTLS material is empty or invalid "
            f"for {target_name}"
        )
    return LocalIntegrationServiceMTLS(
        environment={
            "INTEGRATION_SERVICE_MTLS_CA_FILE": str(ca_path.resolve()),
            "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": str(
                client_cert_path.resolve()
            ),
            "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE": str(
                client_key_path.resolve()
            ),
            "INTEGRATION_SERVICE_MTLS_SERVER_NAME": "integration-service",
        },
        ca_path=ca_path,
        client_cert_path=client_cert_path,
        client_key_path=client_key_path,
    )


def _certificate_binds_client_cn(openssl: str, certificate: Path) -> bool:
    """Accept DNS SAN or CN for CLIENT_CN without LibreSSL-incompatible flags."""

    text = subprocess.run(
        [openssl, "x509", "-in", str(certificate), "-noout", "-text"],
        capture_output=True,
        check=False,
        text=True,
    )
    if text.returncode != 0:
        return False
    body = text.stdout or ""
    if f"DNS:{CLIENT_CN}" in body:
        return True
    subject = subprocess.run(
        [openssl, "x509", "-in", str(certificate), "-noout", "-subject"],
        capture_output=True,
        check=False,
        text=True,
    )
    if subject.returncode != 0:
        return False
    subject_text = subject.stdout or ""
    return (
        f"CN = {CLIENT_CN}" in subject_text
        or f"CN={CLIENT_CN}" in subject_text
        or f"/CN={CLIENT_CN}" in subject_text
        or f"CN={CLIENT_CN} (" in subject_text
        or f"CN = {CLIENT_CN} (" in subject_text
    )


def _material_is_ready(
    openssl: str,
    ca: Path,
    certificate: Path,
    key: Path,
) -> bool:
    if not ca.is_file() or not certificate.is_file() or not key.is_file():
        return False
    if key.is_symlink() or certificate.is_symlink() or ca.is_symlink():
        return False
    if key.stat().st_mode & 0o077:
        return False
    if ca.stat().st_size == 0 or certificate.stat().st_size == 0 or key.stat().st_size == 0:
        return False
    commands = (
        [openssl, "x509", "-in", str(ca), "-noout"],
        [openssl, "x509", "-in", str(certificate), "-checkend", "86400", "-noout"],
        [openssl, "verify", "-CAfile", str(ca), str(certificate)],
    )
    if not all(
        subprocess.run(command, capture_output=True, check=False).returncode == 0
        for command in commands
    ):
        return False
    if not _certificate_binds_client_cn(openssl, certificate):
        return False
    certificate_public_key = subprocess.run(
        [openssl, "x509", "-in", str(certificate), "-noout", "-pubkey"],
        capture_output=True,
        check=False,
    )
    private_public_key = subprocess.run(
        [openssl, "pkey", "-in", str(key), "-pubout"],
        capture_output=True,
        check=False,
    )
    return (
        certificate_public_key.returncode == 0
        and private_public_key.returncode == 0
        and certificate_public_key.stdout == private_public_key.stdout
    )


def _issue_client_certificate(
    *,
    openssl: str,
    target_name: str,
    tls_dir: Path,
    ca_path: Path,
    ca_key_path: Path,
    client_cert_path: Path,
    client_key_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(dir=tls_dir) as temporary:
        temp = Path(temporary)
        next_key = temp / "client.key"
        request_path = temp / "client.csr"
        next_certificate = temp / "client.crt"
        extensions = temp / "client.ext"
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=clientAuth\n"
            f"subjectAltName=DNS:{CLIENT_CN},DNS:localhost,IP:127.0.0.1\n",
            encoding="utf-8",
        )
        commands = (
            [
                openssl,
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(next_key),
            ],
            [
                openssl,
                "req",
                "-new",
                "-key",
                str(next_key),
                "-out",
                str(request_path),
                "-subj",
                f"/CN={CLIENT_CN} ({target_name})",
            ],
            [
                openssl,
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
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "GATE_BLOCK: integration-service mTLS issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        os.chmod(next_key, 0o600)
        os.chmod(next_certificate, 0o600)
        next_key.replace(client_key_path)
        next_certificate.replace(client_cert_path)
        os.chmod(client_key_path, 0o600)
        os.chmod(client_cert_path, 0o600)
