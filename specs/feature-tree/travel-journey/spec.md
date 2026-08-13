# L1 Domain Service：Gathering 共同旅行体验 (`travel-journey`)

> 一句话定位：把多人多日旅行表达为 Gathering + optional Plan/Map/Calendar/Experience 的体验组合，并治理已静态退役 travel-service 的 target-only 历史数据迁移。

## 1. 目标与用户价值

为多人多日 Gathering 的组织者和参与者提供“活的共同旅行体验”：在活动群聊看板上按需启用 Plan、Map、Calendar 与 Experience，一次维护吃玩住行，行中同步变化与讲解，行后形成可编辑、可分享的回顾。旅行不复制 Gathering 的 Host、Participation、准入、会话、生命周期或 Outcome，共同经历也不自动建立关系。

## 2. 领域边界

### 目标所有权

- Circle 的 Gathering 拥有活动身份、Host、root-owned Participation、准入、会话 binding、生命周期、Outcome 与可选 Plan 的目标事实；旅行体验只组合 Plan、Map、Calendar、Experience 和 Content reference。
- `travel-journey` 只拥有旅行体验边界、历史 crosswalk 与 target-only 迁移证据；不保留 Trip 作为长期公共独立根。

### 已退役源边界

- 生产源码、进程、contract、generated client、路由与 App DI 已删除；运行主链不得重新出现源 Reader、Writer、route、client 或 fallback。
- 历史 `TripPlan`、Revision、Membership、Moment、Placement、ShareSnapshot、Template 与 GuideAssignment 只允许作为 target-only inventory、crosswalk、脱敏迁移输入和审计 receipt 存在。
- 每类历史源对象必须通过确定性映射进入 Gathering/Plan/Experience/Content/Chat 目标 owner，或被明确 archived、quarantined、not_applicable；alpha、beta、gamma、prod 的 inventory、parity、cutover 与 target-only rollback 在签名 receipt 完成前不得宣称数据迁移完成。

### 本领域不拥有

- Gathering、Host、Participation、Revision、Outcome 与 room binding；owner：[`circle-community`](../circle-community/spec.md)。
- Conversation、ConversationMembership、Message、Announcement 与附件索引；owner：[`chat-conversation`](../chat-conversation/spec.md)。
- Post、LocalPostDraft、MediaAsset；owner：[`discovery-content`](../discovery-content/spec.md)。
- Persona、Follow 与公开资质声明；owner：[`user-identity-profile-relationship`](../user-identity-profile-relationship/spec.md)。
- Skill、AssistantRun、Trigger、Evidence 与 Presentation；owner：[`assistant-run-learning`](../assistant-run-learning/spec.md)。

### 上下游协作

- 上游：有效多人多日 Gathering、活动群聊、Persona 权限、Post/MediaAsset 引用、Place/Route 事实及用户确认的助手提案。
- 下游：活动看板可消费的 Plan Revision、Timeline/Map/Calendar/Experience 投影，以及回顾草稿请求。
- 跨域写入：只调用 Circle/Chat/Content/Integration 等目标 owner 公开 command；迁移工具也不得直写派生投影。
- 跨域读取：使用 owner 公开 query/projection，并保存 canonical reference 与来源版本。
- 异步协作：目标 owner 发布 Plan/Experience/Calendar/Content 事件；已退役源事件不得成为产品输入。

## 3. Journey / Scenario 职责

- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：定义组织者如何在既有 Gathering 上启用可选 Plan，并把确认后的提案写入 Circle 目标 owner 的 Plan Revision 与 item。
  - 进入条件：Gathering 有效、操作者具有 Organizer authority，计划输入与引用可见。
  - 交付给下游的结果：活动群聊 Board 可查看和继续修订的当前 Plan。
  - 不负责：不创建 Trip 根，不把 Assistant 文本或 Chat Message 当计划真相源。
