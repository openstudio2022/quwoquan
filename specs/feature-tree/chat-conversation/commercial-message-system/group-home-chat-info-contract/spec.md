# L3 Story：group-home-chat-info-contract

## 最小价值点

让群聊天页和聊天信息页共同消费同一个 `GroupHome` 真相源，保证群名称、来源、成员数、公告和能力入口一致。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：群聊天与聊天信息页一致性

## 行为范围

### In Scope

- 群聊天页直接进入会话而非先落群主页。
- 群聊天页顶部与聊天信息页共用 `GroupHome` 数据。
- 云端预合成群头像 `avatarUrl` 的单一来源。

### Out of Scope

- 联系首页聚合。
- 群治理权限模型的底层实现。

## 行为规则

- Given：用户已加入一个带 `GroupHome` 事实源的群。
- When：用户从消息首页进入群聊天并查看聊天信息页。
- Then：两个页面读取同一 `GroupHome` 事实源，展示一致的群基础信息和能力入口。

## 接口契约

- API path / operation：`GetGroupHome` 与群会话相关 metadata operation。
- DTO / projection：`GroupHome`。
- error code：消息域与 runtime error metadata。
- surface / route：群聊天页和聊天信息页 route / surface metadata。

## 验收关注点

- done_when：群聊天页与聊天信息页展示的一致性由同一事实源保障。
- edge cases：群头像 fallback、成员数变更、公告为空。
- test evidence：`T2_module_interaction`、`T3_service_contract`、`T4_device_journey`。
