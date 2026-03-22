# L1 Capability: global-search-experience

## 节点定位

- `L1_capability`: `global-search-experience`

该节点是 App 内统一搜索入口、跨域结果编排、搜索历史与问小趣 handoff 的唯一能力归属。
它不再挂靠 `discovery-content`，也不再沿用 `chat-conversation/contact-and-session-governance/contact-search-index*` 这类历史节点。

## 背景与动机

当前搜索能力存在四个结构性问题：

1. 入口分散：首页、聊天、圈子、助手的搜索入口不一致，且绝大多数页面没有统一全局搜索入口。
2. 壳层失真：现有 `GlobalSearchSheet` 仍是原型态，本质是本地 mock 数据过滤，没有形成可商用的全屏全局搜索体验。
3. 领域边界漂移：联系人搜索只在 chat 域有 `SearchContacts`，但产品语义已经明确为“社交关系”，不能继续把“人”挂死在 chat 域。
4. 历史节点失效：旧的 chat 搜索节点只覆盖联系人局部能力，无法承接内容、圈子、消息、社交关系和问小趣统一入口。

本次 PRD 的目标，是把“全局搜索”从历史局部能力中抽离，升级为独立一级能力域。

## 目标用户

- 需要从任一一级页面快速查找内容、消息、圈子和社交关系的活跃用户。
- 习惯用微信式搜索首页完成“输入即搜、指定类型搜、查看最近搜索”的高频用户。
- 需要在站内搜索失败时快速切到“问小趣”的用户。
- 需要在不增加额外学习成本的前提下统一维护搜索路由、埋点、请求上下文和结果编排的平台与前端团队。

## 能力边界

`global-search-experience` 负责：

- 全局搜索的全屏壳层、一级入口、默认上下文与返回路径。
- 跨 `content / messages / social relation / circle` 的统一查询体验与结果组织。
- 搜索历史的本地存储与云端同步语义。
- 搜索页内的语音 ASR 到文本查询转换。
- “问小趣”快捷入口与 assistant 会话 handoff。
- 搜索相关 `route / surface / request_context` 的 metadata 真相源收口。

`global-search-experience` 不负责：

- 各领域底层索引实现、倒排/向量引擎选型与存储细节。
- 助手 runtime / skill / tool / prompt 的垂类逻辑改造。
- 密信账号分割、私密账号策略本身。
- 各业务详情页自身的页面内二级搜索。

## 关键 Journey

本 L1 当前冻结 1 个 `L2_journey`：

| L2 Journey | 说明 |
|---|---|
| `cross-domain-search-journey` | 从任一一级入口进入全屏搜索，完成指定类型搜索、综合结果浏览、最近搜索管理、语音转词与问小趣跳转 |

## 领域服务与业务对象

| 领域 | 业务对象 | 本 L1 角色 |
|---|---|---|
| `content/post` | `Post`、`Comment`、文章/图片/视频/动态内容投影 | 作为内容结果来源 |
| `messages/conversation` | `Conversation`、`Message` | 作为消息与会话结果来源 |
| `social/circle` | `Circle`、`CircleSectionConfig`、分类投影 | 作为圈子与频道 facet 结果来源 |
| `user/user_profile` + `user/follow_edge` | `UserProfile`、`ProfileSubject`、社交关系读模型 | 作为“社交关系”结果来源 |
| `assistant/assistant_run` | `AssistantRun` | 作为“问小趣” handoff 目标，不参与综合结果混排 |
| `_shared` metadata | `app_routes`、`ui_surfaces`、`request_context` | 作为全局搜索路由、surface、page context 真相源 |

## 功能范围

### In Scope

