# infra-capacity · design · base

覆盖容量、成本、迁移与可靠性的设计期可判定条目。
**具体架构结论必须现场对照代码验证**（原因见 `ROLE.md` 末尾）。

## PRE 准入

- [MUST] 本次改动的成本影响方向已标注（增加 / 持平 / 降低）及其量级依据
  check: 无成本影响说明，判失败
- [MUST] 回滚路径存在且不依赖重新构建；旧配置仍在版本控制中
  check: 缺回滚路径，或回滚需重新发版，判失败
- [SHOULD] 回滚可在 5 分钟内完成
- [SHOULD] 不为省成本牺牲核心体验（首屏、起播、翻页），也不为极致体验无限增成本

## DURING 执行中：D1-D8 判定面

逐项判定，命中风险即报 finding：

- [SHOULD] **D1 埋点链路**：采集批量策略、去重是否跨进程重启有效、离线队列上限
  是否会丢关键事件、前后台切换是否 flush、事件 schema 是否完整
- [SHOULD] **D2 内容存储与生命周期**：创建→审核→上线→下架→归档→删除状态机是否完整；
  软删除与保留期、合规删除是否定义
- [SHOULD] **D3 缓存**：键空间与 `redis_keyspace.yaml` 是否一致；TTL、热 key、大 key、
  穿透/击穿/雪崩防护、多 scene 隔离
- [SHOULD] **D4 消息可靠性**：Pub/Sub 无持久化的丢事件风险是否可接受；
  是否需要 Streams（ACK + 消费者组 + pending + 死信）
- [SHOULD] **D5 CDN 与媒体分发**：Cache-Control、回源、图片变换与格式、
  视频自适应码率、边缘命中率目标
- [SHOULD] **D6 网络与性能**：超时是否分级而非一刀切、重试是否幂等、
  弱网降级、熔断与服务发现
- [SHOULD] **D7 可观测性**：结构化日志、TraceID 穿透、`/metrics` 覆盖、SLI/SLO 落地
- [SHOULD] **D8 安全与合规**：全链路 HTTPS、静态加密、敏感字段与 EXIF 清理、
  数据保留期限、Token 与密钥轮换
- [MUST NOT] 存储访问绕过对象专属端口回到通用 `Repository[T]`
  gate: make verify-domain-governance
- [MUST NOT] 数据迁移采用停机切换；必须在线（双写 → 切读 → 停旧写 → 清理）
  check: 迁移方案缺任一阶段，或要求停服窗口，判失败

## POST 自检

- [MUST] 环境拓扑一致
  gate: make verify-env-topology
- [MUST] 领域治理通过
  gate: make verify-domain-governance
- [SHOULD] 性能预算未超
  gate: make verify-performance-budgets
- [SHOULD] 可靠任务拓扑成立
  gate: make verify-reliable-task-topology

## HANDOFF 交接

- 产出：成本影响结论、回滚步骤、D1-D8 中命中风险的条目
- 未决项去向：缺实测数据的容量判断转 `OPEN-###`，写明需要哪次压测补齐
- 下一步：`dev`
- 证据链：上述 gate 输出
