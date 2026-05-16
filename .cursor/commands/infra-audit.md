---
name: /infra-audit
id: infra-audit
category: Infrastructure
description: 基础设施 · 使用规范自检（埋点管线/存储/缓存/消息/CDN/网络/可观测/安全 8 维审计）
---

# infra-audit

## 命令目的
全面审计当前基础设施使用规范的落实情况，识别断点、误用、缺失和成本风险。覆盖埋点全链路、存储选型与生命周期、缓存策略、消息可靠性、CDN 与媒体、网络性能、可观测性、安全合规 8 个维度。

## 输入
- `--scope {all|telemetry|storage|cache|messaging|cdn|network|observe|security}` 审计范围（默认 all）
- `--env {dev|gamma|prod}` 环境维度（默认 all）
- `--depth {quick|standard|deep}` 审计深度（默认 standard）

## 审计维度（8 维）

### D1. 埋点采集→上报→存储→应用→回流（全链路）

#### 采集层（端侧）
扫描 `quwoquan_app/lib/` 中所有内容查看入口，验证：
- 是否接入 `ContentEngagementTracker` / `ContentBehaviorTracker`
- 批量策略是否合理（当前 5s/20 条，是否需要按场景差异化）
- impression 去重是否覆盖全场景（Set 存活于内存，进程重启后重复上报）
- 离线队列是否持久（Hive 200 条上限，删最旧是否丢关键事件）
- 应用前台/后台切换时是否 flush
- 事件 schema 是否完整（referralSource/engagementDepth/entityRefs/feedRequestId）

#### 上报层
- HTTP POST `/behaviors` 批量大小限制
- 失败重试策略（当前无指数退避，仅下次 flushPending）
- 网络切换时的补发时机
- 是否有数据压缩（gzip）

#### 存储层（云侧）
- 行为原始事件存储在哪里（当前：HotPath 只 Redis 实时状态，投影到 MongoDB 聚合画像）
- **原始事件流是否有持久化**（当前 gap：原始行为事件只经过 HotPath 和投影器，无独立原始事件存储）
- 存储成本评估（MongoDB 存全量行为 vs ClickHouse/S3 Parquet）
- 数据保留策略（行为数据保留多久：30d/90d/永久？冷数据归档？）

#### 应用层（指标计算）
- 运营指标计算引擎（当前：Go atomic 计数 → 手写 Prometheus text）
- 是否支持多维切分（按 surfaceId/实验桶/内容类型/来源）
- 实时 vs 离线指标的分工（实时用 Redis 聚合，离线用批处理）
- 是否有可视化大盘（Grafana/自建 Ops Dashboard）

#### 回流层（推荐系统）
- HotPath → Redis ZADD tag 权重是否实时生效
- 投影器 → MongoDB 用户画像是否覆盖所有行为类型
- LearningEventBuffer → 训练样本 join key 是否对齐
- 模型在线 serving 是否读取最新特征

### D2. 内容存储与生命周期

#### 文本内容
- 帖子 MongoDB 存储：文档大小分布、索引策略、分片策略
- 文章 Markdown 是否存在 MongoDB 16MB 限制风险
- 搜索能力：当前无全文搜索（无 ES/Meilisearch/Atlas Search 索引）

#### 媒体内容
- 图片：
  - 上传路径（端侧 presign → OSS PUT → complete → cdnUrl）
  - 存储位置（当前 oss_adapter 为 stub，无真实 SDK）
  - CDN 分发（当前无查询参数变换/尺寸裁剪/WebP 转换）
  - 多分辨率（缩略图/中图/原图）策略是否存在
  - EXIF 隐私信息是否清理
- 视频：
  - 上传与转码流程
  - 分辨率自适应（HLS/DASH 是否存在）
  - 首帧/封面图生成
  - 播放 CDN 策略（就近节点、预热）
- 音频（语音消息等）：
  - 格式标准化（Opus/AAC）
  - 存储与过期策略

#### 存储无关（切换能力）
- `runtime/media/MediaStore` 接口是否足以切换底层 OSS（S3/OSS/MinIO/R2）
- `runtime/repository/Repository[T]` 的 Mongo→PG 切换能力验证
- 切换时的数据迁移方案是否存在

#### 生命周期
- 创建→审核→上线→下架→归档→删除 的完整状态机
- 删除策略：软删除 vs 硬删除、保留期
- 归档策略：N 天后自动归档到冷存储
- 合规删除：用户注销时关联内容的处理

### D3. 缓存策略

#### Redis 缓存
- 键空间规范（`redis_keyspace.yaml` 与代码实际使用是否一致）
- TTL 设置是否合理（过短：频繁回源；过长：数据不一致）
- 热 key 防护（HotPath ZADD 高频写同一 user key）
- 大 key 检测（ZSET 成员数是否有上限）
- 缓存穿透/击穿/雪崩防护
- 多 scene 隔离（rec/general/realtime 是否正确路由）

#### 进程内缓存
- SessionCache（map + RWMutex）的内存上限（当前 10000 条）
- 淘汰策略（当前仅 TTL 过期，无 LRU）
- 与 Redis 的一致性（write-through 还是 write-behind）

#### 端侧缓存
- `MediaDownloadCache` 200MB LRU 是否合理
- `AppCachedNetworkImage` 磁盘缓存大小限制
- SharedPreferences 中的数据是否会无限增长
- Hive box 是否定期清理

### D4. 消息与事件可靠性

