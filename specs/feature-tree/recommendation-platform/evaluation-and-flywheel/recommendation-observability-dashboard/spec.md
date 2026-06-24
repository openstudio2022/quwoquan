# L3 Story：recommendation-observability-dashboard

## 功能说明

`recommendation-observability-dashboard` 承接非深排推荐商用成熟度 P0/P0+ 后的效果评估入口。它把 feed 下发与行为上报中的 bounded attribution 指标固化到可审计的看板源文件，让算法、运营、产品和测试能按首页、旅行、精品、UGC、数据工程供给、召回路径与交集类别复盘推荐效果。

## 范围

- 推荐 served 与 behavior 归因指标看板：`recommendation_feed_served_by_attribution_total`、`recommendation_behavior_by_attribution_total`。
- 必备分桶：`channel`、`vertical`、`supply_source`、`recall_path`、`ranking_version`、`reason_version`、`intersection_class`。
- 必备视图：served 分布、CTR、负反馈率、unknown attribution rate、旅行/精品消费、fact/affinity 交集解释效果、reason version 对比、UGC/数据工程供给占比。
- 看板源文件、SLO 指标入口与 local_contract 契约测试保持同源。

## 非目标

- 不实现深排平台、双塔 ANN、MMoE/PLE/ESMM、IPS/Thompson 或同步 scorer。
- 不实现离线 replay 脚本、在线 AB 平台或真实流量训练晋升。
- 不实现 product-ops 全局精品池写入、审计、过期、回滚或下架实时剔除。
- 不用看板替代用户验收、压测或线上 AB 显著性结论。

## 验收标准

- A1：看板源文件引用真实 emitter 指标，不引用 objective_only 指标冒充已观测。
- A2：所有核心分桶标签均来自 bounded attribution 契约，禁止引入高基数自由文本标签。
- A3：看板至少覆盖首页、旅行、精品、UGC、数据工程、召回路径、交集类别、reason version 和 unknown attribution。
- A4：local_contract 固化 dashboard UID、标签、指标名、分桶标签、状态分子和 SLO 入口。
