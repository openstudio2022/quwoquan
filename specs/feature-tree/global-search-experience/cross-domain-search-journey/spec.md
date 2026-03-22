# L2 Journey: cross-domain-search-journey

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`

该 Journey 冻结从任一一级页面进入全屏搜索，到完成输入、指定类型搜索、综合结果浏览、最近搜索管理、语音转词和问小趣 handoff 的完整链路。

## 背景与动机

当前 App 搜索体验的问题不在于“没有搜索框”，而在于没有统一 Journey：

1. 首页、聊天、圈子和助手没有同一套搜索首页与结果页。
2. 当前搜索结果主要依赖本地 mock 过滤，缺乏跨域统一体验。
3. “朋友/联系人/用户”边界在产品和领域层不一致。
4. “频道”在体验上存在，但在领域上并不是独立对象。
5. 问小趣、语音输入、最近搜索与站内搜索是分散设计，未形成统一用户旅程。

## 目标用户

- 高频在站内找内容、找人、找消息、找圈子的用户。
- 习惯通过搜索首页快速切换搜索范围的用户。
- 希望在搜索无果或需要外部知识时直接问小趣的用户。
- 需要语音转文本进行检索的移动端用户。

## 核心旅程

1. 用户从首页、聊天页、圈子页或助手页点击搜索入口。
2. App 打开统一的全屏搜索首页，显示搜索框、问小趣、语音、指定搜索内容和最近搜索。
3. 用户输入关键词，或直接点击指定搜索内容发起垂类搜索。
4. App 返回综合结果，按内容、社交关系、消息、圈子与频道 facet 分组组织。
5. 用户可继续切换分组、点击结果进入详情，或改走问小趣。
6. 用户的普通搜索 query 进入最近搜索；问小趣 query 不进入最近搜索。

## 特性树拆分

本 Journey 冻结为 6 个 `L3_scenario`：

| L3 Scenario | 负责的问题 | 归属域 |
|---|---|---|
| `full-screen-search-shell-and-entry` | 全屏搜索首页、统一入口、默认上下文、返回路径 | `global-search-experience` |
| `multi-domain-result-composition` | 综合结果与分组编排 | `global-search-experience` |
| `social-relationship-search-contract` | “社交关系”结果边界与用户域真相源 | `user` 主导，`global-search-experience` 消费 |
| `circle-facet-search-and-filter` | 圈子结果与频道 facet 展示 | `circle` 主导，`global-search-experience` 消费 |
| `recent-search-sync-and-voice-asr` | 最近搜索、本地+云同步、语音转词 | `global-search-experience` |
| `xiaoqu-entry-handoff` | 问小趣快捷入口与 assistant handoff | `assistant` 消费，`global-search-experience` 组织入口 |

## 功能范围

### In Scope

- 统一全屏搜索首页与综合结果页。
- 按 `content / social relation / messages / circle` 组织综合结果。
- 首页级“问小趣”快捷入口，不在综合结果中混排 AI 结果。
- 最近搜索的本地和云同步语义。
- 语音 ASR 到文本 query。
- 圈子频道作为 facet 展示，而不是独立业务对象。

### Out of Scope

- AI 结果与站内结果统一混排。
- 语音语义理解、声纹、原始音频长期存储。
- 密信账号拆分与私密账号能力本身。
- 各域底层搜索索引、召回和排序实现。

## 约束

- 全局搜索必须是唯一允许的全屏全局浮层。
- “朋友”产品文案统一替换为“社交关系”。
- “频道”定义为 `Circle` 分类投影，不单列业务对象。
- 当前账号或登录子账号内的对象全部允许出现在搜索结果中；本期不在账号内再做细分权限裁剪。
- 最近搜索由用户手动清除前持续保留；自动过期时间后续统一治理。
- 问小趣 query 不进入最近搜索，只进入 assistant 对话。
- 发布策略为一把上线，不做双轨兼容；但需要整体回滚口径。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信搜索首页 | 搜索首页四段式信息架构 | 全量吸收 |
| 微信聊天/联系人搜索结果 | 分组展示与列表样式 | 吸收为消息/社交关系结果组织 |
| 微信内容搜索结果 | 内容结果 + 频道/分类并置 | 吸收为内容结果 + 圈子 facet |

## 角色分工

| 角色 | 职责 |
|---|---|
| `global-search-experience` | Journey 壳层、结果编排、历史、语音、问小趣入口 |
| `content` | 内容对象与内容详情跳转契约 |
| `messages` | 消息/会话结果契约 |
| `user` | 社交关系对象与查询真相源 |
| `circle` | 圈子与频道 facet 投影 |
| `assistant` | 问小趣会话接续与 assistant run 消费 |

## 既有 Story 覆盖矩阵

| 历史节点 / 原型 | 当前状态 | Journey 内新归属 |
|---|---|---|
| `contact-search-index` | 删除历史节点 | `social-relationship-search-contract` |
| `search-query-contract` | 删除历史节点 | `social-relationship-search-contract` |
| `GlobalSearchSheet` 原型 | 作为旧实现待替换 | `full-screen-search-shell-and-entry` |

## 数据生命周期合同

- 普通搜索 query：记录到最近搜索，并本地+云同步。
- 最近搜索字段至少包含：`query`、`scope`、`facet`、`timestamp`。
- 问小趣 query：不写入最近搜索；仅沉淀到 assistant 对话。
- 语音输入：只生成文本 query，不把原始音频纳入搜索历史主模型。

## 小趣 / 权限 / 分享边界

- 问小趣是搜索首页里的快捷入口，不属于综合搜索结果来源。
- 当前账号或当前登录子账号内的数据都允许进入搜索结果。
- 本期不提供搜索结果分享链路。
- 后续密信隔离和私密账号能力不在本 Journey 内处理。

## 非功能目标

### SLO

- 打开搜索首页后，首屏壳层即时可见。
- 输入 query 后，综合结果首批分组 P95 在 1.5s 内可见。
- 单个域超时后，允许该分组降级，不阻塞整页。

### KPI

- 搜索主路径完成率 > 95%。
- 结果点击进入详情成功率 > 99%。
- 历史搜索读写成功率 > 99%。

### 弱网与恢复

- 弱网下优先渲染壳层、指定搜索内容与最近搜索。
- 任一结果域失败时，只显示该域降级态，不导致搜索页整体失败。
- 语音权限被拒或 ASR 失败时，必须回退到手动输入，不允许卡死搜索入口。

### 并发与容量假设

- 一次综合查询最多 fan-out 到 4 个域。
- 各域首屏只返回少量结果，更多结果通过二跳页承接。
- 结果混排优先保证首批可见性，不在 Journey 阶段冻结复杂排序算法。

## 迁移、灰度与回滚要求

- 本期不保留历史搜索节点，不做并行治理。
- 不做双轨兼容；整体验收通过后统一上线。
- 若出现不可用、时延持续超标或重大稳定性问题，整体回退到旧搜索实现或整版发布回滚。

## 验收重点

1. 搜索首页、综合结果、历史、语音、问小趣形成完整 Journey，而不是分散功能点。
2. “社交关系”与“频道 facet” 的边界明确，不再复用旧 chat 搜索节点。
3. metadata 真相源边界清晰，可直接进入 `/design`。
