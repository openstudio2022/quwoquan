import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_list_commands.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_avatar_prefetch.dart';

/// ChatInboxView 对象的会话列表状态。
class ChatInboxListState {
  const ChatInboxListState({
    this.items = const <ChatInboxViewData>[],
    this.isLoading = false,
    this.error,
  });

  final List<ChatInboxViewData> items;
  final bool isLoading;
  final String? error;

  ChatInboxListState copyWith({
    List<ChatInboxViewData>? items,
    bool? isLoading,
    String? error,
  }) {
    return ChatInboxListState(
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class ChatInboxListNotifier extends Notifier<ChatInboxListState>
    implements ChatInboxListCommands {
  bool _loaded = false;
  Future<void>? _pendingLoad;
  bool _cacheListenerRegistered = false;

  ChatInboxRepository get _repo => ref.read(chatInboxRepositoryProvider);
  ChatInboxCache get _cache => ref.read(chatInboxCacheProvider);
  ConversationAvatarPrefetchCapability get _avatarPrefetch =>
      ref.read(conversationAvatarPrefetchProvider);

  @override
  ChatInboxListState build() {
    ref.watch(chatInboxRepositoryProvider);
    ref.listen(activePersonaContextProvider, (_, _) {
      _loaded = false;
      Future<void>.microtask(() {
        if (ref.mounted) {
          load(force: true);
        }
      });
    });
    _ensureCacheListener();
    _loaded = false;
    Future<void>.microtask(() {
      if (ref.mounted) {
        load();
      }
    });
    return const ChatInboxListState();
  }

  Future<void> load({bool force = false}) async {
    _ensureCacheListener();
    if (_pendingLoad != null) {
      return _pendingLoad!;
    }
    if (_loaded && !force) {
      return;
    }
    final future = () async {
      _loaded = true;

      final cached = _readCache();
      if (!ref.mounted) {
        return;
      }
      unawaited(_avatarPrefetch.prefetchInbox(_prefetchItems(cached)));
      _preloadConversationAvatarUrls(cached);
      state = state.copyWith(items: cached, isLoading: true);

      try {
        final remote = _sortItems(await _repo.listInbox(limit: 100));
        await _avatarPrefetch.prefetchInbox(_prefetchItems(remote));
        if (!ref.mounted) {
          return;
        }
        _cache.replaceInbox(remote.map(_cacheEntryFromInbox));
        _preloadConversationAvatarUrls(remote);
        state = state.copyWith(items: remote, isLoading: false, error: null);
        unawaited(
          _avatarPrefetch.prefetchInbox(
            _prefetchItems(remote),
            offset: kConversationAvatarInitialPrefetchLimit,
            limit: kConversationAvatarBackgroundPrefetchLimit,
          ),
        );
      } catch (error) {
        if (!ref.mounted) {
          return;
        }
        final fallback = cached.isNotEmpty ? cached : _fallbackItems();
        state = state.copyWith(
          items: fallback,
          isLoading: false,
          error: runtimeErrorDisplayMessage(error),
        );
      }
    }();
    _pendingLoad = future;
    try {
      await future;
    } finally {
      if (identical(_pendingLoad, future)) {
        _pendingLoad = null;
      }
    }
  }

  @override
  Future<void> refresh() async {
    await load(force: true);
  }

  void _refreshFromCache() {
    final cached = _readCache();
    _preloadConversationAvatarUrls(cached);
    state = state.copyWith(items: cached);
  }

  void _preloadConversationAvatarUrls(List<ChatInboxViewData> items) {
    for (final item in items) {
      final avatarUrl = item.avatarUrl.trim();
      if (avatarUrl.isEmpty) {
        continue;
      }
      unawaited(AppImageCacheController.warmAvatarCache(avatarUrl));
    }
  }

  void _ensureCacheListener() {
    if (_cacheListenerRegistered) {
      return;
    }
    final cache = ref.read(chatInboxCacheProvider);
    void handleCacheChange() {
      if (_loaded) {
        _refreshFromCache();
      }
    }

    cache.addInboxListener(handleCacheChange);
    ref.onDispose(() => cache.removeInboxListener(handleCacheChange));
    _cacheListenerRegistered = true;
  }

  @override
  void markConversationRead(String conversationId) {
    final next = _sortItems(
      state.items
          .map((item) {
            if (item.id != conversationId) {
              return item;
            }
            return item.copyWith(unreadCount: 0, mentionUnreadCount: 0);
          })
          .toList(growable: false),
    );
    // 乐观清零未读是展示提示，不是真值：inbox projection 的下一次读结果会覆盖它。
    _cache.applyOptimisticInboxHint(
      conversationId,
      const ChatInboxOptimisticHint(unreadCount: 0, mentionUnreadCount: 0),
    );
    state = state.copyWith(items: next);
  }

  List<ChatInboxViewData> _readCache() {
    final cached = <ChatInboxViewData>[];
    for (final entry in _cache.readInbox()) {
      final dto = _inboxFromCacheEntry(entry);
      if (dto.id.isEmpty) {
        continue;
      }
      cached.add(dto);
    }
    return _sortItems(cached);
  }

  List<ChatInboxViewData> _fallbackItems() {
    return const <ChatInboxViewData>[];
  }

  List<ConversationAvatarPrefetchItem> _prefetchItems(
    List<ChatInboxViewData> items,
  ) {
    return items
        .map(
          (item) => ConversationAvatarPrefetchItem(
            conversationId: item.id,
            conversationType: item.type,
            avatarUrl: item.avatarUrl,
            groupAvatarVersion: item.groupAvatarVersion,
          ),
        )
        .toList(growable: false);
  }

  List<ChatInboxViewData> _sortItems(List<ChatInboxViewData> items) {
    final sorted = [...items];
    sorted.sort((a, b) {
      if (a.pinned != b.pinned) {
        return a.pinned ? -1 : 1;
      }
      final aTime = a.lastMessageTime;
      final bTime = b.lastMessageTime;
      if (aTime == null && bTime == null) {
        return a.title.compareTo(b.title);
      }
      if (aTime == null) {
        return 1;
      }
      if (bTime == null) {
        return -1;
      }
      final timeCompare = bTime.compareTo(aTime);
      if (timeCompare != 0) {
        return timeCompare;
      }
      return a.title.compareTo(b.title);
    });
    return List<ChatInboxViewData>.unmodifiable(sorted);
  }
}

ChatInboxCacheEntry _cacheEntryFromInbox(ChatInboxViewData source) {
  return ChatInboxCacheEntry(
    id: source.id,
    type: source.type,
    title: source.title,
    avatarUrl: source.avatarUrl,
    groupAvatarVersion: source.groupAvatarVersion,
    lastMessagePreview: source.lastMessagePreview,
    lastMessageType: source.lastMessageType,
    lastMessageTime: source.lastMessageTime,
    lastSeq: source.lastSeq,
    unreadCount: source.unreadCount,
    mentionUnreadCount: source.mentionUnreadCount,
    muted: source.muted,
    pinned: source.pinned,
    circleId: source.circleId,
  );
}

ChatInboxViewData _inboxFromCacheEntry(ChatInboxCacheEntry source) {
  return ChatInboxViewData(
    id: source.id,
    type: source.type,
    title: source.title,
    avatarUrl: source.avatarUrl,
    groupAvatarVersion: source.groupAvatarVersion,
    lastMessagePreview: source.lastMessagePreview,
    lastMessageType: source.lastMessageType,
    lastMessageTime: source.lastMessageTime,
    lastSeq: source.lastSeq,
    unreadCount: source.unreadCount,
    mentionUnreadCount: source.mentionUnreadCount,
    muted: source.muted,
    pinned: source.pinned,
    circleId: source.circleId,
  );
}

final chatInboxListProvider =
    NotifierProvider<ChatInboxListNotifier, ChatInboxListState>(
      ChatInboxListNotifier.new,
    );