- [`JNY-013 / SCN-031`](../spec.md#scn-031)
  - 本领域负责：以 owner 的不可变 Plan Revision 推进当前计划，计算可读 diff 与受影响 GatheringParticipation，并发布变化事实。
  - 进入条件：操作者拥有 Gathering Organizer authority，expected revision 与当前事实一致。
  - 交付给下游的结果：新的 current Plan Revision 和可供活动群聊提醒的 typed event。
  - 不负责：不决定通知频控、静默与投递渠道。
- [`JNY-013 / SCN-032`](../spec.md#scn-032)
  - 本领域负责：经用户确认把 Experience 或 Post reference 关联到 Gathering/Plan item，并从同一 owner 事实投影时间线和地图。
  - 进入条件：Gathering、目标 Plan item 与引用对象可见且未失效。
  - 交付给下游的结果：顺序稳定、可追溯且可删除的 Experience/reference 与投影。
  - 不负责：不复制媒体字节、Post 正文或连续位置轨迹。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：基于 Gathering Outcome、Plan、Map 与 Experience 形成隐私裁剪后的分享种子，并向 Content 请求 LocalPostDraft。
  - 进入条件：调用方可分享目标 Gathering 范围，且敏感字段裁剪通过。
  - 交付给下游的结果：整段、单日、单点、路线或 Experience 集合的草稿来源引用。
  - 不负责：不自动发布内容，不创建或修改关系。

## 4. 业务能力

- [`collaborative-trip-lifecycle`](./collaborative-trip-lifecycle/spec.md)：组合 GatheringPlan/Revision、Chat Board、Experience/Content reference、Map/Calendar 与回顾分享，并保存 legacy Trip 对象到当前 owner 的历史 crosswalk。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 旅行是 Gathering 上的可选体验组合

- 每次多人多日旅行必须先有一个 Gathering；Host、Participation、准入、会话、生命周期、取消、完成与 Outcome 始终由 Gathering owner 负责。
- Plan、Map、Calendar 与 Experience 可以按需启用或隐藏；它们不复制活动身份、成员、容量或 room。任务是 Plan item，文件是 Chat AssetIndex，回顾是 Content Post/Media。
- Plan 只引用一个 current Revision；失败、冲突或未确认提案不得改变它，也不得以 Chat Message、Assistant Artifact 或 App cache 作为当前计划。

<a id="req-002"></a>
### REQ-002 时间线、地图、日历、Experience 与隐私边界

- 活动群聊 Board 可呈现当前 Gathering 的 Plan/Map/Calendar/Experience；目标或 Plan 不明确时调用方必须消歧，零写入返回。
- 时间线与地图从同一 canonical reference 投影，不记录连续实时轨迹；公开分享必须移除私人住宿细节、联系方式、参与者名单和实时精确位置。
- Calendar 只是导出/提醒 capability，不拥有日程真相；设备、OAuth Connector 或 Provider 不可用时返回结构化 unavailable，不伪造成功。

<a id="req-003"></a>
### REQ-003 travel-service 生产主链永久退役，历史数据仅允许 target-only 迁移

- travel-service 的进程、contracts、generated client、App DI、旧 Skill 绑定和 route/page/surface 已删除；App、Assistant 与 api-edge 对该服务的依赖必须永久为零，生成链不得从 materialized、symlink 或旧摘要复活源 owner。
- 历史对象只经确定性 target owner、ID crosswalk、幂等映射、count/digest/orphan/collision receipt 与隐私裁剪判定进入目标；每个环境必须独立证明 source inventory 与 target readback，不得以本地合成快照代替环境事实。
- 不得双读、双写或保留兼容 shim；静态退役通过不能替代历史数据迁移准出，历史数据迁移未完成也不能恢复源服务。
- 回滚只允许恢复目标应用/config 或目标数据快照，不得恢复源写入、源 runtime 或源产品入口。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 Gathering 旅行体验所有权与 target-only 收敛

- 条件：多个有效 GatheringParticipant 在活动群聊 Board 启用、修订、记录和分享旅行可选能力；存在历史源数据的环境提供与候选、crosswalk 和目标 readback 绑定的签名 receipt。
- 可观察结果：Gathering 仍是唯一活动根，Plan current Revision 唯一且历史不可变，Experience/Post 只以引用关联，时间线与地图收敛到同一事实；所有生产调用只读目标 owner。
- 禁止结果：不得保留长期公共 Trip 根、复制 Participation/Conversation/Post/Media、手工写投影、以消息或助手状态代替计划、双读双写或恢复 travel-service，或用合成 receipt 冒充环境迁移完成。

## 7. 工程归属

- App：无独立 Travel owner；旅行体验复用 Circle Gathering/Plan、Chat、Content 与 Integration 的 typed ports。
- Contracts / Service：无 `travel-service`；目标合同与 runtime 由 Circle/Chat/Content/Integration 各对象 owner 持有。
- Ops：`quwoquan_ops/migrations/travel_to_gathering` 只保存 target-only crosswalk、证据控制面与回滚审批协议。
- 目标实现归 [`circle-community`](../circle-community/spec.md) 工程归属管理；本节点不重复认领 `quwoquan_app/lib/service/circle_service` 或 `circle-service`。
- 测试：
  - `local_contract`：`quwoquan_ops/tests/local_contract/stackctl/test_travel_to_gathering_migration__mapping__local_contract_test.py`、
    `quwoquan_ops/tests/local_contract/stackctl/test_travel_to_gathering_migration__execute__local_contract_test.py` 与
    `quwoquan_ops/tests/local_contract/stackctl/test_travel_to_gathering_migration__cutover_rollback__local_contract_test.py`
  - `api_integration`：归属各目标 owner 的 Gathering/Plan/Chat/Content/Integration 证据树，不保留源服务目录。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 四环境历史 Trip 数据 target-only 迁移证据未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺验收证据：alpha、beta、gamma、prod 真实历史对象全集的 inventory、目标 owner import/readback、100% parity、cutover 与 target-only rollback receipt。生产主链已经静态退役，仓内现有证据只证明控制面能校验合成快照；若把静态删除当作数据迁移完成，可能遗失历史计划、参与、内容引用或审计义务。
- 完成判定：`DOM-001` 的「历史源数据环境提供与候选/crosswalk/目标 readback 绑定的签名 receipt、生产调用只读目标 owner、不得用合成 receipt 冒充环境迁移完成」子句成立——四环境分别提供绑定同一 source snapshot、crosswalk、ContractGraph、mapping、target candidate 与审批摘要的 inventory、owner-command import、target readback、100% parity、cutover receipt；Prod 另有 target backup 和 target-only rollback 演练，且全部历史对象满足 sourceCount = migrated + archived + quarantined + notApplicable、orphan/collision=0、raw PII emission=0。
- 依赖：各环境受保护的源 inventory、Circle/Chat/Content canonical import command、目标 readback、审批与配置激活证据。

<a id="open-002"></a>
### OPEN-002 Gathering 旅行体验与真环境 UAT 未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：GatheringPlan/Revision、Experience reference、Map/Calendar、Chat Board 与 Content 回顾在同一 production Remote composition 中的完整旅行体验及真实 Provider/Connector；尚缺验收证据：跨域 API integration、离线恢复、隐私分享和 Android/iPhone 真环境结果。travel-service 生产主链已经静态退役，历史数据迁移由 `OPEN-001` 独立阻断。
- 完成判定：`DOM-001` 由目标 owner 的 local_contract、Circle/Assistant/Chat/Content/Integration 跨域 api_integration 和 [AppRoot 双端共同旅行验收](../spec.md#uat-012) 直接覆盖；Android 与 iPhone 真环境均可从活动群聊看板启用、修订、记录和分享，所有结果绑定同一 Gathering/Plan revision，Provider 不可用时结构化降级，公开分享完成隐私裁剪，参与不自动 mutual。
- 依赖：本 L2/L3 的阻断 OPEN、Circle production Remote、Chat Board/AssetIndex、Assistant active Skill package、Content draft/media、Integration Provider/Connector 与 Gathering Outcome。
