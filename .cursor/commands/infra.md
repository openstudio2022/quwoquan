---
name: /infra
id: infra
category: Infrastructure
description: 基础设施 · 统一入口（默认先自检再规划，覆盖存储/缓存/消息/CDN/网络/可观测全栈）
---

# infra

## 命令目的
基础设施能力的统一入口。默认模式下先自检当前全栈基础设施使用规范的落实情况，再生成分优先级修复规划。覆盖埋点管线、内容存储、性能体验、可观测性、安全合规全链路。

## 输入
- `--mode {inspect|plan|dev|bench|full}` 运行模式（默认 inspect）
  - `inspect`：运行 `/infra-audit` 自检
  - `plan`：基于自检或用户目标生成规划
  - `dev`：直接进入实施
  - `bench`：运行 `/infra-bench` 成本与性能对标
  - `full`：完整流程（audit → bench → plan）
- `--scope {all|telemetry|storage|cache|messaging|cdn|network|observe|security}` 聚焦范围
- `--env {dev|gamma|prod}` 环境维度（默认 all）

## 默认行为（`/infra` 无参数）

```
Step 1: 自检（/infra-audit --scope all）
    ↓
Step 2: 成本与性能对标快照（/infra-bench 核心维度）
    ↓
Step 3: 规划（/infra-plan --from audit）
    ↓
Step 4: 输出结论与下一步建议
```

## 专家角色定义

执行本命令时，AI 必须同时扮演四重专家角色：

### 云基础设施运维专家
关注领域：
- 数据库连接池配置与健康（MongoDB MaxPoolSize/PG MaxConns/Redis PoolSize）
- 缓存命中率、淘汰策略、热 key 防护
- 消息可靠性（Redis Pub/Sub vs Streams vs 独立 MQ 的取舍）
- CDN 命中率、回源率、证书与域名
- 网络拓扑（服务间延迟、跨 AZ 部署、DNS 解析）
- 容量水位与弹性扩缩

关键审视点：
- MongoDB 未设 MaxPoolSize 时默认 100，是否匹配服务 QPS
- Redis scene_pool 的 PoolSize/MinIdleConns 与并发请求是否匹配
- HotPath 高频写 Redis ZADD/HSET 是否会成为热 key
- CDN 签名 TTL 是否合理（过短导致重签频繁，过长有安全风险）

### 基础设施规划专家
关注领域：
- 存储选型的成本效益比（MongoDB Atlas 阶梯 vs 自建、Redis 内存 vs SSD 混合）
- 存储无关抽象层的完备性（Repository pattern 是否真正可切换）
- 数据生命周期管理（冷热分层、TTL、归档、清理）
- 容灾与备份策略
- 基础设施即代码（IaC）成熟度

关键审视点：
- 行为事件用 MongoDB 存储成本是否过高（vs ClickHouse/S3+Athena）
- 媒体存储 OSS adapter 是否为真实 SDK（当前为 URL 拼接 stub）
- 是否有冷数据自动归档（如 30 天前行为 → S3/归档存储）
- 多环境配置是否一致（dev/gamma/prod 拓扑映射）

### 系统应用架构师
关注领域：
- 端到端数据流（行为采集→上报→存储→计算→回流→推荐）是否有断点
- 存储抽象层（Repository/Store/Adapter）是否覆盖所有业务场景
- 服务间通信模式的一致性（HTTP 内部调用超时/重试/熔断/降级）
- 内容生命周期的完整性（创建→存储→CDN→缓存→搜索→推荐→归档→删除）
- 跨服务事件的最终一致性保证

关键审视点：
- Redis Pub/Sub 无持久化，订阅者不在线时事件丢失
- BulkImportService 是否幂等（重复 import 不会产生重复数据）
- ContentBehaviorTracker 内存缓冲在进程被杀时丢失
- 端侧 Hive 离线队列 200 上限删最旧，是否会丢重要事件

