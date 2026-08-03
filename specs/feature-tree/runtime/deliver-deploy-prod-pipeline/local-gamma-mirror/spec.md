# L3 Story：本地 Gamma 镜像 (`local-gamma-mirror`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望 gamma-local 同时承担开发与提交前左移验证，以及 main 受控 promotion 的正式阻断回执（gamma 仅本地，无远端 gamma）；真实远端复验由 prod gray-initial rollout stage 承接，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 本地 gamma 语义镜像栈（DB/Redis/核心服务/media/TLS 反代）启停与健康前置检查
- 本地 local_contract->user_acceptance 左移：真实 HTTP API、存储副作用、错误码、RemoteRepository 解码与模拟器/真机 Patrol 核心旅程
- 提交前左移报告与 main 候选 release-fast 回执统一写入 `.qwq_output/env/gamma/runs/<run-id>/report.json` 和 `summary.md`，并指向 `quwoquan_ops/environments/gamma/validation_suites.json`
- main 候选回执绑定同一 candidate digest；缺失、失败或摘要不一致均阻断 Prod
- 与 prod 同构的工作负载图谱解释（同 Service 名、路由前缀、数据面 Service 名/DSN 变量）

### Out of Scope

- 新建托管 Gamma，或替代云侧 K8s/Ingress/Secret/云观测/多云 overlay
- 替代云侧 prod 灰度流量、SLO 卡点、审批与回滚演练
- 新增 local-gamma 环境枚举、APP_ENV 枚举或任何环境 seed manifest
- 在生产包引入 test fixture / seed reset / 本地 mirror URL

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 gamma-local 左移验证与 main 正式阻断回执

- gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- 提交前 gamma-local 通过只形成左移质量事实；main 受控 promotion 必须针对同一候选执行 release-fast，并以 canonical 环境回执作为 Prod 前置阻断门。
- main 候选的 gamma-local 回执缺失、失败或 candidate digest 不一致时必须 `GATE_BLOCK`，不得申请 Prod approval。
- 不新增运行环境枚举或第二套 seed manifest。
- gamma-local 从各服务 `deploy/compose.yaml` 与 Ops external/infra Compose 扫描装配，不维护服务名册；recommendation 各环境统一以 `recommendation-service:8000` 调用。
- edge-media（realtime-gateway/rtc-service/livekit-sfu/coturn）统一在本 compose 以 profile 按需组装；realtime-gateway 实现未就绪以 edge-media-pending 显式占位收敛。
- full 镜像栈使用唯一的 Caddy 路由真相源与各服务声明的内部监听端口；非生产环境不会因生产 operator OIDC 前提阻塞健康检查。
- 以已有 package provenance image 启动时必须先验证本地 image 可用，缺镜像为可诊断的 GATE_BLOCK，禁止通过手工重标记、拉取 localhost tag 或旧 Caddyfile 路径绕开。
- 领域 readback 使用候选绑定的 nonprod acceptance account receipt；账号必须通过正式 OTP 与 `LoginWithPhone` 创建，不得签发无 canonical UserAccount 的验收 JWT，也不得复用 App user_acceptance principal 消耗推荐曝光、改写关系或污染后续自然入口证据。
- 首页、视频书、消息与我的统一由 metadata `app-core-readback` scope 验证；Content 只读取已激活 immutable release，Chat/Circle/User/Assistant/RTC 只由 user_acceptance typed recipe 经公开命令创建并回读。固定账号、固定业务对象 ID、DB seed、派生计数预填与运行时 fake 均不得构成 Gamma 证据。
- 每个 T3/API 验证段必须同时记录执行前和执行后 readiness；验证后 edge 或所需控制面未恢复健康时结果为 `GATE_BLOCK`，不得用已经通过的业务断言掩盖环境失稳。

<a id="req-002"></a>
### REQ-002 远端复验只在 prod gray-initial 执行

- 仓库不定义 hosted gamma 环境；真实远端复验只在 prod `gray-initial` rollout stage 执行，与 gamma-local 的本地左移和正式候选阻断职责不重叠。

<a id="req-003"></a>
### REQ-003 本地阻断验证与远端准出边界

