# L1 圈子社区 v2 — 整体架构设计

## 设计动因

spec.md v2 将圈子从「浏览型列表页」升级为「同频社区空间」，新增三大能力域（体验重构、协作工具、端侧平台化），涉及 4 个云侧域（circle、chat、content、recommendation）和端侧全链路重构。需要在 L1 层面做出跨切架构决策，确保 6 个 L2 在统一架构下协同演进。

## 上游输入评审

| 上游 | 状态 | 阻断项 |
|------|------|--------|
| spec.md v2 | ✅ 已冻结 | 无 |
| acceptance.yaml（9 条） | ✅ 已定义 | 无 |
| circle metadata（fields/service/events/errors/storage） | ✅ 已有基线 | 需扩展 CircleFile、CircleSection 实体 |
| chat metadata（Conversation.circleId, type=circle） | ✅ 已就绪 | 无阻断，event-driven 集成 |
| content metadata（Post.circleIds, PostCircleDistribution） | ✅ 已就绪 | 无阻断，复用 content 域 |
| recommendation（circle_discovery scenario） | ✅ 已就绪 | 推理模型可占位，降级到 RuleScorer |
| domain_taxonomy | ❌ 不存在 | **本次新建**，为 D-1 关键产出 |

## 对标输入分析

| 对标对象 | 借鉴点 | 不借鉴点 | 适用边界 |
|----------|--------|----------|----------|
| Discord Server | 频道 + 角色 + 文件共享 + 机器人集成 | 语音频道、Stage Channel | 圈子定位为兴趣社区而非实时通讯 |
| 小红书圈子 | 兴趣分类 + 瀑布流 + 发布入口 | 电商导购 | 内容创作为核心，不做交易 |
| 豆瓣小组 | 话题讨论 + 成员治理 + 文件帖 | 纯文字论坛形态 | 需要多媒体+结构化板块 |
| Notion Workspace | 可配置板块 + 共享空间 | 在线文档协作 | 仅借鉴板块可配置理念，不做在线编辑 |

## 方案对比

### D-1：领域标签统一方案

#### 方案 A：集中式 domain_taxonomy.yaml（推荐）

在 `contracts/metadata/_shared/domain_taxonomy.yaml` 定义全局领域标签体系，所有消费方（圈子频道、助理路由、推荐场景、内容标签）共同引用。codegen 生成 Go/Dart 枚举。

**优点**：单一真相、编译期安全、跨域一致
**缺点**：变更需全量 codegen
**适用条件**：需要跨域对齐的场景（本次需求）

#### 方案 B：映射层方案

保持助理 `domain_routing_catalog.json` 和圈子频道配置各自独立，增加映射表对齐。

**优点**：最小改动、各自演进
**缺点**：双源易漂移、运行时映射增加复杂度
**适用条件**：仅需弱对齐的场景

**选型决策**：**方案 A**。metadata-first 原则要求唯一真相；领域标签是跨域基础设施，必须集中管理。

---

### D-2：圈子主页板块化方案

#### 方案 A：服务端驱动 UI

Circle 实体新增 `sections` 字段（`List<CircleSection>`），API 返回板块配置，客户端根据配置动态渲染。

**优点**：完全可配置、无需客户端更新
**缺点**：API 复杂、冷启动延迟、离线体验差
**适用条件**：板块类型频繁变化的场景

#### 方案 B：客户端板块注册 + 服务端开关（推荐）

客户端内置所有板块组件（作品区、群聊、存储、互动等），服务端仅返回轻量配置（板块顺序 + 可见性）。每个板块独立加载数据，单板块失败不影响整体。

**优点**：启动快、渐进加载、离线可用、板块隔离
**缺点**：新板块类型需客户端发版
**适用条件**：板块类型相对稳定、移动端优先

**选型决策**：**方案 B**。移动端性能优先；板块类型（作品/群聊/存储/互动）在 v2 范围内已确定，不需频繁变化。

---

### D-3：存储空间架构

#### 方案 A：圈子域内 CircleFile 实体（推荐）

在 circle 域新增 `CircleFile` 实体，元数据存 MongoDB（文件名、大小、路径、权限），文件本体存 S3 对象存储。circle-service 提供存储 CRUD API。

**优点**：域内聚合、简单直接、权限复用圈子角色模型
**缺点**：圈子域职责增大
**适用条件**：v1 快速交付，存储仅服务圈子场景

#### 方案 B：独立 file-service