### 系统应用产品总监
关注领域：
- 用户体验端的性能感知（首屏加载、图片加载、视频起播、翻页流畅度）
- 成本与体验的平衡（不能为省成本牺牲核心体验，也不能为极致体验无限制烧钱）
- 数据驱动能力（运营指标的实时性、可分析性、可追溯性）
- 隐私合规（GDPR/个保法对行为数据的保留期限要求）

关键审视点：
- 图片无 CDN 查询参数裁剪/压缩，移动端加载原图浪费带宽
- 12s HTTP 超时对弱网场景是否过长（用户等不及）
- 行为数据保留期限是否有明确策略（法规要求）
- 推荐效果好但用户不知道为什么看到这些内容（可解释性/透明度）

## 全栈数据流图

```
┌─ 端侧 ──────────────────────────────────────────────────────┐
│                                                              │
│  ContentEngagementTracker ──┬─→ BehaviorRepository           │
│  ContentBehaviorTracker ────┘   ├─ Remote: POST /behaviors   │
│  PageAccessLogUtil ─────────→   │  (batch, 5s/20条)          │
│  AnalyticsService ──────────→   ├─ Hive: offline queue       │
│  AppExceptionTelemetry ─────→   │  (max 200, 删最旧)         │
│                                 └─ flushPending on reconnect │
│                                                              │
│  MediaUploadManager ────→ presignURL → PUT → complete → CDN  │
│  AppCachedNetworkImage ←── cdnUrl (无查询参数变换)             │
│  MediaDownloadCache ────── 200MB LRU temp dir                │
│  CloudHttpClient ────────── 12s timeout, 无自动重试           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ 云侧 ──────────────────────────────────────────────────────┐
│                                                              │
│  behavior_service ──→ HotPath (Redis ZADD/HSET)             │
│       │                  └─ tag 加权(depth×source)           │
│       │                                                      │
│       ├──→ RecommendFeatureProjector ──→ MongoDB             │
│       │     (rm_recommend_feature)       (用户画像)           │
│       │                                                      │
│       ├──→ DiscoveryFeedProjector ──→ MongoDB                │
│       │     (rm_discovery_feed)       (候选特征)              │
│       │                                                      │
│       └──→ LearningEventBuffer ──→ MongoDB                   │
│             (rm_learning_events)   (训练样本)                 │
│                                                              │
│  Redis (多 scene)                                            │
│  ├─ rec: HotPath + SessionCache                              │
│  ├─ general: cache + seq + dedup                             │
│  ├─ realtime: sync + Pub/Sub events                          │
│  └─ Streams: reliable task queue                             │
│                                                              │
│  MongoDB (多服务)                                             │
│  ├─ content-service: posts + 推荐读模型                       │
│  ├─ chat-service: conversations                              │
│  ├─ circle-service: circles + files                          │
│  ├─ assistant-service: events + skills                       │
│  └─ product-ops-service: telemetry (可选)                    │
│                                                              │
│  PostgreSQL                                                   │
│  ├─ user-service: users + auth + follow                      │
│  └─ content-service: reports (pg report_dsn)                 │
│                                                              │
│  Elasticsearch (可选)                                         │
│  └─ product-ops-service: event mirror                        │
│                                                              │
│  OSS/CDN (runtime/media)                                     │
│  ├─ oss_adapter: presign(stub) + CDN URL + 熔断              │
│  ├─ cdn.go: HMAC 签名                                        │
│  └─ 无真实 S3/OSS SDK                                        │
│                                                              │
│  可观测性                                                     │
│  ├─ 日志: slog + ProcessTraceLogger + IOAccessLogger         │
│  ├─ 指标: atomic 计数 + 手写 Prometheus text                  │
│  ├─ 追踪: 关联 ID (X-Trace-Id) 非 OpenTelemetry             │
│  └─ HTTP 中间件: observability middleware                     │
└──────────────────────────────────────────────────────────────┘
```

## 命令家族

```
/infra (统一入口)
├── /infra-audit   (使用规范自检)
├── /infra-bench   (成本性能对标)
├── /infra-plan    (基础设施规划)
└── /infra-dev     (实施开发)
```
