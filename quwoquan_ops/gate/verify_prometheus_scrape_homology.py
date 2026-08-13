#!/usr/bin/env python3
"""Prometheus scrape 目标 ↔ 部署拓扑同源门禁。

第一方服务的 metrics 采集目标必须与其 deploy/base/deployment.yaml 声明的
containerPort 同源：缺 target 会让该服务在监控面成为盲区，端口错配会静默
采空。真相源是各服务 deploy 清单（实时扫描），不建立第二份端口注册表。

校验规则：
1. 每个第一方服务（services/*/deploy/base + control-plane/platform-ops）
   必须以 `<service>:<containerPort>` 出现在 prometheus.yml 的某个
   static_configs target 中。
2. prometheus.yml 中凡是主机名命中第一方服务名的 target，其端口必须与
   deploy 清单一致（双向防漂移）。
3. 非第一方 target（exporter、livekit、otel-collector 等基础设施）不在
   本门禁范围内，由 compose 部署定义自治。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS_CONFIG = REPO_ROOT / "quwoquan_ops/observability/monitoring/prometheus.yml"
SERVICES_ROOT = REPO_ROOT / "quwoquan_service/services"
EXTRA_DEPLOYMENTS = {
    # platform-ops 是控制面服务，deployment 位置不在 services/ 之下。
    "platform-ops-service": REPO_ROOT
    / "quwoquan_service/control-plane/platform-ops/deploy/base/deployment.yaml",
}
_CONTAINER_PORT = re.compile(r"containerPort:\s*(\d+)")


def first_party_ports() -> dict[str, int]:
    """service 名 → deploy/base 声明的首个 containerPort。"""
    ports: dict[str, int] = {}
    for deployment in sorted(SERVICES_ROOT.glob("*/deploy/base/deployment.yaml")):
        service = deployment.parents[2].name
        match = _CONTAINER_PORT.search(deployment.read_text(encoding="utf-8"))
        if match is None:
            raise ValueError(f"deployment without containerPort: {deployment}")
        ports[service] = int(match.group(1))
    for service, deployment in EXTRA_DEPLOYMENTS.items():
        match = _CONTAINER_PORT.search(deployment.read_text(encoding="utf-8"))
        if match is None:
            raise ValueError(f"deployment without containerPort: {deployment}")
        ports[service] = int(match.group(1))
    return ports


def prometheus_targets() -> dict[str, set[int]]:
    """target 主机名 → prometheus.yml 中出现过的端口集合。

    blackbox 探测 job（metrics_path=/probe）的 target 是被测 URL 而非
    host:port 采集地址，不参与第一方服务端口同源校验。
    """
    config = yaml.safe_load(PROMETHEUS_CONFIG.read_text(encoding="utf-8"))
    targets: dict[str, set[int]] = {}
    for job in config.get("scrape_configs", []):
        if str(job.get("metrics_path", "/metrics")) == "/probe":
            continue
        for static in job.get("static_configs", []):
            for target in static.get("targets", []):
                host, _, port = str(target).partition(":")
                if not port.isdigit():
                    raise ValueError(f"target without numeric port: {target}")
                targets.setdefault(host, set()).add(int(port))
    return targets


def main() -> int:
    errors: list[str] = []
    ports = first_party_ports()
    targets = prometheus_targets()
    for service, port in sorted(ports.items()):
        observed = targets.get(service)
        if observed is None:
            errors.append(
                f"{service} is missing from prometheus scrape targets "
                f"(expected {service}:{port})"
            )
            continue
        if port not in observed:
            errors.append(
                f"{service} scrape port drifted: prometheus={sorted(observed)} "
                f"deployment={port}"
            )
        extra = observed - {port}
        if extra:
            errors.append(
                f"{service} has stale scrape ports {sorted(extra)}; deployment "
                f"declares only {port}"
            )
    if errors:
        print("FAIL: prometheus scrape homology")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: prometheus scrape homology")
    print(f"  - {len(ports)} first-party services covered by scrape targets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
