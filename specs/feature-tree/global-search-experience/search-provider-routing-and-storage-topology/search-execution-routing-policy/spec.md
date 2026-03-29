# L3 Scenario: search-execution-routing-policy

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `search-execution-routing-policy`

## 背景与动机

统一接口如果没有统一执行策略，最终仍会退化成页面侧 if/switch。该 Scenario 用来冻结 planner 如何根据 objectType 决定 local、remote 或 hybrid 执行。

## 功能范围

- 冻结 `local_only / remote_only / hybrid_remote_fallback_local`。
- 冻结 planner 的执行优先级与降级规则。
- 冻结 typed `resolvedFrom` / degrade signal 语义。

## Out of Scope

- 具体 provider 实现细节。
- 具体排序算法。

## 约束

- 执行策略必须由 registry / planner 决定，不允许页面特判。
- 单个 provider 失败不阻塞其它 objectType 返回。

## 验收重点

1. 是否存在唯一 execution mode 真相源。
2. 降级语义是否 typed，而不是 UI 文案约定。
