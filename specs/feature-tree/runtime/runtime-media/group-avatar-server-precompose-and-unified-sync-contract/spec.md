# L3 Scenario：group-avatar-server-precompose-and-unified-sync-contract

## 节点定位

- `L1_capability`: `runtime`
- `L2_journey`: `runtime-media`
- `L3_scenario`: `group-avatar-server-precompose-and-unified-sync-contract`

## 背景与动机

当前群头像展示存在明显缺口：客户端列表页和群组相关页面仍可能依赖成员头像列表实时渲染，导致弱网、缓存未命中或解码竞争时出现长时间默认头像、显示抖动和不一致。与此同时，用户头像、群头像、图片、视频在对象标识、URL 暴露和同步传播上也缺少统一规范，容易在服务边界与运行时能力之间反复耦合。

本场景在 `/prd` 阶段收口以下最小可实施合同：

1. 群头像以服务端预合成为唯一主链路
2. 用户头像与群头像归属边界清晰
3. 统一媒体对象引用、objectKey 与 CDN URL 规范
4. 群头像与头像变化通过统一 sync patch + realtime hint 传播

## 目标用户

- 依赖群头像快速辨识会话的聊天用户
- 需要基于统一对象模型实施头像、媒体和同步链路的服务开发者

## 功能范围

### In Scope

- **统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。
- **服务端预合成规则**：仅取前 9 成员、按加入顺序、生成群头像派生资源。
- **重算触发**：
  - `ConversationCreated`
  - `MemberJoined`
  - `MemberLeft`
  - 前 9 成员之一收到 `UserAvatarUpdated`
- **sourceHash**：以 `top9UserIdsInOrder + top9AvatarAssetIds + top9AvatarVersions + top9AvatarUrls + layoutVersion` 计算 `groupAvatarSourceHash`，未变化则跳过重算。
- **对象标识合同**：群头像、用户头像与聊天/内容媒体统一使用 `AssetRef / MediaAsset`，数据库主存 `assetId + version`。
- **URL 合同**：统一对外 `{cdnBaseUrl}/{objectKey}?v={version}`，`cdnBaseUrl` 必须显式包含 `http/https` scheme。
- **同步合同**：
  - patch 类型至少支持 `user.avatar.updated`、`conversation.avatar.updated`
  - realtime 只发 hint
  - 客户端按 `cursor/syncSeq` 拉增量
- **失败策略**：预合成失败时保留上一版 `avatarUrl`；新群没有上一版时建群失败或服务端重试至可用，不向 App 下发空 `avatarUrl`。

### Out of Scope

- 用户手动上传群头像
- 群头像审核、模板市场、多样式切换
- 头像裁剪与智能排版算法优化
- 记录数据批量回填与全量迁移执行细节

## 约束

- 用户头像主数据只归 `user-service`
- 群头像主数据只归 `chat-service`
- runtime 只负责公共能力，不承载“前 9 成员”这类业务规则本身
- metadata 是新增字段、事件、patch 类型和接口的唯一真相源
- 客户端不允许使用旧群头像 URL 字段或 `avatarCompositeUrls` 作为群头像主逻辑输入；旧群头像 URL 字段不再填充。

## 对标输入与吸收结论

| 对标 | 借鉴 | 不借鉴 |
|------|------|--------|
| 微信/企业微信公开 IM 资料 | 长连接通知 + 增量拉取 + seq/gap fill；群头像稳定、弱实时更新策略 | 闭源私有实现与自研基础设施 |
| 通用对象存储/CDN 实践 | 数据库存引用、对象存储存实体、CDN 对外暴露 | 业务表直接存临时签名 URL |

吸收结论：

- 群头像不应在客户端会话列表里实时拼接
- 头像变化传播不能依赖单次推送，必须具备补偿拉取
- URL 规范必须由 runtime 统一，而不是各服务自行拼接

## 角色分工

- `user-service`：用户头像 `avatarAssetId / avatarVersion`
- `chat-service`：群头像 `groupAvatarAssetId / groupAvatarVersion / groupAvatarSourceHash`
- `runtime/media`：对象存储、CDN、objectKey、URL 规范
- `runtime/sync`：patch envelope、cursor、syncSeq
- `runtime/realtime`：在线 hint 通道

## 既有 Story 覆盖矩阵

| 节点 | 关系 | 本场景覆盖 |
|------|------|-----------|
| `runtime/runtime-media/media-upload-and-storage--upload-session-and-cdn-delivery` | 提供底层上传与 CDN 分发能力 | 复用，不重新定义上传三段式 |
| `chat-conversation/chat-experience-optimization/chat-detail-avatar-display` | 已定义对话页头像显示与缓存 | 保留页面行为，改由本场景冻结头像来源与同步输入 |
| `chat-conversation/group-creation-member-management/group-member-roster-version-sync` | 已冻结 roster revision 与合并推送 | 直接作为群头像重算触发与拉取判断前置合同 |

## 数据生命周期合同

- 用户头像：长期保留当前版本，过往版本本延迟清理
- 群头像：由服务端预合成生成，可重算、可替换；过往版本本按策略清理
- 群头像 URL：由服务端保证 active 会话非空可访问；客户端仅保留异常诊断与通用图片加载错误态。

## 权限 / 分享 / 可见性边界

- 仅会话参与者可见对应群头像更新结果
- 同步 patch 不新增跨会话可见性
- 不为分享链路生成单独头像逻辑；分享如需头像，仍消费统一资产引用

## 非功能目标

- 列表首屏群头像展示主链路为单图加载
- 建群第一版群头像必须在会话对 App 可见前生成；成员变更后的重算可异步执行并保留上一版头像。
- 在线 hint 到客户端发起拉取的目标时延 P95 < 500ms
- sync patch 允许重复投递，但客户端必须幂等消费

## 验收重点

1. 对外统一 `avatarUrl` 与内部 `groupAvatarAssetId/groupAvatarVersion/groupAvatarSourceHash`、patch 类型在合同层冻结
2. top9 + sourceHash + 服务端非空保证路径冻结
3. runtime/media 与 runtime/sync 的边界不混淆
4. 复用 roster revision、消息 sync 既有合同，不创建第二套版本体系
