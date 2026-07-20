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
- 默认群图标降级比例：从 user_acceptance 演练记录或正式监控面板统计
- hint-to-pull 延迟：从客户端埋点或预发抓样得到

## 阈值与动作
| 指标 | 阈值 | 查看方式 | 异常动作 |
|------|------|----------|----------|
| 群头像重算平均耗时 | `<= 400ms` | `/metrics/runtime-media` | 先缩小灰度；持续超阈值则关闭 `chat.group_avatar_precompose_enabled` |
| patch fanout 失败比 | `<= 1%` | `/metrics/runtime-media` + 日志 | 先观察是否可自动重试恢复；不可恢复则关闭 `runtime.avatar_patch_enabled` |
| hint-to-pull P95 | `<= 1500ms` | 客户端埋点 / user_acceptance 抓样 | 若服务端正常优先排查客户端节流、弱网与 WS 连接状态 |
| `requiresResync` 比例 | `<= 5%` | `/metrics/runtime-media` | 若突增，优先排查 patch TTL、客户端长离线与 Redis patch 丢失 |
| 默认群图标降级比例 | `<= 2%` | user_acceptance 演练 / 面板统计 | 若突增，优先关闭预合成灰度并保留默认群图标主路径 |

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
- 客户端类指标（默认群图标降级比例、hint-to-pull）当前仍依赖埋点或 user_acceptance 抓样，不应伪装成服务端已自动采集。

## 视频播放指标与阈值

视频 QoE 只允许低基数 `profile/platform/networkBucket/result` 维度；不得把 postId、assetId、
URL、object key、推荐 tag 或原始异常写入 metric label。首帧和 seek settle 只能由平台原生
事件确认，controller initialize 和 `seekTo` Future 不得代替。

| 指标 | 商用阈值 | 灰度动作 |
|------|----------|----------|
| 实际首帧成功率 | `>= 99.5%` | 未达标停止当前 rollout stage |
| 实际首帧 P95 | Wi-Fi `<= 1500ms`；蜂窝 `<= 2500ms` | 关闭 `adaptiveStreaming`，仍失败则关闭 `sharedTimeline` 并复测 P0 |
| release seek settle P95 | Wi-Fi `<= 1000ms`；蜂窝 `<= 2000ms` | 停止放量，回退 P0 delivery profile |
| seek failure rate | `< 0.5%` | 停止放量并检查 Range/keyframe/平台事件 |
| dropped-frame ratio | `< 1%`（以原生 `droppedFrames / processedVideoFrames` 计算） | 停止放量并用 Perfetto 关联 renderer、合成与 codec 证据 |
| audio underrun | `0` | 停止放量并检查 AudioTrack、主线程与解码供给 |
| rebuffer sessions / ready sessions | `< 2%` | 关闭 ABR 实验或回退 progressive MP4 |
| rebuffer time / effective playback time | `< 1%` | 缩小灰度并检查 CDN/编码 ladder |
| terminal playback failure rate | `< 0.5%` | 停止 rollout；保留封面与结构化恢复 |
| processing ready success rate | `>= 99.5%` | 暂停新 asset ready 发布；保留旧 ready 版本 |
| verified/native duration 超容差 | `0` | quarantine asset，禁止 App 覆盖权威值 |
| P1-A preview P95 | 内存 `<= 100ms`；磁盘 `<= 300ms`；网络 `<= 1000ms` | 仅关闭 `preview`，降级时间浮标 |

raw QoE 保留 3 天，去身份 hourly 聚合保留 90 天。样本不足或平台没有原生事件时只观察，不能据此
宣称 SLO 达标；原生不可用字段保持 null，不能写零值。scrub、buffering、后台、离屏和 position jump
不计入 effective_play。

### 发布 readback 合同

`VIDEO_PLAYBACK_QOE_READBACK_PATH` 必须指向 SLS 查询落盘的 JSON，而不是截图、空文件或手写
结论。报告固定包含：

- `source=aliyun_sls`、`eventType=video_playback_qoe`、`status=passed`；
- `rows` 至少覆盖 Android `wifi` 与 `cellular` 两个 bucket；`5g/4g/mobile` 在查询侧合并为
  `cellular`，不以品牌或型号分桶；
- 每个 bucket 的 `sampleCount >= 100`、`seekCount >= 100`，并提供
  `nativeFirstFrameSuccessRate`、`ttffP95Ms`、`seekSettleP95Ms`、`seekFailureRate`、
  `droppedFrames`、`processedVideoFrames`、`audioUnderrunCount`、`rebufferSessionRate`、
  `rebufferTimeRatio`、`terminalFailureRate` 与 `durationMismatchCount`；
- `seekEvidenceSource=native_settled`。controller 命令完成样本不得混入发布 readback。

full gate 按本节阈值逐行重算 dropped-frame ratio，并拒绝缺字段、负值、样本不足或超阈值。

Perfetto 证据由 `VIDEO_PLAYBACK_PERFETTO_TRACE_PATH` 与
`VIDEO_PLAYBACK_PERFETTO_SUMMARY_PATH` 成对提供。summary 必须声明 trace 实际
`sourceTraceSha256`，并给出 `mainThreadStallMaxMs`、`bufferOwnershipErrorCount`、
`sampledFrames`、`jankyFrames`。full gate 重新计算 trace hash，并要求
`mainThreadStallMaxMs < 1000`、ownership error 为 `0`、`jankyFrames / sampledFrames < 1%`；
`logcat` 过滤结果不能替代该证据。

## 视频灰度与回滚

三个功能开关必须独立：`sharedTimeline`、`preview`、`adaptiveStreaming`。P0
progressive MP4/Range 主链不能依赖 P1-A/P1-B。

1. `gray-initial`：只启用 `sharedTimeline`，验证真实首帧、seek settle、结构化失败和 QoE readback。
2. `carry-on`：必须使用同一 release/config hash，扩大流量并复核连续窗口 SLO；该阶段不可达时禁止进入 full。
3. `full`：仅在前两阶段非 dry-run 证据均 passed 后执行。
4. 回滚顺序：关闭 `adaptiveStreaming` → 关闭 `preview` → 关闭 `sharedTimeline`，随后复测
   progressive MP4/Range、封面、暂停和失败恢复。禁止恢复 UI 直控 controller 或 wire 双读。

任一阶段失败都必须停止后续 rollout，并保留截图/录屏、SLS readback、commit/config hash、
probe hash、asset/version 与回滚后复测证据。