- gamma-local 必须覆盖 `local_contract -> api_integration -> user_acceptance` 的本地可验证链路，但不得替代 prod gray-initial 的远端准出证据。
- main 只接受绑定当前候选摘要的 gamma-local canonical 回执，不接受提交前报告、其他候选回执或远端复验证据代替该阶段。
- 本地 `user_acceptance` runner 统一 App 与测试进程 endpoint，至少在一台模拟器或真机完成 Patrol 核心旅程。
- gamma-local 服务名册与 prod `runtime.yaml` 及各服务真实环境部署目录一致。
- recommendation 对外 DNS 名各环境统一为 `recommendation-service:8000`
- 由统一架构门禁守护。
- `realtime-gateway` 作为第一方 workload 纳入 topology 与 `edge-media` 验证链，禁止 pending/registered-only 占位进入 gamma/prod。
- gamma-local 由 Ops infra/external Compose 与各第一方服务自治 Compose 片段共同承载；`profiles` 只表达按需运行能力，不承担服务注册。
- 对外 DNS 名与 prod 对齐：recommendation 服务在各环境统一以 `http://recommendation-service:8000` 被调用。
- edge-media 名册与 prod 目录扫描结果一致：`realtime-gateway / rtc-service / livekit / coturn` 必须由真实 compose/Kustomize 入口承载。

<a id="req-004"></a>
### REQ-004 首页可用性、受保护发布与本地 TLS 边界

- `content-release` workload 只启动首页读取与 release 验证所需的 canonical service 集合，
  并使用与 full workload 同一 packaged OCI candidate；不得维护专用镜像或 fixture 数据源。
- `content-commercial` workload 在同一内容 consumer plane 上只增加
  `product-ops-service`、其持久化依赖与 canonical API edge 路由，用于候选绑定的
  精品池运营 command/event；不得借此声称 Assistant、RTC、通知、外部登录或全量
  商业观测已就绪，也不得把 Data `commercial` phase 的 telemetry/trace/SLO 语义缩减
  为精品池入池。
- Alpha/Beta/Gamma 的 `content-commercial` 操作只接受 target-scoped、短时、最小
  scope 的受管非生产 operator principal；Prod 继续要求真实 OIDC，非生产凭据不得进入
  Prod package 或运行时。精品池只能经
  `UpsertPremiumPoolEntry -> events.ops.premium_pool_entry -> rm_premium_pool` 收敛，
  禁止 Data 直写、projection seed 或手工数据库修补。
- 首页 runtime readiness 与 FilterCatalog 发布是两个独立门：runtime 启动只证明服务
  readiness，不读取或改写 catalog；`stage-and-activate -> verify` 由启动后的显式 release
  操作执行。发布失败不得污染已经健康的 runtime，也不得以空 catalog 合成成功。
- 本地受保护 FilterCatalog 操作只能使用按调用即时签发的短期 service JWT：
  `sub=service:qwq-data`、`roles=["service"]`、
  `scope=content.filter_catalog.manage`、TTL 不超过 30 分钟；token 仅进入子进程环境，
  不得写 argv、日志、报告或长期文件。
- local-managed target 的 host probe 必须显式使用 target CA；Simulator/Emulator 必须将
  同一根安装至系统 trust store 并以默认平台信任栈验证。禁止 `-k`、
  `--no-check-certificate`、App 私有 trust 注入或静默回退系统公网根。
- Feed 黑盒探针必须校验 `outcome/emptyReason`；验收首页时必须证明非空结果来自当前
  immutable release。canonical empty 只能作为空态契约证据，不能替代首页可用性证据。
- Alpha、Beta、Gamma 的 runtime health scope 必须优先读取共享 `stack_status` /
  startup receipt；旧环境专用回执只能作为受控 legacy fallback，不能遮蔽当前 runtime。

## 4. 契约引用

- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`
- canonical：`quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
- canonical：`quwoquan_ops/cli/lib/nonprod_business_data.py`（仅组合 ContractGraph operation，不拥有 wire schema）
- canonical：候选绑定的 `qwq.nonprod_acceptance_dataset_receipt` 运行回执
- canonical：`quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml` 与 `quwoquan_service/services/*/deploy/compose.yaml`
- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/gate/verify_service_architecture.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 gamma-local 左移验证与 main 正式阻断回执

