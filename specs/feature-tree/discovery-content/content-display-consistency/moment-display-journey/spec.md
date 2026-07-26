# L3 Story：moment-display-journey（微趣旅程） (`moment-display-journey`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “moment-display-journey（微趣旅程）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 moment-display-journey（微趣旅程）

- **行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。

<a id="req-002"></a>
### REQ-002 行为基线：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器

- **行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。
- **约束**：按 `category=moment` 隔离；微趣场景顶栏必须为 backOnly 语义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 moment-display-journey（微趣旅程）

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“moment-display-journey（微趣旅程）”对应的公开行为。
- THEN **行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 moment-display-journey（微趣旅程） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“moment-display-journey（微趣旅程）”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
