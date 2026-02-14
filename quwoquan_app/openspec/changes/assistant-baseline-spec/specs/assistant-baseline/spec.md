# assistant-baseline

小趣私人助手基线能力：浏览信息存储与半弹窗入口形态。

## ADDED Requirements

### Requirement: 访问对象与访问记录模型

系统 SHALL 使用 VisitTarget 表示被访问对象、VisitRecord 表示单条访问记录。VisitTarget 须支持页面型（如 `page_discovery_photo`、`page_create_edit`）与实体型（如 `entity_author_<id>`、`entity_circle_<id>`），并具有唯一 targetKey。VisitRecord 须包含 targetKey、firstSeenAt、lastSeenAt、visitCount，以及用于派生 7 天/30 天访问次数的字段（如 lastNTimestamps 或 count7d/count30d）。

#### Scenario: 页面型 VisitTarget 生成 targetKey

- **WHEN** 解析发现页美图 tab
- **THEN** 得到 targetKey 为 `page_discovery_photo`（或与约定一致的页面型 id）

#### Scenario: 实体型 VisitTarget 生成 targetKey

- **WHEN** 解析作者主页且 authorId 为 `uid_123`
- **THEN** 得到 targetKey 为 `entity_author_uid_123`

#### Scenario: VisitRecord 持久化后可查询

- **WHEN** 已对某 VisitTarget 调用 recordVisit 至少一次
- **THEN** getRecord(target) 返回该 targetKey 对应的 VisitRecord，且 firstSeenAt、lastSeenAt、visitCount 与写入一致

---

### Requirement: 体验等级派生

系统 SHALL 根据 VisitRecord 的 visitCount 与 7 天/30 天内访问次数，派生 experienceLevel：first_time（首次）、returning（再次）、frequent（常用）。getExperience(VisitTarget) 返回的体验等级 SHALL 与当前存储数据一致。

#### Scenario: 首次访问为 first_time

- **WHEN** 某 VisitTarget 从未被记录
- **THEN** getExperience(target) 返回 experienceLevel 为 first_time（或等价枚举）

#### Scenario: 再次与常用由次数规则决定

- **WHEN** 某 VisitTarget 已有记录且 7 天内访问次数或总次数满足「再次」或「常用」规则
- **THEN** getExperience(target) 返回 returning 或 frequent（具体阈值由实现与配置约定）

---

### Requirement: 本地存储与 VisitRecorderService

系统 SHALL 使用 Hive 单 box（如 `visit_records`）存储 VisitRecord，key 为 targetKey。系统 SHALL 提供 VisitRecorderService（或等价命名），封装 recordVisit(VisitTarget)、getExperience(VisitTarget)、getRecord(VisitTarget)；同一 targetKey 在 5 分钟内重复 recordVisit 时 SHALL 仅更新 lastSeenAt，不增加 visitCount。

#### Scenario: 5 分钟内同 target 去重

- **WHEN** 对同一 VisitTarget 在 5 分钟内连续调用两次 recordVisit
- **THEN** 该 target 的 visitCount 只增加 1，lastSeenAt 更新为第二次调用时间

#### Scenario: 超过 5 分钟再次记录增加次数

- **WHEN** 对同一 VisitTarget 两次 recordVisit 间隔大于 5 分钟
- **THEN** visitCount 增加 2，lastSeenAt 为第二次时间

---

### Requirement: 云端同步预留接口

系统 SHALL 定义 VisitSyncService 抽象类（或接口），至少包含：uploadLocalVisits()、pullAndMergeRemoteVisits()；数据契约 SHALL 与 VisitRecord 结构一致（含 targetKey、firstSeenAt、lastSeenAt、visitCount 等）。系统 MUST NOT 在本基线内实现具体网络请求、鉴权与冲突策略。

#### Scenario: 存在 VisitSyncService 抽象

- **WHEN** 实现层提供 VisitSyncService 的抽象定义
- **THEN** 方法签名与注释明确上传/拉取合并语义，且与 VisitRecord 可序列化结构一致

---

### Requirement: 打开小趣时传入 AssistantOpenContext

