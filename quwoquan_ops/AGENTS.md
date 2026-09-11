# quwoquan_ops Agent Guide

与根 `AGENTS.md` 同时生效，仅声明 `quwoquan_ops/**` 不变量与入口；环境、拓扑、测试数据、布局解释归各 spec。

## 运维与门禁硬约束

- 环境、打包、URL/topology、health、巡检、诊断、修复和部署仅经 `python3 quwoquan_ops/cli/stackctl.py`；不建第二入口。内部 runner/shell 仅由 stackctl 或登记的 gate/CI 调用，Make/workflow/runbook 不得绕过。
- 脚本按职责归 `cli/ci/gate/observability/runbooks`，禁止业务脚本岛或第二 feature runner。跨环境 smoke/gate/CI 归 `tests/acceptance/user_acceptance/service_ops/<service>/`；`producer: ops` readiness runner 指向该树并双向标注 `readiness_case/spec_ref`。领域可解耦测试归服务的 `tests/local_contract` 或 `tests/api_integration`。
- Ops pytest 套件必须同时满足 `test_` 前缀与三层后缀（`__local_contract_test.py` / `__api_integration_test.py` / `__user_acceptance_test.py`）。`tests/local_contract` 根只允许已登记 concern 子目录（`service_ops`、`stackctl`、`test_data`），根平铺存量与 provider conformance 声明残量只减不增；`service_ops/<service>/` 角色目录为 `ci/smoke/gamma/gate/support` 闭集。
- Python 文件必须唯一归类为脚本角色、三层测试、test support 或明确治理边界；未知路径、无 owner tool、空扫描 gate、临时脚本及 Python/lint/test 缓存（含 `.ruff_cache/.mypy_cache`、编辑器备份）均阻断。
- 环境固定为 `alpha/beta/gamma/prod`，灰度仅为 prod rollout stage，无 `prod-gray`。远端仅 `prod-hosted`，gamma 仅本地。Prod 凭据只用 `PROD_<PLANE>_SSH_KEY`，真相源 `quwoquan_ops/environments/prod/access-isolation.yaml`；禁止依赖 `PROD_KUBECONFIG/kubectl`。
- Alpha App 的 canonical 离线快照与 Beta/Gamma/Prod Remote 只读装配遵循 [`environment-topology-and-packaging` REQ-008](../specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-008)；离线证据不替代 Alpha API gate 或服务端 activation。在线内容、Creator、实体与媒体只经 canonical immutable release 发布；candidate 查询预物化只经各领域 owner 的正式准备路径，不准直写派生库或伪造 ready。Alpha/Beta/Gamma 的账号、评论、圈子、会话和消息只允许 `stackctl verify` 以真实非生产身份经领域公开 command/event 创建，Prod 只接受真实用户或正式运营行为。禁止数据库直写、fixture manifest、运行中隐式数据源切换和故障 fallback。
- 本地遵循 [实例隔离](../specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md)：跨 worktree host-target 单实例、共享租约及 executor fence。不同 target 可并行；矩阵及失败清理不得动未拥有的实例、设备、信任或转发。
- 不手写端口、host、public URL、gateway/media base；统一读取 `quwoquan_ops/environments` manifests 与 stackctl 输出。组网、四平面隔离与放量叙事归 [`system-topology-and-networking`](../specs/feature-tree/runtime/system-topology-and-networking/spec.md)。
- `.qwq_output`、`local/{process,cache}`、`QWQ_DEPLOY_WORK_ROOT` 的目录布局与禁入项由 [`system-architecture-and-engineering-guide`](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md) 拥有并由 `verify_root_layout` 门禁锁定；配置、拓扑、证书规则的真相源留在领域 `deploy/` 或 `quwoquan_ops/environments/`，deployment payload 不写回 `.qwq_output`。
- `repair` 只允许白名单修复；涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性动作时必须停下请求人工确认。
- 门禁须可重复、可解释并指向修复；禁止 allowlist 掩盖新债。新 gate 声明范围、阻断、修复及 `make gate/gate_repo.sh` 接线。
- `readinessEvidence` 绑定实现/测试 exact bytes；graph/lock/manifest 须在输入静止时一并重建，以 `make verify-app-contract-handoff-inputs` 验证，语义归 [合同交接](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md)。

## 证据要求

- 环境相关收口优先使用 `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile smoke|integration|release`；`baseline` 不接受环境参数。hosted prod 操作以 `.qwq_output/env/prod/runs/**`、`QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/**` 与 stackctl summary/report 为证据。
- Alpha/Beta/Gamma 测试数据只经 `stackctl verify` / `test-data-request` / `test-data-evidence` 消费强类型 request/evidence，测试不得手拼 JSON、书写 Provider capability 字符串或导入 Provider；DAG 执行、`ProviderCapabilityKey` 与 capabilities/providers 边界归 [`test-data-provisioning-and-isolation`](../specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md)。
- 环境任务须把 App/Service/Data/Portal 证据汇总至 stackctl 或 gate 输出。
