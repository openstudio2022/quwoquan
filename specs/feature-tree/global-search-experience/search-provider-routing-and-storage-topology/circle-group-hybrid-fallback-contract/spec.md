# L3 Scenario: circle-group-hybrid-fallback-contract

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `circle-group-hybrid-fallback-contract`

## 背景与动机

`circle.group` 是唯一明确冻结为“云优先、本地兜底”的对象。如果不单独成约束，后续会在页面、provider 或服务端各写一版 fallback 语义。

## 功能范围

- 冻结 `circle.group` 的 remote-primary / local-fallback 规则。
- 冻结 fallback 触发条件与结果标记。
- 冻结 fallback 的结果来源是端侧本地全量结果。

## Out of Scope

- remote + local 融合重排。
- 本地索引生命周期的细节治理。

## 约束

- 云侧失败、超时、熔断或 0 结果时触发 fallback。
- fallback 必须返回 typed `resolvedFrom=local_fallback`。
- 页面不得直接决定 fallback。

## 验收重点

1. `circle.group` fallback 是否有唯一 contract。
2. fallback 是否以 typed 结果返回，而不是文案约定。
