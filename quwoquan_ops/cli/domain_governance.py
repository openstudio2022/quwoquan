#!/usr/bin/env python3
"""从环境拓扑派生、应用并验证 quwoquan.com DNS 治理状态。"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
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
from quwoquan_ops.cli.lib.dns_provider import (
    DnsProviderError,
    build_provider,
    caa_value,
    parse_caa_text,
    record_identity,
)
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.public_domain_tls import (
    PublicDomainTlsError,
    verify_certificate,
)


POLICY_PATH = ROOT / "quwoquan_ops" / "environments" / "domain_governance.yaml"
# 显式声明「本次没有 edge 地址」，与「未传参、回退读环境变量」区分开。
EDGE_ADDRESS_ABSENT = ""


class DomainGovernanceError(RuntimeError):
    pass


def _policy() -> dict[str, Any]:
    value = load_json_yaml(POLICY_PATH)
    if not isinstance(value, dict) or value.get("schema") != "quwoquan.domain-governance":
        raise DomainGovernanceError(f"invalid domain policy: {POLICY_PATH}")
    return value


def dns_zones() -> list[dict[str, Any]]:
    """公网 DNS 记录的唯一声明面。"""
    zones = _policy().get("dnsZones")
    if not isinstance(zones, list) or not zones:
        raise DomainGovernanceError("domain policy must declare dnsZones")
    for zone in zones:
        if not isinstance(zone, dict):
            raise DomainGovernanceError("每个 dnsZones 条目必须是映射")
    return [zone for zone in zones if isinstance(zone, dict)]


def _zone_targets(*, addressing: str | None = None) -> tuple[str, ...]:
    return tuple(
        str(zone["target"])
        for zone in dns_zones()
        if addressing is None or str(zone.get("addressing")) == addressing
    )


# 按解析目的地划分的 target 子集。写成函数而非模块级常量：常量会在 import 时读策略
# 文件，既让消费方无法在替换策略后重新派生，也把策略错误抛在 main() 的兜底之外。
def loopback_dns_targets() -> tuple[str, ...]:
    return _zone_targets(addressing="loopback")


def prod_edge_dns_targets() -> tuple[str, ...]:
    return _zone_targets(addressing="prod-edge")


def tls_verifiable_targets() -> tuple[str, ...]:
    """有证书声明、因此 verify 必须核对的 target 全集。

    从 tlsProfiles 派生而非另立清单：另立会让新增 profile（例如生产证书）默默落在
    覆盖面之外，看起来通过其实没验。
    """
    profiles = _policy().get("tlsProfiles") or {}
    targets: list[str] = []
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        declared = profile.get("targets")
        if isinstance(declared, list):
            targets.extend(str(item) for item in declared)
        elif profile.get("target"):
            targets.append(str(profile["target"]))
    return tuple(sorted(set(targets)))


def _loopback_addresses(policy: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            str(policy.get("nonProdAddress") or ""),
            str(policy.get("nonProdIpv6Address") or ""),
        )
        if value
    )


def _prod_edge_address(policy: dict[str, Any], override: str | None) -> str | None:
    """生产 edge 地址是部署时事实：只从受保护变量或显式入参取，不入仓库。

    入参有三种语义，调用方必须选准：`None` 表示「本次不覆盖，回退读受保护变量」，
    `EDGE_ADDRESS_ABSENT` 表示「显式声明本次没有地址」（判仓库事实时用它，否则结
    论会随运行环境漂移），其余表示显式给定地址。
    """
    raw = override
    if raw is None:
        raw = os.environ.get(str(policy.get("prodEdgeAddressEnv") or ""), "")
    candidate = str(raw or "").strip()
    if not candidate:
        return None
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise DomainGovernanceError(
            f"GATE_BLOCK: prod edge address {candidate!r} is not a valid IP address"
        ) from exc
    if parsed.version != 4:
        raise DomainGovernanceError(
            "GATE_BLOCK: prod edge address must be IPv4 until an AAAA edge exists"
        )
    if not parsed.is_global:
        raise DomainGovernanceError(
            "GATE_BLOCK: prod edge address must be a globally routable address"
        )
    return str(parsed)


def _zone_addresses(
    zone: dict[str, Any],
    policy: dict[str, Any],
    prod_edge_address: str | None,
) -> tuple[str, ...]:
    addressing = str(zone.get("addressing") or "")
    if addressing == "loopback":
        return _loopback_addresses(policy)
    if addressing == "prod-edge":
        return (prod_edge_address,) if prod_edge_address else ()
    raise DomainGovernanceError(
        f"dnsZones[{zone.get('scope')}] has unsupported addressing {addressing!r}"
    )


def zone_record_names(zone: dict[str, Any]) -> list[str]:
    """该 zone 需要地址记录的名字集合（apex/wildcard 或 topology 派生 host）。

    `apexFollowers` 用地址记录而非 CNAME 跟随 apex：同一份 edge 地址事实只有一种
    表达，且 apex 地址缺席时 follower 一同缺席，不会留下指向空名字的悬挂别名。
    """
    shape = str(zone.get("recordShape") or "")
    followers = {
        str(name).strip()
        for name in zone.get("apexFollowers") or []
        if str(name).strip()
    }
    if shape == "apex-and-wildcard":
        return sorted({str(zone["apex"]), str(zone["wildcard"]), *followers})
    if shape == "explicit-topology-hosts":
        roles = get_target(
            load_environment_topology(), str(zone["target"])
        ).get("resolvedUrlRoles") or {}
        hosts = {
            str(role.get("host") or "").strip()
            for role in roles.values()
            if isinstance(role, dict) and str(role.get("host") or "").strip()
        }
        hosts.add(str(zone["apex"]))
        hosts.update(followers)
        return sorted(hosts)
    raise DomainGovernanceError(
        f"dnsZones[{zone.get('scope')}] has unsupported recordShape {shape!r}"
    )


def caa_profile(
    zone: dict[str, Any], policy: dict[str, Any] | None = None
) -> tuple[dict[str, Any], ...]:
    """该 zone 的 CAA 记录集。

    每个 zone 必须显式选一个 profile：签发公共证书的选允许清单，其余选 `deny-all`，
    这样非生产子域不会因为省略 CAA 而继承 apex 的允许清单。
    """
    resolved = policy if policy is not None else _policy()
    profiles = resolved.get("caaProfiles") or {}
    name = str(zone.get("caa") or "")
    entries = profiles.get(name)
    if not isinstance(entries, list) or not entries:
        raise DomainGovernanceError(
            f"dnsZones[{zone.get('scope')}] references unknown caaProfile {name!r}"
        )
    return tuple(entries)


def _ttl(policy: dict[str, Any], desired: int) -> int:
    minimum = int((policy.get("dnsProvider") or {}).get("minimumTtlSeconds") or 0)
    return max(int(desired), minimum)


def desired_dns_records(prod_edge_address: str | None = None) -> list[dict[str, Any]]:
    """从 dnsZones 派生完整期望记录集。

    生产 A 记录依赖部署时注入的 edge 地址；未注入时该 zone 的地址记录保持缺席
    （由 `plan` 显式报告 pending），不产出占位值。
    """
    policy = _policy()
    mail_guards = policy.get("mailGuards") or {}
    edge_address = _prod_edge_address(policy, prod_edge_address)
    records: list[dict[str, Any]] = []
    for zone in dns_zones():
        addresses = _zone_addresses(zone, policy, edge_address)
        for name in zone_record_names(zone):
            for address in addresses:
                records.append(
                    {
                        "type": "AAAA" if ":" in address else "A",
                        "name": name,
                        "content": address,
                        "ttl": _ttl(policy, 600),
                    }
                )
        guard_name = str(zone.get("mailGuard") or "")
        guard = mail_guards.get(guard_name)
        if not isinstance(guard, dict):
            raise DomainGovernanceError(
                f"dnsZones[{zone.get('scope')}] references unknown mailGuard "
                f"{guard_name!r}"
            )
        for required in ("spf", "dmarc"):
            if not str(guard.get(required) or "").strip():
                raise DomainGovernanceError(
                    f"mailGuards[{guard_name}].{required} is required so every apex "
                    "denies both envelope and header-From spoofing"
                )
        if guard.get("nullMx"):
            records.append(
                {
                    "type": "MX",
                    "name": str(zone["apex"]),
                    "content": str(guard["nullMx"]),
                    "priority": 0,
                    "ttl": _ttl(policy, 3600),
                }
            )
        records.append(
            {
                "type": "TXT",
                "name": str(zone["apex"]),
                "content": str(guard["spf"]),
                "ttl": _ttl(policy, 3600),
            }
        )
        records.append(
            {
                "type": "TXT",
                "name": f"_dmarc.{zone['apex']}",
                "content": str(guard["dmarc"]),
                "ttl": _ttl(policy, 3600),
            }
        )
        for caa in caa_profile(zone, policy):
            records.append(
                {
                    "type": "CAA",
                    "name": str(zone["apex"]),
                    "data": {
                        "flags": int(caa["flags"]),
                        "tag": str(caa["tag"]),
                        "value": str(caa["value"]),
                    },
                    "ttl": _ttl(policy, 3600),
                }
            )
    return records


def pending_dns_scopes(prod_edge_address: str | None = None) -> list[dict[str, str]]:
    """如实报告哪些 zone 因缺少部署时输入而未产出地址记录。

    判据就是 `_zone_addresses` 的结果为空，与 plan/verify 共用同一函数：另写一份
    「哪些 zone 算 pending」的规则会让两处对同一现实给出不同结论。
    """
    policy = _policy()
    edge_address = _prod_edge_address(policy, prod_edge_address)
    return [
        {
            "scope": str(zone.get("scope") or ""),
            "reason": (
                f"{policy.get('prodEdgeAddressEnv')} is not provided; "
                "address records stay absent"
            ),
        }
        for zone in dns_zones()
        if not _zone_addresses(zone, policy, edge_address)
    ]


def _resolvers(policy: dict[str, Any]) -> list[str]:
    resolvers = [
        str(item).strip()
        for item in policy.get("publicResolvers") or []
        if str(item).strip()
    ]
    if not resolvers:
        raise DomainGovernanceError("domain policy must declare publicResolvers")
    return resolvers


def _resolver_answer(resolver: str, name: str, record_type: str) -> list[str]:
    query = urllib.parse.urlencode({"name": name, "type": record_type})
    request = urllib.request.Request(
        f"{resolver}?{query}",
        headers={"Accept": "application/dns-json"},
    )
    last_error: Exception | None = None
    document: dict[str, Any] | None = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                decoded = json.loads(response.read().decode("utf-8"))
            if isinstance(decoded, dict):
                document = decoded
                break
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
    if document is None:
        raise DomainGovernanceError(
            f"public DNS-over-HTTPS query failed for {record_type} {name} "
            f"via {resolver}"
        ) from last_error
    if int(document.get("Status", -1)) not in {0, 3}:
        raise DomainGovernanceError(
            f"public DNS-over-HTTPS query returned status "
            f"{document.get('Status')} for {record_type} {name} via {resolver}"
        )
    return sorted(
        {
            str(answer.get("data") or "").strip()
            for answer in document.get("Answer") or []
            if str(answer.get("data") or "").strip()
        }
    )


def _dns_over_https_by_resolver(name: str, record_type: str) -> dict[str, list[str]]:
    """跨多个公共解析器读取权威答案，任一解析器不可达即失败（fail-closed）。"""
    policy = _policy()
    by_resolver: dict[str, list[str]] = {}
    for resolver in _resolvers(policy):
        by_resolver[resolver] = _resolver_answer(resolver, name, record_type)
    return by_resolver


def _live_value(record: dict[str, Any]) -> str:
    if str(record["type"]).upper() == "CAA" and isinstance(record.get("data"), dict):
        return caa_value(record["data"])
    return str(record.get("content") or "")


DESTRUCTIVE_DNS_ACTIONS = frozenset({"retuned", "updated", "removed"})
# 这些类型在一个 (name, type) 分组内语义上是「一组等价目标」或「zone 级授权」，
# 必须完全由计划拥有，多余的值就是漂移。TXT 不在此列：同一个名字上的 TXT 会同时
# 承载备案与第三方站点校验令牌，我们只拥有自己声明的那几条。
EXCLUSIVE_RECORD_TYPES = frozenset({"A", "AAAA", "CNAME", "CAA", "MX"})


def _txt_version_token(value: str) -> str:
    """取 TXT 值的 `v=<method>` 归属标记；不带该前缀的一律视为他人所有。"""
    text = str(value).strip()
    if not text:
        return ""
    head = text.split(None, 1)[0].rstrip(";").lower()
    return head if head.startswith("v=") else ""


def _owned_existing(
    record_type: str,
    expected_records: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把该分组的现存记录分成「计划拥有」与「他人所有」两份。"""
    if record_type in EXCLUSIVE_RECORD_TYPES:
        return list(existing), []
    owned_tokens = {
        token
        for token in (
            _txt_version_token(str(record.get("content") or ""))
            for record in expected_records
        )
        if token
    }
    owned: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    for item in existing:
        token = _txt_version_token(str(item.get("content") or ""))
        (owned if token and token in owned_tokens else foreign).append(item)
    return owned, foreign


