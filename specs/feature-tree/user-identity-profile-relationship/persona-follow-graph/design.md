# persona-follow-graph 设计方案

## 设计动因

`persona-follow-graph` 的 PRD 已经把“分身生命周期、公开身份、跨域透传、关系写入、图谱读取”拆成了 5 个正式 `L3_scenario`，但如果没有一版统一设计，后续开发仍会落回三个老问题：

1. owner plane、公开身份和动作主体继续在 UI / Repository / 下游域各讲各话。
2. `Persona / SubAccount / ProfileSubject / userId / username` 继续并存，metadata 与代码生成物无法成为稳定真相源。
3. follow 写入、graph 读取、content/chat/assistant 透传会各自发明兼容逻辑，灰度与回滚无法收口。

本次 `/design` 的目标不是“把 5 个 Scenario 各自设计完就结束”，而是先建立一条 Journey 级主轴：

- **user 域拥有身份真相源**
- **下游域只消费 typed contract**
- **graph 写读分离**
- **metadata -> codegen -> 业务逻辑 -> 测试** 顺序固定

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `persona-follow-graph/spec.md` | 已冻结 Journey 范围、领域边界、业务对象分区、弱网/容量/SLO，可进入 `/design` |
| `persona-follow-graph/acceptance.yaml` | `J1/J2/J3/R1` 完整，足以承载 Journey 级 plan slices |
| `persona-management/*` | 已冻结 owner plane 的入口、配额、切换、停用/删除保护 |
| `persona-profile-subject-and-visibility/*` | 已冻结 `ProfileSubject`、继承/覆写、可见性与历史归因 |
| `persona-context-propagation/*` | 已冻结 active persona 对 content/chat/circle/assistant/notification 的透传边界 |
| `follow-relationship/*` | 已冻结 `FollowEdge` command side、幂等、block 门禁与事件副作用 |
| `social-graph-read/*` | 已冻结 graph read side、分页、`RelationshipCapabilityView` 与过滤语义 |
| `profile-homepage-redesign/owner-subaccount-homepage-unification/*` | 已明确其仅消费 `ProfileSubject` 契约，不再主定义 persona 公开身份 |
| `quwoquan_app/assistant/docs/PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | 助手 runtime 只负责编排，不能新增 persona 语义特判 |
| `quwoquan_app/assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手相关设计必须保证无字符串硬编码、无第二真相源、metadata 驱动 |

结论：

- `/design` 准入满足。
- 必须先冻结 Journey 级统一 contract，再分别落到 5 个 Scenario 的 plan。
- 本次设计涉及 metadata / codegen，需要执行真实 `verify-metadata`、`codegen`、`codegen-app`。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微信 | 登录容器与应用内身份分离；切换身份后消息/关系主体必须稳定 | 不照搬强实名与通讯录模型 |
| 小红书 | 作者主页、评论、内容卡统一消费作者公开身份 | 不照搬其单一创作者中心 IA |
| 微博 | 公开 follow 图谱与粉丝传播链、运营主体分离 | 不照搬其 owner 暴露心智与老式关系层级 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| `owner-subaccount-homepage-unification/design.md` | `ProfileSubjectView`、`ProfileSubjectMutation`、主页消费边界 |
| `content-display-journey-consistency/design.md` | canonical key、typed provider、handoff/result 只是补强而非真相源 |
| 助手两份核心文档 | `runtime-thin`、typed contract、无 persona 字符串路由 |
| 现有 `user_profile / follow_edge / block_edge` metadata | 具备继续细化为 Journey 主轴的基础目录结构 |

## 方案对比

### 方案 A：下游各域自持 persona 规则

核心思路：

- `user` 只保留 `CreateSubAccount / ActivateSubAccount` 等最小能力。
- content/chat/circle/assistant 各自决定如何解释 `personaId / subAccountId / username`。
- follow 与 graph 继续围绕现有局部 DTO 和布尔字段演进。

优点：

- 初始改动最少。
- 每个域可独立推进，不需要先收口统一 metadata。

缺点：

- 必然产生第二真相源。
- 串号、历史归因、owner 泄露无法系统性治理。
- 助手链路会落回 runtime 特判，违反现有设计约束。

