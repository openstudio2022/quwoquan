#!/usr/bin/env python3
"""Canonical TLS material facade for local targets and public DNS-01 targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.dns_provider import DnsProviderError, provider_for_kind
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.openssl3_resolver import (
    OpenSSL3Executable,
    resolve_openssl3,
)
from quwoquan_ops.cli.lib.output_paths import (
    certificate_export_dir,
    deployment_target_path,
)


POLICY_PATH = ROOT / "quwoquan_ops" / "environments" / "domain_governance.yaml"


class PublicDomainTlsError(RuntimeError):
    pass


def load_policy() -> dict[str, Any]:
    policy = load_json_yaml(POLICY_PATH)
    if not isinstance(policy, dict) or policy.get("schema") != "quwoquan.domain-governance":
        raise PublicDomainTlsError(f"GATE_BLOCK: invalid domain policy: {POLICY_PATH}")
    return policy


def _profile_for_target(target: str) -> tuple[str, dict[str, Any]]:
    profiles = load_policy().get("tlsProfiles") or {}
    for profile_name, raw_profile in profiles.items():
        if not isinstance(raw_profile, dict):
            continue
        targets = raw_profile.get("targets") or []
        if raw_profile.get("target") == target or (
            isinstance(targets, list) and target in targets
        ):
            return str(profile_name), raw_profile
    raise PublicDomainTlsError(f"GATE_BLOCK: no canonical TLS profile for target {target}")


def _profile_kind(profile_name: str, profile: dict[str, Any]) -> str:
    kind = str(profile.get("kind") or "").strip()
    if kind:
        return kind
    if profile_name.startswith("acme-dns01-"):
        return "dns-01-public-ca"
    raise PublicDomainTlsError(
        f"GATE_BLOCK: TLS profile {profile_name} has no canonical kind"
    )


def tls_profile(target: str) -> tuple[str, str, dict[str, Any]]:
    profile_name, profile = _profile_for_target(target)
    return profile_name, _profile_kind(profile_name, profile), profile


def _required_names(target: str, profile: dict[str, Any]) -> list[str]:
    if _profile_kind(_profile_for_target(target)[0], profile) == "local-managed":
        resolved_roles = get_target(
            load_environment_topology(), target
        ).get("resolvedUrlRoles") or {}
        names = sorted(
            {
                str(role.get("host") or "").strip()
                for role in resolved_roles.values()
                if isinstance(role, dict) and str(role.get("host") or "").strip()
            }
        )
        if not names:
            raise PublicDomainTlsError(
                f"GATE_BLOCK: {target} topology has no TLS host names"
            )
        return names
    return [
        name
        for name in (
            str(profile.get("apex") or "").strip(),
            str(profile.get("wildcard") or "").strip(),
        )
        if name
    ]


def certificate_dir(target: str) -> Path:
    return certificate_export_dir(target)


def certificate_bundle_dir(target: str) -> Path:
    """加密证书包的落盘目录。

    证书包是待交付的 deployment payload，只能落在仓外受限的部署工作区，不得写回
    `.qwq_output`。调用方一律从这里取路径，不自己拼。
    """
    return deployment_target_path(target, "packages", "tls")


def certificate_paths(target: str, *, require_ready: bool = True) -> tuple[Path, Path]:
    root = certificate_dir(target)
    cert = root / "fullchain.pem"
    key = root / "privkey.pem"
    if require_ready and (not cert.is_file() or not key.is_file()):
        raise PublicDomainTlsError(
            "GATE_BLOCK: canonical certificate is missing for "
            f"{target}; run `stackctl tls --target {target} --action prevalidate`"
        )
    return cert, key


def root_certificate_path(target: str, *, require_ready: bool = True) -> Path:
    path = certificate_dir(target) / "root.crt"
    if require_ready and not path.is_file():
        raise PublicDomainTlsError(
            f"GATE_BLOCK: local-managed root certificate is missing for {target}"
        )
    return path


def _openssl(
    openssl: OpenSSL3Executable,
    command: list[str],
    *,
    failure: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        openssl.argv(*command),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PublicDomainTlsError(f"GATE_BLOCK: {failure}: {detail}")
    return result


def _public_key_digest(
    openssl: OpenSSL3Executable,
    arguments: list[str],
) -> str:
    result = subprocess.run(
        openssl.argv(*arguments),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PublicDomainTlsError("GATE_BLOCK: certificate public-key read failed")
    return hashlib.sha256(result.stdout).hexdigest()


def _certificate_key_pair_matches(
    certificate: Path,
    private_key: Path,
    *,
    openssl: OpenSSL3Executable,
) -> bool:
    if not certificate.is_file() or not private_key.is_file():
        return False
    try:
        certificate_public_key = _openssl(
            openssl,
            ["x509", "-in", str(certificate), "-pubkey", "-noout"],
            failure="certificate public-key read failed",
        )
        with tempfile.NamedTemporaryFile() as public_key:
            public_key.write(certificate_public_key.stdout.encode("utf-8"))
            public_key.flush()
            certificate_digest = _public_key_digest(
                openssl,
                ["pkey", "-pubin", "-in", public_key.name, "-outform", "DER"]
            )
        private_digest = _public_key_digest(
            openssl,
            ["pkey", "-in", str(private_key), "-pubout", "-outform", "DER"]
        )
    except PublicDomainTlsError:
        return False
    return certificate_digest == private_digest


def verify_certificate(
    target: str,
    *,
    renew_before_days: int | None = None,
    openssl: OpenSSL3Executable | None = None,
) -> dict[str, Any]:
    policy = load_policy()
    profile_name, profile = _profile_for_target(target)
    profile_kind = _profile_kind(profile_name, profile)
    if profile.get("certificateAutomation") == "external":
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} certificate is externally managed"
        )
    selected = openssl or resolve_openssl3()
    cert, key = certificate_paths(target)
    days = int(
        renew_before_days
        if renew_before_days is not None
        else profile.get("renewBeforeDays")
        or (policy.get("acme") or {}).get("renewBeforeDays", 30)
    )
    check = subprocess.run(
        selected.argv("x509", "-in", str(cert), "-checkend", str(days * 86400), "-noout"),
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} certificate expires within {days} days"
        )
    if not _certificate_key_pair_matches(cert, key, openssl=selected):
        raise PublicDomainTlsError(f"GATE_BLOCK: {target} certificate/private-key mismatch")
    inspect = subprocess.run(
        selected.argv("x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"),
        text=True,
        capture_output=True,
        check=False,
    )
    sans = inspect.stdout
    required_names = _required_names(target, profile)
    for required_name in required_names:
        if required_name and required_name not in sans:
            raise PublicDomainTlsError(
                f"GATE_BLOCK: {target} certificate SAN is missing {required_name}"
            )
    root = None
    if profile_kind == "local-managed":
        root = root_certificate_path(target)
        _openssl(
            selected,
            ["verify", "-CAfile", str(root), str(cert)],
            failure=f"{target} local-managed certificate chain verification failed",
        )
    return {
        "schema": "quwoquan.tls-evidence",
        "target": target,
        "profile": profile_name,
        "kind": profile_kind,
        "certificate": str(cert),
        "privateKey": str(key),
        "rootCertificate": str(root) if root is not None else "system",
        "sans": required_names,
        "renewBeforeDays": days,
        "status": "ready",
    }


def _issue_local_managed_certificate(
    target: str,
    profile: dict[str, Any],
    *,
    openssl: OpenSSL3Executable,
) -> dict[str, Any]:
    output_root = certificate_dir(target)
    output_root.mkdir(parents=True, exist_ok=True)
    root_key = output_root / "root.key"
    root_cert = root_certificate_path(target, require_ready=False)
    if not _certificate_key_pair_matches(root_cert, root_key, openssl=openssl):
        with tempfile.TemporaryDirectory(dir=output_root) as temporary:
            temporary_root = Path(temporary)
            next_root_key = temporary_root / "root.key"
            next_root_cert = temporary_root / "root.crt"
            _openssl(
                openssl,
                [
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:2048",
                    "-out",
                    str(next_root_key),
                ],
                failure=f"{target} local-managed root key generation failed",
            )
            _openssl(
                openssl,
                [
                    "req", "-x509", "-new", "-sha256", "-days", "3650",
                    "-key", str(next_root_key), "-out", str(next_root_cert),
                    "-subj", f"/CN=Quwoquan local-managed CA ({target})",
                    "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                ],
                failure=f"{target} local-managed root certificate generation failed",
            )
            next_root_key.chmod(0o600)
            next_root_key.replace(root_key)
            next_root_cert.replace(root_cert)

    cert, key = certificate_paths(target, require_ready=False)
    names = _required_names(target, profile)
    with tempfile.TemporaryDirectory(dir=output_root) as temporary:
        temporary_root = Path(temporary)
        csr = temporary_root / "leaf.csr"
        leaf = temporary_root / "leaf.crt"
        extensions = temporary_root / "leaf.ext"
        _openssl(
            openssl,
            ["genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
            failure=f"{target} local-managed leaf key generation failed",
        )
        _openssl(
            openssl,
            ["req", "-new", "-key", str(key), "-out", str(csr), "-subj", f"/CN={names[0]}"],
            failure=f"{target} local-managed certificate request failed",
        )
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            + "subjectAltName="
            + ",".join(f"DNS:{name}" for name in names)
            + "\n",
            encoding="utf-8",
        )
        serial = secrets.token_hex(16)
        _openssl(
            openssl,
            [
                "x509", "-req", "-sha256",
                "-days", str(int(profile.get("certificateDays") or 90)),
                "-in", str(csr), "-CA", str(root_cert), "-CAkey", str(root_key),
                "-set_serial", f"0x{serial}", "-extfile", str(extensions),
                "-out", str(leaf),
            ],
            failure=f"{target} local-managed leaf certificate signing failed",
        )
        cert.write_bytes(leaf.read_bytes() + root_cert.read_bytes())
    key.chmod(0o600)
    return verify_certificate(target, openssl=openssl)


def _challenge_credential_environment(
    policy: dict[str, Any],
    acme: dict[str, Any],
    challenge_credential: str,
) -> dict[str, str]:
    """把中立的 challenge 凭据投影为 ACME 客户端所需的 provider 变量。

    「变量名 -> 部件名」由 policy 的 `acme.credentialEnvironment` 声明，凭据本身
    的形状由 provider 解释，所以换服务商只加 provider 实现，本模块不动。
    """
    mapping = acme.get("credentialEnvironment") or {}
    if not isinstance(mapping, dict) or not mapping:
        raise PublicDomainTlsError(
            "GATE_BLOCK: acme.credentialEnvironment must declare the DNS-01 "
            "credential projection"
        )
    kind = str((policy.get("dnsProvider") or {}).get("kind") or "")
    try:
        provider_class = provider_for_kind(kind)
        return provider_class.challenge_environment(
            challenge_credential, {str(k): str(v) for k, v in mapping.items()}
        )
    except DnsProviderError as exc:
        raise PublicDomainTlsError(str(exc)) from exc


def _lego_command(
    lego: str,
    *,
    acme: dict[str, Any],
    profile: dict[str, Any],
    lego_root: Path,
) -> list[str]:
    """构造 ACME 客户端调用。

    `run` 同时承担首签与续期：是否真正续期由 `--renew-days` 与 CA 的 ARI 判定，
    因此调用面不按证书是否已存在分叉。注册邮箱不是签发前提，不予传递。
    """
    return [
        lego,
        "run",
        "--accept-tos",
        "--dns",
        str(acme.get("dnsProvider") or ""),
        "--server",
        str(acme.get("directory") or ""),
        "--path",
        str(lego_root),
        "--domains",
        str(profile["apex"]),
        "--domains",
        str(profile["wildcard"]),
        "--renew-days",
        str(int(acme.get("renewBeforeDays", 30))),
    ]


def issue_certificate(target: str) -> dict[str, Any]:
    policy = load_policy()
    profile_name, profile = _profile_for_target(target)
    if _profile_kind(profile_name, profile) == "local-managed":
        openssl = resolve_openssl3()
        return _issue_local_managed_certificate(target, profile, openssl=openssl)
    if profile.get("certificateAutomation") == "external":
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} certificate issuance is externally managed"
        )
    acme = policy.get("acme") or {}
    challenge_authority = policy.get("acmeChallengeAuthority") or {}
    token_env = str(challenge_authority.get("apiTokenEnv") or "")
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {token_env} is required for DNS-01 issuance"
        )
    lego = shutil.which(str(acme.get("client") or "lego"))
    if lego is None:
        raise PublicDomainTlsError("GATE_BLOCK: lego is required for DNS-01 issuance")

    output_root = certificate_dir(target)
    lego_root = output_root / "lego"
    output_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(_challenge_credential_environment(policy, acme, token))
    source_cert = lego_root / "certificates" / f"{profile['apex']}.crt"
    command = _lego_command(lego, acme=acme, profile=profile, lego_root=lego_root)
    result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PublicDomainTlsError(f"GATE_BLOCK: DNS-01 issuance failed: {detail}")

    source_key = lego_root / "certificates" / f"{profile['apex']}.key"
    if not source_cert.is_file() or not source_key.is_file():
        raise PublicDomainTlsError("GATE_BLOCK: lego completed without certificate outputs")
    cert, key = certificate_paths(target, require_ready=False)
    shutil.copy2(source_cert, cert)
    shutil.copy2(source_key, key)
    key.chmod(0o600)
    return verify_certificate(target)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("paths", "verify", "issue"):
        child = subparsers.add_parser(command)
        child.add_argument("--target", required=True)
        if command == "paths":
            child.add_argument("--format", choices=("json", "shell"), default="json")
            child.add_argument("--allow-missing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "issue":
            payload = issue_certificate(args.target)
        elif args.command == "verify":
            payload = verify_certificate(args.target)
        else:
            cert, key = certificate_paths(
                args.target,
                require_ready=not args.allow_missing,
            )
            payload = {
                "target": args.target,
                "certificate": str(cert),
                "privateKey": str(key),
            }
            try:
                profile_name, profile = _profile_for_target(args.target)
                if _profile_kind(profile_name, profile) == "local-managed":
                    payload["rootCertificate"] = str(
                        root_certificate_path(
                            args.target,
                            require_ready=not args.allow_missing,
                        )
                    )
            except PublicDomainTlsError:
                if not args.allow_missing:
                    raise
            bundle_dir = certificate_bundle_dir(args.target)
            payload["bundleDirectory"] = str(bundle_dir)
            if args.format == "shell":
                print(
                    "export QWQ_PUBLIC_TLS_CERT_FILE="
                    + shlex.quote(str(cert))
                )
                print(
                    "export QWQ_PUBLIC_TLS_KEY_FILE="
                    + shlex.quote(str(key))
                )
                print(
                    "export QWQ_PUBLIC_TLS_BUNDLE_DIR="
                    + shlex.quote(str(bundle_dir))
                )
                if "rootCertificate" in payload:
                    print(
                        "export QWQ_LOCAL_MANAGED_CA_FILE="
                        + shlex.quote(str(payload["rootCertificate"]))
                    )
                return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except PublicDomainTlsError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
