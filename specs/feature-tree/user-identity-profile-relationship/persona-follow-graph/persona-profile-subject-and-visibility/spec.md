# L3 Scenario: persona-profile-subject-and-visibility

## 节点定位

- `L1_capability`: `user-identity-profile-relationship`
- `L2_journey`: `persona-follow-graph`
- `L3_scenario`: `persona-profile-subject-and-visibility`

本场景冻结“作者分身如何被看见”的领域基线：`Persona` 如何映射成公开可读的 `ProfileSubject`，如何继承用户资料基线，如何覆写作者形象，以及停用后的记录归因如何保持稳定。

本场景只负责 user 域身份读写契约与可见性，不负责主页壳层 UI。`profile-homepage-redesign/owner-subaccount-homepage-unification` 必须消费本场景冻结的契约，而不是再次定义一套 persona 读模型。

## 背景与动机

当前“作者分身”在公开表面的语义仍不稳定：

1. **公开主体混用**：`profileSubjectId`、`subAccountId`、`userHandle`、`username`、`PersonaDto`、`ProfileSubjectView` 在不同页面和 Repository 中并行存在。
2. **资料继承未形成统一合同**：owner 基线、分身覆写、同步范围、公开可见性已有零散字段，但缺少对“作者分身如何编辑和展示”的统一规格。
3. **停用后的记录归因缺失基线**：如果分身退出使用，记录内容、评论、聊天消息、通知如何保留作者快照，目前没有冻结的产品合同。

本场景的目标是冻结 user 域对外可消费的身份读模型与写模型，让 profile/content/chat/circle/assistant 只做消费，不再各自解释“作者是谁”。

## 目标用户

- 希望为不同内容语境维护不同公开作者形象的创作者。
- 既要统一管理 owner 基线，又希望某些分身拥有局部覆写资料的多身份用户。
- 通过主页、内容卡、评论、聊天头像去识别某个作者分身的普通用户。

## 功能范围

### F1. `ProfileSubject` 作为唯一公开身份读模型

对外公开身份统一收口为 `ProfileSubject`，至少包含：

- `profileSubjectId`
- `subjectType`
- `subAccountId`
- `userHandle`
- `username`
- `displayName`
- `avatarUrl`
- `backgroundUrl`
- `bio`
- 统计字段、`isolationLevel` 与 `profileVisibility`

约束：

- 外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- `PersonaDto` 可以继续作为 user 域内部管理对象，但不得直接作为公开主页首屏真相源。
- `userHandle` 是公开句柄真相源；`username` 仅保留为兼容展示/路由别名，不再承担内部主键语义。

### F2. owner 基线与分身覆写

资料语义冻结为：

- owner 提供资料基线。
- 分身默认继承 owner 的公开资料基线。
- 分身只保存覆写字段，不复制一整份 public profile。
- 读路径由 user 域合成 `ProfileSubjectView`。

支持覆写的首批字段：

- `displayName`
- `userHandle`
- `phone`
- `email`
- `avatarUrl`

本阶段不把 `backgroundUrl / bio` 做成 persona 级覆写字段；两者继续作为 owner 基线的公开读字段返回。
`profileVisibility` 也不再单独写入，而是继续由 `isolationLevel` 派生。

### F3. 写入与同步范围

分身资料写入必须显式携带同步范围，不能只藏在前端临时状态里。

写入模型至少支持：

- 当前分身生效
- 仅同步到 owner
- 同步到其它分身
- 选择性同步到指定目标

产品要求：

- 用户在编辑 owner 或分身资料后，系统应能提示“是否同步到其它分身 / owner”。
- 同步范围是 user 域写入契约的一部分，不是 UI 私有逻辑。
- 首批可同步字段冻结为 `displayName / userHandle / phone / email / avatarUrl`；`isolationLevel / purposeHint` 仅对当前分身生效。

### F4. 可见性与公开读取

作者分身的公开可见性冻结如下：

- `open`：可公开访问与被发现
- `semi`：可被已知路径访问，但不参与某些发现/推荐
- `strict`：公开读取返回 `404` 或等效不可见语义

约束：

- `IsolationLevel` 是公开访问边界真相源。
- `ProfileVisibility` 仅作为公开展示层兼容枚举：`open -> public`、`semi -> friends`、`strict -> private`。
- `strict` 只影响公开读取，不影响用户私有管理视角和审计视角。
- 公开读取不允许返回 owner 映射信息。

### F5. 停用后的记录归因

分身停用后，记录归因必须稳定：

- 记录内容、评论、聊天消息、通知保留不可变作者快照。
- 停用不会把记录内容重绑到 owner 或其它分身。
- 停用后的 `ProfileSubject` 是否继续开放公开页，由 user 域可见性策略统一决定；第一版允许公开页关闭，但记录对象仍应使用快照正常渲染。

### F6. 路由与引用合同

- 对外分享路由继续使用公开路径，如 `/user/{userHandle}`。
- 内部身份引用统一使用 `profileSubjectId` 或 `subAccountId`。
- `userHandle` 承担公开路由与展示主语义；`username` 仅作为兼容别名。

## 领域边界

### 本场景负责

- `user` 域 `ProfileSubjectView / ProfileSubjectMutation`
- owner 基线与 persona 覆写语义
- 公开可见性与记录归因规则

### 本场景消费但不负责

- 主页壳层、ActionBar、Tabs、滚动动效：由 `profile-homepage-redesign` 负责
- 内容、评论、聊天、圈子的具体渲染：由各消费域负责

### 明确禁止

- 在 content/chat/circle/assistant 域复制一套作者分身实体
- 在 UI 直接拼接 owner 与 persona 的公开身份规则

## 权限边界与数据生命周期

- 只有 owner 可编辑自己分身的公开身份。
- 普通用户只能读取 `ProfileSubject` 允许公开的字段。
- 停用分身不得继续作为新动作主体，但其记录归因必须可追踪、可渲染、可审计。
- 合规物理清除不在本场景范围；第一版只冻结停用、公开可见性和快照保留策略。

## 不做什么（Out of Scope）

- 主页视觉重构与滚动吸顶实现。
- 分身列表、配额与删除保护 UI。
- 发帖、评论、聊天、圈子、助手中的上下文透传实现。

## 对标输入

| 对标 | 吸收点 |
|---|---|
| 小红书 | 作者主页与内容作者身份的一致性 |
| 抖音 | 公开身份展示与隐私可见性的清晰分层 |
| 微信 | 管理平面与应用主体分离 |

## 非功能目标

- `ProfileSubject` 公开读取 P95 < 800ms。
- 资料编辑与同步范围提交 P95 < 1.5s。
- 停用后的记录对象作者渲染正确率 100%，灰度期不允许出现 owner 重绑。

## 验收重点

1. `ProfileSubject` 成为唯一公开身份真相源，公开读取不再直接消费 `PersonaDto`。
2. owner 基线、分身覆写、同步范围和可见性规则一次性冻结。
3. 停用分身后的记录归因有清晰合同，内容/评论/聊天/通知都可稳定消费。
