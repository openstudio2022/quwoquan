"""domain taxonomy 垂类词派生与服务 domain owner 扫描。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .constants import (
    CONTRACT_GRAPH,
    DOMAIN_TAXONOMY,
    SERVICE_ROOT,
    VERTICAL_WORD_STOPLIST,
)
from .fsscan import _load_yaml_mapping, _read_text, _relative


def _vertical_tokens_from_text(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        return set()
    tokens = {normalized}
    tokens.update(
        token
        for token in normalized.split("_")
        if len(token) >= 4 and token not in VERTICAL_WORD_STOPLIST
    )
    return tokens


def load_vertical_terms(root: Path) -> frozenset[str]:
    path = root / DOMAIN_TAXONOMY
    document = _load_yaml_mapping(path, label="domain taxonomy")
    domains = document.get("domains")
    if not isinstance(domains, list):
        raise ValueError(f"domain taxonomy 缺少 domains 列表: {path}")
    terms: set[str] = set()
    for entry in domains:
        if not isinstance(entry, dict) or entry.get("mode") != "content":
            continue
        terms.update(_vertical_tokens_from_text(entry.get("id")))
        label = entry.get("label")
        if isinstance(label, dict):
            terms.update(_vertical_tokens_from_text(label.get("en")))
        for assistant_id in entry.get("assistant_domain_ids") or []:
            terms.update(_vertical_tokens_from_text(assistant_id))
        for category in entry.get("sub_categories") or []:
            terms.update(_vertical_tokens_from_text(category))
    if not terms:
        raise ValueError("domain taxonomy 没有可派生的 content vertical 标识")
    return frozenset(terms)


def _load_contract_graph_domains(root: Path) -> set[str]:
    path = root / CONTRACT_GRAPH
    if not path.is_file():
        return set()
    try:
        document = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"ContractGraph 无法读取或解析: {path}: {exc}") from exc
    objects = document.get("objects") if isinstance(document, dict) else None
    if not isinstance(objects, list):
        return set()
    return {
        str(item.get("domain") or "").strip()
        for item in objects
        if isinstance(item, dict) and str(item.get("domain") or "").strip()
    }


def _service_has_files(path: Path) -> bool:
    return any(
        candidate.is_file() and candidate.name != ".DS_Store"
        for candidate in path.rglob("*")
    )


def scan_service_domains(root: Path) -> tuple[dict[str, str], list[str]]:
    services_root = root / SERVICE_ROOT
    if not services_root.is_dir():
        return {}, []
    graph_domains = _load_contract_graph_domains(root)
    service_domains: dict[str, str] = {}
    issues: list[str] = []
    domain_owners: dict[str, list[str]] = {}
    for service_dir in sorted(path for path in services_root.iterdir() if path.is_dir()):
        if not _service_has_files(service_dir):
            continue
        relative = _relative(root, service_dir)
        domain_path = service_dir / "contracts" / "domain.yaml"
        if not domain_path.is_file():
            issues.append(
                f"{relative}: 新服务边界缺少 contracts/domain.yaml owner metadata；"
                "不得以垂类目录绕过 canonical domain owner"
            )
            continue
        document = _load_yaml_mapping(domain_path, label=f"{relative} domain owner")
        domain = str(document.get("domain") or "").strip()
        if not domain:
            issues.append(f"{relative}: contracts/domain.yaml.domain 不能为空")
            continue
        service_domains[relative] = domain
        domain_owners.setdefault(domain, []).append(relative)
        if graph_domains and domain not in graph_domains:
            issues.append(
                f"{relative}: domain={domain!r} 未被 canonical ContractGraph 对象拥有；"
                "禁止新建无对象 owner 的垂类服务"
            )
    for domain, owners in sorted(domain_owners.items()):
        if len(owners) > 1:
            issues.append(
                f"domain={domain!r} 同时由多个服务拥有: {', '.join(sorted(owners))}"
            )
    return service_domains, issues


def _matches_vertical_service(
    service_path: str,
    domain: str,
    vertical_terms: frozenset[str],
) -> bool:
    name = Path(service_path).name
    stem = name.removesuffix("-service").removesuffix("-gateway")
    candidates = {
        stem.lower().replace("-", "_"),
        domain.lower().replace("-", "_"),
    }
    for candidate in candidates:
        if candidate in vertical_terms:
            return True
        if any(
            candidate.startswith(f"{term}_") or candidate.endswith(f"_{term}")
            for term in vertical_terms
        ):
            return True
    return False
