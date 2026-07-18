# runtime-media 设计方案

## 设计动因

`runtime-media` 的 PRD 已冻结两条主线：

1. 运行时媒体对象必须统一为 `AssetRef / MediaAsset / objectKey / CDN URL / version`
2. 群头像必须以服务端预合成为主链路，并通过统一 sync 模型传播

现有 `runtime/media` 代码更偏向“上传会话能力”，尚不足以支撑本次 Journey 对对象标识、群头像归属、同步 patch、OSS/COS 适配和客户端消费模型的要求。因此 `/design` 需要把“上传底座”升级为“媒体运行时基线”，并将群头像主链路纳入正式实施切片。

## 上游输入评审

| 输入 | 结论 |
|------|------|
| `runtime/runtime-media/spec.md` | 已冻结对象模型、归属边界、群头像主链路、同步主模型、灰度回滚要求 |
| `runtime/runtime-media/acceptance.yaml` | Journey 级验收 J1~J3 与 R1 已可直接映射到稳定切片 |
| `runtime/runtime-media/group-avatar-server-precompose-and-unified-sync-contract/spec.md` | 已冻结前 9 规则、sourceHash、统一 `avatarUrl` 与 sync patch 类型 |
| `chat-detail-avatar-display` | 页面头像展示行为已存在，需复用，不重做页面规则 |
| `group-member-roster-version-sync` | roster revision / 合并推送 / 定点拉取是群头像更新的上游合同 |
| `specs/runtime/media/*`、`specs/runtime/sync/*` | 作为横切基线设计文档，可直接成为本次设计的真相源输入 |

结论：

- `/design` 进入条件满足
- 本次设计不需要再讨论“是否云端合成”与“是否端侧拼图兜底”
- 需要重点收口 metadata/codegen、同步模型复用、群头像合成任务边界与客户端切换路径

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 当前差距 |
|------|------|--------|---------|
| 微信/企业微信公开 IM 资料 | realtime hint + 增量拉取 + gap fill；群头像弱实时更新策略 | 闭源私有协议与自研基础设施 | 当前群头像主链路仍未统一为单图服务端结果 |
| AWS S3/OSS/COS 对象存储实践 | 数据库存引用、对象存储存实体、CDN 对外域名 | 业务表固化临时 URL | 当前 runtime 代码未统一 object identity 规范 |
| 现有 `runtime/media` | UploadSession / MediaAsset / MediaStore 雏形 | 仅上传视角，不覆盖 sync/asset/ref | 当前需要扩展为 Journey 级统一媒体能力 |

## 方案对比

### 方案 A：各业务服务继续独立维护头像与媒体规则

`user-service`、`chat-service`、`content-service` 各自管理：

- 自己的对象路径
- 自己的 CDN URL
- 自己的 patch 协议
- 自己的头像更新传播

**优点**

- 就地改动，看似实现快

**缺点**

- 形成三套 object identity / URL / sync 规则
- 客户端需要分别适配头像、群头像、聊天媒体、内容媒体
- OSS/COS 切换成本高
- 极易与当前 runtime 横切定位冲突

**结论**

- 拒绝。违背本次 PRD 的“runtime 统一能力”目标。

### 方案 B：runtime 只统一上传，群头像逻辑留在 chat-service 自行扩展

`runtime/media` 只提供 `InitUpload / CompleteUpload / SignURL` 等基础能力；  
群头像生成、objectKey、sync patch 由 `chat-service` 自己实现。

**优点**

- 复用现有 runtime 代码路径
- 对上传会话改动较小

**缺点**

- “统一媒体运行时”只能覆盖上传，无法覆盖对象引用与 URL 规范
- 群头像与用户头像仍会形成两套协议
- 同步 patch 与 object identity 无法在 runtime 统一

**结论**

- 不选。只能解决一半问题。

### 方案 C：runtime 统一媒体对象模型与 vendor adapter，业务服务仅保留归属语义（选定）

运行时统一：

- `AssetRef / MediaAsset`
- `objectKey / CDN URL / version`
- OSS/COS adapter
- 群头像合成结果的落库与 URL 构建
- avatar/media 相关 patch envelope

业务服务保留：

- 用户头像归属
- 群头像归属
- top9 选择规则
- 何时触发重算

**优点**

- 符合 runtime 横切定位
- 保持 DDD 归属清晰
- 统一客户端消费口径
- 后续扩展内容媒体与聊天媒体成本最低

