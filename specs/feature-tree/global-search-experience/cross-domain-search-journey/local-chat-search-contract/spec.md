# L3 Scenario: local-chat-search-contract

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `local-chat-search-contract`

## 背景与动机

记录上“联系人 / 社交关系 / 聊天记录”被混着使用，导致搜索中的“人”和“聊天”既没有统一对象边界，也没有统一执行位置。最新基线已经冻结：聊天相关对象在产品主路径上应由端侧本地搜索承接，而不是继续把云侧搜索接口作为主要语义。

## 目标用户

- 需要快速搜索联系人、会话和消息，并直接进入聊天上下文的用户。
- 在弱网、离线或云侧局部故障下，仍需要获得稳定聊天搜索结果的用户。

## 功能范围

- 冻结 `chat.contact`、`chat.conversation`、`chat.message` 的 canonical searchable object 定义。
- 冻结聊天搜索结果的最小展示字段、跳转字段与统一结果模型映射。
- 冻结聊天搜索为 `local_only` 执行策略。
- 冻结本地聊天搜索的账号隔离、删除同步与主动清理生命周期规则。

## Out of Scope

- 公开用户主页搜索与 profile ranking。
- 低存储设备的阈值、淘汰策略与自动压缩治理。
- 把云侧 `SearchContacts / SearchConversations / SearchMessages` 继续作为产品主入口。

## 约束

- 页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。
- `chat.contact / chat.conversation / chat.message` 全部是 `local_only` 对象。
- 搜索结果必须携带稳定会话定位信息，点击后可直接进入单聊或群聊上下文。
- 登出不清空本地搜索索引，但必须按 owner / sub account 分区隔离。
- 消息撤回、删除或用户显式清理时，必须同步删除对应本地索引项。
- 云端 `messages` 的 14 天 TTL 与端侧本地长期保留可不一致；本期端侧生命周期以“用户主动删除”为主。

## 对标输入与吸收结论

- 借鉴微信聊天搜索的对象直达与列表优先级，但不把“联系人”扩展回泛化的社交关系搜索。
- 吸收现有 chat 本地缓存与增量同步能力，作为本地搜索索引的主数据来源。

## 角色分工

- `messages`: 提供会话、消息、本地 snapshot 与删除同步真相源。
- `global-search-experience`: 负责结果分组、跳转语义与 Journey 消费。
- `search-provider-routing-and-storage-topology`: 提供 `local_only` 执行策略与对象注册真相源。

## 既有 Story 覆盖矩阵

| 记录节点 / 设计 | 处理 |
|---|---|
| `chat-conversation/contact-and-session-governance/contact-search-index` | 已删除记录节点，能力归并到本 Scenario |
| 旧社交关系搜索挂载 | 不再作为本 Journey 中“人”的主节点；本 Scenario 取代其聊天搜索主语义 |

## 数据生命周期合同

- 本地聊天搜索索引登出后保留。
- 本地索引按 owner / sub account 逻辑隔离。
- 端侧保留期当前不自动过期，主要依赖用户主动删除。
- 低存储设备的存储压力治理后续单独冻结，不阻塞本次 baseline。

## 小趣 / 权限 / 分享边界

- 本 Scenario 不处理 `小趣搜`。
- 本期不在账号内再做更细权限裁剪。
- 本期不提供聊天搜索结果的分享链路。

## 非功能目标

- 本地聊天搜索结果首批返回不依赖云侧查询成功。
- 本地索引命中应优先保证交互即时性。
- 子账号切换后，不得读到其他子账号的本地聊天索引结果。

## 迁移、灰度与回滚要求

- 不保留旧的“社交关系搜索”作为并行主路径。
- 若本地聊天搜索契约不稳定，整体回退到旧搜索实现，而不是重新暴露分域页面级接口。

## 验收重点

1. 聊天相关对象边界清晰：`contact / conversation / message` 统一为本地搜索对象。
2. 页面只消费统一 `search(request)`，不再直接消费聊天域搜索方法。
3. 本地搜索结果可稳定直达会话，账号隔离与删除同步语义清晰。
