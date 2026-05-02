# persona-context-propagation 设计方案

## 设计动因

`persona-context-propagation` 决定“当前激活分身是否真的成为全链路默认动作主体”。如果没有统一设计，content/chat/circle/assistant/notification 会各自保存一份 active persona，本质上等于把 user 域真相源拆散。

本场景要解决的不是“字段够不够多”，而是三条主轴：

1. active persona 只能有一个真相源。
2. 下游域拿不到 persona context 时必须 fail closed，不能静默回退到 owner。
3. 助手只消费 typed 用户分身上下文，不能把 prompt `stack.persona` 当成用户身份模型。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `persona-context-propagation/spec.md` | active persona、跨域透传、阻断与恢复边界清晰 |
| `persona-context-propagation/acceptance.yaml` | `A1/A2/A3/S1` 完整，可映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结 `ActivePersonaContextView` 与 typed persona context envelope |
| `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | 助手 runtime 只负责编排，不得承载 persona 语义特判 |
| `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手必须遵守无字符串硬编码、无第二真相源、metadata/codegen 驱动 |
| 当前代码现状 | 评论已有 `personaId`、聊天已有 `senderPersonaId`，但缺乏统一 active persona 主轴与恢复策略 |

结论：

- `/design` 准入满足。
- 本场景是 content/chat/assistant 进入 `/dev` 前的门禁，必须先冻结 typed context contract。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微信 | 切换身份后消息与关系主体必须稳定 | 不照搬账号切换与通讯录语义 |
| 小红书 | 评论、内容创作都要感知当前作者身份 | 不照搬内容入口 IA |
| 微博 | 公开互动和运营主体的一致性 | 不照搬记录 owner 暴露路径 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `ActivePersonaContextView`、typed envelope、fail closed 原则 |
| `content-display-journey-consistency` | canonical key + provider state 统一管理 |
| 助手核心文档 | runtime-thin、metadata 驱动、prompt 资产化、无字符串行为路由 |

## 方案对比

### 方案 A：各下游域本地缓存 active persona，并在缺失时自行兜底

核心思路：

- 每个域自己缓存“最近一次 active persona”。
- 缺失时优先用本地缓存或默认 owner。

优点：

- 现有页面改动最少。
- 每个域都能快速补一版体验。

缺点：

- 真相源立刻分裂。
- 最危险的串号场景正是由这种“本地兜底”造成。
- 助手与通知回放最容易漂移。

### 方案 B：只通过 request headers 透传 persona，不持久化 context version 和快照

核心思路：

- active persona 只通过请求头带给下游。
- 下游不保存 context version，也不保存明确 persona snapshot。

优点：

- 改动集中在请求层。
- 看上去比较轻量。

缺点：

- 记录对象与回放场景无法稳定恢复。
- 通知和助手会话不能精确判断 drift。
- 缺乏对弱网与重试的恢复能力。

### 方案 C：user 域 `ActivePersonaContextView` + typed envelope + 下游快照持久化

核心思路：

- user 域提供唯一 `ActivePersonaContextView`。
- request context 透传 typed envelope。
- 下游对象落库时保存 persona key 与最小快照。
- 通知与助手会话记录 `contextVersion` 以支持回放和 drift 检测。

优点：

- 与 PRD、Journey 设计、助手约束完全一致。
- 同时兼顾在线动作和记录回放。
- 最适合做 fail closed 与 telemetry。

缺点：

- 需要同时改 metadata、provider、cloud client 与部分下游对象。
- 第一版要处理 current 字段兼容。

## 选型决策

**选定方案：方案 C**

理由：

1. 只有方案 C 能保证 active persona 既是在线动作主体，也是回放与审计的稳定基线。
2. 它支持助手和通知的 typed 恢复逻辑，不会落回 runtime 文本推断。
3. 它让 `A1/A2/A3` 在同一条 contract 主轴上闭环。

## 关键设计决策

### KD1：`ActivePersonaContextView` 是跨域唯一真相源

user 域统一提供 `ActivePersonaContextView`，至少包含：

- `personaId`
- `profileSubjectId`
- `subAccountId`
- `profileVisibility`
- `isolationLevel`
- `contextVersion`
- `switchedAt`

下游域只消费这个快照，不允许自建“当前分身是谁”的持久状态中心。

### KD2：跨域透传统一使用 typed envelope

透传字段统一收口为：

- `personaId`
- `profileSubjectId`
- `subAccountId`
- `contextVersion`
- `personaSnapshotVersion`
- `sourceSurfaceId`
- `explicitOverride`

第一版覆盖：

- content 发布 / 评论
- chat 消息发送
- circle 加入 / 创建 / 圈内展示
- invite 归因
- assistant session / request context
- notification open / replay

### KD3：下游对象要保存最小 persona 快照

透传不等于只带 headers。以下对象必须保留最小快照：

- `Post / Comment`
- `Message`
- `Invitation / Notification payload`

快照至少包括：

- `personaId`
- `profileSubjectId`
- `displayName`
- `avatarUrl`
- `snapshotVersion`

这保证 retired persona 或 username 变更后，记录对象仍可稳定渲染。

### KD4：显式 override 是受控行为，不是隐式 fallback

