# chat-experience-optimization L2 设计方案

## 设计动因

趣聊体验优化是对聊天列表页、对话页、群管理页的全面打磨，从 UI 视觉到数据同步到管理权限，消除与微信级体验的差距。

## 四个 L3 Story 的依赖关系

```
chat-list-ui-polish          ← 无依赖（纯前端 UI）
  ↓ 提供 RoundedSquareAvatar / GroupAvatarGrid 组件
chat-detail-avatar-display   ← 依赖 RoundedSquareAvatar
  ↓ 提供 UserProfileCacheService
chat-list-local-cache        ← 独立（会话缓存层）
chat-group-admin-govern      ← 依赖 RoundedSquareAvatar + UserProfileCacheService
```

## 建议实施顺序

```
批次 1（纯前端，无新接口）：
  1. chat-list-ui-polish → 产出通用组件

批次 2（需端云对齐）：
  2. chat-list-local-cache → 会话缓存基础设施
  3. chat-detail-avatar-display → 用户信息缓存 + 头像展示
  4. chat-group-admin-govern → 群管理治理
```

## 共享组件清单

| 组件 | 路径 | 使用方 |
|---|---|---|
| `RoundedSquareAvatar` | `lib/components/avatar/rounded_square_avatar.dart` | 全部 4 个 L3 |
| `GroupAvatarGrid` | `lib/components/avatar/group_avatar_grid.dart` | chat-list-ui-polish |
| `ConversationCacheService` | `lib/cloud/chat/cache/conversation_cache_service.dart` | chat-list-local-cache |
| `UserProfileCacheService` | `lib/cloud/chat/cache/user_profile_cache_service.dart` | chat-detail-avatar-display |
| `ConversationGroupSettings` | `lib/cloud/chat/models/conversation_group_settings.dart` | chat-group-admin-govern |

## 新增云端接口汇总

| 接口 | L3 来源 |
|---|---|
| `GET /conversations/timestamps` | chat-list-local-cache |
| `POST /conversations/batch` | chat-list-local-cache |
| `POST /users/timestamps` | chat-detail-avatar-display |
| `GET /conversations/{id}/settings` | chat-group-admin-govern |
| `PATCH /conversations/{id}/settings` | chat-group-admin-govern |
| `PATCH /conversations/{id}/owner` | chat-group-admin-govern |
| `PUT /conversations/{id}/admins` | chat-group-admin-govern |
| `DELETE /conversations/{id}` | chat-group-admin-govern |
