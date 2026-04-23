# group-avatar-server-precompose-and-unified-sync-contract 设计方案

## 设计动因

本场景是 `runtime-media` Journey 下最先落地的 L3：它把“统一媒体对象模型”压缩到一个可执行切口，即群头像服务端预合成和统一同步合同。目标不是一次性改造所有媒体能力，而是在不引入独立 media-service、不保留端侧拼图兜底的前提下，打通：

- 用户头像版本化
- 群头像服务端派生
- 对象引用与 URL 统一
- avatar patch + realtime hint + cursor pull

## 上游输入评审

| 输入 | 结论 |
|------|------|
| 本场景 `spec.md` | 已冻结 top9/sourceHash/默认群图标降级/统一 patch 类型 |
| Journey `runtime-media/spec.md` | 已冻结运行时边界、灰度回滚、覆盖矩阵 |
| `group-member-roster-version-sync` | 可复用 `membersRosterRevision/updatedAt` 作为上游变更判断基线 |
| `chat-detail-avatar-display` | 客户端页面展示逻辑已存在，可复用，不重做 UI 规则 |
| `quwoquan_service/specs/runtime/media/*` | 已明确 AssetRef、URL、头像策略与安全生命周期 |
| `quwoquan_service/specs/runtime/sync/*` | 已明确 UserSyncStream、patch、cursor、gap fill 基线 |

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 当前差距 |
|------|------|--------|---------|
| 微信/企业微信公开资料 | hint + 增量拉取 + 最终一致；群头像弱实时更新 | 闭源网关与自研存储实现 | 当前群头像尚未进入统一 sync patch |
| 通用服务端合成实践 | sourceHash 去重、服务端缓存结果图、对象存储 + CDN | 客户端会话列表实时多图渲染 | 当前 runtime 尚未承接群头像派生图主链路 |

## 方案对比

### 方案 A：客户端继续实时九宫格渲染

只优化图片缓存与 `Image.network` 组件，不改变主链路。

**优点**

- 服务端改动最小

**缺点**

- 会话列表首屏依然需要多图请求与解码
- 低端机与弱网表现不稳定
- 与“统一媒体对象模型”目标不一致

**结论**

- 拒绝。

### 方案 B：群头像服务端预合成，但同步仍走聊天私有链路

群头像图片由服务端生成，但更新通知仍由 `chat-service` 自己定义专用推送语义。

**优点**

- 群头像问题可被快速修复

**缺点**

- patch、cursor、realtime 语义与 runtime/sync 分叉
- 后续用户头像、内容媒体、更多头像变化无法复用

**结论**

- 不选。会制造第二套同步真相源。

### 方案 C：群头像服务端预合成 + runtime 媒体对象 + runtime sync patch（选定）

群头像结果图由 `chat-service` 触发、runtime media 存储与分发、runtime sync 统一传播变化。

**优点**

- 性能、边界、扩展性三者兼顾
- 客户端消费模型最简单
- 与当前 runtime 基线一致

**缺点**

- 需要跨 `user-service / chat-service / runtime / app` 多处协同

**结论**

- 选定。

## 选型决策

**选定方案：方案 C**

### 关键理由

1. 群头像主链路必须单图化，才能满足低端机和弱网要求
2. 统一 sync patch 才能避免后续头像变化再次分叉
3. runtime 应统一 object identity 与 URL，而不是只做上传

## 关键设计决策

### KD-1：群头像重算由 `chat-service` 触发，runtime 负责结果资产化

职责拆分：

- `chat-service`
  - 判断是否需要重算
  - 维护群头像字段
  - 发布 `ConversationAvatarUpdated`
- `runtime/media`
  - 获取用户头像对象引用
  - 合成目标群头像派生图
  - 上传对象存储并生成 CDN URL

### KD-2：群头像结果对象使用 `avatar_group` 资产类型

统一资产类型：

- 用户头像：`avatar_user`
- 群头像：`avatar_group`

这样客户端和服务端都可明确区分对象语义。

### KD-3：群头像字段设计

建议 metadata 增加：

- `groupAvatarAssetId`
- `groupAvatarVersion`
- `groupAvatarSourceHash`
- `groupAvatarStatus`（可选：`ready | generating | failed`）

### KD-4：重算触发策略

#### 必重算

- `ConversationCreated`
- `MemberJoined`
- `MemberLeft`

#### 异步重算

- 前 9 成员之一收到 `UserAvatarUpdated`

#### 跳过

- sourceHash 不变

### KD-5：客户端只消费群头像结果，不消费成员头像拼图主链路

客户端顺序：

1. `groupAvatarUrl`
2. 默认群图标

不再依赖：

