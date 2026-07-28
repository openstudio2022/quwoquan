#!/usr/bin/env python3
"""从环境拓扑派生、应用并验证 quwoquan.com DNS 治理状态。"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.public_domain_tls import (
    PublicDomainTlsError,
    verify_certificate,
)


POLICY_PATH = ROOT / "quwoquan_ops" / "environments" / "domain_governance.yaml"
LOCAL_TARGETS = ("alpha-local", "beta-local", "gamma-local", "prod-sim")
ALL_TARGETS = (*LOCAL_TARGETS, "prod-hosted")


class DomainGovernanceError(RuntimeError):
    pass


def _policy() -> dict[str, Any]:
    value = load_json_yaml(POLICY_PATH)
    if not isinstance(value, dict) or value.get("schema") != "quwoquan.domain-governance":
        raise DomainGovernanceError(f"invalid domain policy: {POLICY_PATH}")
    return value


def _profile_addresses(
    policy: dict[str, Any],
    *,
    target: str,
    require_values: bool,
) -> tuple[str, str]:
    prefix = "prod" if target == "prod-hosted" else "nonProd"
    address_env = str(policy.get(f"{prefix}AddressEnv") or "")
    ipv6_env = str(policy.get(f"{prefix}Ipv6AddressEnv") or "")
    address = os.environ.get(address_env, "").strip()
    ipv6_address = os.environ.get(ipv6_env, "").strip()
    if not address or not ipv6_address:
        if require_values:
            raise DomainGovernanceError(
                f"GATE_BLOCK: {address_env} and {ipv6_env} must identify public ingress"
            )
        return f"${{{address_env}}}", f"${{{ipv6_env}}}"
    for label, value, expected_version in (
        (address_env, address, 4),
        (ipv6_env, ipv6_address, 6),
    ):
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            raise DomainGovernanceError(
                f"GATE_BLOCK: {label} must be a valid IP address"
            ) from exc
        if parsed.version != expected_version or not parsed.is_global:
            raise DomainGovernanceError(
                f"GATE_BLOCK: {label} must be a globally routable IPv{expected_version} address"
            )
    return address, ipv6_address


def desired_dns_records(
    *,
    require_addresses: bool = False,
) -> list[dict[str, Any]]:
    policy = _policy()
    profiles = [
        profile
        for profile in (policy.get("tlsProfiles") or {}).values()
        if isinstance(profile, dict)
    ]
    records: list[dict[str, Any]] = []
    for profile in profiles:
        target = str(profile["target"])
        address, ipv6_address = _profile_addresses(
            policy,
            target=target,
            require_values=require_addresses,
        )
        for name in (str(profile["apex"]), str(profile["wildcard"])):
            records.extend(
                (
                    {
                        "type": "A",
                        "name": name,
                        "content": address,
                        "ttl": 300,
                        "proxied": False,
                    },
                    {
                        "type": "AAAA",
                        "name": name,
                        "content": ipv6_address,
                        "ttl": 300,
                        "proxied": False,
                    },
                )
            )
        if target != "prod-hosted":
            mail_guard = policy.get("nonProdMailGuard") or {}
            records.extend(
                (
                    {
                        "type": "MX",
                        "name": str(profile["apex"]),
                        "content": str(mail_guard["nullMx"]),
                        "priority": 0,
                        "ttl": 3600,
                    },
                    {
                        "type": "TXT",
                        "name": str(profile["apex"]),
                        "content": str(mail_guard["spf"]),
                        "ttl": 3600,
                    },
                )
            )
    caa_names = {
        str(policy["registrableDomain"]),
        *(
            str(profile["apex"])
            for profile in profiles
        ),
    }
    for name in sorted(caa_names):
        for caa in policy.get("caa") or []:
            records.append(
                {
                    "type": "CAA",
                    "name": name,
                    "data": {
                        "flags": int(caa["flags"]),
                        "tag": str(caa["tag"]),
                        "value": str(caa["value"]),
                    },
                    "ttl": 3600,
                }
            )
    records.append(
        {
            "type": "CNAME",
            "name": f"www.{policy['registrableDomain']}",
            "content": str(policy["registrableDomain"]),
            "ttl": 300,
            "proxied": False,
        }
    )
    return records


def _cloudflare_request(
    method: str,
    path: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method=method,
        data=(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        ),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            document = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DomainGovernanceError(f"Cloudflare API {exc.code}: {detail}") from exc
    if not document.get("success"):
        raise DomainGovernanceError(f"Cloudflare API rejected request: {document}")
    return document


def apply_dns_records() -> dict[str, Any]:
    policy = _policy()
    provider = policy.get("dnsProvider") or {}
    token_env = str(provider.get("apiTokenEnv") or "")
    zone_env = str(provider.get("zoneIdEnv") or "")
    token = os.environ.get(token_env, "").strip()
    zone_id = os.environ.get(zone_env, "").strip()
    if not token or not zone_id:
        raise DomainGovernanceError(
            f"GATE_BLOCK: {token_env} and {zone_env} are required to apply DNS"
        )

    changes: list[dict[str, str]] = []
    for record in desired_dns_records(require_addresses=True):
        query = urllib.parse.urlencode(
            {"type": record["type"], "name": record["name"]}
        )
        existing = _cloudflare_request(
            "GET",
            f"/zones/{zone_id}/dns_records?{query}",
            token=token,
        ).get("result") or []
        candidates = existing
        if record["type"] == "CAA":
            expected_data = record["data"]
            candidates = [
                item
                for item in existing
                if int((item.get("data") or {}).get("flags", -1))
                == int(expected_data["flags"])
                and str((item.get("data") or {}).get("tag") or "")
                == str(expected_data["tag"])
                and str((item.get("data") or {}).get("value") or "")
                == str(expected_data["value"])
            ]
        existing_id = str(candidates[0].get("id") or "") if candidates else ""
        for duplicate in candidates[1:]:
            duplicate_id = str(duplicate.get("id") or "")
            if duplicate_id:
                _cloudflare_request(
                    "DELETE",
                    f"/zones/{zone_id}/dns_records/{duplicate_id}",
                    token=token,
                )
        if existing_id:
            _cloudflare_request(
                "PUT",
                f"/zones/{zone_id}/dns_records/{existing_id}",
                token=token,
                payload=record,
            )
            action = "updated"
        else:
            _cloudflare_request(
                "POST",
                f"/zones/{zone_id}/dns_records",
                token=token,
                payload=record,
            )
            action = "created"
        changes.append(
            {"type": str(record["type"]), "name": str(record["name"]), "action": action}
        )
    return {
        "schema": "quwoquan.domain-governance-apply-receipt",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "zone": policy["registrableDomain"],
        "changes": changes,
    }


def verify_live_state(*, verify_tls: bool) -> dict[str, Any]:
    policy = _policy()
    expected_by_target = {
        target: _profile_addresses(
            policy,
            target=target,
            require_values=True,
        )
        for target in ALL_TARGETS
    }
    issues: list[str] = []
    topology = load_environment_topology()
    host_expectations: dict[str, tuple[str, str]] = {}
    for target_name in ALL_TARGETS:
        for raw_url in (get_target(topology, target_name).get("publicBases") or {}).values():
            host = urllib.parse.urlsplit(str(raw_url)).hostname
            if host:
                host_expectations[host] = expected_by_target[target_name]
    resolved: dict[str, list[str]] = {}
    for host, expected_addresses in sorted(host_expectations.items()):
        expected_address, expected_ipv6_address = expected_addresses
        try:
            addresses = sorted(
                {item[4][0] for item in socket.getaddrinfo(host, None)}
            )
        except socket.gaierror:
            addresses = []
        resolved[host] = addresses
        if expected_address not in addresses or expected_ipv6_address not in addresses:
            issues.append(
                f"{host} must resolve to {expected_address} and "
                f"{expected_ipv6_address}, got {addresses or ['<empty>']}"
            )

    caa_evidence: dict[str, list[str]] = {}
    for name in sorted(
        {
            str(policy["registrableDomain"]),
            *(
                str(profile["apex"])
                for profile in (policy.get("tlsProfiles") or {}).values()
                if isinstance(profile, dict)
            ),
        }
    ):
        result = subprocess.run(
            ["dig", "+short", "CAA", name],
            text=True,
            capture_output=True,
            check=False,
        )
        rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
        caa_evidence[name] = rows
        if not any("letsencrypt.org" in row for row in rows):
            issues.append(f"{name} CAA must authorize letsencrypt.org")

    mail_evidence: dict[str, dict[str, list[str]]] = {}
    mail_guard = policy.get("nonProdMailGuard") or {}
    for profile in (policy.get("tlsProfiles") or {}).values():
        if not isinstance(profile, dict):
            continue
        if profile.get("target") == "prod-hosted":
            continue
        name = str(profile["apex"])
        by_type: dict[str, list[str]] = {}
        for record_type in ("MX", "TXT"):
            result = subprocess.run(
                ["dig", "+short", record_type, name],
                text=True,
                capture_output=True,
                check=False,
            )
            by_type[record_type] = [
                row.strip() for row in result.stdout.splitlines() if row.strip()
            ]
        mail_evidence[name] = by_type
        if not any(
            row.startswith("0 ") and row.rstrip(".").endswith(" 0")
            or row == "0 ."
            for row in by_type["MX"]
        ):
            issues.append(f"{name} must publish null MX")
        expected_spf = str(mail_guard.get("spf") or "")
        if not any(expected_spf in row for row in by_type["TXT"]):
            issues.append(f"{name} must publish {expected_spf}")

    reverse_evidence: dict[str, str] = {}
    for address in sorted(
        {
            item
            for addresses in expected_by_target.values()
            for item in addresses
        }
    ):
        try:
            reverse_name = socket.gethostbyaddr(address)[0].rstrip(".").lower()
        except (socket.herror, socket.gaierror):
            reverse_name = ""
        reverse_evidence[address] = reverse_name
        if any(
            token in reverse_name
            for token in (".internal", ".local", "localhost", "corp", "lan")
        ):
            issues.append(
                f"{address} reverse DNS must not expose internal asset naming"
            )

    tls_evidence: list[dict[str, Any]] = []
    if verify_tls:
        for target_name in LOCAL_TARGETS:
            try:
                tls_evidence.append(verify_certificate(target_name))
            except PublicDomainTlsError as exc:
                issues.append(str(exc))

    payload = {
        "schema": "quwoquan.domain-governance-live-evidence",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "dns": resolved,
        "caa": caa_evidence,
        "mail": mail_evidence,
        "reverseDns": reverse_evidence,
        "tls": tls_evidence,
        "status": "ok" if not issues else "blocked",
        "issues": issues,
    }
    if issues:
        raise DomainGovernanceError(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    subparsers.add_parser("apply")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--skip-tls", action="store_true")
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            payload: Any = {
                "schema": "quwoquan.domain-governance-plan",
                "records": desired_dns_records(require_addresses=True),
            }
        elif args.command == "apply":
            payload = apply_dns_records()
        else:
            payload = verify_live_state(verify_tls=not args.skip_tls)
        if args.report:
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except DomainGovernanceError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
