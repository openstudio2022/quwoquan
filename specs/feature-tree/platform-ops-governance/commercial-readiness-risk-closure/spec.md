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

- 所有 governed workload 必须以 service/environment/instance 绑定的机器主体 ACK
  当前 `CandidateMaterialManifest` 所引用的配置物料、configVersion 与 effectiveHash；发布编排只接受全实例的新鲜零
  drift 收敛，不得把 liveness 当作配置已生效。
- appVersion/userId 是当前唯一可用的灰度维度；province/carrier 只有在可信边缘
  attestation 已部署并有 hosted UAT 后才能启用，客户端自报头一律不得参与分流。
- Portal 数据源对账必须有直接 UAT 证据。

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

<a id="req-009"></a>
### REQ-009 正式生产发布只接受工厂物料事实链

- RC artifact factory 以 reviewed main 可达源码只构建一次并发布不可变 OCI exact bytes；`CandidateMaterialManifest` 只能从该 factory 输出封存 source commit、build number、OCI/config/App/Web/ContractGraph、SBOM、provenance 与 signing digest，不得由部署期重新打包或重建。
- `QualificationFact` 必须 exact-byte 引用同一 `CandidateMaterialManifest`，并绑定最终签名包、真实 Provider、UAT、供应链与 Android/iOS 物理设备资格；qualified RC 被选中后，stable tag 复用同一 source commit、build number 与 factory OCI digest 闭包，不得再次构建或改写物料。
- Prod 唯一入口为 stable tag 对应的 `ReleaseTagAdmissionFact`，经 durable production approval 形成 `ProdActivationAdmissionFact` 后，才可在同一事务依次推进 `canary -> 5 -> 20 -> 50 -> 100`；全部阶段 exact 绑定同一 `CandidateMaterialManifest`/factory digest 闭包，终态写 `ProdReleasedFact`，随后 soak 只读该事实及其阶段前驱。
- Actions Artifact 只允许保存短期诊断，不承担正式阶段传递；正式后继事实必须按 canonical bytes digest 回读前驱，禁止占位文件、mutable tag、`latest`、部署期重生、并行 REM 状态机或从 workflow success 推导发布资格。
- prod-hosted 第一方容器预验证不属于上述正式事实链。若迁移尚未完成，只允许受限 legacy `non-promotable snapshot` reader 消费历史物料做只读 history/rehearsal；不得调用公开 REM writer，不得写 ledger、receipt、admission、qualification、tag、stage 或 `ProdReleasedFact`，其遗留缺口继续由现有 `OPEN-010` 跟踪。
- 受限单机可把声明允许的旧 `Created/Exited` 容器和未使用镜像计入可回收空间，但必须在镜像传输前完成精确回收和二次实测；数据恢复容器与全部 volume 必须保留。隔离数据模式使用重新摘要的不可提升配置投影与独立随机认证材料，不得继承正式 credentials；Provider 绑定只能返回 unavailable，禁止切到 fixture/Mock。

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
- WHEN reviewed main 可达 RC 进入 artifact factory、资格归约、stable tag 选择与生产 rollout。
- THEN artifact factory 只构建一次并发布不可变 OCI exact bytes，`CandidateMaterialManifest` 完整绑定 source commit、build number、OCI/config/App/Web/ContractGraph、SBOM、provenance 与 signing digest。
- THEN `QualificationFact`、stable `ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact`、五个 stage facts 与 `ProdReleasedFact` 按 canonical exact-byte predecessor 串联，并始终引用同一 `CandidateMaterialManifest`/factory digest 闭包；部署 job 与后四阶段 builder invocation 为零。
- THEN Actions Artifact 无容量时仍 fail-closed 地消费不可变 OCI/hosted facts，不允许部署 job 重建任何服务组件、App/Web payload、Provider、测试或配置物料。
- THEN 仓库内公开 REM writer、正式 caller 与其 static gate 已全部删除；任何 legacy generic validate API 均已重命名为显式 history/rehearsal-only、`non-promotable snapshot` reader，且无法产生正式 qualification、admission、ledger、receipt、stage 或 released 事实。

<a id="sit-004"></a>
### SIT-004 灰度发布串行、真实 SLO 回读并可回滚

