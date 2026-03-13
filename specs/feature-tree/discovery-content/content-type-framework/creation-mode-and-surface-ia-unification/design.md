# L3 Story：creation-mode-and-surface-ia-unification — 设计方案

## 设计动因

`spec.md v1.1` 已经冻结了统一 IA、数据生命周期、小趣权限、分享契约、商用品质指标与灰度回滚要求；设计阶段的任务是把这些“商用约束”落到一套可渐进实施、可灰度回退、且不破坏现有 `Post` 聚合的方案上。

当前代码与契约存在五个直接阻断实现的缺口：

1. 创作入口仍是 `CreateEntrySheet` 六宫格（`微趣照片/文字/视频` + `作品图片/文章/视频`），与动作优先入口冲突。
2. `CreatePage` 仍按 `moment/photo/video/article` 四 Tab 组织，并直接走 `DataService` 的裸 endpoint，未对齐 `ContentRepository` 与 metadata path builder。
3. `DiscoveryPage`、`ProfileShell`、`CircleShell` 仍分别持有自己的内容词表，尚未收口到同一套 identity grammar。
4. `content/post` 现有 metadata 只有 `contentType`，缺少“身份层”的持久化表达，也缺少发布后 `点滴 -> 作品` 的显式升级命令。
5. 小趣全局授权已有 `skill_consent` 能力，但“单条内容不给小趣使用”的排除能力尚未落到 Post 契约。

本设计的目标是：在保持 `Post` 单聚合、现有内容可读、现有 deeplink 不失效的前提下，最小化迁移面，建立统一 IA 的执行基线。

## 上游输入评审

| 维度 | 评审结论 |
|------|----------|
| `spec.md` | `v1.1` 已稳定，功能范围、商业 blocker、覆盖矩阵、权限边界、分享契约、迁移回滚均已冻结 |
| `acceptance.yaml` | `A1~A14` 已可测，`T1~T4` 映射齐全，适合直接拆解 task |
| 既有设计依赖 | `dual-rail-discovery-redesign`、`profile-homepage-redesign`、`circle-homepage-redesign` 已有可复用实现，但用户可见 IA 词表需以本 Story 覆盖 |
| 现有 metadata | `content/post` 已具备 `visibility`、`circleIds`、`summary`、`tags`、`shareCount`、`PostCircleDistribution`、`MomentPost` 图/视频可选字段，能承接渐进式升级 |
| 小趣授权能力 | `assistant/skill_consent` 已存在，可复用为“允许小趣使用我的创作内容”的总开关 |
| 阻断项 | **无 P0 阻断项**。设计阶段需要明确字段演进、发布后升级命令、运行时 kill switch 与回填策略 |

## 对标输入分析

### 外部对标

| 产品 | 借鉴点 | 不借鉴点 | 本设计吸收 |
|------|--------|----------|-----------|
| 小红书 | 动作优先入口、作品包装感、图文沉淀心智 | 不把全站统一叫“笔记” | 入口先选动作，发布前再确认身份；作品态强调标题/摘要/封面 |
| 微博 | 轻表达、关系流、即时互动 | 不把全部内容平权为同一种动态 | `点滴` 继续承担当下表达与关系流分发 |
| 微信朋友圈 | 低门槛分享、权限直觉强 | 不借鉴封闭传播与弱沉淀结构 | 分享模板与权限规则走动作层，不进入一级 IA |
| 抖音 | runtime 灰度、指标 gate、回滚路径明确 | 不借鉴单一视频世界观 | 使用 feature flag + runtime 配置 + canary gate 管理 rollout |

### 内部对标

| 现有节点 | 可复用能力 | 需要收口的部分 |
|---------|-----------|----------------|
| `dual-rail-discovery-redesign` | 发现页双轨架构、沉浸式作品轨、微趣轨分离 | 用户可见文案与 filter 语义改收口为 `点滴/作品` |
| `post-create-update--create-entry-location-visibility-circle` | `PublishSettings`、位置/圈子选择器、公开/私密联动 | 创作入口和编辑器需从四 Tab 改为统一编辑器 |
| `profile-homepage-redesign` | `ProfileShell` 骨架、用户资产容器视角 | 二级分类从 `全部/微趣/图片/视频/文字` 收口为 `全部/点滴/作品` |
| `circle-homepage-redesign` | `CircleShell` 骨架、板块式结构、圈内创作区 | 创作 Tab 二级分类收口到 `全部/点滴/作品` + 作品内格式筛选 |