新建 file-service 域，提供通用文件管理能力，circle 通过 fileId 引用。

**优点**：跨域复用（未来用户个人网盘等）
**缺点**：额外服务开销、权限模型需独立设计
**适用条件**：多域共享文件管理的场景

**选型决策**：**方案 A**。v1 存储仅服务圈子，域内实现最简。未来演进：当其他域需要文件管理时，抽取为 file-service。

---

### D-4：群聊集成方式

#### 方案 A：事件驱动松耦合（推荐）

`CircleMemberJoined` / `CircleMemberLeft` 事件 → `event_store` → `chat-service` 消费，自动创建/管理群聊成员。已有 events.yaml 中 chat-service 为 consumer。

**优点**：松耦合、容错好、已有事件基础设施
**缺点**：最终一致性（加入后可能延迟几百 ms 才进群）
**适用条件**：不要求即时一致的场景

#### 方案 B：同步 RPC 调用

circle-service 直接调用 chat-service API 管理群聊成员。

**优点**：即时一致
**缺点**：紧耦合、chat-service 故障会阻塞 circle 操作
**适用条件**：要求强一致的场景

**选型决策**：**方案 A**。events.yaml 已定义 chat-service 为消费者，松耦合符合 DDD 原则。延迟在 P99 < 1s 可接受。

---

### D-5：发布区内容模型

#### 方案 A：复用 content 域 + circleId 过滤（推荐）

圈子 feed = `GET /v1/content/posts?circleId={circleId}`，利用已有 `PostCircleDistribution` 表。circle-service 的 `GetCircleFeed` 代理到 content-service 或直接查投影。

**优点**：零新实体、复用内容基础设施、创作流程统一
**缺点**：跨域查询，circle-service 依赖 content
**适用条件**：内容模型已完善的场景（当前已有 PostCircleDistribution）

#### 方案 B：圈子域内物化投影

从 content 事件异步投影到 circle 域的 `circle_feed` 读模型。

**优点**：查询独立、可优化圈子特定排序
**缺点**：数据冗余、同步复杂度
**适用条件**：圈子 feed 需要复杂个性化排序

**选型决策**：**方案 A**，因 `PostCircleDistribution` 已存在且有索引。未来演进：当圈子 feed 需圈子特定排序（如圈主置顶）时，启用方案 B（投影 YAML 已在 projections/circle_feed.yaml 预留）。

---

## 关键设计决策汇总

| 编号 | 决策 | 方案 | 状态 |
|------|------|------|------|
| D-1 | 领域标签统一 | 集中式 `_shared/domain_taxonomy.yaml` | 已定 |
| D-2 | 圈子主页板块化 | 客户端注册 + 服务端开关 | 已定 |
| D-3 | 存储空间 | 圈子域内 CircleFile | 已定 |
| D-4 | 群聊集成 | 事件驱动松耦合 | 已定 |
| D-5 | 发布区内容 | 复用 content 域 + circleId | 已定 |
| D-6 | 端侧迁移 | features/ → ui/circle/，三层 Repository | 已定 |

## 整体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         端侧 (Flutter/Dart)                          │
│                                                                      │
│  lib/ui/circle/                                                      │
│  ├── pages/                                                          │
│  │   ├── circles_page.dart          ← 频道 Tab + 推荐 + 瀑布流       │
│  │   ├── circle_detail_page.dart    ← 板块式主页                     │
│  │   └── circle_stats_page.dart     ← 统计页                        │
│  ├── providers/                                                      │
│  │   └── circle_providers.dart      ← Riverpod 状态管理              │
│  ├── widgets/                                                        │
│  │   ├── circle_card.dart                                            │
│  │   ├── channel_panel.dart                                          │
│  │   ├── section_works.dart         ← 作品板块                       │
│  │   ├── section_chat.dart          ← 群聊板块                       │
│  │   ├── section_storage.dart       ← 存储板块                       │
│  │   └── section_interaction.dart   ← 互动板块                       │
│  └── models/                                                         │
│      └── circle_view_models.dart    ← 类型化 ViewModel               │
│                                                                      │
│  lib/cloud/services/circle/                                          │
│  ├── circle_repository.dart         ← Abstract + Mock + Remote       │
│  └── mock/circle_mock_data.dart                                      │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                         云侧 (Go/MongoDB/Redis)                      │
│                                                                      │
│  ┌──────────────┐    event     ┌──────────────┐                      │
│  │ circle-svc   │────────────▶│ chat-service  │                      │
│  │              │  Joined/Left │              │                      │
│  │ Circle       │              │ Conversation  │                      │
│  │ CircleMember │              │ (type=circle) │                      │
│  │ CircleFile   │              └──────────────┘                      │
│  │ CircleSection│                                                    │
│  └──────┬───────┘                                                    │
│         │ query                                                      │
│         ▼                                                            │
│  ┌──────────────┐                 ┌────────────────┐                 │
│  │content-svc   │                 │ rec-model-svc  │                 │
│  │ Post         │ ◀─── feed ────▶│ circle_discovery│                 │
│  │ Distribution │                 │ scenario       │                 │
│  └──────────────┘                 └────────────────┘                 │
│                                                                      │
│  contracts/metadata/_shared/domain_taxonomy.yaml ← 领域标签唯一真相   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## 跨域数据流

