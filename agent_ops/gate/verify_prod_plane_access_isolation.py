#!/usr/bin/env python3
"""校验 prod-hosted 四平面访问隔离映射的单一真相源一致性（去 root · 取消远端 gamma）。

真相源：
  - deploy/shared/prod_plane_access_isolation.yaml      （访问隔离层：平面->账号->凭据->路径->stage->workload）
  - deploy/shared/environment_topology_manifest.yaml    （运行时平面：prod.subnets edge/media/service/data）
  - deploy/shared/workload_topology_inventory.yaml      （workload 归属：planes application/edge-media）

校验项（保证单一解释、最小权限、与四环境一致）：
  1. schemaVersion / target=prod-hosted / rolloutStages=[gray-initial,carry-on,full]。
  2. planes 集合 == topology prod.subnets 的四平面 {edge,media,service,data}。
  3. 账号一一对应：每平面账号唯一且命名 prod-<plane>-svc；无两平面共用账号。
  4. 凭据：每平面 sshKeySecret 唯一且命名 PROD_<PLANE>_SSH_KEY；relay=PROD_OPS_SSH_KEY；禁止复用单一全权 secret。
  5. 读写平面：composeProjectRoot 非空 + governedWorkloads 非空；data 平面 read-only-audit、composeProjectRoot=null、
     governedWorkloads 空、appliesToStages 空。
  6. governedWorkloads ⊆ workload_topology_inventory.workloads，且每个 workload 的 inventory plane == 本平面 workloadDeployPlane。
  7. 退役断言：仓库不得在访问隔离层重新引入 PROD_KUBECONFIG 单一全权凭据或 gamma-hosted 远端目标。
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

ROOT = Path(__file__).resolve().parents[2]
ACCESS = ROOT / "deploy/shared/prod_plane_access_isolation.yaml"
TOPOLOGY = ROOT / "deploy/shared/environment_topology_manifest.yaml"
INVENTORY = ROOT / "deploy/shared/workload_topology_inventory.yaml"
CONTROL_PLANE = (
    ROOT / "quwoquan_service/contracts/metadata/_control_plane/platform/control_plane.yaml"
)

EXPECTED_PLANES = {"edge", "media", "service", "data"}
EXPECTED_STAGES = ["gray-initial", "carry-on", "full"]

errors: list[str] = []


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> int:
    for path in (ACCESS, TOPOLOGY, INVENTORY):
        if not path.exists():
            print(f"FAIL: 缺少 {path}", file=sys.stderr)
            return 1

    access = load_yaml(ACCESS)
    topology = load_yaml(TOPOLOGY)
    inventory = load_yaml(INVENTORY)

    # 1. 顶层契约
    if access.get("schemaVersion") != "prod-plane-access-isolation/v1":
        errors.append("schemaVersion 必须为 prod-plane-access-isolation/v1")
    if access.get("target") != "prod-hosted":
        errors.append("target 必须为 prod-hosted（远端唯一托管目标）")
    if access.get("rolloutStages") != EXPECTED_STAGES:
        errors.append(f"rolloutStages 必须为 {EXPECTED_STAGES}")

    relay = access.get("relayAccount") or {}
    if relay.get("name") != "prod-ops":
        errors.append("relayAccount.name 必须为 prod-ops（非 root 中转）")
    if relay.get("sshKeySecret") != "PROD_OPS_SSH_KEY":
        errors.append("relayAccount.sshKeySecret 必须为 PROD_OPS_SSH_KEY")

    planes = access.get("planes") or []
    plane_names = [p.get("plane") for p in planes]

    # 2. 平面集合 == topology prod.subnets
    prod_env = (topology.get("environments") or {}).get("prod") or {}
    topo_subnets = set((prod_env.get("subnets") or {}).keys())
    if set(plane_names) != EXPECTED_PLANES:
        errors.append(f"planes 集合必须为 {sorted(EXPECTED_PLANES)}，实际 {sorted(plane_names)}")
    if topo_subnets and topo_subnets != EXPECTED_PLANES:
        errors.append(
            f"environment_topology prod.subnets 不是四平面 {sorted(EXPECTED_PLANES)}：{sorted(topo_subnets)}"
        )
    if len(plane_names) != len(set(plane_names)):
        errors.append("planes 存在重复 plane 名")

    # workload 归属表：name -> inventory plane
    inv_plane_of = {w["name"]: w.get("plane") for w in inventory.get("workloads", [])}

    seen_accounts: dict[str, str] = {}
    seen_secrets: dict[str, str] = {}

    for p in planes:
        plane = p.get("plane")
        account = p.get("account")
        secret = p.get("sshKeySecret")
        access_mode = p.get("access")
        compose_root = p.get("composeProjectRoot")
        governed = p.get("governedWorkloads") or []
        deploy_plane = p.get("workloadDeployPlane")
        applies = p.get("appliesToStages") or []

        # 3. 账号一一对应
        if account != f"prod-{plane}-svc":
            errors.append(f"{plane}: account 必须为 prod-{plane}-svc，实际 {account}")
        if account in seen_accounts:
            errors.append(f"账号 {account} 被多个平面共用：{seen_accounts[account]} 与 {plane}")
        else:
            seen_accounts[account] = plane

        # 4. 凭据命名 + 唯一
        expected_secret = f"PROD_{str(plane).upper()}_SSH_KEY"
        if secret != expected_secret:
            errors.append(f"{plane}: sshKeySecret 必须为 {expected_secret}，实际 {secret}")
        if secret in seen_secrets:
            errors.append(f"secret {secret} 被多个平面复用：{seen_secrets[secret]} 与 {plane}")
        else:
            seen_secrets[secret] = plane

        # 5. 读写 vs data 只读
        if plane == "data":
            if access_mode != "read-only-audit":
                errors.append("data 平面 access 必须为 read-only-audit")
            if compose_root is not None:
                errors.append("data 平面 composeProjectRoot 必须为 null")
            if governed:
                errors.append("data 平面 governedWorkloads 必须为空（无 wired data workload）")
            if applies:
                errors.append("data 平面 appliesToStages 必须为空（不纳入 rollout）")
        else:
            if access_mode != "read-write":
                errors.append(f"{plane}: 读写平面 access 必须为 read-write")
            if not compose_root:
                errors.append(f"{plane}: 读写平面必须声明 composeProjectRoot")
            if not governed:
                errors.append(f"{plane}: 读写平面必须声明非空 governedWorkloads")
            if applies != EXPECTED_STAGES:
                errors.append(f"{plane}: 读写平面 appliesToStages 必须为 {EXPECTED_STAGES}")

        # 6. governedWorkloads ⊆ inventory，且 inventory plane == workloadDeployPlane
        for w in governed:
            if w not in inv_plane_of:
                errors.append(f"{plane}: governedWorkload '{w}' 不在 workload_topology_inventory")
                continue
            if deploy_plane and inv_plane_of[w] != deploy_plane:
                errors.append(
                    f"{plane}: workload '{w}' 的 inventory plane={inv_plane_of[w]} "
                    f"与 workloadDeployPlane={deploy_plane} 不一致"
                )

    # 7. 退役断言：访问隔离层不得重新引入单一全权 kube 凭据或远端 gamma
    raw = ACCESS.read_text(encoding="utf-8")
    if re.search(r"\bPROD_KUBECONFIG\b", raw) and "已退役" not in raw:
        errors.append("访问隔离层不得重新引入 PROD_KUBECONFIG 单一全权凭据")
    if "gamma-hosted" in raw:
        errors.append("访问隔离层不得引用已退役的 gamma-hosted 远端目标")

    # 8. 控制面投影：control_plane.yaml 必须有只读 prod_plane_access_isolation 投影对象，
    #    且不得引入 config scope（不污染现有配置面）。
    if not CONTROL_PLANE.exists():
        errors.append(f"缺少控制面 metadata {CONTROL_PLANE}")
    else:
        cp = load_yaml(CONTROL_PLANE)
        proj = next(
            (
                o
                for o in (cp.get("object_types") or [])
                if o.get("object_type") == "prod_plane_access_isolation"
            ),
            None,
        )
        if proj is None:
            errors.append("control_plane.yaml 缺少 prod_plane_access_isolation 投影对象")
        else:
            if proj.get("object_kind") != "snapshot":
                errors.append("prod_plane_access_isolation 投影必须为只读 snapshot")
            for op in proj.get("operations") or []:
                if op.get("method") != "GET":
                    errors.append("访问隔离投影只允许只读 GET 操作（不得写/变更）")
                for scope in op.get("scopes") or []:
                    if "config" in scope:
                        errors.append(
                            f"访问隔离投影不得使用 config scope（{scope}），避免污染现有配置面"
                        )

    if errors:
        print("FAIL: prod 四平面访问隔离映射校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        f"PASS: prod 四平面访问隔离映射（{len(planes)} planes，账号/凭据/路径/stage/workload 单一解释、与拓扑+inventory 一致）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
