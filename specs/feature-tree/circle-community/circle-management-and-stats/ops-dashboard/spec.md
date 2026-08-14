# L3 Story：运营看板 (`ops-dashboard`)

> 所属能力：[`circle-management-and-stats`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为圈子成员或圈子运营者，
我希望运营人员能够查看来自真实指标源的圈子健康、活跃与治理状态，
从而完成可治理的社区协作。

## 2. 范围与非目标

### In Scope

- “运营看板”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运营看板

- “运营看板”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 运营看板

- GIVEN 圈子成员或圈子运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“运营看板”对应的公开行为。
- THEN 通过父能力公开契约交付“运营看板”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`circle-management-and-stats`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 运营看板无用户可达面，不阻塞 SCN-014

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前没有独立圈子运营看板产品入口；圈子主页轻统计与 stats 列表已由 kpi-reporting 承接。本 Story 不另造第二套运营后台，不阻塞 SCN-014 商用主旅程。
- 完成判定：若产品交付用户可达运营看板，再由 `GWT-001` 真实测试绑定；在此之前保持 Out of Scope。
