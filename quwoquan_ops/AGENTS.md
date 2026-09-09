# quwoquan_ops Agent Guide

本文件与根 `AGENTS.md` 同时生效，只声明 `quwoquan_ops/**` 每次变更都成立的不变量与工程入口。环境/拓扑/测试数据/布局的解释性知识由各 spec 拥有，这里只给一句指向，不复述。

## 运维与门禁硬约束

- 环境、打包、URL/topology、健康检查、巡检、诊断、修复和部署统一使用 `python3 quwoquan_ops/cli/stackctl.py`；不新增第二套环境脚本入口。`cli/**` 内部 runner 与 shell 只能由 `stackctl` 或登记的 gate/CI 入口调用，Make/workflow/runbook 不得绕过。
- Ops 脚本按职责归入 `cli/`、`ci/`、`gate/`、`observability/`、`runbooks/` 等横切目录；禁止按业务特性新增脚本岛或第二套 feature runner。跨环境 smoke/gate/CI 脚本归 `tests/acceptance/user_acceptance/service_ops/<service>/`，`producer: ops` 的 readiness case runner 直接指向该树内脚本并携带 `readiness_case`/`spec_ref` 双向标注；领域内可解耦测试仍归各服务 `tests/local_contract` 或 `tests/api_integration`。
- Ops pytest 套件必须同时满足 `test_` 前缀与三层后缀（`__local_contract_test.py` / `__api_integration_test.py` / `__user_acceptance_test.py`）。`tests/local_contract` 根只允许已登记 concern 子目录（`service_ops`、`stackctl`、`test_data`），根平铺存量与 provider conformance 声明残量只减不增；`service_ops/<service>/` 角色目录为 `ci/smoke/gamma/gate/support` 闭集。
- Ops 物理树内全部 Python 文件必须由脚本角色、三层测试、test support 或其他明确治理边界唯一归类；未知路径、无 owner 人工 tool、空扫描 gate、临时脚本和 Python/lint/test 缓存（含 `.ruff_cache`、`.mypy_cache`、编辑器备份）均为阻断项。
- 四环境语义固定为 `alpha`、`beta`、`gamma`、`prod`；生产灰度是 `prod` rollout stage，不存在 `prod-gray`。远端唯一托管目标为 `prod-hosted`（远端 gamma 已退役，仅保留 `gamma-local`）；prod 凭据只按平面 `PROD_<PLANE>_SSH_KEY`，真相源 `quwoquan_ops/environments/prod/access-isolation.yaml`，禁止任何 prod 路径依赖已退役的 `PROD_KUBECONFIG` 或 `kubectl`。
- 四环境 App 均使用 production Remote composition。内容、Creator、实体与发布媒体只能由 canonical immutable release activation 产生；Alpha/Beta/Gamma 的账号、评论、圈子、会话和消息只允许 `stackctl verify` 以真实非生产身份经领域公开 command/event 创建，Prod 只接受真实用户或正式运营行为。任何环境禁止 Mongo/PostgreSQL/Redis 直写、fixture manifest、派生投影预填或 App 数据源切换。
- 不手写端口、host、public URL、gateway/media base；统一读取 `quwoquan_ops/environments` manifests 与 stackctl 输出。组网、四平面隔离与放量叙事归 [`system-topology-and-networking`](../specs/feature-tree/runtime/system-topology-and-networking/spec.md)。
- `.qwq_output`、`local/{process,cache}`、`QWQ_DEPLOY_WORK_ROOT` 的目录布局与禁入项由 [`system-architecture-and-engineering-guide`](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md) 拥有并由 `verify_root_layout` 门禁锁定；配置、拓扑、证书规则的真相源留在领域 `deploy/` 或 `quwoquan_ops/environments/`，deployment payload 不写回 `.qwq_output`。
- `repair` 只允许白名单修复；涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性动作时必须停下请求人工确认。
- 门禁脚本应可重复、可解释、失败信息能指向修复路径；禁止用 allowlist 掩盖新债。新增 gate 必须说明触发范围、阻断条件、修复方式和是否接入 `make gate` / `gate_repo.sh`。
- ContractGraph 的 `readinessEvidence` 绑定被扫描实现/测试的确切字节，重建 graph/lock/manifest 必须在这些文件静止时一次做完；判据 `make verify-app-contract-handoff-inputs`，解释归 [`app-cloud-business-object-commercial-closure`](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md)。

## 证据要求

- 环境相关收口优先使用 `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile smoke|integration|release`；`baseline` 不接受环境参数。hosted prod 操作以 `.qwq_output/env/prod/runs/**`、`QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/**` 与 stackctl summary/report 为证据。
- Alpha/Beta/Gamma 测试数据只经 `stackctl verify` / `test-data-request` / `test-data-evidence` 消费强类型 request/evidence，测试不得手拼 JSON、书写 Provider capability 字符串或导入 Provider；DAG 执行、`ProviderCapabilityKey` 与 capabilities/providers 边界归 [`test-data-provisioning-and-isolation`](../specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md)。
- 环境任务是跨域收口层：必须把 App/Service/Data/Portal 的验证证据汇总到 stackctl 或 gate 输出。
