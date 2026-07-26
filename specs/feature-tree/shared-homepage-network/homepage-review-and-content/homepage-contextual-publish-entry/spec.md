# L3 Story：主页上下文创作入口 (`homepage-contextual-publish-entry`)

> 所属能力：[`homepage-review-and-content`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望从主页详情发起创作并自动带入当前主页引用，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 详情页创作入口经 HomepageCanonicalReference extra 进入统一发布器。
- 游客点击先见创作面板/登录门（对齐登录入口无死循环契约）。

### Out of Scope

- 发布器编辑体验与媒体处理。
- 口碑发表（homepage-review-read-and-score-summary 承载）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 主页内发布入口带上下文进入统一发布器

- 主页内入口与全局创作入口产出同一挂载语义。

<a id="req-002"></a>
### REQ-002 主页内发布入口和全局发布入口必须共用同一发布器

- 主页内发布入口和全局发布入口必须共用同一发布器。
- 当前主页必须默认带入，但允许在非口碑场景调整。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 主页内发布入口带上下文进入统一发布器

- GIVEN 用户处于已发布主页详情。
- WHEN 点击「发布/记录」入口。
- THEN 进入统一 create 发布器且当前主页引用已带入，可确认或更换。
- THEN 未登录用户经 requireLogin 门禁；关闭登录回安全态不再复弹。

## 6. 依赖

- 前置要求：[`homepage-review-and-content`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 主页内发布入口带上下文进入统一发布器

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：主页内入口与全局创作入口产出同一挂载语义。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