**缺点**

- 需要同步梳理 metadata/codegen、runtime、chat-service、user-service 和 app 消费路径

**结论**

- 选定方案。

## 选型决策

**选定方案：方案 C**

理由：

1. 能同时满足“业务归属分治”和“公共能力统一”
2. 不新增独立 `media-service`
3. 不把群头像业务规则错误下沉到 runtime
4. 可以直接沿用本次 `/prd` 已冻结的 runtime 文档基线

## 关键设计决策

### KD-1：统一对象引用模型

runtime 统一媒体对象主模型：

- `assetId`
- `provider`
- `bucket`
- `objectKey`
- `cdnDomain`
- `assetKind`
- `ownerType`
- `ownerId`
- `version`
- `variants`

业务表优先存：

- `assetId`
- `version`

不以临时 URL 作为主数据。

### KD-2：群头像归 `chat-service`，用户头像归 `user-service`

边界不变：

- `user-service` 维护 `avatarAssetId / avatarVersion`
- `chat-service` 维护 `groupAvatarAssetId / groupAvatarVersion / groupAvatarSourceHash`
- runtime 不承担“谁拥有这个对象”的业务决策

### KD-3：群头像服务端预合成采用异步任务

合成任务输入：

- `conversationId`
- `top9UserIdsInOrder`
- `top9AvatarVersions`
- `layoutVersion`

输出：

- 一个 `avatar_group` 类型的 `MediaAsset`

流程：

1. 业务层判断是否需要重算
2. runtime media 读取用户头像引用
3. 生成目标派生图
4. 上传对象存储并返回 `assetId/url/version`
5. `chat-service` 回写群头像字段

### KD-4：sourceHash 驱动去重

统一公式：

```text
hash(top9UserIdsInOrder + top9AvatarVersions + layoutVersion)
```

用途：

- 避免重复重算
- 允许任务天然幂等

### KD-5：公开交付 URI 由注入端点 + public slice key 构建

统一规则（环境无关 path/query，仅 authority 随配置变化）：

```text
{injectedHttpsMediaBase}/{publicSliceKey}?v={version}
```

双平面：

- 内部 CAS / `objectKey`：仅存储与处理链路使用，禁止跨服务 JSON 或 UI 透传
- 公开 `publicSliceKey` / `DeliveryReference.deliveryUri`：唯一对外交付引用

业务服务与 App 禁止：

- 自己拼 objectKey / CAS key
- 自己拼 OSS/COS URL、按环境名分支改写 host
- 在数据库主字段中保存签名 URL
- 播放器/图片组件接收未经验证的原始媒体引用

### KD-6：头像变化进入统一 sync patch

统一 patch 类型：

- `user.avatar.updated`
- `conversation.avatar.updated`

realtime 只推 hint，客户端再按 cursor 拉增量。

### KD-7：群头像失败保留上一版 `avatarUrl`

本次不做端侧拼图兜底。  
失败策略：

- 服务端重算失败：保留旧群头像；没有旧值时建群失败或重试至可用
- 客户端拉取失败：保持本地旧 `avatarUrl`，并记录诊断

### KD-8：复用既有 roster revision 与消息 sync 主模型

群头像更新不创建第二套本地版本号。

依赖：

- `group-member-roster-version-sync` 的 `membersRosterRevision / updatedAt`
- 既有 `realtime hint + sync pull` 路径

## metadata / codegen 方案

本次设计涉及 metadata/codegen，但在 `/design` 阶段先冻结方案，不在此阶段直接改契约。

### 计划中的 metadata 影响面

- `contracts/metadata/messages/conversation/fields.yaml`
  - 增 `groupAvatarAssetId`
  - 增 `groupAvatarVersion`
  - 增 `groupAvatarSourceHash`
  - 可选增 `groupAvatarStatus`
- `contracts/metadata/messages/conversation/projections/chat_inbox.yaml`
  - 主头像字段切向统一 `avatarUrl`
  - 旧群头像 URL / `avatarCompositeUrls` 字段从主链路移除
- `contracts/metadata/messages/conversation/events.yaml`
  - 增 `ConversationAvatarUpdated`
- `contracts/metadata/realtime/*` 或对应 sync 契约
  - 增 avatar patch 类型与 envelope 字段
- `contracts/metadata/user/user_profile/*`
  - 明确 `avatarVersion`