def production_record_names() -> frozenset[str]:
    """生产 zone 会被 apply 触碰的记录名。"""
    names: set[str] = set()
    for zone in dns_zones():
        if str(zone.get("addressing") or "") != "prod-edge":
            continue
        apex = str(zone["apex"])
        names.update(zone_record_names(zone))
        names.add(apex)
        names.add(f"_dmarc.{apex}")
    return frozenset(name.rstrip(".").lower() for name in names)


def apply_dns_records(*, allow_production_mutation: bool = False) -> dict[str, Any]:
    """把期望记录集声明式收敛到权威 DNS。

    只有「本次存在期望记录」的 `(name, type)` 分组才参与收敛；期望缺席的分组
    保持原样，避免把缺少部署时输入误解为「要求清空」。

    覆盖或删除现存生产记录是破坏性动作，必须由调用方显式授权。收敛先整体算出
    将发生的动作，`allow_production_mutation` 为假且其中含生产侧覆盖/删除时先行
    fail closed，不做部分收敛；首次下发生产记录不属于破坏性动作。
    """
    policy = _policy()
    provider_config = policy.get("dnsProvider") or {}
    token_env = str(provider_config.get("apiTokenEnv") or "")
    credential = os.environ.get(token_env, "").strip()
    # zone 就是策略已声明的注册域，再要一份部署时输入只会引入第二真相源。
    zone = str(policy.get("registrableDomain") or "").strip()
    if not credential:
        raise DomainGovernanceError(
            f"GATE_BLOCK: {token_env} is required to apply DNS"
        )
    try:
        provider = build_provider(
            kind=str(provider_config.get("kind") or ""),
            credential=credential,
            zone=zone,
        )
    except DnsProviderError as exc:
        raise DomainGovernanceError(str(exc)) from exc

    desired = desired_dns_records()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in desired:
        key = (str(record["name"]).rstrip(".").lower(), str(record["type"]).upper())
        grouped.setdefault(key, []).append(record)

    planned: list[dict[str, Any]] = []
    observed_foreign: list[dict[str, Any]] = []
    try:
        for (name, record_type), expected_records in sorted(grouped.items()):
            existing = provider.list_records(name=name, record_type=record_type)
            owned, foreign = _owned_existing(record_type, expected_records, existing)
            observed_foreign.extend(
                {
                    "type": record_type,
                    "name": name,
                    "value": str(item.get("content") or ""),
                }
                for item in foreign
            )
            existing_by_identity = {record_identity(item): item for item in owned}
            expected_identities = {
                record_identity(item) for item in expected_records
            }
            reusable = [
                item
                for identity, item in existing_by_identity.items()
                if identity not in expected_identities
            ]
            for record in expected_records:
                identity = record_identity(record)
                match = existing_by_identity.get(identity)
                if match is not None:
                    if int(match.get("ttl") or 0) == int(record["ttl"]):
                        planned.append(
                            {
                                "type": record_type,
                                "name": name,
                                "value": _live_value(record),
                                "action": "unchanged",
                            }
                        )
                        continue
                    planned.append(
                        {
                            "type": record_type,
                            "name": name,
                            "value": _live_value(record),
                            "action": "retuned",
                            "providerRecordId": str(match["providerRecordId"]),
                            "record": record,
                        }
                    )
                    continue
                if reusable:
                    stale = reusable.pop(0)
                    planned.append(
                        {
                            "type": record_type,
                            "name": name,
                            "value": _live_value(record),
                            "action": "updated",
                            "providerRecordId": str(stale["providerRecordId"]),
                            "record": record,
                            "replaces": str(stale.get("content") or ""),
                        }
                    )
                else:
                    planned.append(
                        {
                            "type": record_type,
                            "name": name,
                            "value": _live_value(record),
                            "action": "created",
                            "record": record,
                        }
                    )
            for stale in reusable:
                planned.append(
                    {
                        "type": record_type,
                        "name": name,
                        "value": str(stale.get("content") or ""),
                        "action": "removed",
                        "providerRecordId": str(stale["providerRecordId"]),
                    }
                )
    except DnsProviderError as exc:
        raise DomainGovernanceError(str(exc)) from exc

    if not allow_production_mutation:
        production = production_record_names()
        destructive = sorted(
            {
                f"{item['action']} {item['type']} {item['name']}"
                for item in planned
                if item["action"] in DESTRUCTIVE_DNS_ACTIONS
                and str(item["name"]) in production
            }
        )
        if destructive:
            raise DomainGovernanceError(
                "GATE_BLOCK: overwriting or removing existing production DNS "
                "records is a destructive action and requires explicit "
                "confirmation (--allow-production-mutation); planned: "
                f"{destructive}"
            )

    changes: list[dict[str, str]] = []
    try:
        for item in planned:
            action = str(item["action"])
            if action in {"retuned", "updated"}:
                provider.update_record(
                    str(item["providerRecordId"]), item["record"]
                )
            elif action == "created":
                provider.create_record(item["record"])
            elif action == "removed":
                provider.delete_record(str(item["providerRecordId"]))
            changes.append(
                {
                    "type": str(item["type"]),
                    "name": str(item["name"]),
                    "value": str(item["value"]),
                    "action": action,
                }
            )
    except DnsProviderError as exc:
        raise DomainGovernanceError(str(exc)) from exc

    return {
        "schema": "quwoquan.domain-governance-apply-receipt",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "zone": policy["registrableDomain"],
        "providerKind": str(provider_config.get("kind") or ""),
        "changes": changes,
        # 计划外但同名同类型的记录（备案、第三方站点校验等）不被收敛触碰，只如实上报，
        # 让运维能看见 zone 里还有什么，而不是让它们静默消失。
        "observedUnmanaged": observed_foreign,
        "pending": pending_dns_scopes(),
    }


