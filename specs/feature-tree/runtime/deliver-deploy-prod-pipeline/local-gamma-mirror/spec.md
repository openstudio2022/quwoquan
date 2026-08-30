# L3 Story：本地 Gamma 镜像 (`local-gamma-mirror`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望 gamma-local 同时承担开发与提交前左移验证，以及 main 受控 promotion 的正式阻断回执（gamma 仅本地，无远端 gamma）；真实远端复验由 prod canary rollout stage 承接，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

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
- 首页、视频书、消息与我的统一由 metadata `app-core-readback` scope 验证。Content 只读取已激活 immutable release，Chat/Circle/User/Assistant/Notification/RTC 只由当前选中 user_acceptance 用例的强类型 capability request graph 经公开命令创建并回读。未被请求的领域 Provider 不导入、不检查、不清理。固定账号、固定业务对象 ID、DB seed、派生计数预填与运行时 fake 均不得构成 Gamma 证据。
- 每个 T3/API 验证段必须同时记录执行前和执行后 readiness；验证后 edge 或所需控制面未恢复健康时结果为 `GATE_BLOCK`，不得用已经通过的业务断言掩盖环境失稳。

<a id="req-002"></a>
### REQ-002 远端复验只在 prod canary 执行

- 仓库不定义 hosted gamma 环境；真实远端复验只在 prod `canary` rollout stage 执行，与 gamma-local 的本地左移和正式候选阻断职责不重叠。

<a id="req-003"></a>
### REQ-003 本地阻断验证与远端准出边界

- gamma-local 必须覆盖 `local_contract -> api_integration -> user_acceptance` 的本地可验证链路，但不得替代 prod canary 的远端准出证据。
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
- Alpha、Beta、Gamma 的 runtime health scope 只能读取 target-scoped canonical current
  startup attempt receipt，并校验 running、target/environment、workload、配置 digest 与镜像
  identity；receipt 缺失、停止、损坏或 identity 漂移必须 fail-closed 到 full scope，禁止读取
  环境专用状态文件或父运行报告作为 fallback。

<a id="req-005"></a>
### REQ-005 本地孤儿 Compose 栈的精确恢复

- Alpha、Beta、Gamma 的 canonical startup receipt 缺失或已停止、但 target canonical Compose
  project 仍有残留资源时，只能先生成一次性、短时有效的只读 teardown attestation；项目名必须
  从 target 派生，CLI 不接受任意 Compose project 或项目前缀。
- attestation 必须绑定 target、完整 canonical 端口清单、精确 project/Compose labels，以及当次
  容器、网络、volume 的 ID/name/labels/config digest 与容器 image digest；同一路径只能创建一次。
- 旧栈发布的非 canonical host port 必须一并进入 project/non-canonical port 清单；只有该端口不在
  其他 target canonical block、实时 socket 已占用且 Docker publisher 恰为 attested container 时
  才可纳入恢复。删除后必须逐端口证明已释放；若被其他进程接管则保留现场并 `GATE_BLOCK`。
- 执行前必须显式确认并重采全部资源；attestation 过期、资源增删或配置漂移、存在 active
  consumer lease、startup receipt 正在运行或仍可走 candidate-bound normal down 时一律
  `GATE_BLOCK`。
- 执行只允许按 attestation 中的精确 ID 删除容器与网络；named volume 默认保留，额外 live
  resource、旧 attestation、任意项目名、Compose project 级模糊 down 或自动 plan-to-execute
  均禁止。
- 每个删除步骤必须先写一次性 execution journal，并在成功后写精确 resource ID step receipt；
  中途失败必须把已确认删除项、失败命令与 unknown/partial outcome 写入消费回执，禁止报告为
  “未执行破坏性动作”或用同一 attestation 静默重放。
- 全部删除命令成功后，须有界等待目标 runtime 自有的 published endpoint 释放再做最终 postcheck。
  该集合是 transport-exact 的 `role:hostPort/protocol`，由目标 port profile 的 canonical publisher
  闭包排除 Data fleet 自有 role 后并上 attested 的非 canonical 端口构成；Data fleet 是长驻栈，
  同 profile 端口不等于目标 runtime 所有权，TCP/UDP 不得合并判定。若 create-once partial consumption 已精确记录
  全部容器/网络删除成功、failedCommand 为空且失败仅来自该即时 postcheck，则允许同一 confirm 做
  audit-only convergence：不得重跑删除，只重采零容器/网络、volume 全等和上述 endpoint 集合全释放，
  并写绑定原 attestation/consumption digest 的 create-once convergence receipt；其他 partial/unknown
  形状一律禁止收敛。