### G1 执行结果

已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：通过。  
说明当前仓库 baseline 可继续承接下一步 metadata 设计变更。

## 字段演进、迁移与回填

### 阶段 1：加字段，不切主链路

- 增加群头像新字段
- 移除旧群头像 URL 填充链路，并保留 `avatarCompositeUrls` 降级评估记录
- 生产端先写新字段

### 阶段 2：单轨切换（破坏性）

客户端只认：

1. `avatarUrl`

禁止旧字段双读、别名解码或「短期兼容」窗口；旧列表拼图语义一次性退出。

### 阶段 3：清理

- 评估移除或降级旧群头像 URL / `avatarCompositeUrls`

## 阶段 2 高标准准出补充

当前实现把阶段 2 准出拆成两层：

- **功能准出**：`avatarUrl` 已成为客户端唯一会话头像读取路径，群聊头像由服务端预合成并保证 active 会话非空。
- **高标准准出**：在功能准出之上，要求服务端群头像任务具备 Redis-backed 的可恢复/可重试/可去重能力；`runtime/sync` 对 patch 缺洞返回显式 `requiresResync`；客户端在 patch 应用时同步写入 `groupAvatarVersion` 并转入全量修复路径。

这意味着阶段 2 已不再允许仅以“非阻塞 goroutine + 最终靠运气补齐”作为准出说明。

## feature flag、观测、SLO 验证与回滚

### feature flag

- `chat.group_avatar_precompose_enabled`
- `runtime.avatar_patch_enabled`

### 关键观测

- `quwoquan_runtime_media_group_avatar_recompute_total`
- `quwoquan_runtime_media_group_avatar_recompute_duration_ms`
- `quwoquan_runtime_media_patch_fanout_total`
- `quwoquan_runtime_media_patch_fanout_recipient_total`
- `quwoquan_runtime_media_sync_pull_total`
- `quwoquan_runtime_media_sync_requires_resync_total`
- `chat-service` 通过 `/metrics/runtime-media` 暴露上述快照，供预发与灰度核查

### 回滚

1. 关闭 `runtime.avatar_patch_enabled`
2. 关闭 `chat.group_avatar_precompose_enabled`
3. 客户端保持旧 `avatarUrl` 或展示通用图片加载错误态

回滚要求：

- 不影响消息主链路
- 不影响用户头像主链路

## TDD / ATDD 策略

### local_contract

- metadata 字段与 patch schema 契约测试
- objectKey / URL builder contract
- sourceHash contract

### local_contract

- 群头像展示组件与默认图标降级
- sync patch handler

### api_integration

- 用户头像变更 -> 群头像重算 -> patch -> 客户端刷新
- 成员加入离开 -> 群头像重算 -> 客户端刷新

### user_acceptance

- 双设备 / 双账号会话列表群头像一致性
- 弱网下旧图保留 + 最终一致刷新

### user_acceptance 受控演练入口

若本轮仍不引入全自动真机链路，至少需要保留一套固定、可复演的预发准出步骤：

1. 准备两个账号/两台设备，同时登录同一群聊。
2. 在设备 A 执行建群、加人、退群，以及前 9 成员头像更新。
3. 在设备 B 弱网条件下观察：
   - 旧图是否保留而非闪成非法状态；
   - 收到 hint 后是否进入 cursor 拉取；
   - 遇到 gap 时是否转入 `requiresResync` 的全量修复。
4. 恢复正常网络后确认两端 `avatarUrl/groupAvatarVersion` 一致。

若该固定预发演练未执行，阶段 2 只能宣称达到“功能准出”，不能宣称“高标准准出全部完成”。

发布级收口产物统一冻结为：

- `specs/feature-tree/runtime/runtime-media/video-end-to-end-commercial-matrix.md`（视频商用端到端全矩阵；资源不齐时为 `GATE_BLOCK`）
- `specs/feature-tree/runtime/runtime-media/image-end-to-end-commercial-matrix.md`（内容图片商用端到端全矩阵；资源不齐时为 `GATE_BLOCK`）
- `specs/feature-tree/runtime/runtime-media/t4-release-rehearsal.md`
- `specs/feature-tree/runtime/runtime-media/observability-and-rollback.md`
- `specs/feature-tree/runtime/runtime-media/capacity-validation.md`
- `specs/feature-tree/runtime/runtime-media/automation-gates.md`

其中：

