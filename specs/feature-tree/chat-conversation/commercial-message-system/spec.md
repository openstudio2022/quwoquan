# L2 Business Capability：商用消息体系 (`commercial-message-system`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

让消息页、联系页、群主页、交集摘要和互动通知只消费真实云端事实，并在失败时提供明确恢复结果。

## 2. 范围与非目标

### In Scope

- 消息模块内的独立消息页与联系页 IA。
- 消息页全部/未读/群聊/私聊/通知筛选。
- 联系页全部/互关/圈子/群聊筛选。
- Entity/Circle/Group/Conversation/Contact/Intersection/Notification 对象边界。
- 群头像云端预合成、点击群进聊天、聊天信息页群主页能力入口。
- 商用路径 Remote-only 与真实服务 read model。

### Out of Scope

- 新增底栏入口。
- 端到端加密。
- 群对象拉黑。
- 旧 Mock/Prototype 数据继续作为生产能力。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-008`](../../spec.md#scn-008)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：以商用发布为目标，验证消息页、联系页、群主页、交集、通知和真实云端数据的一致性。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`commercial-remote-only-message-system`](./commercial-remote-only-message-system/spec.md)：商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。
- [`contact-home-commercial-ia`](./contact-home-commercial-ia/spec.md)：页面入口和联系首页数据消费继续由消息域 metadata 真相源驱动。
- [`contact-home-relationship-projection`](./contact-home-relationship-projection/spec.md)：联系首页 read model 与交集摘要字段均有稳定契约来源。
- [`group-home-chat-info-contract`](./group-home-chat-info-contract/spec.md)：群聊天页和聊天信息页都能从同一 GroupHome metadata / DTO 来源取数。
- [`interaction-notification-inbox`](./interaction-notification-inbox/spec.md)：统一互动通知的渲染、跳转、已读状态与曝光/点击事件。
- [`message-home-commercial-ia`](./message-home-commercial-ia/spec.md)：页面入口和首页数据消费继续由消息域 metadata 真相源驱动。
- [`message-home-filter-contract`](./message-home-filter-contract/spec.md)：五类筛选、通知 inbox 和已读同步都可映射到 metadata 契约与真实服务投影。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 消息与联系双首页 IA 成立

- 底栏仍为首页/精品/添加/消息/我，消息模块内可进入独立消息页和联系页状态。
- 两页顶部不放内联搜索框，统一使用顶部工具栏搜索按钮入口。
- 小趣入口和底部导航保持现有视觉主线。
- 旧消息二级筛选 @我/@小趣/提醒 不再作为商用首页主 IA。

<a id="req-002"></a>
### REQ-002 消息首页五类筛选由真实收件箱与通知 inbox 驱动

- 全部、未读、群聊、私聊筛选来自 ChatInbox 或 MessageHomeProjection。
- 通知筛选来自 notification-service/app-message 持久 inbox，不靠标题或摘要猜测。
- 小趣发现新圈子/新群聊作为 AppMessage 或 assistant insight 类型通知行展示，支持已读或 dismiss 状态。
- 列表只展示头像、标题、摘要、时间和头像右上未读数。

<a id="req-003"></a>
### REQ-003 联系首页聚合真实关系、圈子、群和交集

- 全部混排用户和群，按最近互动时间倒序。
- 互关只包含 mutual 用户，超过 20 人显示 A-Z 索引，小于等于 20 人不显示。
- 圈子 tab 只展示圈子列表，点击进入圈子联系人页。
- 群聊 tab 只展示已加入群，不展示聊天内容或公告。
- 交集摘要最多展示 2 个具体交集点，不出现 N 个交集。

<a id="req-004"></a>
### REQ-004 群聊天和聊天信息页使用同一 GroupHome 真相源

- 消息列表点击群直接进入聊天页，不先进入群主页。
- 群聊天页顶部展示群名称、来源实体、来源圈子和成员数。
- 右上角进入聊天信息页，展示群信息、群公告、相册/文件/活动/成员四宫格入口。
- 成员、管理员、转让群主、退出/解散等治理能力继续可用。
- 群头像只消费云端预合成 avatarUrl，不触发端侧成员九宫格 fallback。

<a id="req-005"></a>
### REQ-005 商用路径无 Mock、占位和本地业务拼接

- 生产包默认 Remote，无 Mock/Remote 切换入口。
- App UI/Provider 不从 MockChatRepository、MockIntersectionRepository、MockAppMessageRepository 或 PrototypeBundle 拼业务列表。
- 服务端生产配置不允许 mock-user、memory store、noop resolver、baseURL 为空返回空。
- ChatInbox 头像契约只暴露云端预合成 `avatarUrl`，不保留端侧拼图字段。

<a id="req-006"></a>
### REQ-006 metadata/codegen/Remote DTO 与商用消息体系一致

- MessageHome、ContactHome、GroupHome、IntersectionSummary、AppMessage 均有 metadata 真相源。
- App RemoteRepository 只使用 codegen path/operation/surface/header。
- 对象级 typed double 仅存在测试树，并与 Remote 返回同结构 DTO；不得进入任何环境 App。
- 商用服务必须使用真实持久化存储，不得以 mock 或内存仓储替代消息、会话与成员事实。

<a id="req-007"></a>
### REQ-007 统一两行布局：头像、标题、摘要、时间

- 统一两行布局：头像、标题、摘要、时间。
- `通知` 行必须来自 notification / app message 云端 inbox。
- 高保中的“小趣发现新圈子和新讨论”必须是 `AppMessage` 或 assistant insight 类型的真实通知行，不得硬编码运营卡。
- 任一会话从 `全部 / 未读 / 群聊 / 私聊` 任一筛选入口打开并完成已读回执后，所有 `MessageHome` filter 中该会话的未读计数必须同步清零；App 端需失效同一会话的所有聚合引用，服务端以 `MarkAsRead` / read watermark 驱动下一次 `ListMessageHome` 返回一致状态。
- `Intersection` 契约必须独立或明确迁入 `recommendation/intersection`，输出 `IntersectionPoint`、`IntersectionReason`、`ObjectIntersectionSummary`、`ContactIntersectionSummary`。
- `notification-service` 必须实现 `/app-messages`、未读数、标记已读、类型分页和持久化存储。
- `chat/chat/conversation` 的 `ListMessageHome`、`ListContactHome`、`GetGroupHome` 与 `MarkAsRead` 必须由真实持久化 read model / read watermark 支撑，禁止仅靠 App 本地缓存或 Mock 拼接维持筛选状态。
- 关系门禁必须服务端强校验，不信任 App 筛选。
- 讨论头像新建后可见前必须有非空 `avatarUrl` 或稳定服务端 fallback 资产。

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml`、`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/operations.yaml`、`quwoquan_service/services/circle-service/contracts/circle_management/circle/operations.yaml`、`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 消息与联系双首页 IA 成立

- GIVEN 执行“消息与联系双首页 IA 成立”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“消息与联系双首页 IA 成立”对应动作。
- THEN 底栏仍为首页/精品/添加/消息/我，消息模块内可进入独立消息页和联系页状态。
- THEN 两页顶部不放内联搜索框，统一使用顶部工具栏搜索按钮入口。
- THEN 小趣入口和底部导航保持现有视觉主线。
- THEN 旧消息二级筛选 @我/@小趣/提醒 不再作为商用首页主 IA。

<a id="sit-002"></a>
### SIT-002 消息首页五类筛选由真实收件箱与通知 inbox 驱动

- GIVEN 执行“消息首页五类筛选由真实收件箱与通知 inbox 驱动”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“消息首页五类筛选由真实收件箱与通知 inbox 驱动”对应动作。
- THEN 全部、未读、群聊、私聊筛选来自 ChatInbox 或 MessageHomeProjection。
- THEN 通知筛选来自 notification-service/app-message 持久 inbox，不靠标题或摘要猜测。
- THEN 小趣发现新圈子/新群聊作为 AppMessage 或 assistant insight 类型通知行展示，支持已读或 dismiss 状态。
- THEN 列表只展示头像、标题、摘要、时间和头像右上未读数。

<a id="sit-003"></a>
### SIT-003 联系首页聚合真实关系、圈子、群和交集

- GIVEN 执行“联系首页聚合真实关系、圈子、群和交集”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“联系首页聚合真实关系、圈子、群和交集”对应动作。
- THEN 全部混排用户和群，按最近互动时间倒序。
- THEN 互关只包含 mutual 用户，超过 20 人显示 A-Z 索引，小于等于 20 人不显示。
- THEN 圈子 tab 只展示圈子列表，点击进入圈子联系人页。
- THEN 群聊 tab 只展示已加入群，不展示聊天内容或公告。
- THEN 交集摘要最多展示 2 个具体交集点，不出现 N 个交集。

<a id="sit-004"></a>
### SIT-004 群聊天和聊天信息页使用同一 GroupHome 真相源

- GIVEN 执行“群聊天和聊天信息页使用同一 GroupHome 真相源”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“群聊天和聊天信息页使用同一 GroupHome 真相源”对应动作。
- THEN 消息列表点击群直接进入聊天页，不先进入群主页。
- THEN 群聊天页顶部展示群名称、来源实体、来源圈子和成员数。
- THEN 右上角进入聊天信息页，展示群信息、群公告、相册/文件/活动/成员四宫格入口。
- THEN 成员、管理员、转让群主、退出/解散等治理能力继续可用。
- THEN 群头像只消费云端预合成 avatarUrl，不触发端侧成员九宫格 fallback。

<a id="sit-005"></a>
### SIT-005 商用路径无 Mock、占位和本地业务拼接

- GIVEN 执行“商用路径无 Mock、占位和本地业务拼接”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“商用路径无 Mock、占位和本地业务拼接”对应动作。
- THEN 生产包默认 Remote，无 Mock/Remote 切换入口。
- THEN App UI/Provider 不从 MockChatRepository、MockIntersectionRepository、MockAppMessageRepository 或 PrototypeBundle 拼业务列表。
- THEN 服务端生产配置不允许 mock-user、memory store、noop resolver、baseURL 为空返回空。
- THEN ChatInbox 头像契约只暴露云端预合成 `avatarUrl`，不保留端侧拼图字段。

<a id="sit-006"></a>
### SIT-006 metadata/codegen/Remote DTO 与商用消息体系一致

- GIVEN 执行“metadata/codegen/Remote DTO 与商用消息体系一致”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“metadata/codegen/Remote DTO 与商用消息体系一致”对应动作。
- THEN MessageHome、ContactHome、GroupHome、IntersectionSummary、AppMessage 均有 metadata 真相源。
- THEN App RemoteRepository 只使用 codegen path/operation/surface/header。
- THEN 对象级 typed double 仅存在测试树，并与 Remote 返回同结构 DTO；四环境 App 只装配 Remote。
- THEN 消息、会话与成员事实写入真实持久化存储，重启后仍可回读，且商用路径无 mock/内存仓储。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 消息与联系双首页 IA 成立

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：底栏仍为首页/精品/添加/消息/我，消息模块内可进入独立消息页和联系页状态。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 消息首页五类筛选由真实收件箱与通知 inbox 驱动

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：全部、未读、群聊、私聊筛选来自 ChatInbox 或 MessageHomeProjection。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 联系首页聚合真实关系、圈子、群和交集

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：全部混排用户和群，按最近互动时间倒序。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 群聊天和聊天信息页使用同一 GroupHome 真相源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：消息列表点击群直接进入聊天页，不先进入群主页。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 商用路径无 Mock、占位和本地业务拼接

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：生产包默认 Remote，无 Mock/Remote 切换入口。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 metadata/codegen/Remote DTO 与商用消息体系一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：MessageHome、ContactHome、GroupHome、IntersectionSummary、AppMessage 均有 metadata 真相源。
- 完成判定：`SIT-006` 对应行为满足——MessageHome、ContactHome、GroupHome、IntersectionSummary、AppMessage 均有 metadata 真相源。
- App RemoteRepository 只使用 codegen path/operation/surface/header。
- 对象级 typed double 仅存在测试树，并与 Remote 返回同结构 DTO；环境 artifact 不可达。

<a id="open-007"></a>
### OPEN-007 业务事件到设备通知的完整投递链

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：业务事件、持久 inbox 和设备 push 任一断点都会造成用户看不到或重复看到通知。
- 完成判定：`SIT-002` 对应通知 inbox 行为满足，且 [`message-reliability-foundation` SIT-003](../message-reliability-foundation/spec.md#sit-003) 的真实设备投递与打开直达证据有效。

<a id="open-008"></a>
### OPEN-008 群空间首页四宫格剩共享 Skill 挂载

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺共享 Skill 挂载入口的群空间接线。相册/文件宫格已真实承接：
  `ListConversationAssets` 读面（kind=image|file、seq DESC keyset 分页、撤回消息不出现在索引、交付字段随行）经 contracts 演进落地，
  云侧正负例与分页去重见 `conversation_assets_contract__api_integration_test.go`（真实 Mongo）；
  宫格点击打开相册网格/文件列表并复用大图查看与系统打开消费链，
  App 证据见 `chat_settings_page_widget__local_contract_test.dart` 的相册/文件宫格用例。
  已闭合部分（证据见 `chat_group_space_entries__local_contract_test.dart`）：活动群（gatheringId 绑定）能力宫格展示「活动」格直达 Gathering Board；
  普通群不展示活动格（三类群差异化）；成员网格新增搜索入口格直达成员搜索页；`gatheringBoard` 与 `chatMemberSearch` 两个无入口路由已消灭。
- 完成判定：`SIT-004` 对应行为满足（含相册/文件承接与三类群差异化展示）且真实测试 `spec_ref` 有效。
