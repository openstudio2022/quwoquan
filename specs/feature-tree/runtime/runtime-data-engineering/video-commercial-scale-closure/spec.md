# L3 Story：视频商用规模闭环 (`video-commercial-scale-closure`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望通用真实源视频归因、媒体包与环境消费者闭环验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- source admission、asset rights、attribution、takedown 与审计
- download、transcode、poster、subtitle、checksum、provenance
- request 驱动的 release、playback、rollback/replay 与 capacity receipt

### Out of Scope

- 静态区域、目标对象、数量或阶段清单
- 绕过访问控制、去水印或将下载能力冒充商业授权

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 sourced video preserves rights and attribution facts

- 不满足 admission 的候选以 typed issue 阻断。
- 匿名公开 HTTPS 下载只记录候选字节、受限响应头、重定向链、checksum 与无凭证断言；下载成功、可播放或画质合格均只能是 `unverified`，不得替代对象级 commercial admission。
- 下载器不得持有账号、Cookie 会话或 API 凭证，不得绕过访问控制、DRM、robots 或水印；出现非 HTTPS 重定向、访问控制或水印时写 typed rejection。

<a id="req-002"></a>
### REQ-002 media package and attribution reach consumers unchanged

- 数据、服务、App 不维护第二套 attribution 字段。

<a id="req-003"></a>
### REQ-003 video release and capacity conclusions use immutable receipts

- 容量与预算结论只读取真实 receipt，未执行不冒充完成。
- M100/M1000 的 video workload target 分别为 10/100；quota/count 只表达请求负载与里程碑目标，不是发布门。每个 hard-qualified 视频均须发布，shortfall 和带 typed issues 的 discard 不否决其它合格视频。
- receipt 必须记录 target/selected/qualified/finalized/discarded/shortfall，以及 object pass、automatic recovery、first-pass、discard 与 quota attainment 的清晰分子、分母和 rate；这些统计不参与对象发布或 `m1000Eligible`。
- travel/video M1000 只接受精确绑定的 travel/video M100 promotion receipt；receipt 必须与当前 release/manifest、source revision/digest、entity catalog digest、冻结模型绑定、对象级 review/rights/provenance/安全/可播放闭包与 canonical publish receipt 一致。身份、对象硬门或 receipt 缺失 fail closed，partial/shortfall 本身不阻断。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/schema/source`
- canonical：`quwoquan_data/scripts/content/post/video`
- canonical：`quwoquan_service/services/content-service/contracts`
- canonical：`quwoquan_data/scripts/content/release`
- canonical：`quwoquan_ops/environments`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 sourced video preserves rights and attribution facts

- GIVEN provider policy 把平台能力和 publication admission 明确区分。
- WHEN 一个视频候选请求进入发布。
- THEN 原创者、source post、原始资产、rights、风险与 takedown 事实都在对象级证据中保留。
- THEN 无商业授权不能被标成 licensed 或 commercially-cleared。
- THEN 匿名下载证据可复核其无凭证访问、最终 HTTPS URL、重定向和字节 checksum，但候选在 admission 通过前仍不可 render 或 publish。

<a id="gwt-002"></a>
### GWT-002 media package and attribution reach consumers unchanged

- GIVEN 视频已通过 source admission。
- WHEN materialize/package、canonical promotion 与 importer 执行。
- THEN H.264、poster、字幕、checksum、provenance 与 attribution 通过 metadata 同源进入服务和 App。
- THEN 播放、错误恢复、投诉和下架链路都能关联同一媒体对象。

<a id="gwt-003"></a>
### GWT-003 video release and capacity conclusions use immutable receipts

- GIVEN execution request、runtime policy、source digest 和对象存储能力已冻结。
- WHEN execution 形成 release 并通过对应 environment profile。
- THEN import、API、播放、rollback/replay、成本与 QoE 证据绑定同一 release digest。
- THEN 缺 commercial profile 依赖时返回 GATE_BLOCK，不影响 baseline 或 integration 数据面验证。
- THEN 每个 qualified 视频均 finalize；target shortfall 与 typed discard 只进入 receipt，各 rate 明确分子/分母且不参与 promotion 判定。
- THEN 请求 M1000 时，缺精确 M100 promotion receipt、receipt digest/冻结输入漂移、任一对象未达到 review/rights/provenance/安全/可播放与 publish closure 均返回 GATE_BLOCK；未命中 `10/100` target 或比率阈值不构成该阻断。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 sourced video preserves rights and attribution facts

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：不满足 admission 的候选以 typed issue 阻断。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 media package and attribution reach consumers unchanged

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：数据、服务、App 不维护第二套 attribution 字段。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 video release and capacity conclusions use immutable receipts

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：容量与预算结论只读取真实 receipt，未执行不冒充完成。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