## 方案对比

### 方案 A：纯 UI 推导，不改 metadata

**描述**：继续沿用现有 `contentType`（`micro/image/video/article`），只在端侧通过 UI 规则把 `micro` 解释成 `点滴`、`image/video/article` 解释成 `作品`，不新增字段、不新增命令。

**优点**：

- 迁移成本最低
- 不需要新增 codegen 产物
- 不需要回填历史数据

**缺点**：

- 无法把“身份层”作为可查询、可审计、可灰度、可观测的显式契约
- 发布后 `点滴 -> 作品` 只能通过隐式改写 `contentType` 实现，缺少专用命令与事件
- 小趣长期知识、分享模板、跨面一致性仍然依赖 UI 推导，无法形成稳定单一真相源

### 方案 B：新增 `contentIdentity`，保留现有 `contentType`，格式按组合与投影推导（选定）

**描述**：在 `Post` 上新增 `contentIdentity`，显式表达 `moment/work`；保留现有 `contentType` 作为兼容字段与作品格式字段。`点滴` 继续用 `contentType=micro`，但可携带图片/视频；`作品` 则使用 `contentType=image/video/article`。新增发布后升级命令 `PromotePostToWork`，用显式事件驱动投影与小趣索引刷新。

**优点**：

- 以最小 metadata 变更达成“身份层显式化”
- 不破坏现有 `Post` 聚合、已有 read model、现有 DTO 分发方式
- 支持 `点滴 -> 作品` 原地升级，并保持 `postId`、互动、deeplink 不变
- 可以把 discovery/profile/circle/share/assistant 全部挂到同一 identity 语义上

**缺点**：

- 需要新增字段、命令、事件与回填逻辑
- `点滴` 的展示格式需要通过 `contentType + media 字段` 推导，而不是单字段直接命中

### 方案 C：同时新增 `contentIdentity + contentFormat`，并逐步废弃 `contentType`

**描述**：把 `点滴/作品` 和 `图片/视频/笔记` 全部拆为两个持久字段，`contentType` 仅作为兼容层保留，后续彻底移除。

**优点**：

- 语义最纯粹
- 查询与统计维度最清晰

**缺点**：

- 迁移面过大，需要同时改写 DTO、路由、投影、历史数据、索引与大量现有 UI 分支
- 对当前 `MomentPost` / `PhotoPost` / `VideoPost` / `ArticlePost` read model 冲击过大
- 不适合在当前 Story 内作为最小可上线方案

## 选型决策

**选定方案 B**：新增 `contentIdentity`，保留现有 `contentType`，通过显式升级命令和投影规则完成统一 IA。

**理由**：

1. 它是满足 `spec.md v1.1` 的最小迁移方案。
2. 它可以让 identity 进入服务契约、事件、投影、埋点、灰度和回滚系统。
3. 它能复用现有 `MomentPost` 对图片/视频的可选承载能力，不需要同时引入第二个“格式字段”的大规模兼容工程。
4. 它为后续是否正式化 `contentTier`（精选/攻略/清单）保留扩展空间，但不把当前 Story 的迁移面做得过大。

## 关键设计决策

### DK1：规范化数据模型

本期持久化只新增“身份层”，不新增“格式层”持久字段。

| 用户可见语义 | `contentIdentity` | `contentType` | 展示格式来源 |
|-------------|-------------------|---------------|--------------|
| 点滴-纯文字 | `moment` | `micro` | derived = `note` |
| 点滴-多图 | `moment` | `micro` | derived = `image`（`mediaUrls.isNotEmpty`） |
| 点滴-短视频 | `moment` | `micro` | derived = `video`（`videoUrl != null`） |
| 作品-图片 | `work` | `image` | persisted |
| 作品-视频 | `work` | `video` | persisted |
| 作品-笔记 | `work` | `article` | persisted |

