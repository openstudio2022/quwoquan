# L3 Story：圈子流中的 post 虽已有部分进入媒体浏览器的路径 (`circle-feed-viewer-handoff-contract`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望圈子 post 进入 viewer 时必须传入，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “圈子流中的 post 虽已有部分进入媒体浏览器的路径”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 圈子流中的 post 虽已有部分进入媒体浏览器的路径

- 圈子 post 进入 viewer 时必须传入。

<a id="req-002"></a>
### REQ-002 文案、作者信息、来源上下文与 discovery 旅程未形成统一协议

- 文案、作者信息、来源上下文与 discovery 旅程未形成统一协议。
- 圈子 post 进入 viewer 时必须传入。
- viewer 返回时必须回写。
- 圈子来源不得只回写部分数字。
- discovery 与 circle 的 viewer handoff 字段集合必须保持同构。
- 所有 handoff 字段必须兼容 content post projections 与 `PostSummaryView` 消费模型。
- 通过统一 provider 自动同步回 circle feed，无需 circle 单独重新推断关系态。
- 圈子来源进入 viewer 的 handoff 不得导致首屏额外自拉数据。
- 弱网下 circle 来源不得丢失 pending interaction intents。
- 灰度由主 journey 的统一 feature flag 与 `sys.client_state_sync.*` 控制。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 圈子流中的 post 虽已有部分进入媒体浏览器的路径

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“圈子流中的 post 虽已有部分进入媒体浏览器的路径”对应的公开行为。
- THEN 圈子 post 进入 viewer 时必须传入。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 圈子流中的 post 虽已有部分进入媒体浏览器的路径 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“圈子流中的 post 虽已有部分进入媒体浏览器的路径”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
