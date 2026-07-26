# L3 Story：Markdown 文章内核 (`markdown-article-kernel`)

> 所属能力：[`content-type-framework`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望小屏或可访问性大字号下统一降级为 `fullWidth`，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “Markdown 文章内核”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Markdown 文章内核

- 小屏或可访问性大字号下统一降级为 `fullWidth`。

<a id="req-002"></a>
### REQ-002 小屏或可访问性大字号下统一降级为 fullWidth

- 小屏或可访问性大字号下统一降级为 `fullWidth`。
- 降级不能丢失图片、caption、阅读顺序和语义标签。
- Markdown 解析失败时必须返回结构化 runtime failure，不向用户暴露原始异常字符串。
- 素材缺失、hash 不匹配、scope 不合法时不可发布。
- 详情页、发现沉浸式和侵入式媒体浏览器必须消费同一 AST/page model。
- seed、fixture、冷启动 batch 中不得再新增 `articleDocument` 长文真相源。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Markdown 文章内核

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“Markdown 文章内核”对应的公开行为。
- THEN 小屏或可访问性大字号下统一降级为 `fullWidth`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Markdown 文章内核 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“Markdown 文章内核”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
