# L3 特性：profile-read-update

## 功能说明
- 细化 profile-read-update 特性的功能边界与端云协同行为。

## 约束
- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。
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
