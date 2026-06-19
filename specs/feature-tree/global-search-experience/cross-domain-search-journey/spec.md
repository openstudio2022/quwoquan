# L2 Journey: cross-domain-search-journey

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `cross-domain-search-journey`

该 Journey 冻结从任一一级页面进入两段式全屏搜索，到完成初始记录浏览、实时联想、独立网络结果浏览、最近搜索管理、语音转词与 `小趣搜` assistant 结果查看的完整链路。

## 背景与动机

当前 App 搜索体验的问题不在于“没有搜索框”，而在于没有统一 Journey：

1. 首页、聊天、群组和助手没有同一套搜索首页、联想页与网络结果页。
2. 当前搜索结果主要依赖本地 mock 过滤，缺乏稳定的两段式跨域搜索体验。
3. “联系人/聊天记录/用户关系”边界在产品和领域层不一致。
4. `群组` 已成为首页与搜索中的统一用户词，但网络结果页仍停留在“圈子频道”提法，造成入口与结果面认知不一致。
5. 小趣搜、最近搜索与站内搜索是分散设计，未形成统一用户旅程。
6. 聊天对象、本地搜索、群组 fallback 与云侧搜索拓扑缺少统一治理，导致体验与架构容易分叉。

## 目标用户

- 高频在站内找联系人、找聊天记录、找内容、找群组结果的用户。
- 习惯通过搜索页先看联想结果、再进入网络结果页的用户。
- 希望在同一个搜索 query 下查看 `小趣搜` assistant 结果的用户。
- 需要语音转文本进行检索的移动端用户。

## 核心旅程

1. 用户从首页、聊天页、群组页或助手页点击搜索入口。
2. App 打开统一的全屏搜索首页初始态，显示搜索框与 `最近在搜` 双列卡片，并允许进入记录管理态。
3. 用户输入关键词后，当前页切换到实时联想态，严格按 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段展示。
4. 用户点击联系人或聊天记录项时直接进入对应单聊/群聊；点击“更多联系人/更多聊天记录”只在当前页内联展开列表，不跳到新的中间页。
5. 用户点击“搜索网络结果”后进入独立网络结果页，顶部保留搜索框，并以 `小趣搜 + 群组分类 facet` 作为顶层 tab。
6. 用户在网络结果页切换 `小趣搜` 或群组分类 facet，查看 assistant 摘要/引用或对应分类内容结果；普通搜索 query 进入最近搜索。

## 2026-06-16 双阶段口径对齐（取代旧「四段联想 / 群组分类 facet」表述）