def _topology_hosts(target_name: str) -> list[str]:
    topology = load_environment_topology()
    hosts = {
        urllib.parse.urlsplit(str(raw_url)).hostname
        for raw_url in (
            get_target(topology, target_name).get("publicBases") or {}
        ).values()
    }
    return sorted(host for host in hosts if host)


def verify_live_state(
    *,
    verify_tls: bool,
    prod_edge_address: str | None = None,
) -> dict[str, Any]:
    policy = _policy()
    edge_address = _prod_edge_address(policy, prod_edge_address)
    mail_guards = policy.get("mailGuards") or {}
    issues: list[str] = []
    pending = pending_dns_scopes(prod_edge_address)

    resolved: dict[str, dict[str, list[str]]] = {}
    caa_evidence: dict[str, dict[str, list[str]]] = {}
    mail_evidence: dict[str, dict[str, dict[str, list[str]]]] = {}
    verified_addresses: set[str] = set()

    for zone in dns_zones():
        scope = str(zone.get("scope") or "")
        expected_addresses = _zone_addresses(zone, policy, edge_address)
        if expected_addresses:
            verified_addresses.update(expected_addresses)
            probe_hosts = sorted(
                {
                    name
                    for name in zone_record_names(zone)
                    if not name.startswith("*.")
                }
                | set(_topology_hosts(str(zone["target"])))
            )
            for host in probe_hosts:
                by_resolver: dict[str, list[str]] = {}
                for record_type in ("A", "AAAA"):
                    try:
                        answers = _dns_over_https_by_resolver(host, record_type)
                    except DomainGovernanceError as exc:
                        issues.append(str(exc))
                        continue
                    for resolver, rows in answers.items():
                        by_resolver.setdefault(resolver, []).extend(rows)
                resolved[host] = {
                    resolver: sorted(set(rows))
                    for resolver, rows in by_resolver.items()
                }
                observed = {
                    address
                    for rows in by_resolver.values()
                    for address in rows
                }
                for expected in expected_addresses:
                    if expected not in observed:
                        issues.append(
                            f"{host} must resolve to {expected}, got "
                            f"{sorted(observed) or ['<empty>']}"
                        )
                unexpected = sorted(observed - set(expected_addresses))
                if unexpected:
                    issues.append(
                        f"{host} resolves to addresses outside the canonical "
                        f"plan: {unexpected}"
                    )

        apex = str(zone["apex"])
        try:
            caa_evidence[apex] = _dns_over_https_by_resolver(apex, "CAA")
        except DomainGovernanceError as exc:
            caa_evidence[apex] = {}
            issues.append(str(exc))
        observed_caa_rows = [
            row for rows in caa_evidence[apex].values() for row in rows
        ]
        observed_caa: set[tuple[int, str, str]] = set()
        for row in observed_caa_rows:
            parsed = parse_caa_text(row)
            if parsed is None:
                issues.append(f"{apex} publishes an unparsable CAA record {row!r}")
                continue
            observed_caa.add(parsed)
        expected_caa = {
            (int(entry["flags"]), str(entry["tag"]).lower(), str(entry["value"]))
            for entry in caa_profile(zone, policy)
        }
        for flags, tag, value in sorted(expected_caa - observed_caa):
            issues.append(f"{apex} CAA must publish {flags} {tag} {value}")
        # 反向检查是 deny-all 的全部意义：漏掉它时，一个声明 deny-all 的 zone 只要
        # 同时挂着允许型 issue 就仍判通过，等于没有拒签。
        for flags, tag, value in sorted(observed_caa - expected_caa):
            issues.append(
                f"{apex} publishes a CAA record outside its profile: "
                f"{flags} {tag} {value}"
            )

        guard = mail_guards.get(str(zone.get("mailGuard") or ""))
        if not isinstance(guard, dict):
            issues.append(f"dnsZones[{scope}] references an unknown mailGuard")
            continue
        by_type: dict[str, dict[str, list[str]]] = {}
        for record_type in ("MX", "TXT"):
            try:
                by_type[record_type] = _dns_over_https_by_resolver(apex, record_type)
            except DomainGovernanceError as exc:
                by_type[record_type] = {}
                issues.append(str(exc))
        mail_evidence[apex] = by_type
        if guard.get("nullMx"):
            mx_rows = [
                row for rows in by_type["MX"].values() for row in rows
            ]
            if not any(row.strip() in {"0 .", "0"} for row in mx_rows):
                issues.append(f"{apex} must publish null MX")
        expected_spf = str(guard.get("spf") or "")
        txt_rows = [row for rows in by_type["TXT"].values() for row in rows]
        if expected_spf and not any(expected_spf in row for row in txt_rows):
            issues.append(f"{apex} must publish {expected_spf}")
        expected_dmarc = str(guard.get("dmarc") or "")
        dmarc_name = f"_dmarc.{apex}"
        try:
            dmarc_answers = _dns_over_https_by_resolver(dmarc_name, "TXT")
        except DomainGovernanceError as exc:
            dmarc_answers = {}
            issues.append(str(exc))
        mail_evidence[dmarc_name] = {"TXT": dmarc_answers}
        dmarc_rows = [row for rows in dmarc_answers.values() for row in rows]
        if expected_dmarc and not any(
            expected_dmarc in row for row in dmarc_rows
        ):
            issues.append(f"{dmarc_name} must publish {expected_dmarc}")

    # 反向解析有三种结果，必须分开：有 PTR、无 PTR（在场为空）、查询失败。把失败
    # 折成空串会让下面的内部命名断言恒真通过，等于没查。
    reverse_evidence: dict[str, str] = {}
    for address in sorted(verified_addresses):
        try:
            reverse_name = socket.gethostbyaddr(address)[0].rstrip(".").lower()
        except socket.herror:
            reverse_evidence[address] = "absent"
            continue
        except (socket.gaierror, OSError) as exc:
            reverse_evidence[address] = "lookup-failed"
            issues.append(
                f"{address} reverse DNS lookup failed ({exc}); internal naming "
                "cannot be ruled out"
            )
            continue
        reverse_evidence[address] = reverse_name
        if any(
            token in reverse_name
            for token in (".internal", ".local", "corp", ".lan")
        ):
            issues.append(
                f"{address} reverse DNS must not expose internal asset naming"
            )

    tls_evidence: list[dict[str, Any]] = []
    if verify_tls:
        for target_name in tls_verifiable_targets():
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
        "pending": pending,
        # 有 scope 未被核对时既不是 ok 也不是 blocked：报 ok 会让「跳过检查」冒充
        # 「检查通过」，而 pending 的成因是缺注入而非现网故障。
        "status": "blocked" if issues else ("incomplete" if pending else "ok"),
        "issues": issues,
    }
    if issues:
        raise DomainGovernanceError(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    apply = subparsers.add_parser("apply")
    apply.add_argument(
        "--allow-production-mutation",
        action="store_true",
        help=(
            "确认执行生产 DNS 记录写入；缺省时一旦计划触碰生产 zone 即 fail closed"
        ),
    )
    verify = subparsers.add_parser("verify")
    verify.add_argument("--skip-tls", action="store_true")
    for child in (plan, apply, verify):
        child.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            payload: Any = {
                "schema": "quwoquan.domain-governance-plan",
                "providerKind": str(
                    (_policy().get("dnsProvider") or {}).get("kind") or ""
                ),
                "records": desired_dns_records(),
                "pending": pending_dns_scopes(),
            }
        elif args.command == "apply":
            payload = apply_dns_records(
                allow_production_mutation=args.allow_production_mutation
            )
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
        if isinstance(payload, dict) and payload.get("status") == "incomplete":
            print(
                "[domain-governance] INCOMPLETE: "
                f"{len(payload.get('pending') or [])} scope(s) were not verified",
                file=sys.stderr,
            )
            return 3
        return 0
    except DomainGovernanceError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
