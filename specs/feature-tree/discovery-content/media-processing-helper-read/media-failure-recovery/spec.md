# L3 Story：媒体处理失败恢复 (`media-failure-recovery`)

> 所属能力：[`media-processing-helper-read`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-002`](../../../spec.md#scn-002)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望媒体处理基础设施重试、内容性拒绝、checkpoint 重放与端侧发布排队语义，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- worker checkpoint、幂等重放、rejected 终态、media_not_ready 与 reauthenticate 恢复动作。
- checkpoint、重放、dead letter、health、Prometheus 指标与告警。

### Out of Scope

- 用户主动删除资产的产品入口。
- 独立媒体服务部署。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 媒体处理故障不丢事实且不会误发布

- checkpoint 保存失败后重放同一事实只产生一个有效 ready 结果。
- 非媒体字节进入 rejected 且没有公开主 slice。
- media_not_ready 自动排队，未授权永久阻断并要求重新认证。

<a id="req-002"></a>
### REQ-002 无视频流、不可解码或违反媒体约束属于内容性失败：幂等写入 rejected 与稳定原因

- 无视频流、不可解码或违反媒体约束属于内容性失败：幂等写入 `rejected` 与稳定原因。

<a id="req-003"></a>
### REQ-003 Worker 故障与回滚不丢事件、不破坏已发布媒体

- 故障注入证明首次 checkpoint 失败后第二次处理成功。
- poison event 只记录 source identity、cursor 与原因，不记录原始 payload；成功隔离后 后续事实继续处理，隔离写入失败时 checkpoint 不推进。
- health、jobs（按 media_type/input_size_class/result）、处理时长、complete-to-ready、 outbox oldest-event age、DLQ 准入年龄、扫描批量、连续满批和 poison event 有自动化断言。
- 回滚流程不把 processing 强改 ready，不删除已发布版本 slice。

<a id="req-004"></a>
### REQ-004 FFmpeg/对象存储不可用时禁止降级为原始字节或伪造 ready

- FFmpeg/对象存储不可用时禁止降级为原始字节或伪造 ready。
- 带有效 cursor 的损坏 outbox 记录必须先写入 durable dead letter，确认隔离事实持久化后才能推进 checkpoint。
- 告警覆盖 Worker 不可用、任务失败、连续满批和 poison event；死信不包含原始 payload。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/errors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml`
- canonical：`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 媒体处理故障不丢事实且不会误发布

- GIVEN outbox 中存在尚未完成的媒体创建事实。
- WHEN checkpoint 持久化、对象存储或媒体内容发生故障。
- THEN 基础设施故障保留可重放事实，内容性故障进入 rejected，发布请求按 metadata 恢复动作处理。

<a id="gwt-002"></a>
### GWT-002 Worker 故障与回滚不丢事件、不破坏已发布媒体

- GIVEN outbox 存在待处理事实且 Worker 使用持久 checkpoint。
- WHEN checkpoint 保存失败、Worker 重启、损坏 outbox 事实或发布版本回滚。
- THEN 正常事实可重放，损坏且带 cursor 的事实会被幂等隔离，派生物按版本保留，已发布 Post 继续可读。

## 6. 依赖

- 前置要求：[`media-processing-helper-read`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 媒体处理故障不丢事实且不会误发布

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：checkpoint 保存失败后重放同一事实只产生一个有效 ready 结果。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 Worker 故障与回滚不丢事件、不破坏已发布媒体

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：故障注入证明首次 checkpoint 失败后第二次处理成功。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