- 新建独立 `L1_capability`，承接全局搜索全部产品与文档治理。
- 全屏搜索首页：搜索框、问小趣入口、语音按钮、指定搜索内容、最近搜索。
- 综合结果页：按内容、社交关系、消息、圈子与频道 facet 分组。
- 社交关系搜索：不再沿用 chat contact 的产品命名。
- 频道能力：明确为 `Circle` 分类投影，不新建独立业务对象。
- 历史搜索同步：本地存储 + 云端同步，用户手动清除前持续保留。
- 语音入口：只做 ASR 转搜索词。

### Out of Scope

- AI 搜索结果混排。
- 语音语义理解、语音直达助手推理。
- 密信按账号隔离的后续扩展。
- 独立 `channel` 主实体与新领域服务。
- 搜索引擎、ES/向量库/召回算法的技术实现细节。

## 约束与适用边界

- 全局搜索必须遵循 `/.cursor/rules/07-ios-native-ux.mdc`，作为唯一允许的全屏全局浮层。
- `path / operation / surface / route / decoder context` 必须以 metadata 为唯一真相源。
- “朋友”产品语义统一改为“社交关系”。
- “频道”只允许作为圈子分类投影，不允许在 PRD 中升级为独立对象。
- 助手入口只能作为 typed handoff，不能靠字符串匹配在 runtime 内分流。
- 本次按“一把上线”处理，不保留历史搜索节点并行治理。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信搜索首页 | 全屏壳层、顶部搜索框、指定搜索内容、最近搜索 | 全量吸收为搜索首页基线 |
| 微信聊天/联系人搜索结果 | 搜索结果按对象类型展示、聊天与人分组 | 吸收为消息/社交关系结果组织方式 |
| 微信内容搜索结果 | 内容结果与频道/分类联合展示 | 吸收为内容结果 + 圈子分类投影联动 |

## 角色分工

| 角色 | 职责 |
|---|---|
| `global-search-experience` | 产品体验、全局壳层、跨域编排、历史与 handoff 治理 |
| `content` | 提供内容搜索对象与结果跳转契约 |
| `messages` | 提供消息/会话结果对象与消息命中跳转契约 |
| `user` | 提供社交关系搜索真相源 |
| `circle` | 提供圈子结果与分类投影 |
| `assistant` | 提供问小趣会话 handoff |
| `_shared` metadata | 承载路由、surface、request context 真相源 |

## 既有 Story 覆盖矩阵

| 历史节点或实现 | 处理方式 | 新归属 |
|---|---|---|
| `chat-conversation/contact-and-session-governance/contact-search-index` | 从特性树删除，不再保留 | `social-relationship-search-contract` |
| `chat-conversation/contact-and-session-governance/contact-search-index--search-query-contract` | 从特性树删除，不再保留 | `social-relationship-search-contract` + `multi-domain-result-composition` |
| 现有 `GlobalSearchSheet` 原型 | 保留为待替换实现，不再作为产品真相源 | `full-screen-search-shell-and-entry` |

## 数据生命周期合同

- 最近搜索记录为 `query + scope + facet + timestamp` 的组合。
- 最近搜索同时落本地与云端；本期不冻结自动过期时间，用户主动清除前持续保留。
- “问小趣”产生的 query 不进入最近搜索；对应内容只保存在小趣私人助手对话中。
- 语音输入只生成文本搜索词，不额外保存原始音频作为搜索历史的一部分。

## 小趣 / 权限 / 分享边界

- 当前账号或当前登录子账号可见范围内的对象，都允许出现在搜索结果中。
- 本期不在账号内部再做更细权限裁剪；后续密信通过账号分割解决。
- “问小趣”仅作为入口，不在综合结果中与站内结果混排。
- 本期不引入搜索结果对外分享链路。

## 非功能目标

### SLO / KPI

- 搜索页打开即时完成，最近搜索与指定搜索内容优先可见。
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
2. 搜索首页、结果页、历史、语音和问小趣入口在同一 Journey 内完成收口。
3. “社交关系”与“频道 facet” 的对象边界冻结，不再模糊挂靠旧节点。
4. 历史搜索节点从特性树统一清理，不再保留平行旧路径。
