# L2 Business Capability：商用就绪风险收口 (`commercial-readiness-risk-closure`)

> 所属领域：[`platform-ops-governance`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。

## 2. 范围与非目标

### In Scope

- 当前阻断级 `OPEN` 清零、三层测试、供应链与 `stackctl release` 证据
- OIDC/RBAC、双签原子 receipt、遥测与日志可靠投递
- Build Once、灰度锁/CAS、SLO 回读、灾备容量与真实数据对账
- 配置 ACK、可信灰度维度与 acceptance 路径诚信

### Out of Scope

- 伪造 IdP、企业法务信息、生产凭据或云厂商恢复结果
- 未经批准执行 prod-hosted 放量、回滚或破坏性恢复

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md)：缺失项逐一有稳定错误与修复指引，发布不能继续。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 遥测与日志在异常条件下不丢关键事实

- 相关 `local_contract` 与 `api_integration` 必须直接证明异常遥测和日志链路不存在静默成功。

<a id="req-002"></a>
### REQ-002 控制面身份和危险动作职责分离

- 匿名、伪造头、同人双签与 digest 漂移必须被拒绝；事务失败与幂等重放必须恢复到唯一可审计终态。

<a id="req-003"></a>
### REQ-003 构建一次与不可变制品

- same-digest、Action pin、SBOM/provenance 和缺制品 fail-closed 必须由可执行门禁直接证明。

<a id="req-004"></a>
### REQ-004 灰度发布串行、真实 SLO 回读并可回滚

- 本地失败注入和 prod-hosted 真实流量/回滚演练均有 report。

<a id="req-005"></a>
### REQ-005 观测、灾备和容量闭环

- 生产演练 report 与 Portal 证据可追溯。
- prod service plane 必须由受版本控制的 rootless Compose 装配 Prometheus、Alertmanager、OTel Collector 与主机/容器/数据面 exporter；镜像必须为外部注入的不可变 digest，通知 URL 与 ingest token 只能通过主机 secret 文件注入。
- 部署必须在流量切换前启动并验证观测栈、Prometheus target 和 Alertmanager readiness；任一依赖缺失都必须 fail closed。

<a id="req-006"></a>
### REQ-006 配置 ACK、可信灰度维度与真实 Portal 数据

- 四维分流、ACK 矩阵和 Portal 数据源对账必须有直接 UAT 证据。

<a id="req-007"></a>
### REQ-007 验收追踪和开放事项零漂移

- 全部触达范围门禁绿且无 warn-only/skip/allowlist 逃逸。

<a id="req-008"></a>
### REQ-008 仓库内可修复的断点必须在本 Story 内实现、测试并关闭

- 仓库内可修复的断点必须在本 Story 内实现、测试并关闭。
- 外部账号权益、真实法务主体信息、IdP 凭据或 prod-hosted 凭据缺失时，必须在最低归属 spec 记录 `external_blocker` OPEN，并阻断受影响准出范围。
- province/carrier 必须来自可信服务端或边缘解析，不信任客户端自报。
- Portal 页面不得以 seed、hardcode 或合成趋势冒充生产数据。
- 测试中的 `spec_ref` 必须指向现存规格与验收锚点。

## 6. 契约与依赖

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml`、`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`、`quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`、`quwoquan_service/contracts/metadata/_control_plane/platform/control_plane.yaml`、`quwoquan_service/contracts/metadata/_control_plane/product/control_plane.yaml`、`quwoquan_ops/policies/branch_policy.yaml`、`.github/workflows/service_pipeline.yml`、`.github/workflows/deploy-prod-auto.yml`、`quwoquan_ops/environments/prod/rollout/stages.yaml`、`quwoquan_ops/policies/config-release/slo_thresholds.yaml`、`quwoquan_ops/observability/monitoring/docker-compose.prod.yml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`、`quwoquan_ops/environments/prod/rollout/routing_policy.yaml`、`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/config_snapshot/operations.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 遥测与日志在异常条件下不丢关键事实

