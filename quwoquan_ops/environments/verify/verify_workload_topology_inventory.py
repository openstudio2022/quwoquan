#!/usr/bin/env python3
"""校验 ACK prod 工作负载三态 inventory 与真相源/渲染一致。

真相源：
  - quwoquan_ops/environments/process_domain_mapping.yaml   (domain 归属唯一真相源)
  - quwoquan_ops/environments/workload_topology_inventory.yaml (部署形态三态分类)

校验项：
  1. inventory.workloads 业务进程名集合 == process_domain_mapping.prod 进程名集合；
     external_workloads 只声明 capability，不得伪装为业务 domain/process。
  2. 每个 workload.domains == process_domain_mapping.prod 对应进程 domains。
  3. seed-box 为 modular-monolith-unit；recommendation 独立 [recommendation] 且不并入 seed-box。
  4. split_candidates 的 domain 必须都属于 seed-box domains。
  5. wired_to_prod_root=true 的 workload：
     - kustomize_overlay 存在；prod_root_kustomizations 非空且 root 引用该 overlay。
     - kustomize build root 渲染出该 workload 的全部 required_primitives。
     - 反模式：业务 Deployment 只允许 1 个业务容器（sidecar 仅限 allowlist）；
       initContainers 仅允许 allowlist 后缀。
  6. wired_to_prod_root=false 的 workload：kustomize_overlay 必须为 null（planned）。
  7. 反向：每个 prod root include 的 overlay 都必须对应一个 wired_to_prod_root=true 的
     workload（防止 root 与 inventory 漂移——root 里悄悄多挂 overlay 必须被 inventory 显式认领）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FAIL: PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "quwoquan_ops/environments/workload_topology_inventory.yaml"
PDM = ROOT / "quwoquan_ops/environments/process_domain_mapping.yaml"

errors: list[str] = []
warnings: list[str] = []


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def render_root(root_rel: str):
    """kustomize build 一个 root，返回资源文档列表；无工具时返回 None。"""
    root_path = ROOT / root_rel
    if shutil.which("kustomize"):
        cmd = ["kustomize", "build", str(root_path)]
    elif shutil.which("kubectl"):
        cmd = ["kubectl", "kustomize", str(root_path)]
    else:
        return None
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        errors.append(f"kustomize build 失败 {root_rel}: {out.stderr.strip()[:300]}")
        return []
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def main() -> int:
    if not INVENTORY.exists():
        print(f"FAIL: 缺少 {INVENTORY}", file=sys.stderr)
        return 1
    if not PDM.exists():
        print(f"FAIL: 缺少 {PDM}", file=sys.stderr)
        return 1

    inv = load_yaml(INVENTORY)
    pdm = load_yaml(PDM)

    prod_procs = pdm.get("environments", {}).get("prod", {})
    pdm_names = set(prod_procs.keys())
    pdm_domains = {n: set(v.get("domains", [])) for n, v in prod_procs.items()}

    workloads = inv.get("workloads", [])
    external_workloads = inv.get("external_workloads", [])
    all_deployments = workloads + external_workloads
    inv_names = {w["name"] for w in workloads}

    # 1. 进程名集合一致
    missing = pdm_names - inv_names
    extra = inv_names - pdm_names
    if missing:
        errors.append(f"inventory 缺少 prod 进程: {sorted(missing)}")
    if extra:
        errors.append(f"inventory 多出 process_domain_mapping 未声明的进程: {sorted(extra)}")

    seed_domains: set[str] = set()
    sidecar_allow = inv.get("sidecar_allowlist", {})
    allow_init_suffix = tuple(sidecar_allow.get("init_container_suffixes", []))
    allow_container_names = set(sidecar_allow.get("container_names", []))

    # 缓存 root 渲染
    root_cache: dict[str, object] = {}

    for w in workloads:
        name = w["name"]
        kind = w.get("deploy_kind")
        domains = set(w.get("domains", []))
        wired = bool(w.get("wired_to_prod_root"))
        overlay = w.get("kustomize_overlay")

        # 2. domains 一致
        if name in pdm_domains and domains != pdm_domains[name]:
            errors.append(
                f"{name} domains 与 process_domain_mapping prod 不一致: "
                f"inventory={sorted(domains)} pdm={sorted(pdm_domains[name])}"
            )
        if name == "seed-box":
            seed_domains = domains
            if kind != "modular-monolith-unit":
                errors.append("seed-box 必须是 modular-monolith-unit")
        if name == "recommendation-service":
            if domains != {"recommendation"}:
                errors.append("recommendation-service domains 必须恰为 [recommendation]")
            if kind != "standalone-workload":
                errors.append("recommendation-service 必须是 standalone-workload（不做 sidecar）")

        # 5/6. wired 状态与 overlay
        if wired:
            if not overlay:
                errors.append(f"{name} wired_to_prod_root=true 但缺 kustomize_overlay")
                continue
            if not (ROOT / overlay).exists():
                errors.append(f"{name} kustomize_overlay 不存在: {overlay}")
                continue
            roots = w.get("prod_root_kustomizations", [])
            if not roots:
                errors.append(f"{name} wired 但 prod_root_kustomizations 为空")
            for root_rel in roots:
                root_kust = ROOT / root_rel / "kustomization.yaml"
                if not root_kust.exists():
                    errors.append(f"{name} prod root 不存在: {root_rel}")
                    continue
                root_resources = load_yaml(root_kust).get("resources", []) or []
                resolved_resources = {(ROOT / root_rel / r).resolve() for r in root_resources}
                if (ROOT / overlay).resolve() not in resolved_resources:
                    errors.append(f"{name} 未被 {root_rel} root include overlay {overlay}")
                if root_rel not in root_cache:
                    root_cache[root_rel] = render_root(root_rel)
                docs = root_cache[root_rel]
                if docs is None:
                    warnings.append(f"无 kustomize/kubectl，跳过 {root_rel} 渲染校验")
                    continue
                _check_rendered_primitives(w, docs, root_rel, allow_init_suffix, allow_container_names)
        else:
            if overlay is not None:
                errors.append(
                    f"{name} wired_to_prod_root=false 但 kustomize_overlay 非 null（应为 planned）"
                )

    for w in external_workloads:
        name = w["name"]
        if w.get("profile") != "external-workload":
            errors.append(f"{name} external workload 缺 profile=external-workload")
        if w.get("domains"):
            errors.append(f"{name} external workload 禁止声明业务 domains")
        if not w.get("capabilities"):
            errors.append(f"{name} external workload 必须声明 capabilities")
        _check_wiring(
            w,
            root_cache,
            allow_init_suffix,
            allow_container_names,
        )

    # 3. recommendation 不并入 seed-box
    if "recommendation" in seed_domains:
        errors.append("seed-box domains 不得包含 recommendation（必须独立 workload）")

    # 4. split_candidates 必须属于 seed-box
    for sc in inv.get("split_candidates", []):
        d = sc.get("domain")
        if d not in seed_domains:
            errors.append(f"split_candidate '{d}' 不在 seed-box domains 内")

    # 7. 反向：prod root include 的每个 overlay 必须对应 wired=true 的 inventory workload
    wired_overlays = {
        (ROOT / w["kustomize_overlay"]).resolve()
        for w in all_deployments
        if w.get("wired_to_prod_root") and w.get("kustomize_overlay")
    }
    seen_roots: set[str] = set()
    for w in all_deployments:
        for root_rel in w.get("prod_root_kustomizations", []) or []:
            seen_roots.add(root_rel)
    for root_rel in sorted(seen_roots):
        root_kust = ROOT / root_rel / "kustomization.yaml"
        if not root_kust.exists():
            continue
        for r in load_yaml(root_kust).get("resources", []) or []:
            resolved = (ROOT / root_rel / r).resolve()
            if resolved not in wired_overlays:
                errors.append(
                    f"{root_rel} root include overlay '{r}' "
                    f"未对应任何 wired_to_prod_root=true 的 inventory workload（root 与 inventory 漂移）"
                )

    if warnings:
        for w in warnings:
            print(f"WARN: {w}")
    if errors:
        print("FAIL: workload topology inventory 校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        "PASS: workload topology inventory（"
        f"{len(workloads)} 业务 workloads + {len(external_workloads)} 外部 capabilities，"
        "三态一致、标准原语齐全、无 sidecar 反模式）"
    )
    return 0


def _check_wiring(
    w,
    root_cache,
    allow_init_suffix,
    allow_container_names,
):
    name = w["name"]
    wired = bool(w.get("wired_to_prod_root"))
    overlay = w.get("kustomize_overlay")
    if not wired:
        if overlay is not None:
            errors.append(
                f"{name} wired_to_prod_root=false 但 kustomize_overlay 非 null（应为 planned）"
            )
        return
    if not overlay:
        errors.append(f"{name} wired_to_prod_root=true 但缺 kustomize_overlay")
        return
    if not (ROOT / overlay).exists():
        errors.append(f"{name} kustomize_overlay 不存在: {overlay}")
        return
    roots = w.get("prod_root_kustomizations", [])
    if not roots:
        errors.append(f"{name} wired 但 prod_root_kustomizations 为空")
    for root_rel in roots:
        root_kust = ROOT / root_rel / "kustomization.yaml"
        if not root_kust.exists():
            errors.append(f"{name} prod root 不存在: {root_rel}")
            continue
        root_resources = load_yaml(root_kust).get("resources", []) or []
        resolved_resources = {(ROOT / root_rel / r).resolve() for r in root_resources}
        if (ROOT / overlay).resolve() not in resolved_resources:
            errors.append(f"{name} 未被 {root_rel} root include overlay {overlay}")
        if root_rel not in root_cache:
            root_cache[root_rel] = render_root(root_rel)
        docs = root_cache[root_rel]
        if docs is not None:
            _check_rendered_primitives(
                w,
                docs,
                root_rel,
                allow_init_suffix,
                allow_container_names,
            )


def _check_rendered_primitives(w, docs, root_rel, allow_init_suffix, allow_container_names):
    name = w["name"]
    required = set(w.get("required_primitives", []))
    found_kinds = set()
    for d in docs:
        if d.get("metadata", {}).get("name") != name:
            continue
        k = d.get("kind")
        found_kinds.add(k)
        if k in ("Deployment", "StatefulSet"):
            spec = d.get("spec", {}).get("template", {}).get("spec", {})
            containers = spec.get("containers", []) or []
            biz = [c for c in containers if c.get("name") not in allow_container_names]
            if len(biz) != 1:
                errors.append(
                    f"反模式：{name} ({root_rel}) {k} 业务容器数={len(biz)} "
                    f"({[c.get('name') for c in biz]})，每个 workload 只允许 1 个业务容器"
                )
            for ic in spec.get("initContainers", []) or []:
                icn = ic.get("name", "")
                if not icn.endswith(allow_init_suffix) and icn not in allow_container_names:
                    errors.append(
                        f"反模式：{name} ({root_rel}) initContainer '{icn}' 不在 sidecar allowlist"
                    )
    missing_prims = required - found_kinds
    if missing_prims:
        errors.append(
            f"{name} ({root_rel}) 缺标准原语 {sorted(missing_prims)}（已渲染 {sorted(found_kinds)}）"
        )


if __name__ == "__main__":
    sys.exit(main())
