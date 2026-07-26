# L3 Story：真实内容发布与远端消费 (`remote-content-delivery`)

> 所属能力：[内容云侧生产交付](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望经审核的内容发布后能由真实服务导入并在 App 中读取，从而获得与 Mock 无关的发布和消费闭环。

## 2. 范围与非目标

### In Scope

- importer 校验 immutable release、对象引用闭包与环境 desired state。
- content-service owner 写入对象，App Remote Repository 读取公开投影。

### Out of Scope

- 数据采集过程、页面视觉细节和测试执行日志。

## 3. 行为要求

### REQ-001 Release 到 Remote 单轨

- 缺 release、路径逃逸或悬挂引用必须拒绝导入；成功导入后 App 必须通过统一 gateway 读取，不得回退 fixture。

## 4. 契约引用

- release：`quwoquan_data/schema/release/release_manifest.schema.json`
- content：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`

## 5. 验收场景

### GWT-001 审核 release 可被远端读取

- GIVEN 一个通过 schema、审核和引用闭包检查的 immutable content release。
- WHEN importer 将 desired state 写入 content-service，App 以 Remote 模式读取对应对象。
- THEN App 返回 owner 服务投影；缺失或非法 release 被拒绝且不生成部分成功对象。

## 6. 依赖

- 前置要求：数据发布、content owner 与 gateway 可用。
- 上游事实：immutable release desired state。
- 下游结果：可读取内容投影或导入失败报告。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 Release 消费环境证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：本地契约不能替代 gamma 的真实导入与 App 消费证据。
- 完成判定：`GWT-001` 由 gamma import、API 与 App UAT 的直接 `spec_ref` 证明。
