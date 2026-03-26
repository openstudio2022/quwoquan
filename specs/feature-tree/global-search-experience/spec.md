# L1 Capability: global-search-experience

## 节点定位

- `L1_capability`: `global-search-experience`

该节点是 App 内统一搜索入口、两段式搜索建议、独立网络结果页、搜索历史与“小趣搜” assistant 结果的唯一能力归属。
它不再挂靠 `discovery-content`，也不再沿用 `chat-conversation/contact-and-session-governance/contact-search-index*` 这类历史节点。

## 背景与动机

当前搜索能力存在四个结构性问题：

1. 入口分散：首页、聊天、群组、助手的搜索入口不一致，且绝大多数页面没有统一全局搜索入口。
2. 壳层失真：现有 `GlobalSearchSheet` 仍是原型态，本质是本地 mock 数据过滤，没有形成可商用的全屏全局搜索体验。
3. 领域边界漂移：最新 UX 已冻结“联系人直达会话”，但历史文档仍混用联系人、社交关系与用户主页搜索，导致 contract 挂载混乱。
4. 历史节点失效：旧的 chat 搜索节点只覆盖联系人局部能力，无法承接内容、群组、聊天记录、网络结果页与 `小趣搜` assistant 结果统一入口。

本次 PRD 的目标，是把“全局搜索”从历史局部能力中抽离，升级为独立一级能力域，并把首页与搜索中的用户词统一收口为 `群组`。

## 目标用户

- 需要从任一一级页面快速查找联系人、聊天记录、内容与群组结果的活跃用户。
- 习惯用微信式两段搜索体验完成“先联想、再进入网络结果页”的高频用户。
- 需要在站内搜索后继续查看“小趣搜” assistant 结果的用户。
- 需要在不增加额外学习成本的前提下统一维护搜索路由、埋点、请求上下文和结果编排的平台与前端团队。

## 能力边界

`global-search-experience` 负责：

- 全局搜索的全屏壳层、一级入口、默认上下文与返回路径。
- 两段式搜索体验：初始历史页、输入后的实时联想页、以及独立网络结果页。
- 联系人/聊天记录直达会话、网络结果进入独立结果页的统一跳转语义。
- 搜索里的 `群组` 结果类型，以及网络结果页内 `小趣搜 + 群组分类 facet` 的顶层组织。
- 搜索历史的本地存储与云端同步语义。
- 搜索页内的语音 ASR 到文本查询转换。
- “小趣搜” assistant 结果与引用跳转语义。
- 搜索相关 `route / surface / request_context` 的 metadata 真相源收口。

`global-search-experience` 不负责：

- 各领域底层索引实现、倒排/向量引擎选型与存储细节。
- 助手 runtime / skill / tool / prompt 的垂类逻辑改造。
- 密信账号分割、私密账号策略本身。
- 各业务详情页自身的页面内二级搜索。
- 面向用户新增“实体”作为新的搜索总类目。

## 关键 Journey

本 L1 当前冻结 1 个 `L2_journey`：

| L2 Journey | 说明 |
|---|---|
| `cross-domain-search-journey` | 从任一一级入口进入两段式全屏搜索，完成历史管理、实时联想、网络结果浏览、最近搜索同步与小趣搜 assistant 结果查看 |

## 领域服务与业务对象

| 领域 | 业务对象 | 本 L1 角色 |
|---|---|---|
| `content/post` | `Post`、`Comment`、文章/图片/视频/动态内容投影 | 作为内容结果来源 |
| `messages/conversation` | `Conversation`、`Message` | 作为消息与会话结果来源 |
| `social/circle` | `Circle`、`CircleSectionConfig`、分类投影 | 作为群组结果与群组分类 facet 的真相源 |
| `user/user_profile` + `user/follow_edge` | `UserProfile`、`ProfileSubject`、身份补充读模型 | 作为联系人身份补充与后续扩展来源 |
| `assistant/assistant_run` | `AssistantRun`、assistant 搜索结果/引用投影 | 作为网络结果页左侧 `小趣搜` tab 的结果来源，并承接后续 assistant continuation |
| `_shared` metadata | `app_routes`、`ui_surfaces`、`request_context` | 作为全局搜索路由、surface、page context 真相源 |

## 功能范围

### In Scope

- 新建独立 `L1_capability`，承接全局搜索全部产品与文档治理。
- 全屏搜索首页初始态：搜索框、`最近在搜` 双列卡片、展开、垃圾桶进入历史管理态。
- 输入后的实时联想页：严格按 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段组织。
- 联系人、聊天记录各默认展示 3 条，并支持在当前页内联展开更多后直接跳转会话。
- 独立网络结果页：顶部保留搜索框，顶部 tab 为 `小趣搜 + 群组分类 facet`。
- 用户面向的结果类型统一显示为 `群组`；其分类 facet 仍由 `Circle` 域输出，不新建独立业务对象。
- 历史搜索同步：本地存储 + 云端同步，用户手动清除前持续保留。
- 语音入口：只做 ASR 转搜索词。

