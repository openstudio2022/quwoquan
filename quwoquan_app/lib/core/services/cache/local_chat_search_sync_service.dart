import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

class LocalChatSearchSyncService {
  LocalChatSearchSyncService({
    required ChatRepository chatRepository,
    required ConversationCacheService conversationCache,
    required LocalChatSearchStore store,
    required PersonaContextLoader personaContextLoader,
  }) : _chatRepository = chatRepository,
       _conversationCache = conversationCache,
       _store = store,
       _personaContextLoader = personaContextLoader;

  final ChatRepository _chatRepository;
  final ConversationCacheService _conversationCache;
  final LocalChatSearchStore _store;
  final PersonaContextLoader _personaContextLoader;

  bool _syncing = false;
  final Map<String, DateTime> _lastSuccessfulSyncAtByNamespace =
      <String, DateTime>{};
  String? _activeNamespaceKey;
  static const _minSyncInterval = Duration(seconds: 30);

  Future<bool> sync({bool force = false}) async {
    if (_syncing) {
      return false;
    }
    final namespace = await _resolveNamespace();
    if (namespace == null) {
      return false;
    }
    _activateNamespace(namespace);
    final lastSuccessfulSyncAt =
        _lastSuccessfulSyncAtByNamespace[namespace.key];
    if (!force &&
        lastSuccessfulSyncAt != null &&
        DateTime.now().difference(lastSuccessfulSyncAt) < _minSyncInterval) {
      return false;
    }
    _syncing = true;
    try {
      await _store.ensureReady();
      final contacts = await _chatRepository.listContacts(limit: 200);
      await _store.upsertContacts(namespace: namespace, contacts: contacts);

      final timestamps = await _chatRepository.getConversationTimestamps();
      final cloudIds = <String>{};
      final localConversations = await _store.listConversationPayloads(
        namespace: namespace,
      );
      final localById = <String, Map<String, dynamic>>{
        for (final item in localConversations) _conversationId(item): item,
      };
      final needFetchIds = <String>[];

      for (final timestamp in timestamps) {
        final conversationId = _conversationId(timestamp);
        if (conversationId.isEmpty) {
          continue;
        }
        cloudIds.add(conversationId);
        final localConversation =
            _conversationCache.get(conversationId) ?? localById[conversationId];
        final cloudSettingsUpdatedAt = _firstNonEmpty(<Object?>[
          timestamp['settingsUpdatedAt'],
          timestamp['updatedAt'],
        ]);
        final cloudLastMessageAt = _firstNonEmpty(<Object?>[
          timestamp['lastMessageAt'],
          timestamp['lastMessageTime'],
        ]);
        final localSettingsUpdatedAt = _firstNonEmpty(<Object?>[
          localConversation?['settingsUpdatedAt'],
          localConversation?['updatedAt'],
        ]);
        final localLastMessageAt = _firstNonEmpty(<Object?>[
          localConversation?['lastMessageAt'],
          localConversation?['lastMessageTime'],
        ]);
        final missingConversation = localConversation == null;
        final settingsChanged =
            cloudSettingsUpdatedAt.isNotEmpty &&
            cloudSettingsUpdatedAt != localSettingsUpdatedAt;
        final messageChanged =
            cloudLastMessageAt.isNotEmpty &&
            cloudLastMessageAt != localLastMessageAt;
        if (missingConversation || settingsChanged || messageChanged) {
          needFetchIds.add(conversationId);
        } else {
          final lastSeq = await _store.lastSeqForConversation(
            namespace: namespace,
            conversationId: conversationId,
          );
          if (lastSeq <= 0) {
            needFetchIds.add(conversationId);
          }
        }
      }

      if (needFetchIds.isNotEmpty) {
        const batchSize = 40;
        for (var i = 0; i < needFetchIds.length; i += batchSize) {
          final end = i + batchSize > needFetchIds.length
              ? needFetchIds.length
              : i + batchSize;
          final batchIds = needFetchIds.sublist(i, end);
          final conversations = await _chatRepository.batchGetConversations(
            batchIds,
          );
          _conversationCache.putAll(conversations);
          await _store.upsertConversations(
            namespace: namespace,
            conversations: conversations,
          );
          for (final conversation in conversations) {
            await _syncConversationMessages(
              namespace: namespace,
              conversation: conversation,
              forceFull: true,
            );
          }
        }
      }

      for (final localId in localById.keys) {
        if (localId.isEmpty || cloudIds.contains(localId)) {
          continue;
        }
        _conversationCache.remove(localId);
        await _store.removeConversation(
          namespace: namespace,
          conversationId: localId,
        );
      }
      _lastSuccessfulSyncAtByNamespace[namespace.key] = DateTime.now();
      return true;
    } catch (_) {
      return false;
    } finally {
      _syncing = false;
    }
  }

  Future<void> syncConversation({
    required String conversationId,
    bool forceFull = false,
  }) async {
    try {
      final namespace = await _resolveNamespace();
      if (namespace == null || conversationId.trim().isEmpty) {
        return;
      }
      _activateNamespace(namespace);
      final conversation = await _chatRepository.getConversation(
        conversationId,
      );
      _conversationCache.put(conversationId, conversation);
      await _store.upsertConversations(
        namespace: namespace,
        conversations: <Map<String, dynamic>>[conversation],
      );
      await _syncConversationMessages(
        namespace: namespace,
        conversation: conversation,
        forceFull: forceFull,
      );
    } catch (_) {}
  }

