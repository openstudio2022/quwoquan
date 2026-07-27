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
- GHCR digest 是成功构建的唯一交付输入；CI 必须关闭自动 Docker build record 上传和未受控的 GHA layer cache，不能以成功 Actions Artifact 或无限增长缓存承担发布传递。
- 主线 Service Pipeline 使用仓库已注册、在线且标签受控的 self-hosted macOS ARM64 runner。
- Go builder 必须以不可变多架构索引在原生 `BUILDPLATFORM` 运行并通过 `TARGETOS/TARGETARCH` 交叉编译；最终 linux/amd64 运行层才使用固定 Action 的 QEMU/Buildx，禁止用 QEMU 执行 Go 工具链，也不得因 GitHub-hosted 计费预算不可用而回退本地临时构建或放弃 attestation。
- Prod 构建基镜像必须使用用途匹配的固定 digest；Recommendation 固定使用官方 Python 3.11 slim-bookworm 多架构索引，避免完整开发镜像放大传输与 ECS 磁盘占用。服务 Dockerfile 必须支持受控 runtime 的包管理器，镜像源签名异常时硬失败，禁止以 `--allow-untrusted` 伪造供应链通过。

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

<a id="req-009"></a>
### REQ-009 第一方容器预验证不得提升生产资格

- prod-hosted 第一方容器预验证只消费 reviewed main 的不可变 Service Pipeline 制品，并在镜像传输前执行主机硬门禁。
- Service Pipeline 将 ReleaseManifest 配置包作为带 digest 的 GHCR OCI 制品交付；Actions Artifact 配额不得成为发布输入传递的单点依赖，也不得通过本地重生清单绕过。
- 受限单机可把声明允许的旧 `Created/Exited` 容器和未使用镜像计入可回收空间，但必须在镜像传输前完成精确回收和二次实测；数据恢复容器与全部 volume 必须保留。
- 预验证与正式 rollout transaction、ledger/receipt 和 Provider readiness 分轨；容器验证通过不能改变 release `GATE_BLOCK`。
- 隔离数据模式使用重新摘要的不可提升配置投影与独立随机认证材料；不得继承正式 credentials 文件。Provider 绑定只能返回 unavailable，禁止切到 fixture/Mock。

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
- GIVEN GitHub-hosted runner 计费预算不可用，但受控 self-hosted macOS ARM64 runner 在线且 Docker daemon 可用。
- WHEN service/app/portal/config 进入 pre-release 与生产 rollout。
- THEN ReleaseManifest 绑定 git commit、OCI/config/portal/SBOM/provenance/signature/test evidence digest。
- THEN gray-initial/carry-on/full 只消费同一 manifest，禁止 latest 与部署时重建。
- THEN ReleaseManifest 配置包以 GHCR OCI digest 交付；Actions Artifact 无容量时仍 fail-closed 地消费同一 OCI 内容，不允许在部署 job 重生 manifest。
- THEN Service Pipeline 在受控 runner 上以原生 ARM64 Go builder 交叉编译 linux/amd64 二进制，QEMU/Buildx 只装配目标运行层，仍生成相同 SBOM/provenance 与 release manifest；runner、多架构 builder 索引或跨架构前置缺失时硬失败。
- THEN Go module cache 在 runner 启动后的 step 通过 `RUNNER_TEMP` 按 job 隔离，不进入 checkout 工作区或 GitHub Actions cache；job-level `env` 不得引用不可用的 `runner` context，后续矩阵 job 不得因另一 job 的只读 module cache 失败。
- THEN Docker 凭据和构建状态按 job 隔离时，必须先保存并硬校验受控 runner 当前 daemon endpoint；隔离 `DOCKER_CONFIG` 不得令客户端回退到未运行的默认 socket。
- THEN Delivery Gate 硬校验 self-hosted runner 的受控 Python 版本并在 `RUNNER_TEMP` 创建隔离 venv，不得运行会尝试写入 `/Users/runner` 或系统 framework 的 Python 安装器。
- THEN Prod 的受控 Alpine runtime 通过签名包索引安装运行依赖；包索引签名不可信时不得使用 `--allow-untrusted` 继续构建。
- THEN Recommendation 只消费固定 digest 的 Python slim runtime；完整 Python 开发镜像或传输不完整的 layer 不得作为发布输入。
- THEN Docker build record 与无界 Buildx GHA layer cache 不进入 Actions 存储；失败诊断仍按短保留期、单次运行范围保留。

