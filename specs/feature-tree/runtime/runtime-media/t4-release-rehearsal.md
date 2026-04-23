# runtime-media T4 预发演练包

## 目标
把 `runtime-media` 阶段 2 的“受控手工入口”收敛成可重复执行的预发演练步骤，并形成统一证据口径。

## 适用范围
- 群头像服务端预合成
- `conversation.avatar.updated` / `user.avatar.updated`
- `sync_hint` -> cursor pull -> `requiresResync`
- 默认群图标兜底

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
   - 列表优先展示 `groupAvatarUrl`
   - 未出现端侧成员头像拼图主链路
4. 设备 B 切到弱网后重复第 2 步中的头像变更，确认：
   - 旧图保留，不闪成非法状态
   - 收到 hint 后进入 cursor 拉取
5. 在弱网期间人为制造 patch gap 或等待 patch 过期窗口命中，确认：
   - 客户端收到 `requiresResync = true`
   - 自动转入全量修复
6. 恢复正常网络后确认：
   - 两端 `groupAvatarUrl/groupAvatarVersion` 一致
   - 无需手工下拉刷新即可最终一致

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

## 通过标准
- 建群、加人、退群、头像变更均不阻塞主流程
- 弱网下旧图可保留，恢复后最终一致
- gap 明确走 `requiresResync`，不出现静默丢头像更新
- 双端最终 `groupAvatarUrl/groupAvatarVersion` 一致

## 失败判定
- 会话列表退回到成员头像拼图主路径
- 弱网下头像闪为空白、错图或非法状态
- hint 已到但 cursor pull 未触发
- gap 后未进入 `requiresResync`
- 恢复网络后双端版本仍不一致

## 证据记录模板
- 环境：`<integration|pre-release>`
- 执行时间：`<UTC timestamp>`
- 执行人：`<name>`
- 设备组合：`<A/B model>`
- 弱网条件：`<profile>`
- 指标快照：`<paste or screenshot path>`
- 结果：`pass|fail`
- 失败回滚动作：`<if any>`

## 发布声明边界
- 若本演练未执行，只能宣称“功能准出成立”。
- 若本演练执行失败，只能在修复并重演后宣称“高标准准出成立”。
