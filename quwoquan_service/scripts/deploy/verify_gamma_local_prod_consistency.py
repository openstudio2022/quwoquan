#!/usr/bin/env python3
"""校验 gamma-local 镜像栈与 prod 工作负载 inventory 的“环境一致性”。

环境一致性原则（用户口径）：各环境一致、逻辑独立、物理按需组装、当前阶段统一部署。
gamma-local 用 docker-compose 单文件统一承载，用 compose profiles 实现“按需组装”，
其服务名册/对外 DNS 名必须与 prod（deploy/shared/workload_topology_inventory.yaml）对齐。

真相源：
  - deploy/shared/workload_topology_inventory.yaml  (prod 三态 wired workloads)
  - quwoquan_service/docker-compose.gamma-local.yaml  (gamma-local 统一 compose)

校验项：
  A. recommendation：prod wired 的 recommendation-service ↔ gamma-local 某 service 的网络别名含
     recommendation-service；且 content-service 经 recommendation-service:8000 调用（与 prod 同名）。
  B. edge-media：prod plane=edge-media 的 wired workload（realtime-gateway/rtc-service/livekit-sfu/coturn）
     必须在 gamma-local compose 中以同名 service 存在，且归属 edge profile（edge-media / edge-media-pending）。
  C. 主栈纯净：默认 profile（无 profiles）不得包含 edge-media wired 服务（edge 必须按需启用）。
  D. 应用面 split-candidate（seed-box 聚合域）在 gamma-local 以独立 service 体现的，作为一致性提示（warning）。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FAIL: PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "deploy/shared/workload_topology_inventory.yaml"
GAMMA_COMPOSE = ROOT / "quwoquan_service/docker-compose.gamma-local.yaml"

EDGE_PROFILES = {"edge-media", "edge-media-pending"}

errors: list[str] = []
warnings: list[str] = []


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def service_aliases(svc: dict) -> set[str]:
    nets = svc.get("networks") or {}
    if isinstance(nets, list):
        return set()
    default = nets.get("default") or {}
    return set(default.get("aliases") or [])


def main() -> int:
    for p in (INVENTORY, GAMMA_COMPOSE):
        if not p.exists():
            print(f"FAIL: 缺少 {p}", file=sys.stderr)
            return 1

    inv = load_yaml(INVENTORY)
    compose = load_yaml(GAMMA_COMPOSE)
    services = compose.get("services", {}) or {}

    workloads = inv.get("workloads", []) or []
    wired = [w for w in workloads if w.get("wired_to_prod_root")]
    edge_wired = {w["name"] for w in wired if w.get("plane") == "edge-media"}
    rec_wired = any(w["name"] == "recommendation-service" for w in wired)

    # A. recommendation 对外 DNS 名统一
    if rec_wired:
        has_alias = any(
            "recommendation-service" in service_aliases(s) for s in services.values()
        )
        if not has_alias:
            errors.append(
                "gamma-local 无任一 service 暴露网络别名 recommendation-service"
                "（rec 对外 DNS 名未与 prod 对齐）"
            )
        content = services.get("content-service", {})
        url = (content.get("environment", {}) or {}).get("REC_MODEL_SERVICE_URL", "")
        if "recommendation-service:" not in str(url):
            errors.append(
                f"content-service REC_MODEL_SERVICE_URL 未经 recommendation-service 调用: {url!r}"
            )

    # B. edge-media 服务集一致
    for name in sorted(edge_wired):
        svc = services.get(name)
        if svc is None:
            errors.append(
                f"prod edge-media wired 服务 {name} 在 gamma-local compose 缺失（环境名册不一致）"
            )
            continue
        profs = set(svc.get("profiles") or [])
        if not (profs & EDGE_PROFILES):
            errors.append(
                f"{name} 未归属 edge profile {sorted(EDGE_PROFILES)}（当前 profiles={sorted(profs)}）"
            )

    # C. 主栈纯净：默认 profile 不得含 edge wired 服务
    for name, svc in services.items():
        profs = svc.get("profiles") or []
        if not profs and name in edge_wired:
            errors.append(f"edge-media 服务 {name} 不应出现在默认主栈 profile（须按需启用）")

    # D. 应用面 split-candidate 独立 service（提示）
    seed = next((w for w in workloads if w["name"] == "seed-box"), {})
    seed_domains = set(seed.get("domains", []))
    domain_to_service = {
        "content": "content-service",
        "chat": "chat-service",
        "user": "user-service",
    }
    for dom, svc_name in domain_to_service.items():
        if dom in seed_domains and svc_name not in services:
            warnings.append(
                f"seed-box 域 {dom} 在 gamma-local 无独立 service {svc_name}（形态差异，可接受）"
            )

    if warnings:
        for w in warnings:
            print(f"WARN: {w}")
    if errors:
        print("FAIL: gamma-local 与 prod 环境一致性校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        f"PASS: gamma-local ↔ prod 环境一致性（rec DNS 统一、edge-media {sorted(edge_wired)} "
        f"名册一致且 profile 化、主栈纯净）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
