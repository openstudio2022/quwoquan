# L3 Story：首页流式性能与可用性 (`streaming-feed-performance`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为连续浏览首页 Post 和视频书的用户，
我希望在正常网络、弱网、并发峰值和长时间使用下都能快速看到内容、顺滑续接并在失败时立即获得可恢复终态，
从而不因无限加载、资源泄漏、重试放大或媒体等待而中断消费。

## 2. 范围与非目标

### In Scope

- feed query/cursor/index/projection、active supply 预检、依赖并发与响应预算。
- App 首屏/翻页生命周期、长滚动窗口、渲染预算、频道回收与长会话资源上限。
- QuerySnapshot stale-while-revalidate、图片字节预算、视频 N+1 预热、弱网恢复与离线首屏组合验收。
- typed 性能/QoE/可用性事件、SLO、告警、真机长滚动与四环境 Remote 证据。

### Out of Scope

- 重做召回、粗排、精排或曝光策略。
- 在 feed 内实现第二套缓存、视频处理、网关、弹性引擎或遥测管道。
- 用 fixture、本地 UI Mock、源码 grep 或空门禁代替真实 Remote/环境/真机证据。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 feed 读路径和依赖成本有界

- `GET /content/feed` 的 `limit` 必须在 contract 声明的闭区间内验证和截断；任何内部召回或 hydration 放大都必须从同一上限派生。
- cursor 必须不透明、具备完整性保护、绑定完整请求上下文并限制可续接深度。App 只透传 cursor；伪造、过期、超界或与请求上下文不匹配时返回 canonical error。cursor 不携带协议版本信封。
- 推荐首刷完成最终排序后必须生成 [DEC-003](../design.md#dec-003) 的不可变 `RankedFeedWindow`。读取不得滑动 TTL，窗口、canonical subject 与全族 live key/live payload bytes 必须同时受硬限保护。序列化按条目逐块累积完整 wire bytes，超过剩余预算时立即拒绝，不得先物化无界整窗 JSON。
- `RankedFeedWindow` 以 subject digest 确定性映射到 256 个固定 quota shard。每 shard 默认最多 128 个 live value / 134217728 live payload bytes，同 subject 最多 8 个窗口，因此全族默认硬上限为 32768 个 live value / 34359738368 live payload bytes。`FeedDeliveryPage` 以 scope digest 映射到 256 个固定 quota shard。每 shard 默认最多 512 个 live value / 33554432 live payload bytes，同 scope 最多 400 页，因此全族默认硬上限为 131072 个 live value / 8589934592 live payload bytes。该预算是业务准入上限，不得用 Redis `maxmemory`、淘汰策略或环境物理容量替代。
- value、quota index 与 owner/payload-bytes metadata 必须共享固定 quota-shard Redis Cluster slot。Adapter 最多预读 `max_live_records_per_shard + 1` 个成员，并把脚本可访问的每个 value 明确列入 `EVAL KEYS`。Lua 内也只读取同一硬界内成员，禁止动态 key、`SCAN/KEYS`、无界 `ZRANGE`、跨 slot 操作和可漂移 mutable counter。winner replay 不重复增加 bytes。过期/缺失 value 清理精确删除 index/metadata 并扣除 bytes。并发索引变化只能无写入有界重试。
- 每 subject/scope 上限命中只原子淘汰该 owner 最老记录；quota shard key/byte 上限命中必须 typed fail-closed 拒绝 contender，禁止淘汰其他 owner。index/metadata 超界、缺失或 byte 不一致必须以 repair-bound typed failure 拒绝，禁止在线无界修复。
- content Post、user Persona、tag TagNodeView 与 entity Homepage 是其 ID/ref/title/URL 的单字段 UTF-8 byte/count 上限 owner；`RankedFeedWindow` 与 `FeedDeliveryPage` 编码前按这些 owner contract 准入。2 MiB/64 KiB 聚合门不得替代字段门。
- Redis keyspace 只读写无协议版本前缀的 canonical `rec:ranked_feed_window:*` / `rec:feed_delivery_page:*` 固定 quota-shard key，payload 与 cursor 均无 schema-version 信封；任何其他形态不得 dual-read 或 shim。生产切换必须使用单候选制受控发布，并把 cursor 刷新终态、回滚窗口与 readback 纳入环境验收。
- 商用 HotPath composition 必须在构造期要求 Redis pipeline capability；session、硬排除、served/impressed/negative 与 relaxed exposure 过滤只走同一 pipeline，禁止顺序或并行兼容回退。
- 具名或已验证设备流量按 actor 隔离，无身份公开流量按 session 隔离；续页只按 `(ordinal, contentId)` 读取冻结结果。
- 每个成功下发且仍可继续的页面必须先写入 10 分钟固定 TTL 的不可变 `FeedDeliveryPage`，再返回带 delivery-page 身份的 next cursor。下一页通过 previous cursor 回放已交付 Post identity/顺序与对象卡快照，只做当前可见性 hydration；缺失或不可见 Post 只缩短页面，禁止重新 recall、重排或补替代内容。cursor scope 同时绑定 actor/session/route/pageSize/release/feedRequestId/expiry。
- discovery feed 的查询过滤、排序、cursor keyset 与 `storage.yaml` 索引完全一致；服务启动与 importer 都执行幂等 `EnsureIndexes`，API integration 以真实 Mongo `explain` 防止全表扫描或内存排序。
- 召回和 hydration 只读取下发必需的 canonical projection，禁止先解码完整 Post 再丢弃字段；cursor 必须沿用排序 keyset，不得回退到 Mongo `_id` 续接。
- 每个 recall source 的主输出最多接纳 `RecallRequest.limit` 项。仅为 canonical active-release anchor 允许检查紧邻主窗口的一个同尺寸 handoff window，总复制和扫描不得超过 `2 * limit`，更远输出 fail-closed 且仍记录 source budget failure。
- active supply readiness 在同一环境/release 内使用有界 TTL、抖动和 singleflight 共享成功快照；失败、切 release 与 attestation 变更立即失效，不用旧快照伪造新 release 成功。

<a id="req-002"></a>
### REQ-002 App 请求、长滚动与渲染资源有界

- 首屏加载、刷新与翻页分别持有 request generation 和取消权；任一操作不得取消无关操作，被替代、超时、返回或 dispose 的旧结果不得回写。
- 列表只保留能支持当前 viewport、有界回滑和续接的内存窗口，裁剪时保持顺序、滚动锚点、cursor 与跨页去重语义。
- 首页每个远端响应页最多接受 20 个 Post，超限在归因与互动投影副作用前 fail-closed。
- 首页 generated operation 的 JSON body 必须在完整缓冲和 raw JSON 物化前按所属 operation 的 canonical live-response byte limit 分块准入；active/physical decode、pending task 和 queued bytes 必须分别有硬限，取消、deadline 与迟到结果不得释放物理预算后继续无界累积。
- 当前 Widget 展开最多 4 个完整页，前后缓冲合计最多保留 6 页/120 个 Post 引用，跨页 seen item 采用 2048 项 LRU。页移动只发生在完整远端页边界。回滑到顶部先从 leading buffer 回补，后续下滑先消费 trailing buffer 再发 Remote。内存压力与非活跃频道按声明策略释放。
- 本地 leading buffer 耗尽后，App 只使用服务端 previous cursor prepend 已交付页。远端回页仅与当前 retained Post 去重，禁止用历史 seen LRU 删除已经被窗口淘汰、现在应重新显示的 Post。prepend 使用独立 generation/cancellation/error 状态。append/prepend 每次发出 Remote 前都从 resident-window 真相源重新判定 cursor expiry，过期或跨 session 的持久快照以及长时间空闲后的过期 render snapshot cursor 均不得发出。
- 首页频道配置最多 8 个唯一 id；整份远端覆盖超限、重复或任一条目/字段解析失败时都必须 fail-closed 回退发布默认，禁止截断、静默去重或部分接受。运行期配置替换只回收被移除的首页频道 generation/controller/state，不得误删 discovery tab。
- 高频 rebuild 只订阅可见项必需的状态，网格不嵌套多个可滚动容器；每卡定时、JSON 解码、布局与绘制成本必须在 frame 预算内可观测，不把扩大 `cacheExtent` 当成性能修复。

<a id="req-003"></a>
### REQ-003 图片、视频和离线首屏共用一套资源预算

- content-addressed public media 使用稳定资产身份作为 App/CDN 缓存 key，签名查询参数不得造成同一资产无界分片；只有不可变且授权语义允许的 public slice 可返回长期 `immutable` 缓存。
- alpha/beta/gamma-local/prod 的媒体 origin/CDN 对同一 public slice 保持 Range、MIME、CORS、cache-control 和 authority-only 差异；本地 origin 不得用 `no-store` 隐藏生产缓存行为。
- 图片内存/磁盘字节、解码尺寸、失败负缓存与 pageflip 纹理均有界；所有业务图片只经统一入口。
- 视频书仅对当前项和 N+1 项执行取消友好的封面/媒体预热，两者共用全局解码槽位与 6 秒准备预算；N+1 不自动播放，方向变更、切集、离开或内存压力立即取消。
- QuerySnapshot 必须通过 `runtime-client-foundation/local-cache-architecture` 提供真实 stale-while-revalidate 与离线首屏；HLS/CMAF ABR 仅经 `runtime-media` P1-B 契约和 capability/feature flag 进入，失败时回退到同源 P0 progressive MP4。
- 持久 QuerySnapshot 只能保存从首屏 `nextCursor` 连续可达的有界页链，禁止保存无法续接的“最新页孤岛”；当前策略最多保存连续 4 页，未证明的更长离线窗口保持开放事项。
- QuerySnapshot 写盘前必须按 canonical 契约声明的逐字段 UTF-8 字节上限准入每个 Post 字段，任一字段超限即拒绝整个 snapshot/page，整页 2 MiB 预算只是聚合兜底，不得替代字段门。限额表只能由 content-service Post `fields.yaml` 与 discovery feed projection 的 `max_utf8_bytes` 经 codegen 派生（当前为 `postId=256`、`authorId=128`、`title=320`）；同一 wire key 在两处声明不一致或派生结果为空时，生成期 fail-closed，不得落盘空限额表。
- HLS/CMAF 与 progressive MP4 切换属于同一 asset/version 时必须尽力从原位置续播；seek 恢复失败不得把可播放 fallback 误判为媒体失败。
- 普通拖动与 source-switch seek 共用同一物理命令 admission 和绝对 deadline；平台 Future 不可取消时，跨 controller epoch 的未终止命令总量仍必须有 session 硬限，迟到完成只能释放预算且不得回写 superseded 状态。

<a id="req-004"></a>
### REQ-004 弱网、峰值与依赖故障不得放大

- App 以 canonical connectivity 与实际请求结果表达网络质量；首屏与翻页分别遵循声明的 wait/retry/deadline 预算，只对幂等且可恢复失败执行有界退避和抖动。
- long-poll/WebSocket 断线使用有界退避、可见性与前后台恢复；无活动订阅时不连续轮询。
- feed 路由的 deadline、rate limit、InflightLimiter/bulkhead、circuit breaker、Redis/Mongo timeout、fanout 上限与缓存 TTL/jitter 必须来自所属 contract/config 真相源，并返回 typed canonical failure 或预先声明的降级。
- 固定 quota shard 数、每 shard live key/live payload byte 上限必须来自 `sys.content-service.feed.*` restart 配置；启动时对 power-of-two、owner 上限、全族乘积溢出执行 fail-fast。创建指标必须区分 owner eviction、shard key reject、shard byte reject 与 repair reject，并提供触达 shard 的精确 live key/live bytes 分布、SLO、告警、看板和回滚入口。
- recall orchestrator 不得用 `WaitGroup` 等待不遵守 context 的依赖。deadline 后只接纳已完成结果，迟到结果不回写；每 source 未终止调用必须受 feed canonical inflight budget 约束，槽位耗尽立即进入可观察失败终态。

<a id="req-005"></a>
### REQ-005 长会话状态可回收且可恢复

- 曝光、fallback、visit、频道和媒体状态不得随会话无界增长；每个集合都声明 TTL/LRU/window 与超限后语义。
- 首页 `impressed` 去重采用 30 分钟滚动 TTL 与最多 2048 个 contentId 的 LRU 窗口，行为待发缓冲最多保留 3 个 batch；文章 reader fallback 去重采用 30 分钟滚动 TTL 与最多 512 个 `postId|reason`。TTL 到期或 LRU 淘汰只允许后续真实行为重新计量，不得改变内容过滤、推荐负反馈或恢复语义。
- realtime patch 幂等窗口最多保留 256 个 patchId，visit 本地记录最多 2048 项。首页频道滚动锚点最多 8 项，配置 churn 回收已移除频道。作品 viewer 局部 post 状态最多 16 项并保护当前 ±2，派生投影 LRU 最多 48 项，单 post 原图授权最多 12 项且预留 5 秒过期安全窗。内存压力只保留当前作品。
- 文章详情 hydration 同时最多 1 个 active 与 1 个 latest-only pending；切换作品、进入非文章页、淘汰或 dispose 必须贯穿 cancellation，并将迟到成功记为 `superseded`，不得回写已淘汰 post 或伪造错误态。
- 视频分集 session 只由已 mounted episode stage 持有，子树卸载后立即注销并 dispose；父 viewer registry 不拥有历史 session。分集 stage/session identity 必须由 Post、canonical asset/version（无 asset 时用 delivery cache identity）和重复 occurrence 共同唯一化，不能把公开交付 URL 当作分集唯一键。
- access token 以 JWT `exp` 作为不授予权限的调度提示，在失效前 2 分钟受控刷新；所有 refresh（包括强制恢复）必须共享 singleflight，禁止同一 refresh token 并发 rotation。不可解析的旧 token 不做推测性换发，服务端仍是有效性的唯一裁判。
- WebSocket 在前台恢复后从 canonical cursor 续接；失效身份或续接不可能时进入明确恢复组。
- 内存压力、ANR 或解码槽位紧张时先停止预取、回收非活跃频道与媒体，保留当前内容、滚动锚点和可执行恢复。

<a id="req-006"></a>
### REQ-006 typed 性能遥测保留分母并与 SLO 同源

- feed 首屏/翻页终态、滚动帧、图片缓存读取、活跃视频 controller/等待队列、TTFF/rebuffer/seek、ANR 与内存压力必须通过 product-ops catalog 的 typed payload 上报，不经 dynamic event 黑名单或丢字段投影。
- 滚动帧样本必须记录 `sampledFrames=0` 之外的每个完整批次，包括 `jankyFrames=0` 的清洁批次；分子、分母、build/raster 最坏帧与阈值不得丢失。
- 事件维度只保留 catalog 声明的低基数 surface/channel/network/result/cache source 等值；objectId、URL、cursor 与动态错误不进入 Prometheus label。
- SLO、采样、保留、告警、灰度与回滚只从 metadata/config/observability contract 派生；空门禁、无分母比率或未被生产调用的 record 方法不构成证据。

## 4. 契约引用

- canonical feed：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical delivered page：`quwoquan_service/services/content-service/contracts/content/feed_delivery_page/**`
- canonical storage：`quwoquan_service/services/content-service/contracts/content/post/storage.yaml`
- canonical error：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`
- canonical cache：[`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)
- ranked window Redis：`quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml`
- 首页频道远程配置：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml` 的 `AppConfigSlice` / `ContentAppConfigHomeChannel`，由同对象 `operations.yaml` 的 `GetAppConfig` 唯一公开 query 交付
- typed telemetry：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`
- SLO/alert：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- runtime resilience：[`runtime-governance/resilience-policy-engine`](../../../runtime/runtime-governance/resilience-policy-engine/spec.md)
- gateway rate limit：[`gateway-orchestrator-foundation/unified-entry-security/rate-limit-protection`](../../../gateway-orchestrator-foundation/unified-entry-security/rate-limit-protection/spec.md)
- gateway timeout：[`gateway-orchestrator-foundation/orchestration-degradation-rollback/downstream-timeout-fallback`](../../../gateway-orchestrator-foundation/orchestration-degradation-rollback/downstream-timeout-fallback/spec.md)
- local cache：[`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)
- runtime media：[`runtime-media`](../../../runtime/runtime-media/spec.md)
- feed admission 配置：`quwoquan_service/services/content-service/config/schema.yaml` 的 `sys.content-service.feed.*`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 feed 读路径不放大请求或扫描

- GIVEN 客户端传入边界、越界、伪造或过期的 limit/cursor，且 Mongo 中存在大量可推荐内容。
- WHEN content-service 处理首页、翻页和并发首页请求。
- THEN 只执行 contract 上限内的查询、召回与 hydration，非法 cursor 返回 canonical error，`explain` 命中与 filter/sort/keyset 一致的索引。
- AND 同 release 的并发首页共享一次 readiness 工作，切 release 或失败不复用旧成功。
- AND 真实 Redis Lua 在多个 subject/scope 映射到同一 quota shard 时仍满足全族 key/byte 上限。owner 第 9 个窗口/第 401 页只淘汰自身最老值，shard 已满只拒绝 contender，不跨 owner 淘汰。winner replay、过期/缺失清理及并发创建后的 index/metadata/value 数量与 bytes 精确一致且无孤儿。
- AND `RankedFeedWindow`、`FeedDeliveryPage` value/index/metadata 全部使用无协议版本前缀的 canonical quota-shard key 并位于同一 slot；脚本可访问 key 集合和索引读取量保持固定硬界，payload/cursor 不含 schema-version 信封，运行时不存在第二读取轨。

<a id="gwt-002"></a>
### GWT-002 持续滚动与频道切换保持稳定内存

- GIVEN 用户在四个频道长时间滚动、回滑、刷新和切换，并发生翻页失败与内存压力。
- WHEN App 持续续接 feed 并回收非活跃资源。
- THEN 列表、去重集、频道状态、图片字节和定时器保持在声明上限内，滚动锚点与既有内容不丢失。
- AND 首屏、刷新和翻页的取消/失败互不污染，旧 generation 不回写。
- AND 越过 6 页本地保留边界后可用 previous cursor 原序回到已交付页，再向下时先恢复 trailing、后按原 outbound cursor 访问被淘汰页；全程不重新召回历史页。

<a id="gwt-003"></a>
### GWT-003 视频 N+1 预热不抢占当前播放

- GIVEN 当前视频正在准备或播放，下一项可预热，且解码槽位、网络或内存发生变化。
- WHEN 用户前后翻页、改变方向、切集、离开或重试。
- THEN 只有当前项和 N+1 使用共享槽位，当前项优先，N+1 不自动播放并可立即取消，6 秒后均进入成功或恢复组终态。
- AND HLS/CMAF 只在 descriptor、capability 和 feature flag 同时成立时使用，否则同源回退 P0 progressive MP4。

<a id="gwt-004"></a>
### GWT-004 弱网与依赖故障进入有界终态

- GIVEN feed、Redis、Mongo、媒体 origin 或 realtime 依赖发生超时、限流、部分失败或断网。
- WHEN App 在首屏、翻页、前后台恢复或离线重入中处理该故障。
- THEN 重试、退避、fanout、并发与缓存使用都不超过 contract/config 预算，并返回 canonical failure、合法降级或可见的 stale snapshot。
- AND 不出现无限 spinner、空白伪成功、请求风暴或无活动订阅轮询。
- AND quota owner 淘汰、shard key 拒绝、shard byte 拒绝、repair 拒绝分别进入闭集指标与告警；无效/溢出配置阻止服务启动，拒绝路径不把其他 owner 数据或 Redis `maxmemory` 淘汰包装成成功。
- AND path-versioned public slice 的 query-free HEAD/Range 共享同一 path cache identity、长期 immutable 与 CORS；任何 signed、冗余 query、unversioned 或 private media 均为 no-store 且不返回 public cache key，四环境不得另造缓存规则。
- AND 超过 canonical 逐字段 UTF-8 字节上限的 Post 在 QuerySnapshot 写盘前被拒绝，既不落盘也不在下次冷启动恢复，不得靠整页 2 MiB 聚合预算兜底放行。

<a id="gwt-005"></a>
### GWT-005 长会话不累积无界状态

- GIVEN App 连续运行多小时并经历曝光、fallback、访问、token 刷新、realtime 断线和内存压力。
- WHEN 会话越过各集合 TTL/LRU/window 边界或 App 恢复前台。
- THEN 集合、controller、订阅和非活跃频道被回收，token/realtime 从权威状态恢复，当前内容与滚动锚点仍可用。

<a id="gwt-006"></a>
### GWT-006 性能与可用性证据可重放且有分母

- GIVEN 同一候选版本在受控正常/弱网、并发峰值、长滚动和视频播放场景中运行。
- WHEN product-ops 收集 typed feed/frame/media/cache/ANR/memory 事件并派生 SLO/告警。
- THEN 成功、失败和清洁样本均可读回，每个比率有真实分母，维度低基数且无对象级 PII/高基数。
- AND 端侧、服务端、真机与环境证据均能重放同一可观察结果；真机、四环境或真实 Provider 证据缺失时结果保持 `GATE_BLOCK`。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 P0 feed 服务端读路径与依赖成本闭环

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺同一候选版本在目标 Redis Cluster 的物理容量校准、受控发布与回滚演练、Prometheus/Alertmanager/Grafana readback，以及默认 8 页冻结深度的产品长滚动定标。受管单机环境输入只能校准容量假设，不能证明生产容量或替代业务准入上限。
- 完成判定：alpha/beta/gamma/prod 对同一 release digest 留存 Redis cluster topology/容量余量、`GWT-001` 的 canonical key/pipeline 实际 readback、受控发布与回滚、`GWT-004` 的四类 quota 指标/告警/看板 readback；默认冻结深度经产品长滚动场景验证且拒绝率满足 SLO。任一环境缺证时继续 `GATE_BLOCK`。

<a id="open-002"></a>
### OPEN-002 P0 App 长滚动、媒体预热与 typed 遥测闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺真机长滚动像素/QoE、trim 后跨 surface 互动/viewer 组合证据和同候选版本 product-ops readback，因此本 OPEN 继续阻断 READY。typed 首屏/翻页、清洁/卡顿帧批次、图片缓存、视频 controller/队列与 QoE、ANR/内存压力的生产 reporter 已接入；真实生产滚动容器已由 Provider 驱动 8 页并实际越过 6 页 retained 边界，相关 Provider/Widget local_contract 已通过。超出 retained 页后的稳定远端反向回补已落地。content-service 在返回 next cursor 前原子追加 `FeedDeliveryPage`，下一页返回 previous cursor 与 `paginationExpiresAt`。AEAD scope 已绑定 `pageSize`，回放不调用 recall/list，只原序 bulk hydrate 当前可见 Post，删除项不补位，对象卡使用已交付快照重基准。App 的 4 页 resident/6 页 retained deque 在 leading 耗尽后以独立 prepend generation 回取，远端页只与 retained identity 去重。QuerySnapshot 持久化 previous/next/expiry/session，过期或跨 session 仅回显内容。Contract decoder 强制 cursor 与 expiry 成对，append 也会在用户动作入口从 resident window 重读 live cursor，长时间空闲后不会发送状态快照里的过期 continuation。六页边界回退再前进、删除缩页、篡改/跨 actor/session/route/pageSize、原子 quota/payload/TTL 均有 local_contract。
- 当前边界：首页 `GetFeed` operation 已声明 default/max=20 与 2 MiB live response admission，ContractGraph 已生成到服务 binder、App policy 与 transport；stream chunk 越界在完整缓冲/JSON decode 前取消。成功与非 2xx JSON 共用有界 decoder，logical active、不可取消 physical work、pending task 与 queued bytes 分别有硬限。非 generated JSON verbs 不属于本 Story 的首页主链，但其治理仍由 runtime-client-foundation 跟踪。
- 完成判定：`GWT-002`、`GWT-003` 与 `GWT-006` 的窗口/锚点 local_contract、长滚动 widget 及 product-ops readback 证据通过。

<a id="open-003"></a>
### OPEN-003 P0 public media 缓存与四环境交付语义对齐

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺同一 release 在本地 origin、CDN 和 prod-hosted 的 Range/MIME/CORS/cache-control/cache-key 实际 readback，不能由本地单测替代；public path-versioned slice 的长期 immutable 与非 public/signed/unversioned 的 no-store 策略已落地。
- 完成判定：环境 inspect 与 media Range/readback UAT 直接引用 `GWT-004`，并绑定同一 release digest。

<a id="open-004"></a>
### OPEN-004 P1 弱网、峰值、长会话与 cloud governance 闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺目标环境的绕过检查、Redis/Mongo 故障注入和同 release 峰值/长会话压力 readback，当前 per-instance operation admission 也不能冒充环境级网关治理。api-edge 复用同一 Redis Lua 的 stable/gray 双副本主体/operation 原子限流、canonical 429/retry 与 TTL api_integration 已通过。viewer/visit/频道/session 状态预算、App operation retry/deadline/cancel、服务端 generated deadline、模型 timeout/circuit fallback、feed operation rate/inflight admission、曝光/fallback/行为窗口、token proactive refresh singleflight 与 realtime 全抖动恢复已闭环，媒体上传恢复也已改为有界全抖动。recall deadline 已改为 orchestrator 强制终态，不再等待忽略 context 的 source。每 source 迟到调用由 canonical feed max_inflight 限制。超量 source 只复制主窗口，active-release handoff 也只检查第二个同尺寸窗口，总扫描上限为 `2 * RecallRequest.limit`，每 32 项检查 context 并保留 budget failure。
- 完成判定：`GWT-004` 与 `GWT-005` 的 fault injection、api_integration 和 user_acceptance 通过。

<a id="open-005"></a>
### OPEN-005 P2 离线持久 feed、HLS/CMAF ABR 与网关统一治理组合验收

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍缺无网重启、主动 LRU/TTL 与真机磁盘压力组合证据。单 snapshot 内 Post 字段级 canonical UTF-8 byte admission 已由 `REQ-003 / GWT-004` 接管：限额表经 codegen 从 Post `fields.yaml` 与 discovery feed projection 的 `max_utf8_bytes` 派生并已落盘（`postId=256`、`authorId=128`、`title=320`），超限字段在写盘前被拒绝；整页 2 MiB payload 预算仍在编码调度前 fail-closed。长窗口双向续填、cursor session/expiry 约束和主动 expiry 已闭环：QuerySnapshot `freshFor=5m`、最大可恢复 24 小时，超过 24 小时在内存读取和持久恢复时删除。分页 cursor 只有在同 session 且 `paginationExpiresAt` 尚未到期时才可复用。四环境启用、CDN/弱网/真机 ABR、网关压力组合证据仍须以当前候选版本验证。QuerySnapshot 继续提供首屏 cache-first SWR、续页 remote-first 失败回退、从首屏 cursor 连续可达的最多 4 页离线链，以及 2 MiB UTF-8 persisted payload 硬限。写入按完整 snapshot/page 原子选择，首页连续链优先，单 active drain 合并并发变更并保证最新状态最终落盘。整页编码先用无输出有界 writer 精确预检，再逐字段、逐 item 写最终 payload，字符串临时分块为 1024 code units，因此不先物化整页 Map/List/局部 JSON String，超预算时保持 page/cursor 原子。HLS/CMAF 与物理命令 admission 的既有边界不变。
- 完成判定：`GWT-003` 与 `GWT-004` 对应三层证据通过，且不新建第二套实现。

<a id="open-006"></a>
### OPEN-006 候选版本真机长滚动、弱网、峰值与四环境 Exit Report

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：需同一候选版本的 iOS/Android 真机长滚动/Android Perfetto/iOS performance trace、受控弱网、并发峰值、长会话与 alpha/beta/gamma/prod Remote readback。本地或模拟结果不得代替。当前工作机只有 Android emulator、iOS Simulator、macOS 与 Chrome，没有 Android/iPhone 物理设备。当前两份首页推荐/视频 Patrol user_acceptance 入口可加载，但未启用真实 T4 时 7 个场景全部 `skip`，退出码 0 不得记为 UAT 通过。性能门禁现已对 release/commit/device/platform、样本/分子分母、build/raster、内存、controller/队列、媒体 QoE 与双端物理证据 fail-closed，缺候选证据不能再以文件存在或源码断言空通过。
- 完成判定：`GWT-006` 的 local_contract、api_integration、user_acceptance、SLO/readback 与回滚证据绑定同一 release digest，Exit Report 无未解释性能阻断。
