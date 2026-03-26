# multi-domain-result-composition 设计方案

## 设计动因

综合搜索的难点不是“展示几个 section”，而是如何在统一 `Search` 接口之下，仍保持 typed 结果模型、局部降级和稳定跳转。

## 最新实现基线（2026-03-22）

本 Scenario 的结果编排基线已经从“单页综合结果”切换为“两段式结果组织”：

- 联想页只允许 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段。
- 联系人与聊天记录是会话导向结果，点击后直接进入聊天页。
- 独立网络结果页负责 `小趣搜` assistant 结果与按群组二级分类过滤的内容结果。
- 因此，下文若仍出现“按四域综合分组”的旧表述，统一以“联想页四段 + 网络结果页 tab”解释。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `multi-domain-result-composition/spec.md` | 已冻结四域结果分组、局部降级与不混排问小趣 |
| `multi-domain-result-composition/acceptance.yaml` | `A1/S1` 足以承接实施切片 |
| `cross-domain-search-journey/design.md` | Journey 已选定统一 `Search` 接口 + 内部 `SearchCoordinator` + 域级 `Search*` contract |

## 对标输入分析

- 微信的结果组织提供了“对象分组优先于统一瀑布流”的参考。
- 对我们更重要的是：单域失败不能拖垮整页，且结果项必须 typed 化。

## 方案对比

### 方案 A：继续在 App 内按本地数据池过滤

优点：

- 简单。

缺点：

- 无法商用。
- 结果模型不稳定。

### 方案 B：统一后端 `SearchAll`

优点：

- 客户端逻辑最轻。

缺点：

- 当前服务端改造面过大。
- 不利于一把上线。

### 方案 C：统一 `Search` 接口内部由 `SearchCoordinator` 并行调用四域 Repository，结果 typed 分组

优点：

- 实施成本与能力边界最平衡。
- 页面与业务层不需要面对分域搜索接口。
- 可沿用现有 Repository 模式和 metadata/codegen 主轴。

缺点：

- 客户端需要承担 fan-out 与局部降级。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：统一 `Search` 接口是页面唯一入口，`SearchCoordinator` 是其内部编排中心

职责：

- debounce
- cancel stale request
- parallel fan-out
- section composition
- partial degrade

### KD2：结果模型固定为 typed section + item

- `SearchSectionKind`
- `SearchResultItemKind`
- `SearchResultItem`
- `SearchSection`

各域返回 typed DTO，再映射为统一 item。

### KD3：每个域各自负责结果对象，不负责综合排序

- `content`：内容项
- `user`：社交关系项
- `messages`：会话项、消息项
- `circle`：群组项、facet buckets

### KD4：局部降级优先

- 任一域超时或失败时，只标记对应 section 为 degraded。
- 其它 section 正常返回。
- 不做整页 fail fast。

### KD5：metadata / codegen 方案

- `content/post`：
  - `SearchPosts`
  - `PostSearchItemView`
- `messages/conversation`：
  - `SearchConversations`
  - `SearchMessages`
  - `ConversationSearchItemView`
  - `MessageSearchItemView`
- `user/user_profile`：
  - `SearchSocialRelations`
  - `SocialRelationSearchItemView`
- `social/circle`：
  - `SearchCircles`
  - `CircleSearchItemView`
  - `CircleFacetBucketView`

### KD6：结果跳转不在搜索页写死路径

- 详情跳转一律消费 metadata 生成的 route paths。
- 搜索页只根据 result kind 选择 route id 或 typed navigation helper。

## 字段演进、迁移/回填、必要时双读双写方案

- 从原型 `Map` 结果迁到 typed `SearchResultItem`。
- 不做结果双写；结果仅作为当前会话读模型。
- `SearchContacts` 不再作为综合结果中的“人”定义。

## feature flag、观测、SLO 验证与回滚方案

- 无业务 feature flag。
- 观测：
  - `search_section_latency_ms`
  - `search_section_degrade_count`
  - `search_result_click_count`
- SLO：
  - 首批 section `P95 < 1.5s`
- 回滚：
  - 整版回退到旧搜索实现

## TDD / ATDD 策略

- `T1_schema`：统一 `SearchRequest / SearchResponse`、四域 search DTO 与 unified result model
- `T2_module_interaction`：分组渲染、空态、降级态
- `T3_cross_service_integration`：并发 fan-out、部分失败
- `T4_user_journey`：搜索结果进入详情

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结统一 `Search` 接口、四域 search contract 和 unified result model | `T1_schema` |
| `P2` | 落地统一 `Search` 接口、`SearchCoordinator` 与 section composition | `T2_module_interaction`, `T3_cross_service_integration` |
| `P3` | 验证局部降级与结果跳转 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 后续如果引入统一聚合搜索，也只替换统一 `Search` 接口的底层数据源，不改 section/item 模型。