补充约束：

- `contentIdentity=moment` 时，`contentType` 必须为 `micro`
- `contentIdentity=work` 时，`contentType` 必须为 `image/video/article`
- `displayFormat` 只作为 app/assistant/view-model 计算属性，不在本 Story 中新增持久字段

### DK2：Post 新增字段最小集

在 `content/post/fields.yaml` 的 `Post` 上新增：

1. `contentIdentity`
   - enum：`moment / work`
   - 第一阶段 `NULLABLE`
   - 新写入必填，旧数据通过读路径 resolver 补全
2. `assistantUsePolicy`
   - enum：`inherit / exclude`
   - 默认 `inherit`
   - 与全局 consent 共同决定是否允许进入小趣消费链路

本 Story **不新增**：

- `contentFormat` 持久字段
- `contentTier` 持久字段
- 新的 Post 子聚合或独立作品表

### DK3：发布后可变能力拆成两个专用命令

为避免打破“发布后正文与媒体不可随意编辑”的约束，本期不复用 `UpdatePost` 做全部修改，而是引入两个显式命令：

1. `UpdatePostSettings`
   - 用途：更新 `visibility / circleIds / assistantUsePolicy`
   - 适用：草稿与已发布内容
   - 目的：支持转私密、圈子分发调整、单条内容不给小趣使用

2. `PromotePostToWork`
   - 用途：把已发布 `点滴` 原地升级为 `作品`
   - 可写字段：`title / summary / tags / coverUrl / assistantUsePolicy / visibility / circleIds`
   - 语义：同一 `postId` 下把 `contentIdentity=moment` 提升为 `work`，并把 `contentType` 改为 `image/video/article`

### DK4：`点滴 -> 作品` 的内容类型重绑定规则

`PromotePostToWork` 时，`contentType` 按已有素材与作者选择重绑定：

- `micro + mediaUrls` → `image`
- `micro + videoUrl` → `video`
- `micro + 无媒体` → `article`

规则：

- 原始正文和媒体不丢失
- 互动计数、评论、收藏、分享计数不重建
- 旧 deeplink、新详情页、分享落地页都指向同一 `postId`
- 事件层额外发布 `PostPromotedToWork`

### DK5：创作入口与统一编辑器的拆分方式

入口与编辑器分两层：

1. **动作层入口**
   - `从相册选`
   - `写点什么`
   - 可选：`拍一下`

2. **统一编辑器**
   - 统一 `CreateDraft` 状态模型
   - 统一 `PublishSettings`
   - 根据起始动作和当前素材决定编辑态
   - 编辑器顶部或发布前提供 `点滴 / 作品` 身份切换

端侧实现策略：

- 保留现有 `createEntry` / `create` 路由 ID，不改业务路径
- `CreateEntrySheet` 从六宫格改为三动作入口
- `CreatePage` 从四 Tab 改为 `UnifiedCreateEditor`
- 位置/圈子选择器继续复用 `PublishLocationSelectorPage`、`PublishCircleSelectPage` 与 `PublishSettings`

### DK6：创作链路停止走裸 `DataService`

当前 `CreatePage` 仍直接调用 `dataService.createDataItem(endpoint: '/posts')`，不符合 metadata-first 与 Repository 模式。

本期统一改为：

- 读写内容：`contentRepositoryProvider`
- 读写圈子列表：`circleRepositoryProvider` 或统一封装的 create-flow provider
- 路由、headers、decoder context 全部来自 codegen metadata

### DK7：统一 UI 配置模型

在 `content/post/ui_config.yaml` 中新增或收口以下配置段，由 codegen 生成端侧常量：

1. `discovery_rails`
   - `moment`
   - `work`

2. `creation_identity_filters`
   - 适用于 profile / circle 的 `全部 / 点滴 / 作品`

3. `work_format_filters`
   - `全部 / 图片 / 视频 / 笔记`

4. `share_template_profiles`
   - `moment`
   - `work`

