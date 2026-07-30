# L2 Design：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚”需要 `daily-merge-release-strategy`、`gray-release-to-prod`、`local-gamma-mirror`、`multi-environment-instance-isolation`、`multi-environment-wave-deployment`、`workflow-naming-consolidation` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：**分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：按 alpha、beta、gamma、prod 的准入顺序发布同一制品，任一波次失败即停止晋级。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_ops/environments`、`quwoquan_ops/environments/prod/kustomization.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 main 后只允许一条权威受控主链
- 决策：main 后只允许一条权威受控主链。
- 理由：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- main push 自动启动同一 DAG，完成不可变 OCI `ReleaseEvidenceManifest` 的 `component-ready -> candidate-ready` 总装与 Alpha/Beta/Gamma 阻断验证；正式 Prod apply 不由 workflow_run 或 push 静默执行，必须由人工 dispatch 绑定可达 main 的精确 Git SHA、显式设置非 dry-run，并通过 production environment approval。
- `candidate-ready` 必须绑定四环境配置包、四环境 App 真实 payload、ContractGraph、真实 Provider readiness 与三层测试；按序接受 Alpha/Beta/Gamma 回执并绑定 rollback readiness 后才成为 `deployable`，Prod 全量验证后才成为 `released`。
- 同一候选制品就绪后，Alpha、Beta、Gamma-local 在隔离运行面并行执行；聚合器仍按 `alpha -> beta -> gamma` 验证回执，任一失败均不得申请 Prod approval。
- Prod 只保留一个 production environment approval 与一个事务 job；checkout、OIDC/registry login、ReleaseEvidenceManifest 验签、治理校验和配置包物化只执行一次，随后由 `stackctl` 依次推进 5%、25%、100%。
- push 与默认 dispatch 均保持 dry-run；dry-run 不提交 hosted ledger，因此只执行 gray-initial 只读校验并明确标记边界，禁止伪造 carry-on/full 回执。
- 发布身份只使用 `fromCandidateDigest -> toCandidateDigest`；镜像 transport tag 和逐服务配置包仅是装配坐标，不得重新成为晋级或恢复身份。
- 600/1800 秒准出以 GitHub workflow `created_at -> candidate/prod completed_at` 的官方日历时长为唯一关键路径；Jobs API 的 DAG 只生成 `machineCriticalPath` 诊断，矩阵长尾与 runner 排队不得由 shell timer 或静态预算替代。
- mainline timing 在渲染后以精确 GHCR OCI digest 发布，再由独立 append-only hosted timing authority 按 candidate digest + workflow run 建索引并执行 bind/query readback；该索引不复用 Prod rollout CAS，AI advisory 与普通 gate 均无写入口，三天 Actions Artifact 仅作诊断副本。
- 任一匹配 job 缺少 GitHub `created_at` 时保留日历与机器路径中仍可证明的事实，但不生成 queue 数值；`CiTimingSummary.missingEvidence` 写入 `githubJobs.createdAt`、状态保持 `historical_incomplete`，随后确定性阻断。
- Deployment 与 Deployment Status 的 `pending/queued/in_progress` 会承载部署、并发或 runner 状态，不能证明 required-reviewer 的请求或批准时刻。approval 分段计时必须消费绑定 repository、workflow run、head SHA 与 `production` environment 的显式 durable `deployment_review` 事件；当前缺少该 hosted 事件事实时必须 `historical_incomplete + GATE_BLOCK`。
- 主链软目标 600 秒、硬门 1800 秒；创建后 1500 秒停止继续晋级，并由 `stackctl` 的确定性回滚闭环恢复上一稳定候选。
- 第一方容器 prevalidate 经 stackctl 独立执行，不能取得正式 rollout、ledger、receipt 或 Provider readiness。
- 本地镜像重用 package 时必须校验来源 image；Caddyfile、服务内部端口与 non-prod control-plane policy 均由 canonical 装配消费，禁止临时 symlink、手工重标记或脚本旁路。
- 关联要求：`REQ-001`
- 影响 Story：[`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)、[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`local-gamma-mirror`](./local-gamma-mirror/spec.md)、[`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、候选摘要冲突、证据缺失或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- `prod-hosted` 的正式灰度 workflow 必须人工 dispatch 并保留 approval；在 Provider、SFU、真实数据、观测、灾备或回滚证据缺失时只允许不可提升 prevalidate，且 post-deploy probe 置信度仍须单独验收。
- 运行装配从各服务 `environments/<env>/deploy`、Ops 同名环境入口和真实 Compose/Kustomize 扫描推导；本地端口保留 `local_env_port_manifest`，prod rollout 保留 `gray_rollout_stages`，服务配置由自治 package 的 provenance 摘要证明。
- 每个 Prod rollout stage 必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`；任一失败写入 GATE_BLOCK/rollback 证据，不得由 workflow 合成成功。
- App 四分片耗时必须读取四个实际 Jobs API 节点并取最大值；任何 shard 缺失时 timing gate 失败，不允许回退到 static/serial 近似值。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。
