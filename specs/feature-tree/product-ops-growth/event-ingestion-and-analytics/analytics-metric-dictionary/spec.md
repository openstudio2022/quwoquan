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

<a id="req-003"></a>
### REQ-003 指标注册表是阈值与展示成员的唯一真相源

- `golden_metric_catalog.yaml` 的 `source.track` 闭集为 `product_telemetry`、
  `behavior_attribution` 与 `domain_fact_readface`；`behavior_attribution`
  以 Prometheus series 登记推荐归因口径
  （CTR 权威分子为 `recommendation_feed_engagement_total{action="click"}`），
  只登记口径不搬事实。`domain_fact_readface` 登记交集飞轮北极星三比例
  `flywheel_wishlist_to_join_rate`、`flywheel_formed_to_experienced_rate`、
  `flywheel_facilitation_republish_rate`，分子分母唯一真相源为
  recommendation 内部读面 `GetRecommendationFlywheelFunnel`——域事实读时聚合、
  时间窗必填，可按 sourceObjectKind/sourceObjectId/capacityTier/tagRef 切片，
  空数据为零、越界 truncated、无预聚合缓存、读面不下发百分比。series
  字段登记读面响应字段名而非 Prometheus series。App `product_action` 轨
  的 `gathering_flywheel` journey 埋点只作体验辅证，不得充当分子分母。
- 每条指标的 `target` 是体验目标唯一声明处；`alerting`
  （policy / alert_name / threshold）声明告警绑定，阈值必须落在
  target 违反侧，且与告警定义文件数值逐字一致
  （`make verify-metric-threshold-homology`）。
- `display.portal_level`（L1/L2）+ `display.label` 驱动 Portal
  `/control-plane/product/metrics/l1l4` 的 L1/L2 卡片成员
  （经 codegen `golden_metric_catalog.go`）；L3/L4 由契约 SLI 轨与基础设施轨
  归属，不进入字典。event_ratio / unique_session_ratio 由 summary 门面
  承载，percentile_p95 / sum_ratio 由 raw 原始样本统计门面
  （`GetEventValueStats`，与 RTC QoE 同口径）承载；实时卡片无法承载的
  形态（扩展字段过滤）必须显式 unavailable，禁止合成数值。
- PV 唯一口径 = `page_open` 页面浏览量；活跃唯一口径 = DAU/WAU/MAU
  （actorHash 去重），禁止 uv 混称与全事件数冒充 PV。

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
### OPEN-001 剩余归因指标缺事件生产者

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺可注册的事件生产者或归因 series——剩余
  `circle_join_rate`、`xiaoqu.mention.triggered`、
  `content.homepage.attach` 无法入册形成可触发告警；登录成功率、
  发布成功率、搜索有效点击率、推荐 CTR、崩溃/ANR 会话率、主旅程完成率
  已入册 `golden_metric_catalog.yaml` 并绑定既有告警。交集转化已收窄：
  北极星三比例经 `domain_fact_readface` 轨入册（见 REQ-003），分子分母由
  rec 漏斗读面从域事实读时派生并有 api_integration 精确正负例；
  三比例暂不绑定告警（上线前无稳定基线，target 登记为 ≥0 观察位）。
- 完成判定：剩余指标的事件/series 进入 canonical catalog 或归因计数器，
  经注册表登记 target 与 alerting，阈值同源门禁通过并满足
  [GWT-001](#gwt-001) 的同源可观察结果；缺数据明确显示不可用而非合成趋势。
- 依赖：circle / assistant / entity 领域事件生产者与 observability pipeline。
