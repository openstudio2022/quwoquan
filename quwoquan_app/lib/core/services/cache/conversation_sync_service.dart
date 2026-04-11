import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';

/// 会话列表同步引擎
///
/// 从云端拉取全量会话 ID + 分拆时间戳，与本地缓存逐项比较：
/// - `settingsUpdatedAt` 变化 → 需批量拉取完整会话数据
/// - `lastMessageAt` 变化但 settings 未变 → 仅更新列表展示字段
/// - 30 秒防抖，避免切 Tab 频繁触发
class ConversationSyncService {
  ConversationSyncService({
    required this.repo,
    required this.cache,
  });

  final ChatRepository repo;
  final ConversationCacheService cache;

  bool _syncing = false;
  DateTime? _lastSyncTime;
  static const _minSyncInterval = Duration(seconds: 30);

  /// 执行增量同步，返回是否有数据变更
  Future<bool> sync({bool force = false}) async {
    if (_syncing) return false;
    if (!force && _lastSyncTime != null &&
        DateTime.now().difference(_lastSyncTime!) < _minSyncInterval) {
      return false;
    }

    _syncing = true;
    _lastSyncTime = DateTime.now();
    try {
      final timestamps = await repo.getConversationTimestamps();
      final cloudIds = <String>{};
      final needFetchIds = <String>[];
      var hasChanges = false;

      for (final ts in timestamps) {
        final m = ts.toMap();
        final id = m['id'] as String? ?? '';
        if (id.isEmpty) continue;
        cloudIds.add(id);

        final cloudSettingsUpdatedAt =
            m['settingsUpdatedAt'] as String? ?? m['updatedAt'] as String? ?? '';
        final cloudLastMessageAt =
            m['lastMessageAt'] as String? ?? '';
        final localSettingsTs = cache.getSettingsTimestamp(id);
        final localMessageTs = cache.getMessageTimestamp(id);

        if (localSettingsTs == null || localSettingsTs != cloudSettingsUpdatedAt) {
          needFetchIds.add(id);
          hasChanges = true;
        } else if (localMessageTs != cloudLastMessageAt) {
          cache.updateListFields(
            id,
            lastMessagePreview: m['lastMessagePreview'] as String?,
            lastMessageAt: cloudLastMessageAt,
            unreadCount: m['unreadCount'] as int?,
          );
          hasChanges = true;
        }
      }

      final localAll = cache.getAll();
      for (final local in localAll) {
        final localId = local['_id'] as String? ?? local['id'] as String? ?? '';
        if (localId.isNotEmpty && !cloudIds.contains(localId)) {
          cache.remove(localId);
          hasChanges = true;
        }
      }

      if (needFetchIds.isNotEmpty) {
        const batchSize = 50;
        for (var i = 0; i < needFetchIds.length; i += batchSize) {
          final batch = needFetchIds.sublist(
            i,
            i + batchSize > needFetchIds.length
                ? needFetchIds.length
                : i + batchSize,
          );
          final conversations = await repo.batchGetConversations(batch);
          cache.putAll(
            conversations.map((c) => c.toMap()).toList(growable: false),
          );
        }
      }

      return hasChanges;
    } catch (_) {
      return false;
    } finally {
      _syncing = false;
    }
  }
}
