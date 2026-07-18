# L2 特性：event-ingestion-and-analytics

## 目标与用户价值

把 App 产品事件和异常从采集、批量上报、云端明细、小时聚合到 Portal 查询收敛为一条
可验证的单轨链路；推荐反馈继续走 `/content/behaviors`，启动阶段诊断继续走受限
`/ops/startup-events`。产品、运营和运维由此获得一致口径，用户获得可定位、可恢复且不会
泄露身份的体验。

AppRoot Journey/Scenario：

- `cold-start-safe-handoff-and-telemetry`
- 统一页面访问旅程
- 内容发现、消费、反馈、推荐生效旅程

## In Scope

- 九字段公共事件信封、严格事件目录和强类型扩展。
- 会话、页面、设备、版本和网络上下文；actor-scoped 加密 outbox。
- `/ops/events` 的 canonical-body SHA-256 幂等批次与全有或全无 ACK。
- 产品事件/异常与启动诊断分别写入三天 SLS Logstore；无身份小时聚合保留 90 天。
- product-ops 的 summary/drilldown 查询门面及 Portal 应用。
- `/content/behaviors`、内容业务命令、Redis HotPath、`rm_behavior_events`、推荐投影与指标的独立闭环。
- `local_contract / api_integration / user_acceptance` 三层证据及 alpha/beta/gamma/prod 发布门。

## Out of Scope

- ClickHouse、Elasticsearch、Kafka/RocketMQ、对象存储日志归档。
- Assistant 学习协议并入运营日志。
- 修改 `visit_record` 业务事实及 Mongo 存储。
- 将推荐热状态迁移出 Redis。

## 公共事件契约

公共 wire 信封固定为九个必填字段：

```text
logType,eventType,sessionId,pageName,occurredAt,
deviceManufacturer,deviceModel,appVersion,networkClass
```

- `logType` 仅允许 `event | error`；`eventType` 是唯一语义键，不存在 `eventName`。
- `networkClass` 仅允许 `wifi | ethernet | 5g | 4g | mobile | other | none`；不得上报 `vpn`、
  `lte`、`nr`、`offline` 或其他别名。
- `connectivity_plus` 负责识别 Wi‑Fi、有线、蜂窝、无网络和其他底层接入；VPN 只是覆盖层，
  必须忽略并上报同批可见的底层接入。仅有 VPN 而无法识别底层时上报 `other`。
- 已确认蜂窝接入时，平台防腐层可将 Android/iOS 原生蜂窝代际细化为 `5g` 或 `4g`；
  无授权、未知、2G/3G 或不支持平台必须诚实降级为 `mobile`，不得推断 5G。
- `ops/event_record/event_catalog.yaml` 是事件、强类型扩展、采样率、慢阈值和内部优先级唯一真相源。
- `_shared/app_pages.yaml` 是 pageName、GoRouter、内部 Navigator 页面和采集开关唯一真相源。
- 不允许自由 `properties/payload/metrics`。通用扩展为 `durationMs/result/failReasonCode`；
  `app_startup` 固定四段耗时和 `hasError`；异常至少含 `errorCode`。
- `callStack` 只保存脱敏方法名，最多十层、单层最多 256 字符，不建全文索引。
- `occurredAt` 只接受当前时间前 72 小时至未来 5 分钟。

## 会话与页面身份

```text
sessionId = s.{base64urlWithoutPadding(reversibleUserKey)}.{sessionStartMs}
```

- 登录主体使用真实账号用户键做可逆 URL-safe 编码；游客使用安全持久化的 `guest_<ULID>`，禁止硬件标识。
- 从最后一个 `.` 拆分时间戳；同毫秒重建以单调 `+1ms` 校正。
- `inactive` 不结束会话；`paused/hidden/detached` 结束；下一次 `resumed` 新建。
- 登录、登出、账号切换立即结束旧会话。旧 actor outbox 只允许限时刷新后删除，绝不重绑新账号。
- `sessionId` 为 `SENSITIVE`：原始明细三天、Portal 默认掩码、完整值查询需高权限与审计，
  且不得进入 Prometheus label。
- 导航 observer、底栏和全屏模态统一写 `AppPageContextStore`；无页面异常使用
  `app_bootstrap` 或 `app_background`。

## 入口、ACK 与失败语义

### `POST /ops/events`

- 要求已验证 persona 或 device actor；匿名请求拒绝。
- 每批最多 50 条、canonical JSON 最大 128 KiB。
- `Idempotency-Key` 必须等于 canonical 请求体 SHA-256；无逐事件 `eventId`。
- 服务端重算摘要；同一密封批次重试返回相同 acceptedCount 与 `duplicateBatch=true`。
- SLS 内部写 `_batchKey/_batchIndex/ingestedAt`，不进入公共 API；明细/聚合按
  `_batchKey + _batchIndex` 去重。
