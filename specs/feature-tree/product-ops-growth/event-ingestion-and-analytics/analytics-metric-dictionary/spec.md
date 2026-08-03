# L3 Story：分析指标字典 (`analytics-metric-dictionary`)

> 所属能力：[`event-ingestion-and-analytics`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，
我希望指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件，
从而获得可度量、可回滚的运营结果。

## 2. 范围与非目标

### In Scope

- “分析指标字典”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分析指标字典

- 指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。

<a id="req-002"></a>
### REQ-002 指标必须声明

- 指标必须声明。
- 指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。
- 新增指标不得绕过字典直接进入 dashboard 或模型特征表。
- 每个关键业务最多登记 3 个一级黄金指标；二级指标只能用于定位一级指标。机器门必须校验。
- 指标名称、分组与含义必须稳定；当前未上线阶段采用单轨替换，不维护事件版本兼容信封。
- L2：推荐 surface `featured / circle / campus / travel / homepage_detail / search_xiaoqu` 均必须通过 `BehaviorReporter` 上报曝光、点击与停留，由服务端归因指标计算 CTR；缺既有 behavior attribution 维度视为看板不可发布。
- 新增指标必须经过字典、事件目录或领域 metadata 的单轨评审。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分析指标字典

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“分析指标字典”对应的公开行为。
- THEN 指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`event-ingestion-and-analytics`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 首发归因指标与端侧 SLO 告警落点

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：`circle_join_rate`、交集转化、`xiaoqu.mention.triggered`、`content.homepage.attach` 与端侧 API 延迟/错误率尚未全部形成可触发指标和告警路由。
- 完成判定：事件进入 canonical catalog，recording rule/Elasticsearch projection、dashboard、阈值、值班路由与测试同源；缺数据明确显示不可用而非合成趋势。
- 依赖：各 owner 领域事件生产者与 observability pipeline。
