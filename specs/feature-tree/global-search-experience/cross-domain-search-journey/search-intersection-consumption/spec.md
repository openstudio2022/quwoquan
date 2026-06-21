# L3 Story：全局搜索交集消费

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `cross-domain-search-journey`
- `L3_story`: `search-intersection-consumption`

## 功能说明

全局搜索的「交集」Tab、搜索首页「今日交集」激发区、以及「全部」Tab 发现区交集分组，统一消费 search hit 上的 `connectionState` + `intersectionReason` 子集。交集结论句只读 `primaryText`（G2）。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.4 S6 / §18。

## 范围

- 搜索 contract：`connectionState` 闭集 + `intersectionReason` IntersectionReason 子集（metadata `_shared/search_contract.yaml` / `search_objects.yaml`）。
- 结果页「交集」Tab：概览 + 推荐区 + 交集发现流；每张卡一条 primaryText。
- 「全部」Tab 发现区：交集 lead 分组消费 `connectionState=intersection_lead`。
- 搜索首页默认态：「今日交集」一行 4 卡激发搜索（compact surface，单句）。
- PostSearchItemView / 各 domain search hit 投影补齐 intersection 字段（alpha mock）。

## Out of Scope

- 云侧 search read model 全量落地（P1）。
- 端侧本地拼装交集文案（G2 禁止）。
- 小趣 Tab 交集混排。

## 验收标准概要

- A1：交集 Tab 每张卡有且仅一条 primaryText，无 displayText 回退。
- A2：connectionState 分组与 global-search-experience spec 已连接/发现区规则一致；**缺 connectionState 的 hit 不进入交集展示窗**（零过渡，禁止客户端推断）。
- A3：无 primaryText 的 hit 不进入交集展示窗（不占位）。
- A4：alpha mock search hit 含 intersectionReason 子集，local_contract widget 测试绿。