  Future<void> ingestRealtimeMessage({
    required String conversationId,
    required Map<String, dynamic> payload,
  }) async {
    try {
      final namespace = await _resolveNamespace();
      if (namespace == null || conversationId.trim().isEmpty) {
        return;
      }
      _activateNamespace(namespace);
      Map<String, dynamic>? conversation = _conversationCache.get(
        conversationId,
      );
      if (conversation == null) {
        try {
          conversation = await _chatRepository.getConversation(conversationId);
          _conversationCache.put(conversationId, conversation);
          await _store.upsertConversations(
            namespace: namespace,
            conversations: <Map<String, dynamic>>[conversation],
          );
        } catch (_) {}
      }
      final mergedMessage = <String, dynamic>{
        ...payload,
        'conversationId': conversationId,
      };
      await _store.upsertMessages(
        namespace: namespace,
        messages: <Map<String, dynamic>>[mergedMessage],
        conversation: conversation,
      );
      if (conversation != null) {
        final updatedConversation = <String, dynamic>{
          ...conversation,
          'lastMessagePreview': _firstNonEmpty(<Object?>[
            payload['content'],
            payload['contentPreview'],
            conversation['lastMessagePreview'],
          ]),
          'lastMessageAt': _firstNonEmpty(<Object?>[
            payload['timestamp'],
            conversation['lastMessageAt'],
            conversation['lastMessageTime'],
          ]),
          'lastMessageTime': _firstNonEmpty(<Object?>[
            payload['timestamp'],
            conversation['lastMessageAt'],
            conversation['lastMessageTime'],
          ]),
        };
        _conversationCache.put(conversationId, updatedConversation);
        await _store.upsertConversations(
          namespace: namespace,
          conversations: <Map<String, dynamic>>[updatedConversation],
        );
      }
    } catch (_) {}
  }

  Future<void> markMessageRecalled({
    required String conversationId,
    required String messageId,
  }) async {
    final namespace = await _resolveNamespace();
    if (namespace == null || messageId.trim().isEmpty) {
      return;
    }
    _activateNamespace(namespace);
    await _store.removeMessage(namespace: namespace, messageId: messageId);
    if (conversationId.trim().isNotEmpty) {
      try {
        await syncConversation(conversationId: conversationId, forceFull: true);
      } catch (_) {}
    }
  }

  Future<void> removeConversation(String conversationId) async {
    try {
      final namespace = await _resolveNamespace();
      if (namespace == null || conversationId.trim().isEmpty) {
        return;
      }
      _activateNamespace(namespace);
      _conversationCache.remove(conversationId);
      await _store.removeConversation(
        namespace: namespace,
        conversationId: conversationId,
      );
    } catch (_) {}
  }

  Future<LocalSearchNamespace?> _resolveNamespace() async {
    try {
      final context = await _personaContextLoader();
      return LocalSearchNamespace.fromActivePersonaContext(context);
    } catch (_) {
      return null;
    }
  }

  void _activateNamespace(LocalSearchNamespace namespace) {
    if (_activeNamespaceKey == namespace.key) {
      return;
    }
    _activeNamespaceKey = namespace.key;
    _conversationCache.clear();
  }

  Future<void> _syncConversationMessages({
    required LocalSearchNamespace namespace,
    required Map<String, dynamic> conversation,
    required bool forceFull,
  }) async {
    final conversationId = _conversationId(conversation);
    if (conversationId.isEmpty) {
      return;
    }
    var lastSeq = forceFull
        ? 0
        : await _store.lastSeqForConversation(
            namespace: namespace,
            conversationId: conversationId,
          );
    final aggregatedMessages = <Map<String, dynamic>>[];
    var hasMore = true;
    var guard = 0;
    while (hasMore && guard < 20) {
      guard += 1;
      final delta = await _chatRepository.syncMessages(
        conversationId: conversationId,
        lastSeq: lastSeq,
        limit: 200,
      );
      final messages = _extractMessages(delta);
      if (messages.isEmpty) {
        hasMore = false;
        break;
      }
      aggregatedMessages.addAll(messages);
      final nextSeq = _maxSeq(messages);
      if (nextSeq <= lastSeq) {
        hasMore = false;
        break;
      }
      lastSeq = nextSeq;
      hasMore = delta['hasMore'] == true;
    }
    if (aggregatedMessages.isEmpty && forceFull) {
      final fallbackMessages = await _chatRepository.listMessages(
        conversationId: conversationId,
        limit: 200,
      );
      aggregatedMessages.addAll(fallbackMessages);
    }
    if (aggregatedMessages.isEmpty) {
      return;
    }
    await _store.upsertMessages(
      namespace: namespace,
      messages: aggregatedMessages,
      conversation: conversation,
    );
  }

  List<Map<String, dynamic>> _extractMessages(Map<String, dynamic> delta) {
    final candidates = <dynamic>[
      delta['messages'],
      delta['items'],
      delta['data'],
    ];
    for (final candidate in candidates) {
      if (candidate is List) {
        return candidate
            .whereType<Map>()
            .map((item) {
              return item.cast<String, dynamic>();
            })
            .toList(growable: false);
      }
    }
    return const <Map<String, dynamic>>[];
  }

  int _maxSeq(List<Map<String, dynamic>> messages) {
    var maxSeq = 0;
    for (final message in messages) {
      final seq = (message['seq'] as num?)?.toInt() ?? 0;
      if (seq > maxSeq) {
        maxSeq = seq;
      }
    }
    return maxSeq;
  }

  String _conversationId(Map<String, dynamic>? conversation) {
    return _string(
      conversation?['conversationId'] ??
          conversation?['id'] ??
          conversation?['_id'],
    );
  }

  String _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = _string(value);
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  String _string(Object? value) {
    return value?.toString().trim() ?? '';
  }
}
