# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象使用同一 execution/release 边界发布，从而能复核来源、媒体、实体与环境消费是否闭合。

## 2. 范围与非目标

### In Scope

- execution 冻结 target set，release 绑定 source digest、对象闭包与 desired state。
- 各载体复用同一创建、审核、promotion 和 ship 生命周期。

### Out of Scope

- 为不同地区或载体维护第二套发布目录与运行台账。

## 3. 行为要求

### REQ-001 多载体统一发布边界

- 每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。

## 4. 契约引用

- release：`quwoquan_data/schema/release/release_manifest.schema.json`
- ship：`quwoquan_data/schema/release/ship_report.schema.json`

## 5. 验收场景

### GWT-001 引用闭包后才允许 promotion

- GIVEN 同一 execution 中包含文章、图片、视频和主页对象。
- WHEN 操作者请求聚合并 promotion release。
- THEN 仅当全部对象引用与媒体处置闭合时生成 immutable release；任一悬挂引用使整次 promotion 失败。

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 多载体环境消费证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：发布合同完成不等于四类载体已在目标环境被真实消费。
- 完成判定：`GWT-001` 与目标环境四载体消费 UAT 均有直接 `spec_ref`。