### 方案 B：只在 App 侧编排 persona，服务端继续保留 owner/user 兼容

核心思路：

- App provider 维护 active persona 与 `ProfileSubject` 组合状态。
- 服务端仍以 owner/user 级 contract 为主，persona 由 App 做映射。
- follow/graph 通过前端 adapter 兼容旧接口。

优点：

- 可以较快打通端侧体验。
- 短期不需要调整太多 metadata。

缺点：

- 与 metadata-first 原则冲突。
- App 会变成 owner/persona/profileSubject 映射中心，后续 remote/mock 一定漂移。
- 无法支撑跨服务一致的审计、回放和回滚。

### 方案 C：user 域统一身份契约 + typed context 透传 + graph 读写分离

核心思路：

- user 域冻结 `ProfileSubjectView / ProfileSubjectMutation / ActivePersonaContextView` 等统一 contract。
- 下游域只消费 `profileSubjectId / subAccountId / persona snapshot` 等 typed 字段，不再自己解释 owner/persona 关系。
- `FollowEdge` 与 `social graph` 明确拆成 command side / read side。
- 助手只消费 typed persona context，不在 runtime、prompt 拼接层发明用户分身逻辑。

优点：

- 与 DDD、metadata-first、assistant 约束同时一致。
- 方便按 Scenario 灰度、观测和回滚。
- Journey 范围内的 5 个 Scenario 可以围绕同一套 canonical key 和 request context 落地。

缺点：

- 需要一次性设计 metadata、codegen、迁移与兼容出口。
- 首轮切换比方案 A/B 更重。

## 选型决策

**选定方案：方案 C**

决策理由：

1. 只有方案 C 能把 owner plane、公开身份、动作主体和图谱写读一次性收进 user 域的统一 contract。
2. 它满足仓库的 metadata-first 与 assistant runtime-thin 双重约束，不会把复杂度推给 UI 或 runtime。
3. 它天然支持 Journey 级灰度：管理台、公开身份、上下文透传、graph 能力可以分别开关与回退。

## 关键设计决策

### KD1：业务对象与真相源拓扑

- `UserProfile`：owner 管理平面、资料基线、统计冗余、active persona。
- `Persona(SubAccount)`：分身生命周期、override 字段、隔离等级、管理字段。
- `ProfileSubjectView`：公开读模型，只暴露公开身份与统计，不暴露 owner 映射。
- `FollowEdge`：关系写入与图谱边主对象。
- `BlockEdge`：写入门禁与读取过滤对象。
- `content/chat/circle/assistant/notification`：只持久化 user 域下发的稳定 identity key 和历史快照。

这五类对象的主目录分别固定为：

- `contracts/metadata/user/user_profile/`
- `contracts/metadata/user/follow_edge/`
- `contracts/metadata/user/block_edge/`
- `contracts/metadata/content/post/`
- `contracts/metadata/messages/conversation/`
- 助手消费 contract 位于 `contracts/metadata/assistant/`，但 persona 真相源仍归 user 域

### KD2：Journey 切片与 Scenario 依赖

- `persona-management` 负责 owner plane。
- `persona-profile-subject-and-visibility` 负责 public plane。
- `persona-context-propagation` 负责 action plane。
- `follow-relationship` 负责 graph command side。
- `social-graph-read` 负责 graph read side。

依赖顺序固定为：

1. `persona-management` 与 `persona-profile-subject-and-visibility` 建立基础 identity contract。
2. `persona-context-propagation` 复用 active persona 与 `ProfileSubject`。
3. `follow-relationship` 与 `social-graph-read` 统一建立在 `ProfileSubject` 级别 key 上。

### KD3：公开身份与当前动作主体双轨 contract

Journey 统一冻结两类核心模型：

- `ProfileSubjectView`
  - 公开读取、列表项展示、主页首屏、作者卡展示统一消费
  - key 为 `profileSubjectId`
- `ActivePersonaContextView`
  - owner 私有的当前动作主体快照
  - 至少包含 `profileSubjectId`、`subAccountId`、`isolationLevel`、`visibility`、`contextVersion`

两者关系：

