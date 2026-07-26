# L3 Story：图片商用规模闭环 (`image-commercial-scale-closure`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望通用图片 rights、去重、Agent 文案与 release 生命周期验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- provider policy、资产级 rights/provenance、watermark 和对象匹配
- 跨 execution canonical identity 去重
- request 驱动的 environment import、consumer、rollback/replay 证据

### Out of Scope

- 静态区域、目标对象、数量或阶段清单
- 绕过登录、DRM、robots 或反爬

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 each publishable image has an asset-level disposition

- 缺任一 required rights 字段的资产不能进入 release。

<a id="req-002"></a>
### REQ-002 image identity and visible copy are unique and attributable

- 同一视觉资产不能通过改 URL、尺寸或文件名成为第二对象。

<a id="req-003"></a>
### REQ-003 image release and capacity evidence are request-derived

- 任何 dry-run、缺环境 receipt 或估算值都不能作为放量完成。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/schema/release/asset_rights_closure.schema.json`
- canonical：`quwoquan_data/scripts/content/post/image`
- canonical：`quwoquan_data/scripts/content/release`
- canonical：`quwoquan_data/scripts/governance/coverage/benchmark.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 each publishable image has an asset-level disposition

- GIVEN family 和 provider policy 已声明来源分类和 rights 规则。
- WHEN 图片候选进入 source unit、review 和 canonical promotion。
- THEN 原始落地页、作者、rights、使用范围、watermark、对象匹配与处置结论完整可审计。

<a id="gwt-002"></a>
### GWT-002 image identity and visible copy are unique and attributable

- GIVEN 资产已通过 rights admission，模型绑定已冻结。
- WHEN 图片完成下载、安全检测、Agent 配文、独立 review 和对象事务。
- THEN hash、perceptual similarity 和 source identity 阻止重复发布。
- THEN 归因和用户可见 copy 与 canonical 对象一致。

<a id="gwt-003"></a>
### GWT-003 image release and capacity evidence are request-derived

- GIVEN request 冻结 target set、runtime policy、source digest 和模型绑定。
- WHEN execution 形成 immutable release 并进入 integration 环境。
- THEN import、API、consumer、rollback/replay 和成本吞吐 evidence 都绑定同一 release digest。
- THEN 后续容量评估只读取真实 receipt。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 each publishable image has an asset-level disposition

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺任一 required rights 字段的资产不能进入 release。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 image identity and visible copy are unique and attributable

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：同一视觉资产不能通过改 URL、尺寸或文件名成为第二对象。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 image release and capacity evidence are request-derived

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：任何 dry-run、缺环境 receipt 或估算值都不能作为放量完成。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
