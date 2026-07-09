# deliver-deploy-prod-pipeline 设计

## 设计动因

当前仓库已经具备多环境基础设施，但 promotion 链是割裂的：

- `alpha-local / beta-local` 主要由本地脚本与 self-hosted 设备矩阵维护。
- 远端 `gamma-hosted` 曾由 PR 轻量 preflight、手动 ECS deploy、nightly full validation 分散维护；现已退役，远端真实集成复验下沉到 prod `gray-initial`，`gamma` 仅保留本地 mirror。
- `prod-hosted` 已有自动灰度 workflow，但仍保留人工 approval，且 post-deploy probe 置信度偏低。

本设计的目标不是新增环境，而是在保持现有混合拓扑的前提下，把 `main` 入库后的自动主链收敛为一条可审计、可回滚、15 分钟内完成 blocking promotion 的流水线。

## 适用场景与约束

- **适用**：`main` 后多环境自动推进、prod 部署（唯一远端目标）、prod 自动灰度与自动回滚。
- **约束**：
  - 继续依赖 `process_domain_mapping`、`environment_topology_manifest`、`local_env_port_manifest`、`gray_rollout_stages` 与 `config_release_*` 脚本。
  - 继续支持 `CLOUD_PROVIDER=aliyun|volcengine|huaweicloud` 的多云 prod overlay。
  - 不引入 `beta-hosted`、`prod-gray`、第二套 gamma mirror 命名或第二套 workflow 逻辑。
- **局限性**：beta 仍依赖 self-hosted macOS runner、Flutter 设备可见性与本地网络环境；这是有意保留的拓扑前提。

## 设计原则

### 1. 单一自动 promotion 链

`main` 后只允许一条权威主链：

```text
repo verify/package
  -> alpha-local stage
  -> beta-local stage
  -> prod gray-initial
  -> prod checks
  -> prod full
```

约束：

- PR 仍由 `03/04/05` 收敛，但 `07` 负责真正的自动 promotion，并在 `gray-initial` 承接真实远端集成复验。
- `09` 保留为 local-gamma nightly full validation，不再与 `07` 竞争“权威主链”角色；远端 gamma 部署已退役。

### 2. stackctl 为唯一命令面

所有 workflow 必须编排以下统一入口，而不是复制环境脚本逻辑：

- `stackctl package/verify`
- `stackctl up/down/status`
- `stackctl health`
- `stackctl inspect`
- `stackctl doctor`
- `stackctl deploy`

对应约束：

- workflow 可以复用 reusable workflow，但 reusable workflow 产出的 probe/evidence 必须能映射回 `stackctl` 同名能力。
- `.qwq_output/runs/<env>/<run-id>/report.json` 与 `summary.md` 是环境证据的单一真相源。

### 3. profile 分层与主链轻重分离

`quwoquan_ops/environments/gamma_validation_suites.json` 统一定义所有 hosted / self-hosted profile：

| Profile | 作用 | 阻断链职责 |
|---|---|---|
| `pr_light` | PR 默认 preflight | 共享 gamma readiness + advisory smoke |
| `manual_full` | 手动完整 gamma 复验 | ECS deploy + api_integration + hosted/high-signal smoke |
| `nightly_full` | 夜间全量验证 | hosted full + Patrol + 全设备矩阵 |
| `release_candidate` | 发布前回归 | 与 nightly_full 同级但更靠近发布 |
| `mainline_auto_prod` | `main` 自动 promotion | beta matrix + prod gray-initial 阻断链（承接旧 gamma-hosted）+ prod initial checks |

设计要求：

- `mainline_auto_prod` 只保留高信号、低时延、可直接证明端云正确性的阻断项。
- full semantic / Patrol / 全量多旅程继续由 `nightly_full` 与 `release_candidate` 承担。

### 4. prod 自动放量必须绑定自动回滚

由于用户已明确选择 full-auto prod，本设计要求：

