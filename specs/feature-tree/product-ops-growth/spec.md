# L1 特性：product-ops-growth（运营横切）

## 功能说明
- 建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。
- 建立面向用户全生命周期的发现、邀请、分群、激活、留存、召回与恢复经营闭环。
- 以特性粒度驱动增长策略的自动化验证与持续迭代。
- 作为统一 Web 门户 `ops-portal` 中 `Product Ops` 工作域的特性树承载层。
- 冻结统一运营控制面的两大模块：`治理处置` 与 `增长/实验/推荐运营`。

## 约束
- 运营事件必须统一 schema，禁止各模块自由扩展核心字段语义。
- 实验发布必须具备审计、灰度、回滚链路。
- 运营链路必须可关联 request/trace/page/session。
- 用户增长链路必须区分 `OwnerAccount` 管理视角与 `SubAccount` 应用视角：
  - 通讯录匹配归 `OwnerAccount`
  - 好友/圈子/群/邀请归因与奖励归 `SubAccount`
- 面向 `product-ops` 的管理接口必须从统一控制面元数据生成，禁止手写临时运营后台接口。
- 推荐运营范围必须覆盖召回、粗排、精排的受控干预，而不是仅限 AB 实验。
- 审核、处罚、申诉、恢复必须支持工作流、证据、SLA 与双签审计。
- 用户发展、邀请传播、通讯录发现、分群经营、恢复治理必须支持跨域审计与生命周期视图。
- 三类面必须支持部署时任意组合，且不得依赖当前同 Pod 形态固化契约。

## 与父/子节点关系

- 父节点：`product-ops-growth` L1（运营横切能力边界）
- 已冻结并可进入 `/dev` 的关键子节点：
  - `event-ingestion-and-analytics`（L2）：统一事件、反馈应用、云侧冷热分层与运营分析基线
  - `experiment-bucketing-and-rollout`（L2）：实验分桶与发布治理
- `event-ingestion-and-analytics` 下的关键子节点：
  - `analytics-metric-dictionary`（L3）：统一指标字典与下钻维度
  - `event-schema-governance`（L3）：统一 envelope、字段分级、版本兼容、幂等与背压

## 相关文档

- [`event-ingestion-and-analytics/spec.md`](./event-ingestion-and-analytics/spec.md)
- [`event-ingestion-and-analytics/design.md`](./event-ingestion-and-analytics/design.md)
- [`event-ingestion-and-analytics/plan.yaml`](./event-ingestion-and-analytics/plan.yaml)
- [`event-ingestion-and-analytics/acceptance.yaml`](./event-ingestion-and-analytics/acceptance.yaml)

## 验收重点
- A4：运营事件可观测且可检索
- A5：实验与优化闭环可执行
- A7：事件契约与 metadata 一致
- A8：运营链路自动化测试完整
- A1：治理工作流与推荐运营干预可真实执行
- A2：用户邀请、通讯录发现、分群经营与恢复治理的归属边界清晰冻结