5. `feature_flags`
   - `enable_create_action_entry`
   - `enable_unified_create_editor`
   - `enable_identity_based_surfaces`
   - `enable_identity_share_template`
   - `enable_assistant_content_identity_index`

设计原则：

- discovery、profile、circle 共享同一份 generated config
- 页面代码不再硬编码 `微趣/作品/图片/视频/文章`
- 旧 label 只保留 alias 映射，不继续出现在新 UI 代码中

### DK8：小趣总开关与单条排除的组合方式

**总开关**：复用现有 `assistant/skill_consent`，约定 skill id 为 `personal_content_access`。  
**单条排除**：使用 Post 上的 `assistantUsePolicy=exclude`。

判定公式：

`assistantEligible = globalConsentGranted && assistantUsePolicy != exclude && visibilityCheckPassed`

消费策略：

- `moment`：进入短中期 context memory，默认 TTL 30 天
- `work`：进入长期 knowledge index
- `guide/checklist`：本期作为 derived tier，不新增持久字段；由 `contentType=article` + tags taxonomy + summary/title 信号推导

### DK9：分享模板不新增服务端接口

分享模板由端侧根据现有 DTO 与新增 identity 字段组装，不新增专用 share-preview 接口。

模板规则：

- `moment`：首图/拼图 + 短文案 + 作者 + 时间/圈子语境
- `work`：封面 + 标题 + 摘要 + 作者 + 标签

权限规则：

- `private`：禁止对外分享
- `circle-visible`：只允许生成权限受控链接
- `public`：标准 deeplink

### DK10：圈子与主页的过滤顺序统一

两类容器页统一为：

1. 一级：`创作`
2. 二级 identity filter：`全部 / 点滴 / 作品`
3. 仅在 `作品` 内出现 format filter：`全部 / 图片 / 视频 / 笔记`

查询层约束：

- `ListUserPosts` 新增 `identity`
- `GetCircleFeed` 新增 `identity`
- 当 `identity=work` 时，`type` 才允许传 `image/video/article`
- 当 `identity=moment` 时，服务侧忽略 `type`

### DK11：精选/攻略/清单先做 derived tier，不立即持久化

本 Story 需要 assistant 优先级语义，但不适合在当前范围内同时引入 curation 工作流、运营台和多源写入。

因此本期规则是：

- `featured`：沿用圈子/运营既有精选位或后续配置来源
- `guide/checklist`：由 tags taxonomy + summary/title 推导
- 真正的 `contentTier` 持久字段，延后到“精品内容治理/攻略模板”后续 Story

### DK12：灰度与回滚粒度按能力拆分

五个能力独立 kill switch：

1. 动作优先入口
2. 统一编辑器与身份切换
3. 跨面 identity IA
4. identity-based 分享模板
5. assistant content identity index

任一开关关闭时，系统回到旧能力，但读路径继续支持新字段，避免数据回退。

## metadata / codegen 方案

### 需要修改的 metadata

1. `quwoquan_service/contracts/metadata/content/post/fields.yaml`
   - `Post` 新增 `contentIdentity`
   - `Post` 新增 `assistantUsePolicy`

2. `quwoquan_service/contracts/metadata/content/post/service.yaml`
   - `CreatePost` / `UpdatePost` / `PublishPost` 增加对 identity / assistant policy 的写入支持
   - `GetFeed` / `ListUserPosts` 增加 `identity` query
   - 新增 `UpdatePostSettings`
   - 新增 `PromotePostToWork`

3. `quwoquan_service/contracts/metadata/social/circle/service.yaml`
   - `GetCircleFeed` 增加 `identity` query
   - `type` 仅在 `identity=work` 时使用

4. `quwoquan_service/contracts/metadata/content/post/events.yaml`
   - `PostCreated` / `PostPublished` / `PostUpdated` payload 增加 `contentIdentity`
   - 新增 `PostPromotedToWork`
   - 新增 `PostSettingsUpdated`