- `ProfileSubjectView` 面向公开与消费域展示。
- `ActivePersonaContextView` 面向 owner plane 和跨域透传。
- 下游域即使拿到 `ActivePersonaContextView`，也不得借此反推出 owner。

### KD4：typed persona context envelope

跨域透传不采用“页面变量 + 文案 + 本地兜底”模式，而采用 typed envelope：

- `profileSubjectId`
- `subAccountId`
- `contextVersion`
- `personaSnapshotVersion`
- `sourceSurfaceId`
- `explicitOverride`（仅显式改用其它分身时出现）

使用规则：

- content/chat/circle/invite/assistant/notification 都只消费这套 typed envelope。
- 任一关键链路缺少 envelope 时必须 fail closed：阻断、要求确认或回退到最近一次稳定 active persona 快照。
- 明确禁止静默回退到 owner。

### KD5：graph 写读分离

`follow-relationship` 与 `social-graph-read` 不能共享同一个“万能关系对象”：

- command side：`FollowCommandRequest`、幂等、block gate、事件发布
- read side：`FollowerListItemView`、`FollowingListItemView`、`RelationshipView`、`RelationshipCapabilityView`

写读之间的协作规则：

- `FollowEdge` 写成功后发布 `UserFollowed / UserUnfollowed`
- `UserProfile` 通过事件修正计数
- `social-graph-read` 组合 `FollowEdge + BlockEdge + ProfileSubject`
- 主页、聊天、RTC 只消费 `RelationshipCapabilityView`

### KD6：metadata / codegen 主轴

| 目录 | 本次需要冻结的 contract | 主要消费方 |
|------|-------------------------|------------|
| `user/user_profile` | `ProfileSubjectView`、`ProfileSubjectMutation`、`ProfileInheritanceStateView`、`ActivePersonaContextView`、管理台列表/配额/停用错误码 | user service、App user repository、profile homepage |
| `user/follow_edge` | `FollowCommandRequest`、graph list item、`RelationshipView`、`RelationshipCapabilityView`、follow events | user service、social graph repository |
| `user/block_edge` | block gate 与过滤错误码、读取过滤枚举 | follow command、graph read |
| `content/post` | `personaId / profileSubjectId`、作者快照、request context | content repository、comment flow |
| `messages/conversation` | `senderPersonaId`、消息作者快照、request context | chat repository、conversation flow |
| `assistant/*` | assistant request/session context 中的 `profileSubjectId`、`contextVersion` | assistant cloud client、application/orchestration |

`circle` 当前若仍处于 app/local contract 阶段，不允许新建第二套 metadata 真相源；先消费同一 `ActivePersonaContextView` provider，待正式服务化时再接入相同 envelope。

### KD7：App / cloud / provider 编排边界

- `app_providers.dart` 继续作为 repository 工厂真相源。
- 新增或收口：
  - `activePersonaContextProvider`
  - `profileSubjectRepositoryProvider`
  - `socialGraphRepositoryProvider`
- UI 只读取 provider，不直接 `new Mock...` 或 `new Remote...`。
- Router 继续消费 metadata 产物生成的 path / surface；内部 provider key 统一使用 `profileSubjectId`，不再使用 `username`。

### KD8：迁移、回填与兼容出口

兼容期冻结以下规则：

- identity key 读取优先级：
  - `profileSubjectId`
  - `personaId / subAccountId`
  - legacy owner `userId`（仅限兼容桥接，不得写回新对象）
- 现有 owner 级 follow 关系需在 persona-aware graph 开关打开前回填到主分身 `profileSubjectId`。
- 既有内容/评论/消息历史对象不重写作者快照；新写入开始补齐 `profileSubjectId` 和 snapshot version。
- 助手链路允许短期保留“从旧会话模型映射出 `profileSubjectId`”的 compatibility shim，但退出条件必须是所有入口统一改为 typed session context。

### KD9：feature flag、观测、SLO 与回滚

建议最小开关集：

- `ops.user.persona_management_v1`
- `ops.user.profile_subject_v1`
- `ops.user.persona_context_v1`
- `ops.user.persona_graph_v1`

关键观测：

