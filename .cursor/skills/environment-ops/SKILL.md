---
name: environment-ops
description: Use stackctl to package, start, verify, inspect, diagnose, repair, and deploy the alpha/beta/gamma/prod environment topology. Use when the user asks about 环境启动、打包、URL/路由、健康检查、巡检、stackctl、gamma hosted、prod rollout, or environment troubleshooting in this repository.
---
# Environment Ops

## Quick Start

在本仓库处理环境相关任务时，优先使用统一入口：

- `python3 agent_ops/deploy/stackctl.py package --env <alpha|beta|gamma|prod>`
- `python3 agent_ops/deploy/stackctl.py up --env <alpha|beta|gamma|prod-sim|prod> [--device-id <id>]`
- `make dev-up ENV=<alpha|beta|gamma|prod-sim|prod> [DEVICE_ID=<id>]`
- `python3 agent_ops/deploy/stackctl.py verify [--env <env>] [--kind <topology|config|packaging|all>] [--tier <t1|t2|t3|t4|all>]`
- `python3 agent_ops/deploy/stackctl.py health --target <target> --scope <edge|media|service|full>`
- `python3 agent_ops/deploy/stackctl.py inspect --target <target> --kind <logs|network|data|metrics|config|security|all>`
- `python3 agent_ops/deploy/stackctl.py doctor --target <target>`
- `python3 agent_ops/deploy/stackctl.py repair --target <target> --fix <rebuild-packages|restart-stack|reclaim-ports>`
- `python3 agent_ops/deploy/stackctl.py deploy --target <gamma-hosted|prod-hosted> ...`

## Rules

1. 不要把 `prod-gray` 当成额外环境。生产灰度是 `prod` 下的 rollout stage。
2. 不要手写本地 canonical 端口；读取 `deploy/shared/local_env_port_manifest.yaml` 对应 profile。
3. 不要手写 public topology；读取 `deploy/shared/environment_topology_manifest.yaml`。
4. 需要环境打包、纯度、URL 契约或 artifact 隔离时，先跑 `stackctl package`，再跑 `stackctl verify --kind ...`；需要 T1~T4 证据时再显式追加 `--tier ...`。
5. 需要诊断时，先 `health`，再 `inspect`，最后 `doctor`。只有白名单问题才执行 `repair`。
6. `gamma-hosted` / `prod-hosted` 发布优先走 `stackctl deploy`，不要直接发散到多套旧脚本，除非是在修 `stackctl` 本身。

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
3. 不要为 prod attach 另写第二套 gateway/media 参数；public base 统一来自 topology

### hosted gamma / prod

1. 先确认 `stackctl verify --kind all` 通过。
2. `gamma-hosted` 使用 `stackctl deploy --target gamma-hosted ...`
3. `prod-hosted` 使用 `stackctl deploy --target prod-hosted ...`
4. 发布后立即执行 `stackctl health --scope full`、`stackctl inspect --kind all`、`stackctl doctor`

## Stop Conditions

遇到以下情况必须停下并请求人工确认：

- 生产审批、受保护环境放量、回滚前版本选择不明确
- 缺少密钥、token、SSH 凭据或 hosted base URL
- `repair` 需要超出白名单的破坏性动作
- 发现环境配置、artifact 或 host 污染与用户当前目标矛盾

## Evidence

优先引用这些产物：

- `artifacts/stackctl/<env>/<run-id>/report.json`
- `artifacts/stackctl/<env>/<run-id>/summary.md`
- `artifacts/local-gamma/report.json`
