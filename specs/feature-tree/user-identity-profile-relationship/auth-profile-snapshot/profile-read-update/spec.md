# L3 特性：profile-read-update

## 功能说明
- 细化 profile-read-update 特性的功能边界与端云协同行为。
- 个人资料编辑页按固定商用字段顺序提供完整编辑闭环：封面、头像、昵称、性别、生日、地区、手机号、趣我圈号、我的二维码、签名、标签。
- 编辑资料页必须采用 iOS 分组列表：封面/头像为独立紧凑媒体区块，基础资料、账号社交、扩展资料拆分为独立区块；普通字段的右侧值、图标和 chevron 必须在同一右侧槽位对齐。
- 编辑资料读取必须使用本人私有 `ProfileEditSnapshotWire`，公开主页资料不得暴露手机号、生日等私有字段；手机号只展示 owner credential 脱敏摘要。
- 趣我圈号由服务端在 owner/persona 初始化时系统分配，客户端只读展示与复制，不提供填写、修改或唯一性校验入口。
- 我的二维码由服务端 `ProfileQrCardWire` 生成公开主页 HTTPS payload，并附可撤销 `qrTokenId/styleVersion`；payload 禁止编码手机号、ownerId 或 bearer token。App 侧必须使用真实二维码 SDK 渲染 payload，不得用静态占位图或模拟图案。
- 标签选择必须进入 tag-service 标签体系：职业 V1 单选，兴趣 V1 多选；`identityTags` 只作为展示摘要和兼容投影，不作为 App 侧第二套标签真相源。

## 约束
- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。
- 资料编辑字段、错误码、请求上下文、route/surface、DTO projection 先走 metadata，再由 codegen/verify 闭合；禁止手改生成物作为契约来源。
- 封面/头像选择使用 App 既有 `ImagePickGateway.pickImage()`，强制单图返回；云侧保存只接受 media asset/url，不持久化本地临时路径。
- 二维码 SDK 选型以长期维护优先：Flutter 展示层使用 `pretty_qr_code`，其底层依赖 Dart `qr` 编码库；服务端只生成 payload 和 token 摘要，不生成客户端静态二维码图片。
- 生日按自然日期 `YYYY-MM-DD` 保存，不携带时区，范围为 1900-01-01 至当天；默认不预填今天。
- 签名 UI 文案为“签名”，服务字段可继续使用 `bio`，但 PATCH 校验和端侧输入上限为 60 字。
- 手机号绑定必须复用登录域 OTP/运营商一键能力：`SendOtp(sourceOperation=bind_phone)` + `BindPhoneCredential` 或 `BindCarrierPhoneCredential`；通用 `BindCredential` 不再承担手机号验证。
- 用户资料读侧缓存必须遵守 `runtime-client-foundation/local-cache-architecture`，对象策略以 [`object-cache-policy.yaml`](../../../runtime/runtime-client-foundation/local-cache-architecture/object-cache-policy.yaml) 中 `UserProfile` 为准。
- 当前用户、关注用户、互相关注用户、聊天联系人、最近互动作者进入 `pinned` 或 `recent` 缓存；仅 feed 中偶遇的作者不得升级为长期保留对象。
- 头像资源跟随 `avatarVersion` 失效；清理临时图片时只删除头像字节，不删除用户资料、头像 URL 与版本。
- 关注/取消关注、拉黑/解除拉黑等关系写操作通过 overlay/outbox 呈现 desired state，云端确认后按 `relationshipVersion` 合并。
- 普通缓存清理不得删除当前用户最小资料、关注/联系人关系、待同步关系 outbox。

## 验收标准
- A1：功能路径可执行且输出稳定。
- A7：契约一致性校验通过。
- A8：对应自动化测试映射完整。
- A9：用户对象缓存命中时可离线展示最小资料；头像版本变化可刷新；分层清理不破坏当前用户、关注/联系人与待同步关系操作。
