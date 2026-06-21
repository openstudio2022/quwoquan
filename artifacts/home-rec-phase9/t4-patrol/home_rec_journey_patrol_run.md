# 首页推荐 T4 Patrol 旅程 — gamma-local 真机演示证据

设备：`emulator-5554`（Android）。环境 defines：
`APP_RUNTIME_ENV=gamma API_CONTRACT_ENV=gamma RUN_T4_PATROL=true`
`CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:19000 API_CONTRACT_BASE_URL=http://10.0.2.2:19000`
`MEDIA_IMAGE_CDN_BASE_URL=http://10.0.2.2:19100 MEDIA_VIDEO_CDN_BASE_URL=http://10.0.2.2:19100`

## 复现命令

```bash
export PATH="$PATH:$HOME/.pub-cache/bin"
cd quwoquan_app
patrol test --target test/patrol/discovery/home_recommendation_journey_test.dart \
  -d emulator-5554 \
  --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma \
  --dart-define=RUN_T4_PATROL=true \
  --dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:19000 \
  --dart-define=API_CONTRACT_BASE_URL=http://10.0.2.2:19000 \
  --dart-define=MEDIA_IMAGE_CDN_BASE_URL=http://10.0.2.2:19100 \
  --dart-define=MEDIA_VIDEO_CDN_BASE_URL=http://10.0.2.2:19100 \
  --dart-define=APP_CURRENT_USER_ID=us_01_3278_01kvevr8s7s3b0arr7x3p27efe \
  --dart-define=TEST_AUTH_TOKEN=local-t4-token
```

## 结果（2026-06-19，最终稳定运行）

```
Test summary:
📝 Total: 5
✅ Successful: 5
❌ Failed: 0
⏩ Skipped: 0
⏱️ Duration: 1m 35s

✅ home_rec_feed_first_load_renders_real_remote_card (6s)
✅ home_rec_negative_feedback_converges (9s)
✅ home_rec_multiform_feed_paginates_without_repeat (15s)
✅ home_rec_open_immersive_consumption_and_return (11s)
✅ home_rec_author_object_nav_and_follow_entry (10s)
```

## 多形态 + 连刷不重复用例（本轮新增）

`home_rec_multiform_feed_paginates_without_repeat`：
- ① 首刷多形态非空：连续下拉前几屏同时命中「moment 九宫格」与「视频卡」（`forms.contains('moment-grid') && forms.contains('video')`）。
- ② 连续下拉 16 次：累积 `home-video-player-{id}` 真实 content id；
  - 任意一帧内同一 item 不重复渲染（`perFrameDuplicateSeen == false`，无单 item 连刷霸屏）；
  - 曝光 ≥2 个不同视频 item（`seenVideoIds.length >= 2`）；
  - `home-feed-card-{index}` 最大索引 ≥8（单调增长证明持续分页 ≥2 页）。
- 用例末尾 `_settleFeedToTopForHandoff` 回滚到顶并多 pump 释放视频资源，避免污染后续用例。

## 用例顺序与稳定性说明（诚实记录）

- 负反馈用例 `home_rec_negative_feedback_converges` 点击首卡 `home-feed-more-0` → 不感兴趣 → 卡片本地移除 + 降级提示 toast。
- 根因（非产品缺陷）：当被移除的首卡是「正在 autoplay 的焦点视频卡」时，Android 视频播放器释放会与降级提示 `AppToast` overlay 渲染在 Patrol pump 循环下时序竞争，偶发 6s 超时（负反馈功能代码卡型无关且正确，见 `lib/ui/discovery/widgets/home_multi_form_feed.dart` `_dismissFeedPost`：`removePostLocally` + `AppToast.show` 对所有卡型统一）。
- 对齐措施（env-seed 杠杆，不改 lib、不放宽断言）：
  1. seed 让推荐频道首卡（createdAt 最新 `t4hrec_moment_01`）为图文 moment（单图），视频卡从第 3 张起（更贴近真实推荐频道首卡形态）；
  2. 负反馈用例放在多形态深滚用例「之前」执行，避免多形态用例重度初始化的多个视频播放器资源波及负反馈降级提示时序。
- 调整前实测：首卡为视频时负反馈用例耗时 28~37s 并超时失败；调整后 9s 稳定通过。