#### Redis Pub/Sub
- 订阅者不在线时事件丢失风险评估
- 是否需要升级到 Redis Streams 或独立 MQ
- 事件类型与通道命名规范

#### Redis Streams
- 可靠任务队列的 ACK 机制是否完善
- 消费者组配置（consumer group + pending 处理）
- 死信队列策略

#### 事件最终一致性
- MongoDB 事件存储 + 投影器的 at-least-once 保证
- Change Stream 断连后的恢复（resume token）
- 跨服务事件传播的延迟预期

#### 是否需要独立 MQ
- 当前 Redis Pub/Sub + Streams 的局限性评估
- 何时应引入 Kafka/NATS/RabbitMQ
- 成本与运维复杂度权衡

### D5. CDN 与媒体分发

#### CDN 配置
- 域名与 HTTPS 证书
- 缓存策略（Cache-Control 头、节点缓存时间）
- 回源策略（源站保护、回源鉴权）
- 多 CDN 切换能力

#### 图片优化
- 是否支持 CDN 侧图片处理（裁剪/压缩/WebP/AVIF）
- 响应式图片（srcset/不同密度）
- 懒加载策略
- 预加载策略（feed 中提前加载下 N 张）

#### 视频分发
- 是否支持切片分发（HLS/DASH）
- 自适应码率
- 预缓冲策略
- 起播优化（首包时间）

#### 成本控制
- CDN 流量费用预估模型
- 图片压缩带来的带宽节省
- 边缘缓存命中率目标

### D6. 网络与性能

#### 端侧网络
- HTTP 客户端超时配置（当前 12s 全局统一）
- 是否需要分级超时（行为上报短/媒体上传长/推荐请求中）
- 自动重试策略（当前无通用重试，仅业务层个别实现）
- 连接复用（HTTP/2 是否启用）
- 弱网降级策略

#### 服务间网络
- 内部 HTTP 调用超时（通过 RuntimeConfigProvider）
- 熔断/降级（runtime/governance 是否生效）
- 服务发现机制
- 跨 AZ/跨区域延迟

#### 性能断点排查
- 首屏加载耗时拆解（DNS + TLS + 首字节 + 内容传输 + 渲染）
- 推荐接口 P99 延迟（召回→排序→重排 各阶段）
- 图片/视频加载延迟
- 翻页/滑动帧率

### D7. 可观测性

#### 日志
- 结构化日志覆盖率（slog vs 裸 log.Printf）
- 日志级别规范
- 关联 ID 穿透率（TraceID/RequestID 是否每个服务都注入）
- 日志存储与检索（本地文件 vs 集中式如 ELK/Loki）
- 敏感信息脱敏

#### 指标
- Prometheus 指标暴露（当前仅 content-service 的 /metrics/rec/prometheus）
- 是否所有服务都有标准 /metrics 端点
- 关键业务指标是否有告警规则
- SLI/SLO 定义是否落地

#### 链路追踪
- 当前仅关联 ID（X-Trace-Id），非 OpenTelemetry 标准 span
- 跨服务调用链是否可追踪
- 采样策略
- 追踪数据存储与查询

### D8. 安全与合规

#### 认证与授权
- Token 机制与 JWT 签名（LiveKit HMAC-SHA256 自实现 vs 标准库）
- API Key 管理（是否有轮换机制）
- 服务间认证（是否 mTLS 或共享 secret）

#### 数据安全
- 传输加密（全链路 HTTPS）
- 存储加密（MongoDB/PG 静态加密）
- 敏感字段脱敏（拦截链是否覆盖所有出口）
- EXIF/地理位置信息清理

#### 合规
- 行为数据保留期限（个保法/GDPR 要求）
- 用户数据导出/删除能力
- 日志中是否含 PII（个人可识别信息）

## 输出格式

```
╔══════════════════════════════════════════════════╗
║     基础设施使用规范自检报告（/infra-audit）       ║
╠══════════════════════════════════════════════════╣
║ D1. 埋点全链路          ✓ PASS / ✗ N项断点      ║
║ D2. 内容存储与生命周期   ✓ PASS / ✗ N项缺失      ║
║ D3. 缓存策略            ✓ PASS / ✗ N项风险      ║
║ D4. 消息与事件可靠性     ✓ PASS / ✗ N项隐患      ║
║ D5. CDN与媒体分发        ✓ PASS / ✗ N项缺失      ║
║ D6. 网络与性能           ✓ PASS / ✗ N项断点      ║
║ D7. 可观测性            ✓ PASS / ✗ N项缺失      ║
║ D8. 安全与合规           ✓ PASS / ✗ N项风险      ║
╠══════════════════════════════════════════════════╣
║ 成本风险摘要                                      ║
║   存储月估: ...                                   ║
║   CDN月估:  ...                                   ║
║   缓存月估: ...                                   ║
║   优化空间: ...                                   ║
╠══════════════════════════════════════════════════╣
║ 性能断点摘要                                      ║
║   P0(阻塞): N 项                                  ║
║   P1(高):   N 项                                  ║
║   P2(中):   N 项                                  ║
║   P3(低):   N 项                                  ║
╚══════════════════════════════════════════════════╝
```

每个 ✗ 项附带：
- **位置**：文件路径 + 行号
- **问题**：具体描述
- **风险**：影响面（性能/成本/可靠性/安全）
- **方案**：修复建议 + 业界最佳实践
- **成本**：修复工作量预估

## 后续动作
- 自检完成后可通过 `/infra-plan` 生成修复规划
- 若指定 `--fix`，直接进入 `/infra-plan` 流程
