# L3 Story：文章商用规模闭环 (`article-commercial-scale-closure`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望通用文章 provider onboarding、单 execution 生产与基于真实回执的发布容量验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- provider policy 与文本、插图的 source/rights 闭包
- Agent authoring、独立 review、canonical promotion 与 immutable release
- request 驱动规模下的 import/API/consumer/rollback/replay 证据

### Out of Scope

- 静态区域、目标对象、数量或阶段清单
- 未经真实 receipt 支撑的生产容量结论

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 provider onboarding is reusable and source-role complete

- 缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。

<a id="req-002"></a>
### REQ-002 each approved article closes one execution and release lifecycle

- 任何缺失对象、来源、rights 或环境 receipt 均阻断 release。

<a id="req-003"></a>
### REQ-003 capacity conclusions use only measured execution receipts

- 容量评估可重算且不被当作生产完成。

<a id="req-004"></a>
### REQ-004 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool

- 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool
- homepage 必须通过显式 `homepageExecutionId` 绑定已冻结、已发布的同档主页批次。
- 搜索补全供给使用独立 execution，不能和主线共享冻结目标、状态或准出口径。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/verticals/<vertical>/content_policy.yaml`
- canonical：`quwoquan_data/scripts/content/source`
- canonical：`quwoquan_data/scripts/content/execution`
- canonical：`quwoquan_data/scripts/content/release`
- canonical：`quwoquan_data/scripts/governance/coverage/benchmark.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 provider onboarding is reusable and source-role complete

- GIVEN 垂类 provider policy、content policy 与 family 已由仓内真相源声明。
- WHEN 任一文章 execution 以 request 选择 provider 和主题。
- THEN provider admission、文本事实来源和插图 rights/provenance 使用同一合同。
- THEN 静态 policy 不包含实体 URL、区域、数量或运行结论。

<a id="gwt-002"></a>
### GWT-002 each approved article closes one execution and release lifecycle

- GIVEN request 已冻结 target set、provider 选择、模型与 source digest。
- WHEN article 完成 source、compose、draft、review、canonical promotion 和 release aggregate。
- THEN 文章、关联主页、creator、资产、tag 和 source digest 可闭包追溯。
- THEN Beta/Gamma integration 证明 full-sync、API、幂等、rollback 与 replay。

<a id="gwt-003"></a>
### GWT-003 capacity conclusions use only measured execution receipts

- GIVEN 至少一个完成闭包的文章 execution 已产生不可变 receipt。
- WHEN 运营评估后续规模与预算。
- THEN 吞吐、成本、first-pass rate、queue lag 与 source capacity 都来自 receipt。
- THEN 缺失实时证据时结论为 GATE_BLOCK，不能写入静态 policy 或 acceptance 数字。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 provider onboarding is reusable and source-role complete

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 each approved article closes one execution and release lifecycle

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：任何缺失对象、来源、rights 或环境 receipt 均阻断 release。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 capacity conclusions use only measured execution receipts

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：容量评估可重算且不被当作生产完成。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
