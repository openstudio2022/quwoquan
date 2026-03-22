# L3 Scenario: circle-facet-search-and-filter

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `circle-facet-search-and-filter`

## 背景与动机

用户已经明确“频道”只是 `Circle` 的分类投影，而不是独立业务对象。PRD 需要在搜索里冻结这一点，否则后续 route、result model 和 metadata 很容易再次分叉。

## 目标用户

- 需要查找圈子、圈子频道或通过频道筛圈子的用户。

## 功能范围

- 圈子搜索结果与频道 facet 的展示规则。
- 圈子分类投影在综合搜索与垂类搜索中的过滤行为。
- 圈子结果与 facet 的跳转目标。

## Out of Scope

- 新建 `channel` 业务对象。
- 圈子管理、频道管理或 section 配置本身。

## 约束

- “频道”只允许作为 `Circle` 的分类投影 / facet。
- 圈子 facet 的真相源必须来自 circle 域已有分类与配置模型。
- 不允许在搜索层新增第二套 channel 实体定义。

## 对标输入与吸收结论

- 参考微信内容搜索结果中“内容 + 分类”联动展示方式。
- 结合现有圈子频道 UI，吸收为搜索页中的 facet 过滤表达。

## 角色分工

- `circle`: 圈子对象与分类投影真相源。
- `global-search-experience`: facet 展示、筛选与结果承接。

## 既有 Story 覆盖矩阵

| 既有能力 | 当前角色 |
|---|---|
| 现有圈子频道 UI 与分类投影 | 继续作为 circle facet 真相源输入 |
| 旧搜索原型中的圈子本地过滤 | 被新 Scenario 吸收替换 |

## 数据生命周期合同

- facet 是当前查询上下文的瞬时过滤条件。
- 若用户通过指定搜索内容进入圈子搜索，可把当前 facet 写入最近搜索上下文。

## 小趣 / 权限 / 分享边界

- 本 Scenario 不处理问小趣。
- 当前账号或登录子账号可见的圈子与分类投影都可进入搜索结果。

## 非功能目标

- 圈子与 facet 结果需在综合搜索首批结果内可见。
- facet 切换不应破坏当前搜索 query。

## 迁移、灰度与回滚要求

- 不保留“频道独立对象”历史提法。
- 若 facet 逻辑异常，整体回退到旧搜索实现，不引入并行治理。

## 验收重点

1. 频道严格冻结为 circle facet。
2. 圈子结果与 facet 过滤关系清晰。
3. 搜索层不再发明新的 channel 业务对象。
