# L3 Story：feed-item-dto-contract（Feed 规范 DTO 契约） (`feed-item-dto-contract`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览内容流的用户，
我希望在不同内容流看到字段、互动状态和跳转语义一致的内容卡片，
从而不会因来源不同看到缺字段或错误动作。

## 2. 范围与非目标

### In Scope

- “feed-item-dto-contract（Feed 规范 DTO 契约）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 feed-item-dto-contract（Feed 规范 DTO 契约）

- `generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。

<a id="req-002"></a>
### REQ-002 generated/content/feed_item_dto.g.dart 标记 // Code generated ... DO NOT EDIT.，禁止手改

- `generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- 字段变更必须走 metadata → `make verify` → `make codegen-app` 流程。
- mock 数据字段必须与 `FeedItemDto` schema 100% 一致，由 contract test 验证。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 feed-item-dto-contract（Feed 规范 DTO 契约）

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“feed-item-dto-contract（Feed 规范 DTO 契约）”对应的公开行为。
- THEN `generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 feed-item-dto-contract（Feed 规范 DTO 契约） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“feed-item-dto-contract（Feed 规范 DTO 契约）”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
