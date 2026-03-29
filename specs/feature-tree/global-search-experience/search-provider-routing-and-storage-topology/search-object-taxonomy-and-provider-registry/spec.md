# L3 Scenario: search-object-taxonomy-and-provider-registry

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `search-object-taxonomy-and-provider-registry`

## 背景与动机

如果 searchable object 继续以页面、仓库或服务内部名字存在，统一搜索接口很快会退化为一个壳。该 Scenario 用来冻结 object taxonomy 与 provider registry。

## 功能范围

- searchable object 的统一命名。
- object -> provider -> execution mode 的注册表。
- objectType 与展示语义、跳转语义的绑定边界。
- 外部网页对象与趣我圈内部对象共用同一 taxonomy。

## Out of Scope

- 排序策略。
- 存储实现。

## 约束

- objectType 必须是统一枚举或 metadata 注册项。
- 页面层不得自定义新的搜索对象字符串。
- taxonomy 必须覆盖 `web.document`，使 AI 能通过同一接口同时检索网页与站内对象。

## 验收重点

1. searchable object 是否有统一注册表。
2. provider routing 是否基于 registry，而不是页面 if/switch。
