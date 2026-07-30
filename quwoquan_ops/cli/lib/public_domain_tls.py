#!/usr/bin/env python3
"""DNS-01 公共证书签发与本地 target 证书路径单一入口。"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.output_paths import certificate_export_dir


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
        if isinstance(raw_profile, dict) and raw_profile.get("target") == target:
            return str(profile_name), raw_profile
    raise PublicDomainTlsError(f"GATE_BLOCK: no DNS-01 TLS profile for target {target}")


def certificate_dir(target: str) -> Path:
    return certificate_export_dir(target)


def certificate_paths(target: str, *, require_ready: bool = True) -> tuple[Path, Path]:
    root = certificate_dir(target)
    cert = root / "fullchain.pem"
    key = root / "privkey.pem"
    if require_ready and (not cert.is_file() or not key.is_file()):
        raise PublicDomainTlsError(
            "GATE_BLOCK: public DNS-01 certificate is missing for "
            f"{target}; run `stackctl tls --target {target} --action prevalidate`"
        )
    return cert, key


def verify_certificate(target: str, *, renew_before_days: int | None = None) -> dict[str, Any]:
    policy = load_policy()
    _, profile = _profile_for_target(target)
    if profile.get("certificateAutomation") == "external":
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} certificate is externally managed"
        )
    cert, key = certificate_paths(target)
    days = int(
        renew_before_days
        if renew_before_days is not None
        else (policy.get("acme") or {}).get("renewBeforeDays", 30)
    )
    check = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-checkend", str(days * 86400), "-noout"],
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} public certificate expires within {days} days"
        )
    key_match = subprocess.run(
        [
            "sh",
            "-c",
            f"test \"$(openssl x509 -in {shlex.quote(str(cert))} -pubkey -noout | "
            "openssl pkey -pubin -outform der 2>/dev/null | openssl sha256)\" = "
            f"\"$(openssl pkey -in {shlex.quote(str(key))} -pubout -outform der 2>/dev/null | "
            "openssl sha256)\"",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if key_match.returncode != 0:
        raise PublicDomainTlsError(f"GATE_BLOCK: {target} certificate/private-key mismatch")
    inspect = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
        text=True,
        capture_output=True,
        check=False,
    )
    sans = inspect.stdout
    for required_name in (str(profile.get("apex") or ""), str(profile.get("wildcard") or "")):
        if required_name and required_name not in sans:
            raise PublicDomainTlsError(
                f"GATE_BLOCK: {target} certificate SAN is missing {required_name}"
            )
    return {
        "schema": "quwoquan.public-domain-tls-evidence",
        "target": target,
        "certificate": str(cert),
        "privateKey": str(key),
        "apex": profile["apex"],
        "wildcard": profile["wildcard"],
        "renewBeforeDays": days,
        "status": "ready",
    }


def issue_certificate(target: str) -> dict[str, Any]:
    policy = load_policy()
    _, profile = _profile_for_target(target)
    if profile.get("certificateAutomation") == "external":
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {target} certificate issuance is externally managed"
        )
    acme = policy.get("acme") or {}
    provider = str(acme.get("dnsProvider") or "")
    email_env = str(acme.get("accountEmailEnv") or "")
    email = os.environ.get(email_env, "").strip()
    challenge_authority = policy.get("acmeChallengeAuthority") or {}
    token_env = str(challenge_authority.get("apiTokenEnv") or "")
    token = os.environ.get(token_env, "").strip()
    if not email or not token:
        raise PublicDomainTlsError(
            f"GATE_BLOCK: {email_env} and {token_env} are required for DNS-01 issuance"
        )
    lego = shutil.which(str(acme.get("client") or "lego"))
    if lego is None:
        raise PublicDomainTlsError("GATE_BLOCK: lego is required for DNS-01 issuance")

    output_root = certificate_dir(target)
    lego_root = output_root / "lego"
    output_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CLOUDFLARE_DNS_API_TOKEN"] = token
    source_cert = lego_root / "certificates" / f"{profile['apex']}.crt"
    action = "renew" if source_cert.is_file() else "run"
    command = [
        lego,
        "--accept-tos",
        "--email",
        email,
        "--dns",
        provider,
        "--server",
        str(acme.get("directory") or ""),
        "--path",
        str(lego_root),
        "--domains",
        str(profile["apex"]),
        "--domains",
        str(profile["wildcard"]),
        action,
    ]
    if action == "renew":
        command.extend(["--days", str(int(acme.get("renewBeforeDays", 30)))])
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
            if args.format == "shell":
                print(
                    "export QWQ_PUBLIC_TLS_CERT_FILE="
                    + shlex.quote(str(cert))
                )
                print(
                    "export QWQ_PUBLIC_TLS_KEY_FILE="
                    + shlex.quote(str(key))
                )
                return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except PublicDomainTlsError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
