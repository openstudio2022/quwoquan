# L3 Scenario: circle-facet-search-and-filter

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `circle-facet-search-and-filter`

## 背景与动机

用户侧搜索入口已经统一为 `群组`，但其分类来源仍来自 `Circle` 域的分类投影。最新两段式搜索 UX 又进一步冻结了它的展示位置：群组分类不再作为联想页独立分组，而是作为独立网络结果页顶部 facet 的来源，因此必须在 spec 中收口。

## 目标用户

- 需要在网络结果页按群组分类 facet 筛选内容结果的用户。

## 功能范围

- 独立网络结果页顶部群组分类 facet 的展示规则。
- 群组分类对内容搜索结果的过滤行为。
- 搜索 query 在切换频道 tab 时的保留与刷新语义。

## Out of Scope

- 新建 `channel` 业务对象。
- 圈子管理、频道管理或 section 配置本身。

## 约束

- 首页和搜索里的用户词统一为 `群组`，不再把结果面直接叫“圈子”。
- “群组分类 facet” 只允许作为 `Circle` 的分类投影 / facet。
- 群组 facet 的真相源必须来自 circle 域已有分类与配置模型。
- 不允许在搜索层新增第二套 channel 实体定义。

## 对标输入与吸收结论

- 参考微信内容搜索结果中“内容 + 分类”联动展示方式。
- 结合现有 circle 二级分类 UI，吸收为独立网络结果页中的群组 facet 表达。

## 角色分工

- `circle`: 群组分类 facet 真相源。
- `global-search-experience`: 网络结果页 tab 展示、筛选与结果承接。
- `content`: 接收分类过滤并返回对应内容结果。

## 既有 Story 覆盖矩阵

| 既有能力 | 当前角色 |
|---|---|
| 现有 circle 分类 UI 与分类投影 | 继续作为群组 facet 真相源输入 |
| 旧搜索原型中的圈子本地过滤 | 被新 Scenario 吸收替换为群组结果 + 群组分类 facet |

## 数据生命周期合同

- facet 是当前网络结果查询上下文的瞬时过滤条件。
- 若用户在网络结果页停留于某个频道 tab，可把当前 `category_context` 写入最近搜索上下文。

## 小趣 / 权限 / 分享边界

- 本 Scenario 不处理问小趣。
- 当前账号或登录子账号可见的群组与分类投影都可进入搜索结果。

## 非功能目标

- 顶部群组 facet 需在进入网络结果页后即时可见。
- facet 切换不应破坏当前搜索 query。

## 迁移、灰度与回滚要求

- 不保留“频道独立对象”记录提法。
- 若 facet tab 逻辑异常，整体回退到旧搜索实现，不引入并行治理。

## 验收重点

1. 群组分类严格冻结为网络结果页上的 circle facet tab。
2. 当前 query 在切换频道 tab 时保持稳定，内容结果按分类刷新。
3. 搜索层不再发明新的 channel 业务对象。
