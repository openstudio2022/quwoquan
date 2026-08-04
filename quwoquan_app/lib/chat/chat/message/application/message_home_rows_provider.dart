import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_app/chat/chat/chat_inbox_view/application/chat_inbox_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const List<String> messageHomeFilters = <String>[
  'all',
  'unread',
  'group',
  'direct',
  'notification',
];

class MessageHomeRowsState {
  const MessageHomeRowsState({
    required this.items,
    this.cacheFallbackError,
    this.copyKey,
  });

  final List<ChatListItemViewModel> items;
  final Object? cacheFallbackError;
  final String? copyKey;

  bool get isCacheFallback => cacheFallbackError != null;
}

final messageHomeRowsStateProvider =
    FutureProvider.family<MessageHomeRowsState, String>((ref, filter) async {
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
        final items = rows
            .map(ChatListItemViewModel.fromMessageHomeDto)
            .toList();
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'chat_list',
              route: '/chat',
              surface: filter,
              phase: 'onlineSuccess',
              source: 'online',
              itemCount: items.length,
              hasCache: false,
            );
        return MessageHomeRowsState(items: items);
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
          return MessageHomeRowsState(
            items: cached,
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

int totalUnreadMessages(Iterable<ChatListItemViewModel> rows) {
  return rows.fold<int>(0, (total, row) => total + row.unreadCount);
}

void refreshMessageReadState(WidgetRef ref, String conversationId) {
  ref.read(chatInboxListProvider.notifier).markConversationRead(conversationId);
  for (final filter in messageHomeFilters) {
    ref.invalidate(messageHomeRowsStateProvider(filter));
  }
}

void _storeMessageRowsInConversationCache(
  Ref ref,
  Iterable<MessageHomeRow> rows,
) {
  final records = rows
      .where((row) => row.conversationId.trim().isNotEmpty)
      .map(_conversationCacheRecordFromMessageHomeRow)
      .where((record) => record.id.isNotEmpty)
      .toList(growable: false);
  if (records.isEmpty) {
    return;
  }
  ref.read(conversationCacheProvider).putAll(records);
}

List<ChatListItemViewModel> _cachedMessageRowsForFilter(
  Ref ref,
  String filter,
) {
  final records = ref
      .read(conversationCacheProvider)
      .getAll()
      .where((record) {
        final item = ChatListItemViewModel.fromDto(
          record.toChatInboxViewData(),
        );
        return _matchesMessageHomeFilter(item, filter);
      })
      .toList(growable: false);
  records.sort((a, b) {
    if (a.pinned != b.pinned) {
      return a.pinned ? -1 : 1;
    }
    final aTime = DateTime.tryParse(a.lastMessageAt);
    final bTime = DateTime.tryParse(b.lastMessageAt);
    if (aTime == null && bTime == null) {
      return a.title.compareTo(b.title);
    }
    if (aTime == null) return 1;
    if (bTime == null) return -1;
    return bTime.compareTo(aTime);
  });
  final rows = records
      .map(
        (record) => ChatListItemViewModel.fromDto(record.toChatInboxViewData()),
      )
      .toList(growable: false);
  return List<ChatListItemViewModel>.unmodifiable(rows);
}

bool _matchesMessageHomeFilter(ChatListItemViewModel item, String filter) {
  switch (filter) {
    case 'unread':
      return item.hasUnread || item.hasMention;
    case 'group':
      return item.isGroup;
    case 'direct':
      return !item.isGroup && !item.isNotification;
    case 'notification':
      return item.isNotification;
    case 'all':
    default:
      return true;
  }
}

ConversationCacheRecord _conversationCacheRecordFromMessageHomeRow(
  MessageHomeRow row,
) {
  return ConversationCacheRecord(
    id: row.conversationId.trim(),
    type: row.conversationType.trim().isEmpty
        ? 'direct'
        : row.conversationType.trim(),
    title: row.title.trim(),
    avatarUrl: row.avatarUrl.trim(),
    groupAvatarVersion: row.groupAvatarVersion,
    lastMessagePreview: row.summary.trim(),
    lastMessageType: MessageType.text,
    lastMessageAt: row.lastActiveAt?.toIso8601String() ?? '',
    unreadCount: row.unreadCount,
    mentionUnreadCount: row.mentionUnreadCount,
    muted: row.muted,
    pinned: row.pinned,
  );
}
