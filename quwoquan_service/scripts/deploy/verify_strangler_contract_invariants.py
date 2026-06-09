#!/usr/bin/env python3
"""Strangler Fig 拆分契约不变量校验（SIT2 T1/T2 合同测试）。

验证「合并态（seed-box modular monolith）↔ 拆分态（域级独立 workload）」之间的契约不变量
在真相源中自洽，使得任一 split_candidate 域被抽出为独立 Deployment 后，域级 API path / route /
Service DNS 名 / 数据面归属保持不变（对外无感、可逆回滚）。

真相源：
  - deploy/shared/process_domain_mapping.yaml        (domain 归属唯一真相源)
  - deploy/shared/workload_topology_inventory.yaml   (部署形态三态 + split_candidates 不变量)
  - deploy/shared/module_package_mapping.yaml        (包→模块；拆分时模块迁移依据)

校验项：
  1. 三真相源对 prod seed-box 的 domain 集合完全一致。
  2. prod 每个 domain 唯一归属一个 workload（无双归属、无遗漏）：
     seed-box.domains ⊎ 各 standalone-workload.domains == process_domain_mapping.prod 所有 domain。
  3. 每个 split_candidate.domain ∈ seed-box.domains，且 route_prefix == "/v1/<domain>/"。
  4. 每个 split_candidate 声明 invariant_service_dns（拆分不变量契约存在）。
  5. 拆分可行性自洽：每个 split_candidate 域 D 在 module_package_mapping.prod.seed-box.modules
     中存在至少一个 "D.*" 模块（拆出时这些模块迁移到 D-service），且拆出 D 后 seed-box 仍非空。
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
PDM = ROOT / "deploy/shared/process_domain_mapping.yaml"
INVENTORY = ROOT / "deploy/shared/workload_topology_inventory.yaml"
MPM = ROOT / "deploy/shared/module_package_mapping.yaml"

errors: list[str] = []


def load_yaml(path: Path):
    if not path.exists():
        print(f"FAIL: 缺少 {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


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
    route_re = re.compile(r"^/v1/[a-z][a-z0-9_-]*/$")
    for sc in inv.get("split_candidates", []):
        d = sc.get("domain")
        if d not in inv_seed:
            errors.append(f"split_candidate '{d}' 不在 seed-box.domains 内（无法拆分）")
        prefix = sc.get("route_prefix", "")
        if prefix != f"/v1/{d}/":
            errors.append(
                f"split_candidate '{d}' route_prefix 不变量错误：期望 '/v1/{d}/'，实际 '{prefix}'"
            )
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
