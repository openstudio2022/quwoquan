#!/usr/bin/env python3
"""gamma-local ↔ prod-hosted 工作负载图谱同构校验（SIT2 T1/T2）。

证明 gamma-local 与 prod-hosted 在「暴露面 / 平面划分 / 数据面 Service 名·DSN 变量」维度同构，
两环境只换 backend（本机容器编排 vs ACK + 托管 DB）与 secret 取值，业务代码与契约不变。

真相源：
  - deploy/shared/environment_topology_manifest.yaml  (环境/target 暴露面与平面)
  - deploy/service/seed-box/kustomize/base/deployment.yaml      (数据面 DSN 变量经 secret 注入)
  - deploy/service/seed-box/kustomize/overlays/prod/kustomization.yaml (prod overlay 仅改环境无关参数)

校验项：
  A. environments.gamma 与 environments.prod 的 publicBases / serviceAliases / subnets /
     mockBoundaryFlags 键集合一致（暴露面与四平面同构）。
  B. targets.gamma-local 与 targets.prod-hosted 的 publicBases 键集合一致；env 字段分别为 gamma / prod。
  C. 数据面 DSN 变量同构：seed-box base deployment 的数据面变量经 secretKeyRef 注入（环境无关变量名），
     prod overlay 的 replacements 不修改任何数据面变量（只改 APP_ENV/CONFIG_VERSION/IMAGE_VERSION/
     replicas/HPA），证明跨环境数据面 Service 名/DSN 变量名不变、只换 secret 取值。
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
ETM = ROOT / "deploy/shared/environment_topology_manifest.yaml"
SEED_DEPLOY = ROOT / "deploy/service/seed-box/kustomize/base/deployment.yaml"
SEED_PROD = ROOT / "deploy/service/seed-box/kustomize/overlays/prod/kustomization.yaml"

errors: list[str] = []


def load_yaml(path: Path):
    if not path.exists():
        print(f"FAIL: 缺少 {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _keys(d, *path):
    cur = d
    for p in path:
        cur = (cur or {}).get(p, {})
    return set((cur or {}).keys())


def main() -> int:
    etm = load_yaml(ETM)
    envs = etm.get("environments", {})
    targets = etm.get("targets", {})

    # A. 环境暴露面 / 平面同构
    for section in ("publicBases", "serviceAliases", "subnets", "mockBoundaryFlags"):
        g = _keys(envs, "gamma", section)
        p = _keys(envs, "prod", section)
        if g != p:
            errors.append(
                f"environments.gamma 与 environments.prod 的 {section} 键集合不同构："
                f"gamma={sorted(g)} prod={sorted(p)}"
            )

    # B. target 暴露面同构 + env 映射
    gl = targets.get("gamma-local", {})
    ph = targets.get("prod-hosted", {})
    if not gl:
        errors.append("targets 缺 gamma-local")
    if not ph:
        errors.append("targets 缺 prod-hosted")
    if gl and ph:
        gl_pb = set((gl.get("publicBases") or {}).keys())
        ph_pb = set((ph.get("publicBases") or {}).keys())
        if gl_pb != ph_pb:
            errors.append(
                f"gamma-local 与 prod-hosted publicBases 键不同构：gamma-local={sorted(gl_pb)} prod-hosted={sorted(ph_pb)}"
            )
        if gl.get("env") != "gamma":
            errors.append(f"gamma-local.env 应为 gamma，实际 {gl.get('env')}")
        if ph.get("env") != "prod":
            errors.append(f"prod-hosted.env 应为 prod，实际 {ph.get('env')}")

    # C. 数据面 DSN 变量同构
    dep = load_yaml(SEED_DEPLOY)
    containers = (
        dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) or []
    )
    data_vars: set[str] = set()
    for c in containers:
        for e in c.get("env", []) or []:
            vf = e.get("valueFrom", {}) or {}
            if "secretKeyRef" in vf:
                data_vars.add(e.get("name"))
    if not data_vars:
        errors.append("seed-box base deployment 未发现经 secretKeyRef 注入的数据面变量（DSN 应走 Secret）")

    prod = load_yaml(SEED_PROD)
    changed_env: set[str] = set()
    env_re = re.compile(r"env\.\[name=([^\]]+)\]")
    for rep in prod.get("replacements", []) or []:
        for tgt in rep.get("targets", []) or []:
            for fp in tgt.get("fieldPaths", []) or []:
                m = env_re.search(fp)
                if m:
                    changed_env.add(m.group(1))
    leaked = data_vars & changed_env
    if leaked:
        errors.append(
            f"prod overlay replacements 修改了数据面 DSN 变量 {sorted(leaked)}，破坏跨环境同构（数据面应只换 secret 取值）"
        )

    if errors:
        print("FAIL: gamma-local ↔ prod-hosted 同构校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        f"PASS: gamma-local↔prod-hosted 同构（暴露面/四平面键一致；数据面 {len(data_vars)} 个 DSN 变量经 Secret 注入、跨环境不变）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
