# L3 Story：跨域会话疲劳记忆 (`cross-session-fatigue-memory`)

> 所属能力：[`exposure-governance`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “跨域会话疲劳记忆”的输入、可观察主路径、失败语义以及与父能力的交接。
- per-user impressed 窗口。
- 时间衰减疲劳惩罚。
- 强负反馈优先级。
- P0 不引入 Bloom/Cuckoo 或精确 Sorted Set；先用 user+day bucket 与候选 membership 点查闭合中小规模容量路径。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 跨域会话疲劳记忆

- 过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。

<a id="req-002"></a>
### REQ-002 过滤路径用 membership 点查或近似结构，禁止长窗口全量 SMembers

- 过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 跨域会话疲劳记忆

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“跨域会话疲劳记忆”对应的公开行为。
- THEN 过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`exposure-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 跨域会话疲劳记忆 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“跨域会话疲劳记忆”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
