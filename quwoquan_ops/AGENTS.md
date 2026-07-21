# quwoquan_ops Codex Guide

在 `quwoquan_ops/` 工作时，除仓库根 `AGENTS.md` 外，先阅读：

1. `docs/agent_context_contract.md`
2. `.cursor/skills/environment-ops/SKILL.md`
3. `quwoquan_ops/gate/gate_repo.sh`

## 运维与门禁硬约束

- 环境、打包、URL/topology、健康检查、巡检、诊断、修复和部署统一使用 `python3 quwoquan_ops/cli/stackctl.py`；不要新增第二套环境脚本入口。
- Ops 脚本按职责归入 `cli/`、`ci/`、`gate/`、`observability/`、`runbooks/` 等横切目录；禁止在 `quwoquan_ops/` 中按业务特性新增 `assistant/`、`avatar/`、`chat_avatar/` 等脚本岛或第二套 feature runner。跨环境 smoke/gate/CI 脚本统一归 `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/<service>/`；领域内可解耦测试仍归各服务 `tests/local_contract` 或 `tests/api_integration`。
- 四环境语义固定为 `alpha`、`beta`、`gamma`、`prod`；生产灰度是 `prod` rollout stage，不存在 `prod-gray`。
- 不手写端口、host、public URL、gateway/media base；统一读取 quwoquan_ops/environments manifests 与 stackctl 输出。
- `.qwq_output` 一级只允许 `env/` 与 `data/`。环境输出统一放 `.qwq_output/env/<env>/{runs,observability,local}/`，repo 级证据与临时状态放 `.qwq_output/env/repo/{runs,observability,local}/`，数据执行输出放 `.qwq_output/data/{tasks,releases,local}/`。
- `local/` 下每个 target 只允许 `process/` 与 `cache/`；`process/` 只保存 pid、进程状态、stdout/stderr 等可删除运行记录，`cache/` 只保存可重建缓存。渲染配置、`.env`、Caddyfile、Caddy data/config、TLS/证书和临时部署卷一律放仓外受限的 `QWQ_DEPLOY_WORK_ROOT`；配置、网络拓扑、证书生成规则与部署约束的真相源必须留在领域 `deploy/` 或 `quwoquan_ops/environments/`，不得写入 `.qwq_output`。
- App、Service、Legal-static 与 Portal 的可发布包统一写入 `QWQ_DEPLOY_WORK_ROOT/<target>/packages/{app,service,legal-static,ops-portal}/`；禁止将 deployment payload 写回 `.qwq_output`，也禁止重新引入 `packages/runtime/cache/tmp` 环境类别、根 `artifacts/`、`state/` 或环境特例目录。
- 远端唯一托管目标为 `prod-hosted`（ssh-hosted；远端 gamma 已退役，仅保留 `gamma-local`）。prod 远端访问按 `edge/media/service/data` 四平面去 root 隔离，凭据为按平面 SSH 私钥 `PROD_<PLANE>_SSH_KEY`，单一真相源 `quwoquan_ops/environments/prod_plane_access_isolation.yaml`；已退役单一全权 `PROD_KUBECONFIG`，禁止任何 prod 路径再依赖它或 `kubectl`。
- `repair` 只允许白名单修复；涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性动作时必须停下请求人工确认。
- 门禁脚本应可重复、可解释、失败信息能指向修复路径；禁止用 allowlist 掩盖新债。

## 证据要求

- 环境相关收口优先使用：`python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile smoke|integration|release`；`baseline` 不接受环境参数。
- hosted prod 操作（含 gray-initial 灰度验证，承接原远端 gamma 验证职责）以 `.qwq_output/env/prod/runs/**`、`QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/**` 和 stackctl summary/report 为证据。
- 新增 gate 必须说明触发范围、阻断条件、修复方式和是否接入 `make gate` / `gate_repo.sh`。

## 典型触发与 E2E

- 用户说“启动环境、部署、放量、回滚、健康检查、巡检、修复、门禁、CI”时，默认加载本文件。
- 环境任务通常是跨域收口层；必须把 App/Service/Data/Portal 的验证证据汇总到 stackctl 或 gate 输出。
- prod-hosted、密钥、破坏性 repair、回滚版本和流量放量必须人工确认后再执行。
