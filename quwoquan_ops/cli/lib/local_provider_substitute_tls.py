"""Issue target-isolated server certificates for external Provider substitutes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3
from .output_paths import deployment_target_path
from .public_domain_tls import PublicDomainTlsError, root_certificate_path


@dataclass(frozen=True)
class LocalProviderSubstituteTls:
    certificate_path: Path
    private_key_path: Path
    ca_path: Path


def prepare_local_provider_substitute_tls(
    target_name: str,
    *,
    role: str,
) -> LocalProviderSubstituteTls:
    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        raise ValueError("Provider substitute TLS is limited to local non-production")
    openssl = resolve_openssl3()
    ca_path = root_certificate_path(target_name)
    ca_key_path = ca_path.with_name("root.key")
    if not ca_key_path.is_file() or ca_key_path.stat().st_mode & 0o077:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: protected local-managed root key is unavailable for {target_name}"
        )
    tls_dir = deployment_target_path(target_name, "secrets", role)
    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)
    certificate_path = tls_dir / "server.crt"
    private_key_path = tls_dir / "server.key"
    if not _certificate_is_ready(
        certificate_path,
        private_key_path,
        ca_path,
        role=role,
        openssl=openssl,
    ):
        _issue_certificate(
            target_name=target_name,
            role=role,
            tls_dir=tls_dir,
            ca_path=ca_path,
            ca_key_path=ca_key_path,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            openssl=openssl,
        )
    return LocalProviderSubstituteTls(
        certificate_path=certificate_path,
        private_key_path=private_key_path,
        ca_path=ca_path,
    )


def _certificate_is_ready(
    certificate: Path,
    key: Path,
    ca: Path,
    *,
    role: str,
    openssl: OpenSSL3Executable,
) -> bool:
    if not certificate.is_file() or not key.is_file() or key.stat().st_mode & 0o077:
        return False
    commands = (
        openssl.argv("x509", "-in", str(certificate), "-checkend", "86400", "-noout"),
        openssl.argv("verify", "-CAfile", str(ca), str(certificate)),
        openssl.argv(
            "x509",
            "-in",
            str(certificate),
            "-noout",
            "-checkhost",
            role,
        ),
    )
    if not all(
        subprocess.run(command, capture_output=True, check=False).returncode == 0
        for command in commands
    ):
        return False
    certificate_public_key = subprocess.run(
        openssl.argv("x509", "-in", str(certificate), "-noout", "-pubkey"),
        capture_output=True,
        check=False,
    )
    private_public_key = subprocess.run(
        openssl.argv("pkey", "-in", str(key), "-pubout"),
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
    role: str,
    tls_dir: Path,
    ca_path: Path,
    ca_key_path: Path,
    certificate_path: Path,
    private_key_path: Path,
    openssl: OpenSSL3Executable,
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
            f"subjectAltName=DNS:{role},DNS:localhost,IP:127.0.0.1\n",
            encoding="utf-8",
        )
        commands = (
            (
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(next_key),
            ),
            (
                "req",
                "-new",
                "-key",
                str(next_key),
                "-out",
                str(request_path),
                "-subj",
                f"/CN={role} ({target_name})",
            ),
            (
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
            ),
        )
        for arguments in commands:
            result = subprocess.run(
                openssl.argv(*arguments),
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "GATE_BLOCK: Provider substitute TLS issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        os.chmod(next_key, 0o600)
        os.chmod(next_certificate, 0o600)
        next_key.replace(private_key_path)
        next_certificate.replace(certificate_path)