```
用户加入圈子 ─▶ circle-service.JoinCircle()
                 ├── 写入 CircleMember
                 ├── 更新 Circle.memberCount
                 └── 发布 CircleMemberJoined 事件
                      ├── chat-service: 将用户加入 circle 群聊
                      ├── recommendation-engine: 更新 social_signal
                      └── notification-service: 通知圈主

用户在圈内发帖 ─▶ content-service.CreatePost(circleIds=[circleId])
                 ├── 写入 Post + PostCircleDistribution
                 ├── 发布 PostCreated 事件
                 │    ├── circle-service: 更新 Circle.postCount
                 │    └── recommendation-engine: 更新 hot_path_signal
                 └── 端侧 circle feed 自动刷新

圈子 feed 查询 ─▶ circle-service.GetCircleFeed(circleId, cursor)
                 └── 代理查询 content 域 PostCircleDistribution → Post

存储空间上传 ─▶ circle-service.UploadFile(circleId, file)
                 ├── 验证权限（CircleMember.role）
                 ├── 验证容量（Circle.storageUsedBytes vs quota）
                 ├── 上传到 S3 → 获取 objectKey
                 ├── 写入 CircleFile 元数据
                 └── 发布 CircleFileUploaded 事件
```

## Story 与测试层映射

| L2 | L4 Story | T1 单元 | T2 集成 | T3 契约 | T4 端到端 |
|----|----------|---------|---------|---------|-----------|
| circle-client-platform | features-to-ui-migration | import 检查 | Provider 切换 | Repository 契约 | 路由导航 |
| circle-client-platform | circle-repository-contract | Mock 返回 | Remote HTTP | service.yaml 对齐 | — |
| circle-client-platform | circle-semantic-cleanup | verify_dart_semantic.py | — | — | — |
| circle-experience-redesign | domain-taxonomy-contract | 枚举完整性 | 圈子+助理引用 | taxonomy codegen | — |
| circle-experience-redesign | resonance-matching | 排序算法 | 推荐 API 集成 | — | 推荐相关度 |
| circle-experience-redesign | homepage-layout | 板块渲染 | 配置加载 | — | 板块独立降级 |
| circle-collaboration-tools | storage-crud | CRUD 单元 | S3 mock | service.yaml | 上传下载 |
| circle-collaboration-tools | chat-integration | 事件发布 | chat-svc 消费 | — | 加入→进群 |
| circle-collaboration-tools | publishing-contract | feed 查询 | content 代理 | — | 发帖→圈子feed |

## 未来演进

| 演进点 | 触发条件 | 预期方案 |
|--------|----------|----------|
| 存储空间 → 独立 file-service | 其他域需要文件管理 | 抽取 CircleFile 为 File，file-service 统一管理 |
| 发布区 → 物化投影 | 圈子 feed 需圈子特定排序（置顶/加权） | 启用 projections/circle_feed.yaml |
| 多群聊 | 大型圈子需要子频道 | Circle 支持多 conversationId，UI 增加频道列表 |
| 实时协作 | 存储空间需在线编辑 | 引入 CRDT/OT 协议，对接在线文档服务 |
| 付费圈子 | 商业化需求 | 新增 CircleSubscription 实体，对接支付域 |

## 遗留带规划任务

- 现有 3 个 L2（activity-member-governance、in-circle-recommendation-loop、circle-management-and-stats）的 design.md 仍为占位模板，在各自进入 /dev 阶段时补充具体设计。
- `projections/circle_feed.yaml` 已预留，暂不启用。
