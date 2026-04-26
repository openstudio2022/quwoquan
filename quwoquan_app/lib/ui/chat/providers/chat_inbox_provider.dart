import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

class ChatInboxListState {
  const ChatInboxListState({
    this.items = const <ChatInboxDto>[],
    this.isLoading = false,
    this.error,
  });

  final List<ChatInboxDto> items;
  final bool isLoading;
  final String? error;

  ChatInboxListState copyWith({
    List<ChatInboxDto>? items,
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

class ChatInboxListNotifier extends Notifier<ChatInboxListState> {
  bool _loaded = false;
  Future<void>? _pendingLoad;
  bool _cacheListenerRegistered = false;

  ChatRepository get _repo => ref.read(chatRepositoryProvider);
  ConversationCacheService get _cache => ref.read(conversationCacheProvider);

  @override
  ChatInboxListState build() {
    ref.watch(chatRepositoryProvider);
    ref.listen(activePersonaContextProvider, (_, __) {
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
      state = state.copyWith(items: cached, isLoading: true);

      try {
        final remote = _sortItems(await _repo.listInbox(limit: 100));
        if (!ref.mounted) {
          return;
        }
        if (remote.isNotEmpty) {
          _cache.putAll(
            remote.map((item) => item.toMap()).toList(growable: false),
          );
        }
        state = state.copyWith(
          items: remote.isNotEmpty ? remote : cached,
          isLoading: false,
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

  Future<void> refresh() async {
    await load(force: true);
  }

  void _refreshFromCache() {
    final cached = _readCache();
    state = state.copyWith(items: cached);
  }

  void _ensureCacheListener() {
    if (_cacheListenerRegistered) {
      return;
    }
    final cache = ref.read(conversationCacheProvider);
    void handleCacheChange() {
      if (_loaded) {
        _refreshFromCache();
      }
    }

    cache.addListener(handleCacheChange);
    ref.onDispose(() => cache.removeListener(handleCacheChange));
    _cacheListenerRegistered = true;
  }

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
    _cache.updateListFields(
      conversationId,
      unreadCount: 0,
      mentionUnreadCount: 0,
    );
    state = state.copyWith(items: next);
  }

  List<ChatInboxDto> _readCache() {
    final cached = <ChatInboxDto>[];
    for (final row in _cache.getAll()) {
      final dto = ChatInboxDto.fromMap(row);
      if (dto.id.isEmpty) {
        continue;
      }
      cached.add(dto);
    }
    return _sortItems(cached);
  }

  List<ChatInboxDto> _fallbackItems() {
    return const <ChatInboxDto>[];
  }

  List<ChatInboxDto> _sortItems(List<ChatInboxDto> items) {
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
    return List<ChatInboxDto>.unmodifiable(sorted);
  }
}

final chatInboxListProvider =
    NotifierProvider<ChatInboxListNotifier, ChatInboxListState>(
      ChatInboxListNotifier.new,
    );
