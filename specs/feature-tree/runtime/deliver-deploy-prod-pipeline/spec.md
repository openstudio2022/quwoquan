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



- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：仓库只保留 `dev1.0`、`main` 与六条声明的长期 lane；日常开发只经 `lane/* -> dev1.0` PR 合入唯一集成主干，`main` 是唯一发布主干且只接受 promotion PR。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：同一 source release train 预先封存 nonprod/prod 组件与四环境配置 composition，按 alpha、beta、gamma、prod 的准入顺序验证，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 deliver deploy prod pipeline 能力 SIT

- 合法 `dev1.0 -> main` promotion 入库后自动启动候选 DAG，生成带 canonical candidate digest 的 OCI `ReleaseEvidenceManifest` 并完成 Alpha/Beta/Gamma 阻断验证；`dev1.0` push 只生成集成证据，`main` push 不得静默执行正式 Prod apply。
- 第一方容器预验证由显式 `stackctl deploy --mode prevalidate` 在独立 namespace 执行，不属于正式 rollout。
- 正式 Prod apply 只能由人工 dispatch 绑定可达 main 的精确 Git SHA、显式关闭 dry-run 并通过 production environment approval；`workflow_dispatch dry_run=false` 必须先运行轻量 `formal_prod_authority_preflight`，并在任何 Service/App/Delivery/candidate、Alpha/Beta/Gamma/preprod 重型 job 前从 Hosted protection/ruleset authority 得出权威结论。当前该 authority 尚未接入，因此必须立即以 `OPS.BRANCH.AUTHORITY_UNAVAILABLE: terminal=blocked` 和稳定 `recovery=restore_git_authority_then_retry` fail closed；不得伪造 authority，也不得关闭相关 OPEN。`dry_run=true` 与非 dispatch 运行必须返回 typed `applicability=not_applicable / decision=pass` 并继续验证链；`prod_rollout` 在任何 mutation 前仍须保留独立防御性 authority 复核。通过 authority 后，同一候选摘要进入 `alpha-local / beta-local / gamma-local` 隔离 fanout，准入聚合严格按 `alpha -> beta -> gamma` 判定，全部通过后才能进入 `prod-hosted(canary -> 5 -> 20 -> 50 -> 100)`。
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
- 同一 lane 或 `dev1.0` source SHA 的候选级 App `static/tests/serial/coverage` 证据只由对应 source 分支的 push lane 执行一次。push 的 App 影响面按当前 source 分支的 exact push 区间派生，lane 首推按 `merge-base(origin/dev1.0, HEAD) -> HEAD` 派生，不得只看最后一次 push。该判定只允许 typed `required|not_required` 两态且写入 scope receipt，`not_required` 必须绑定 base/head 与完整 changed-path digest，不能由普通 job skipped 反推。PR 继续独立验证 base SHA 到 head SHA 的区间敏感 gate。App required 时，App L1 必须从 GitHub Actions 只读 authority 精确验签同 workflow、同 repository、`event=push`、`head_branch=<PR source branch>`、同 head SHA 的唯一 push run、该 run 的最高 `run_attempt` 及 7 个 App jobs（static、4 shards、serial、coverage）全部 completed/success。缺失、多个不同 run ID、未完成、失败、取消、skipped、attempt 混用、job 集不闭合或 SHA/branch/workflow 漂移一律 `GATE_BLOCK`，不得本地重跑第二份候选 App 证据或把 skipped 当成功。
- PR 验签使用当前 PR workflow 的官方 `created_at` 推导绝对 `evidenceDeadline=created_at+1500s` 与 `hardDeadline=created_at+1800s`。job 因排队晚启动时不得重开相对计时。缺失/运行中只在 evidence deadline 前轮询，HTTP timeout、退避与 sleep 必须被剩余时间 clamp。到 1500 秒仍未取得完整成功闭包即停止继续等待并阻断，为汇总保留 300 秒。PR 的 candidate-ready 取本地各区间 gate 官方 `completed_at` 与 push evidence 验签 job 官方 `completed_at` 的最大值，日历仍从 PR workflow `created_at` 开始。push App phase duration 只进入 machine 诊断，不得替代 PR 等待时间或借用 push 的更早起点。workflow_call / release 调用不依赖独立 push run，仍在调用 DAG 内执行完整 App 证据。
- GitHub authority reader 必须全分页读取并保持最小 `actions:read`，对 401、普通 403 与不可解析响应 fail closed。429、rate-limit 403、5xx、timeout 与网络暂态按 `Retry-After`/`X-RateLimit-Reset` 有界重试且受绝对 deadline 限制。诊断只记录 reason、request/retry count、最后 HTTP 状态、脱敏 rate-limit、matched run count、run ID/attempt、observed/deadline 与 job-closure digest，不记录 token。唯一 run ID 的 rerun 只接受最高 attempt 的完整成功闭包。失败或取消后由人工对该唯一 run 发起 rerun，再重跑 PR 验签。多个不同 run ID 不任选，必须以新提交形成新 SHA。API 暂态耗尽只重跑 PR 验签，不制造第二份 App 证据。回滚只允许原子 Git revert 本增量，禁止运行时双轨开关。
- Delivery CI/latency 切片统一由版本化 `delivery-impact-plan` artifact 驱动：同一 workflow 只计算一次 changed paths，artifact 必须绑定 `schema_version`、`source_sha`、canonical `changed_paths_digest`、planner identity 与 plan digest；所有 shard/coverage/device 消费前验证，不得各自重新推导。App Device Matrix 的普通 PR 只在 runtime/bootstrap、platform/plugin、permissions/entitlements、device scripts/workflows 或 environment/topology 路径命中时执行，普通 UI/domain Dart 改动产出 typed `not_required`/`skipped`；promotion/release/manual/nightly profile 与显式 `force_device_matrix` 仍强制执行。
- `pr_light` 目标为 120 秒、job 硬边界 180 秒；只保留 changed candidate secret/PII/generated boundary 与 canonical impact plan，不再重复运行 detect/timing 三份 pytest 治理测试。`manual_full/mainline_auto_prod` 的 live `/search` admission 不降级，merge admission full profile 不受该切片影响。
- timing telemetry 对 job 分为 `attempted/runnable/skipped/infra`，预算显式区分 `release_sla` 与 `telemetry_advisory`。`release_sla` 的完整 telemetry 超过 hard budget 投影 `GATE_BLOCK`；`telemetry_advisory` 的缺失或超预算在功能 PASS 时仅投影 `PR_WARN`。功能 job 自身 timeout/失败仍 FAIL，不得用 timing warning 覆盖。当前 Delivery PR 与普通 device PR timing 均为 advisory；`mainline_auto_prod` device profile 使用 7800 秒 release SLA，覆盖 beta stack 1200 秒、双平台最长 5400 秒与聚合 1200 秒的完整 machine path，不宣称 8 分钟。
- canonical coverage 只在对应业务域 impact 时执行；coverage baseline/schema/planner/governance contract 路径触发 App+Service coverage 契约闭包。
- `03. Delivery Gate` 在 hosted runner 上将 Service core 与完整 packaging 作为同一 topology 前置后的并行 sibling。本地默认 `GATE_SERVICE_PHASE=all` 仍按 core-before → packaging → core-after 完整顺序执行；packaging 的 prepare、逐环境 package、contract、isolation 与 isomorphism 必须输出阶段耗时，并保留首个 typed blocker。
- `03. Delivery Gate` 的 data 段由 `GATE_DATA_PHASE` 拆成静态门与契约判据两个 sibling job，后者以四片矩阵承接本域判据全量。片归属由判据文件仓内相对路径的摘要取模决定（`quwoquan_ops/gate/delivery_gate_data_shard.py`），不维护分片清单——清单外的新判据文件会落在所有片之外，每片都判它不属于自己，于是四片全绿而它一次没跑。matrix 片数、传给 gate 的分片总数与权威计时的 require-count 必须同值，否则少跑一片不会被任何判据发现。
- commit gate 的 data 段按影响面选判据，横切实现面（`quwoquan_data/scripts/verify/`、`cli.py`、`content/review/`、`content/templates/`）的影响面就是全域，必须显式登记延后项交给上述四片，不得选一批判据冒充全域覆盖：commit gate 硬顶 15 分钟而本域判据全量约 21 分钟，本地无论怎么选都不构成全域证据。超出选择上限的部分同样进延后项而不是丢弃。
- 原生依赖安装最多两次、每次命令 80 秒且强制终止宽限 10 秒，两次之间仅间隔 10 秒，完整最坏墙钟为 190 秒；耗尽后输出 typed blocker，并要求从当前 attempt 日志修复 runner、镜像源、dpkg 锁或包声明后重跑同一 Job，不得用无界 apt、skip 或 `continue-on-error` 消红。
- `prod` 灰度是 `prod` 语义下的 rollout stage，不得再引入独立环境枚举。
- `alpha-local` 阶段必须完成环境包、启动与 `stackctl health --scope full`，并落证据产物。
- `beta-local` 阶段必须完成 `stackctl up/health/inspect` 与 self-hosted beta 设备矩阵，通过后才能进入 gamma。
- `gamma-local` 阶段必须完成 package、up、full health、release verify 与 inspect，并以同一候选摘要回执阻断 Prod。
- Prod 在一个保留 production approval 的事务 job 内只拉取、验签、解包一次，再执行 `canary -> 5 -> 20 -> 50 -> 100`；任一阶段失败由 `stackctl` 自动回滚到上一稳定候选并恢复 ready 状态。
- dry-run 保持只读：formal Prod authority 前置门返回 typed `applicability=not_applicable / decision=pass`，随后只验证 `canary` 及全部适用前置门禁；不得伪造 `5/20/50/100` ledger 状态，也不得形成正式发布成功事实。
- `CiTimingSummary` 的 600/1800 秒预算只读取 GitHub workflow `created_at -> candidate/prod completed_at` 的官方日历时长。job DAG 仅保留为 `machineCriticalPath` 诊断。App matrix 必须计入 Android nonprod/prod、iOS nonprod/prod 与 Web shared 五个 shard 的真实最长时长，不允许用静态或串行阶段近似。
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
- THEN `dev1.0` 直接 push 绑定该精确 SHA 的 `03/04/05` hosted check evidence，但不生成正式 candidate 或 Prod apply。
- THEN 同 SHA 的候选级 App 四相位只在 push lane 执行一次，promotion PR 的 `03` 在保留 `main -> head` 区间 gate 的同时 fail-closed 验签该唯一 push App job 闭包，且 PR 日历 SLI 包含等待证据的全部时间。
- THEN 只有具备治理回执的合法 `dev1.0 -> main` promotion 入库后才自动生成可验证 OCI `ReleaseEvidenceManifest` 并执行三个前置环境；人工 `workflow_dispatch dry_run=false` 在这些 Service/App/Delivery/Alpha/Beta/Gamma/preprod 重型阶段前先运行 `formal_prod_authority_preflight`，当前 authority 未接入时立即返回 `OPS.BRANCH.AUTHORITY_UNAVAILABLE: terminal=blocked; recovery=restore_git_authority_then_retry`，而 dry-run 返回 typed `not_applicable/pass` 且不被阻断。
- THEN promotion 成功后系统仅以 compare-and-swap fast-forward 将 `main` backsync 到 `dev1.0`，分叉或 ref 漂移时停止且不得 force；缺 promotion receipt、可信 `main` ancestry 或 durable Prod approval 时在 candidate eligibility、Prod credential 与 canary 前阻断，正式 Prod apply 还必须由精确 SHA 的人工 dispatch 显式关闭 dry-run。
- THEN 第一方 prevalidate 不写正式 rollout、ledger 或 receipt。
- THEN 同一候选在隔离运行面并行执行 Alpha、Beta、Gamma，按 `alpha -> beta -> gamma` 聚合准入后，才执行 `prod-hosted(canary -> 5 -> 20 -> 50 -> 100)`；即使前置 authority 已通过，`prod_rollout` 仍在首个 mutation 前防御性复核，不得删除硬门或把 OPEN 标记为关闭。
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

