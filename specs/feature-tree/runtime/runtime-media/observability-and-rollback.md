# runtime-media 观测与回滚手册

## 发布前必须回答的问题
1. 看什么指标？
2. 阈值是多少？
3. 异常时先灰度止血还是直接回滚？
4. 回滚后消息主链路是否仍保持可用？

## 指标口径
### 服务端快照
- `quwoquan_runtime_media_group_avatar_recompute_total`
- `quwoquan_runtime_media_group_avatar_recompute_duration_ms`
- `quwoquan_runtime_media_patch_fanout_total`
- `quwoquan_runtime_media_patch_fanout_batch_total`
- `quwoquan_runtime_media_patch_fanout_recipient_total`
- `quwoquan_runtime_media_group_avatar_task_recovery policy_failed_total`
- `quwoquan_runtime_media_group_avatar_task_terminal_failed_total`
- `quwoquan_runtime_media_group_avatar_task_queue_depth`
- `quwoquan_runtime_media_sync_append_total`
- `quwoquan_runtime_media_sync_append_batch_total`
- `quwoquan_runtime_media_sync_pull_total`
- `quwoquan_runtime_media_sync_pull_duration_ms`
- `quwoquan_runtime_media_sync_requires_resync_total`

### 发布级人工/外部观测项
- 默认群图标降级比例：从 T4 演练记录或正式监控面板统计
- hint-to-pull 延迟：从客户端埋点或预发抓样得到

## 阈值与动作
| 指标 | 阈值 | 查看方式 | 异常动作 |
|------|------|----------|----------|
| 群头像重算平均耗时 | `<= 400ms` | `/metrics/runtime-media` | 先缩小灰度；持续超阈值则关闭 `chat.group_avatar_precompose_enabled` |
| patch fanout 失败比 | `<= 1%` | `/metrics/runtime-media` + 日志 | 先观察是否可自动重试恢复；不可恢复则关闭 `runtime.avatar_patch_enabled` |
| hint-to-pull P95 | `<= 1500ms` | 客户端埋点 / T4 抓样 | 若服务端正常优先排查客户端节流、弱网与 WS 连接状态 |
| `requiresResync` 比例 | `<= 5%` | `/metrics/runtime-media` | 若突增，优先排查 patch TTL、客户端长离线与 Redis patch 丢失 |
| 默认群图标降级比例 | `<= 2%` | T4 演练 / 面板统计 | 若突增，优先关闭预合成灰度并保留默认群图标主路径 |

## 灰度策略
1. 先开 `chat.group_avatar_precompose_enabled`
2. 观察重算耗时、失败率、默认图标降级比例
3. 再开 `runtime.avatar_patch_enabled`
4. 观察 patch fanout、`requiresResync`、hint-to-pull

## 回滚入口
1. 关闭 `runtime.avatar_patch_enabled`
2. 若问题仍在，关闭 `chat.group_avatar_precompose_enabled`
3. 客户端退回默认群图标主路径

## 回滚核查清单
- 消息主链路未受阻
- 用户头像主链路未受阻
- 会话列表仍可正常打开与刷新
- `requiresResync` 未持续飙升
- 默认群图标兜底语义仍成立

## 与正式监控系统的接缝
- 当前 `/metrics/runtime-media` 是轻量 JSON 快照，适合作为预发核查与灰度观察入口。
- 正式发布前应把同名指标映射到统一监控系统；本文件保留指标名、阈值和动作作为单一口径。
- 客户端类指标（默认群图标降级比例、hint-to-pull）当前仍依赖埋点或 T4 抓样，不应伪装成服务端已自动采集。