### Out of Scope

- AI 结果进入联想页四段混排。
- 语音语义理解、语音直达助手推理。
- 密信按账号隔离的后续扩展。
- 独立 `channel` 主实体与新领域服务。
- 搜索引擎、ES/向量库/召回算法的技术实现细节。

## 约束与适用边界

- 全局搜索必须遵循 `/.cursor/rules/07-ios-native-ux.mdc`，作为唯一允许的全屏全局浮层。
- `path / operation / surface / route / decoder context` 必须以 metadata 为唯一真相源。
- 当前两段式搜索首段“人”结果统一展示为“联系人”，并以直达会话为主。
- 首页和搜索中的统一用户词必须是 `群组`。
- “群组分类 facet” 只允许作为 circle 域分类投影，不允许在 PRD 中升级为独立对象。
- `小趣搜` 必须通过 assistant typed contract 提供真实结果，不能退回为字符串 handoff 占位。
- 本次按“一把上线”处理，不保留历史搜索节点并行治理。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信搜索首页 | 全屏壳层、顶部搜索框、最近搜索、实时联想 | 吸收为两段式搜索基线 |
| 微信聊天/联系人搜索结果 | 联系人与聊天记录分段、页内展开更多 | 吸收为联想页结构与直达会话交互 |
| 微信内容搜索结果 | 内容结果与分类联合展示 | 吸收为独立网络结果页与群组分类 facet 联动 |

## 角色分工

| 角色 | 职责 |
|---|---|
| `global-search-experience` | 产品体验、全局壳层、两段式联想编排、历史与网络结果治理 |
| `content` | 提供内容搜索对象与结果跳转契约 |
| `messages` | 提供联系人/聊天记录结果对象与会话直达契约 |
| `user` | 提供用户身份补充信息与后续人关系扩展真相源 |
| `circle` | 提供群组结果与群组分类 facet 投影 |
| `assistant` | 提供 `小趣搜` assistant 结果、摘要与引用 |
| `_shared` metadata | 承载路由、surface、request context 真相源 |

## 既有 Story 覆盖矩阵

| 历史节点或实现 | 处理方式 | 新归属 |
|---|---|---|
| `chat-conversation/contact-and-session-governance/contact-search-index` | 从特性树删除，不再保留 | `social-relationship-search-contract` |
| `chat-conversation/contact-and-session-governance/contact-search-index--search-query-contract` | 从特性树删除，不再保留 | `social-relationship-search-contract` + `multi-domain-result-composition` |
| 现有 `GlobalSearchSheet` 原型 | 保留为待替换实现，不再作为产品真相源 | `full-screen-search-shell-and-entry` |

## 数据生命周期合同

- 最近搜索记录为 `query + launch_context + category_context + timestamp` 的组合。
- 最近搜索同时落本地与云端；本期不冻结自动过期时间，用户主动清除前持续保留。
- `小趣搜` 复用当前全局搜索 query，不额外新增一套 AI query 历史模型；若用户继续进入 assistant 对话，对话内容保存在小趣私人助手会话中。
- 语音输入只生成文本搜索词，不额外保存原始音频作为搜索历史的一部分。

## 小趣 / 权限 / 分享边界

- 当前账号或当前登录子账号可见范围内的对象，都允许出现在搜索结果中。
- 本期不在账号内部再做更细权限裁剪；后续密信通过账号分割解决。
- `小趣搜` 仅存在于独立网络结果页左侧 tab，不进入联系人/聊天记录实时联想分组。
- 本期不引入搜索结果对外分享链路。

## 非功能目标

### SLO / KPI

- 搜索页打开即时完成，最近搜索与初始壳层优先可见。
- 用户输入查询后，首批分组结果 P95 在 1.5s 内可见。
- 单域失败不阻塞其它分组返回。
- 搜索主路径完成率目标 > 95%。

### 弱网 / 并发 / 容量

- 默认按移动弱网场景设计。
- 一次综合搜索最多 fan-out 到 `content / user-social / messages / circle` 四个域。
- 首屏各分组只返回少量结果，更多结果通过二跳页面承接。

## 迁移、灰度与回滚要求

- 本期不保留历史节点并行治理，也不做双轨兼容方案。
- 发布方式为整体验收后一把上线。
- 如出现搜索不可用、首批结果时延持续超标或崩溃率异常升高，回滚粒度为整体验收回退到旧搜索实现或整版发布回滚。

## 验收重点

1. 全局搜索成为独立一级能力，而非内容或聊天的附属能力。
2. 搜索首页初始态、联想态、网络结果页、小趣搜结果与历史管理在同一 Journey 内完成收口。
3. “联系人直达会话”和“群组分类 facet tab” 的对象边界冻结，不再模糊挂靠旧节点。
4. 历史搜索节点从特性树统一清理，不再保留平行旧路径。
