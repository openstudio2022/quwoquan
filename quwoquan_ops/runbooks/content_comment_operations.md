# Content Comment 商用运行手册

## 适用范围

本手册覆盖 `content.comment.*` 请求、Comment outbox/checkpoint、hotScore 与计数投影、
Report→Comment 治理以及创建时 IP 属地快照。Comment aggregate、Report aggregate 和
ContentReaction 各自保持独立提交边界；排障不得直接改业务文档或跳过 checkpoint。

## 商用目标

- `ListComments`、`ListCommentReplies`、个人评论查询：P95 ≤ 400ms。
- Comment command：P95 ≤ 500ms。
- operation availability ≥ 99.9%（5xx 比率 ≤ 0.1%）。
- 每条 Comment relay health 为 1，最近成功 scan 不超过 30 秒。
- IP 属地有效查询 `not_found` 比率 ≤ 20%，离线库年龄 < 45 天。
- `CreateComment` 429 比率连续 15 分钟 > 20% 时必须区分攻击、误配置和真实用户阻塞。

Grafana 入口：`qwq-l2-content-objects`。告警真相源：
`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`。

## 统一诊断顺序

```bash
python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope full
python3 quwoquan_ops/cli/stackctl.py inspect --target gamma-local --kind all
python3 quwoquan_ops/cli/stackctl.py doctor --target gamma-local
```

生产只允许把 target 改为 `prod-hosted` 后执行只读 health/inspect/doctor。任何 rollout、
restart、回滚版本选择或破坏性修复都必须走受保护发布审批，不得在排障中临时执行。

## 请求延迟或 5xx

1. 在 dashboard 按 `operation`、`contract_metric`、HTTP status 确认影响面。
2. 通过 `requestId` / `traceId` 下钻；日志不得包含评论正文、原始 IP 或认证信息。
3. 读取对应 RuntimeFailure code，区分 Mongo 事务、Redis 关系投影、MediaAsset reader
   与 Report 协作失败；禁止把依赖失败降级为成功或 Mock。
4. `ListComments` / `ListCommentReplies` 重点确认 hot/latest keyset 命中复合索引、无
   `COLLSCAN` 和阻塞 `SORT`，并确认附件、reaction、relationship、block 均为批量读取。
5. `CreateComment` 重点确认 author rate-lock、aggregate 与 outbox 在同一事务完成。

恢复后执行：

```bash
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile release
```

## 429 频控异常

1. 核对 `content.comment.CreateComment` 总请求与 429 比率，按 persona/device 风险标签聚合，
   不记录或导出正文。
2. 确认 burst/daily 配置分别为 30 秒 5 条、24 小时 200 条，且 burst 小于 daily。
3. 核对 command key 重放是否命中原 receipt；幂等重放不得重复扣减额度。
4. 若为攻击，使用既有网关治理策略；若为真实用户阻塞，先形成产品验收与压测证据，再改
   typed config。禁止删 rate-lock、扩大 allowlist 或在 App 伪造提交成功。

## Comment relay / checkpoint 不健康

受监控的 health check 至少包括：

- `content_comment_outbox_events`
- `content_comment_lifecycle_stream`
- `content_comment_post_count`
- `content_comment_profile_interaction`
- `content_comment_hot_score`
- `content_comment_recommend_signal`
- `report_comment_moderation`

处理步骤：

1. 用 stackctl inspect 查看 content-service 日志、metrics 和 config，定位具体 consumer。
2. 核对最后成功 checkpoint、待处理 outbox event identity 和最近错误。
3. 修复 poison event 的生产者/消费者契约后，依赖相同 event identity 幂等重放。
4. 禁止手工推进 checkpoint、删除 outbox、改 hotScore/commentCount 或跳过失败事件。
5. Post 删除链路需同时确认 `CommentsTombstoned` 已产生、CommentCountProjector 已重算为
   0；Report 链路需确认 `ReportResolved(delete_content)` 最终产生
   `CommentModerated`。

本地白名单恢复仅在 doctor 明确建议时使用：

```bash
python3 quwoquan_ops/cli/stackctl.py repair --target gamma-local --fix restart-stack
python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope full
```

## IP 属地告警

1. 检查 provider：alpha 只能为 deterministic；beta/gamma/prod 只能为 ip2region。
2. 校验 IPv4/IPv6 xdb、固定 SHA256、Apache-2.0 许可证与 `data_version`。
3. 数据年龄 > 35 天开始升级；到 45 天前必须完成新镜像、双栈样本与 gamma 回归。
4. `error/unavailable` 必须修复库或装配并保持 fail-fast；`not_found` 只落空串，不臆造属地。
5. 原始 IP 不得进入 Comment、日志、指标 label、trace attribute 或告警通知。

## 准出验证

```bash
make -C quwoquan_service verify-metadata
make -C quwoquan_service verify-production-wiring-purity
cd quwoquan_service && go test ./services/content-service/internal/content/comment/application ./services/content-service/internal/content/post/infrastructure/iplocation ./services/content-service/tests/local_contract/content/post ./services/notification-service/tests/local_contract/notification_delivery/notification
cd quwoquan_app && flutter test --concurrency=1 test/local_contract/service/content_service/content/comment
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile release
```

只有同一 commit/ContractGraph hash 的 local_contract、真实 API、Gamma 设备 Journey、metrics
readback 与告警规则均通过后，才可作为 prod rollout 输入。