- 默认始终使用 active persona。
- 只有页面明确提供“改用另一个分身”交互时，才允许 `explicitOverride = true`。
- override 必须被持久化为 request context 的一部分，供审计和回放使用。

### KD5：缺失或过期 context 时必须 fail closed

关键动作如果拿不到合法 persona context，系统只能执行以下动作之一：

- 阻断并要求用户确认当前分身
- 回退到最近一次稳定 `ActivePersonaContextView`
- 记录 mismatch / stale context / drift 事件

明确禁止：

- 回退到 owner
- 使用页面缓存里的旧 persona 静默提交
- 助手根据提示词文案猜当前分身

## 助手链路符合性

### 影响层

- `UI`：`lib/ui/assistant/` 的会话入口与回放入口
- `cloud client`：`lib/cloud/services/assistant/`
- `application / orchestration`：`lib/assistant/` 中的 session context 读取与事件投影
- `generated contract`：`contracts/metadata/assistant/` 与 `quwoquan_app/lib/assistant/generated/`

本次**不**引入新的 skill / tool / prompt 垂类逻辑。

### 影响的业务大类聚类

- `conversation`
- `tool`
- `channel`

如后续涉及记忆回写，也必须复用同一 typed persona context，而不是新增字符串标签。

### 真相源映射

- 用户分身真相源：`contracts/metadata/user/user_profile/*`
- 助手 session/request contract：`contracts/metadata/assistant/*`
- Prompt 只消费 typed 变量绑定，不承载 persona 主模型

### 无垂类特判、无字符串硬编码、模板资产化落实

- runtime 不根据文案、label、中文词汇识别分身
- planner / react / tool registry 不新增 persona 特判分支
- 若 prompt 需要展示当前身份，只能消费 typed `personaId/profileSubjectId` 对应的已解析资料变量

### 兼容逻辑与退出条件

- 允许短期保留“current session personaId -> profileSubjectId”的 adapter
- 退出条件：所有 assistant 入口、回放与工具请求都直接携带 typed persona context

## metadata / codegen 方案

建议冻结：

- `user/user_profile`
  - `ActivePersonaContextView`
  - activate/switch 相关 response entity
- `content/post`
  - 发布/评论 request context 中的 persona envelope
- `messages/conversation`
  - `senderPersonaId` 与 persona snapshot
- `assistant/*`
  - session/request payload 中的 `personaId`、`profileSubjectId`、`contextVersion`

执行：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

要求：

- App 与 assistant orchestration 只消费生成 contract
- 不允许在 runtime 中手写 `Map<String, dynamic>` persona 解析逻辑

## 字段演进、迁移/回填与兼容

### 字段演进

- 新写链路对内统一优先写 `personaId`
- `profileSubjectId` 保留为公开读取与兼容投影字段
- `subAccountId / senderPersonaId` 只作为 current alias 保留，但必须能映射回当前 `personaId`
- 新对象增加 `contextVersion` 与 `personaSnapshotVersion`

### 迁移 / 回填

- 旧内容/评论/消息记录对象不重写主体，只补充读取优先级与 snapshot adapter
- assistant 旧会话若只有 current persona 字段，读取时先映射成 `personaId`，再生成兼容 `profileSubjectId`
- circle 若当前仍是 app/local 状态，先统一消费 provider 中的 typed context，等正式服务化后迁到 metadata contract

### 退出条件

- 关键动作、通知回放、assistant 会话全部直接依赖 typed context
- current owner fallback 路径完全下线

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.persona_context_v1`

关键观测：

- `persona_context_switch_latency_ms`
- `persona_context_mismatch_count`
- `persona_context_stale_count`
- `notification_wrong_persona_open_count`
- `assistant_persona_drift_count`

回滚原则：

- 关闭开关后退回单 active persona 安全基线
- 已持久化的 `profileSubjectId` 与记录快照不回滚
- 助手只关闭 persona-aware session context，不得回滚成 runtime 文本判断

## TDD / ATDD 策略

- `T1_schema`
  - active persona context、request context、assistant session contract
- `T2_module_interaction`
  - provider、入口切换、stale context recovery、assistant adapter
- `T3_cross_service_integration`
  - content/chat/assistant/notification persona attribution 一致性
- `T4_user_journey`
  - 切换分身后立即评论/发消息/进入助手/打开通知
- `T4_release_rehearsal`
  - drift telemetry、mismatch blocking 与 rollback rehearsal

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结 active persona、request context 与 assistant session metadata | `A1/A2` | `T1_schema` |
| `P2` | 建立 codegen、cloud client、provider 基线 | `A1/A2` | `T1_schema`, `T2_module_interaction` |
| `P3` | 落地 content/chat/circle/assistant/notification 的 persona 消费与恢复逻辑 | `A2/A3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 验证 fail closed、telemetry、rollback 与端到端旅程 | `A3/S1` | `T3_cross_service_integration`, `T4_user_journey`, `T4_release_rehearsal` |

## 未来演进

- 后续若引入更复杂的“临时切换分身”体验，仍必须落在 typed override contract 内，不允许 UI 私有状态绕开 user 域。
- 助手若未来扩展 persona-aware memory，也只能以 session context 为入口，不新增 prompt/runtime 第二真相源。
