#!/usr/bin/env python3
"""校验 prod-hosted 四平面访问隔离映射的单一真相源一致性（去 root · 取消远端 gamma）。

真相源：
  - quwoquan_ops/environments/prod/access-isolation.yaml            （访问隔离层：平面->账号->凭据->路径->stage->workload）
  - quwoquan_ops/environments/prod/runtime.yaml                      （prod 网络与目标事实）
  - 服务和 external 的 prod deploy 入口                             （prod workload 与 plane 归属）

校验项（保证单一解释、最小权限、与四环境一致）：
  1. schema / target=prod-hosted / rolloutStages=[gray-initial,carry-on,full]。
  2. planes 集合 == topology prod.subnets 的四平面 {edge,media,service,data}。
  3. 账号一一对应：每平面账号唯一且命名 prod-<plane>-svc；无两平面共用账号。
  4. 凭据：每平面 sshKeySecret 唯一且命名 PROD_<PLANE>_SSH_KEY；relay=PROD_OPS_SSH_KEY；禁止复用单一全权 secret。
  5. 读写平面：composeProjectRoot 非空 + governedWorkloads 非空；data 平面 read-only-audit、composeProjectRoot=null、
     governedWorkloads 空、appliesToStages 空。
  6. governedWorkloads ⊆ environment topology 的 prod workload，且 plane == 本平面 workloadDeployPlane。
  7. prevalidation 必须不可提升、资源阈值充足、服务/端口归属唯一且隔离数据镜像全部 digest-pinned。
  8. 退役断言：仓库不得在访问隔离层重新引入 PROD_KUBECONFIG 单一全权凭据或 gamma-hosted 远端目标。
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import load_environment_topology

ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
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
    for path in (ACCESS,):
        if not path.exists():
            print(f"FAIL: 缺少 {path}", file=sys.stderr)
            return 1

    access = load_yaml(ACCESS)
    topology = load_environment_topology()

    # 1. 顶层契约
    if access.get("schema") != "prod-plane-access-isolation":
        errors.append("schema 必须为 prod-plane-access-isolation")
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

    topology_workloads = prod_env.get("workloads") or []
    topology_plane_of = {
        str(workload.get("id")): str(workload.get("plane"))
        for workload in topology_workloads
    }

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

        # 6. governedWorkloads only reference the sole prod topology.
        for w in governed:
            if w not in topology_plane_of:
                errors.append(f"{plane}: governedWorkload '{w}' 不在 prod environment topology")
                continue
            if deploy_plane and topology_plane_of[w] != deploy_plane:
                errors.append(
                    f"{plane}: workload '{w}' 的 topology plane={topology_plane_of[w]} "
                    f"与 workloadDeployPlane={deploy_plane} 不一致"
                )

        if plane == "service":
            runtime_layout = p.get("rootlessRuntimeLayout") or {}
            if "mediaRoot" in runtime_layout:
                errors.append("service: mediaRoot 物理路径已退役，必须使用 mediaStateRef")
            media_state_ref = str(runtime_layout.get("mediaStateRef") or "")
            if not media_state_ref.startswith(("process/", "cache/")):
                errors.append(
                    "service: mediaStateRef 必须归属 env/prod/local/prod-hosted 的 process 或 cache"
                )
            if ".." in Path(media_state_ref).parts:
                errors.append("service: mediaStateRef 禁止路径穿越")
            rootless_services = set(
                p.get("rootlessGovernedComposeServices") or []
            )
            bindings = p.get("rootlessProjectionBindings") or []
            binding_services = [
                str(binding.get("composeService") or "")
                for binding in bindings
            ]
            if set(binding_services) != rootless_services:
                errors.append(
                    "service: rootlessProjectionBindings 必须与 "
                    "rootlessGovernedComposeServices 一一对应"
                )
            if len(binding_services) != len(set(binding_services)):
                errors.append(
                    "service: rootlessProjectionBindings 存在重复 composeService"
                )
            for binding in bindings:
                compose_service = str(
                    binding.get("composeService") or ""
                )
                owner_workload = str(
                    binding.get("ownerWorkload") or ""
                )
                runtime_role = str(binding.get("runtimeRole") or "")
                if owner_workload not in governed:
                    errors.append(
                        f"service: {compose_service} ownerWorkload "
                        f"{owner_workload!r} 不在 governedWorkloads"
                    )
                    continue
                if compose_service != owner_workload and not runtime_role:
                    errors.append(
                        f"service: {compose_service} 是 {owner_workload} "
                        "的运行投影别名，必须声明 runtimeRole"
                    )

    # 7. 不可提升的第一方容器预验证投影。
    prevalidation = access.get("prevalidation") or {}
    if (
        prevalidation.get("mode") != "prevalidate"
        or prevalidation.get("promotable") is not False
        or prevalidation.get("scopes") != ["first-party"]
        or prevalidation.get("allowedDataModes") != ["isolated", "external"]
    ):
        errors.append("prevalidation 必须为不可提升的 first-party isolated|external 投影")
    release_evidence = prevalidation.get("releaseEvidence") or {}
    if any(
        release_evidence.get(key) is not False
        for key in ("eligible", "writeLedger", "writeReceipt")
    ):
        errors.append("prevalidation 禁止获得 release 资格或写 ledger/receipt")
    readiness = prevalidation.get("readinessPolicy") or {}
    if not (
        readiness.get("requireContainerRunning") is True
        and readiness.get("requireHealthyExceptProviderBound") is True
        and readiness.get("providerReadinessStatus") == "GATE_BLOCK"
        and set(readiness.get("providerBoundServices") or [])
        == {"product-ops-service"}
    ):
        errors.append(
            "prevalidation 必须区分容器存活与外部 Provider readiness，且后者保持 GATE_BLOCK"
        )
    minimum = prevalidation.get("minimumHostResources") or {}
    if (
        int(minimum.get("cpuCores") or 0) < 4
        or int(minimum.get("memoryBytes") or 0) < 16 * 1024**3
        or int(minimum.get("containerFreeBytes") or 0) < 40 * 1024**3
    ):
        errors.append("prevalidation 主机阈值不得低于 4C/16GiB/40GiB free")
    prevalidation_planes = prevalidation.get("planes") or {}
    if set(prevalidation_planes) != {"service", "edge"}:
        errors.append("prevalidation 只允许 service/edge 两个运行平面")
    prevalidation_ports: list[int] = []
    for plane_name, projection in prevalidation_planes.items():
        plane_spec = next((item for item in planes if item.get("plane") == plane_name), {})
        governed = set(plane_spec.get("rootlessGovernedComposeServices") or [])
        startup = set(projection.get("startupServices") or [])
        image_only = set(projection.get("imageAndConfigOnlyServices") or [])
        if not startup or not (startup | image_only).issubset(governed):
            errors.append(f"prevalidation {plane_name} 服务逃逸 rootless 平面归属")
        if startup & image_only:
            errors.append(f"prevalidation {plane_name} startup/image-only 重叠")
        ports = [int(item) for item in projection.get("exposedPorts") or []]
        if not ports or any(port < 1024 or port > 65535 for port in ports):
            errors.append(f"prevalidation {plane_name} 暴露端口非法")
        prevalidation_ports.extend(ports)
    if len(prevalidation_ports) != len(set(prevalidation_ports)):
        errors.append("prevalidation service/edge 目标端口必须全局唯一")
    service_projection = prevalidation_planes.get("service") or {}
    if service_projection.get("imageAndConfigOnlyServices") != ["integration-service"]:
        errors.append("prevalidation integration-service 必须且只能 image/config-only")
    isolated = prevalidation.get("isolatedData") or {}
    if not (
        isolated.get("empty") is True
        and isolated.get("seedAllowed") is False
        and isolated.get("productionDataAllowed") is False
        and isolated.get("releaseEvidenceEligible") is False
    ):
        errors.append("prevalidation isolated data 必须空、无 seed、无正式数据且非 release evidence")
    isolated_services = set(isolated.get("services") or [])
    isolated_images = isolated.get("images") or {}
    if isolated_services != set(isolated_images) or any(
        re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", str(ref or "")) is None
        for ref in isolated_images.values()
    ):
        errors.append("prevalidation isolated data 镜像必须逐项固定 digest")
    excluded = prevalidation.get("excluded") or {}
    if not {"livekit", "coturn"}.issubset(set(excluded.get("workloads") or [])):
        errors.append("prevalidation 必须排除 LiveKit SFU 与 Coturn")

    # 8. 退役断言：访问隔离层不得重新引入单一全权 kube 凭据或远端 gamma
    raw = ACCESS.read_text(encoding="utf-8")
    if re.search(r"\bPROD_KUBECONFIG\b", raw) and "已退役" not in raw:
        errors.append("访问隔离层不得重新引入 PROD_KUBECONFIG 单一全权凭据")
    if "gamma-hosted" in raw:
        errors.append("访问隔离层不得引用已退役的 gamma-hosted 远端目标")
    if "/opt/quwoquan/gamma/.qwq_output" in raw:
        errors.append("prod 访问隔离层不得依赖 gamma-local 物理输出路径")

    # 9. 控制面投影：control_plane.yaml 必须有只读 prod_plane_access_isolation 投影对象，
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
            if proj.get("view_kind") != "snapshot":
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
        f"PASS: prod 四平面访问隔离映射（{len(planes)} planes，账号/凭据/路径/stage/workload 单一解释、与唯一环境拓扑一致）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
