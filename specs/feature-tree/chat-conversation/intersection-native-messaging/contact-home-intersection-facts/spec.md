# L3 Story：联系首页真实交集 (`contact-home-intersection-facts`)

> 所属能力：[`intersection-native-messaging`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为翻看联系人的用户，
我希望每个人下面写的是我和他真实的共同点，
从而在想找人说话时知道该找谁、聊什么。

## 2. 范围与非目标

### In Scope

- 联系首页用户行的交集聚合来源与展示上限。
- 圈子行与群组行的展示口径。
- 无交集时的降级展示。

### Out of Scope

- 消息首页展示：消息首页不叠加交集行。
- 交集事实的识别与排序，由 `object-homepage-network` 负责。
- 联系首页的信息架构与索引，由 `commercial-message-system` 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 交集摘要必须来自真实交集聚合

- 用户行的交集摘要必须来自真实交集聚合结果；不得由资料字段拼接产生。

<a id="req-002"></a>
### REQ-002 展示具体交集点且有上限

- 摘要最多展示两个具体交集点；不得以聚合计数表述代替具体内容。

<a id="req-003"></a>
### REQ-003 圈子与群组行不展示裸标识

- 圈子行与群组行不得拼接内部标识作为摘要；无可展示内容时该行不展示摘要而不是展示空串或标识。

<a id="req-004"></a>
### REQ-004 无交集时干净降级

- 双方无成立交集时该行不展示交集摘要，也不展示占位文案。

<a id="req-005"></a>
### REQ-005 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/contact_home_row.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_action_hint.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 有交集时展示具体交集点

- GIVEN 当前用户与某联系人之间存在成立的交集。
- WHEN 用户打开联系首页。
- THEN 该联系人行展示最多两个具体交集点，内容整体来自云侧。
- AND 不出现聚合计数式表述。

<a id="gwt-002"></a>
### GWT-002 无交集与非用户行干净降级

- GIVEN 某联系人与当前用户无成立交集，且列表中同时存在圈子行与群组行。
- WHEN 用户打开联系首页。
- THEN 该联系人行不展示交集摘要，圈子行与群组行不展示任何内部标识。
- AND 不展示占位文案。

## 6. 依赖

- 前置要求：[`intersection-native-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-003](../design.md#dec-003)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实交集摘要尚缺环境消费证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 alpha/beta/gamma 真实身份、真实交集数据和页面 UAT readback；Chat 已通过 delegated persona 调用 content 的公开对象交集 Reader，并投影最多两个 typed summary，App 用户行只消费该摘要，圈子与群组行不再拼 raw id，本地契约已覆盖数量上限与 typed object identity。
- 完成判定：`GWT-001` 与 `GWT-002` 除本地契约外，取得至少一个非生产 Remote composition 的真实对象交集响应与 App 页面证据
