---
name: environment-ops
description: Use stackctl to package, start, verify, inspect, diagnose, repair, and deploy the alpha/beta/gamma/prod environment topology. Make sure to use this skill whenever the user mentions 环境启动, 打包, URL, 路由, 健康检查, 巡检, 部署, 灰度, 回滚, stackctl, gamma-local, prod-hosted, prod gray rollout, or any environment troubleshooting in this repository, even without an explicit command.
metadata:
  kind: workflow
---

# environment-ops

以 `stackctl` 为唯一主线操作 alpha/beta/gamma/prod 环境拓扑。五段执行契约见根 `AGENTS.md`。

## 触发

无斜杠命令，自然语言自动触发：环境打包、启动、URL/路由、health/inspect/doctor/repair、
部署、灰度或回滚。

## 输入

- 目标环境 / target（`alpha|beta|gamma|prod-sim|prod|prod-hosted`）与服务。
- 发布类请求另需：候选制品（image/config/manifest）、SLO 参数、人工确认状态。
- 恢复类请求另需：诊断证据与白名单内的修复动作。

## 角色

见 [references/roles/](references/roles/)：

- [environment-operator](references/roles/environment-operator.md)：package / up / health / inspect。
- [release-operator](references/roles/release-operator.md)：candidate、SLO 与 prod-hosted rollout。
- [recovery-operator](references/roles/recovery-operator.md)：doctor、白名单 repair、rollback。

按请求类型选定角色与 stackctl 子命令序列，逐步采集运行证据。

## 执行

自由度：低（stackctl 子命令是固定操作面）。

统一入口：

- `python3 quwoquan_ops/cli/stackctl.py package --env <alpha|beta|gamma|prod>`
- `python3 quwoquan_ops/cli/stackctl.py up --env <alpha|beta|gamma|prod-sim|prod> [--device-id <id>]`
- `make dev-up ENV=<alpha|beta|gamma|prod-sim|prod> [DEVICE_ID=<id>]`
- `python3 quwoquan_ops/cli/stackctl.py verify --kind all --profile <baseline|smoke|integration|release>`
- `python3 quwoquan_ops/cli/stackctl.py health --target <target> --scope <edge|media|service|full>`
- `python3 quwoquan_ops/cli/stackctl.py inspect --target <target> --kind <logs|network|data|metrics|config|security|all>`
- `python3 quwoquan_ops/cli/stackctl.py doctor --target <target>`
- `python3 quwoquan_ops/cli/stackctl.py repair --target <target> --fix <rebuild-packages|restart-stack|reclaim-ports>`
- `python3 quwoquan_ops/cli/stackctl.py deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>`
- `python3 quwoquan_ops/cli/stackctl.py deploy --target prod-hosted --mode prevalidate --ssh-host <ssh-host> --data-mode <isolated|external> --prevalidate-scope first-party --release-manifest <manifest.json>`

规则：

1. 不把 `prod-gray` 当环境。生产灰度是 `prod` 下的 rollout stage。
2. 不手写本地 canonical 端口；读 `quwoquan_ops/environments/local_env_port_manifest.yaml` 对应 profile。
3. 不手写 public topology；经 `stackctl` 读 `quwoquan_ops/environments/<env>/runtime.yaml`。
4. 打包 / 纯度 / URL 契约先 `stackctl package`，再按证明边界选 profile：
   无环境依赖 `baseline`，四环境 Remote 启动与 release 只读探针 `smoke`，
   Alpha/Beta/Gamma 内容数据平面 `integration`，Gamma 商业观测和 Prod `release`。
5. 诊断顺序固定：先 `health`，再 `inspect`，最后 `doctor`；只有白名单问题才 `repair`。
6. 远端 / hosted 目标只有 `prod-hosted`；`gamma` 仅本地（`gamma-local`）。
   `prod-hosted` 只经 `stackctl deploy` 驱动 `canary / 5 / 20 / 50 / 100` rollout stage，
   真实远端集成与 curated 媒体路由复验在 `canary` 阶段完成。
7. `mode=prevalidate` 是不可提升的第一方容器验证：公网 IP 只允许作为 `--ssh-host`，
   必须消费 clean reviewed main 的 Service Pipeline digest 制品；不得接受 rollout/SLO/rollback
   参数，不得写正式 release ledger/receipt，release eligibility 始终 `GATE_BLOCK`。
8. prod-hosted 的 `inspect/doctor --ssh-host` 只用于隔离账号 SSH 巡检；该值不得写入
   runtime public base，巡检必须同时报告 user systemd enabled/active、容器状态和镜像 identity。

典型序列（本地联调 / rollout / prevalidate 的完整步骤见各角色文件）。

## 交付件

**环境操作回执**：环境报告、运行证据、发布或恢复结论。证据引用：

- `.qwq_output/env/<env>/runs/<run-id>/report.json` 与 `summary.md`
- `.qwq_output/env/gamma/local/gamma-local/process/report.json`
- prod 发布状态：`QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/<service>.state`

送审前自检：每一步有运行证据引用；停止条件逐条核对未触发。

## 内置评审

- 涉及 prod rollout / rollback 的操作 POST 调 `review`
  （workflow=`environment-ops`，segment=POST，deliverable=`release-evidence`），
  角色 ops（environment-release）+ infra-capacity。
- 纯查询类操作（health / inspect / verify 只读）免评审。

## 失败与停止

遇到以下情况必须停下并请求人工确认：

- 生产审批、受保护环境放量、回滚前版本选择不明确。
- 缺少密钥、token、SSH 凭据或 hosted base URL。
- `prod-hosted` 缺少 `service / image / config / step / SLO` 任一必填输入。
- prevalidate 缺 GHCR OCI digest manifest、工作区非 clean/reviewed main、
  主机低于 `access-isolation.yaml` 资源门，或目标端口冲突。
- `repair` 需要超出白名单的破坏性动作。
- 发现环境配置、artifact 或 host 污染与用户当前目标矛盾。

## HANDOFF

- **产出物**：环境操作回执，报告给用户。
- **未决项去向**：未完成的诊断或发布步骤如实列出并给出恢复入口。
- **唯一合法下游**：发现代码缺陷时交接 `incident-inspection`（需巡检定级）或 `dev`
  （已有复现证据）；其余报告给用户结束。
- **证据链**：上述 `.qwq_output` 运行产物。