- GIVEN stable `ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 与上一稳定 `ProdReleasedFact` 的 exact digest 已验证。
- GIVEN 全局 lock 和 CAS release ledger 可用。
- WHEN 执行 canary、5、20、50、100 或自动回滚。
- THEN 并发发布被拒绝，stage 只能按 CAS 顺序推进。
- THEN SLO 只从 Prometheus 读取且满足最小样本/窗口。
- THEN 超阈值自动回滚并生成不可变 receipt。
- THEN stage fact 在托管 service-plane 内以 generation CAS 原子提交，绑定 `ProdActivationAdmissionFact`、同一 `CandidateMaterialManifest`/factory digest 闭包、RTC image、Provider binding config、ContractGraph、adapter、post-check 与 last-good `ProdReleasedFact`；CI 必须按 fact identity 从 hosted authority 回读并重算 digest。

<a id="sit-005"></a>
### SIT-005 观测、灾备和容量闭环

- GIVEN Prometheus、Alertmanager、OTel、exporter、备份目标和异地副本配置真实可用。
- WHEN 触发服务/基础设施告警或执行 PostgreSQL/Mongo/Elasticsearch 恢复演练。
- THEN 告警完成 firing -> notify -> ack -> resolved。
- THEN 备份按计划生成、校验并恢复到隔离目标，RPO/RTO/容量/成本水位有机器证据。

<a id="sit-006"></a>
### SIT-006 配置 ACK、可信灰度维度与真实 Portal 数据

- GIVEN 全部 governed workloads 使用同一 ConfigSnapshot/ACK 契约。
- GIVEN 每个自治服务 package 仅保留 config/config.yaml，部署时平铺为 config-root/<service>.yaml；服务 loader 与 Platform ConfigSnapshot 读取同一工件。
- GIVEN province/carrier 尚未取得可信边缘 attestation 时，IaC 策略显式禁用这两个维度。
- WHEN 发布高版本并按 appVersion/userId 分流。
- THEN 所有实例 ACK 收敛，drift 为零。
- THEN 每份 ACK 与 service/environment/instance、`CandidateMaterialManifest` 中的配置物料 digest、configVersion、
  desired/effective hash 绑定；过期、disk fallback、缺实例或候选不一致时 hosted rollout
  必须停在 config-convergence readiness。
- THEN 服务有效配置缺失、摘要不匹配或无法解析时 beta/gamma/prod 不能启动；不得回退旧分层路径、空配置或第二套默认配置。
- THEN 客户端伪造 province/carrier 不命中；只有可信边缘上下文与 hosted UAT 同时到位后才可启用。
- THEN 未知 rollout stage 被拒绝，不能回退全局 dimensions 或静默退化为稳定流量。
- THEN Portal 页面只展示真实控制面、Elasticsearch、Prometheus 或业务投影数据。

<a id="sit-007"></a>
### SIT-007 验收追踪和开放事项零漂移

- GIVEN 目录原生 feature-tree、节点 OPEN 与磁盘测试文件已加载。
- WHEN 运行 feature-tree、`spec_ref`、single-track、全仓编译和 stackctl release gate。
- THEN 已支持验收均有真实测试或可执行门直接追踪，未支持验收均由同节点 OPEN 明确完成判定。
- THEN 本能力范围不存在未关闭的 `block` OPEN；外部前置条件缺失则 release 保持 GATE_BLOCK。

<a id="sit-008"></a>
### SIT-008 不可提升的 prod-hosted 第一方容器预验证

- GIVEN reviewed main 的历史物料可由受限 legacy `non-promotable snapshot` reader 读取，且隔离 SSH key 与受控主机可用。
- WHEN prevalidation 在唯一 prevalidate namespace 执行 first-party history/rehearsal scope。
- THEN host 资源/端口、隔离空数据、integration image-only、service/edge systemd 和容器 digest 均可机读复验，报告只标记 `non-promotable` 并且不授予任何正式生产资格。
- THEN 受限单机的当前可用空间与可回收空间分别报告；只可删除声明匹配且未运行的旧容器、清理未使用镜像，禁止删除 volume，并在任何镜像传输前复验回收后的实际空间。
- THEN 容器进程存活与 Provider readiness 分开判定；Elasticsearch 等被排除能力可使对应服务 readiness 保持阻断，但不得伪装为容器未部署或正式健康。
- THEN reader 与报告均为 `non-promotable`，零 ledger、零 receipt、零 qualification、零 admission、零 tag/stage/`ProdReleasedFact` 写入；正式发布仍为 `GATE_BLOCK`。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 商业化能力上线前必须补充专项条款并通过 legal-static 发布门禁

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：商业化能力上线前必须补充专项条款并通过 legal-static 发布门禁
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-002"></a>
### OPEN-002 正式 Portal IdP/RBAC 绑定与双账号登录回执未取得

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓内已实现 OIDC Authorization Code + PKCE、RS256/JWKS/issuer/audience/MFA
  校验、generated permission scope 与伪造身份头清除，但尚未绑定正式企业 IdP，也没有两个
  真实 operator principal 完成菜单/API 权限分离和危险动作双签的发布回执。
- 完成判定：`SIT-002` 的可观察验收在正式 IdP 上通过——正式 IdP issuer/audience/JWKS 与 Portal client 配置由仓外受控注入；IdP group/role
  到 canonical permission scope 的映射经安全审批；两个不同 MFA principal 分别完成允许、拒绝、
  伪造 `X-Actor`/`X-User-Id` 失败及同 digest 双签，API audit/outbox/receipt 与 Portal 展示一致。

<a id="open-003"></a>
### OPEN-003 mutation 与审批/审计非原子，单人自批可执行

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：mutation 与审批/审计非原子，单人自批可执行
- 完成判定：`SIT-002` 的可观察验收通过，双人双签后状态、workflow、audit、outbox 与 receipt 原子提交，单人自批被拒绝。

<a id="open-004"></a>
### OPEN-004 发布 SLO Prometheus 读回已收口，缺真实发布窗口验收

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：调用方数字旁路已全部关闭——deploy 主链按
  `slo_thresholds.yaml` 的窗口/最小样本从 Prometheus 读回
  （errorRate/p95/redis/推荐业务指标），样本不足 pause、读回失败
  rollback；`stackctl verify --kind config-slo` 与 `make config-slo-gate`
  手工入口改为强制 `--prometheus-url` 并拒绝人工 SLO 数字
  （local_contract 已锁定拒绝/pause/透传语义）；CI workflow 的
  caller-supplied SLO token 由 `verify_prod_rollout_stackctl_contract.py`
  禁用。剩余缺口是真实发布窗口的可观察验收。
- 完成判定：`SIT-004` 的可观察验收在真实 canary 发布中通过——SLO 读回
  样本满足最小样本与窗口，超阈值自动回滚 receipt 落
  `.qwq_output/env/prod/runs/**`。

<a id="open-006"></a>
<a id="open-007"></a>
### OPEN-007 无注册备份恢复演练、RPO/RTO 与容量成本水位

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：没有受控备份、隔离恢复、RPO/RTO、远端加密副本与容量成本水位时，任何生产
  发布都无法证明可恢复，不能以本机 dump 或合成报告替代。
- 完成判定：`SIT-005` 的备份恢复与 RPO/RTO/容量成本机器证据成立——`stackctl verify --env prod --target prod-hosted --profile release` 只能接受摘要、
  KMS key version、远端副本状态、隔离恢复目标、RPO/RTO 和容量成本水位全部有效的新鲜
  receipt；任一缺失、过期、未加密或摘要不一致必须 GATE_BLOCK。真实生产恢复演练需由受控
  data-plane 权限执行并保留 hosted receipt。

<a id="open-008"></a>
### OPEN-008 服务结构化日志没有统一 collector 上云

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：服务结构化日志没有统一 collector 上云
- 完成判定：`SIT-001` 的可观察验收通过，服务结构化日志经统一 collector 上云后在异常条件下仍不丢关键事实。

<a id="open-009"></a>
### OPEN-009 GitHub 分支/环境/runner/Action 安全保护不足

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：GitHub 分支/环境/runner/Action 安全保护不足
- 完成判定：`SIT-003` 的可观察验收通过，CI action 固定 commit SHA、工作流最小权限与 CODEOWNERS 在分支、环境和 runner 上均生效。

<a id="open-010"></a>
### OPEN-010 构建与部署不是同一不可变制品

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式链尚未完全证明 artifact factory 的 OCI exact bytes 经 `CandidateMaterialManifest -> QualificationFact -> stable ReleaseTagAdmissionFact -> ProdActivationAdmissionFact -> stage facts -> ProdReleasedFact -> soak` 原子单轨复用；现存 REM writer/formal caller/static gate 或可提升的 generic validate API 会形成第二 authority。
- 完成判定：`SIT-003` 的可观察验收通过——canary/5/20/50/100 与 soak exact 绑定同一 `CandidateMaterialManifest`/factory digest 闭包，部署不重建制品；仓库内 public REM writer、formal caller、static gate 全部删除；legacy generic validate API 已重命名且只允许 history/rehearsal 的 `non-promotable snapshot` 读取，不能写任何 ledger、receipt、qualification、admission、tag、stage 或 released 事实。

<a id="open-011"></a>
### OPEN-011 缺少获批 Prod 发布与真实灰度回滚回执

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库已将本地 release-state 降为缓存，并由 hosted service-plane CAS/不可变 receipt 裁决；仍缺受控 Prod SSH、发布审批与真实 gray traffic/rollback 执行，当前不能生成 last-good 或 rollback 运行回执。
- 完成判定：`SIT-004` 的可观察验收在获批 Prod 发布上通过，真实 gray traffic 与回滚产生不可变 receipt。

<a id="open-012"></a>
### OPEN-012 prod 渲染配置路径/证书/Secret 漂移

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：prod 渲染配置路径/证书/Secret 漂移
- 完成判定：相关缺口消失，`SIT-006` 的可观察验收在 prod 渲染配置路径、证书与 Secret 上通过——实例 ACK 零 drift，有效配置缺失或摘要不匹配时不得启动，也不回退旧分层路径。

<a id="open-013"></a>
<a id="open-014"></a>
### OPEN-014 配置中心（platform-ops-service）生产链路收口

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：配置中心（platform-ops-service）生产链路收口
- 完成判定：相关缺口消失，`SIT-006` 的可观察验收在 platform-ops-service 生产链路上通过——全部 governed workload 共用同一 ConfigSnapshot/ACK 契约并收敛到零 drift，Portal 只展示真实控制面数据。

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
- 影响或价值：仍须在获批 Prod 环境执行 canary→5→20→50→100、阈值回滚与 rollback failure 演练并为每阶段保留 hosted receipt；本地合同已覆盖 hosted receipt CAS、摘要回读和候选绑定。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-019"></a>
### OPEN-019 观测、灾备和容量闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：生产演练 report 与 Portal 证据可追溯。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-020"></a>
### OPEN-020 可信 province/carrier 边缘证明与 hosted UAT 未取得

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：机器 ACK、候选摘要收敛门和真实 Portal ACK 数据均已在仓内收口；客户端自报
  province/carrier 已被 render 与 policy gate 拒绝。当前仍没有外部受控边缘提供的可信
  地域/运营商证明，也没有对应 hosted UAT，因此这两个维度绝不能启用。
- 完成判定：受审批的边缘服务以不可伪造的 server-side attestation 传入 region/carrier；
  该信任链、边缘到服务的身份边界和 hosted UAT 证明它们命中/不命中均符合 `SIT-006` 的可信灰度维度策略。未取得
  该证据时，`appVersion/userId` 是唯一可用维度，release 保持 `GATE_BLOCK`，不得将“空数组禁用”
  误报为该项完成。

<a id="open-021"></a>
### OPEN-021 验收路径和风险台账零漂移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：全部触达范围门禁绿且无 warn-only/skip/allowlist 逃逸。
- 完成判定：`SIT-007` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-022"></a>
### OPEN-022 self-hosted 设备矩阵的物理前置长期不满足

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`App Env Device Matrix` 在可查的历史运行区间内无一成功，两条失败都不是代码问题。Android 侧报 `device_runner_lease: GATE_BLOCK: no android device is present on this runner`，即那台 self-hosted Mac 上没有连接安卓真机。iOS 侧报 `assistant-matrix-fail-fast/gateway_unreachable`，因为 `pr_light` 档声明不启动完整栈、把 beta 当常驻依赖，而该 runner 上的 beta 栈当前没在跑。于是所有 PR 都带着一个恒红的必需检查，真实的设备回归信号被噪声淹没。
- 完成判定：`SIT-007` 的门禁零逃逸子句满足——设备矩阵在 `pr_light` 档下能稳定产出成功回执，或 profile 与工作流对齐到「无真机/无常驻 beta 时显式不作为必需检查」，两者都不得靠 warn-only 或 allowlist 绕过。
- 依赖：self-hosted Mac 上连接安卓真机、常驻 beta 栈的运维值守。