5. `quwoquan_service/contracts/metadata/content/post/projections/*.yaml`
   - `discovery_feed.yaml`
   - `moment_post.yaml`
   - `photo_post.yaml`
   - `video_post.yaml`
   - `article_post.yaml`
   - 均增加 `contentIdentity`
   - 端侧投影增加 `identity` 与 `displayFormat` 计算属性

6. `quwoquan_service/contracts/metadata/content/post/ui_config.yaml`
   - discovery rails
   - creation identity filters
   - work format filters
   - share template profiles
   - compile-time flag defaults

7. `quwoquan_service/contracts/metadata/content/post/tests/contract.yaml`
   - 新增 identity filter、promotion、settings 更新、权限撤销场景

### 需要更新的 codegen 产物

- `content_api_metadata.g.dart`
- `content_request_page_ids.g.dart`
- `content_dtos.dart` 及各 Post DTO
- `content_ui_config.g.dart`
- `PostBaseDto` 手写基类

### `PostBaseDto` 基类扩展

统一抽象基类新增：

- `identity`
- `displayFormat`
- `assistantUsePolicy`

其中：

- `displayFormat` 对 `MomentPostDto` 采用 computed getter
- `PhotoPostDto` / `VideoPostDto` / `ArticlePostDto` 直接返回常量

## 字段演进、迁移 / 回填、双读双写方案

### 第 1 步：加字段，不收紧约束

- `contentIdentity`: `NULLABLE`
- `assistantUsePolicy`: `NULLABLE` 或带 `DEFAULT_INHERIT`

读路径 resolver：

```text
contentIdentity =
  persisted.contentIdentity
  ?? (contentType == micro ? moment : work)

assistantUsePolicy =
  persisted.assistantUsePolicy
  ?? inherit
```

### 第 2 步：新写入走双写

所有新创建 / 草稿保存 / 发布 / 升级命令都必须写入：

- `contentType`
- `contentIdentity`
- `assistantUsePolicy`

### 第 3 步：历史内容回填

回填规则：

- `micro` → `contentIdentity=moment`
- `image/video/article` → `contentIdentity=work`
- `assistantUsePolicy` 统一回填 `inherit`

### 第 4 步：本地草稿迁移

`CreatePage` 当前本地草稿结构按 `moment/photo/video/article` 存储。迁移到 `CreateDraft v2` 时：

- 老草稿读取后转为统一 draft
- `moment` 草稿 -> `contentIdentity=moment`
- `photo/video/article` 草稿 -> `contentIdentity=work`

### 第 5 步：投影与索引重建

需要重建：

- discovery feed
- user posts list
- circle feed
- assistant content index

### 第 6 步：稳定后再收紧约束

当回填和灰度指标稳定后，再将 `contentIdentity` 升级为 `NOT_NULL`。  
该动作不在本 Story 首次上线批次内执行。

## feature flag、观测、SLO 验证与回滚方案

### 运行时开关来源

采用“两层开关”：

1. `ui_config.yaml` 生成编译期默认值
2. `GetAppConfig` 返回运行时覆盖值

灰度分桶由 `ops/experiment_bucket` 负责，app 只消费已解析好的布尔开关。

### 核心运行时开关

| flag | 作用 | 关闭后的回退 |
|------|------|--------------|
| `enable_create_action_entry` | 三动作入口 | 回退到旧六宫格入口 |
| `enable_unified_create_editor` | 统一编辑器 + 身份切换 | 回退到旧四 Tab `CreatePage` |
| `enable_identity_based_surfaces` | discovery/profile/circle 新 IA | 回退到旧 surface 配置 |
| `enable_identity_share_template` | `点滴/作品` 分享模板 | 回退到旧通用分享 sheet |
| `enable_assistant_content_identity_index` | 小趣 identity 路由 | 回退到旧统一内容索引路径 |

### 观测指标

| 指标 | 来源 |
|------|------|
| 入口打开成功率 / 耗时 | app 埋点 |
| 身份建议曝光率 / 接受率 / 手动切换率 | app 埋点 |
| 草稿自动保存成功率 / 恢复成功率 | app 埋点 + crash 恢复日志 |
| 发布成功率 / promote 成功率 | content-service 指标 |
| discovery/profile/circle 跨面 identity mismatch | 端侧 audit + 服务侧抽样校验 |
| assistant revoke latency | assistant-service + projector 指标 |
| 分享完成率 / 权限拦截率 | app 埋点 |

