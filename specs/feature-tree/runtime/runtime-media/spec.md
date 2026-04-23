# L2 Journey：runtime-media

## 节点定位

- `L1_capability`: `runtime`
- `L2_journey`: `runtime-media`

## 背景与动机

当前媒体能力与头像同步能力分散在多个域中：

- `content-service` 已有上传初始化与完成接口，但以内容场景为中心，未形成统一资产模型
- `chat-service` 会话列表与详情页已依赖头像与多媒体展示，但群头像仍缺少稳定的服务端预合成主链路
- `user-service` 管理用户资料，却未冻结用户头像版本、群头像更新传播与统一对象标识之间的合同

与此同时，已有运行时代码和本次补充的 `specs/runtime/media/*`、`specs/runtime/sync/*` 已经明确：媒体与同步都应沉淀为横切基础能力，而不应让各业务服务分别维护第二套对象标识、URL 规则、CDN 拼接和补偿逻辑。

本 Journey 的目的，是在 `/dev` 前冻结一条完整的运行时主线：

1. 媒体资产统一用 `AssetRef / MediaAsset` 表达
2. 用户头像与群头像有清晰业务归属
3. 群头像采用服务端预合成，失败只回退默认群图标
4. 群成员变化、头像变化与消息变化通过统一同步模型传播

## 目标用户

- **服务开发者**：`user-service`、`chat-service`、`content-service` 开发者，需要共享一致的媒体对象模型、URL 规范和同步协议
- **端侧开发者**：需要消费稳定的头像/媒体 URL 与统一 sync patch，而不是拼接 object key 或做端侧群头像九宫格
- **最终用户**：间接受益，表现为群头像更快、更稳定，头像与会话状态在多端与弱网下更一致

## 功能范围

### In Scope

1. **统一媒体对象模型**：冻结 `AssetRef / MediaAsset`、`assetKind / ownerType / ownerId / version / variants`
2. **统一 URL 与 objectKey 规范**：冻结 CDN URL、版本参数、objectKey 命名规则与 vendor adapter 责任边界
3. **用户头像归属**：用户头像业务归 `user-service`，运行时只承载上传/存储/URL 构建能力
4. **群头像归属**：群头像业务归 `chat-service`，由服务端预合成并通过 runtime media 存储与分发
5. **群头像更新触发合同**：前 9 成员加入/离开必重算，前 9 成员头像变更异步重算
6. **群头像失败策略**：客户端不做端侧拼图兜底，失败时显示默认群图标
7. **统一同步基线接口**：runtime media 相关变化必须能进入统一 `UserSyncStream`，支持 realtime hint + cursor 增量拉取
8. **云厂商适配**：冻结 OSS / COS 适配接口、bucket/prefix 组织与 CDN 域名对外暴露规则
9. **观测与治理基线**：冻结上传、重算、同步、签名 URL、回源失败等关键指标与降级原则

### Out of Scope

- 用户自定义上传群头像的产品能力
- 媒体审核、转码、智能裁剪等独立媒体处理管线
- WebRTC 实时音视频流本身
- 全量历史媒体数据清洗与搬迁
- 所有内容媒体能力的一次性重构；本次只冻结统一基线和群头像主场景

## 约束

### 技术约束

- `runtime/media` 只作为共享模块存在，不独立部署
- 业务服务不得直接拼接 OSS/COS URL
- `contracts/metadata/*` 仍是字段、事件、path、operation 的唯一真相源
- 客户端不得根据成员头像列表自行推导群头像

### 业务约束

- 用户头像归 `user-service`
- 群头像归 `chat-service`
- 内容图片/视频归 `content-service`
- runtime 只负责底层能力，不吞业务语义

### 发布约束

- 群头像链路必须支持灰度切换
- 必须保留默认群图标降级能力
- 必须具备回滚到“服务端不返回 groupAvatarUrl、客户端仅显示默认图标”的最小回滚路径

### 发布级证据包

- T4 演练步骤与发布声明边界：`specs/feature-tree/runtime/runtime-media/t4-release-rehearsal.md`
- 指标、阈值、灰度与回滚核查：`specs/feature-tree/runtime/runtime-media/observability-and-rollback.md`
- 容量假设、边界与非目标：`specs/feature-tree/runtime/runtime-media/capacity-validation.md`
- 自动化/半自动化门禁：`specs/feature-tree/runtime/runtime-media/automation-gates.md`

## 对标输入与吸收结论

| 对标 | 借鉴 | 不借鉴 | 适用边界 |
|------|------|--------|---------|
| 微信/企业微信公开 IM 资料 | 长连接 hint + 增量拉取 + sequence/gap fill；群头像稳定规则、弱实时更新 | 闭源私有协议与自研基础设施 | 借鉴同步模型与产品策略，不复制实现细节 |
| 通用 IM/社交媒体对象存储实践 | 对象存储 + CDN + 业务表存引用而非二进制 | 业务表直接固化临时 URL | 适用于头像、图片、视频等所有媒体对象 |
| 现有 runtime/media | UploadSession / MediaAsset / MediaStore 雏形 | 仅上传视角，不覆盖对象标识与同步合同 | 作为本次 Journey 的代码起点 |

吸收结论：

- 统一媒体运行时必须覆盖对象引用与 URL 规范，不止是“上传”
- 群头像应走服务端预合成，客户端不做端侧拼图兜底
- 同步应采用“实时通知 + 增量拉取 + gap fill”主模型

## 角色分工

- `user-service`：用户头像主数据、版本递增、用户头像更新事件
- `chat-service`：群头像归属、前 9 成员规则、群头像重算与相关 patch 生产
- `content-service`：内容图片/视频绑定与内容侧媒体语义
- `runtime`：媒体对象模型、URL 规范、vendor adapter、同步 envelope 与治理能力
- App：消费统一 `avatarUrl/groupAvatarUrl/sync patch`，不推导底层存储路径

