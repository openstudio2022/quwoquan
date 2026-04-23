# Sync Runtime 设计

本目录定义统一同步能力，包括：

- 用户同步流
- patch envelope
- cursor / seq
- 在线通知与 gap fill
- 排序、幂等、补偿

## 阅读顺序

1. `00-sync-overview.md`
2. `01-sync-domain-model.md`
3. `02-user-sync-stream.md`
4. `03-patch-envelope-and-cursor.md`
5. `04-realtime-and-gap-fill.md`
6. `05-ordering-idempotency-and-retry.md`
7. `06-message-avatar-roster-sync-flows.md`
8. `07-client-server-contracts.md`
