---
name: environment-ops
description: Use stackctl to package, start, verify, inspect, diagnose, repair, and deploy the alpha/beta/gamma/prod environment topology. Use when the user asks about 环境启动、打包、URL/路由、健康检查、巡检、stackctl、gamma-local、prod gray rollout, or environment troubleshooting in this repository.
---
# Environment Ops

## Quick Start

在本仓库处理环境相关任务时，优先使用统一入口：

- `python3 quwoquan_ops/cli/stackctl.py package --env <alpha|beta|gamma|prod>`
- `python3 quwoquan_ops/cli/stackctl.py up --env <alpha|beta|gamma|prod-sim|prod> [--device-id <id>]`
- `make dev-up ENV=<alpha|beta|gamma|prod-sim|prod> [DEVICE_ID=<id>]`
- `python3 quwoquan_ops/cli/stackctl.py verify --kind all --profile baseline`
- `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile <smoke|integration|release>`
- `python3 quwoquan_ops/cli/stackctl.py health --target <target> --scope <edge|media|service|full>`
- `python3 quwoquan_ops/cli/stackctl.py inspect --target <target> --kind <logs|network|data|metrics|config|security|all>`
- `python3 quwoquan_ops/cli/stackctl.py doctor --target <target>`
- `python3 quwoquan_ops/cli/stackctl.py repair --target <target> --fix <rebuild-packages|restart-stack|reclaim-ports>`
- `python3 quwoquan_ops/cli/stackctl.py deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>`

## Rules

1. 不要把 `prod-gray` 当成额外环境。生产灰度是 `prod` 下的 rollout stage。
2. 不要手写本地 canonical 端口；读取 `quwoquan_ops/environments/local_env_port_manifest.yaml` 对应 profile。
3. 不要手写 public topology；通过 `stackctl` 读取 `quwoquan_ops/environments/<env>/runtime.yaml`，workload 从各服务和外部依赖的环境部署目录实时扫描。
4. 需要环境打包、纯度、URL 契约或 artifact 隔离时，先跑 `stackctl package`，再按证明边界选择 profile：无环境依赖为 `baseline`，Alpha mock 投影为 `smoke`，Beta/Gamma 内容数据平面为 `integration`，Gamma 商业观测和 Prod 为 `release`。
5. 需要诊断时，先 `health`，再 `inspect`，最后 `doctor`。只有白名单问题才执行 `repair`。
6. 远端/hosted 目标只有 `prod-hosted`（backend SSH 托管，gray 与 full 共享同一集群）；`gamma` 仅本地（`gamma-local`），不存在远端 gamma。`prod-hosted` 只通过 `stackctl deploy --target prod-hosted` 驱动 `gray-initial / carry-on / full` rollout stage，真实远端集成与 curated 媒体路由复验在 `gray-initial` 阶段完成；不要跳回旧脚本，除非是在修 `stackctl` 本身。

## Recommended Flows

### 本地 beta 联调

1. `stackctl package --env beta --include-services`
2. `stackctl up --env beta`
3. `stackctl health --target beta-local --scope full`
4. `stackctl inspect --target beta-local --kind all`

### local-gamma mirror

1. `stackctl package --env gamma --include-services`
2. `stackctl up --env gamma`
3. `stackctl health --target gamma-local --scope full`
4. `stackctl inspect --target gamma-local --kind all`

### 本地 prod / prod-sim 连接

1. `prod-sim` 使用 `stackctl up --env prod-sim`
2. `prod` 使用 `stackctl up --env prod`，它会先对 `prod-hosted` 执行 edge health，再拉起本地 App/浏览器
3. 不要为 prod attach 另写第二套 gateway/media 参数；public base 统一来自 `prod/runtime.yaml`

### hosted prod rollout（唯一远端目标）

1. 先确认 `stackctl verify --env prod --kind all --profile release` 通过。
2. 使用 `stackctl deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>`。
3. `prod-hosted` 走 `gray-initial / carry-on / full` rollout stage；真实远端集成与 curated 媒体路由复验在 `gray-initial` 阶段完成（不再有独立的远端 gamma-hosted 阶段）。
4. 每步运行证据以 `.qwq_output/env/prod/runs/**` 为准；prod 发布状态固定为 `QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/<service>.state`。

## Stop Conditions

遇到以下情况必须停下并请求人工确认：

- 生产审批、受保护环境放量、回滚前版本选择不明确
- 缺少密钥、token、SSH 凭据或 hosted base URL
- `prod-hosted` 缺少 `service / image / config / step / SLO` 任一必填输入
- 计划对 `prod-hosted` 执行 restart / rollout / cold-build 三模式，但当前实现并未开放对应命令面
- `repair` 需要超出白名单的破坏性动作
- 发现环境配置、artifact 或 host 污染与用户当前目标矛盾

## Evidence

优先引用这些产物：

- `.qwq_output/env/<env>/runs/<run-id>/report.json`
- `.qwq_output/env/<env>/runs/<run-id>/summary.md`
- `.qwq_output/env/gamma/local/gamma-local/process/report.json`
