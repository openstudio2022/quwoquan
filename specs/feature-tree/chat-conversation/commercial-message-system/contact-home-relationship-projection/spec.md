# L3 Story：联系首页关系投影 (`contact-home-relationship-projection`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望联系首页 read model 与交集摘要字段均有稳定契约来源，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “联系首页关系投影”的输入、可观察主路径、失败语义以及与父能力的交接。
- 消息首页通知筛选。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 联系首页关系投影

- 联系首页 read model 与交集摘要字段均有稳定契约来源。

<a id="req-002"></a>
### REQ-002 联系首页关系投影与交集摘要契约一致

- 联系首页 read model 与交集摘要字段均有稳定契约来源。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 联系首页关系投影

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“联系首页关系投影”对应的公开行为。
- THEN 联系首页 read model 与交集摘要字段均有稳定契约来源。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 联系首页关系、圈子、群和交集由真实聚合驱动

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：联系首页的各类关系视图都可映射到真实 projection 和交集契约。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 联系首页关系投影与交集摘要契约一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：联系首页 read model 与交集摘要字段均有稳定契约来源。
- 完成判定：联系首页 read model 与交集摘要字段均有稳定契约来源。
