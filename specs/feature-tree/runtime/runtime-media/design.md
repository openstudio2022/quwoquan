# L2 Design：运行时媒体 (`runtime-media`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“四环境媒体交付、公开 slice key、播放器终态与防羊群验收”需要 `group-avatar-server-precompose-and-unified-sync-contract`、`media-upload-and-storage` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：四环境媒体交付、公开 slice key、播放器终态与防羊群验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`group-avatar-server-precompose-and-unified-sync-contract`](./group-avatar-server-precompose-and-unified-sync-contract/spec.md)：**统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。
- [`media-upload-and-storage`](./media-upload-and-storage/spec.md)：上传完成持久化 `assetId`，重复 complete 返回同一 `MediaAsset` 并允许客户端继续发布。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 AssetRef 与 MediaAsset 统一媒体身份和派生资源
- 决策：`MediaUploadSession` 拥有上传 ticket、pending/completed/aborted 生命周期与完成重放；`MediaAsset` 拥有资产不变量、处理状态、访问策略和公开 slice。Session 完成时通过 MediaAsset 的 `CreationAppender` 在同一 Mongo transaction 追加资产、两类 receipt 与 outbox，失败必须整体回滚。
- 理由：四环境媒体交付、公开 slice key、播放器终态与防羊群验收。
- 被否决方案：Post 聚合复制上传会话、Session persistence 自行拼装 MediaAsset、App/页面保存 object key 或 CDN URL 作为发布命令，或 complete 后跨事务补写资产。
- 约束与影响：`MediaUploadSession/MediaAsset` 聚合只属于 content-service；runtime media 只提供对象存储端口、S3 适配与交付引用，不保留第二套 store/aggregate/mock。
- 对象存储 key 只在服务端 domain/infrastructure 内流转。App 上传命令结果只暴露继续上传所需的 signed `uploadUrl` 与恢复所需的 `assetId`，发布命令只提交 `mediaAssetIds`。
- Post 原子绑定后由服务端投影 path-versioned `publicSliceKey`，公开 URL query-free。私有 CAS/processed object 只走严格校验的短期签名 URL，两者不得共用 builder。
- App 只经统一 delivery resolver 将公开引用解析为 URI。
- 关联要求：`REQ-001`
- 影响 Story：[`group-avatar-server-precompose-and-unified-sync-contract`](./group-avatar-server-precompose-and-unified-sync-contract/spec.md)、[`media-upload-and-storage`](./media-upload-and-storage/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 上传 init/complete/abort、对象存储校验/晋升、处理状态变更、Post 绑定分别使用 canonical operation telemetry；receipt replay、失败阶段和处理延迟可区分观测。
- content-service 的健康检查与 SLO 必须覆盖 Mongo transaction、对象存储和处理 worker；任一权威依赖不可用时返回结构化失败，不得生成本地 URL 或伪成功资产。
- 发布和读取按 `assetId/publicSliceKey` 复验；alpha/beta/gamma/prod 仅由各环境 endpoint 与 CA 配置改变，业务身份和恢复语义保持一致。
