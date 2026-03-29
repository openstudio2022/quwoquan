# L3 Scenario: local-search-lifecycle-and-account-isolation

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `local-search-lifecycle-and-account-isolation`

## 背景与动机

本地聊天搜索要成立，必须先冻结生命周期与账号隔离规则，否则执行策略和数据保留都会漂移。

## 功能范围

- 冻结登出不清空、本地长期保留、用户主动删除。
- 冻结 owner / sub account 隔离。
- 冻结删除 / 撤回同步删本地索引。

## Out of Scope

- 低存储设备自动淘汰。
- 复杂生命周期策略。

## 约束

- 本地索引必须按账号命名空间隔离。
- 云端 TTL 与端侧长期保留可以不一致。
- 本期以“用户主动删除”为主要清理机制。

## 验收重点

1. 本地生命周期规则是否清晰。
2. 子账号隔离是否有唯一口径。
