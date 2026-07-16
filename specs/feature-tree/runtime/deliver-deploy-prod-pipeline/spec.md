# L2 特性：deliver-deploy-prod-pipeline

## 功能说明

沿用当前 `alpha-local / beta-local / prod-hosted` 混合拓扑（`gamma` 仅本地 mirror，已无远端 gamma；远端/hosted 目标只有 `prod-hosted`），把环境打包、启动、健康检查、端云集成验证、灰度发布与证据归档统一收敛到 `stackctl` 与 GitHub Actions。目标是让 `main` 入库后自动完成 `alpha -> beta -> prod` promotion 主链，并在 `prod gray-initial -> prod full` 之间自动执行健康探针、只读集成探针、SLO gate 与 auto rollback。真实远端集成与 curated 媒体路由复验由 prod `gray-initial` rollout stage 承接（旧 `gamma-hosted` 阶段已退役）。

主链分层如下：

- `03. Delivery Gate` 继续负责 PR 前 L1/L2 静态与模块收敛。
- `04. Pre-Release Gate` 继续负责 PR 前 local-gamma 轻量预检，不承担 `main` 后真 promotion。
- `05. App Env Device Matrix` 继续负责 self-hosted 设备矩阵，并新增可供 `main` promotion 复用的 `mainline_auto_prod` profile。
- `07. Deploy To Prod (Auto)` 演进为 `main` 入库后的单一自动 promotion workflow。

## 范围

- **PR 前置收敛**：`03/04/05` 保持 required checks 名称稳定，继续负责进入 `main` 前的质量收敛。
- **main 自动 promotion**：`repo verify/package -> alpha-local -> beta-local -> prod gray-initial -> prod checks -> prod full`（已无 `gamma-hosted` 阶段）。
- **统一验证 profile**：`quwoquan_ops/environments/gamma_validation_suites.json` 统一定义 `pr_light / manual_full / nightly_full / release_candidate / mainline_auto_prod`。
- **统一证据归档**：每个 promotion 阶段必须落 `.qwq_output/env/<env>/runs/<run-id>/report.json` 与 `summary.md`，workflow 同步上传 artifact。
- **15 分钟硬预算**：阻断主链的 `critical_path_seconds <= 900`，重型 Patrol/full semantic/全设备全旅程留在 `nightly_full` 与 `release_candidate`。
- **local-gamma left shift**：仍作为提交前左移预测试拓扑，但不替代 `main` 后自动 promotion。
- **ACK 集群拓扑形态**：`prod-hosted` 采用 single-cluster + modular-monolith-first + 独立 Deployment + 托管数据面 + Strangler split-ready，且 `gamma-local` 与 `prod-hosted` 工作负载图谱同构。

## ACK 集群部署形态与 split-ready（本轮 baseline 冻结）

> 本节冻结 `prod-hosted` 在阿里云 ACK 上的标准部署形态，对齐业界云原生最佳实践（Modular Monolith 起步 + 共享集群 bin-packing + Strangler Fig 渐进拆分），不引入定制结构。

### 三层正交边界

- 逻辑边界 = 领域服务（DDD bounded context）：独立路由前缀 `/v1/<domain>/*`、独立 `service.name`、独立指标/日志/配置段/错误码，是第一真相源。
- 部署单元 = Kubernetes Deployment：最小发布与伸缩单元，初期尽量少、规模后按需增多；对外稳定标识是 Service（DNS 名/路由），不是 Deployment。
- 物理资源 = 单 ACK 集群 + 共享节点池：靠 `requests/limits` + bin-packing + HPA + cluster-autoscaler + namespace `ResourceQuota` 复用资源降本。

### 首发形态（modular-monolith-first）

- 应用平面：`seed-box` 为单一 Deployment 承载 Go Modular Monolith 进程，聚合可聚合的 Go 领域；`recommendation-service`（Python）为同集群独立 Deployment。
- 实时/媒体平面：`realtime-gateway / rtc-service / livekit-sfu / coturn` 从第一天即为同集群独立 workload（Deployment/StatefulSet + hostNetwork/UDP），不并入 Modular Monolith。
- 数据平面：PostgreSQL / Redis / MongoDB 用阿里云托管（同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入 + 安全组白名单），不进集群自建 StatefulSet；采用固定小规格的存算分离弹性单主（单写主节点 + 按需加只读节点扩性能 + 共享存储自动扩容量），不做主备冗余与分库分表，归档才做冷分区。不依赖 Serverless 形态（MongoDB Serverless 已于 2025-12-31 EOS）。
- 部署形态唯一：所有服务一律独立 Deployment，不用 sidecar 承载领域职责。

