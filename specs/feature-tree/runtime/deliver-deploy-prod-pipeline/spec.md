# L2 Business Capability：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。

## 2. 范围与非目标

### In Scope

- `dev1.0 -> main` 单一受控 promotion 主链、`dev1.0` 直接集成、OCI `ReleaseEvidenceManifest` 归档与不可提升预验证
- prod-hosted ssh-hosted + rootless Podman 单一执行面，modular-monolith-first 工作负载图谱，托管数据面
- 同一 `prod-hosted` 内 `cluster member × deployment instance × replica` 可重复部署与聚合 CAS
- Strangler split-ready 拆分与契约不变
- gamma-local 与 prod-hosted 工作负载图谱同构

### Out of Scope

- 新增 beta-hosted / prod-gray 等额外环境名
- 恢复 Kubernetes / ACK / `PROD_KUBECONFIG` / `kubectl` 作为第二发布执行面
- 多业务容器共享 Pod / sidecar 承载领域职责 / 集群内自建数据库 StatefulSet 默认

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；为所有 Journey 提供同一候选的受控集成、发布、环境验证、灰度与回滚证据。
- 本能力接收已授权的精确 Git SHA 与 immutable candidate，输出直属 Story 组合的可观察结果；失败时保留已确认事实并返回可恢复的 canonical failure。

## 4. Story



- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：仓库只保留 `dev1.0` 与 `main`；`dev1.0` 是唯一集成主干并接受日常直接开发，`main` 是唯一发布主干且只接受 promotion PR。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：同一 source release train 预先封存四份环境专属 artifact，按 alpha、beta、gamma、prod 的准入顺序验证，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 deliver deploy prod pipeline 能力 SIT

- 合法 `dev1.0 -> main` promotion 入库后自动启动候选 DAG，生成带 canonical candidate digest 的 OCI `ReleaseEvidenceManifest` 并完成 Alpha/Beta/Gamma 阻断验证；`dev1.0` push 只生成集成证据，`main` push 不得静默执行正式 Prod apply。
- 第一方容器预验证由显式 `stackctl deploy --mode prevalidate` 在独立 namespace 执行，不属于正式 rollout。
- 正式 Prod apply 只能由人工 dispatch 绑定可达 main 的精确 Git SHA、显式关闭 dry-run 并通过 production environment approval；同一候选摘要进入 `alpha-local / beta-local / gamma-local` 隔离 fanout，准入聚合严格按 `alpha -> beta -> gamma` 判定，全部通过后才能进入 `prod-hosted(canary -> 5 -> 20 -> 50 -> 100)`。
- `stackctl`、workflow、runbook 与环境矩阵口径一致，不再维护第二套自动推进或回滚逻辑。
- `canary -> 5 -> 20 -> 50 -> 100` 各阶段的健康检查、只读集成探针、SLO gate 与 rollback 可验证；Provider、SFU、真实数据、观测和灾备证据未齐时不得启动正式 apply。

<a id="req-002"></a>
### REQ-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- `prod-hosted` 唯一执行后端是 `ssh-hosted` + 平面隔离 Linux 账号 + rootless Podman/compose/user systemd；禁止恢复 K8s/ACK/`kubectl`/`PROD_KUBECONFIG` 第二执行面。
- 首发形态由各第一方服务自治 workload、external 实时/媒体 workload 和平台装配共同组成；不存在组合业务 `seed-box`，无 sidecar 承载领域职责。
- 三层正交边界成立：领域服务是逻辑真相源，compose project / systemd unit 是部署单元，`cluster member`（SSH 主机）是物理执行面。
- `prevalidate` / `gray` / `prod` 是同一 hosted 目标内的 deployment instance，不是环境枚举。
- 拓扑真相源为 `quwoquan_ops/environments/prod/access-isolation.yaml` 的 `management.hosts` + `deploymentInstances.*.replicas`；单 member / 单 replica 是默认兼容形态，扩容只追加 host 与 co-located replica placement。
- 正式 rollout 必须对每个 `hostId × plane × replicaId` 产出独立 runtime receipt，并由 service-plane hosted ledger 做聚合 CAS；任一成员缺失、失败或 digest 漂移不得推进 stage / 写入 `full` 成功事实。
- 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

<a id="req-003"></a>
### REQ-003 统一验证 profile：`quwoquan_ops/environments/gamma/validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`

