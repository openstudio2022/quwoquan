# L3 Story：运行前上下文装配与渠道边界 (`context-assembly-slot-filling`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为在页面、群聊和主动提醒中唤起小趣的同一个用户，我希望它自动带上当前对象、我与该对象的交集关系和必要的时间地点信息，只在真的缺信息时才问我；同时在群聊这类公开场合不泄露我的私人记忆。

## 2. 范围与非目标

### In Scope

- 运行前统一上下文装配结果
- 槽位状态与缺失槽位的填充任务
- 渠道差异的统一声明与公开场合记忆边界

### Out of Scope

- 页面上下文采集协议与端侧上报字段
- 交集事实的计算与排序
- 长期记忆的写入与撤销流程

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运行前产出统一上下文装配结果

- 每轮运行必须在调用模型前产出统一的上下文装配结果，包含可进入的领域、实时信息需求与可用地理范围。
- 装配结果必须只包含已通过授权校验的事实；页面对象与交集证据必须以当前发起者身份回查后才可进入提示与引用。
- 授权缺失或事实过期时必须降级为不注入该事实，不得注入陈旧副本或未授权内容。

<a id="req-002"></a>
### REQ-002 槽位缺失产出填充任务

- 装配必须输出槽位状态，区分缺失、推断、已确认、过期与冲突。
- 缺失且无法推断的必需槽位必须产出填充任务，交由编排决定反问还是使用默认值。
- 已由用户确认的槽位在同一会话内不得被重复询问。

<a id="req-003"></a>
### REQ-003 渠道差异由统一声明表达

- 个人会话、群聊提及与主动投递必须通过同一渠道抽象接入，各渠道只声明身份解析、上下文窗口、答案边界与记忆范围。
- 公开渠道的记忆范围不得包含发起者的私人长期记忆，也不得在回答中泄露非本渠道成员可见的事实。
- 新增渠道不得要求改动编排、技能选择或工具执行。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/context_assembly_result/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/slot_schema/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/context_fill_task/schema.yaml`
- error / recovery：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面唤起自动带入对象与交集事实

- GIVEN 用户在某个对象页唤起小趣且已授权读取当前页
- WHEN 用户就该对象提问
- THEN 上下文装配结果包含以当前发起者身份回查后的页面对象与交集事实
- THEN 授权缺失或事实过期时该事实不进入提示，且回答降级为不含该事实的通用回答
- THEN 缺失且无法推断的必需槽位产出填充任务

<a id="gwt-002"></a>
### GWT-002 群聊渠道不泄露提问者私人记忆

- GIVEN 用户在群聊中提及小趣，且该用户已有私人长期记忆事实
- WHEN 小趣在群聊内生成回答
- THEN 该渠道的记忆范围不包含发起者的私人长期记忆
- THEN 回答不包含非该群成员可见的事实
- THEN 同一用户在个人会话中提问时私人长期记忆仍然生效

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：页面上下文缓存、内容领域公开的交集事实、偏好与记忆事实。
- 下游结果：本 Story 声明的 GWT 可观察结果，供编排决策与技能执行消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

- 无。
