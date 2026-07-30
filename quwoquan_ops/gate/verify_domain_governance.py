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

from quwoquan_ops.cli.domain_governance import LOCAL_TARGETS, desired_dns_records
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    ENVIRONMENT_CANONICAL_TARGET,
    URL_GOVERNANCE_FIELDS,
    URL_FIELDS,
    get_target,
    load_environment_topology,
    validate_environment_topology,
)
from quwoquan_ops.cli.lib.media_delivery_manifest import (
    build_media_delivery_url,
    load_media_delivery_manifest,
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
    "OBJECT_STORAGE_CA_FILE",
    "object-storage-ca.crt",
    "QWQ_LOCAL_UPLOAD_LOCAL_HOST",
    "ssl._create_unverified_context",
    "socket.getaddrinfo =",
)
PRIVATE_TRUST_SCAN_ROOTS = (
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "android",
    ROOT / "quwoquan_app" / "ios",
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_ops" / "cli",
    ROOT / "quwoquan_ops" / "tests" / "acceptance" / "user_acceptance" / "service_ops",
    ROOT / "quwoquan_ops" / "tests" / "support",
    ROOT / "quwoquan_ops" / "environments" / "compose",
    ROOT / "quwoquan_data" / "scripts",
    ROOT / "quwoquan_service" / "services",
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
    media_assets = load_media_delivery_manifest()
    tracked_files = _tracked_files()
    issues.extend(validate_environment_topology(topology))
    policy = load_json_yaml(
        ROOT / "quwoquan_ops" / "environments" / "domain_governance.yaml"
    )
    if policy.get("registrableDomain") != "quwoquan.com":
        issues.append("domain governance registrableDomain must be quwoquan.com")
    if policy.get("nonProdAddress") != "127.0.0.1":
        issues.append("non-production public DNS must project canonical hosts to 127.0.0.1")
    if policy.get("nonProdIpv6Address") != "::1":
        issues.append("non-production public DNS must project canonical hosts to ::1")
    dns_provider = policy.get("dnsProvider") or {}
    challenge_authority = policy.get("acmeChallengeAuthority") or {}
    provisioning_token_env = str(dns_provider.get("apiTokenEnv") or "")
    challenge_token_env = str(challenge_authority.get("apiTokenEnv") or "")
    if provisioning_token_env != "QWQ_DNS_PROVISIONING_API_TOKEN":
        issues.append("DNS record provisioning must use its dedicated protected token")
    if challenge_token_env != "QWQ_ACME_DNS_API_TOKEN":
        issues.append("ACME DNS-01 must use its dedicated challenge-only token")
    if not challenge_token_env or challenge_token_env == provisioning_token_env:
        issues.append("DNS provisioning and ACME challenge tokens must be isolated")
    if challenge_authority.get("mode") != "scoped-dns-api-token":
        issues.append("ACME challenge authority must use a scoped DNS API token")
    if challenge_authority.get("requiredNamePrefix") != "_acme-challenge":
        issues.append("ACME token scope must be limited to _acme-challenge")
    if challenge_authority.get("forbidProductionZoneMutation") is not True:
        issues.append("ACME challenge authority must forbid production zone mutation")
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
        actual_fields = set(endpoint)
        if actual_fields != URL_GOVERNANCE_FIELDS:
            issues.append(
                f"endpointRegistry[{index}] must contain only governance fields; "
                f"got {sorted(actual_fields)}"
            )
        for field in ("name", "role", "classification", "owner", "exposure"):
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

    derived_link_ownership = policy.get("derivedLinkOwnership")
    if not isinstance(derived_link_ownership, dict):
        issues.append("derivedLinkOwnership must be a mapping")
    else:
        expected_link_ownership = {
            "originRole": "publicWeb",
            "pathSource": (
                "quwoquan_service/contracts/metadata/_shared/link_templates.yaml"
            ),
            "serviceProjection": (
                "quwoquan_service/generated/linktemplates/link_templates.g.go"
            ),
        }
        for field, expected in expected_link_ownership.items():
            if derived_link_ownership.get(field) != expected:
                issues.append(f"derivedLinkOwnership.{field} must be {expected}")
        consumers = derived_link_ownership.get("consumers")
        if not isinstance(consumers, list) or not consumers:
            issues.append("derivedLinkOwnership.consumers must be non-empty")
        for field in ("pathSource", "serviceProjection"):
            relative = derived_link_ownership.get(field)
            if isinstance(relative, str) and not (ROOT / relative).is_file():
                issues.append(f"derivedLinkOwnership.{field} does not exist: {relative}")

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
        for asset in media_assets:
            try:
                delivery_url = build_media_delivery_url(public_bases, asset)
            except (KeyError, TypeError, ValueError) as exc:
                issues.append(
                    f"{target_name}: media delivery contract rejected "
                    f"{asset.get('logicalAssetId', '<unknown>')}: {exc}"
                )
                continue
            if re.search(r"/media/([^/]+)/media/\1(?:/|$)", delivery_url):
                issues.append(
                    f"{target_name}: media delivery URL repeats its role path: "
                    f"{delivery_url}"
                )
        try:
            attachment_url = build_media_delivery_url(
                public_bases,
                {
                    "mediaType": "attachment",
                    "publicSliceKey": (
                        "media/attachment/s/asset/domain-governance/v1/source.pdf"
                    ),
                    "version": 1,
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(
                f"{target_name}: attachment delivery contract rejected: {exc}"
            )
            continue
        expected_attachment_prefix = (
            f"{parsed['mediaImage'].scheme}://{parsed['mediaImage'].netloc}"
            "/media/attachment/"
        )
        if not attachment_url.startswith(expected_attachment_prefix):
            issues.append(
                f"{target_name}: attachment delivery must use the canonical CDN origin"
            )
    dns_records = desired_dns_records()
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
    for target_name in LOCAL_TARGETS:
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

    for path in tracked_files:
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

    profile_service_path = (
        ROOT
        / "quwoquan_service/services/user-service/internal/account/user_account/"
        "application/account_orchestration/profile_service.go"
    )
    profile_service_source = profile_service_path.read_text(encoding="utf-8")
    if '"/u/"' in profile_service_source:
        issues.append(
            "user profile links must not duplicate the metadata-owned /u/{username} path"
        )
    if "linktemplates.UserWebPath(handle)" not in profile_service_source:
        issues.append(
            "user profile links must consume the generated link template builder"
        )

    topology_projection_consumers = (
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_t4.sh",
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_search_api_uat.sh",
        ROOT
        / "quwoquan_app/scripts/gamma/"
        "run_local_gamma_profile_proposal_api_uat.sh",
        ROOT
        / "quwoquan_app/scripts/gamma/"
        "run_local_gamma_assistant_learning_api_uat.sh",
        ROOT
        / "quwoquan_data/scripts/content/release/canonical/"
        "build_lookup_indexes.py",
    )
    for path in topology_projection_consumers:
        source = path.read_text(encoding="utf-8")
        if '"publicBases"' not in source:
            continue
        if (
            "load_environment_topology" not in source
            and "resolve_environment_release_target" not in source
        ):
            issues.append(
                f"{path.relative_to(ROOT)} reads source runtime publicBases "
                "instead of the canonical topology projection"
            )

    device_matrix_workflow = (
        ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
    ).read_text(encoding="utf-8")
    for retired in (
        "gamma_base_url:",
        "media_base_url:",
        "http://127.0.0.1",
        "10.0.2.2",
    ):
        if retired in device_matrix_workflow:
            issues.append(
                "App device matrix must not expose manual/private endpoint "
                f"override {retired}"
            )
    assistant_matrix = (
        ROOT
        / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "assistant-service/ci/run_assistant_device_matrix_ci.py"
    ).read_text(encoding="utf-8")
    if "canonical_gateway_base_url(env_name)" not in assistant_matrix:
        issues.append("Assistant device matrix must resolve its gateway from topology")
    chat_avatar_probe = (
        ROOT
        / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "chat-service/smoke/run_chat_avatar_e2e_probe.py"
    ).read_text(encoding="utf-8")
    if "validate_topology_endpoints(args)" not in chat_avatar_probe:
        issues.append("Chat avatar probe endpoints must be canonical-equality checked")
    for retired in (
        "CHAT_AVATAR_MEDIA_BASE_URL",
        "PROD_MEDIA_BASE_URL",
    ):
        if retired in chat_avatar_probe:
            issues.append(f"Chat avatar probe contains retired endpoint fallback {retired}")
    gamma_t4 = (
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_t4.sh"
    ).read_text(encoding="utf-8")
    if "require_canonical_endpoint gateway" not in gamma_t4:
        issues.append("Gamma T4 endpoint overrides must be canonical-equality checked")

    tls_profiles = policy.get("tlsProfiles") or {}
    profile_targets = {
        str(profile.get("target") or "")
        for profile in tls_profiles.values()
        if isinstance(profile, dict)
    }
    if profile_targets != set(LOCAL_TARGETS):
        issues.append("DNS-01 TLS profiles must cover every local topology target exactly once")
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
    prod_roles = get_target(topology, "prod-hosted").get("resolvedUrlRoles") or {}
    if any(
        role.get("tlsProfile") != "public-ca-prod"
        for role in prod_roles.values()
        if isinstance(role, dict)
    ):
        issues.append("prod-hosted roles must use externally managed public-ca-prod")

    for path in tracked_files:
        if (
            not path.is_file()
            or path.suffix.lower() not in TEXT_SUFFIXES
            or not any(scan_root in path.parents for scan_root in PRIVATE_TRUST_SCAN_ROOTS)
        ):
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