### SLO 验证

- create entry → editor ready：warm `P95 <= 1.2s`，cold `P95 <= 2.0s`
- identity switch：`P95 <= 150ms`
- publish success：`>= 99.5%`
- crash-free sessions：`>= 99.8%`
- author/profile/circle 收敛：`P95 <= 5s`
- discovery/assistant reindex：`P95 <= 30s`
- revoke latency：`P95 <= 5 分钟`

### 回滚策略

| 故障类型 | 回滚动作 |
|---------|---------|
| 入口崩溃/严重卡顿 | 关闭 `enable_create_action_entry` 与 `enable_unified_create_editor` |
| surface 文案错乱/混层 | 关闭 `enable_identity_based_surfaces` |
| 分享越权 | 关闭 `enable_identity_share_template` |
| 小趣继续引用已撤销内容 | 关闭 `enable_assistant_content_identity_index`，并触发索引补偿任务 |
| promote 命令异常 | 关闭 `PromotePostToWork` 的 runtime exposure，仅保留读路径兼容 |

## TDD / ATDD 策略

| 验收项 | 设计策略 |
|--------|----------|
| A1 | 先写 metadata / generated config contract，确保 identity、旧 alias、显示词表唯一化 |
| A2 | 先写入口 widget / patrol，确保没有 `微趣/作品/图片/视频/文章` 六入口残留 |
| A3 | 先写 unified editor draft round-trip test，再重构 `CreatePage` |
| A4 | 先写 publish suggestion 规则 test，再接入 `contentIdentity` 写入 |
| A5 | 先写 discovery rail config + widget audit，再切页面 |
| A6 | 先写 profile/circle cross-surface consistency journey，再切容器页 |
| A7 | 先写 promote contract 与 deeplink 保持测试，再落升级命令 |
| A8 | 先写 assistant route policy test，再接 projector/index |
| A9 | 先写 launch blocker checklist 与 SLA probe，再放灰度 |
| A10 | 先写 spec precedence audit，再做 legacy consumer 清理 |
| A11 | 先写 in-place upgrade lifecycle contract，再做 backfill |
| A12 | 先写 revoke eligibility integration test，再做权限回放 |
| A13 | 先写 share payload matrix test，再接模板装配 |
| A14 | 先写 rollout/rollback rehearsal checklist，再放 canary |

## Task 与 `T1~T4` 证据矩阵

| Task 组 | 对应验收 | 测试层 | 说明 |
|--------|----------|--------|------|
| P1-P4 | A1-A2 | T1/T2/T4 | metadata、codegen、入口动作优先 |
| P5-P9 | A3-A4 | T1/T2/T3/T4 | 统一编辑器、发布建议、专用命令 |
| P10-P16 | A5-A7 | T1/T2/T3 | discovery/profile/circle/cross-surface/promote |
| P17-P18 | A8 | T1/T3 | 小趣语义路由与授权排除 |
| P19-P21 | A9 | T1/T3/T4 | 商用品质指标、SLO probe、blocker checklist |
| P22-P23 | A10 | T1/T2 | precedence audit 与 legacy 文案清理 |
| P24-P25 | A11 | T1/T3 | 生命周期合同、投影重建、回填审计 |
| P26-P27 | A12 | T1/T3 | 权限边界、撤销时效、引用标注 |
| P28-P29 | A13 | T1/T2/T3 | 分享模板与权限回退 |
| P30-P32 | A14 | T1/T3/T4 | feature flag、canary、rollback rehearsal |

## 未来演进

- 正式化 `contentTier` 持久字段（`normal/featured/guide/checklist`）
- 外部平台 SDK 级分享接入（微信/朋友圈/微博/小红书）
- 使用统一 runtime config / remote config 替代 `GetAppConfig` 的局部 flag 承载
- 为 assistant 引用增加更细粒度的“片段级引用来源”与用户可见引用面板
