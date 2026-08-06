import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_rows.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final messageHomeRowsStateProvider =
    FutureProvider.family<MessageHomeRowsSnapshot, String>((ref, filter) async {
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'chat_list',
            route: '/chat',
            surface: filter,
            phase: 'onlineLoading',
            source: 'online',
          );
      final repo = ref.watch(chatConversationRepositoryProvider);
      try {
        final rows = await repo.listMessageHome(filter: filter, limit: 100);
        _storeMessageRowsInConversationCache(ref, rows);
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'chat_list',
              route: '/chat',
              surface: filter,
              phase: 'onlineSuccess',
              source: 'online',
              itemCount: rows.length,
              hasCache: false,
            );
        return MessageHomeRowsSnapshot(
          rows: List<MessageHomeRow>.unmodifiable(rows),
        );
      } catch (error) {
        final cached = _cachedMessageRowsForFilter(ref, filter);
        if (cached.isNotEmpty) {
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'chat_list',
                route: '/chat',
                surface: filter,
                phase: 'cacheFallback',
                source: 'cache',
                error: error,
                copyKey: 'chatListCacheFallback',
                itemCount: cached.length,
                hasCache: true,
              );
          return MessageHomeRowsSnapshot(
            rows: cached,
            cacheFallbackError: error,
            copyKey: 'chatListCacheFallback',
          );
        }
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'chat_list',
              route: '/chat',
              surface: filter,
              phase: 'blockingFailure',
              source: 'online',
              error: error,
              copyKey: 'chatListLoadFailedTitle',
              itemCount: 0,
              hasCache: false,
            );
        rethrow;
      }
    });

void _storeMessageRowsInConversationCache(
  Ref ref,
  Iterable<MessageHomeRow> rows,
) {
  final cachedRows = rows
      .where((row) => row.conversationId.trim().isNotEmpty)
      .toList(growable: false);
  if (cachedRows.isEmpty) {
    return;
  }
  ref.read(messageHomeCacheProvider).putMessageHomeRows(cachedRows);
}

List<MessageHomeRow> _cachedMessageRowsForFilter(Ref ref, String filter) {
  final rows = ref
      .read(messageHomeCacheProvider)
      .readMessageHomeRows()
      .where((row) {
        return _matchesMessageHomeFilter(row, filter);
      })
      .toList(growable: false);
  rows.sort((a, b) {
    if (a.pinned != b.pinned) {
      return a.pinned ? -1 : 1;
    }
    final aTime = a.lastActiveAt;
    final bTime = b.lastActiveAt;
    if (aTime == null && bTime == null) {
      return a.title.compareTo(b.title);
    }
    if (aTime == null) return 1;
    if (bTime == null) return -1;
    return bTime.compareTo(aTime);
  });
  return List<MessageHomeRow>.unmodifiable(rows);
}

bool _matchesMessageHomeFilter(MessageHomeRow item, String filter) {
  switch (filter) {
    case 'unread':
      return item.unreadCount > 0 || item.mentionUnreadCount > 0;
    case 'group':
      return item.conversationType == 'group';
    case 'direct':
      return item.conversationType != 'group' &&
          item.notificationId.trim().isEmpty;
    case 'notification':
      return item.notificationId.trim().isNotEmpty;
    case 'all':
    default:
      return true;
  }
}