- `gray_rollout_stages.yaml` 中 `full` 阶段也必须允许自动执行。
- `prod initial` 后必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`。
- 任一 blocking probe 失败时，workflow 必须自动回滚到上一稳定 `image/config`，并把 rollback 结果纳入同一阶段证据。

## 核心编排设计

### 1. alpha / beta 本地阶段

`alpha-local`：

- `stackctl package --env alpha --include-services`
- `stackctl up --target alpha-local`
- `stackctl health --target alpha-local --scope full`

`beta-local`：

- `stackctl package --env beta --include-services`
- `stackctl up --target beta-local`
- `stackctl health --target beta-local --scope full`
- `stackctl inspect --target beta-local --scope all`
- self-hosted 设备矩阵复用 `05. App Env Device Matrix`，但使用 `mainline_auto_prod` profile 的环境默认值与 gate 文案。

### 2. 远端集成复验阶段（prod gray-initial 承接，旧 gamma-hosted 退役）

旧 `gamma-hosted` 远端阶段已退役。真实远端集成复验不再单独成阶段，而是作为 prod `gray-initial` rollout stage 的一部分由 `07` 统一驱动：

- `07` 在 `gray-initial` 通过 `stackctl deploy --target prod-hosted` 完成 deploy + readiness + API contract + assistant/chat-avatar probes。
- `mainline_auto_prod` profile 描述这一组阻断项，`07` 按同一 contract 消费其输出。

`gray-initial` 远端复验输出必须至少包含：

- deploy artifact
- readiness report
- API contract report
- assistant smoke report
- chat avatar probe report
- critical path duration

### 3. prod initial / prod checks / prod full

`prod initial`：

- `stackctl deploy --target prod-hosted --step <initial>`

`prod checks`：

- `stackctl health --target prod-hosted --scope full`
- `stackctl inspect --target prod-hosted --scope all`
- `stackctl doctor --target prod-hosted`
- prod 只读集成探针：
  - assistant protocol smoke
  - chat avatar API probe
  - 必要的 hosted API contract smoke

`prod full`：

- `stackctl deploy --target prod-hosted --step <full>`
- 成功后更新 release-state；失败则回滚到 `from_image/from_config`

### 4. 900 秒关键路径预算

主链预算由 `quwoquan_ops/environments/pr_gate_timing_budgets.json` 扩展承载，新增 mainline 自动 promotion gate。

策略：

- alpha / beta 可尽量并行。
- gamma / prod 必须严格串行。
- 通过 artifact 复用、bundle 复用、self-hosted cache repo、Flutter 依赖缓存、skip upload、镜像预拉取来压缩关键路径。
- `quwoquan_ops/ci/render_ci_timing_summary.py` 继续作为统一耗时摘要渲染器。

## ACK 集群部署形态设计（modular-monolith-first + split-ready）

> 本节冻结 `prod-hosted` 在阿里云 ACK 上的标准部署形态，对标业界云原生最佳实践，避免“多业务容器共享 Pod / sidecar 承载领域职责”等定制反模式。

### 设计对标

- Modular Monolith / “MonolithFirst”：早期边界不确定时单体起步、内部按 bounded context 模块化，是低成本高演进的标准路径。
- 共享集群 bin-packing：用调度器与 autoscaler 复用物理资源，是 K8s 原生降本手段，优于把进程塞进一个 Pod。
- Strangler Fig Pattern：单体到微服务的标准渐进迁移模式，保证拆分可逆、对外无感。
- 12-Factor App：进程无状态、配置注入、日志即事件流，保证“同一镜像既能合并跑也能拆开跑”。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。

### 三层正交边界

| 边界 | 对象 | 含义 |
|---|---|---|
| 逻辑边界 | 领域服务（DDD bounded context） | 第一真相源：路由前缀 `/v1/<domain>/*`、`service.name`、指标/日志/配置段/错误码独立 |
| 部署单元 | Kubernetes Deployment | 最小发布与伸缩单元；对外稳定标识是 Service（DNS/路由），Deployment 可替换 |
| 物理资源 | 单 ACK 集群 + 共享节点池 | `requests/limits` + bin-packing + HPA + cluster-autoscaler + namespace `ResourceQuota` 降本 |

逻辑与部署是“多对一 → 一对一”的演进关系：初期多域共享一个 Deployment（modular monolith），拆分后一域一个 Deployment。

### 平面划分与工作负载形态

- 应用平面：
  - `seed-box`：单一 Deployment，承载 Go Modular Monolith 进程，聚合可聚合的 Go 领域。
  - `recommendation-service`：Python，同集群独立 Deployment，独立伸缩，不做 co-located sidecar、不并入 Go 二进制。
- 实时/媒体平面（从第一天即独立 workload，但共享集群）：
  - `realtime-gateway / rtc-service`：标准 Deployment + HPA + PDB。
  - `livekit-sfu`：首发用 Deployment + HPA + PDB，UDP（7882）经 NodePort/`LoadBalancer` 暴露；若后续需稳定网络标识可演进为 StatefulSet（拆分不变量不变）。
  - `coturn`：`hostNetwork` 固定副本 Deployment（UDP/TCP 3478 + TLS 5349），中继按节点容量手动扩，不配 HPA。
- 数据平面：阿里云托管（ApsaraDB PostgreSQL/Redis + MongoDB），不进集群自建。
- 入口：共享 Ingress/ALB，按 `/v1/<domain>/*` 路由到对应 Service。

部署形态唯一：所有服务一律独立 Deployment（或有状态用 StatefulSet），sidecar 仅限代理/日志/配置 bootstrap 等辅助进程，不承载领域职责。

### 数据面与应用/实时面的对应关系

- 网络：ACK 集群与托管 DB 处于同一 VPC，应用面/实时面通过 VPC 私网 endpoint 访问，安全组/白名单只放行集群节点网段，不走公网。
- 服务发现抽象：集群内用 ExternalName Service（如 `pg.data.svc → ApsaraDB 私网域名`）把托管 DB 暴露成“像集群内 Service”，使 `gamma-local`（本地容器 DB）与 `prod-hosted`（托管 DB）用同一 Service 名/同一 DSN 变量切换，两环境同构、业务代码不改。
- 连接信息：DSN/账号/口令走 K8s Secret（阿里云 RAM/KMS 管理），不硬编码、不打进镜像、不入 git。
- 存储归属（按领域、存储无关）：每域只连归属存储（`content → MongoDB`、`user/circle → PostgreSQL`、会话/计数/限流/presence `→ Redis`，以各域实际归属为准），走 repository 接口，禁止跨域直连他域库表。
- 不变量：Strangler 拆分某域后仍连同一托管 DB、同一归属、同一 ExternalName/DSN 抽象，数据面对应关系是拆分的不变量。

### 数据面弹性形态（成本优先 · 固定小规格存算分离单主，非主备冗余/分库分表）

- 起步形态：每个存储以**固定小规格的单写主节点**起步，不预先做主备冗余、不做传统分库分表。固定规格相较 Serverless 费用恒定可预测、无突发扩容抖动，更易守住成本封顶。
- 弹性方式（存算分离 + 在线变配）：
  - 关系型用 PolarDB PostgreSQL 标准版入门规格（存算分离）：读性能靠按需增减只读节点扩展，容量靠共享存储自动扩，纵向算力靠在线变配，无需分库分表。
  - 缓存用 Tair（Redis）固定 1G 小规格：常驻内存延迟可预测，扩容走在线变配。
  - 文档库用云数据库 MongoDB 单节点实例：单主、去副本冗余，在线扩存储。注意阿里云 MongoDB Serverless（预设容量）已于 2025-12-31 EOS，因此不采用 Serverless 形态。
- 不采用 Serverless 的理由：Serverless 弹性为反应式，突发尖峰存在秒级至分钟级扩容延迟与瞬时抖动（PolarDB 实测 1→32 PCU ≈87s、缩容≈231s、只读节点回收 15–20min），峰值费用随用量线性上涨且需显式封顶；对“有基本常驻流量 + 硬成本封顶”的初期场景，固定小规格更稳更可控。
- 高可用演进：放量前再升只读副本/副本集获得读扩展与故障冗余；这是“成本封顶档 → 最小高可用档”的升级动作，不改领域归属与连接抽象。
- 归档：冷数据按时间分区或转 OSS 冷存储；只有归档库在必要时才做分表，主链路保持单逻辑库。
- 连接稳定性：纵向变配可能引发短暂连接中断，应用侧（Repository/HTTP/驱动层）必须配连接池 + 重试，避免变配窗口请求失败。

### 成本优化（标准 K8s 能力，非定制）

- 合理 `requests/limits` 让调度器 bin-packing，多个 Deployment 落到同一批节点。
- 每个 Deployment 配 HPA（CPU/内存或自定义指标）。
- 集群配 cluster-autoscaler / 弹性节点池，低峰缩容降本。
- namespace + `ResourceQuota`/`LimitRange` 做软隔离。

### Strangler Fig 拆分机制

拆分触发阈值（满足任一）：

- 域级 CPU/内存长期高占用或与其他域明显争用。
- 域级请求量/延迟 SLO 需要独立伸缩曲线。
- 域级发布频率显著高于其他域（独立发布窗口）。
- 域级故障需要独立故障域隔离。
- 域级安全/合规需要独立边界。

拆分步骤：

1. 新建独立 Deployment / HPA / PDB / Service，保持原域 Service DNS 名与 `/v1/<domain>/*` 路由不变。
2. 把 Ingress/gateway upstream 或 Service selector 切到新 Deployment。
3. 从 `seed-box` 发布单元移除该域模块，rollout/rollback 按域独立。

回滚：从独立包回退到 `seed-box` 内模块；App 端无需改环境注入。

拆分不变量：域级 API / route / Service DNS 名 / 端侧 runtime 注入 / 数据面归属保持不变。

### 反模式禁止（明确写入门禁意图）

- 一个 Pod 塞多个业务容器当常态。
- 用 sidecar 承载领域服务职责。
- 把不同技术栈合并成一个超级二进制。
- 把数据库做成集群内自建 StatefulSet 当默认。
- 业务代码硬编码 DB 连接串，或跨域直连他域库表。
- 为“统一”而新增第二套环境名 / 路由真相源。

### 与现有 promotion 链 / 多云 overlay 的关系

- 本形态不改 `alpha-local / beta-local / prod-hosted` 主链抽象（`gamma` 仅本地），也不新增环境名。
- 复用 `quwoquan_ops/environments/cloud-providers/aliyun/`、`quwoquan_ops/environments/kustomization/aliyun-prod/` 与 `CLOUD_PROVIDER` 切换参数。
- `stackctl` 仍是唯一命令面；prod rollout 仍走 `gray-initial / carry-on / full` stage，拆分后按域独立 rollout。

## 多云与 overlay 设计

多云 prod overlay 方案保持不变，继续使用：

- `quwoquan_ops/environments/cloud-providers/{aliyun|volcengine|huaweicloud}/`
- `quwoquan_ops/environments/kustomization/{cloud}-{env}/`
- `CLOUD_PROVIDER` 作为 workflow / CLI 的统一切换参数

本次变更只调整自动推进链与回滚闭环，不重写多云 overlay 结构。

## 风险与防线

### 1. self-hosted runner 是 beta 阶段硬依赖

风险：

- 设备不可见、Xcode/adb 漂移、runner 缓存损坏会直接阻断 `main` 自动 promotion。

防线：

- 设备发现、artifact 证据、gate hint、失败分类必须可机读。
- `mainline_auto_prod` profile 不得默认要求不存在的平台通过，但已发现的平台必须全部成功。

### 2. prod 自动放量的误放风险

风险：

- 如果 `prod full` 自动推进时只看 `/healthz`，会把低置信度通过当成发布成功。

防线：

- prod checks 必须要求 `health + inspect + doctor + integration probes + slo gate` 全绿。
- rollback 结果必须写回证据与 release-state，不能只停在日志提示。

### 3. 第二套逻辑回归风险

风险：

- workflow 为了追求快速落地，再次在 YAML 里复制 `health`、`probe`、`rollback` 逻辑，导致 `stackctl` 与 workflow 漂移。

防线：

- 新增能力优先沉到 `stackctl`。
- workflow 只保留编排与 artifact 上传，不再维护第二套探针语义。

## 未来演进

- 若后续引入 GitOps，可把 `prod initial/prod full` 的 apply 动作迁移到 Argo CD，但 `stackctl` 与证据 contract 仍保持稳定。
- 若后续新增 hosted beta，只允许通过扩展 topology manifest 与 `stackctl` target，不允许跳过当前 `alpha-local / beta-local / prod-hosted` 主线抽象（`gamma` 仅本地）。