- GIVEN 开发机具备 Docker mirror 栈与至少一台模拟器/浏览器 runner。
- GIVEN 服务以 APP_ENV=gamma 启动，端侧以 APP_RUNTIME_ENV=gamma 的 production Remote composition 接入本地 mirror endpoint，代码图中不存在运行时 Mock/Remote 开关。
- GIVEN 内容与 creator 仅来自当前 immutable release，非内容业务数据由当前候选的 typed recipe 经正式认证与公开 API 创建。
- WHEN 提交前运行 make gate-local-gamma，或 main 受控 promotion 对当前 candidate digest 执行 gamma-local release-fast。
- THEN 启动 gamma 语义镜像栈并完成配置摘要、依赖、health、local-managed TLS/resolver 与 media 前置检查。
- THEN 依次执行 local_contract->user_acceptance，并在 `.qwq_output/env/gamma/runs/<run-id>/` 生成 canonical 报告与摘要；缺 local-managed TLS/resolver、设备或服务依赖时状态为 GATE_BLOCK，公网 DNS/ACME 缺失不阻断 gamma-local。
- THEN 提交前运行只形成左移报告；main 运行形成绑定当前 candidate digest 的正式 Gamma 环境回执，缺失、失败或摘要不一致均阻断 Prod。
- THEN full health 覆盖 platform-ops、content、user、Elasticsearch 与 proxy；受保护 user route 经 canonical Caddy 上游抵达 user-service。
- THEN content 等领域探针从候选绑定 receipt 解析独立真实 verification principal，App user_acceptance principal 的推荐曝光与关系事实保持不变。
- THEN `app-core-readback` 在同一 production Remote composition 中断言首页推荐非空、视频书只返回可播放 video work、Chat API contract 可发送/撤回/回读消息、`/me` 的 owner/persona/displayName/postCount 与本次 ephemeral principal 一致。
- THEN ContactDiscovery、Conversation 与 Message 验收事实经公开 operation 与幂等键建立；环境不得读取 fixture 或直接写服务存储冒充在线业务 provisioning。
- THEN 每段集成探针结束后重新验证 edge/readiness；PostgreSQL 连接耗尽、outbox heartbeat stale 或任一依赖降级均阻断通过。
- THEN 复用 package 时的 image 缺失在启动前失败并给出修复动作，而非运行时拉取或人工 image tag 修补。

<a id="gwt-002"></a>
### GWT-002 远端复验只在 prod gray-initial 执行

- GIVEN gamma-local 已作为提交前主验证链，gamma 仅本地、无远端 gamma。
- WHEN 需要云侧手动复验、nightly 或发布前高置信度回归时，统一在 prod gray-initial rollout stage 执行。
- THEN prod gray-initial 执行 hosted deploy、readiness、api_integration API contract、assistant/chat-avatar probe。
- THEN 远端复验不承担提交前左移职责，也不与 gamma-local 重复维护第二套验证逻辑。

<a id="gwt-003"></a>
### GWT-003 首页 content-release 与系统 TLS 可用

- GIVEN full runtime candidate 已绑定 candidate/rollback release，FilterCatalog active release
  已由显式短期 service JWT 操作激活，target local-managed CA 有效。
- WHEN 启动 Alpha、Beta 或 Gamma `content-release` workload 并运行 App 首页与 Feed probe。
- THEN runtime 只装载 canonical content consumer 服务，health scope 与 startup receipt
  一致，Feed 返回 `outcome=content`、`emptyReason=null` 且至少一个 postId 命中当前 release。
- THEN host、Simulator/Emulator 与 App 默认信任栈均完成 TLS 验证，App 不含私有 CA 或
  TLS bypass。
- AND FilterCatalog、TLS、Feed 契约或 release identity 任一失败均返回可区分的
  `GATE_BLOCK`，不显示“环境健康”伪成功、不写入 fixture 或 fallback 内容。

<a id="gwt-004"></a>
### GWT-004 候选绑定的精品池运营闭环

- GIVEN Alpha、Beta 或 Gamma 已以当前 immutable package 启动并完成 release import，
  release 中至少一个 video work 具备可播放媒体事实。
- WHEN 以 `content-commercial` workload 启动最小运营切片，并由符合环境身份策略的
  operator 调用 `UpsertPremiumPoolEntry`。
- THEN command receipt、`events.ops.premium_pool_entry` 与 Recommendation
  `rm_premium_pool` 回读绑定同一 contentId/release/importRunId，公网 Ops 路由与
  Product Ops 内部 health 均通过。
- WHEN 随后恢复 `content-release` workload 并重新执行 consumer verify。
- THEN candidate-bound readiness、通用 Feed、视频书与 premium Feed 均只读取当前
  release，`premiumPlayableVideos > 0`；任何身份、事件、投影或候选摘要不一致均
  `GATE_BLOCK`，不得使用历史 receipt 代替。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 gamma-local 左移验证与 main 正式阻断回执

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺真实 main 候选 Gamma 回执与直接 `spec_ref`；目标：gamma-local 既是开发与提交前的主验证链，也是绑定当前 candidate digest 的正式 Prod 前置阻断阶段。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 prod gray-initial 远端复验证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：真实远端复验只允许在 prod `gray-initial` rollout stage 产生，不能用 gamma-local 证据替代。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
