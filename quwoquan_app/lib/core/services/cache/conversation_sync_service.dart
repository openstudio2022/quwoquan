import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';

/// 会话列表同步引擎
///
/// 从云端拉取全量会话 ID + 时间戳，与本地缓存逐项比较，
/// 仅拉取新增或更新的会话数据，删除本地多余会话。
class ConversationSyncService {
  ConversationSyncService({
    required this.repo,
    required this.cache,
  });

  final ChatRepository repo;
  final ConversationCacheService cache;

  bool _syncing = false;

  /// 执行增量同步，返回是否有数据变更
  Future<bool> sync() async {
    if (_syncing) return false;
    _syncing = true;
    try {
      final timestamps = await repo.getConversationTimestamps();
      final cloudIds = <String>{};
      final needFetchIds = <String>[];

      for (final ts in timestamps) {
        final id = ts['id'] as String? ?? '';
        if (id.isEmpty) continue;
        cloudIds.add(id);

        final cloudUpdatedAt = ts['updatedAt'] as String? ?? '';
        final localUpdatedAt = cache.getTimestamp(id);

        if (localUpdatedAt == null || localUpdatedAt != cloudUpdatedAt) {
          needFetchIds.add(id);
        }
      }

      // 删除云端已不存在的本地会话
      final localAll = cache.getAll();
      for (final local in localAll) {
        final localId = local['_id'] as String? ?? local['id'] as String? ?? '';
        if (localId.isNotEmpty && !cloudIds.contains(localId)) {
          cache.remove(localId);
        }
      }

      if (needFetchIds.isEmpty) return false;

      // 分批拉取（每批最多 50 个）
      const batchSize = 50;
      for (var i = 0; i < needFetchIds.length; i += batchSize) {
        final batch = needFetchIds.sublist(
          i,
          i + batchSize > needFetchIds.length
              ? needFetchIds.length
              : i + batchSize,
        );
        final conversations = await repo.batchGetConversations(batch);
        cache.putAll(conversations);
      }

      return true;
    } catch (_) {
      return false;
    } finally {
      _syncing = false;
    }
  }
}
