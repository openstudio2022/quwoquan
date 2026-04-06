# 阶段 4（Chat / User / RTC）类型化 — 状态快照

本文件与整改计划 **m4** 对齐，记录当前基线结论（非一次性完成声明）。

## Chat

- **`listInbox` → `List<ChatInboxDto>`** 已为强类型入口；新功能应优先使用。
- **`listConversations` → `List<Map<String, dynamic>>`** 仍为 legacy wire，迁移时需对照 `service.yaml` 与 `ChatInboxDto` 字段对齐后淘汰或改为分页 DTO。

## User / User profile

- `user_profile_repository` / `user_repository` 仍存在大量 `Future<Map<String, dynamic>>`；下一切片应按 API 分批引入 metadata DTO（与 `contracts/metadata` 同步）。

## RTC

- `rtc_repository` 中会话/令牌类响应仍以 Map 为主；应对齐 `rtc` 域 projection 后再改 Abstract 签名。

## 验证

```bash
make verify-app-ui-map-literal-budget
flutter test test/cloud/chat/
```