<a id="open-004"></a>
### OPEN-004 正式 Android 身份外部登记同步

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式 Android applicationId 已冻结为 `com.leadwise.quwoquan`（vivo 开放平台已登记）；微信/QQ/支付宝开放平台回调、Firebase/推送、App Links/OAuth、其余市场后台与签名证书登记仍需按新身份同步。任一外部平台存在其他 applicationId 登记时保持 `GATE_BLOCK`，禁止同时发布两个身份。iOS 正式 Bundle ID 仍缺已登记外部事实。
- 目标：完成全部外部平台对 `com.leadwise.quwoquan` + 生产签名证书摘要的登记，并以渠道 readback 证明一致。
- 完成判定：`SIT-001` 下 `stackctl store-channels` 对已启用渠道的身份 readback 与 `app_artifact_manifest.yaml` 一致，且 DEC-004 正式身份条目无冲突登记

<a id="open-005"></a>
### OPEN-005 build-once 构建矩阵原子切换未完成

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前流水线仍按四环境重复编译 App（12 份）与云镜像（4 套），`environment_suffixes` 仍是唯一现行 App 身份派生轨，`candidateId` 摘要仍混入环境专属制品输入；DEC-005/DEC-006 已冻结目标身份但尚缺实现与验收证据。
- 目标：按 DEC-005/DEC-006 完成统一 nonprod 包身份切换、runtime config 外置、组件按 digest 复用与 producer/reader 原子 cutover，删除四环境重复编译路径且不保留双轨。
- 实现约束：Android native runtime package 现由 Gradle 从 `dart-defines` property 抄写生成（iOS plist 由 build phase 同理派生），endpoint define 的移除必须与原生注入通道改造、nonprod/prod flavor 收敛及 pipeline producer 在同一受审增量内原子切换，不得先行单独删除 define 造成注入源断供。注入通道改造时 runtime config package 一并携带 schema 版本、签发时间与 source tree digest，App 启动握手校验 staleness，过期即进入阻断式配置错误页而不是继续裸跑。
- 云侧实现约束：镜像环境分叉的物理来源有三。其一，所有一方 Dockerfile 把 `QWQ_ARTIFACT_ENVIRONMENT`/`QWQ_ARTIFACT_CONFIG_DIGEST` 烤入 `/etc/quwoquan/artifact-identity.json`（`runtime/artifactidentity/identity.go` 启动时用 `APP_ENV` 断言匹配，reader 已支持 `QWQ_ARTIFACT_IDENTITY_FILE` 挂载路径覆盖）。其二，platform-ops 把整棵环境配置树拷进镜像 `/app` 并以 `REPO_ROOT=/app` 消费。其三也是最深的一处：external Provider binding 按环境选择（非生产 provider substitute 与 prod 真实三方互斥），经 `QWQ_PROVIDER_BINDING_MANIFEST_DIGEST` overlay 在编译期固化为 Go 二进制内的 `CompiledBindingFor` 单环境视图，`verify_cloud_environment_artifact_binding.py` 门禁同时强制这三处存在且禁止生产源码做运行时环境选择。
- 云侧信任域裁决（DEC-005 已定）：保留 Provider binding 编译期固化这一防 substitute 进 prod 的最强供应链阻断，云镜像收敛为 `nonprod/prod` 两档而不是四环境同 digest，与 App 档位对称。实施前提：alpha/beta/gamma 的 `externalBindings` 声明先收敛为同一 nonprod 档内容（当前 integration-service 与 product-ops-service 存在个别能力 enabled/not_required 差异）。落地时须同一受审增量内：身份文件与环境配置树改为部署面挂载物料、binding overlay 输入从每环境改为每信任域、反转 `environment_artifact_identity.yaml` 与 `manifest_validation.py` 的"repository 环境绑定 + 跨环境 digest 禁令"为"nonprod 三环境同 owner 必须同 digest、prod 独立"、收敛 `plan_service_release_images.py` 矩阵与 `service_pipeline.yml` 计数 gate，并同步 stackctl 本地环境装配与全部 release local_contract fixture。
- 完成判定：`SIT-001` 下同一候选的 App 构建为 nonprod/prod 两档、Cloud 组件按信任域两档且 alpha/beta/gamma 同 owner 同 digest，App-only change 的 Cloud builder invocation 为 0