## 既有 Story 覆盖矩阵

| 既有节点 | 关系 | 本次处理 |
|---------|------|---------|
| `runtime/runtime-media/media-upload-and-storage--upload-session-and-cdn-delivery` | 已覆盖基础上传会话与 CDN 分发 | 继续复用，作为本 Journey 的媒体底座前置能力 |
| `chat-conversation/chat-experience-optimization/chat-detail-avatar-display` | 已覆盖对话页头像显示与用户信息缓存 | 保留页面行为；头像来源与群头像主链路改由本 Journey 统一冻结 |
| `chat-conversation/group-creation-member-management/group-member-roster-version-sync` | 已冻结成员 revision、合并推送与 roster 拉取语义 | 作为群头像重算与同步的上游合同输入 |
| `chat-conversation/list-detail-message-delivery/realtime-push-and-offline-sync--websocket-push-gap-fill-policy` | 已覆盖聊天消息推拉混合同步 | 继续作为消息同步前置，不单独复制协议 |

优先级：

1. 以本 Journey 为媒体与头像主规范
2. 不覆盖既有聊天页面展示细节，只覆盖其媒体来源与同步来源
3. roster/version/sync 已有合同优先复用，不重复定义第二套版本机制

## 数据生命周期合同

- **用户头像**：长期保留当前有效版本，旧版本延迟清理；数据库主存 `avatarAssetId + avatarVersion`
- **群头像**：由服务端预合成生成派生资源；数据库主存 `groupAvatarAssetId + groupAvatarVersion + groupAvatarSourceHash`
- **聊天图片/视频/语音/文件**：沿 runtime media 统一上传与对象存储引用模型，后续按业务保留期管理
- **默认群图标**：作为客户端静态兜底资源，不进入媒体资产主链路

## 小趣 / 权限 / 分享边界

- 本 Journey 不通过 runtime 垂类特判或字符串硬编码兼容任何助手特例
- 小趣、分享卡片、可见性策略后续若依赖头像/媒体，只能通过 `asset/metadata/config` 读取统一运行时结果
- 群头像更新只影响已授权可见该会话的用户，不新增越权可见性

## 非功能目标

### SLO / KPI

- 群头像主链路为单图加载，不允许列表首屏依赖 4~9 张成员头像实时渲染
- 在线设备收到群头像相关同步 hint 后，P95 在 500ms 内可发起定点拉取
- 群头像重算必须异步执行，不阻塞主请求链路
- 上传初始化、上传完成、签名 URL 构建、群头像重算、sync patch 生成必须具备统一监控
- `chat-service` 必须通过 runtime/config 提供群头像 CDN 域名，禁止在业务代码中保留 mock 常量
- 运行时必须暴露最小观测快照，至少覆盖：
  - `quwoquan_runtime_media_group_avatar_recompute_total`
  - `quwoquan_runtime_media_group_avatar_recompute_duration_ms`
  - `quwoquan_runtime_media_patch_fanout_total`
  - `quwoquan_runtime_media_sync_pull_total`
  - `quwoquan_runtime_media_sync_requires_resync_total`

### 弱网 / 并发 / 容量

- 弱网下允许 avatar patch 延迟可见，但最终一致必须由 gap fill 或显式 `requiresResync` 补偿保障
- 多个成员短时间连续变更时，群头像重算应允许去重/合并
- object storage 与 CDN 厂商切换必须通过 adapter 层屏蔽
- 群头像任务调度不得依赖全量任务扫描作为主消费路径，必须使用 ready queue / score queue 等可扩展结构
- sync pull 读取必须支持批量化，避免长离线追赶时按 seq 单 key RTT 线性放大
- 客户端会话缓存必须按 persona / namespace 隔离，不能通过全局 `cache.clear()` 作为主切换策略
- 当前容量验证仅冻结在 `capacity-validation.md` 中列出的热点群、大 fanout、长离线追赶、高频 hint 与大本地列表场景；不夸大为已完成企业级极限压测

## 迁移、灰度与回滚要求

### 阶段 2 准出口径

阶段 2 在本 Journey 内分成两层口径：

- **功能准出**：`chat-service` 已稳定产出 `groupAvatarUrl/groupAvatarVersion`，App 主链路优先消费 `groupAvatarUrl`，缺失或失败时统一显示默认群图标。
- **高标准准出**：在功能准出基础上，群头像重算必须具备可恢复、可去重、可重试的任务模型；avatar sync 必须具备显式 gap / `requiresResync` 语义；并提供至少一套受控的 T4 发布演练入口。

### 迁移

- 第一阶段：冻结 runtime 规范与群头像新字段
- 第二阶段：`chat-service` 产出 `groupAvatarUrl/groupAvatarVersion`
- 第三阶段：App 切换到消费 `groupAvatarUrl`

### 灰度

- 使用 feature flag 控制新群头像主链路是否返回
- 允许按用户批次灰度新同步 patch 类型

### 回滚

- 若群头像预合成失败率异常，回滚到“客户端统一显示默认群图标”
- 若新 sync patch 异常，回滚到既有消息 sync，不阻塞消息主链路

## 验收重点

1. 统一对象模型、URL 规范、vendor adapter 与归属边界在 spec 与 acceptance 中冻结
2. 群头像服务端预合成策略、更新触发与失败策略冻结
3. 用户头像/群头像变化进入统一 sync 模型，而不是散落成独立推送规则
4. 对聊天头像显示、roster version sync、消息推拉模型的覆盖矩阵明确，不制造第二套真相源
