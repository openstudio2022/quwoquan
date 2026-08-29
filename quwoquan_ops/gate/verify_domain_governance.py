#!/usr/bin/env python3
"""统一域名拓扑、DNS/TLS 与消费者投影静态门禁。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.domain_governance import (
    EDGE_ADDRESS_ABSENT,
    DomainGovernanceError,
    desired_dns_records,
    dns_zones,
    loopback_dns_targets,
    pending_dns_scopes,
    prod_edge_dns_targets,
    zone_record_names,
)
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.dns_provider import (
    DnsProviderError,
    provider_for_kind,
    registered_kinds,
)
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
from quwoquan_ops.gate.verify_domain_model_storage_governance import (
    collect_storage_governance_issues,
)


RETIRED_AUTHORITY_TOKENS = (
    "quwoquan-env.test",
    "app.quwoquan.com",
    "realtime.quwoquan.com",
)
# 门禁探针必须过 `is_global` 校验，所以不能用 RFC 5737 文档地址；这里取 RFC 7526
# 已废弃的 6to4 中继 anycast 地址——它可路由但不会是任何人的生产 edge。
GATE_PROBE_EDGE_ADDRESS = "192.88.99.1"
PRIVATE_TRUST_TOKENS = (
    "QWQ_ANDROID_LOCAL_ENV_CA",
    "local_env_debug_root",
    "install-ios-simulator-ca",
    "materialize-app-trust-bundle",
    "badCertificateCallback",
    "SecurityContext.defaultContext.setTrustedCertificatesBytes",
    "object-storage-ca.crt",
    "QWQ_LOCAL_UPLOAD_LOCAL_HOST",
    "ssl._create_unverified_context",
    "socket.getaddrinfo =",
)
LOCAL_MANAGED_TRUST_TOKEN = "OBJECT_STORAGE_CA_FILE"
LOCAL_MANAGED_TRUST_OWNERS = {
    "quwoquan_ops/cli/lib/local_environment_object_storage.py",
    "quwoquan_ops/cli/stackctl.py",
    "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
}
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
    issues.extend(collect_storage_governance_issues(ROOT))
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
    provider_kind = str(dns_provider.get("kind") or "")
    if provider_kind not in registered_kinds():
        issues.append(
            "dnsProvider.kind must name a registered neutral provider "
            f"implementation; registered: {registered_kinds()}"
        )
    if int(dns_provider.get("minimumTtlSeconds") or 0) <= 0:
        issues.append("dnsProvider.minimumTtlSeconds must be positive")
    if str(policy.get("prodEdgeAddressEnv") or "") != "QWQ_PROD_EDGE_IPV4":
        issues.append(
            "production edge address must come from the protected "
            "QWQ_PROD_EDGE_IPV4 input"
        )
    resolvers = policy.get("publicResolvers")
    if not isinstance(resolvers, list) or len(resolvers) < 2:
        issues.append(
            "publicResolvers must list at least two independent DoH resolvers"
        )
    else:
        # 只数个数不够：用权威服务商自家的解析器去核对自家的写入，等于自证。
        try:
            vendor_tokens = provider_for_kind(provider_kind).vendor_hostname_tokens
        except Exception:  # noqa: BLE001 - kind 非法已在上面报过
            vendor_tokens = ()
        for resolver in resolvers:
            hostname = (urlsplit(str(resolver)).hostname or "").lower()
            if any(token in hostname for token in vendor_tokens):
                issues.append(
                    f"publicResolvers must stay independent of {provider_kind}; "
                    f"{hostname} belongs to the authoritative provider"
                )
        if len({urlsplit(str(r)).hostname for r in resolvers}) < 2:
            issues.append("publicResolvers must not repeat the same resolver host")
    mail_guards = policy.get("mailGuards")
    if not isinstance(mail_guards, dict) or not mail_guards:
        issues.append("mailGuards must declare the canonical mail-guard modes")
        mail_guards = {}
    for guard_name, guard in mail_guards.items():
        if not isinstance(guard, dict) or not str(guard.get("spf") or "").strip():
            issues.append(f"mailGuards[{guard_name}].spf is required")
        if not isinstance(guard, dict) or not str(guard.get("dmarc") or "").strip():
            issues.append(f"mailGuards[{guard_name}].dmarc is required")
        elif "p=reject" not in str(guard["dmarc"]):
            issues.append(
                f"mailGuards[{guard_name}].dmarc must reject header-From spoofing"
            )
    caa_profiles = policy.get("caaProfiles")
    if not isinstance(caa_profiles, dict) or not caa_profiles:
        issues.append("caaProfiles must declare the canonical CAA record sets")
        caa_profiles = {}
    deny_all = caa_profiles.get("deny-all")
    if not isinstance(deny_all, list) or not any(
        isinstance(entry, dict)
        and str(entry.get("tag") or "") == "issue"
        and str(entry.get("value") or "") == ";"
        for entry in deny_all or []
    ):
        issues.append(
            "caaProfiles must offer a deny-all profile so zones without public "
            "certificates block every CA"
        )
    if "caa" in policy:
        issues.append(
            "the legacy flat caa list is retired; zones must name a caaProfile"
        )
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
    if challenge_authority.get("forbidNonChallengeMutation") is not True:
        issues.append(
            "ACME challenge authority must forbid mutating anything other than "
            "_acme-challenge records"
        )
    if str(challenge_authority.get("providerEnforcement") or "") not in {
        "credential-isolation-only",
        "provider-enforced-prefix",
    }:
        issues.append(
            "ACME challenge authority must state how far the DNS provider can "
            "actually enforce the challenge scope"
        )
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
    # 门禁只判仓库事实，因此两种寻址场景都显式传参，绝不读 QWQ_PROD_EDGE_IPV4：
    # 让结果依赖运行环境会在生产接线完成的那一刻把这个门禁变成永久红灯。
    absent_edge_records = desired_dns_records(EDGE_ADDRESS_ABSENT)
    dns_records = desired_dns_records(GATE_PROBE_EDGE_ADDRESS)
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
    # 白名单而非黑名单：逐个列举厂商字段永远滞后于新增字段。
    neutral_record_fields = {"type", "name", "content", "data", "ttl", "priority"}
    for record in dns_records:
        extra = sorted(set(record) - neutral_record_fields)
        if extra:
            issues.append(
                "DNS plan records must stay provider-neutral; "
                f"{record['type']} {record['name']} carries {extra}"
            )

    zones = dns_zones()
    zone_by_target = {str(zone["target"]): zone for zone in zones}
    expected_zone_targets = {
        *(ENVIRONMENT_CANONICAL_TARGET[environment] for environment in ENVIRONMENTS),
        "prod-sim",
    }
    if set(zone_by_target) != expected_zone_targets:
        issues.append(
            "dnsZones must cover every canonical environment target exactly once; "
            f"expected {sorted(expected_zone_targets)}, got {sorted(zone_by_target)}"
        )
    if set(loopback_dns_targets()) & set(prod_edge_dns_targets()):
        issues.append("a DNS zone must not be both loopback and prod-edge addressed")
    if set(prod_edge_dns_targets()) != {"prod-hosted"}:
        issues.append("only prod-hosted may resolve to the production edge address")
    absent_pending = {item["scope"] for item in pending_dns_scopes(EDGE_ADDRESS_ABSENT)}
    if "prod" not in absent_pending:
        issues.append(
            "without an injected edge address the production zone must report "
            "pending instead of silently planning nothing"
        )
    if pending_dns_scopes(GATE_PROBE_EDGE_ADDRESS):
        issues.append(
            "an injected edge address must clear every pending scope; "
            f"still pending: {sorted(pending_dns_scopes(GATE_PROBE_EDGE_ADDRESS))}"
        )
    prod_zone = zone_by_target.get("prod-hosted") or {}
    if prod_zone:
        absent_prod_addresses = [
            record
            for record in absent_edge_records
            if str(record["type"]) in {"A", "AAAA"}
            and str(record["name"]) in set(zone_record_names(prod_zone))
        ]
        if absent_prod_addresses:
            issues.append(
                "without an injected edge address the production zone must plan "
                "no address record at all; got "
                f"{[record['name'] for record in absent_prod_addresses]}"
            )
    for target_name, zone in sorted(zone_by_target.items()):
        declared_names = set(zone_record_names(zone))
        if str(zone.get("apex") or "") not in declared_names:
            issues.append(f"dnsZones[{zone.get('scope')}] must cover its own apex")
        topology_hosts = {
            urlsplit(str(value)).hostname
            for value in (
                get_target(topology, target_name).get("publicBases") or {}
            ).values()
        }
        for host in sorted(item for item in topology_hosts if item):
            covered = host in declared_names or any(
                name.startswith("*.") and host.endswith(name[1:])
                for name in declared_names
            )
            if not covered:
                issues.append(
                    f"dnsZones[{zone.get('scope')}] does not cover topology host {host}"
                )
        public_web_host = urlsplit(
            str(
                (get_target(topology, target_name).get("publicBases") or {}).get(
                    "publicWeb"
                )
                or ""
            )
        ).hostname
        if public_web_host and str(zone.get("apex") or "") != public_web_host:
            issues.append(
                f"dnsZones[{zone.get('scope')}].apex must equal the canonical "
                f"publicWeb host {public_web_host}"
            )
        apex = str(zone.get("apex") or "")
        for follower in zone.get("apexFollowers") or []:
            name = str(follower)
            if not name.endswith(f".{apex}"):
                issues.append(
                    f"dnsZones[{zone.get('scope')}] apexFollowers must live under "
                    f"{apex}; got {name}"
                )
            if name not in declared_names:
                issues.append(
                    f"dnsZones[{zone.get('scope')}] apexFollowers must receive the "
                    f"same address records as the apex; {name} is uncovered"
                )
    if any("aliases" in zone for zone in zones):
        issues.append(
            "CNAME aliases are retired; apex followers must share the apex "
            "address records so one edge address has exactly one expression"
        )
    if any(str(record["type"]).upper() == "CNAME" for record in dns_records):
        issues.append(
            "the DNS plan must not mix CNAME with address records on managed names"
        )

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
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh",
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_search_api_uat.sh",
        ROOT
        / "quwoquan_app/scripts/gamma/"
        "run_local_gamma_profile_proposal_api_uat.sh",
        ROOT
        / "quwoquan_app/scripts/gamma/"
        "run_local_gamma_assistant_learning_api_uat.sh",
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
    gamma_device_uat = (
        ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh"
    ).read_text(encoding="utf-8")
    if "require_canonical_endpoint gateway" not in gamma_device_uat:
        issues.append("Gamma device-UAT endpoint overrides must be canonical-equality checked")

    tls_profiles = policy.get("tlsProfiles") or {}
    local_profile = tls_profiles.get("local-managed")
    if not isinstance(local_profile, dict):
        issues.append("local-managed TLS profile is required")
    else:
        if local_profile.get("kind") != "local-managed":
            issues.append("local-managed TLS profile kind mismatch")
        if set(local_profile.get("targets") or []) != {
            "alpha-local",
            "beta-local",
            "gamma-local",
        }:
            issues.append("local-managed TLS profile must own Alpha/Beta/Gamma local targets")
        for field in ("renewBeforeDays", "certificateDays"):
            if int(local_profile.get(field) or 0) <= 0:
                issues.append(f"local-managed.{field} must be positive")
    public_profile_targets = {
        str(profile.get("target") or "")
        for profile in tls_profiles.values()
        if isinstance(profile, dict)
        and profile.get("kind") == "dns-01-public-ca"
    }
    if public_profile_targets != {"prod-sim", "prod-hosted"}:
        issues.append(
            "DNS-01 public-CA profiles must cover prod-sim and prod-hosted "
            "exactly once each"
        )
    for profile_name, profile in tls_profiles.items():
        if not isinstance(profile, dict):
            continue
        if profile.get("certificateAutomation") == "external":
            issues.append(
                f"tlsProfiles[{profile_name}] must not defer certificate "
                "automation to an unowned external surface"
            )
    for profile_name, profile in tls_profiles.items():
        if (
            not isinstance(profile, dict)
            or profile.get("kind") != "dns-01-public-ca"
        ):
            continue
        # apex/wildcard 的唯一声明面是对应 zone；TLS profile 只能与它一致，门禁不再
        # 维护第三份 target -> apex 的硬编码映射。
        target_name = str(profile.get("target") or "")
        zone = zone_by_target.get(target_name)
        if zone is None:
            issues.append(
                f"tlsProfiles[{profile_name}] targets {target_name!r} which has no "
                "dnsZones entry to derive apex/wildcard from"
            )
            continue
        expected_apex = str(zone.get("apex") or "")
        if profile.get("apex") != expected_apex:
            issues.append(
                f"{profile_name}.apex must match dnsZones[{zone.get('scope')}].apex "
                f"({expected_apex})"
            )
        if profile.get("wildcard") != f"*.{expected_apex}":
            issues.append(f"{profile_name}.wildcard must be *.{expected_apex}")
    prod_roles = get_target(topology, "prod-hosted").get("resolvedUrlRoles") or {}
    if any(
        role.get("tlsProfile") != "public-ca-prod"
        for role in prod_roles.values()
        if isinstance(role, dict)
    ):
        issues.append("prod-hosted roles must all bind the public-ca-prod TLS profile")
    prod_tls_profile = tls_profiles.get("public-ca-prod")
    if not isinstance(prod_tls_profile, dict):
        issues.append("public-ca-prod TLS profile is required for prod-hosted")
    elif prod_tls_profile.get("kind") != "dns-01-public-ca":
        issues.append("public-ca-prod must be issued through owned DNS-01 automation")

    for target_name, zone in sorted(zone_by_target.items()):
        expects_public_certificate = target_name in public_profile_targets
        selected = str(zone.get("caa") or "")
        if expects_public_certificate and selected == "deny-all":
            issues.append(
                f"dnsZones[{zone.get('scope')}] issues public certificates and "
                "must not deny every CA"
            )
        if not expects_public_certificate and selected != "deny-all":
            issues.append(
                f"dnsZones[{zone.get('scope')}] has no public certificate and "
                "must deny every CA instead of inheriting the apex allowlist"
            )

    for path in tracked_files:
        if (
            not path.is_file()
            or path.suffix.lower() not in TEXT_SUFFIXES
            or not any(scan_root in path.parents for scan_root in PRIVATE_TRUST_SCAN_ROOTS)
        ):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        relative_path = path.relative_to(ROOT).as_posix()
        if (
            LOCAL_MANAGED_TRUST_TOKEN in source
            and relative_path not in LOCAL_MANAGED_TRUST_OWNERS
        ):
            issues.append(
                f"{relative_path} contains local-managed trust material outside "
                "the stackctl-owned object-storage path"
            )
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
                "dnsZones": [str(zone.get("scope") or "") for zone in zones],
                "dnsRecords": len(dns_records),
                "providerKind": str(dns_provider.get("kind") or ""),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cli() -> int:
    # 策略/注入值非法时也要走同一套输出契约，而不是抛栈——消费方按
    # `[verify-domain-governance] FAIL` 解析结果。
    try:
        return main()
    except (DomainGovernanceError, DnsProviderError) as exc:
        print("[verify-domain-governance] FAIL")
        print(f"  - {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