## 4. 契约引用

- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`
- canonical：`quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
- canonical：`quwoquan_ops/cli/lib/test_data/capabilities/**` 与 `test_data/api.py`（只公开强类型 capability contract，不拥有 wire schema）
- canonical：候选绑定的追加式 test-data instance / request / operation / cleanup receipt
- canonical：`quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml` 与 `quwoquan_service/services/*/deploy/compose.yaml`
- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/gate/verify_service_architecture.py`
- canonical：`quwoquan_ops/cli/lib/orphan_compose_teardown/`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 gamma-local 左移验证与 main 正式阻断回执

- GIVEN 开发机具备 Docker mirror 栈与至少一台模拟器/浏览器 runner。
- GIVEN 服务以 APP_ENV=gamma 启动，端侧以 APP_RUNTIME_ENV=gamma 的 production Remote composition 接入本地 mirror endpoint，代码图中不存在运行时 Mock/Remote 开关。
- GIVEN 内容与 Creator 仅来自当前 immutable release，非内容业务数据由当前候选下所选用例的强类型 capability request graph 经正式认证与公开 API 创建。
- WHEN 提交前运行 make gate-local-gamma，或 main 受控 promotion 对当前 candidate digest 执行 gamma-local release-fast。
- THEN 启动 gamma 语义镜像栈并完成配置摘要、依赖、health、local-managed TLS/resolver 与 media 前置检查。
- THEN 依次执行 local_contract->user_acceptance，并在 `.qwq_output/env/gamma/runs/<run-id>/` 生成 canonical 报告与摘要；缺 local-managed TLS/resolver、设备或服务依赖时状态为 GATE_BLOCK，公网 DNS/ACME 缺失不阻断 gamma-local。
- THEN 提交前运行只形成左移报告；main 运行形成绑定当前 candidate digest 的正式 Gamma 环境回执，缺失、失败或摘要不一致均阻断 Prod。
- THEN full health 覆盖 platform-ops、content、user、Elasticsearch 与 proxy；受保护 user route 经 canonical Caddy 上游抵达 user-service。
- THEN content 等领域探针从候选绑定 receipt 解析独立真实 verification principal，App user_acceptance principal 的推荐曝光与关系事实保持不变。
- THEN `app-core-readback` 在同一 production Remote composition 中断言首页推荐非空、视频书只返回可播放 video work、Chat API contract 可发送/撤回/回读消息、`/me` 的 owner/persona/displayName/postCount 与本次 ephemeral principal 一致。
- THEN ContactDiscovery、Conversation 与 Message 验收事实经公开 operation 与幂等键建立；环境不得读取 fixture 或直接写服务存储冒充在线业务 provisioning。
- THEN 数据准备、测试正文与 cleanup 分段计时并记录 operation count、加载 Provider 和 DAG critical path；Chat-only 用例不加载 Assistant、Notification 或 RTC Provider。
- THEN 每段集成探针结束后重新验证 edge/readiness；PostgreSQL 连接耗尽、outbox heartbeat stale 或任一依赖降级均阻断通过。
- THEN 复用 package 时的 image 缺失在启动前失败并给出修复动作，而非运行时拉取或人工 image tag 修补。

<a id="gwt-002"></a>
### GWT-002 远端复验只在 prod canary 执行

- GIVEN gamma-local 已作为提交前主验证链，gamma 仅本地、无远端 gamma。
- WHEN 需要云侧手动复验、nightly 或发布前高置信度回归时，统一在 prod canary rollout stage 执行。
- THEN prod canary 执行 hosted deploy、readiness、api_integration API contract、assistant/chat-avatar probe。
- THEN 远端复验不承担提交前左移职责，也不与 gamma-local 重复维护第二套验证逻辑。

<a id="gwt-003"></a>
### GWT-003 首页 content-release 与系统 TLS 可用

- GIVEN full runtime candidate 已绑定 candidate/rollback release，FilterCatalog active release
  已由显式短期 service JWT 操作激活，target local-managed CA 有效。
- WHEN 启动 Alpha、Beta 或 Gamma `content-release` workload 并运行 App 首页与 Feed probe。
- THEN runtime 只装载 canonical content consumer 服务，health scope 与 target-scoped running
  startup attempt receipt 一致，Feed 返回 `outcome=content`、`emptyReason=null` 且至少一个
  postId 命中当前 release。
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

<a id="gwt-005"></a>
### GWT-005 本地孤儿 Compose 栈只按一次性精确清单恢复

- GIVEN Alpha、Beta 或 Gamma 没有 active consumer lease，canonical startup receipt 不存在、
  状态为 stopped，或状态非 stopped 但其 candidate 已不可用，且 canonical target project 仍有
  带完整 Compose labels 的残留资源。
- WHEN 运维先以显式 canonical attestation path 运行 orphan Compose repair plan。
- THEN 只生成 create-once、短时有效、带自身 digest 的完整资源清单和人工复核计划，不删除任何
  容器、网络或 volume。
- WHEN 运维使用同一路径和显式 teardown confirmation 再次执行，且实时重采与 attestation
  完全一致。
- THEN 只删除 attestation 列出的容器 ID 与网络 ID，保留全部 named volumes，并写入一次性消费
  回执；active lease、过期/重放、额外资源或任一 identity/config/image/port
  漂移均在删除前 `GATE_BLOCK`；中途失败则以 create-once journal、逐步 success receipt 与
  partial-failure consumption 保存实际成功 ID 和未确定命令，禁止把部分删除记为零变更。
  非 canonical published host port 还必须绑定唯一实时 Docker publisher，且不得落入另一环境的
  canonical block；执行后目标 runtime 自有的 published endpoint 须逐条按 `role:hostPort/protocol`
  实测释放，该集合为 canonical publisher 闭包排除 Data fleet 自有 role 后并上 attested 非 canonical 端口。
  全删除成功但即时端口转发尚未释放时必须保留 partial receipt；仅在全部 success step、完整 removed
  ID、空 failedCommand、零资源重现、volume 全等且有界端口复验通过时，后续同一 confirm 才可写
  audit-only convergence receipt，且不得再次执行任何删除命令。
- AND 状态非 stopped 的 receipt 只在它自己的 candidate 已不可用时进入本恢复路径，判据是
  candidate 目录缺失或其 runtime 拓扑不可加载这一客观事实，而不是任何操作者声明；candidate
  仍可用的运行中 receipt 一律在采样前 `GATE_BLOCK`，必须改走 candidate-bound normal down。
- AND 经该出口完成删除后 receipt 转为 stopped 并把 reclaim 原因写入 failure，named volumes
  全部保留，后续 up 不再被这份已失效的运行中 receipt 阻断。

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
- 完成判定：`GWT-001` 的 17 条 THEN 组全部具备子句级 `spec_ref`（`gwt-001.t1..t17`）绑定的真实测试或可执行门证据，且 Gamma 回执必须绑定真实 main 候选的 candidate digest。

<a id="open-002"></a>
### OPEN-002 prod canary 远端复验证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：真实远端复验只允许在 prod `canary` rollout stage 产生，不能用 gamma-local 证据替代。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 startup receipt 不记录 candidate 所属 deployment work root

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 receipt 只记 `candidateDigest`，不记该 candidate 当时所在的 `QWQ_DEPLOY_WORK_ROOT`。于是同一 digest 在不同 work root 下不可寻址：一次在 hermetic 打包工作区（`$TMPDIR/quwoquan-deploy.XXXXXX`）里完成的 up 会写下引用该临时 candidate 的运行中 receipt，而之后任何在默认 work root（`~/.cache/quwoquan/deploy`）下执行的 down 都只能报 candidate 缺失。gamma-local 已实测落入该状态并触发三路互锁：normal down 强绑 candidate 重放拓扑而 candidate 不可寻址，orphan Compose 恢复当时只接受不存在或 stopped 的 receipt，`reclaim-undownable-startup-receipt` 又要求运行时残留为零而 18 个容器仍在运行。`GWT-005` 的 t10 到 t12 已把「candidate 客观不可用时的合法拆除」补成受治理出口并解开本次死锁，但只要 receipt 不携带 work root 归属，同样的互锁就还会由下一次 hermetic 打包再造出来。
- 完成判定：`GWT-005` 断言 receipt 记录 candidate 所属 deployment work root，且 candidate 在其记录的 work root 下可寻址时 normal down 必须走 candidate-bound 路径、不得落入 orphan 出口；并且 gamma-local 经恢复后 `stackctl health --scope full` 复验 mongodb 与 postgres 均 healthy。
