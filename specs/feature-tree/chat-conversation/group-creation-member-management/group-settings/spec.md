# L3 Story：group-settings — 群聊设置与治理边界 (`group-settings`)

> 所属能力：[`group-creation-member-management`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “group-settings — 群聊设置与治理边界”的输入、可观察主路径、失败语义以及与父能力的交接。
- UpdateGroupGovernanceSettings（owner/admin）写 Conversation 权威字段并被 UpdateConversationTitle 授权消费。
- UpdateAnnouncement（owner/admin）写权威公告并经 system_announcement 消息触达全员。
- GetConversation / GroupHome 回读真实治理开关与公告（消灭硬编码空串假实现）
- 用户级 mute/pin 走 ConversationUserState.UpdateConversationSettings，与群治理单轨分离。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。
- 邀请链接、扫码入群和入群审批不在当前发布范围；设置页不得显示无权威对象支撑的假开关。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 group-settings — 群聊设置与治理边界

- 群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。

<a id="req-002"></a>
### REQ-002 群聊设置页不得承担对象级治理聚合页角色

- 群聊设置页不得承担对象级治理聚合页角色。
- 群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。
- 若用户已拉黑某成员，群设置页中仍可展示该成员基础占位，但必须在下游消费层阻断互动和实时沟通入口。
- 1v1 会话设置与群聊设置都应遵循“设置页用于会话管理，不用于动作型扩展能力”的统一原则。
- 如未来新增“举报群”，必须通过独立 metadata 与对象建模接入，不能在设置页先加一个临时入口占位。
- **禁止**：在全屏表单页使用帖子「更多功能」式 **描边大圆角卡片**（`selectionCardBorderRadius` + `blockBorderColor`）作为默认分组容器。
- **适用**：Feed/媒体上下文贴底 `MoreActionPopup` 等，归属 `content.post` 对象的 `presentation` 层，与全屏表单态区分，不得混用默认容器语义。
- 用户可见静态文案须 `UITextConstants` / l10n；群管理解散确认等 **禁止** 在业务 Dart 中硬编码中文（满足 `verify_dart_semantic`）。
- 群管理页为 **管理员专项** 全屏页，**不**纳入本节 GS1–GS5 的「普通成员设置」清单，但 **必须** 与 §9.1 使用同一套表单态组件与 token，保证与群聊信息页视觉一致。

<a id="req-003"></a>
### REQ-003 群治理设置、公告与用户偏好分离

- 系统必须群设置与治理：治理开关权威对象链（nameEditableByAdminOnly）、群公告权威化（公告即触达）、用户级 mute/pin 与治理设置分离，且失败时不得写入成功事实。
- 私建群管理员由群主通过成员治理命令设置，管理员最多 3 人；群主转让、管理员变更与解散都必须以 Conversation/ConversationMembership 的服务端事实为准。
- 圈子来源群不得走私建群解散、群主转让或管理员设置；页面必须显示所属 owner 的治理入口或 canonical 拒绝，不得本地伪造可写能力。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#UpdateGroupGovernanceSettings`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#UpdateAnnouncement`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/chat_conversation.yaml#ChatConversation`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/group_home.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 group-settings — 群聊设置与治理边界

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“group-settings — 群聊设置与治理边界”对应的公开行为。
- THEN 群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 管理员变更受角色与人数上限约束

- GIVEN 私建群群主通过 production Remote 读取当前成员与管理员事实，候选不包含群主本人，且当前管理员集合可回读。
- WHEN 群主选择不超过 3 名成员并提交管理员变更，或普通成员、圈子来源群与超过上限的选择尝试同一动作。
- THEN 合法变更通过 generated client 写入 canonical ConversationMembership，后续 Remote 读取的角色集合与服务端事实收敛，语义重放不重复推进版本。
- AND 越权、来源不符、人数超限或依赖失败返回 canonical failure，页面恢复提交前的管理员与 roster，不产生部分角色变更。

<a id="gwt-003"></a>
### GWT-003 群治理设置与解散由 Remote 回读收敛

- GIVEN 私建群 owner/admin 已从 GetConversation 或 GroupHome 读取当前治理开关，且只有群主可见解散动作。
- WHEN owner/admin 更新群治理设置，或群主确认解散后重新读取会话与消息首页。
- THEN 设置成功后以 Remote 返回的 Conversation/GroupHome 为准；解散成功后会话进入 canonical dissolved 终态并从可进入的消息列表收敛移除，同一意图重放不产生第二终态。
- AND 越权、圈子来源群、版本冲突或依赖失败时保留原设置与原会话状态，页面提供 canonical 恢复动作且不跳转到伪成功首页。

<a id="gwt-004"></a>
### GWT-004 群主转让按成员事实与版本收敛

- GIVEN 私建群群主从 production Remote roster 选择一名非群主成员，且页面持有提交前的 owner/admin/member 角色集合。
- WHEN 群主确认转让并发生成功、语义重放、并发治理或失败结果。
- THEN 成功与重放只产生一个新群主，后续 ListMembers 与 roster revision 读取收敛到同一角色集合，原群主不再保留 owner 权限。
- AND 越权、无效目标、来源不符、并发冲突或依赖失败时页面回滚到提交前角色集合并刷新服务端事实，不保留本地半转让状态。

<a id="gwt-005"></a>
### GWT-005 群公告以同一意图写入并由 Conversation 权威回读

- GIVEN 私建群 owner/admin 已从 production Remote 读取当前公告，且页面持有本次编辑的稳定意图身份。
- WHEN owner/admin 提交新公告、重放同一意图，或发生越权、会话不存在与依赖失败。
- THEN generated client 只调用 UpdateAnnouncement，成功与同意图重放返回同一 Conversation 公告事实，随后 GetConversation 权威回读公告内容与更新身份；服务端另以 canonical `system_announcement` 消息负责成员触达，App 不本地合成触达成功。
- AND 失败返回 canonical failure，保留提交前公告并允许用户重试同一意图，不写入或展示伪成功公告。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 群治理页面 production Remote UAT 尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺验收证据：同一候选下真实群主、管理员与普通成员完成成功、越权、并发及失败恢复的双端用户验收结果；现有源码只表达 production Remote 路径，不能替代该结果。
- 完成判定：`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005` 均由 production Remote user_acceptance 直接绑定，并分别取得 Android 与 iPhone physical ResultBundle；缺环境、身份、Provider 或候选摘要时保持 BLOCK。
