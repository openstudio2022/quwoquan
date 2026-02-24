# 配置分层与统一规范（运营配置 vs 运维/系统配置）

本规范用于明确**配置的受众、范围与治理方式**，避免把“运营（业务）”与“运维（平台/SRE）”混用。
适用于：Gateway / Orchestrator / Content / Circle / User / Chat / Assistant / Ops（运营）以及平台模块（可观测性、可靠性、性能与系统配置）。

---

## 1. 三类配置：业务运营 / 系统运维 / 部署基础设施

### 1.1 运营配置（Business Ops Config）

**受众**：运营/内容治理/产品策略团队（也可由研发提供后台工具）
**目的**：改变“业务策略与体验”，不改变系统实现细节。
**典型内容**：
- 实验（A/B）、分桶规则、灰度策略（面向用户/人群）
- 推荐/内容策略参数（阈值、开关、名单）
- 审核/治理规则（黑白名单、敏感词、内容策略）
- 运营活动配置（活动规则、权益/曝光）

**存储/管理**：建议由 `product-ops`（产品运营服务）管理为“业务数据”，具备审计、回滚、灰度发布。
**变更要求**：必须可审计、可回滚、可灰度；变更需记录操作者与生效范围。

### 1.2 运维/系统配置（Platform / Runtime Config）

**受众**：研发/运维/SRE
**目的**：改变“系统运行时行为与稳定性”，不改变业务策略本身。
**典型内容**：
- 连接与依赖：DB/MQ/Redis 连接、超时、重试、熔断、并发限制
- 网关与安全：鉴权开关、限流阈值、WAF/黑白名单（系统层）
- 可观测性：采样率、日志级别、指标开关、trace exporter 配置
- 可靠性与性能：降级开关、缓存 TTL、批处理大小、队列并发/预取参数

**存储/管理**：配置中心（如 Nacos）+ Secrets（凭据）+ 环境变量（启动参数）。
**变更要求**：变更需支持“按环境/按服务”发布，具备回滚与变更审计；高风险配置必须灰度。

### 1.3 基础设施/部署配置（Infra / IaC）

**受众**：平台/运维
**典型内容**：K8s 资源、HPA、网络、LB、证书、存储、权限策略等。
**管理方式**：IaC（Terraform/Helm/云控制台）与 CI/CD；不进入业务配置中心。

---

## 2. 关键边界（必须遵守）

- **运营配置 ≠ 运维配置**：运营配置是业务数据；运维配置是运行时参数。
- **运营配置不得包含 Secret**（token/password/连接串）。
- **运维配置不得按用户维度高基数变化**（避免配置中心与缓存失控）；按用户/人群的变更应走运营配置/实验系统。
- **灰度职责**：
  - 运营灰度：按用户/人群/地域/渠道
  - 运维灰度：按环境/按服务实例/按机房

---

## 3. 统一命名与元数据要求

### 3.1 运营配置命名（建议）

以“业务对象”为核心，便于治理与审计：
`ops.<domain>.<object>.<policy>.<key>`

示例：
- `ops.reco.discovery.rank.weight_click`
- `ops.content.moderation.blocklist.enabled`
- `ops.experiment.feed_layout.v1.enabled`

### 3.2 运维/系统配置命名（建议）

以“服务/运行时能力”为核心：
`sys.<service>.<area>.<key>`

示例：
- `sys.gateway.rate_limit.per_user_rps`
- `sys.orchestrator.downstream.timeout_ms`
- `sys.content.mongo.max_pool_size`
- `sys.assistant.otel.trace_sample_ratio`

### 3.3 每个配置项必须具备的元数据（规范）

无论运营/运维配置，都应具备：
- `owner`（负责团队/人）
- `description`（用途）
- `type`（bool/int/float/string/json）
- `default`（默认值）
- `scope`（global/env/service/tenant）
- `reload`（是否热更新；若热更新，刷新周期与一致性要求）
- `rollout`（灰度方式与回滚策略）

---

## 4. 变更治理（Change Governance）

- **审计**：所有变更必须记录：操作者、时间、生效范围、旧值/新值、关联工单/发布号。
- **回滚**：必须支持一键回滚到上一版本。
- **灰度**：高风险项必须灰度（尤其是：超时/重试、限流阈值、降级开关、采样率）。
- **本地/测试环境**：
  - local/test：文件 + 环境变量（见 `技术选型.md` 的配置抽象）
  - cloud：配置中心（Nacos）

---

## 5. 运维/系统配置范围清单（建议最小集合）

> 下面是“系统与实现层面”的配置边界示例，用于避免被运营配置吞并。

### 5.1 可观测性（Observability）

- `sys.<service>.otel.trace_sample_ratio`
- `sys.<service>.log.level`
- `sys.<service>.metrics.enabled`
- `sys.<service>.exporter.endpoint`

### 5.2 可靠性（Reliability）

- `sys.<service>.downstream.timeout_ms`
- `sys.<service>.downstream.retry.max_attempts`
- `sys.<service>.downstream.circuit_breaker.enabled`
- `sys.<service>.degrade.enabled`（降级总开关）

### 5.3 性能（Performance）

- `sys.<service>.worker.concurrency`
- `sys.<service>.cache.ttl_seconds`
- `sys.<service>.batch.size`
- `sys.<service>.queue.prefetch`

### 5.4 安全与防护（Security / Protection）

- `sys.gateway.rate_limit.per_user_rps`
- `sys.gateway.rate_limit.per_ip_rps`
- `sys.gateway.allowlist.enabled`
- `sys.gateway.blocklist.enabled`