- `make gate-runtime-media` 用于本地高频回归；
- `make gate-runtime-media-full` 必须结合真实 `RUNTIME_MEDIA_T4_EVIDENCE` 一起执行，不能用空模板替代已执行证据。

## plan slice 与 三层测试 证据矩阵映射

| Slice | 目标 | local_contract | local_contract | api_integration | user_acceptance |
|------|------|----|----|----|----|
| M0 | metadata/codegen 设计基线 | ✓ | | | |
| M1 | runtime media 资产与 URL 规范 | ✓ | | ✓ | |
| M2 | chat-service 群头像字段与重算任务 | ✓ | | ✓ | |
| M3 | avatar patch + realtime hint + cursor pull | ✓ | ✓ | ✓ | |
| M4 | app 切主链路与默认图标降级 | | ✓ | ✓ | ✓ |
| M5 | 灰度、观测、回滚与清理 | ✓ | | ✓ | ✓ |

## 未来演进

1. 自定义群头像上传
2. 媒体审核与转码管线
3. 内容媒体全面接入统一资产模型
4. 更细粒度的多云/多 CDN 策略

## KD-9：内容 VOD 权威描述符与 storyboard

### 处理所有权与发布门

内容视频是 `content-service` 的业务对象；`runtime/media` 提供受控的对象交付、处理任务端口、
存储和可观测基础设施。上传或导入完成后，content-service 以
`{assetId, assetVersion, processorProfile}` 提交幂等处理任务，处理状态固定为
`processing -> ready | rejected`，不引入协议版本或兼容分支。

处理成功的唯一权威输出是 generated `VideoPlaybackDescriptor` 所需的数据：

- `assetId`、`assetVersion`、processing status、访问策略；
- `verifiedDurationMs`、宽高、codec/container；
- canonical video/cover `publicSliceKey`；
- 可选、版本绑定的 `previewTrack` manifest 与 track version。

Post publish、Feed、Post detail 与 WorkBrowser 只投影 `ready` asset 的 descriptor。上传端宣称的
时长、客户端 `VideoPlayerController` 时长和临时 URL 都不能作为权威字段；native duration
只供 session seek 边界和一次性数据质量比对。无 verified/native duration 时，App 禁用可拖动
时间轴，不伪造 `0:00` 或播放失败。

### storyboard 交付与缓存

storyboard 是处理阶段产出的受控派生资源，不是 UI 现场抽帧：

1. 处理器在 asset/version ready 后生成固定采样/尺寸 profile 的 manifest 和帧 slice；
2. manifest 通过 `MediaDeliveryReference` 交付，禁止 objectKey、上传 URL、任意 host 进入 App；
3. 缓存 key 固定为 asset/version/track/profile/access policy；私有资源按账号隔离，登出清除；
4. 控件拖动时只请求 target 对应帧；相邻预取、并发与内存有上限，切集、不可见或 generation
   变化立即取消；
5. 缺轨或请求失败仅降级为时间浮标，不得影响视频播放状态或显示重试 CTA。

### QoE、推荐信号与回滚

QoE 是 Ops 产品遥测，单独使用强类型 `video_playback_qoe` 事件，记录 ready、真实 TTFF（仅平台可
取得时）、rebuffer、seek、时长偏差和受限播放模式。事件不得带 postId、feedRequestId、tag、
ranking 归因或播放器异常栈，且不得进入 recommendation hot path。

推荐只接收 metadata 定义的 `effective_play`：服务端按真实累计播放、连续会话与 seek 排除校验后，
每播放会话/内容最多一次进入 `BehaviorSignal` 和兴趣更新。`play_progress` 不再将“跳至末尾”的
位置比误记为完整消费。

首期不新增端侧 `AppRemoteConfig` 播放门槛：有效播放阈值由服务端 policy 作为唯一准入权威。回滚
顺序是关闭 storyboard → 关闭新 controls → 回滚 image/config；已发布内容的 video/cover
canonical slice 和播放主链路必须持续可用。

SLS raw QoE 保留 3 天、去身份 hourly 聚合保留 90 天。看板和告警按低基数 playback mode 聚合
P50/P95 ready、TTFF、rebuffer incidents per ready 与 duration mismatch rate；告警必须包含
最小样本量和连续窗口抑制。任何 beta/gamma/prod 真机 readback 缺失时，商用矩阵继续为
`GATE_BLOCK`。
