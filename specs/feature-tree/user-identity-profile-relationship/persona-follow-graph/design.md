# 用户及分身统一升级设计方案

## 设计动因

当前用户域的记录设计同时存在 `OwnerAccount / SubAccount / Persona / ProfileSubject / username / subAccountId` 等多套语义。即使业务能力已经初步可用，也仍有三个根问题：

1. 产品、规格、接口、DTO 和页面文案对“谁是真实主体”没有唯一答案。
2. `用户ID`、`分身ID`、`公开句柄` 之间没有稳定分层，导致公开读取和内部归属边界反复漂移。
3. 手机号、邮箱、用户号、昵称在旧模型中分散在不同层，无法直接支撑“一个用户，多个分身，各分身可独立修改并可选择同步”的目标。

本次 `/design` 不做兼容收敛，而做一次性统一升级：

- 对外与对内主概念统一为 `用户` 与 `分身`
- `用户ID` 只保留内部归属含义
- `分身` 成为唯一真实业务主体
- `用户号` 成为分身级唯一公开句柄
- 手机号、邮箱、用户名全部下沉为分身属性
- 不保留旧术语、旧 DTO 别名、旧接口路径和旧兼容桥

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| 当前会话 PRD 冻结结论 | 已明确“统一到用户及分身”“用户号全局唯一”“手机号/邮箱分身级，默认继承主分身，可同步到其它分身”“不保留兼容层” |
| `persona-follow-graph/acceptance.yaml` | `J1/J2/J3/R1` 仍可作为 Journey 级验收骨架，但后续需同步改写术语 |
| `persona-management/*` | 可复用“主分身管理、创建、切换、停用/删除保护、配额”等行为基线 |
| `persona-context-propagation/*` | 可复用“动作主体必须一致、缺上下文即 fail closed”的基线 |
| `follow-relationship/*` 与 `social-graph-read/*` | 可复用 graph 写读分离思想，但主键与字段语义需要改写为新模型 |
| `auth-profile-snapshot/*` | 可复用资料更新与快照思路，但字段归属必须从旧 owner 模型切到用户/分身模型 |
| `quwoquan_app/assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手链路仍需保持 typed contract、无字符串硬编码、无运行时特判 |

结论：

- `/design` 准入满足。
- 本次设计应按 Journey 级统一升级处理，而不是各 Scenario 各自兼容旧模型。
- 由于本次明确“不保留兼容层”，后续 `/dev` 必须按一次性替换实施，而不是双模型并行。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微信 | 公开句柄稳定、登录身份与业务身份可解耦、用户号心智清晰 | 不照搬强实名与单身份世界观 |
| 小红书 | 昵称/主页/作者主体统一、对外消费的是单一公开主体 | 不照搬单主体创作者模型 |
| 微博 | 公开关系网络、公开主体一致、内部治理不外露 | 不照搬记录账号层级和运营号结构 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| `persona-management/design.md` | 主分身管理、创建/切换/停用保护、失败恢复 |
| `persona-context-propagation/design.md` | 动作主体统一透传、缺上下文 fail closed |
| `profile-read-update/design.md` | 资料更新、快照版本与字段 contract 思路 |
| 助手设计约束文档 | typed context、runtime-thin、无第二真相源 |

## 方案对比

### 方案 A：渐进兼容升级

核心思路：

- 保留 `OwnerAccount / SubAccount / Persona / ProfileSubject` 记录命名。
- 新增 `用户 / 分身` 只作为新文档别名。
- 读接口双读旧字段，写接口双写新旧字段。

优点：

- 落地风险看起来较小。
- 可减少首轮替换量。

缺点：

- 旧语义会长期残留。
- `用户ID / 分身ID / 用户号` 无法形成唯一口径。
- 很容易继续出现 App、service、metadata 三套映射。

### 方案 B：一次性非兼容统一升级

核心思路：

- 直接以 `用户 / 分身 / 用户ID / 分身ID / 用户号` 重写主规格。
- metadata、codegen、DTO、接口、页面文案一次性替换。
- 记录数据只做一次性重整，不保留旧桥接读写层。

优点：

- 概念最清晰。
- 真相源唯一，后续扩展成本最低。
- 最符合本次产品要求与 spec-first 原则。

缺点：

- 首轮替换范围大。
- 需要严格切片与一次性验证。

## 选型决策

**选定方案：方案 B**

决策理由：

1. 用户已经明确要求“统一升级实现时无需考虑兼容，记录代码不用保留”。
2. 只有方案 B 能真正消除旧 `账号 / 主账号 / 子账号 / owner / subAccount` 心智残留。
3. 方案 B 更适合 metadata-first：先冻结新模型，再统一 codegen 和业务改造，不制造临时桥接层。

## 关键设计决策

### KD1：用户与分身双层模型

- `User`
  - 仅代表内部归属根
  - 唯一主键为 `userId`
  - 不参与公开展示
  - 承担审计、恢复、风控、安全和分身归属责任
- `Persona`
  - 即分身
  - 是聊天、内容、搜索、主页、关系、邀请、助手的唯一真实主体
  - 每个分身归属于一个 `userId`
  - 每个用户至少有一个主分身

### KD2：标识体系一次性收敛

统一只保留三类核心标识：

- `userId`
  - 内部唯一
  - 不公开
  - 不可修改
- `personaId`
  - 分身内部唯一 ID
  - 作为系统内部 canonical key
  - 替代旧 `profileSubjectId / subAccountId / senderPersonaId` 的主体主键职责
- `userHandle`
  - 即用户号
  - 对外公开
  - 全局唯一
  - 可修改

本次设计明确删除以下主链路概念：

- `OwnerAccount`
- `SubAccount`
- `ProfileSubject`
- `username` 作为模糊公开句柄

### KD3：字段归属全部落到分身层

以下字段统一定义为分身字段，而不是用户字段：

- `displayName`
- `userHandle`
- `phone`
- `email`
- `avatar`
- `bio`
- 其它公开主页资料

字段语义：

- `displayName`：用户名/昵称，不要求唯一
- `userHandle`：用户号，全局唯一
- `phone`：分身绑定手机号
- `email`：分身绑定邮箱

### KD4：主分身与继承/同步模型

- 新用户创建后自动生成一个主分身
- 主分身不可删除
- 每个用户至少保留一个分身
- 新建分身时默认继承主分身的 `displayName` 基线策略、`phone`、`email` 和基础资料
- 分身创建后可独立修改
- 当某个分身修改 `displayName / userHandle / phone / email` 时，系统可建议同步到全部或指定其它分身

需要的分身管理元数据至少包含：

- `isPrimary`
- `isActive`
- `inheritanceState`
- `lastSyncedAt`
- `hasAttributedHistory`

### KD5：公开与内部边界

- 对外只暴露分身信息
- 普通读接口、搜索结果、主页、聊天名片不得暴露 `userId`
- 普通业务读接口不得暴露“这些分身属于同一用户”
- 审计、风控、恢复链路可以内部追踪 `userId -> personas`

### KD6：跨域 canonical key 与透传 envelope

所有下游域统一以 `personaId` 作为内部主体主键，以 `userHandle` 作为公开引用句柄；`profileSubjectId` 只保留为当前公开读模型与兼容投影层字段。

统一透传 envelope：

- `personaId`
- `userHandle`
- `contextVersion`
- `personaSnapshotVersion`
- `sourceSurfaceId`
- `explicitOverride`

规则：

- content/chat/circle/assistant/notification/invite 只消费这套 typed envelope
- 缺少 envelope 时必须 fail closed
- 明确禁止静默回退到 `userId`

### KD7：graph 写读分离继续保留，但主语义改写

- command side：围绕 `personaId` 建立 follow/unfollow/block contract
- read side：围绕分身公开信息与关系能力读取
- 主页、聊天、邀请、助手只消费分身级关系能力，不读取用户层映射

### KD8：metadata / codegen 主轴

本次建议直接重整 user 域 metadata 真相源：

| 目录 | 本次冻结的 contract | 主要消费方 |
|------|---------------------|------------|
| `user/user_profile`（后续应重命名为用户/分身语义目录） | `User`、`Persona`、分身资料 mutation、分身管理列表、同步 patch、错误码 | user-service、app user repository |
| `user/follow_edge` | 分身级 follow command、relationship read view、事件 | user-service、graph repository |
| `user/block_edge` | 分身级 block gate、读取过滤 | follow command、graph read |
| `content/post` | 作者 `personaId`、作者快照 | content |
| `messages/conversation` | 发送者 `personaId`、消息作者快照 | chat |
| `assistant/*` | request/session 中的 `personaId`、`contextVersion` | assistant |

本次不允许：

- 在 App 侧维持第二套 owner/subAccount 映射
- 在 assistant runtime 用字符串规则推断分身
- 在公开 DTO 中继续混用 `profileSubjectId / subAccountId / username`

### KD9：一次性迁移与数据重整

本次不做长期兼容，但仍需做一次性数据重整：

1. 旧用户容器记录映射为新 `User`
2. 旧 `Persona/SubAccount` 记录映射为新 `Persona`
3. 若某用户缺少旧分身记录，则自动生成一个默认主分身
4. 旧 `phone` 下沉到主分身，并按“默认继承”规则复制到其它分身
5. 旧 `email` 若存在，同步下沉到分身
6. 旧 `username / nickname / subAccountId` 统一收敛生成 `userHandle`
7. 记录内容、评论、消息、关系中的旧主体字段统一改写为 `personaId`

`userHandle` 一次性生成策略：

- 优先使用已有公开句柄
- 若冲突，采用确定性后缀规则生成唯一值
- 若仍无法安全生成，使用系统保底句柄并允许用户后续修改

### KD10：发布、观测与回滚

本次虽然是非兼容统一升级，仍需具备发布控制，但不允许旧新双语义并行。

建议最小开关：

- `ops.user.persona_model_v2`
- `ops.user.persona_sync_v2`
- `ops.user.persona_graph_v2`

关键观测：

- `persona_switch_latency_ms`
- `persona_profile_sync_apply_count`
- `persona_handle_conflict_count`
- `persona_attribution_mismatch_count`
- `persona_public_leakage_count`
- `persona_migration_failed_count`

回滚原则：

- 仅允许整体验证失败后回退到上一版本部署
- 不允许在同一运行期内让旧模型和新模型双写并行
- 已完成的数据重整必须具备可重跑脚本与校验脚本

## metadata / codegen 方案

执行顺序固定：

1. 先重写 user 域 metadata
2. 再执行：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
3. 再让 service / app / assistant 全部切到生成物

需要冻结的核心 contract：

- `User`
- `Persona`
- `PersonaProfileView`
- `PersonaProfileMutation`
- `PersonaManagementItemView`
- `PersonaSyncSuggestion`
- `PersonaSyncPatch`
- `ActivePersonaContextView`
- 分身级 `FollowCommandRequest`
- 分身级 `RelationshipCapabilityView`

## 字段演进、迁移/回填与替换策略

### 字段演进

- 旧 `profileSubjectId / subAccountId / username` 退出主规格
- 新写链路统一只写 `personaId / userHandle`
- 旧 user-level `phone/email` 退出主字段定义

### 数据重整

- 把旧用户层资料拆分为 `User` 与主分身资料
- 对每个既有分身补齐 `personaId / userHandle / phone / email / inheritanceState`
- 记录 follow edge、内容作者、消息发送者统一回填 `personaId`

### 替换策略

- 不做双读双写
- 不做旧 DTO 兼容
- 不做旧接口 path 保留
- 采用“一次性 metadata 替换 -> codegen -> 业务重构 -> 数据校验”的方式推进

## feature flag、观测、SLO 验证与回滚方案

灰度顺序建议：

1. 先验证 metadata/codegen 与 user-service 主链路
2. 再验证 App 的分身管理与资料流
3. 然后验证 content/chat/assistant 透传
4. 最后验证 graph 与公开读取

SLO 验证：

- 主分身切换到首个关键动作的端到端耗时
- 用户号修改后的唯一性与同步提示链路稳定性
- 分身资料同步在弱网重试下不串号
- 内容/聊天/助手主体不出现漂移

回滚动作：

- 回退部署版本
- 重新执行数据校验脚本
- 禁止回到旧旧并行语义

## TDD / ATDD 策略

- `T1_schema`
  - metadata contract、错误码、字段分层、迁移脚本校验、codegen drift
- `T2_module_interaction`
  - 分身管理页、资料编辑、同步建议弹层、搜索/主页消费、provider 状态
- `T3_cross_service_integration`
  - user/content/chat/assistant/follow graph 联调、数据重整校验、可见性验证
- `T4_user_journey`
  - 新用户建主分身、多分身创建与切换、修改手机号/邮箱/用户号并同步、发帖评论聊天搜索关系闭环
- `T4_release_rehearsal`
  - 数据重整 rehearsal、观测面板校验、整版回滚 rehearsal

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结用户/分身 metadata 拓扑与命名收敛 | `J1/J2/J3` | `T1_schema` |
| `P2` | 完成 codegen 并替换 app/service/assistant 生成物消费 | `J1/J2/J3` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地分身管理、资料字段、用户号与同步建议 contract | `J1/J3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 落地 content/chat/assistant 的分身上下文透传 | `J2/J3` | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P5` | 落地分身级 graph command/read split | `J2/J3` | `T1_schema`, `T3_cross_service_integration` |
| `P6` | 执行一次性数据重整、发布演练与回滚验证 | `R1` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 在本轮统一升级完成后，再评估是否重命名 feature-tree 路径，清理 `persona-follow-graph` 记录目录名。
- 若后续引入更复杂的多分身记忆、业务权限或企业身份，也必须继续围绕 `userId + personaId + userHandle` 三层模型扩展。
- `circle` 服务化时，直接消费新的分身 envelope，不再重走旧 `subAccount` 语义。