### split-ready（Strangler Fig）

- 满足拆分触发阈值（域级资源占用 / SLO 伸缩曲线 / 发布频率 / 故障域隔离 / 安全合规）时，把某域从 `seed-box` 抽成独立 Deployment + HPA + PDB + Service。
- 拆分不变量：域级 API / route / Service DNS 名 / 端侧 runtime 注入 / 数据面归属保持不变。

### 环境同构

- `gamma-local`：复用与 `prod-hosted` 同构的工作负载图谱（同 Deployment 拓扑、Service 名、路由前缀、edge/media 分层、数据面 Service 名/DSN 变量），只把 backend 换成本机容器编排 + 本机模拟器/浏览器。`gamma` 仅本地，无远端 gamma。
- 真实远端复验：旧 `gamma-hosted` 阶段已退役，云侧真实集成、nightly 与发布前高置信度回归统一在 prod `gray-initial` rollout stage 完成。

## 适用范围与约束

- **适用**：PR 前 required checks、`main` 后自动 promotion、prod `gray-initial` 远端复验、prod 自动灰度、prod 自动回滚。
- **不适用**：新增 `beta-hosted`、`prod-gray` 等额外环境名或第二套拓扑命名。
- **不适用（部署形态反模式）**：多业务容器共享 Pod 当常态、sidecar 承载领域职责、跨技术栈合并超级二进制、集群内自建数据库 StatefulSet 作为默认、业务代码硬编码 DB 连接或跨域直连他域库表。
- **约束**：
  - `03/04/05` 名称与 required-check 语义必须保持稳定。
  - `stackctl` 是环境自动化唯一入口；workflow 只编排，不复制第二套环境逻辑。
  - `prod` 灰度是 `prod` 语义下的 rollout stage，不得再引入独立环境枚举。
  - `mainline_auto_prod` 只保留高信号阻断链：beta 设备矩阵、gamma readiness/api_integration/high-signal probes、prod 初始灰度后的只读集成探针。
  - 自动升 `prod full` 的前提是 auto rollback、SLO gate、stage evidence 与 release-state 一致性先落地。

## 与父/子节点关系

**父节点**：runtime（L1 能力域）

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **multi-environment-wave-deployment** | 冻结 `alpha-local / beta-local / prod-hosted` 拓扑与主链波次关系（gamma 仅本地） | **优先** |
| **gray-release-to-prod** | `prod initial / prod full`、SLO gate、rollback 与 release-state 一致性 | **优先** |
| **local-gamma-mirror** | 提交前左移预测试，复用 gamma 语义但不进入 `main` 阻断主链 | **并行配套** |
| **multi-environment-instance-isolation** | 本地 alpha/beta 多设备并行与 beta/gamma 单套服务生命周期 | **并行配套** |

## 验收标准概要

- A1：`main` push 触发单一 workflow，按固定顺序执行 `repo verify/package -> alpha-local -> beta-local -> prod gray-initial -> prod checks -> prod full`（无 `gamma-hosted` 阶段）。
- A2：`alpha-local` 阶段必须完成环境包、启动与 `stackctl health --scope full`，并落证据产物。
- A3：`beta-local` 阶段必须完成 `stackctl up/health/inspect` 与 self-hosted beta 设备矩阵，通过后才能进入 gamma。
- A4：旧 `gamma-hosted` 阶段已退役；其 hosted deploy、readiness、api_integration API contract、assistant protocol smoke、chat avatar probe 由 prod `gray-initial` rollout stage 承接，并由 `mainline_auto_prod` 单源描述。
- A5：`prod initial -> prod checks -> prod full` 默认全自动，不再依赖人工 approval。
- A6：`prod checks` 或 `prod full` 失败时，workflow 必须自动回滚到上一稳定 `image/config` 并恢复 ready 状态。
- A7：每个阶段都能输出 `report.json`、`summary.md`、stdout/diagnostics，支持人工排障与 workflow 复用。
- A8：主链耗时摘要必须落关键路径统计，并以 `critical_path_seconds <= 900` 作为硬门禁。
- A9：`prod-hosted` 首发形态为 `seed-box` 单 Deployment + `recommendation`/实时/媒体各自独立 Deployment，无 sidecar 承载领域职责。
- A10：每个 workload 标准 K8s 原语齐全（独立 Deployment/Service/HPA/PDB/probe/resources），且 domain 不双归属。
- A11：Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- A12：`gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构，`stackctl` / workflow / ACK root 对同一 inventory 解释一致。
