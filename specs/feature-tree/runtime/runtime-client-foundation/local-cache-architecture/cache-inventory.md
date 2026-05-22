# 本地缓存 Inventory 基线

## 目的

本 inventory 记录对象级缓存首批覆盖面、当前仓库状态、缺口与实施入口。它不是运行时真相源；实施后真相源应沉淀到 `ObjectCacheStore`、`QuerySnapshotStore`、`ResourceCacheController` 与对应 tests。

## 对象视角

| 对象 | 当前状态 | 首批缺口 | 实施入口 |
|---|---|---|---|
| `UserProfile` | 已存在 `user_profile_cache_service.dart` 线索，但需确认接线范围 | 头像版本、关系状态 overlay、当前用户/关注/联系人保护策略未统一 | `quwoquan_app/lib/core/services/cache/user_profile_cache_service.dart`、profile Repository/Provider |
| `Post` | feed Provider 多为进程内状态；详情页直接远端取详情 | 缺 `PostObjectCacheService`、正文/blocks 持久化、互动 overlay、离线详情回显 | content Repository、discovery feed Provider、article/photo/video detail pages |
| `Conversation` | 已有会话缓存、聊天搜索本地库、sync patch、群头像版本字段 | 需纳入统一输出合同与分层清理保护；成员头像预取需和缓存策略登记 | `conversation_cache_service.dart`、`chat_inbox_provider.dart`、avatar members provider |
| `Comment` | 评论列表与作者头像散落在评论组件/Repository | 缺 comment page snapshot、作者快照、pending comment outbox 保护 | comment viewer、content comment Repository |
| `MediaResource` | 已有 `AppCachedNetworkImage` 与 media download cache；仍有裸 `NetworkImage` / `CachedNetworkImage` allowlist | 入口未全收口，resource variant、清理策略、引用关系未统一 | `app_cached_network_image.dart`、`media_download_cache.dart`、network image gate |
| `QuerySnapshot` | chat 搜索已有本地库；feed/search/profile/circle 查询快照未统一 | 缺 surface + query signature + cursor 的统一 store；tab 切换/重启恢复未统一 | discovery/search/profile/circle Providers |

## 缓存层级

| 层级 | 现有能力 | 需要补齐 |
|---|---|---|
| L0 UI 状态 | 部分页面依赖 Flutter 保活或 Provider 状态 | 一级/二级 tab 保活、滚动位置与 query snapshot 结合 |
| L1 查询快照 | chat 搜索局部具备 | feed/search/profile/circle 统一 `QuerySnapshotStore` |
| L2 对象缓存 | chat 较完整，user 有部分服务，content 缺失 | `ObjectCacheStore<T>` 与对象策略登记 |
| L3 资源缓存 | 图片 wrapper 存在，媒体下载缓存存在 | 统一语义 wrapper、variant、空间清理与门禁递减 |
| L4 同步一致性 | chat 有 sync patch；content 互动状态分散 | outbox/overlay 统一、版本字段与 sync hint 对齐 |

## 关键文件基线

| 文件 | 当前角色 | 后续动作 |
|---|---|---|
| `quwoquan_app/lib/core/widgets/app_cached_network_image.dart` | 图片缓存统一入口基础 | 增加 avatar/cover/inline/full 语义 wrapper 或 preset 使用规范 |
| `quwoquan_app/lib/cloud/media/media_download_cache.dart` | 媒体下载缓存 | 明确与图片 wrapper 的边界：大资源下载 vs UI 图片显示 |
| `quwoquan_app/lib/core/services/cache/conversation_cache_service.dart` | 会话对象缓存 | 对齐 `CacheReadResult`、清理保护、diagnostics |
| `quwoquan_app/lib/core/services/cache/local_chat_search_store.dart` | chat query/search 本地库 | 作为 `QuerySnapshotStore` 设计参考 |
| `quwoquan_app/lib/core/services/cache/user_profile_cache_service.dart` | 用户资料缓存线索 | 确认接线，补版本、关系 overlay、保护策略 |
| `quwoquan_app/lib/ui/discovery/providers/discovery_feed_provider.dart` | feed 状态入口 | 接入 `ContentQuerySnapshotStore` 与 post object cache |
| `quwoquan_app/lib/ui/content/pages/article_detail_page.dart` | 文章详情读取入口 | 接入 post detail object cache 与正文离线恢复 |
| `quwoquan_app/scripts/media/verify_app_network_image_surface.py` | 图片入口静态门禁 | 纳入直用 `CachedNetworkImage` ratchet |
| `specs/gates/app_network_image_policy_allowlist.yaml` | 图片入口豁免清单 | 只允许递减，不新增新债 |

## 首批实施清单

1. 冻结 `CacheReadResult<T>` 与 `object-cache-policy.yaml`。
2. 确认并标注现有 chat/user 缓存是否已接线。
3. 新增 `PostObjectCacheService` 与 `ContentQuerySnapshotStore`。
4. 收口头像/封面/正文图入口到统一 wrapper。
5. 增加 `CacheManagementService`，先实现空间估算与资源清理。
6. 增加 T2 请求数、命中、清理保护测试。
7. 增加 T4 真机冷启动、滚动、离线、清理缓存证据。

## 风险与约束

- 不允许页面直接操作底层缓存表或文件。
- 不允许清理普通缓存时删除草稿、待发送消息、待同步 outbox。
- 不允许资源字节缓存决定业务对象新鲜度。
- 不允许绕过 metadata/codegen 在客户端硬编码服务端版本字段语义。