<a id="open-006"></a>
### OPEN-006 Vivo 首链真实市场分发闭环

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前分发编排工具链已就位——`stackctl store-channels` 渠道准入门、`stackctl store-distribution` 逐渠道 append-only 分发回执（fan-out 强制同一 candidate 的全部 android 渠道引用同一 release APK digest）、`InstallReceipt` 契约与官网 latest 指针条件更新；仍缺 vivo 开发者凭据在位后的一次真实上传、审核、上架、市场客户端下载安装与首启兼容闭环。静态渠道登记、side-load 或官网安装不得替代市场安装事实。
- 目标：以同一 reviewed Prod APK 完成 vivo 首链：上传与审核回执经 `store-distribution` 登记，上架后从 vivo 市场客户端安装并产出 `channelId=vivo_market` 的 InstallReceipt 与启动 telemetry。其他市场复用同一分发编排与同一 source digest，仅凭据、审核与公开能力按平台独立，不新增渠道专包。
- 依赖：`QWQ_VIVO_DEV_CREDENTIAL_PATH` 凭据文件、vivo 开放平台审核通过、真机市场安装通道。
- 完成判定：`SIT-001` 下 vivo_market 存在 uploaded→published 完整回执链与 verified InstallReceipt，且回执 artifactDigest 与官网 latest 指针引用同一 release APK source digest

<a id="open-003"></a>
### OPEN-003 300 秒止损演练执行证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺一次带计时 receipt 的真实演练验收证据，无法证明三条止损路径各自在 300 秒内完成。三条工具链实现均已存在且不触发重打包：内容 active pointer 回上一 immutable release（`quwoquan_data ship rollback`）、Web current pointer 回上一 artifact（`stackctl deploy --artifact-kind web --expected-current` CAS 切换）、远端配置关闭不兼容能力（`GetAppConfig` kill_switches `immediate`）；演练仍依赖运行中的环境和可回切的上一 release/artifact。
- 目标：在 `gamma-local` 对三条止损路径各执行一次演练，产出含开始/结束时间戳与恢复验证的机器 receipt，全程无打包/编译步骤。
- 完成判定：`SIT-001` 的 auto rollback 可验证子句满足，且演练 receipt 证明三条路径耗时 ≤300 秒并有真实 `spec_ref` 绑定
