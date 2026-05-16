---
name: /infra-plan
id: infra-plan
category: Infrastructure
description: 基础设施 · 能力演进规划（基于自检或对标，生成分优先级基础设施改进计划）
---

# infra-plan

## 命令目的
基于 `/infra-audit` 和 `/infra-bench` 的发现，生成分优先级、可执行的基础设施改进计划。每个条目必须同时标注性能收益、成本影响和实施风险。

## 输入
- `--from {audit|bench|goal|all}` 规划来源（默认 all）
- `--priority {p0|p1|p2|p3|all}` 只输出指定优先级（默认 all）
- `--horizon {sprint|quarter|half}` 规划周期（默认 sprint）
- `--budget {low|medium|high}` 成本约束（默认 medium）

## 规划层级（7 层）

### L1. 埋点管线（采集→上报→存储→计算→回流）

#### L1.1 端侧采集加固
- `ContentBehaviorTracker` 缓冲策略优化：
  - 前台 → 后台切换时强制 flush
  - 进程被杀时 pending 事件落盘（AppLifecycleListener + Hive）
  - 离线队列按事件优先级排序（impression < dwell < like/share），删最旧时保留高优
- impression 去重跨 session（Hive 布隆过滤器，内存 Set 仅热路径）
- 事件压缩（gzip request body，减少上行带宽）

#### L1.2 上报可靠性
- HTTP 重试策略：指数退避（1s/2s/4s/8s）+ 最多 3 次 + jitter
- 批量上报支持 gzip Content-Encoding
- 按网络状态调整策略（WiFi 实时；蜂窝 batch 10s；离线入队）

#### L1.3 行为事件高性价比存储（核心选型）

**推荐分层方案**（综合成本与查询需求）：

```
行为事件流                         存储策略
───────────                        ────────
< 7d  → Redis HotPath             实时推荐回流（已实现）
< 30d → MongoDB TTL 集合           近期指标 + 快速查询
< 90d → S3 Parquet (按天分区)      历史分析 + 训练数据
> 90d → S3 Glacier/归档           合规保留 + 极低成本

指标计算：
  实时: Redis atomic + Go 进程内聚合（已实现）
  近期: MongoDB 聚合管道（aggregation pipeline）
  历史: S3 Parquet + DuckDB/Athena 查询
```

成本对比（Growth 阶段 150GB/月行为数据）：
| 方案 | 月成本 | 查询延迟 | 运维复杂度 |
|------|--------|----------|------------|
| 全存 MongoDB | ~$40 | ms级 | ★ |
| MongoDB 30d + S3 90d | ~$12 | ms/秒级 | ★★ |
| ClickHouse Cloud | ~$15 | ms级 | ★★ |
| S3 Parquet + Athena | ~$3 | 秒级 | ★★ |

**推荐**：startup/growth 阶段用 MongoDB TTL(30d) + S3 Parquet 归档；scale 阶段引入 ClickHouse。

#### L1.4 运营指标计算引擎
- 实时指标：保留当前 Go atomic 聚合 + Redis 辅助
- 近期指标：MongoDB Aggregation Pipeline（按天/按小时预聚合到 `rm_daily_metrics` 集合）
- 多维切分：surfaceId × experimentBucket × contentType × referralSource
- 可视化：product-ops-service 的 Ops Dashboard 消费预聚合集合
- AB 指标：按 experimentBucket 自动统计 CTR/深度消费率/互动率的 p-value

#### L1.5 推荐回流闭环
- HotPath 实时状态 → 已实现
- MongoDB 画像 → 投影器已实现，需补齐所有行为类型覆盖
- 训练数据：LearningEventBuffer → S3 Parquet（定期导出，非 MongoDB 永久存）
- 模型更新：训练完成 → model_registry → CascadeScorer 自动加载

### L2. 内容存储（高性价比 + 弹性 + 存储无关）

#### L2.1 对象存储 SDK 落地
- 替换 `oss_adapter.go` 的 URL 拼接 stub 为真实 S3 兼容 SDK
- 抽象层：`MediaStore` interface 保持不变，适配器支持 AWS S3 / 阿里云 OSS / CloudFlare R2 / MinIO
- 配置驱动切换：config.yaml 的 `media.provider` 字段
- 本地开发：MinIO 容器（docker-compose 已有 redis/mongo，加 minio）

#### L2.2 图片处理管线
- 上传后处理：
  - 原图存 S3（永久，低频访问层）
  - 自动生成缩略图（240p）+ 中图（720p）+ WebP 版本
  - EXIF 信息清理
  - 文件 hash 去重（相同图片不重复存储）
- CDN 分发：
  - 优先 WebP/AVIF（Accept 头判断浏览器支持）
  - CDN 查询参数变换（`?w=720&q=80&f=webp`）
  - 端侧按 devicePixelRatio 请求对应尺寸

#### L2.3 视频处理管线
- 上传后转码（异步任务）：
  - HLS 切片（240p/480p/720p/1080p）
  - 首帧截图作封面
  - 时长/分辨率元数据提取
- CDN 分发：
  - HLS 自适应码率
  - 预缓冲前 N 个 ts 片段
  - 起播优化（moov atom 前置）

#### L2.4 存储生命周期
```
创建 → 审核(可选) → 上线 → [N天无访问] → 冷存储 → [M天] → 归档
  ↓       ↓          ↓         ↓              ↓           ↓
S3标准  S3标准      CDN缓存   S3 IA        S3 Glacier   S3 Deep
$0.023  $0.023     CDN费用    $0.0125      $0.004       $0.00099

用户删除 → 软删除(30d可恢复) → 硬删除(S3 + CDN purge + DB 清理)
用户注销 → 72h 内关联内容全部进入删除流程
```

