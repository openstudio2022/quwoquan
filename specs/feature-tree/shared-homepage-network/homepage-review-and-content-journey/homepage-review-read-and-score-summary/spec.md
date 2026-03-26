# L3 Scenario: homepage-review-read-and-score-summary

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-review-and-content-journey`
- `L3_scenario`: `homepage-review-read-and-score-summary`

## 背景与动机

主页口碑如果只有一个平均分，用户无法建立真实心智；  
如果口碑又完全散落在二级页，主页首屏就失去“信任入口”。

## 目标用户

- 通过评分和口碑辅助决策的用户。
- 希望快速浏览精选口碑与维度摘要的用户。

## 功能范围

- 总评分与维度摘要。
- 口碑数量、标签分布、精选口碑摘要。
- 进入更多口碑或写口碑入口。

## Out of Scope

- 口碑发布流程。
- 评分计算底层实现。
- 认领方回应机制。

## 约束

- 口碑模板跟主页类目走。
- 评分摘要必须与真实口碑聚合保持一致。

## 角色分工

- `shared-homepage-network`：评分摘要与口碑读取

## 数据生命周期合同

- 评分摘要只消费已发布口碑聚合结果。
- 写口碑入口只负责跳转，不在本场景写入。

## 非功能目标

- 首批评分摘要 `p95 < 1.5s`

## 验收重点

1. 主页可展示可信的评分摘要。
2. 维度信息与精选口碑可读。
3. 口碑入口清晰但不侵入口碑发布流程。