<a id="sit-004"></a>
### SIT-004 灰度发布串行、真实 SLO 回读并可回滚

- GIVEN ReleaseManifest 与上一稳定 digest 已验证。
- GIVEN 全局 lock 和 CAS release ledger 可用。
- WHEN 执行 gray-initial、carry-on、full 或自动回滚。
- THEN 并发发布被拒绝，stage 只能按 CAS 顺序推进。
- THEN SLO 只从 Prometheus 读取且满足最小样本/窗口。
- THEN 超阈值自动回滚并生成不可变 receipt。
- THEN release receipt 在托管 service-plane 内以 generation CAS 原子提交，绑定 manifest、RTC image、Provider binding config、ContractGraph、adapter、post-check 与 last-good target；CI 必须按 receipt ID 从 hosted authority 回读并重算 digest。

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

<a id="sit-008"></a>
### SIT-008 不可提升的 prod-hosted 第一方容器预验证

- GIVEN deployable ReleaseManifest、GHCR digest、隔离 SSH key 与受控主机。
- WHEN stackctl 在唯一 prevalidate namespace 执行 first-party scope。
- THEN host 资源/端口、隔离空数据、integration image-only、service/edge systemd 和容器 digest 均可机读复验。
- THEN 受限单机的当前可用空间与可回收空间分别报告；只可删除声明匹配且未运行的旧容器、清理未使用镜像，禁止删除 volume，并在任何镜像传输前复验回收后的实际空间。
- THEN 受控回收与巡检的远端 inline Python 必须兼容当前 prod-hosted 系统 Python 3.6；不得使用只在更新解释器中存在的 subprocess 参数导致镜像传输前误阻断。
- THEN 容器进程存活与 Provider readiness 分开判定；SLS 等被排除能力可使对应服务 readiness 保持阻断，但不得伪装为容器未部署或正式健康。
- THEN 报告分别给出容器部署与正式发布资格；不写 ledger/receipt，正式发布仍为 `GATE_BLOCK`。

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
- 完成判定：正式 IdP issuer/audience/JWKS 与 Portal client 配置由仓外受控注入；IdP group/role
  到 canonical permission scope 的映射经安全审批；两个不同 MFA principal 分别完成允许、拒绝、
  伪造 `X-Actor`/`X-User-Id` 失败及同 digest 双签，API audit/outbox/receipt 与 Portal 展示一致。

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
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：没有受控备份、隔离恢复、RPO/RTO、远端加密副本与容量成本水位时，任何生产
  发布都无法证明可恢复，不能以本机 dump 或合成报告替代。
- 完成判定：`stackctl verify --env prod --target prod-hosted --profile release` 只能接受摘要、
  KMS key version、远端副本状态、隔离恢复目标、RPO/RTO 和容量成本水位全部有效的新鲜
  receipt；任一缺失、过期、未加密或摘要不一致必须 GATE_BLOCK。真实生产恢复演练需由受控
  data-plane 权限执行并保留 hosted receipt。

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
### OPEN-011 缺少获批 Prod 发布与真实灰度回滚回执

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库已将本地 release-state 降为缓存，并由 hosted service-plane CAS/不可变 receipt 裁决；仍缺受控 Prod SSH、发布审批与真实 gray traffic/rollback 执行，当前不能生成 last-good 或 rollback 运行回执。
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
- 影响或价值：仍须在获批 Prod 环境执行 gray-initial→carry-on→full、阈值回滚与 rollback failure 演练并保留 hosted receipt；本地合同已覆盖 hosted receipt CAS、摘要回读和候选绑定。
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
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺全部 governed workload 的 authenticated ACK 与可信 edge attestation；ACK 未绑定机器身份或未覆盖全部实例时无法证明配置收敛，province/carrier 信任客户端头还会允许伪造分流，因此当前仅允许 appVersion/userId。
- 完成判定：`SIT-006` 对应行为满足；所有 governed workload 对本次 release 的
  service/environment/instance/config digest 有新鲜、鉴权 ACK，drift=0；伪造
  province/carrier 不能命中，可信边缘上下文的 hosted UAT 证据有效。

<a id="open-021"></a>
### OPEN-021 验收路径和风险台账零漂移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：全部触达范围门禁绿且无 warn-only/skip/allowlist 逃逸。
- 完成判定：`SIT-007` 对应行为满足且真实测试 `spec_ref` 有效