- 当前官方 Go SDK 不暴露 PutLogs sequence-id 参数，因此生产实现不虚构该能力；
  API 幂等由 Redis 批次状态、`_batchKey` 查询确认和查询/聚合去重共同保证，协议测试必须覆盖
  “超时但已写入”。
- `400/422` 进入本地加密死信；`401/403` 保留到主体变化；`429/5xx/网络错误` 重试。

### `POST /ops/startup-events`

- 唯一匿名 Ops 入口；只接受现有固定 phase、脱敏字段与 startup proof。
- 禁止 `sessionId/userId/pageName/callStack` 等产品或身份字段。
- 阶段 journal 只用于可靠性诊断；内容可交互后由普通 Reporter 另发 `app_startup`。

### Portal 查询门面

- `/ops/events/summary` 读取闭合小时聚合。
- `/ops/events/drilldown` 读取三天内原始明细；时间范围必填，最多 100 条。
- 响应携带 `source=sls_aggregate|sls_raw`、freshness 与实际窗口。
- 浏览器不持有 SLS 凭据，也不直接访问阿里云接口。

## App 采集与交付策略

- `AppTelemetrySessionStore`：actor、生命周期状态机和会话广播。
- `AppTelemetryContextProvider`：静态设备上下文、网络监听和当前页面。
- `CellularNetworkProbe`：只在网络 transport 为 mobile 时读取 Android Telephony / iOS
  CoreTelephony 代际；缺 `READ_PHONE_STATE` 授权不弹启动权限框，返回 unknown 并由
  ContextProvider 降级为 `mobile`。
- `AppTelemetryOutbox`：actor-scoped 加密队列、密封批次、单飞、ACK 删除与死信。
- `AppTelemetryReporter`：目录校验、上下文组装、稳定采样、限流和入队。
- 事件每 10 秒或 50 条刷新，异常最多等待 1 秒；单一 in-flight，重试期间 body/digest 不变。
- outbox 上限 1000 条或 2 MiB；event TTL 24h、error TTL 72h。
- event 120/min burst 50；error 20/min burst 10；full-jitter 1s 起、5min 封顶，网络恢复立即尝试。
- 队列满先删最旧普通采样事件；异常仅在普通事件清完后进入加密死信，禁止静默丢弃。
- `app_startup`、页面、关键转化和异常全量；启动的 `hasError` 与 3000ms 阈值只用于聚合分析和告警，不参与端侧采样。其他正常性能事件按 session 稳定采样 10%，慢/失败全量。
- cache/debug、成功 HTTP 明细、正常资源快照、成功重试细节和 AppLog 不自动上云。

## 存储、聚合与应用

- `app-product-telemetry-raw`：产品事件/异常，TTL 3 天。
- `app-startup-diagnostic-raw`：受限启动阶段事实，TTL 3 天。
- `app-product-telemetry-hourly`：无身份小时增量聚合，TTL 90 天。
- SLS `__time__` 使用服务端 `ingestedAt`，业务时间保存在 `occurredAt`。
- 小时 Scheduled SQL 延迟 120 秒，按接收窗口处理并按业务小时输出增量；Portal 汇总迟到增量。
- 页面/事件、性能分位数/启动错误率、异常 TopN 三类聚合均不得包含 session/user。

## 推荐反馈边界

- `behaviors.yaml` 与 `/content/behaviors` 是推荐信号唯一入口，绝不占用 `logType`。
- App 网络出口统一为 `BehaviorReporter`；Engagement tracker 只做计算并调用该端口。
- like/comment/report 等专用命令成功后由 content-service 事务 outbox 投影一次
  canonical `BehaviorSignal`，App 不补发第二条。
- content-service 只发布 `BehaviorBatchReported`；推荐、曝光和搜索投影只消费该事件。
- `rm_behavior_events` 保留 30 天作为足迹/推荐业务投影，不迁移 SLS。

## SLI/SLO、环境与回滚

- ingest 成功/拒绝/重复/限流，SLS 写入耗时/错误率，raw/aggregate 查询耗时，
  Scheduled SQL failure/freshness 均有低基数指标和告警。
- Portal summary P95 ≤ 2s，drilldown P95 ≤ 3s；异常 1min 内可见，小时聚合整点后 10min 内可见。
- alpha 用协议模拟器；beta 验证真实 SLS；gamma 做端到端 UAT；prod 采用 5%→25%→50%→100%，
  不存在 `prod-gray`。
- 不双写、不保留 Mongo/ES fallback。回滚只回退 App/服务制品；SLS 资源保留，App 继续加密排队。
- 缺真实 SLS、gamma 或真机证据时 acceptance 必须保持 `partial/GATE_BLOCK`。
