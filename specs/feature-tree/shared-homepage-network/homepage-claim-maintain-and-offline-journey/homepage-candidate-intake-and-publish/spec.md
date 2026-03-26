# L3 Scenario: homepage-candidate-intake-and-publish

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-claim-maintain-and-offline-journey`
- `L3_scenario`: `homepage-candidate-intake-and-publish`

## 背景与动机

共享主页的第一步不是用户浏览，而是把候选主页治理成正式主页。  
如果候选链路不清晰，主页网络就会被重复、脏数据和低可信条目拖垮。

## 目标用户

- 平台运营与审核人员。
- 触发补充主页的社区贡献者。

## 功能范围

- 候选主页 intake。
- 候选状态管理。
- 审核发布为正式主页。

## Out of Scope

- 认领审核。
- 下线治理。
- 主页合并。

## 约束

- 候选主页不能绕过审核直接公开。
- 候选来源必须可追踪。

## 角色分工

- `shared-homepage-network`：候选 intake 与发布
- `product-ops`：审核规则

## 数据生命周期合同

- 候选至少经过 `candidate -> pending_verify -> published`

## 非功能目标

- 支持批量审核

## 验收重点

1. 候选主页主线成立。
2. 审核前不公开。
3. 发布后可进入正式主页网络。
