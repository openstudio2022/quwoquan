# L3 Scenario: homepage-content-and-question-aggregation

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-review-and-content-journey`
- `L3_scenario`: `homepage-content-and-question-aggregation`

## 背景与动机

主页必须成为内容和问答的聚合面，但不能吞掉内容域本身。  
因此需要冻结主页如何消费 `笔记 / 作品 / 提问 / 口碑` 的聚合结果。

## 目标用户

- 希望通过主页继续看内容和问答的用户。
- 想从主页判断这个具体事物是否“有社区活性”的用户。

## 功能范围

- 主页内容聚合区。
- 主页问答聚合区。
- 按内容类型切换或筛选的基础能力。

## Out of Scope

- 内容详情页本身。
- 问答写入流程。
- 复杂排序算法。

## 约束

- 主页只消费内容域聚合结果，不自建第二套内容真相。
- 问答和内容必须可区分，但都属于主页聚合面。

## 角色分工

- `shared-homepage-network`：主页聚合视图
- `content`：内容与提问来源

## 数据生命周期合同

- 已发布内容按主页引用字段进入主页聚合。
- 聚合统计允许最终一致，不要求强同步。

## 非功能目标

- 首批聚合结果 `p95 < 1.5s`

## 验收重点

1. 主页可稳定聚合内容和提问。
2. 聚合面与内容详情边界清晰。
3. 内容按主页引用回流成立。
