import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
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
      final contactDtos = await _chatRepository.listContacts(limit: 200);
      await _store.upsertContacts(
        namespace: namespace,
        contacts: contactDtos
            .map((c) => Map<String, Object?>.from(c.toMap()))
            .toList(growable: false),
      );

      final timestamps = await _chatRepository.getConversationTimestamps();
      final cloudIds = <String>{};
      final localConversations = await _store.listConversationRecords(
        namespace: namespace,
        limit: null,
      );
      final localConversationIds = await _store.listConversationIds(
        namespace: namespace,
      );
      final localById = <String, ConversationCacheRecord>{
        for (final item in localConversations) item.id: item,
      };
      final needFetchIds = <String>[];
      final needIncrementalMessageSyncIds = <String>[];

      for (final timestamp in timestamps) {
        final conversationId = timestamp.conversationId.trim();
        if (conversationId.isEmpty) {
          continue;
        }
        cloudIds.add(conversationId);
        final localConversation =
            _conversationCache.get(conversationId) ?? localById[conversationId];
        final cloudSettingsUpdatedAt = _firstNonEmpty(<Object?>[
          timestamp.settingsUpdatedAt,
          timestamp.updatedAt,
        ]);
        final cloudLastMessageAt = _firstNonEmpty(<Object?>[
          timestamp.lastMessageAt,
          timestamp.lastMessageTime,
        ]);
        final localSettingsUpdatedAt =
            localConversation?.settingsTimestamp ?? '';
        final localLastMessageAt = localConversation?.messageTimestamp ?? '';
        final missingConversation = localConversation == null;
        final settingsChanged =
            cloudSettingsUpdatedAt.isNotEmpty &&
            cloudSettingsUpdatedAt != localSettingsUpdatedAt;
        final messageChanged =
            cloudLastMessageAt.isNotEmpty &&
            cloudLastMessageAt != localLastMessageAt;
        if (missingConversation || settingsChanged) {
          needFetchIds.add(conversationId);
        } else if (messageChanged) {
          _conversationCache.applyListPatch(
            conversationId,
            ConversationListPatch(
              lastMessagePreview: timestamp.lastMessagePreview,
              lastMessageAt: cloudLastMessageAt,
              unreadCount: timestamp.unreadCount,
            ),
          );
          needIncrementalMessageSyncIds.add(conversationId);
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
          final records = conversations
              .map(ConversationCacheRecord.fromConversationDto)
              .toList(growable: false);
          _conversationCache.putAll(records);
          await _store.upsertConversationRecords(
            namespace: namespace,
            conversations: records,
          );
          for (final conversation in records) {
            await _syncConversationMessages(
              namespace: namespace,
              conversation: conversation,
              forceFull: true,
            );
          }
        }
      }

      for (final conversationId in needIncrementalMessageSyncIds.toSet()) {
        final conversation =
            _conversationCache.get(conversationId) ?? localById[conversationId];
        if (conversation == null) {
          continue;
        }
        await _syncConversationMessages(
          namespace: namespace,
          conversation: conversation,
          forceFull: false,
        );
      }

      for (final localId in localConversationIds) {
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
      final conversationDto = await _chatRepository.getConversation(
        conversationId,
      );
      final conversation = ConversationCacheRecord.fromConversationDto(
        conversationDto,
      );
      _conversationCache.put(conversation);
      await _store.upsertConversationRecords(
        namespace: namespace,
        conversations: <ConversationCacheRecord>[conversation],
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
    required MessageDto message,
  }) async {
    try {
      final namespace = await _resolveNamespace();
      if (namespace == null || conversationId.trim().isEmpty) {
        return;
      }
      _activateNamespace(namespace);
      ConversationCacheRecord? conversation = _conversationCache.get(
        conversationId,
      );
      if (conversation == null) {
        try {
          final dto = await _chatRepository.getConversation(conversationId);
          conversation = ConversationCacheRecord.fromConversationDto(dto);
          _conversationCache.put(conversation);
          await _store.upsertConversationRecords(
            namespace: namespace,
            conversations: <ConversationCacheRecord>[conversation],
          );
        } catch (_) {}
      }
      final messageRecord = LocalChatSearchMessageRecord.fromMessageDto(
        message,
        conversation: conversation,
      );
      await _store.upsertMessages(
        namespace: namespace,
        messages: <LocalChatSearchMessageRecord>[messageRecord],
        conversation: conversation,
      );
      if (conversation != null) {
        final updatedConversation = conversation.copyWith(
          lastMessagePreview: _firstNonEmpty(<Object?>[
            message.content,
            conversation.lastMessagePreview,
          ]),
          lastMessageAt: _firstNonEmpty(<Object?>[
            message.timestamp?.toIso8601String(),
            conversation.lastMessageAt,
          ]),
        );
        _conversationCache.put(updatedConversation);
        await _store.upsertConversationRecords(
          namespace: namespace,
          conversations: <ConversationCacheRecord>[updatedConversation],
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
    _conversationCache.activateNamespace(namespace.key);
  }

  Future<void> _syncConversationMessages({
    required LocalSearchNamespace namespace,
    required ConversationCacheRecord conversation,
    required bool forceFull,
  }) async {
    final conversationId = conversation.id;
    if (conversationId.isEmpty) {
      return;
    }
    var lastSeq = forceFull
        ? 0
        : await _store.lastSeqForConversation(
            namespace: namespace,
            conversationId: conversationId,
          );
    final aggregatedMessages = <LocalChatSearchMessageRecord>[];
    var hasMore = true;
    var guard = 0;
    while (hasMore && guard < 20) {
      guard += 1;
      final delta = await _chatRepository.syncMessages(
        conversationId: conversationId,
        lastSeq: lastSeq,
        limit: 200,
      );
      final messages = delta.messages
          .map(
            (message) => LocalChatSearchMessageRecord.fromMessageDto(
              message,
              conversation: conversation,
            ),
          )
          .toList(growable: false);
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
      hasMore = delta.hasMore;
    }
    if (aggregatedMessages.isEmpty && forceFull) {
      final fallbackMessages = await _chatRepository.listMessages(
        conversationId: conversationId,
        limit: 200,
      );
      aggregatedMessages.addAll(
        fallbackMessages.map(
          (message) => LocalChatSearchMessageRecord.fromMessageDto(
            message,
            conversation: conversation,
          ),
        ),
      );
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

  int _maxSeq(List<LocalChatSearchMessageRecord> messages) {
    var maxSeq = 0;
    for (final message in messages) {
      final seq = message.seq;
      if (seq > maxSeq) {
        maxSeq = seq;
      }
    }
    return maxSeq;
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