本节把本 Journey 的旧描述（`最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段联想、`小趣搜 + 群组分类 facet` 顶层 Tab）统一收口到 L1 spec 已冻结的现行两阶段模型。凡上文「核心旅程」「功能范围」与本节冲突处，以本节为准。

### suggest 阶段（本地快速检索）

- 输入过程中只做**本地快速检索**，定位用户已有对象：严格按 `联系人 / 聊天记录 / 已加入圈子 / 已关注地点 / 已关注的人 / 推荐搜索词` 组织；无命中分组隐藏。
- 命名空间限定在本地：`chat.contact / chat.conversation / chat.message`（`local_only`）与 `circle.group` 本地全量；未连接圈子、未关注地点、未连接的人，以及图片/视频/长文正式结果不得出现。
- 点击联系人 / 聊天记录直达对应单聊 / 群聊；「更多」只在当前页内联展开，不跳中间页。
- 交互反馈对标微信搜索：输入后本地分段应即时替换默认态；键盘保持焦点；点击“搜索网络结果”前不得因云侧慢请求卡住输入、删除或返回。
- App 可保留本地 query/session 上下文用于最近搜索、归因和 AB 粘性，但不得把 suggest 本地 hit 作为 result 数据源。

### result 阶段（云侧最终结果，固定 Tab）

- 点击搜索后进入独立网络结果页，顶部保留搜索框，固定 Tab 为 `小趣 ｜ 全部 ｜ 交集 ｜ 图片 ｜ 视频 ｜ 长文`，默认进入 `全部`。
- `result` 阶段**最终结果只来自云侧**：`content.post / entity.homepage / location.place / 相关搜索词 / 小趣`；本地对象不进入 result。
- `全部` Tab 分已连接区（每类一组）与发现区（同类成组、按比例混排、无查看更多）；`交集` Tab 展示交集概览 + 推荐区 + 发现流，每卡展示交集原因；`图片 / 视频 / 长文` 只展示对应消费流；`小趣` 为独立 assistant 结果页，不参与 `全部` 混排。
- 结果页可以保留上一页路由栈，但数据与 finder/测试必须 scoped 到 `SearchNetworkResultsPage`；offstage suggest 命中不视为 result 命中。

### 旅程状态覆盖（加载 / 空态 / 错误 / 降级 / 权限 / 最近搜索管理）

| 状态 | suggest 阶段 | result 阶段 |
|---|---|---|
| 加载态 | 本地检索即时；壳层与最近搜索优先可见 | 首批分组 P95 ≤ 1.5s；各 Tab 分域加载，互不阻塞，加载中显骨架/占位 |
| 空态 | 无命中分组隐藏；全部为空显示「最近在搜」回落 | 单 Tab 无结果显空态文案；全部为空回落到相关搜索词与最近搜索 |
| 错误态 | 本地检索异常回退到最近搜索，不卡死入口 | 单域失败显该域错误占位，整页仍可用 |
| 降级态 | — | 远端降级 / 能力受限时由 `degradeSignals` 驱动降级横幅（当前 `_buildDegradeBanner()` 仍是死逻辑，登记为 R-002 / WP-B） |
| 权限态 | 语音权限被拒回退手动输入；账号 / 子账号隔离生效 | 仅展示当前账号 / 登录子账号可见对象 |
| 最近搜索管理 | 记录页支持进入管理态、单条删除与清空；记录 `query + launch_context + category_context + timestamp` | 普通 query 进入最近搜索，本地 + 云同步 |

### 埋点与归因链

- 搜索默认页 / 结果页必须有曝光、停留、`referralSource`、`feedRequestId` 归因链；当前埋点核实属待办（R-007 / WP-B），是漏斗与推荐归因闭环前置。
- 点击本地 suggest hit、点击“搜索网络结果”、切换结果 Tab、点击 result hit、点击相关搜索词、点击 `小趣` citation 均必须保留 query/session/request 关联，避免搜索词热力、Feed 推荐归因和 AB 分析断链。

### `/plan-review` 补充：商用 UX / 性能 / 准确性门槛

| 维度 | 要求 | 验收 |
|---|---|---|
| 过程动效 | suggest 输入变化即时；result 跳转显示骨架/加载态；错误/重试不丢 query；最近搜索管理有明确进入/退出态 | T4 journey + widget pump 覆盖加载、错误、重试、最近搜索 |
| 空态/错误/降级/权限 | 四态齐全，且 typed error/degrade 驱动；语音权限拒绝回手动输入；远端单域错误不阻塞整页 | `AppPageErrorState` retry、degrade banner、权限态用例 |
| 触控与可访问 | 结果卡、Tab、清除按钮、重试按钮符合最小触控热区；语义文案来自 `UITextConstants`/l10n | 页面质量矩阵 P1-P8 + 语义门禁 |
| 弱网与并发 | 连续输入只保留最新 query；旧请求晚返回不能覆盖新结果；云 result 超时可恢复 | provider/widget 测试 + T3 弱网/timeout 验证 |
| 准确性 | result 排序原因可见/可追溯；同 query 在稳定版本下不跳变；本地对象不污染云侧 TopN | rankReasons/rankPosition 断言 + repeatability golden + result-only negative 断言 |

## 特性树拆分

本 Journey 冻结为 6 个 `L3_story`：

| L3 Scenario | 负责的问题 | 归属域 |
|---|---|---|
| `full-screen-search-shell-and-entry` | 初始记录页、实时联想页、统一入口、默认上下文、返回路径 | `global-search-experience` |
| `multi-domain-result-composition` | 联想分段与独立网络结果页编排 | `global-search-experience` |
| `local-chat-search-contract` | 本地联系人 / 会话 / 消息搜索对象边界、账号隔离与会话直达契约 | `messages` 主导，`global-search-experience` 消费 |
| `circle-facet-search-and-filter` | 网络结果页群组分类 facet 与内容过滤 | `circle` 主导，`global-search-experience` 消费 |
| `recent-search-sync-and-voice-asr` | 最近搜索、本地+云同步、记录管理态、语音转词 | `global-search-experience` |
| `xiaoqu-entry-handoff` | `小趣搜` assistant 结果 tab 与后续 assistant continuation | `assistant` 主导，`global-search-experience` 消费 |

## 功能范围

### In Scope

- 统一全屏搜索首页初始态、实时联想态（suggest 本地）与独立网络结果页（result 云侧）。
- suggest 阶段按 `联系人 / 聊天记录 / 已加入圈子 / 已关注地点 / 已关注的人 / 推荐搜索词` 组织本地联想（详见「2026-06-16 双阶段口径对齐」）。
- result 阶段网络结果页固定 Tab `小趣 ｜ 全部 ｜ 交集 ｜ 图片 ｜ 视频 ｜ 长文`，最终结果只来自云侧 `content.post / entity.homepage / location.place / 相关搜索词 / 小趣`。
- 搜索里的用户面向结果类型统一叫 `群组`，内部由 circle 域继续提供结果与分类投影。
- 最近搜索的本地和云同步语义。
- 语音 ASR 到文本 query。

### Out of Scope

- assistant 结果进入联想页四段混排。
- 语音语义理解、声纹、原始音频长期存储。
- 密信账号拆分与私密账号能力本身。
- 各域底层搜索索引、召回和排序实现。

## 约束

- 全局搜索必须是唯一允许的全屏全局浮层。
- 联想页中的“人”结果本期冻结为“联系人”，且点击目标必须是会话而不是用户主页中间页。
- 首页与搜索中的统一用户词必须是 `群组`。
- “群组分类 facet” 定义为 `Circle` 分类投影，不单列业务对象。
- 当前账号或登录子账号内的对象全部允许出现在搜索结果中；本期不在账号内再做细分权限裁剪。
- 最近搜索由用户手动清除前持续保留；自动过期时间后续统一治理。
- `小趣搜` 必须提供真实 assistant 搜索结果，不能只保留占位 handoff。
- 发布策略为一把上线，不做双轨兼容；但需要整体回滚口径。
- 本 Journey 统一消费 `search(request)` canonical contract，不再向页面暴露分域搜索方法名。
- `chat.contact / chat.conversation / chat.message` 由端侧本地搜索 provider 承担；`circle.group` 在旅程内允许云优先、本地 fallback。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信搜索首页 | 顶部搜索框、最近搜索、输入后实时联想 | 全量吸收为两段式搜索基线 |
| 微信聊天/联系人搜索结果 | 联系人与聊天记录分段、更多后页内扩展 | 吸收为联想页结构与会话直达方式 |
| 微信内容搜索结果 | 内容结果 + 分类并置 | 吸收为网络结果页与群组分类 facet |

## 角色分工

| 角色 | 职责 |
|---|---|
| `global-search-experience` | Journey 壳层、联想编排、网络结果页、记录、语音 |
| `content` | 内容对象与内容详情跳转契约 |
| `messages` | 本地联系人/会话/消息搜索对象与会话直达契约 |
| `user` | 当前不作为搜索 Journey 中“人”的主搜索对象，仅保留身份补充与后续扩展真相源 |
| `circle` | 群组结果与群组分类 facet 投影 |
| `assistant` | `小趣搜` assistant 结果、引用与后续会话接续 |
| `search-provider-routing-and-storage-topology` | 提供 canonical contract、execution mode 与 fallback 策略真相源 |

## 既有 Story 覆盖矩阵

| 记录节点 / 原型 | 当前状态 | Journey 内新归属 |
|---|---|---|
| `contact-search-index` | 删除记录节点 | `local-chat-search-contract` |
| `search-query-contract` | 删除记录节点 | `local-chat-search-contract` |
| `GlobalSearchSheet` 原型 | 作为旧实现待替换 | `full-screen-search-shell-and-entry` |

## 数据生命周期合同

- 普通搜索 query：记录到最近搜索，并本地+云同步。
- 最近搜索字段至少包含：`query`、`launch_context`、`category_context`、`timestamp`。
- `小趣搜` 复用当前 query 拉取 assistant 结果，不额外新增一套 AI 记录模型；若后续进入 assistant 对话，则仅由 assistant 保存该会话。
- 语音输入：只生成文本 query，不把原始音频纳入搜索记录主模型。

## 小趣 / 权限 / 分享边界

- `小趣搜` 是独立网络结果页左侧 tab，不属于联想页实时分组来源。
- 当前账号或当前登录子账号内的数据都允许进入搜索结果。
- 本期不提供搜索结果分享链路。
- 后续密信隔离和私密账号能力不在本 Journey 内处理。

## 非功能目标

### SLO

- 打开搜索首页后，首屏壳层即时可见。
- 输入 query 后，`suggest` 本地首批分段即时可见，不等待云侧；本地异常时回落最近搜索。
- 点击“搜索网络结果”后，云侧 `result` 首批分组 P95 ≤ 1.5s；P99/错误率/降级率按 `search_slo.yaml#load_model`。
- 单个域超时后，允许该分组降级，不阻塞整页；整页错误必须有重试恢复动作。

