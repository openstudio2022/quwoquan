#!/usr/bin/env python3
"""统一域名拓扑、DNS/TLS 与消费者投影静态门禁。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.domain_governance import ALL_TARGETS, desired_dns_records
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    ENVIRONMENT_CANONICAL_TARGET,
    ROLE_PATH_BASES,
    TARGETS,
    URL_FIELDS,
    get_target,
    load_environment_topology,
    validate_environment_topology,
)


RETIRED_AUTHORITY_TOKENS = (
    "quwoquan-env.test",
    "app.quwoquan.com",
    "realtime.quwoquan.com",
)
PRIVATE_TRUST_TOKENS = (
    "QWQ_ANDROID_LOCAL_ENV_CA",
    "local_env_debug_root",
    "install-ios-simulator-ca",
    "materialize-app-trust-bundle",
    "badCertificateCallback",
    "SecurityContext.defaultContext.setTrustedCertificatesBytes",
)
PRIVATE_TRUST_SCAN_ROOTS = (
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "android",
    ROOT / "quwoquan_app" / "ios",
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_ops" / "cli",
)
TEXT_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".py",
    ".sh",
    ".swift",
    ".xml",
    ".yaml",
    ".yml",
}
PUBLIC_AUTHORITY_RE = re.compile(
    r"(?:https|wss)://(?:[a-z0-9-]+\.)*quwoquan\.com(?::\d+)?",
    re.IGNORECASE,
)
GENERIC_PUBLIC_MEDIA_RE = re.compile(
    r"(?<![A-Z0-9_])(?:MEDIA_BASE_URL|MEDIA_PUBLIC_BASE_URL|"
    r"LOCAL_GAMMA_MEDIA_BASE_URL|CDN_DOMAIN)(?![A-Z0-9_])"
)
RUNTIME_AUTHORITY_PREFIXES = (
    "quwoquan_app/lib/",
    "quwoquan_app/scripts/",
    "quwoquan_app/android/",
    "quwoquan_app/ios/Runner/",
    "quwoquan_data/scripts/",
    "quwoquan_ops/cli/",
    "quwoquan_ops/environments/compose/",
    "quwoquan_ops/environments/gamma/local/",
    "quwoquan_service/services/",
    "quwoquan_service/static/",
)
RUNTIME_AUTHORITY_EXCLUDED_PARTS = (
    "/test/",
    "/tests/",
    "/generated/",
    "/contracts/",
)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [ROOT / row for row in result.stdout.splitlines() if row.strip()]


def main() -> int:
    issues: list[str] = []
    topology = load_environment_topology()
    issues.extend(validate_environment_topology(topology))
    policy = load_json_yaml(
        ROOT / "quwoquan_ops" / "environments" / "domain_governance.yaml"
    )
    if policy.get("registrableDomain") != "quwoquan.com":
        issues.append("domain governance registrableDomain must be quwoquan.com")
    for field in (
        "nonProdAddressEnv",
        "nonProdIpv6AddressEnv",
        "prodAddressEnv",
        "prodIpv6AddressEnv",
    ):
        if not re.fullmatch(r"QWQ_[A-Z0-9_]+", str(policy.get(field) or "")):
            issues.append(f"domain governance {field} must name a secret/runtime variable")
    endpoint_registry = policy.get("endpointRegistry")
    if not isinstance(endpoint_registry, list):
        issues.append("domain governance endpointRegistry must be a list")
        endpoint_registry = []
    registry_roles: list[str] = []
    registry_names: list[str] = []
    for index, endpoint in enumerate(endpoint_registry):
        if not isinstance(endpoint, dict):
            issues.append(f"endpointRegistry[{index}] must be a mapping")
            continue
        registry_roles.append(str(endpoint.get("role") or ""))
        registry_names.append(str(endpoint.get("name") or ""))
        for field in (
            "name",
            "role",
            "classification",
            "source",
            "owner",
            "exposure",
        ):
            if not str(endpoint.get(field) or "").strip():
                issues.append(f"endpointRegistry[{index}].{field} is required")
        consumers = endpoint.get("consumers")
        if not isinstance(consumers, list) or not consumers:
            issues.append(f"endpointRegistry[{index}].consumers must be non-empty")
    if sorted(registry_roles) != sorted(URL_FIELDS):
        issues.append("endpointRegistry must contain every public URL role exactly once")
    if len(registry_names) != len(set(registry_names)):
        issues.append("endpointRegistry names must be unique")
    class_registry = policy.get("urlClassRegistry")
    expected_classes = {
        "derived-deep-link",
        "oauth-callback",
        "east-west-upstream",
        "third-party",
        "test-only",
    }
    if not isinstance(class_registry, list):
        issues.append("domain governance urlClassRegistry must be a list")
        class_registry = []
    actual_classes = {
        str(item.get("classification") or "")
        for item in class_registry
        if isinstance(item, dict)
    }
    if actual_classes != expected_classes or len(class_registry) != len(actual_classes):
        issues.append("urlClassRegistry classifications must be complete and unique")
    for index, item in enumerate(class_registry):
        if not isinstance(item, dict):
            continue
        for field in ("classification", "owner", "source", "consumers"):
            if not item.get(field):
                issues.append(f"urlClassRegistry[{index}].{field} is required")

    for env_name in ENVIRONMENTS:
        target_name = ENVIRONMENT_CANONICAL_TARGET[env_name]
        public_bases = get_target(topology, target_name).get("publicBases") or {}
        if set(public_bases) != set(URL_FIELDS):
            issues.append(f"{target_name}: publicBases role set drift")
            continue
        parsed = {key: urlsplit(str(value)) for key, value in public_bases.items()}
        if parsed["realtime"].hostname != parsed["api"].hostname:
            issues.append(f"{target_name}: realtime must share api host")
        media_hosts = {
            parsed[key].hostname
            for key in ("mediaAvatar", "mediaImage", "mediaVideo", "appDownload")
        }
        if len(media_hosts) != 1:
            issues.append(f"{target_name}: avatar/image/video/download must share cdn host")
        if parsed["mediaUpload"].hostname in media_hosts:
            issues.append(f"{target_name}: media upload must keep a separate upload host")
        if parsed["publicWeb"].hostname and parsed["publicWeb"].hostname.startswith("www."):
            issues.append(f"{target_name}: canonical public web must use apex, not www")
        expected_paths = {
            role: ROLE_PATH_BASES[role]
            for role in (
                "mediaAvatar",
                "mediaImage",
                "mediaVideo",
                "appDownload",
                "legal",
            )
        }
        for role, expected_path in expected_paths.items():
            if parsed[role].path != expected_path:
                issues.append(
                    f"{target_name}: {role} path must be {expected_path}, got {parsed[role].path}"
                )

    dns_records = desired_dns_records(require_addresses=False)
    dns_names = {
        str(record["name"])
        for record in dns_records
        if record["type"] == "A"
    }
    record_identities = [
        (
            str(record["type"]),
            str(record["name"]),
            json.dumps(record.get("data") or record.get("content"), sort_keys=True),
        )
        for record in dns_records
    ]
    if len(record_identities) != len(set(record_identities)):
        issues.append("DNS plan contains duplicate record identities")
    topology_local_hosts: set[str] = set()
    for target_name in ALL_TARGETS:
        for value in (get_target(topology, target_name).get("publicBases") or {}).values():
            host = urlsplit(str(value)).hostname
            if host:
                topology_local_hosts.add(host)
    for host in topology_local_hosts:
        covered = host in dns_names or any(
            name.startswith("*.") and host.endswith(name[1:])
            for name in dns_names
        )
        if not covered:
            issues.append(f"DNS plan does not cover topology host {host}")

    for path in _tracked_files():
        if (
            path.resolve() == Path(__file__).resolve()
            or not path.is_file()
            or path.suffix.lower() not in TEXT_SUFFIXES
        ):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for token in RETIRED_AUTHORITY_TOKENS:
            if token in source:
                issues.append(f"{path.relative_to(ROOT)} contains retired authority {token}")
        relative = path.relative_to(ROOT).as_posix()
        is_runtime_source = relative.startswith(RUNTIME_AUTHORITY_PREFIXES)
        is_excluded = any(part in f"/{relative}" for part in RUNTIME_AUTHORITY_EXCLUDED_PARTS)
        if (
            is_runtime_source
            and not is_excluded
            and relative
            not in {
                "quwoquan_ops/environments/domain_governance.yaml",
                *(
                    f"quwoquan_ops/environments/{environment}/runtime.yaml"
                    for environment in ENVIRONMENTS
                ),
            }
        ):
            authorities = sorted(set(PUBLIC_AUTHORITY_RE.findall(source)))
            if authorities:
                issues.append(
                    f"{relative} defines public authorities outside runtime topology: "
                    + ", ".join(authorities)
                )
            generic_media = GENERIC_PUBLIC_MEDIA_RE.search(source)
            if generic_media:
                issues.append(
                    f"{relative} contains retired generic public media token "
                    f"{generic_media.group(0)}"
                )

    tls_profiles = policy.get("tlsProfiles") or {}
    profile_targets = {
        str(profile.get("target") or "")
        for profile in tls_profiles.values()
        if isinstance(profile, dict)
    }
    if profile_targets != set(TARGETS):
        issues.append("TLS profiles must cover every topology target exactly once")
    if len(tls_profiles) != len(profile_targets):
        issues.append("TLS profiles must not duplicate topology targets")
    for profile_name, profile in tls_profiles.items():
        if not isinstance(profile, dict):
            continue
        target_name = str(profile.get("target") or "")
        env_label = {
            "alpha-local": "alpha",
            "beta-local": "beta",
            "gamma-local": "gamma",
            "prod-sim": "sim",
            "prod-hosted": "",
        }.get(target_name)
        expected_apex = (
            f"{env_label}.quwoquan.com" if env_label else "quwoquan.com"
        )
        if profile.get("apex") != expected_apex:
            issues.append(f"{profile_name}.apex must be {expected_apex}")
        if profile.get("wildcard") != f"*.{expected_apex}":
            issues.append(f"{profile_name}.wildcard must be *.{expected_apex}")

    for scan_root in PRIVATE_TRUST_SCAN_ROOTS:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for token in PRIVATE_TRUST_TOKENS:
                if token in source:
                    issues.append(
                        f"{path.relative_to(ROOT)} contains private trust token {token}"
                    )

    if issues:
        print("[verify-domain-governance] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(
        "[verify-domain-governance] OK "
        + json.dumps(
            {
                "environments": list(ENVIRONMENTS),
                "roles": list(URL_FIELDS),
                "dnsNames": len(dns_names),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