- **统一验证 profile**：`quwoquan_ops/environments/gamma/validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`。
- `pr_light` 不要求 active content release 或视频 canary，只执行 content-free `assistant + environment-smoke` 双平台基线；`manual_full / nightly_full / release_candidate` 必须继续执行绑定 exact immutable release 与视频 canary 的 `app-core-readback`，不得用 PR-light 结果替代内容体验验收。
- `nightly_full` 只对 `gamma-local` 的同一 released nonprod candidate 执行 Simulator/Emulator 诊断；不得轮转 Alpha/Beta/Gamma 或把 nightly 诊断提升为正式三环境 Green/Prod 回执。
- **统一证据归档**：每个 promotion 阶段必须落 `.qwq_output/env/<env>/runs/<run-id>/report.json` 与 `summary.md`；发布输入为 GHCR OCI `ReleaseEvidenceManifest` 的 candidate digest，Actions Artifact 只保留短期失败诊断且不得作为阶段传递。
- **定时与 Provider 单引用消费**：Nightly schedule 与 Provider producer 只能接收或经
  `RELEASED_RELEASE_EVIDENCE_REF` 发现一个 exact immutable `ReleaseEvidenceManifest`
  OCI digest ref；消费端必须验证 status、完整文件闭包、BuildKit SBOM/provenance 和
  GitHub OIDC signer，再从 manifest 导出 candidate、artifact、source/producer、
  pilot/rollback、lifecycle/Green Matrix。禁止 `NIGHTLY_*` / `PROVIDER_*` 字段回填、
  mutable tag 与调用方重复声明派生身份。
- 仓库不定义 `gamma-hosted` 环境；`gamma-local` 的 release-fast 验证是正式主链阻断阶段，云侧真实复验仍由 prod `canary` rollout stage 承接。
- `03/04/05` 名称与 required-check 语义必须保持稳定。
- `03. Delivery Gate` 在 hosted runner 上将 Service core 与完整 packaging 作为同一 topology 前置后的并行 sibling。本地默认 `GATE_SERVICE_PHASE=all` 仍按 core-before → packaging → core-after 完整顺序执行；packaging 的 prepare、逐环境 package、contract、isolation 与 isomorphism 必须输出阶段耗时，并保留首个 typed blocker。
- 原生依赖安装最多两次、每次命令 80 秒且强制终止宽限 10 秒，两次之间仅间隔 10 秒，完整最坏墙钟为 190 秒；耗尽后输出 typed blocker，并要求从当前 attempt 日志修复 runner、镜像源、dpkg 锁或包声明后重跑同一 Job，不得用无界 apt、skip 或 `continue-on-error` 消红。
- `prod` 灰度是 `prod` 语义下的 rollout stage，不得再引入独立环境枚举。
- `alpha-local` 阶段必须完成环境包、启动与 `stackctl health --scope full`，并落证据产物。
- `beta-local` 阶段必须完成 `stackctl up/health/inspect` 与 self-hosted beta 设备矩阵，通过后才能进入 gamma。
- `gamma-local` 阶段必须完成 package、up、full health、release verify 与 inspect，并以同一候选摘要回执阻断 Prod。
- Prod 在一个保留 production approval 的事务 job 内只拉取、验签、解包一次，再执行 `canary -> 5 -> 20 -> 50 -> 100`；任一阶段失败由 `stackctl` 自动回滚到上一稳定候选并恢复 ready 状态。
- dry-run 保持只读：只验证 `canary` 及全部前置门禁，不伪造 `5/20/50/100` ledger 状态，也不得形成正式发布成功事实。
- `CiTimingSummary` 的 600/1800 秒预算只读取 GitHub workflow `created_at -> candidate/prod completed_at` 的官方日历时长；job DAG 仅保留为 `machineCriticalPath` 诊断。App matrix 必须计入四个 shard 的真实最长时长，不允许用静态/串行阶段近似。
- mainline `CiTimingSummary` 必须作为 `ghcr.io/.../ci-timing-summary@sha256:...` 精确 OCI 证据发布，并按 candidate digest 与 workflow run 写入独立、append-only 的 hosted timing authority；写后必须从 hosted 索引查询并逐字段匹配。未初始化、不可达、写入失败或回读漂移均保持 `GATE_BLOCK`，Actions Artifact 只允许作为可丢失诊断副本。
- production approval 的请求、批准与等待时长只能来自绑定 repository、workflow run、head SHA 与 `production` environment 的显式 durable review event。Deployment/Deployment Status 的 `pending/queued/in_progress` 只表示部署或作业状态，不能替代 reviewer decision，也不得与 runner/concurrency queue 混算。
- 任一 job `created_at`、queue、候选、Prod 回执或显式 review event 证据缺失时状态必须为 `historical_incomplete` 并保持 `GATE_BLOCK`，不得用 `started_at` 替代、填零或进入 10/30 分钟 SLO 达成统计。
- 主链软目标为 600 秒、硬门为 1800 秒；从 workflow 创建起达到 1500 秒时停止后续晋级，为自动回滚与 ready 恢复预留 300 秒。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_ops/environments`、`quwoquan_ops/environments/prod/kustomization.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 deliver deploy prod pipeline 能力 SIT