- GIVEN startup、Behavior、RuntimeLogger 与服务日志使用 canonical metadata 契约。
- GIVEN WARN/ERROR、永久 4xx、临时网络/5xx 和进程重启均可注入测试。
- WHEN 发生重放、断网、422、队列拥塞或 exporter 重启。
- THEN startup 以 canonical body digest 幂等，同 proof 不同 body 不会误判重放。
- THEN Behavior 正确处理 gzip、clientEventId、occurredAt 与事务 outbox。
- THEN WARN/ERROR 优先、TTL/退避/DLQ/spool 生效，永久失败不堵塞后续记录。
- THEN ANR/卡顿可查询、可 rollup、可告警。

<a id="sit-002"></a>
### SIT-002 控制面身份和危险动作职责分离

- GIVEN Portal 使用 OIDC Authorization Code + PKCE。
- GIVEN 服务端只信任已验证 principal。
- WHEN operator 读取菜单或提交 premium takedown。
- THEN 菜单与 API 均按 scope fail-closed。
- THEN X-Actor/X-User-Id 等客户端头不能构造 actor。
- THEN 两个不同 principal 对同一 digest 双签后，状态、workflow、audit、outbox 和 receipt 原子提交。
- THEN Portal 不暴露 release apply / rollback mutation；发布唯一执行面保持为受保护 CI/CD + stackctl。

<a id="sit-003"></a>
### SIT-003 构建一次与不可变制品

- GIVEN CI action 固定 commit SHA，工作流最小权限和 CODEOWNERS 已声明。
- WHEN service/app/portal/config 进入 pre-release 与生产 rollout。
- THEN ReleaseManifest 绑定 git commit、OCI/config/portal/SBOM/provenance/signature/test evidence digest。
- THEN gray-initial/carry-on/full 只消费同一 manifest，禁止 latest 与部署时重建。

<a id="sit-004"></a>
### SIT-004 灰度发布串行、真实 SLO 回读并可回滚

- GIVEN ReleaseManifest 与上一稳定 digest 已验证。
- GIVEN 全局 lock 和 CAS release ledger 可用。
- WHEN 执行 gray-initial、carry-on、full 或自动回滚。
- THEN 并发发布被拒绝，stage 只能按 CAS 顺序推进。
- THEN SLO 只从 Prometheus 读取且满足最小样本/窗口。
- THEN 超阈值自动回滚并生成不可变 receipt。

<a id="sit-005"></a>
### SIT-005 观测、灾备和容量闭环

- GIVEN Prometheus、Alertmanager、OTel、exporter、备份目标和异地副本配置真实可用。
- WHEN 触发服务/基础设施告警或执行 PostgreSQL/Mongo/SLS 恢复演练。
- THEN 告警完成 firing -> notify -> ack -> resolved。
- THEN 备份按计划生成、校验并恢复到隔离目标，RPO/RTO/容量/成本水位有机器证据。

<a id="sit-006"></a>
### SIT-006 配置 ACK、可信灰度维度与真实 Portal 数据

- GIVEN 全部 governed workloads 使用同一 ConfigSnapshot/ACK 契约。
- GIVEN 每个自治服务 package 仅保留 config/config.yaml，部署时平铺为 config-root/<service>.yaml；服务 loader 与 Platform ConfigSnapshot 读取同一工件。
- GIVEN 可信边缘可解析 province/carrier。
- WHEN 发布高版本并按 appVersion/userId/province/carrier 分流。
- THEN 所有实例 ACK 收敛，drift 为零。
- THEN 服务有效配置缺失、摘要不匹配或无法解析时 beta/gamma/prod 不能启动；不得回退旧分层路径、空配置或第二套默认配置。
- THEN 客户端伪造 province/carrier 被覆盖，未知维度不命中。
- THEN 未知 rollout stage 被拒绝，不能回退全局 dimensions 或静默退化为稳定流量。
- THEN Portal 页面只展示真实控制面、SLS、Prometheus 或业务投影数据。

<a id="sit-007"></a>
### SIT-007 验收追踪和开放事项零漂移