- `avatarCompositeUrls` 做主链路拼图

### KD-6：avatar patch 类型进入统一 sync

新增或冻结 patch：

- `user.avatar.updated`
- `conversation.avatar.updated`

realtime 消息体只需要：

```json
{
  "type": "sync_hint",
  "latestSyncSeq": 12345
}
```

### KD-7：失败与回滚策略

- 生成失败：保留旧图；无旧图时返回默认群图标语义
- sync patch 异常：不影响消息主链路
- feature flag 关闭：群头像链路回退到默认群图标主路径

## metadata / codegen 方案

### 计划改动

1. `contracts/metadata/messages/conversation/fields.yaml`
2. `contracts/metadata/messages/conversation/projections/chat_inbox.yaml`
3. `contracts/metadata/messages/conversation/events.yaml`
4. 统一 sync / realtime 相关 metadata
5. 视需要补 `user_profile` 头像版本字段约束

### codegen 影响

- `quwoquan_service`
  - chat DTO / event / projection
- `quwoquan_app`
  - chat inbox DTO
  - realtime / sync 相关常量与 DTO

### G1 baseline

本次 `/design` 已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：通过。

## 字段演进、迁移与双读双写

### 阶段 1：写新字段，不切主消费

- 服务端开始写 `groupAvatar*` 字段
- 客户端暂不切换

### 阶段 2：客户端双读

- 优先读 `groupAvatarUrl`
- 缺失则显示默认群图标
- 不再使用成员头像列表做兜底拼图

### 阶段 3：单读

- 客户端主链路只读新字段
- 旧 `avatarCompositeUrls` 退为兼容字段

### 阶段 4：清理

- 评估删除旧字段或降为历史兼容字段

本次不要求双写两套群头像结果图；只要求字段兼容窗口。

## 阶段 2 高标准准出补充

本场景下的阶段 2 双读，除了“客户端优先读 `groupAvatarUrl`，失败回默认群图标”之外，还增加三项高标准要求：

1. 群头像重算不只是异步，而且要具备可恢复、可去重、可重试的任务语义。
2. `conversation.avatar.updated` fanout 不能因部分成员 append 失败而长期失配，需要显式补偿。
3. `runtime/sync` 拉取遇到 patch 缺洞时，必须返回显式 `requiresResync`，而不是静默跳过。

因此，阶段 2 现在既是“字段双读”阶段，也是“最终一致语义收口”阶段。

## feature flag、观测、SLO 验证与回滚

### feature flag

- `chat.group_avatar_precompose_enabled`
- `runtime.avatar_patch_enabled`

### 关键观测

- group avatar recompute success rate
- group avatar recompute latency
- default group icon fallback ratio
- avatar patch delivery count
- hint-to-pull latency

### 回滚

1. 关闭 patch 开关
2. 关闭群头像预合成开关
3. 客户端统一显示默认群图标

## TDD / ATDD 策略

### T1

- 字段与事件契约
- avatar patch envelope
- sourceHash contract

### T2

- app 群头像主路径展示
- 默认群图标降级
- patch handler 局部刷新

### T3

- 用户头像更新触发群头像异步重算
- 成员加入/离开触发重算与 patch
- inbox/detail 拉取后展示一致

### T4

- 双账号一致性演练
- 弱网场景最终一致

### T4 受控演练入口

至少保留以下可复演步骤作为阶段 2 的发布前入口检查：

1. 双账号同时加入同一群聊，确认初始 `groupAvatarUrl/groupAvatarVersion` 一致。
2. 在一端触发成员加入、成员退出、前 9 用户头像更新。
3. 在另一端模拟弱网或延迟网络，确认：
   - 会话列表仍显示旧图或默认群图标，而不是损坏 URL；
   - hint 到达后进入 patch 拉取；
   - patch 缺洞时不推进游标，而是走 `requiresResync` 全量修复。
4. 网络恢复后，两端群头像 URL 与 version 收敛一致。

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | T1 | T2 | T3 | T4 |
|------|------|----|----|----|----|
| G0 | metadata/chat inbox/avatar patch 基线 | ✓ | | | |
| G1 | runtime group avatar 资产化与 sourceHash | ✓ | | ✓ | |
| G2 | chat-service 触发重算与字段回写 | ✓ | | ✓ | |
| G3 | sync patch + realtime hint 接入 | ✓ | ✓ | ✓ | |
| G4 | app 切换主渲染链路与默认图标兜底 | | ✓ | ✓ | ✓ |

## 未来演进

1. 用户自定义群头像
2. 更多头像布局模板
3. 内容媒体统一对象模型的全面迁移
4. 群头像审核与治理链路