系统 SHALL 在打开小趣时组装 AssistantOpenContext，包含 source（如 discovery/circles/article/profile/chat/create）、当前 tab 或 dimension 或 entityId、当前页对应的 VisitTarget、由 VisitRecorderService 得到的 experienceLevel、以及可选的 hints（如 hasAddedMedia、channelCount）。半弹窗与进入完整对话时 SHALL 使用同一 AssistantOpenContext。

#### Scenario: 从发现页打开小趣携带 source 与 tab

- **WHEN** 用户在发现页美图 tab 点击小趣入口
- **THEN** AssistantOpenContext 的 source 为 discovery，tab（或等价字段）标识美图，且 experienceLevel 来自 getExperience(当前页 VisitTarget)

#### Scenario: 会话页可读取 extra 中的 context

- **WHEN** 用户在半弹窗内点击「进入完整对话」并 push 至 `/chat/assistant`
- **THEN** 会话页可从 state.extra 读取 AssistantOpenContext，用于首条欢迎与推荐

---

### Requirement: 小趣统一先展示半弹窗

系统 SHALL 将所有「打开小趣」的入口改为先展示半弹窗（如 showModalBottomSheet，isScrollControlled: true，初始高度约 50% 屏高，可拖拽展开/收起），不再直接 push 助理主页或会话页。半弹窗 SHALL 接收 AssistantOpenContext 并据此渲染内容。

#### Scenario: 发现页小趣入口打开半弹窗

- **WHEN** 用户在发现页点击小趣图标
- **THEN** 展示半弹窗而非全屏助理页或会话页

#### Scenario: 聊天列表助理入口打开半弹窗

- **WHEN** 用户在聊天列表点击置顶助理会话或「找小趣」
- **THEN** 展示半弹窗，且 context 的 source 可标识来自 chat

---

### Requirement: 半弹窗内容结构

半弹窗 SHALL 包含：顶部标题区（小趣头像与名称）；上下文欢迎区（一句根据 source/tab/experienceLevel 选择的短文案）；推荐操作 chips（3～5 个，文案与行为可配置）；「当前适合干啥」区块（1～2 条）；底部输入框与「进入完整对话」按钮。点击「进入完整对话」SHALL 关闭半弹窗并 push `/chat/assistant`，且 extra 为当前 AssistantOpenContext。

#### Scenario: 半弹窗显示上下文欢迎句

- **WHEN** 用户打开半弹窗且 AssistantOpenContext 为发现·美图、first_time
- **THEN** 欢迎区显示与「发现·美图」「首次」对应的欢迎句（来自配置或常量）

#### Scenario: 进入完整对话关闭半弹窗并跳转

- **WHEN** 用户在半弹窗内点击「进入完整对话」
- **THEN** 半弹窗关闭，且当前路由变为 `/chat/assistant`，state.extra 为 AssistantOpenContext

---

### Requirement: 欢迎句与推荐 chips 由配置驱动

欢迎句、推荐 chips 与「当前适合干啥」内容 SHALL 由配置（常量或小型配置表）按 (source, tab/entityKind, experienceLevel) 驱动，半弹窗仅负责查表与渲染，不内联复杂分支。

#### Scenario: 不同体验等级展示不同 chips

- **WHEN** experienceLevel 为 first_time 与 frequent
- **THEN** 展示的推荐 chips 可不同（如首次偏教学向、常用偏效率向），且来自同一配置体系

---

### Requirement: 关键场景记录访问

系统 SHALL 在以下场景解析当前 VisitTarget 并调用 VisitRecorderService.recordVisit(target)：发现页切到一级 tab；圈子页切到一级维度或进入圈子详情；作者主页进入；圈子主页进入；创作页进入子步骤（选图/编辑/写文案/发布）。解析可由各页或 RouteToVisitTargetMapper 完成，且须满足 5 分钟同 target 去重（由 VisitRecorderService 保证）。

#### Scenario: 进入发现页美图 tab 时记录

- **WHEN** 用户进入发现页并切换到美图 tab
- **THEN** recordVisit 被调用，且 VisitTarget 对应 page_discovery_photo（或约定 id）

#### Scenario: 进入作者主页时记录

- **WHEN** 用户进入某作者主页（如 /user/:id）
- **THEN** recordVisit 被调用，且 VisitTarget 为 entity_author_<id>