### L3. 缓存精细化

#### L3.1 Redis 缓存策略加固
- HotPath 热 key 防护：用户级 ZADD 限频（单用户 100次/分钟 cap）
- 大 key 治理：ZSET 限制成员数（如 tag 亲和 ZSET 最多 500 个 member）
- 缓存预热：服务启动时预加载热内容到 Redis
- 多级缓存：进程内 L1（100ms TTL）→ Redis L2（5min TTL）→ MongoDB L3

#### L3.2 SessionCache 升级
- 替换 map+RWMutex 为带 LRU 淘汰的实现（如 hashicorp/golang-lru）
- 支持内存水位监控（当前条目数 / 内存占用）
- 配置化上限（从 config.yaml 读取，非硬编码 10000）

#### L3.3 端侧缓存策略
- 图片缓存分级：缩略图（长 TTL）/ 中图（中 TTL）/ 原图（短 TTL 或不缓存）
- SharedPreferences 定期清理过期数据
- Hive box 大小监控 + 自动 compact

### L4. 消息可靠性升级

#### L4.1 关键事件路径升级
- 行为事件：Redis Pub/Sub → **Redis Streams**（消费者组 + ACK + 死信）
- 内容发布事件：确保 PostPublished → 推荐索引/搜索索引 的 at-least-once
- 用户关注事件：确保 UserFollowed → 社交召回源 的 at-least-once

#### L4.2 死信与补偿
- Redis Streams pending 超时自动重投（XCLAIM）
- 投影器失败时的重试策略
- 手动补偿工具（admin API 触发重放指定时间窗事件）

#### L4.3 远期：独立 MQ 评估
- DAU > 50 万时评估引入 NATS JetStream（轻量、高吞吐、持久化）
- 不建议直接上 Kafka（运维复杂度高，当前规模不需要）

### L5. CDN 与媒体分发优化

#### L5.1 CDN 图片处理
- 接入 CDN 图片处理功能（阿里云 OSS 图片处理 / CloudFlare Image Resizing）
- 端侧 `AppCachedNetworkImage` 统一添加尺寸/质量/格式参数
- 创建 `CdnImageUrlBuilder` 工具类：`buildUrl(raw, width, quality, format)`

#### L5.2 CDN 性能优化
- 预热：新内容发布后主动推送到 CDN 边缘
- 缓存策略：静态资源 1 年 / 图片 30 天 / 视频 7 天 / API 不缓存
- HTTPS/HTTP2 确保启用

### L6. 网络性能优化

#### L6.1 端侧网络加固
- 分级超时：
  ```
  行为上报:    5s
  推荐请求:    8s
  内容详情:    10s
  媒体上传:    60s
  媒体下载:    30s
  ```
- 通用重试中间件：`RetryHttpClient` wrapper（指数退避 + 幂等判断 + 最多 3 次）
- 请求优先级队列：推荐/内容 > 行为上报 > 同步 > 非关键

#### L6.2 弱网体验
- 骨架屏（skeleton loading）覆盖所有列表页
- 图片渐进式加载（先缩略图再清晰图）
- 离线模式（本地缓存内容可浏览，标记"已离线"）

#### L6.3 服务端性能
- MongoDB 查询分析（explain + 索引覆盖率）
- Redis 慢查询监控（slowlog）
- 推荐管道各阶段耗时分解与预算分配

### L7. 可观测性体系

#### L7.1 统一指标暴露
- 所有 Go 服务接入 Prometheus client_golang
- 标准 /metrics 端点 + 运行时 Go metrics + 业务 metrics
- Grafana dashboard 模板（per-service + overview）

#### L7.2 分布式追踪
- OpenTelemetry SDK 接入（Go + Dart）
- Trace context 传播（W3C TraceContext 标准）
- 采样策略：全量采 error / 1% 正常请求
- 后端：Jaeger / Tempo（成本友好）

#### L7.3 告警
- SLO 卡点（推荐 P99 < 200ms 违约率 > 0.1% 触发）
- 错误率告警（5xx > 1% 触发）
- 资源水位（Redis 内存 > 80%、MongoDB 连接池 > 80%）

## 输出格式

```
╔══════════════════════════════════════════════════╗
║     基础设施能力演进规划（/infra-plan）             ║
╠══════════════════════════════════════════════════╣
║ P0 阻塞修复（本 sprint 必须）                      ║
║   [INFRA-P0-001] 标题 — 影响/成本/工作量          ║
╠══════════════════════════════════════════════════╣
║ P1 高优改进（本 sprint 规划）                      ║
║   [INFRA-P1-001] 标题 — 影响/成本/工作量          ║
╠══════════════════════════════════════════════════╣
║ P2 中优改进（下季度规划）                          ║
║   [INFRA-P2-001] 标题                             ║
╠══════════════════════════════════════════════════╣
║ P3 远期能力（半年规划）                            ║
║   [INFRA-P3-001] 标题                             ║
╠══════════════════════════════════════════════════╣
║ 成本影响总结                                       ║
║   当前月估: $XXX → 优化后: $XXX（节省 XX%）         ║
╚══════════════════════════════════════════════════╝
```

每项含：标题 / 所属层（L1-L7） / 性能收益 / 成本影响 / 实施风险 / 依赖项 / 验收标准

## 与其他命令的关系

| 命令 | 角色 | 关系 |
|------|------|------|
| `/infra-audit` | 规范自检 | 发现问题 |
| `/infra-bench` | 成本性能对标 | 量化差距 |
| `/infra-plan` | 演进规划 | 制定方案 |
| `/infra-dev` | 实施开发 | 执行方案 |
