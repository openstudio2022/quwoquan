# quwoquan_ops Codex Guide

在 `quwoquan_ops/` 工作时，除仓库根 `AGENTS.md` 外，先阅读：

1. `specs/feature-tree/README.md`
2. 目标特性父链，或运行 `make feature-context TARGET=<path>`
3. `.cursor/skills/environment-ops/SKILL.md`
4. `quwoquan_ops/gate/gate_repo.sh`

## 运维与门禁硬约束

- 环境、打包、URL/topology、健康检查、巡检、诊断、修复和部署统一使用 `python3 quwoquan_ops/cli/stackctl.py`；不要新增第二套环境脚本入口。
- Ops 脚本按职责归入 `cli/`、`ci/`、`gate/`、`observability/`、`runbooks/` 等横切目录；禁止在 `quwoquan_ops/` 中按业务特性新增 `assistant/`、`avatar/`、`chat_avatar/` 等脚本岛或第二套 feature runner。跨环境 smoke/gate/CI 脚本统一归 `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/<service>/`；领域内可解耦测试仍归各服务 `tests/local_contract` 或 `tests/api_integration`。
- `cli/**` 内部 runner 与 shell 只能由 `stackctl` 或登记的 gate/CI 入口调用；存在实现文件不等于公开入口，Make/workflow/runbook 不得绕过 canonical 编排直接调用。
- Ops 物理树内全部 Python 文件必须由脚本角色、三层测试、test support 或其他明确治理边界唯一归类；未知路径、无 owner 人工 tool、空扫描 gate、临时脚本和 Python/lint/test 缓存均为阻断项。
- 四环境语义固定为 `alpha`、`beta`、`gamma`、`prod`；生产灰度是 `prod` rollout stage，不存在 `prod-gray`。
- 四环境 App 均使用 production Remote composition。内容、Creator、实体与发布媒体只能由 canonical immutable release activation 产生；Alpha/Beta/Gamma 的账号、评论、圈子、会话和消息只允许 `stackctl verify` 使用真实非生产身份经领域公开 command/event 创建，Prod 只接受真实用户或正式运营行为。任何环境均禁止 Mongo/PostgreSQL/Redis 直写、fixture manifest、派生投影预填或 App 数据源切换。
- 不手写端口、host、public URL、gateway/media base；统一读取 quwoquan_ops/environments manifests 与 stackctl 输出。
- `.qwq_output` 一级只允许 `env/` 与 `data/`。环境输出统一放 `.qwq_output/env/<env>/{runs,observability,local}/`，repo 级证据与临时状态放 `.qwq_output/env/repo/{runs,observability,local}/`，数据执行输出放 `.qwq_output/data/{tasks,releases,local}/`。
- `local/` 下每个 target 只允许 `process/` 与 `cache/`；`process/` 只保存 pid、进程状态、stdout/stderr 等可删除运行记录，`cache/` 只保存可重建缓存。渲染配置、`.env`、Caddyfile、Caddy data/config、TLS/证书和临时部署卷一律放仓外受限的 `QWQ_DEPLOY_WORK_ROOT`；配置、网络拓扑、证书生成规则与部署约束的真相源必须留在领域 `deploy/` 或 `quwoquan_ops/environments/`，不得写入 `.qwq_output`。
- App、Service、Legal-static 与 Portal 的可发布包统一写入 `QWQ_DEPLOY_WORK_ROOT/<target>/packages/{app,service,legal-static,ops-portal}/`；禁止将 deployment payload 写回 `.qwq_output`，也禁止重新引入 `packages/runtime/cache/tmp` 环境类别、根 `artifacts/`、`state/` 或环境特例目录。
- 远端唯一托管目标为 `prod-hosted`（ssh-hosted；远端 gamma 已退役，仅保留 `gamma-local`）。prod 远端访问按 `edge/media/service/data` 四平面去 root 隔离，凭据为按平面 SSH 私钥 `PROD_<PLANE>_SSH_KEY`，单一真相源 `quwoquan_ops/environments/prod/access-isolation.yaml`；已退役单一全权 `PROD_KUBECONFIG`，禁止任何 prod 路径再依赖它或 `kubectl`。
- `repair` 只允许白名单修复；涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性动作时必须停下请求人工确认。
- 门禁脚本应可重复、可解释、失败信息能指向修复路径；禁止用 allowlist 掩盖新债。
- ContractGraph 的输入不只是契约声明：编译期还按 `--repo-root` 扫描 `internal/**`、`tests/**` 与端侧 `lib/service/**`，把每个文件的确切字节绑进 `readinessEvidence`。`sourceDigestSetSha256` 只覆盖声明侧，`compilerHash` 只覆盖 `internal/metadata/**`，两者都看不到实现/测试输入漂移，因此「摘要不变而 graph sha256 变化」是合法现象，不是生成器非确定性。重建 graph/lock/manifest 必须在这些被扫描的实现与测试文件静止时一次做完，中途被并行会话改动会得到一份自洽但已过期的锁；用 `make verify-app-contract-handoff-inputs` 判定 graph 相对自身输入是否仍成立。
- 可再生产 Python 输出和缓存只进入 `.qwq_output/env/repo/**` 或仓外受管缓存；源码树禁止 `__pycache__`、`.pytest_cache`、`.ruff_cache`、`.mypy_cache`、编辑器备份与 scratch 文件。

## 证据要求

- 环境相关收口优先使用：`python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile smoke|integration|release`；`baseline` 不接受环境参数。
- hosted prod 操作（含 `canary` 单实例验证及 `5/20/50/100` 分阶段放量，承接原远端 gamma 验证职责）以 `.qwq_output/env/prod/runs/**`、`QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/**` 和 stackctl summary/report 为证据。
- 新增 gate 必须说明触发范围、阻断条件、修复方式和是否接入 `make gate` / `gate_repo.sh`。
- Alpha/Beta/Gamma 测试数据统一由 `stackctl verify` 消费强类型 request/evidence：控制面只加载选中 capability 的 Provider 依赖闭包，以 DAG 有界并行执行并记录 provision/readback/test/cleanup 分段耗时、operation count 与追加式 receipt；Prod 在首条 mutation 前拒绝。
- 七领域 release 关键 Journey 请求只由 `python3 quwoquan_ops/cli/stackctl.py test-data-request` 从强类型 composition 生成；integration 的 focused selection 由具体测试直接组合 case factory，不得手工拼 JSON、case 字符串 registry 或 capability inventory。
- 外部 Provider 依赖使用 `ProviderCapabilityKey`，由 `stackctl test-data-evidence` 从当前 conformance readiness 仅投影选中 request 的精确闭包并绑定 candidate/request digest；测试不得直接书写 Provider capability 字符串。
- `quwoquan_ops/cli/lib/test_data/capabilities/**` 只公开 frozen params/result 与 capability 引用，`providers/**` 只实现所属领域且不得导入兄弟 Provider；测试不得导入 Provider、书写 capability key 或传裸 `dict` params。不得建立 registry/inventory、兼容双轨或测试专用业务 API。

## 典型触发与 E2E

- 用户说“启动环境、部署、放量、回滚、健康检查、巡检、修复、门禁、CI”时，默认加载本文件。
- 环境任务通常是跨域收口层；必须把 App/Service/Data/Portal 的验证证据汇总到 stackctl 或 gate 输出。
- prod-hosted、密钥、破坏性 repair、回滚版本和流量放量必须人工确认后再执行。
