# L1 群组入口与圈子内核 — 整体设计方案

## 设计动因

本轮 PRD 已经把圈子主线重写为：

- 全局入口统一叫 `群组`
- 详情页分为 `通用圈子模板` 与 `组织主页模板`
- 群不再等同于聊天群，而是承接 `交流 / 资料 / 公告` 的子单元
- 内容、成员、群与具体事物的边界必须重新冻结

如果没有一版新的 L1 设计，后续实现会继续回到三类旧问题：

1. 首页与搜索都叫“圈子”，学校、院系、班级、公司、部门会继续显得违和。
2. 详情页只有一套兴趣圈模板，组织型关系沉淀无法自然承接。
3. 群仍会被误建模成 Conversation 的别名，无法承接群主、群资料、群公告和加入审批。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-community/spec.md` | 已冻结“群组入口 + 圈子内核 + 组织主页模板” |
| `circle-community/acceptance.yaml` | `A1~A9` 已能承接本轮设计与后续 plan |
| `circle-experience-redesign/spec.md` | 已冻结统一发现与双模板详情基线 |
| `circle-homepage-redesign/spec.md` | 已冻结模板级首页、内容、群/组织、成员结构 |
| `circle-collaboration-tools/spec.md` | 已冻结群不是纯聊天群，而是子单元协作空间 |
| `global-search-experience/spec.md` | 已冻结首页与搜索统一入口词为 `群组` |
| 具体事物会话边界 | 已明确只消费摘要，不在本会话展开主档与抓取 |

结论：

- `/design` 准入满足。
- 本次设计需要真正覆盖 metadata/codegen、字段演进、迁移、观测与回滚。
- 由于本轮设计涉及 metadata/codegen 方案，后续将执行真实 G1 校验命令。

## 对标输入分析

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| 微信群 / 企业微信 | 单入口容纳不同关系对象、正式组织不必强行娱乐化命名 | 不照搬企业通讯录与聊天完全绑定的结构 |
| Discord Server | 子单元治理、角色分层、子空间可承载多能力 | 不照搬频道级信息架构与实时通讯优先 |
| 小红书 | 统一发布模型、内容再挂载具体对象 | 不把所有详情页都做成同一种兴趣社区页 |
| 豆瓣小组 | 内容沉淀、管理员秩序和精华心智 | 不延续纯文字论坛和单列主形态 |

## 方案对比

### 方案 A：所有关系主页前台统一继续叫“圈子”

优点：

- 命名最省事。
- 现有代码、文案和路径改动最小。

缺点：

- 学校、院系、班级、公司、部门会继续显得世俗化。
- 组织型角色与节点语义会被兴趣圈语言污染。
- 搜索与首页在用户层无法自然解释。

### 方案 B：把兴趣圈和组织主页拆成两个完全独立世界

优点：

- 前台语义最纯。
- 可以分别设计完全不同的信息架构。

缺点：

- 首页、搜索、推荐、关注、加入、管理都会分裂成两套。
- 会重复建设内容、成员、群等同构能力。
- 后续与具体事物和搜索结果面会再次裂开。

### 方案 C：全局统一 `群组` 入口，详情页使用双模板，共享一个 circle 内核

优点：

- 首页和搜索保持一个入口心智。
- 兴趣型与组织型只在模板层分叉，底层能力保持复用。
- 可以在不重命名服务与仓储的前提下完成一把升级。

缺点：

- 需要新增群模型，而不是继续把群等同于会话。
- 需要在 UI 层仔细处理模板差异，避免看起来像“强套皮”。

## 选型决策

**选定方案：方案 C**

理由：

1. 它同时满足“用户心智不分裂”和“前台语言不违和”。
2. 它允许本轮只升级产品和领域模型，不强制重命名现有 `circle` 域。
3. 它最适合与全局搜索、推荐、内容和后续具体事物摘要集成保持一致。

## 关键设计决策

### D1：全局入口统一叫 `群组`

- 首页一级入口和搜索一级筛选统一叫 `群组`。
- `圈子` 只保留为兴趣型详情页名称。
- 学校、院系、班级、公司、部门前台直接显示具体名称。

### D2：底层内核继续复用 `circle` 域

- 本轮不重命名 `circle-service`、`CircleRepository`、`ui/circle/`。
- `Circle` 在领域层继续代表“群组主页”这一聚合根。
- 用户词与技术词分离：前台叫群组，内部保留 circle。

### D3：引入独立的 `CircleGroup` 子单元实体

本轮必须停止把“群”直接等同于 `Conversation`。

选型对比：

- 方案 A：继续用 `Conversation` 直接代表群。
- 方案 B：引入 `CircleGroup`，并把 `conversationId` 作为群的一个能力绑定。

**选定方案：方案 B。**

原因：

- 群还要承载资料、公告、加入审批、公开/私有、群主/群管。
- 组织节点（院系、班级、部门）也要复用同一子单元模型。
- `Conversation` 只能代表交流能力，不能承担群的全量语义。

### D4：公开内容归群组层，群层不再承接主公开时间线

- 群组详情页承接公开内容主 feed。
- 群层承接 `交流 / 资料 / 公告`。
- 组织节点可以独立发布内容，但其内容仍归属于群组内容体系，并支持父节点聚合。

### D5：内容模型统一为“发布内容”

- 一级内容类型冻结为 `笔记 / 作品 / 提问 / 口碑`。
- 表达形式冻结为 `图文笔记 / 视频 / 文章`。
- 总添加入口继续保持 `相册 / 视频 / 长文`。
- 群组内入口与总添加入口共用同一发布器，只改变默认上下文。

### D6：加入群组与加入群严格分离

- 用户加入群组后，不默认自动加入任何群。
- `公共群` 一律只能 `申请加入`。
- 小型群组可只有一个默认公共群，但仍需要用户主动申请。
- 大型群组不自动分裂，不自动建群，由圈主/管理员或负责人/管理员手动新建。
- 多个公共群必须先命名后对外展示。

### D7：自建群的公开与私有边界

- 自建群分为 `公开` 与 `私有`。
- 默认公开。
- 公开自建群：圈内成员可在群列表中看到。
- 私有自建群：不出现在默认列表中，仅圈内成员可搜索。
- 私有自建群搜索规则：
  - 按 `groupId` 精确匹配
  - 按 `groupName` 支持模糊匹配

### D8：角色分层

- 圈级：`圈主 / 圈管`
- 组织主页级：`负责人 / 管理员`
- 群级：`群主 / 群管`

治理边界：

- 上位治理者只对 `公共群` 拥有 `转让群主 / 解散群` 权限。
- 不拥有对私有自建群的处置权。
- 普通成员可见管理页面骨架，但所有不可执行操作为 disabled。

### D9：组织节点内容支持向上聚合

- 组织节点可以独立发布内容。
- 父节点可聚合展示子节点内容。
- 默认排序按 `最近活跃时间`，而不是仅按发布时间。
- 最近活跃时间由发布时间与评论/回复更新时间共同决定。

### D10：组织型主页保留关注关系

- 组织型主页同时支持 `关注` 与 `加入 / 身份归属`。
- 关注用于轻量订阅与后续推荐。
- 加入或身份归属用于节点参与、群申请与治理。

### D11：搜索接口使用统一搜索入口

- 产品层不再为群组、内容、人、具体事物分别设计独立搜索体验接口。
- 对用户暴露的是一个统一的 `Search` 能力，类似 web search。
- `global-search-experience` 负责统一编排；circle 域只提供群组结果与 facet 真相源。

## 元数据 / codegen 方案

本轮设计冻结以下元数据演进方向：

### `contracts/metadata/social/circle/fields.yaml`

新增或扩展：

- `Circle.kind`
  - `interest`
  - `organization`
- `Circle.display_subject_type`
  - `circle`
  - `school`
  - `college`
  - `grade`
  - `class`
  - `company`
  - `department`
- `Circle.follow_enabled`
- `CircleGroup`
- `CircleGroupMember`

`CircleGroup` 关键字段建议：

- `circleId`
- `parentGroupId`
- `groupType`: `public | self_built | org_node`
- `nodeType`: `generic | college | grade | class | department | team`
- `displayName`
- `description`
- `visibility`: `public | private`
- `joinPolicy`: `apply_only`
- `searchMode`
- `conversationId`
- `storageEnabled`
- `noticeEnabled`
- `isDefaultPublicGroup`
- `status`
- `ownerUserId`
- `managerIds`

`CircleGroupMember` 关键字段建议：

- `groupId`
- `userId`
- `role`: `owner | manager | member`
- `status`: `pending | joined | rejected`

### `contracts/metadata/social/circle/service.yaml`

新增或扩展：

- `ListCircleGroups`
- `CreateCircleGroup`
- `UpdateCircleGroup`
- `ApplyJoinCircleGroup`
- `ApproveCircleGroupJoin`
- `RejectCircleGroupJoin`
- `TransferCircleGroupOwner`
- `ArchiveCircleGroup`

### `contracts/metadata/content/post/*`

扩展群组内容分发字段：

- 在 `PostCircleDistribution` 或等价分发表中增加 `groupId` / `nodeId`
- 支持组织节点独立发布
- 支持父节点聚合查询
- 支持按最近活跃时间排序

### `contracts/metadata/messages/conversation/*`

保留：

- `circleId`

新增建议：

- `circleGroupId`

使 Conversation 绑定到具体 `CircleGroup`，而非直接把 Conversation 当群本身。

### `_shared/*`

- 首页与搜索入口相关 route / surface / request context 继续对齐 `群组` 用户词
- 内部仍消费 circle 域的 typed 结果与 facet

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- `Circle` 从单一兴趣圈模型演进为群组主页聚合根。
- 新增 `CircleGroup / CircleGroupMember`。
- `Conversation.circleId` 补充 `circleGroupId`，把“交流能力”从“群模型”中拆开。
- 内容分发表新增 `groupId/nodeId`。

### 迁移 / 回填

- 现有单 `conversationId` 的圈子，迁移为“默认公共群”。
- 小型群组可由迁移脚本自动生成 1 个默认公共群记录，并把原 `conversationId` 绑定到该群。
- 组织型主页首期支持手工录入与批量导入组织树。
- 原有圈子内容默认落在 `circleId` 维度；无明确分组归属的记录内容不强制回填 `groupId`。

### 双读 / 双写

- 迁移阶段允许 `Circle.conversationId` 与 `CircleGroup.conversationId` 短期并行读取。
- dev 完成后，`Circle.conversationId` 只保留为兼容字段，最终退出条件：
  - 所有公共群均有 `CircleGroup`
  - 端侧与 chat 域全部改读 `CircleGroup.conversationId`

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 本轮不新增用户可见 feature flag。
- 发布控制采用整版上线与整版回滚。

### 观测

关键指标：

- `group_hub_open_count`
- `group_hub_join_count`
- `circle_group_apply_count`
- `circle_group_apply_approved_count`
- `circle_group_apply_rejected_count`
- `circle_group_search_private_hit_count`
- `circle_group_content_aggregate_latency_ms`

### SLO 验证

- 群组首页首屏即时可见。
- 群目录打开与申请流程 P95 在可接受范围内。
- 父节点内容聚合首批结果 P95 不超过群组内容主流约定阈值。

### 回滚

1. 优先整版回退到旧圈子实现。
2. 若仅群模型迁移失败，允许回退到“单圈默认群”兼容读路径。
3. 记录圈子内容不做破坏性清理。

## TDD / ATDD 策略

- `T1_schema`
  - Circle / CircleGroup / CircleGroupMember contract
  - groupId / nodeId 内容分发表
  - search route / surface / request context
- `T2_module_interaction`
  - 群组首页、群目录、组织树、管理页面 disabled 状态
- `T3_cross_service_integration`
  - CircleGroup 与 Conversation 绑定
  - 内容节点发布与父节点聚合
  - 群申请与审批
- `T4_user_journey`
  - 首页进入群组
  - 组织型主页加入与节点浏览
  - 圈子加入后申请公共群

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|---|---|---|---|
| `P1` | 冻结群组 / 群 / 角色 / 内容 / 搜索元数据模型 | `A3/A4/A6` | `T1_schema` |
| `P2` | 完成 codegen baseline 与兼容字段策略 | `A1/A2/A7/A8` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地双模板详情页与首页 IA | `A4/A5` | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 落地公共群 / 自建群 / 申请入群 / 资料与公告能力 | `A6` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P5` | 落地组织节点发布、父节点聚合与搜索统一群组结果 | `A5/A9` | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P6` | 完成观测、SLO、回滚与发布前验证 | `A7/A8/A9` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 若未来组织型群组需要更复杂的人员导入与身份认证，再把组织树与身份校验拆到独立 L2。
- 若群资料能力未来需要跨域复用，再把文件能力从 circle 域中抽离。
- 若搜索量级上升，再把统一搜索接口下沉到更稳定的聚合实现，但不改变用户词与结果类型。

## 存量带规划任务

- 现有 `activity-member-governance`、`circle-management-and-stats` 仍需在进入 `/dev` 前补齐与新群模型一致的设计。
- 具体事物主档与抓取、口碑模板和展示配置，由独立会话冻结，不在本设计中展开。
