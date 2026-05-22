# tasks：local-cache-architecture

## M1：规格基线

- 冻结 `spec.md`、`design.md`、`acceptance.yaml`。
- 冻结 `object-cache-policy.yaml`、`cache-inventory.md`、`cache-management-runbook.md`。
- 在 `runtime-client-foundation/spec.md` 登记 L3 子节点。

## M2：业务对象规格登记

- `Post`：在 post-create-update 登记对象缓存、详情正文、媒体引用、互动 overlay。
- `Comment`：在 comment-thread 登记分页 snapshot、作者快照、pending comment outbox。
- `UserProfile`：在 profile-read-update 登记头像版本、关系 overlay、当前用户保护策略。
- `Conversation`：在 chat-list-local-cache 登记群头像版本、members roster revision、待发送消息保护。
- `MediaResource`：在 runtime-media 登记资源引用、variant、字节清理边界。
- `QuerySnapshot`：在 unified-items-cursor 登记 surface + query signature + cursor 快照。

## M3：首批代码实施

- 新增或收敛 `ObjectCacheStore<T>`、`QuerySnapshotStore<TId>`、`ResourceCacheController`。
- 为内容域新增 `PostObjectCacheService` 与 `ContentQuerySnapshotStore`。
- 用 `CacheRepositoryDecorator` 接入 stale-while-revalidate、请求去重、后台刷新。
- 图片、头像、封面、正文图统一通过 `AppCachedNetworkImage` 及语义 wrapper。

## M4：缓存清理入口

- 新增 `CacheManagementService`。
- 设置页提供分层清理入口、空间估算、影响说明、二次确认和完成统计。
- 清理必须保护草稿、待发送消息、待同步 outbox、当前用户最小资料。

## M5：测试与门禁

- T1：策略文件、业务 spec 引用、图片入口 allowlist ratchet。
- T2：对象缓存命中、stale-while-revalidate、分层清理保护。
- T3：Remote 版本字段、sync patch/outbox 合并、弱网恢复。
- T4：真机冷启动、滚动、重复详情、头像/封面变更、清理缓存后离线回显。
