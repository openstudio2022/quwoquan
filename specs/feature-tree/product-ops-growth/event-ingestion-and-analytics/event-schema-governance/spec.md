# L3 Story：event-schema-governance

## 功能说明

冻结产品事件与异常的九字段公共信封、强类型扩展目录、页面身份目录、批次幂等、采样、背压、
隐私和留存规则。唯一真相源为：

- `quwoquan_service/contracts/metadata/ops/event_record/event_catalog.yaml`
- `quwoquan_service/contracts/metadata/_shared/app_pages.yaml`
- `quwoquan_service/contracts/metadata/ops/event_record/fields.yaml`

## 公共信封

`logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass`
九字段全部必填。`logType` 只允许 `event/error`，`networkClass` 只允许
`wifi/ethernet/5g/4g/mobile/other/none` 七枚举，`eventType` 是唯一语义键。

`vpn` 不属于 wire 枚举：它是覆盖于 Wi‑Fi、有线或蜂窝之上的隧道。端侧必须忽略
`ConnectivityResult.vpn` 并上报底层接入；仅报告 VPN 而没有底层接入时使用 `other`。
蜂窝只有在原生 probe 明确返回 NR 或 LTE 时才写 `5g` 或 `4g`；未授权、2G/3G、未知和
不支持平台统一写 `mobile`。服务端、App codegen、Portal codegen 与 SLS 查询筛选必须拒绝
`vpn/lte/nr/offline` 等非 canonical 值。

不允许 `eventId/eventName/eventVersion/priority/producer/userIdHash/surfaceId/properties/payload/metrics`
等公共或自由字段。每个 eventType 必须在目录声明 required/optional 强类型扩展、正常采样率、慢阈值和
端侧内部优先级。

`app_startup` 当前固定 `normal_sample_rate: 1.0`，正常、慢启动和 `hasError=true` 均全量采集；
`slow_threshold_ms: 3000` 仅作为聚合、看板和告警分类阈值，不得影响是否入队。

App 体验事件固定为三条独立事实，均全量采集且不得由自由 Map 代替：

- `app_anr_outcome`：Dart event-loop watchdog 的本次 stall，或 Android
  `ApplicationExitInfo` / iOS MetricKit 在下次安全启动补报的上一进程 hang；200ms
  severe frame 仍只是 jank，不得冒充 ANR。
- `page_first_usable`：`navigation_start → first_usable_content`，并以
  `terminalState=content|empty|error` 明确结算；`page_open.readyMs` 只表示路由首帧。
- `page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`，
  必须带受控 `surfaceId/errorCode/recoveryAction`。

## 幂等与时间

- 事件不生成逐条 ID；每个密封批次以 canonical JSON SHA-256 作为 `Idempotency-Key`。
- 重试期间 body、顺序和 digest 不得变化；服务端重算摘要并全批校验。
- 内部 `_batchKey/_batchIndex` 只用于 SLS 完整性确认和查询/聚合去重，不进入公共 API。
- `occurredAt` 只接受过去 72h 至未来 5min；SLS `__time__` 使用服务端 ingestedAt。

## 隐私与生命周期

- sessionId 为可逆账号用户键会话标识，必须按 `SENSITIVE` 管理：raw 3d、Portal 默认掩码、完整查询审计。
- callStack 只允许方法名数组，最多十层、单层 256 字符；禁止路径、token、用户输入，且不建全文索引。
- raw 产品/异常与启动诊断保留 3d；无身份小时聚合保留 90d；不做对象存储长期归档。
- 本地 AppLog/debug/cache/success HTTP 不自动上云。

## 单轨约束

- product-ops 日志只写 SLS，不写 Mongo、不镜像 Elasticsearch、不发推荐/Assistant 领域事件。
- 推荐反馈只走 behaviors.yaml、`/content/behaviors` 或专用业务命令的事务 outbox。
- 不提供 eventVersion 兼容、旧键双读、双写、fallback 或 warn-only 逃逸。

## 验收标准

- App/Go/Portal 目录产物由同一 metadata 生成且二次 codegen 无漂移。
- App 本地和服务端都拒绝未知事件、未知扩展、非法枚举、越界时间与超限批次。
- `wifi+vpn`、`ethernet+vpn` 与 `mobile+vpn` 分别归一为底层 `wifi`、`ethernet` 与
  `5g/4g/mobile`；仅 VPN 为 `other`，`vpn` 入站必须被拒绝。
- 相同 canonical batch 重放只形成一批 raw 事实并返回 duplicateBatch。
- `/ops/startup-events` 拒绝产品/身份字段，且匿名 `/ops/events` 始终 401。
- ANR 原生事实采用 `read → 产品 outbox accepted → acknowledge` 两阶段转存；入队拒绝或异常时
  必须保留原生标记供下次启动重试，确认后不得重复补报。Dart watchdog 在 10 秒窗口内去重；
  页面 TTI 每个 visit 只接受首个明确终态；统一错误面展示和恢复动作产生可关联 outcome。
- 缺真实 SLS/gamma/真机证据时状态保持 partial。
