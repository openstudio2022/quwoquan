# L3 Story：发布器主主页挂载与主页内发布上下文自动带入的单轨语义 (`homepage-attach-in-publish-flow`)

> 所属能力：[`homepage-discovery-and-attach`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望发布器主主页挂载与主页内发布上下文自动带入的单轨语义，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 发布器经 homepagePicker 选择主主页并写入 post primaryHomepageId。
- 从主页详情进入创作时经 HomepageCanonicalReference extra 自动带入当前主页。
- 口碑必绑主页、笔记/作品/提问可选绑的规则。

### Out of Scope

- 发布器完整编辑体验。
- 多主页挂载。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 全局发布与主页内发布共用同一挂载语义

- 两个入口产生的挂载字段与回流聚合语义一致。

<a id="req-002"></a>
### REQ-002 全局发布入口与主页内入口必须共用同一发布器

- 全局发布入口与主页内入口必须共用同一发布器。
- `口碑` 必须且只能绑定 1 个主主页。
- 写入失败时不能出现“内容已发布但主页未挂上”的静默不一致。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 全局发布与主页内发布共用同一挂载语义

- GIVEN 用户从创作入口或主页详情「发布」进入同一发布器。
- WHEN 用户选择/确认主主页并发布内容。
- THEN 发布 payload 携带唯一 primaryHomepage 引用；主页内进入时默认带入且可更换。
- THEN 发布失败不出现「内容已发布但主页未挂上」的静默不一致。

## 6. 依赖

- 前置要求：[`homepage-discovery-and-attach`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 全局发布与主页内发布共用同一挂载语义

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：两个入口产生的挂载字段与回流聚合语义一致。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