### KPI

- 搜索主路径完成率 > 95%。
- 结果点击进入详情成功率 > 99%。
- 记录搜索读写成功率 > 99%。

### 弱网与恢复

- 弱网下优先渲染壳层、最近搜索与首批联想结果。
- 任一结果域失败时，只显示该域降级态，不导致搜索页整体失败。
- 语音权限被拒或 ASR 失败时，必须回退到手动输入，不允许卡死搜索入口。

### 并发与容量假设

- 实时联想页只返回少量联系人/聊天记录/最常使用项；更多联系人与更多聊天记录通过页内展开承接。
- 网络结果页按 tab 分域加载，`小趣搜` 与群组分类结果互不阻塞。
- Journey 不另起排序算法，严格消费 provider/topology 的统一 ranking pipeline；排序准确性、可重复性、term-heat、AB 分桶归 `search-provider-routing-and-storage-topology` 验收。
- 弱网下网络请求可取消/超时/重试；异步响应必须按 query/requestId 防乱序覆盖。

## 迁移、灰度与回滚要求

- 本期不保留记录搜索节点，不做并行治理。
- 不做双轨兼容；整体验收通过后统一上线。
- 若出现不可用、时延持续超标或重大稳定性问题，整体回退到旧搜索实现或整版发布回滚。

## 验收重点

1. 搜索首页初始态、实时联想、独立网络结果页、记录管理态与 `小趣搜` 结果形成完整 Journey，而不是分散功能点。
2. “联系人直达会话”与“群组分类 facet tab” 的边界明确，不再复用旧 chat 搜索节点。
3. metadata 真相源边界清晰，可直接进入 `/design`。
4. suggest/result 两阶段体验可测：本地缓存命中即时、云侧最终结果独立、本地对象不进 result。
5. 加载 / 空态 / 错误 / 降级 / 权限 / 最近搜索管理 / 埋点归因链均有 T2/T4 证据。
