# runtime-media user_acceptance 预发演练包

## 目标
把 `runtime-media` 阶段 2 的“受控手工入口”收敛成可重复执行的预发演练步骤，并形成统一证据口径。

## 适用范围
- 群头像服务端预合成
- `conversation.avatar.updated` / `user.avatar.updated`
- `sync_hint` -> cursor pull -> `requiresResync`
- 默认群图标兜底
- 视频上传、公开 slice 交付、Feed/详情播放与失败恢复

## 前置条件
1. 两个账号、两台设备，同时登录同一套预发环境。
2. `chat.group_avatar_precompose_enabled = true`
3. `runtime.avatar_patch_enabled = true`
4. 可访问 `chat-service` 的 `/metrics/runtime-media`
5. 预发环境网络工具可模拟弱网 / 丢包 / 短暂断连

## 演练步骤
1. 设备 A 建群，并确认设备 B 会话列表出现该群。
2. 设备 A 依次执行：
   - 加人
   - 退群
   - 前 9 成员之一更换头像
3. 设备 B 在正常网络下确认：
   - 列表只展示统一 `avatarUrl`
   - 未出现端侧成员头像拼图主链路
4. 设备 B 切到弱网后重复第 2 步中的头像变更，确认：
   - 旧图保留，不闪成非法状态
   - 收到 hint 后进入 cursor 拉取
5. 在弱网期间人为制造 patch gap 或等待 patch 过期窗口命中，确认：
   - 客户端收到 `requiresResync = true`
   - 自动转入全量修复
6. 恢复正常网络后确认：
   - 两端 `avatarUrl/groupAvatarVersion` 一致
   - 无需手工下拉刷新即可最终一致

## 视频播放演练

### 前置条件

1. 当前 target 的 canonical video canary 已通过 HTTPS、Range `206` 与 `video/*` MIME preflight。
2. beta/gamma-local 使用已发布的受控视频；`prod-hosted` 仅使用 `gray-initial` 中声明的 release playback canary，禁止 fixture。
3. iOS Simulator 已经通过 target root CA preflight；证书安装失败必须在启动 Patrol 前中止。
4. App 由 topology 驱动的四个 `MEDIA_*_CDN_BASE_URL` 启动，报告记录实际 video authority。

### 演练步骤

1. 在内容创作端完成 InitUpload → PUT → CompleteUpload，并等待媒体资产 ready。
2. 以 `mediaAssetId` 绑定草稿并发布；服务端返回的 Feed/详情仅携带 canonical public slice key 或由它构建的 delivery reference，不得是 CAS key、upload URL 或临时签名 URL。
3. 在设备 A 打开 Feed，确认同源 `thumbnailUrl`/`coverUrl` 可见；点击后等待播放器进入 ready，记录首帧或播放 position 推进。
4. 在设备 B/第二账号打开同一 post，确认 authority、publicSliceKey 与版本同源，且可独立播放。
5. 制造一次可恢复网络失败，确认同源封面保留、用户只看到消费者主/副文案与有效“重试”；日志/埋点记录结构化 failure kind，但界面不出现证书、DNS、CDN 或环境名。
6. 制造一次内容不可用（4xx/404），确认展示“这条视频暂时无法观看”类文案，不提供无效重试；恢复资源后重新执行 preflight。
7. `prod-hosted gray-initial` 失败时停止 rollout，执行 release rollback/runbook 核查后才允许继续。

## 观测点
- `/metrics/runtime-media` 中的：
  - `quwoquan_runtime_media_group_avatar_recompute_total`
  - `quwoquan_runtime_media_group_avatar_recompute_duration_ms`
  - `quwoquan_runtime_media_patch_fanout_total`
  - `quwoquan_runtime_media_sync_pull_total`
  - `quwoquan_runtime_media_sync_requires_resync_total`
- 客户端侧：
  - 会话列表是否始终保持单图语义
  - persona / namespace 切换后是否串号
- 视频侧：
  - `media_load_state` 的 `mediaFailureKind`、`userScene`、`recovery.action` 与首帧/ready 延迟
  - target、rollout stage、publicSliceKey、video authority、Range/MIME 与播放器 ready 的同一证据链

## 通过标准
- 建群、加人、退群、头像变更均不阻塞主流程
- 弱网下旧图可保留，恢复后最终一致
- gap 明确走 `requiresResync`，不出现静默丢头像更新
- 双端最终 `avatarUrl/groupAvatarVersion` 一致
- 公开视频仅由 `mediaAssetId -> publicSliceKey -> MediaDeliveryReference` 链路交付
- Feed 与详情播放器均进入 ready，且未落入 `video-player-error`
- 失败时封面、消费者文案、恢复动作与结构化观测一致

## 失败判定
- 会话列表退回到成员头像拼图主路径
- 弱网下头像闪为空白、错图或非法状态
- hint 已到但 cursor pull 未触发
- gap 后未进入 `requiresResync`
- 恢复网络后双端版本仍不一致
- 视频 URL 落入 upload/CAS/另一媒体种类 authority，或 target 的 canonical video Range/MIME 失败
- 视频页面只出现节点而播放器未 ready，或 UI 暴露技术细节/万能“视频没加载出来”文案
- prod 灰度没有 release canary、分平面凭据或结构化证据却宣称播放通过

## 证据记录模板
- 环境：`<integration|pre-release>`
- 执行时间：`<UTC timestamp>`
- 执行人：`<name>`
- 设备组合：`<A/B model>`
- 弱网条件：`<profile>`
- 视频 canary：`<postId / mediaAssetId / publicSliceKey / version>`
- video authority：`<https origin>`
- 播放器证据：`<ready latency / screenshot / report path>`
- 指标快照：`<paste or screenshot path>`
- 结果：`pass|fail`
- 失败回滚动作：`<if any>`

## 发布声明边界
- 若本演练未执行，只能宣称“功能准出成立”。
- 若本演练执行失败，只能在修复并重演后宣称“高标准准出成立”。
