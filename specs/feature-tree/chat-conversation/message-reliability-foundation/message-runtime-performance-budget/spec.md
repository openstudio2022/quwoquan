# L3 Story：会话运行时性能预算 (`message-runtime-performance-budget`)

> 所属能力：[`message-reliability-foundation`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为在长会话里滚动和发消息的用户，
我希望打开会话、翻阅历史和发送消息的响应速度有明确上界并且不会随版本悄悄劣化，
从而在千条消息的群聊里仍然觉得应用是跟手的。

## 2. 范围与非目标

### In Scope

- 会话首帧、长列表滚动 jank 比、发送到气泡确认延迟与会话图片缓存字节上界的声明阈值。
- 阈值来源唯一性与门禁接线。
- 会话 surface 的客户端性能指标上报。

### Out of Scope

- 启动阶段性能预算，由既有启动预算负责。
- 服务端容量与扩缩策略，由父能力设计的质量与观测节负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 预算必须声明且进入门禁

- 会话首帧、长列表滚动 jank 比、发送到气泡确认延迟与会话图片缓存字节上界必须有声明阈值，并由既有性能门禁在合入前校验。
- 预算文件必须复用既有预算文件形状与既有门禁脚本，不得新造并行格式或并行脚本。
- 预算形状按证据等级分轨：测试环境 wall time 预算由测试树受版本控制的 `MessageRuntimePerformanceBudgets` 声明承载；真机棘轮预算沿用 `policies/gates` 既有 JSON 基线形状。图片缓存字节上界唯一复用 `AppResourceCacheProfile`，不另设第二份上限。

<a id="req-002"></a>
### REQ-002 阈值单一来源

- 服务端相关阈值必须复用所属 `operations.yaml` 的 `slo.latency_p95_ms`，不得在预算文件内另写一份服务端阈值。

<a id="req-003"></a>
### REQ-003 指标分母必须干净

- 滚动 jank 比必须以采样帧数为分母且与既有 feed 性能观测使用同一载荷形状；不得以不可比的分母产生看起来更好的比值。

<a id="req-004"></a>
### REQ-004 预算必须由运行时采样判定

- 预算是否满足必须由运行时采集的指标判定；仅检查代码结构而不采集运行时指标的静态断言不构成满足证据。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml`
- canonical：`quwoquan_ops/policies/gates/startup_ttid_ratchet_baseline.json`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 长会话滚动与发送在预算内

- GIVEN 一个已加载千条量级消息的会话。
- WHEN 用户连续滚动该会话并发送一条消息。
- THEN 滚动 jank 比与发送到气泡确认延迟均在声明预算内。
- AND 超出预算时门禁阻断合入而不是仅记录告警。

<a id="gwt-002"></a>
### GWT-002 会话首帧、资源上界与性能上报在预算内

- GIVEN 一个已加载千条量级消息的会话与声明的首帧/缓存预算。
- WHEN 用户打开该会话直至首条消息可见，且会话图片缓存被灌入超过声明上界的数据。
- THEN 打开会话到首条消息可见的耗时在声明预算内。
- AND 图片缓存实际字节经淘汰后不超过声明上界，上界唯一来源于既有资源缓存 profile。
- AND 会话首屏可用时向观测面上报一次性能采样，payload 与 telemetry 契约同源且同一次打开不重复上报。

## 6. 依赖

- 前置要求：[`message-reliability-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

当前无开放事项：滚动/发送、首帧、图片缓存上界与首屏性能上报均已由
`GWT-001` 与 `GWT-002` 的子句级真实测试闭合，预算形状分轨已由 REQ-001 裁决。