- `persona_switch_latency_ms`
- `persona_attribution_mismatch_count`
- `persona_public_leakage_count`
- `retired_subject_read_count`
- `graph_filter_mismatch_count`
- `assistant_persona_drift_count`

回滚原则：

- 管理台、公开身份、上下文透传、graph 可独立降级。
- 任何回滚都不得破坏历史归因与已持久化 `profileSubjectId`。
- 助手回滚只允许关闭 persona-aware session context，不允许把用户分身逻辑塞回 runtime 字符串判断。

## metadata / codegen 方案

执行顺序固定：

1. 补齐 `user_profile / follow_edge / block_edge / content/post / messages/conversation / assistant/*` metadata
2. 运行：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
3. 让 App / service / cloud client 全部改为消费生成物

codegen 期望产物：

- service 侧：DTO、错误码、path builder、request context、事件结构
- App 侧：typed DTO、repository path builder、operation 常量、surface/route 生成物
- 助手侧：typed session/request contract，禁止再靠 prompt 文本推导 persona

## 字段演进、迁移/回填与兼容

### 字段演进

- 新写链路统一补齐 `profileSubjectId`
- 历史兼容字段 `personaId / senderPersonaId / subAccountId` 暂时保留，但其语义必须能映射回 `profileSubjectId`
- `username` 只承担展示和路由职责

### 迁移 / 回填

- 为现有分身回填 `profileSubjectId`
- 将 legacy owner-level follow edge 映射到主分身
- 为新旧内容/评论/消息建立稳定的 snapshot version 读取优先级

### 双读 / 双写策略

- 本次不采用长期双写 `UserProfile <-> PublicProfile` 模型
- 采用短期双读兼容：
  - 读时优先新字段
  - 写时只写新字段和必要兼容字段
- 退出条件：
  - graph、content、chat、assistant 均以 `profileSubjectId` 为主
  - 旧 owner-level persona bridge 不再被访问

## feature flag、观测、SLO 验证与回滚方案

灰度顺序建议：

1. 先开 `persona_management`
2. 再开 `profile_subject`
3. 然后开 `persona_context`
4. 最后开 `persona_graph`

SLO 验证：

- 关注 active persona 切换到首个关键动作的端到端耗时
- 验证 strict isolation 与 retired attribution 的公开读取稳定性
- 验证 follow write / graph read 在弱网与重试下不串号
- 验证 assistant session 不出现 drift

回滚动作：

- 关闭对应 flag
- 清空相关 pending outbox / 缓存快照
- 保持 `profileSubjectId` 数据和历史快照不回退

## TDD / ATDD 策略

- `T1_schema`
  - metadata contract、错误码、request context、codegen drift、backfill 规则
- `T2_module_interaction`
  - App provider、route handoff、管理台状态机、主页消费矩阵、assistant context adapter
- `T3_cross_service_integration`
  - user/content/chat/assistant/follow graph 联调、事件副作用、visibility/filter
- `T4_user_journey`
  - owner 创建/切换/停用分身、发帖评论聊天、查看 graph、通知/助手回放
- `T4_release_rehearsal`
  - feature flag、监控面板、backfill rehearsal、rollback rehearsal

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结 identity / graph / context metadata 拓扑 | `J1/J2/J3` | `T1_schema` |
| `P2` | 建立 codegen 与 app/cloud 消费基线 | `J1/J2/J3` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地 owner plane 与 public plane contract | `J1/J3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 落地跨域 persona context 透传 | `J2/J3` | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P5` | 落地 graph command/read split | `J2/J3` | `T1_schema`, `T3_cross_service_integration` |
| `P6` | 验证灰度、回填、回滚与 Journey 证据 | `R1` | `T2_module_interaction`, `T4_user_journey`, `T4_release_rehearsal` |

## 未来演进

- 当 `profileSubjectId` 成为全链路唯一 key 后，单开 Story 清理 `personaId / senderPersonaId / SubAccount` 历史命名。
- `circle` 服务化后，把当前 app/local persona context 消费切到正式 metadata contract。
- assistant 若后续引入更强的多身份记忆策略，仍必须围绕 typed session context 扩展，不得回到 runtime 特判。
