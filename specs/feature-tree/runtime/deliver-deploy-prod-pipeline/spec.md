# L2 Business Capability：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。

## 2. 范围与非目标

### In Scope

- main 后单一受控 promotion 主链、OCI 制品归档与不可提升预验证
- prod-hosted ACK single-cluster + modular-monolith-first + 独立 Deployment + 托管数据面
- Strangler split-ready 拆分与契约不变
- gamma-local 与 prod-hosted 工作负载图谱同构

### Out of Scope

- 新增 beta-hosted / prod-gray 等额外环境名
- 多业务容器共享 Pod / sidecar 承载领域职责 / 集群内自建数据库 StatefulSet 默认

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：**分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：按 alpha、beta、gamma、prod 的准入顺序发布同一制品，任一波次失败即停止晋级。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 deliver deploy prod pipeline 能力 SIT

- `main` 入库后只生成带 digest 的 OCI release artifact。
- 第一方容器预验证由显式 `stackctl deploy --mode prevalidate` 在独立 namespace 执行，不属于正式 rollout。
- 正式 promotion 只能由人工 dispatch 绑定成功的 main Service Pipeline run，按 `alpha-local -> beta-local -> prod-hosted(gray-initial -> carry-on -> full)` 固定顺序执行。gamma 只用于本地左移验证，远端复验由 prod `gray-initial` 承接。
- `stackctl`、workflow、runbook 与环境矩阵口径一致，不再维护第二套自动推进或回滚逻辑。
- `prod initial -> prod checks -> prod full` 之间的健康检查、只读集成探针、SLO gate 与 rollback 可验证；Provider、SFU、真实数据、观测和灾备证据未齐时不得自动启动该链路。

<a id="req-002"></a>
### REQ-002 ACK 集群部署形态（modular-monolith-first + split-ready）SIT

- `prod-hosted` 首发形态由各第一方服务自治 workload、external 实时/媒体 workload 和平台装配共同组成；不存在组合业务 `seed-box`，无 sidecar 承载领域职责。
- 三层正交边界成立：领域服务=逻辑真相源，Deployment=部署单元，单 ACK 集群+共享节点池=物理资源；对外稳定标识是 Service 而非 Deployment。
- 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / ACK root 对同一 topology 解释一致。

<a id="req-003"></a>
### REQ-003 统一验证 profile：`quwoquan_ops/environments/gamma/validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`

- **统一验证 profile**：`quwoquan_ops/environments/gamma/validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`。
- **统一证据归档**：每个 promotion 阶段必须落 `.qwq_output/env/<env>/runs/<run-id>/report.json` 与 `summary.md`；发布输入为 GHCR OCI digest，Actions Artifact 只保留短期失败诊断且不得作为阶段传递。
- 真实远端复验：仓库不定义 `gamma-hosted` 环境；云侧真实集成、nightly 与发布前高置信度回归统一在 prod `gray-initial` rollout stage 完成。
- `03/04/05` 名称与 required-check 语义必须保持稳定。
- `prod` 灰度是 `prod` 语义下的 rollout stage，不得再引入独立环境枚举。
- `alpha-local` 阶段必须完成环境包、启动与 `stackctl health --scope full`，并落证据产物。
- `beta-local` 阶段必须完成 `stackctl up/health/inspect` 与 self-hosted beta 设备矩阵，通过后才能进入 gamma。
- `prod checks` 或 `prod full` 失败时，workflow 必须自动回滚到上一稳定 `image/config` 并恢复 ready 状态。
- 主链耗时摘要必须落关键路径统计，并以 `critical_path_seconds <= 900` 作为硬门禁。

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
- THEN `main` 入库后生成可验证 OCI release artifact，只有显式受控动作才能发起正式 promotion。
- THEN 第一方 prevalidate 不写正式 rollout、ledger 或 receipt。
- THEN 正式 promotion 按 `alpha-local -> beta-local -> prod-hosted(gray-initial -> carry-on -> full)` 执行。gamma 只用于本地左移验证，远端复验由 prod `gray-initial` 承接。
- THEN `stackctl`、workflow、runbook 与环境矩阵口径一致，不再维护第二套自动推进或回滚逻辑。
- THEN `prod initial -> prod checks -> prod full` 之间的健康检查、只读集成探针、SLO gate 与 auto rollback 可验证。

<a id="sit-002"></a>
### SIT-002 ACK 集群部署形态（modular-monolith-first + split-ready）SIT

- GIVEN 执行“ACK 集群部署形态（modular monolith first + split ready）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“ACK 集群部署形态（modular monolith first + split ready）”对应动作。
- THEN `prod-hosted` 从服务自治部署入口扫描装配第一方 workload，实时/媒体 external workload 独立归 Ops，且不存在组合业务 `seed-box` 或承载领域职责的 sidecar。
- THEN 三层正交边界成立：领域服务=逻辑真相源，Deployment=部署单元，单 ACK 集群+共享节点池=物理资源；对外稳定标识是 Service 而非 Deployment。
- THEN 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- THEN Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- THEN `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / ACK root 对同一 topology 解释一致。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 deliver deploy prod pipeline 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：`main` 入库后由单一 promotion workflow 执行；gamma 只用于本地左移验证，远端复验由 prod `gray-initial` 承接。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 ACK 集群部署形态（modular-monolith-first + split-ready）SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：`prod-hosted` 的每个第一方 workload 都有唯一服务 owner，可独立构建、验证、发布和回滚，且无组合业务 `seed-box`。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效
