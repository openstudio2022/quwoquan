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
- **适用**：Feed/媒体上下文贴底 `MoreActionPopup` 等，归属 `lib/components/settings_conversation/`，与全屏表单态区分，不得混用默认容器语义。
- 用户可见静态文案须 `UITextConstants` / l10n；群管理解散确认等 **禁止** 在业务 Dart 中硬编码中文（满足 `verify_dart_semantic`）。
- 群管理页为 **管理员专项** 全屏页，**不**纳入本节 GS1–GS5 的「普通成员设置」清单，但 **必须** 与 §9.1 使用同一套表单态组件与 token，保证与群聊信息页视觉一致。

<a id="req-003"></a>
### REQ-003 群治理设置、公告与用户偏好分离

- 系统必须群设置与治理：治理开关权威对象链（nameEditableByAdminOnly）、群公告权威化（公告即触达）、用户级 mute/pin 与治理设置分离，且失败时不得写入成功事实。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#UpdateGroupGovernanceSettings`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#UpdateAnnouncement`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/chat_group_settings_client.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/group_home.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 group-settings — 群聊设置与治理边界

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“group-settings — 群聊设置与治理边界”对应的公开行为。
- THEN 群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
