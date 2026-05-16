---
name: /infra-dev
id: infra-dev
category: Infrastructure
description: 基础设施 · 实施开发（按规划执行基础设施改进）
---

# infra-dev

## 命令目的
按 `/infra-plan` 产出的规划执行基础设施改进。确保每项改进有可回滚方案、性能基线、成本验证。

## 输入
- `--plan {planFile}` 指定规划文件
- `--items {INFRA-P0-001,INFRA-P1-002}` 指定实施条目
- `--scope {telemetry|storage|cache|messaging|cdn|network|observe|security}` 指定范围

## 实施原则

### 成本与体验平衡
- 每项改进必须标注成本变化（±$N/月）
- 不能为节省成本牺牲核心体验（首屏/起播/翻页流畅度）
- 不能为极致体验无限制增加成本（CDN 预热全量 vs 热内容）

### 存储无关
- 所有存储操作必须通过抽象层（`MediaStore`/`Repository[T]`/`BulkImportStore`）
- 新增适配器必须实现完整 interface，含健康检查和指标上报
- 切换存储只需修改配置，不改业务代码

### 零停机
- 数据迁移必须在线完成（双写→切读→停旧写→清理）
- 配置变更通过热更新或灰度发布
- 回滚必须在 5 分钟内完成

## 实施检查清单

### 埋点管线变更
```
☐ 端侧 BehaviorEvent schema 变更 → 同步 behavior_service.go
☐ 上报策略变更 → ContentBehaviorTracker flushInterval/maxBatchSize
☐ 离线队列策略变更 → RemoteBehaviorRepository Hive 配置
☐ 行为存储变更 → 新增 MongoDB TTL 索引 / S3 导出脚本
☐ 指标计算变更 → 预聚合集合 schema / Aggregation Pipeline
☐ 推荐回流变更 → HotPath/投影器/LearningBuffer 对齐
```

### 内容存储变更
```
☐ OSS 适配器实现 → runtime/media/s3_adapter.go（或等价）
☐ MediaStore interface 无变更（向后兼容）
☐ presign URL 安全性验证（过期时间/单次使用/IP 绑定）
☐ CDN 配置（域名/HTTPS/缓存策略/回源策略）
☐ 图片处理管线（缩略图/WebP/EXIF 清理）
☐ 视频处理管线（HLS 转码/封面截图/元数据提取）
☐ 存储生命周期策略（S3 Lifecycle Rule）
☐ 端侧 CdnImageUrlBuilder 创建与统一接入
```

### 缓存变更
```
☐ Redis 键空间变更 → 更新 redis_keyspace.yaml
☐ TTL 变更 → 代码与 YAML 同步
☐ 新增缓存 → 评估内存占用 + 淘汰策略
☐ SessionCache 替换 → LRU 库引入 + 配置化上限
☐ 端侧缓存策略 → MediaDownloadCache/SharedPreferences 清理
```

### 消息变更
```
☐ Pub/Sub → Streams 升级 → 消费者组配置 + ACK 逻辑
☐ 死信队列 → XCLAIM 超时配置 + 手动重放 admin API
☐ 事件 schema 变更 → MessageEnvelope 更新 + 投影器适配
```

### 网络变更
```
☐ 超时策略变更 → CloudHttpClient 分级配置
☐ 重试策略变更 → RetryHttpClient 实现 + 幂等判断
☐ 弱网策略变更 → 骨架屏/渐进加载/离线模式
☐ 服务端性能 → MongoDB explain + Redis slowlog + 推荐耗时分解
```

### 可观测性变更
```
☐ Prometheus 接入 → go.mod 依赖 + /metrics 端点 + 中间件
☐ OpenTelemetry 接入 → trace SDK + context 传播 + exporter
☐ Grafana dashboard → 模板文件 + 数据源配置
☐ 告警规则 → SLO/错误率/资源水位规则文件
```

## 验证门禁

```bash
# Go 编译
cd quwoquan_service && go build ./...

# 服务测试
cd quwoquan_service && go test ./... -v -count=1

# 端侧分析
cd quwoquan_app && dart analyze

# 配置一致性
diff <(yq '.redis' services/*/configs/default/config.yaml) <(cat contracts/metadata/_shared/redis_keyspace.yaml)

# 全量门禁
make gate
```

## 回滚检查清单
```
☐ 数据迁移：旧存储数据未删除，可切回
☐ 配置：旧配置在版本控制中，可还原
☐ 代码：feature flag 控制新路径，可关闭
☐ DNS/CDN：旧 CNAME 保留，可切回
☐ 监控：回滚后 5 分钟内核心指标恢复
```

## 与其他命令的关系

| 命令 | 角色 | 关系 |
|------|------|------|
| `/infra-audit` | 规范自检 | 发现问题 |
| `/infra-bench` | 成本性能对标 | 量化差距 |
| `/infra-plan` | 演进规划 | 制定方案 |
| `/infra-dev` | 实施开发 | 执行方案 |
| `/rec-dev` | 推荐实施 | 可能需要先完成 infra 依赖 |
