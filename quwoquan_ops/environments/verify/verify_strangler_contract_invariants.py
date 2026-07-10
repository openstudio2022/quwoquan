#!/usr/bin/env python3
"""Strangler Fig 拆分契约不变量校验（SIT2 T1/T2 合同测试）。

验证「合并态（seed-box modular monolith）↔ 拆分态（域级独立 workload）」之间的契约不变量
在真相源中自洽，使得任一 split_candidate 域被抽出为独立 Deployment 后，域级 API path / route /
Service DNS 名 / 数据面归属保持不变（对外无感、可逆回滚）。

真相源：
  - quwoquan_ops/environments/process_domain_mapping.yaml        (domain 归属唯一真相源)
  - quwoquan_ops/environments/workload_topology_inventory.yaml   (部署形态三态 + split_candidates 不变量)
  - quwoquan_ops/environments/module_package_mapping.yaml        (包→模块；拆分时模块迁移依据)

校验项：
  1. 三真相源对 prod seed-box 的 domain 集合完全一致。
  2. prod 每个 domain 唯一归属一个 workload（无双归属、无遗漏）：
     seed-box.domains ⊎ 各 standalone-workload.domains == process_domain_mapping.prod 所有 domain。
  3. 每个 split_candidate.domain ∈ seed-box.domains，且 route_prefix 必须来自 metadata service.yaml 的真实 API path 前缀。
  4. 每个 split_candidate 声明 invariant_service_dns（拆分不变量契约存在）。
  5. 拆分可行性自洽：每个 split_candidate 域 D 在 module_package_mapping.prod.seed-box.modules
     中存在至少一个 "D.*" 模块（拆出时这些模块迁移到 D-service），且拆出 D 后 seed-box 仍非空。
  6. seed-box 声明承载的 domain 必须在 entrypoint 里有真实子进程与路由分发，防止幽灵域只在 YAML 自洽。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FAIL: PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
PDM = ROOT / "quwoquan_ops/environments/process_domain_mapping.yaml"
INVENTORY = ROOT / "quwoquan_ops/environments/workload_topology_inventory.yaml"
MPM = ROOT / "quwoquan_ops/environments/module_package_mapping.yaml"
METADATA_DIR = ROOT / "quwoquan_service/contracts/metadata"
SEED_BOX_ENTRYPOINT = ROOT / "quwoquan_service/services/seed-box/deploy/seed_box_entrypoint.py"

errors: list[str] = []


def load_yaml(path: Path):
    if not path.exists():
        print(f"FAIL: 缺少 {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def route_prefixes_from_metadata(domain: str) -> set[str]:
    prefixes: set[str] = set()
    for service_yaml in METADATA_DIR.glob("**/service.yaml"):
        data = load_yaml(service_yaml)
        service = data.get("service") or {}
        if service.get("domain") != domain:
            continue
        for route in data.get("api_routes") or []:
            raw_path = str(route.get("path") or "").strip()
            if not raw_path.startswith("/v1/"):
                continue
            path = raw_path.split("{", 1)[0].split(":", 1)[0]
            if not path.endswith("/"):
                path = path.rsplit("/", 1)[0] + "/"
            prefixes.add(path)
    return prefixes


def seed_box_runtime_contract() -> tuple[set[str], str]:
    if not SEED_BOX_ENTRYPOINT.exists():
        errors.append(f"缺少 seed-box entrypoint: {SEED_BOX_ENTRYPOINT.relative_to(ROOT)}")
        return set(), ""
    source = SEED_BOX_ENTRYPOINT.read_text(encoding="utf-8")
    service_names = set(re.findall(r'name="([^"]+-service)"', source))
    return service_names, source


def main() -> int:
    pdm = load_yaml(PDM)
    inv = load_yaml(INVENTORY)
    mpm = load_yaml(MPM)

    prod_procs = pdm.get("environments", {}).get("prod", {})
    pdm_seed = set((prod_procs.get("seed-box") or {}).get("domains", []))
    pdm_all_domains: list[str] = []
    for proc, cfg in prod_procs.items():
        pdm_all_domains.extend((cfg or {}).get("domains", []))

    workloads = inv.get("workloads", [])
    inv_seed = set()
    standalone_domains: list[str] = []
    for w in workloads:
        if w["name"] == "seed-box":
            inv_seed = set(w.get("domains", []))
        elif w.get("deploy_kind") == "standalone-workload":
            standalone_domains.extend(w.get("domains", []))

    mpm_prod = mpm.get("environments", {}).get("prod", {})
    mpm_seed = set((mpm_prod.get("seed-box") or {}).get("domains", []))
    mpm_seed_modules = (mpm_prod.get("seed-box") or {}).get("modules", [])

    # 1. 三真相源 seed-box domain 一致
    if not (pdm_seed == inv_seed == mpm_seed):
        errors.append(
            "prod seed-box domain 集合在三真相源不一致："
            f"process_domain_mapping={sorted(pdm_seed)} "
            f"workload_inventory={sorted(inv_seed)} "
            f"module_package_mapping={sorted(mpm_seed)}"
        )

    # 2. prod 每个 domain 唯一归属（无双归属、无遗漏）
    owned = list(inv_seed) + standalone_domains
    dup = sorted({d for d in owned if owned.count(d) > 1})
    if dup:
        errors.append(f"domain 双归属（出现在多个 workload）：{dup}")
    if set(owned) != set(pdm_all_domains):
        missing = set(pdm_all_domains) - set(owned)
        extra = set(owned) - set(pdm_all_domains)
        errors.append(
            "workload 覆盖的 domain 与 process_domain_mapping.prod 不一致："
            f"缺失={sorted(missing)} 多出={sorted(extra)}"
        )

    # 3/4. split_candidate 路由前缀 + Service DNS 不变量
    route_re = re.compile(r"^/v1/[a-z][a-z0-9_-]*(?:/[a-z][a-z0-9_-]*)*/$")
    for sc in inv.get("split_candidates", []):
        d = sc.get("domain")
        if d not in inv_seed:
            errors.append(f"split_candidate '{d}' 不在 seed-box.domains 内（无法拆分）")
        prefix = sc.get("route_prefix", "")
        metadata_prefixes = route_prefixes_from_metadata(d)
        if metadata_prefixes and prefix not in metadata_prefixes:
            errors.append(
                f"split_candidate '{d}' route_prefix 不来自 metadata service.yaml："
                f"metadata={sorted(metadata_prefixes)} 实际='{prefix}'"
            )
        if not metadata_prefixes:
            errors.append(f"split_candidate '{d}' 找不到 metadata service.yaml API path 前缀")
        if not route_re.match(prefix):
            errors.append(f"split_candidate '{d}' route_prefix 格式非法：'{prefix}'")
        if not sc.get("invariant_service_dns"):
            errors.append(f"split_candidate '{d}' 缺 invariant_service_dns 契约不变量声明")

    # 5. 拆分可行性自洽：split_candidate 域在 seed-box modules 有对应模块，且拆出后 seed-box 非空
    for sc in inv.get("split_candidates", []):
        d = sc.get("domain")
        if d not in inv_seed:
            continue
        d_modules = [m for m in mpm_seed_modules if str(m).startswith(f"{d}.")]
        if not d_modules:
            errors.append(
                f"split_candidate '{d}' 在 module_package_mapping.prod.seed-box.modules 无 '{d}.*' 模块，拆分无模块可迁"
            )
        if inv_seed - {d} == set():
            errors.append(f"拆出 '{d}' 后 seed-box.domains 为空（modular monolith 不应被拆空）")

    # 6. seed-box 声明承载的 domain 必须被 entrypoint 实际承载。
    runtime_services, runtime_source = seed_box_runtime_contract()
    expected_runtime = {
        "content": ("content-service", ["/v1/content"]),
        "integration": ("integration-service", ["/v1/integration"]),
        "chat": ("chat-service", ["/v1/chat"]),
        "user": ("user-service", ["/v1/user", "/v1/users"]),
        "circle": ("circle-service", ["/v1/circles"]),
        "notification": ("notification-service", ["/v1/notifications", "/v1/app-messages"]),
        "entity": ("entity-service", ["/v1/homepages"]),
        "tag": ("tag-service", ["/v1/tag"]),
        "ops": ("product-ops-service", ["/v1/ops"]),
        "assistant": ("assistant-service", ["/v1/assistant"]),
    }
    for domain in sorted(inv_seed):
        spec = expected_runtime.get(domain)
        if spec is None:
            errors.append(f"seed-box domain '{domain}' 没有 entrypoint runtime contract 映射（可能是幽灵域）")
            continue
        service_name, route_markers = spec
        if service_name not in runtime_services:
            errors.append(f"seed-box domain '{domain}' 缺少 ServiceSpec 子进程 {service_name}")
        for marker in route_markers:
            if marker not in runtime_source:
                errors.append(f"seed-box domain '{domain}' entrypoint 缺路由分发标记 {marker}")

    if errors:
        print("FAIL: Strangler 契约不变量校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        f"PASS: Strangler 契约不变量（{len(inv.get('split_candidates', []))} 个 split_candidate，"
        "三真相源 seed-box 一致、domain 唯一归属、route/Service DNS 不变量自洽、拆分模块可迁）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