- GIVEN 执行“deliver deploy prod pipeline 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“deliver deploy prod pipeline 能力”对应动作。
- THEN `dev1.0` 直接 push 绑定该精确 SHA 的 `03/04/05` hosted check evidence，但不生成正式 candidate 或 Prod apply；只有具备治理回执的合法 `dev1.0 -> main` promotion 入库后才自动生成可验证 OCI `ReleaseEvidenceManifest` 并执行三个前置环境。
- THEN promotion 成功后系统仅以 compare-and-swap fast-forward 将 `main` backsync 到 `dev1.0`，分叉或 ref 漂移时停止且不得 force；缺 promotion receipt、可信 `main` ancestry 或 durable Prod approval 时在 candidate eligibility、Prod credential 与 canary 前阻断，正式 Prod apply 还必须由精确 SHA 的人工 dispatch 显式关闭 dry-run。
- THEN 第一方 prevalidate 不写正式 rollout、ledger 或 receipt。
- THEN 同一候选在隔离运行面并行执行 Alpha、Beta、Gamma，按 `alpha -> beta -> gamma` 聚合准入后，才执行 `prod-hosted(canary -> 5 -> 20 -> 50 -> 100)`。
- THEN `stackctl`、workflow、runbook 与环境矩阵口径一致，不再维护第二套自动推进或回滚逻辑。
- THEN Prod 五个 rollout stage 在一个受审批事务中复用一次制品物化与治理校验，健康检查、只读集成探针、SLO gate 与 auto rollback 可验证。
- THEN 权威计时包含 runner 排队与矩阵长尾，600 秒软目标、1800 秒硬门和 1500 秒晋级截止均可验证。

<a id="sit-002"></a>
### SIT-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- GIVEN 执行“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”对应动作。
- THEN `prod-hosted` 从服务自治部署入口扫描装配第一方 workload，实时/媒体 external workload 独立归 Ops，且不存在组合业务 `seed-box` 或承载领域职责的 sidecar。
- THEN 执行面仅为 SSH + rootless Podman；`stackctl prod-hosted-plan` / `deploy_to_prod.sh` 按 `host × deployment instance × replica` 迭代，单 host 默认仍可解析。
- THEN 每个 placement 有独立 remote root / compose project / systemd unit / config ACK identity；gray 与 prod placement 共置匹配以便本机 gray router handoff。
- THEN 正式 ledger commit 的 `postChecks` 覆盖全部期望 placement；部分成功不得聚合 CAS。
- THEN 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- THEN Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- THEN `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 deliver deploy prod pipeline 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：`main` 入库后由单一受控 promotion workflow 执行，Gamma-local 作为阻断阶段，远端复验由 prod `canary` 承接。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 prod-hosted 多 member 真实远端放量

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仓内已具备多 host/replica plan、渲染 identity、部署迭代与聚合 CAS 合同；真实第二台 ECS、平面 SSH 凭据与一次完整 `canary → 5 → 20 → 50 → 100` 仍缺。
- 目标：在声明 ≥2 个 `management.hosts` 与匹配 replica placement 的前提下，用真实 SSH 完成多 member 发布、逐 host receipt 与 ledger 聚合 CAS。
- 完成判定：`SIT-002` 对应 live 行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 300 秒止损演练执行证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：三条止损工具链均已存在且不触发重打包——内容 active pointer 回上一 immutable release（`quwoquan_data ship rollback`）、Web current pointer 回上一 artifact（`stackctl deploy --artifact-kind web --expected-current` CAS 切换）、远端配置关闭不兼容能力（`GetAppConfig` kill_switches `immediate`）；尚缺一次带计时 receipt 的真实演练证明三者各自在 300 秒内完成（依赖环境在跑且存在可回切的上一 release/artifact）。
- 目标：在 `gamma-local` 对三条止损路径各执行一次演练，产出含开始/结束时间戳与恢复验证的机器 receipt，全程无打包/编译步骤。
- 完成判定：`SIT-001` 的 auto rollback 可验证子句满足，且演练 receipt 证明三条路径耗时 ≤300 秒并有真实 `spec_ref` 绑定
