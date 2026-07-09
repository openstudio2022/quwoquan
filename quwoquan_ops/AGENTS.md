# quwoquan_ops Codex Guide

在 `quwoquan_ops/` 工作时，除仓库根 `AGENTS.md` 外，先阅读：

1. `docs/agent_context_contract.md`
2. `.cursor/skills/environment-ops/SKILL.md`
3. `quwoquan_ops/gate/gate_repo.sh`

## 运维与门禁硬约束

- 环境、打包、URL/topology、健康检查、巡检、诊断、修复和部署统一使用 `python3 quwoquan_ops/cli/stackctl.py`；不要新增第二套环境脚本入口。
- Ops 脚本按职责归入 `cli/`、`ci/`、`gate/`、`observability/`、`runbooks/` 等横切目录；禁止在 `quwoquan_ops/` 中按业务特性新增 `assistant/`、`avatar/`、`chat_avatar/` 等脚本岛或第二套 feature runner。特性相关 smoke/gate/CI 脚本归属对应领域服务的 `tests/ops/**`，Ops 只保留共享能力，例如 `ci/device_matrix/**`。
- 四环境语义固定为 `alpha`、`beta`、`gamma`、`prod`；生产灰度是 `prod` rollout stage，不存在 `prod-gray`。
- 不手写端口、host、public URL、gateway/media base；统一读取 quwoquan_ops/environments manifests 与 stackctl 输出。
- 环境临时凭据、配置文件、运行状态和验证证据保持跨环境一致；本地生成物统一放 `.qwq_output/**`，禁止新增根 `artifacts/`、`state/` 或环境特例目录。
- 远端唯一托管目标为 `prod-hosted`（ssh-hosted；远端 gamma 已退役，仅保留 `gamma-local`）。prod 远端访问按 `edge/media/service/data` 四平面去 root 隔离，凭据为按平面 SSH 私钥 `PROD_<PLANE>_SSH_KEY`，单一真相源 `quwoquan_ops/environments/prod_plane_access_isolation.yaml`；已退役单一全权 `PROD_KUBECONFIG`，禁止任何 prod 路径再依赖它或 `kubectl`。
- `repair` 只允许白名单修复；涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性动作时必须停下请求人工确认。
- 门禁脚本应可重复、可解释、失败信息能指向修复路径；禁止用 allowlist 掩盖新债。

## 证据要求

- 环境相关收口优先使用：`python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --tier all`。
- hosted prod 操作（含 gray-initial 灰度验证，承接原远端 gamma 验证职责）以 `.qwq_output/runs/**`、`.qwq_output/local/release-state/**` 和 stackctl summary/report 为证据。
- 新增 gate 必须说明触发范围、阻断条件、修复方式和是否接入 `make gate` / `gate_repo.sh`。

## 典型触发与 E2E

- 用户说“启动环境、部署、放量、回滚、健康检查、巡检、修复、门禁、CI”时，默认加载本文件。
- 环境任务通常是跨域收口层；必须把 App/Service/Data/Portal 的验证证据汇总到 stackctl 或 gate 输出。
- prod-hosted、密钥、破坏性 repair、回滚版本和流量放量必须人工确认后再执行。