- GIVEN 目录原生 feature-tree、节点 OPEN 与磁盘测试文件已加载。
- WHEN 运行 feature-tree、`spec_ref`、single-track、全仓编译和 stackctl release gate。
- THEN 已支持验收均有真实测试或可执行门直接追踪，未支持验收均由同节点 OPEN 明确完成判定。
- THEN 本能力范围不存在未关闭的 `block` OPEN；外部前置条件缺失则 release 保持 GATE_BLOCK。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 商业化能力上线前必须补充专项条款并通过 legal-static 发布门禁

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：商业化能力上线前必须补充专项条款并通过 legal-static 发布门禁
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-002"></a>
### OPEN-002 Portal 无 OIDC/RBAC，actor 可由客户端 header 伪造

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`track`
- 影响或价值：Portal 无 OIDC/RBAC，actor 可由客户端 header 伪造
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-003"></a>
### OPEN-003 mutation 与审批/审计非原子，单人自批可执行

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：mutation 与审批/审计非原子，单人自批可执行
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-004"></a>
### OPEN-004 发布 SLO 使用调用方数字而非真实监控读回

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：发布 SLO 使用调用方数字而非真实监控读回
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-006"></a>
### OPEN-006 治理、推荐与运营页仍依赖 seed 或硬编码

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：治理、推荐与运营页仍依赖 seed 或硬编码，无法证明生产数据源和权限边界。
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-007"></a>
### OPEN-007 无注册备份恢复演练、RPO/RTO 与容量成本水位

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：无注册备份恢复演练、RPO/RTO 与容量成本水位
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-008"></a>
### OPEN-008 服务结构化日志没有统一 collector 上云

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：服务结构化日志没有统一 collector 上云
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-009"></a>
### OPEN-009 GitHub 分支/环境/runner/Action 安全保护不足

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：GitHub 分支/环境/runner/Action 安全保护不足
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-010"></a>
### OPEN-010 构建与部署不是同一不可变制品

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：构建与部署不是同一不可变制品
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-011"></a>
### OPEN-011 灰度无真实流量、release-state 分脑且无生产锁

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：灰度无真实流量、release-state 分脑且无生产锁
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-012"></a>
### OPEN-012 prod 渲染配置路径/证书/Secret 漂移

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：prod 渲染配置路径/证书/Secret 漂移
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-013"></a>
### OPEN-013 文档声明 ACK 与真实 SSH-hosted 执行面冲突

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：文档声明 ACK 与真实 SSH-hosted 执行面冲突
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-014"></a>
### OPEN-014 配置中心（platform-ops-service）生产链路收口

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：配置中心（platform-ops-service）生产链路收口
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-015"></a>
### OPEN-015 遥测与日志在异常条件下不丢关键事实

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少异常条件下 local_contract、api_integration 与日志无静默成功的组合证据。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-016"></a>
### OPEN-016 控制面身份和危险动作职责分离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少匿名、伪造头、同人双签、digest 漂移、事务失败与幂等重放的完整负向证据。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-017"></a>
### OPEN-017 构建一次与不可变制品

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少 same-digest、Action pin、SBOM/provenance 和缺制品 fail-closed 的同版本证据。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-018"></a>
### OPEN-018 灰度发布串行、真实 SLO 回读并可回滚

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本地失败注入和 prod-hosted 真实流量/回滚演练均有 report。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-019"></a>
### OPEN-019 观测、灾备和容量闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：生产演练 report 与 Portal 证据可追溯。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-020"></a>
### OPEN-020 配置 ACK、可信灰度维度与真实 Portal 数据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少四维分流、ACK 矩阵与 Portal 真实数据源对账的 UAT 证据。
- 完成判定：`SIT-006` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-021"></a>
### OPEN-021 验收路径和风险台账零漂移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：全部触达范围门禁绿且无 warn-only/skip/allowlist 逃逸。
- 完成判定：`SIT-007` 对应行为满足且真实测试 `spec_ref` 有效
