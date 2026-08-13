// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/local-search-lifecycle-and-account-isolation/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_message_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/runtime/di/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('LocalChatSearchSyncService', () {
    late Directory tempDir;
    late LocalChatSearchStore store;
    late ConversationCacheService cache;
    late ActivePersonaContextViewData currentContext;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp(
        'local_chat_search_sync_test_',
      );
      store = LocalChatSearchStore(
        databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
        databasePath: '${tempDir.path}/chat_search.db',
      );
      cache = ConversationCacheService();
      currentContext = ActivePersonaContextViewData.fallback(
        personaId: 'user_owner',
        ownerUserId: 'user_owner',
        subjectType: 'owner',
        displayName: '主账号',
        avatarUrl: '',
        contextVersion: 1,
      );
      await store.ensureReady();
    });

    tearDown(() async {
      await store.close();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('sync is throttled per namespace instead of globally', () async {
      final repo = _CountingChatRepository();
      final service = LocalChatSearchSyncService(
        contactRepository: repo.contact,
        conversationRepository: repo.conversation,
        messageRepository: repo.message,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const SilentCacheTelemetrySink(),
      );

      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(1));

      currentContext = ActivePersonaContextViewData.fallback(
        personaId: 'sub_001',
        ownerUserId: 'user_owner',
        subjectType: 'persona',
        displayName: 'Persona',
        avatarUrl: '',
        contextVersion: 2,
      );

      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(2));

      final ownerNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          personaId: 'user_owner',
          ownerUserId: 'user_owner',
          subjectType: 'owner',
          displayName: '主账号',
          avatarUrl: '',
          contextVersion: 1,
        ),
      );
      final subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      final ownerContacts = await store.searchContacts(
        namespace: ownerNamespace,
        query: 'fixture_user_friend',
      );
      final subContacts = await store.searchContacts(
        namespace: subNamespace,
        query: 'fixture_user_friend',
      );

      expect(ownerContacts, isNotEmpty);
      expect(subContacts, isNotEmpty);
    });

    test('failed sync can retry immediately without force', () async {
      final repo = _FlakyChatRepository();
      final telemetry = _RecordingCacheTelemetrySink();
      final service = LocalChatSearchSyncService(
        contactRepository: repo.contact,
        conversationRepository: repo.conversation,
        messageRepository: repo.message,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: telemetry,
      );

      expect(await service.sync(), isFalse);
      expect(
        telemetry.events,
        contains(
          predicate<Map<String, Object?>>(
            (event) =>
                event['eventName'] == 'local_chat_search_sync' &&
                event['operation'] == 'fullSync' &&
                event['result'] == 'failed' &&
                event['errorType'] == 'StateError',
          ),
        ),
      );
      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(2));

      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );
      final contacts = await store.searchContacts(
        namespace: namespace,
        query: 'fixture_user_friend',
      );
      expect(contacts, isNotEmpty);
    });

    test('markMessageRecalled removes message from local index', () async {
      final repo = _StableChatRepository();
      final service = LocalChatSearchSyncService(
        contactRepository: repo.contact,
        conversationRepository: repo.conversation,
        messageRepository: repo.message,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const SilentCacheTelemetrySink(),
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      await store.upsertConversationRecords(
        namespace: namespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(id: 'conv_1', title: '摄影讨论组', type: 'group'),
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: ConversationCacheRecord.fromCacheMap(
          const <String, dynamic>{
            'conversationId': 'conv_1',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ),
        messages: const <LocalChatSearchMessageRecord>[
          LocalChatSearchMessageRecord(
            messageId: 'msg_1',
            conversationId: 'conv_1',
            contentPreview: '讨论布光技巧',
            senderDisplayName: '小趣',
            senderPersonaId: 'u_1',
            messageType: 'text',
            seq: 1,
            timestamp: '2026-03-27T10:00:00.000Z',
          ),
        ],
      );

      expect(
        await store.searchMessages(namespace: namespace, query: '布光'),
        hasLength(1),
      );

      await service.markMessageRecalled(
        conversationId: 'conv_1',
        messageId: 'msg_1',
      );

      expect(
        await store.searchMessages(namespace: namespace, query: '布光'),
        isEmpty,
      );
      expect(repo.getConversationCalls, greaterThan(0));
    });

    test('removeConversation deletes conversation and its messages', () async {
      final repo = _StableChatRepository();
      final service = LocalChatSearchSyncService(
        contactRepository: repo.contact,
        conversationRepository: repo.conversation,
        messageRepository: repo.message,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const SilentCacheTelemetrySink(),
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      await store.upsertConversationRecords(
        namespace: namespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(id: 'conv_1', title: '摄影讨论组', type: 'group'),
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: ConversationCacheRecord.fromCacheMap(
          const <String, dynamic>{
            'conversationId': 'conv_1',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ),
        messages: const <LocalChatSearchMessageRecord>[
          LocalChatSearchMessageRecord(
            messageId: 'msg_1',
            conversationId: 'conv_1',
            contentPreview: '讨论布光技巧',
            senderDisplayName: '小趣',
            senderPersonaId: 'u_1',
            messageType: 'text',
            seq: 1,
            timestamp: '2026-03-27T10:00:00.000Z',
          ),
        ],
      );

      expect(
        await store.listConversationRecords(namespace: namespace),
        isNotEmpty,
      );
      expect(
        await store.searchMessages(namespace: namespace, query: '布光'),
        hasLength(1),
      );

      await service.removeConversation('conv_1');

      expect(
        await store.hasConversation(
          namespace: namespace,
          conversationId: 'conv_1',
        ),
        isFalse,
      );
      expect(
        await store.searchMessages(namespace: namespace, query: '布光'),
        isEmpty,
      );
    });

    test('sync removes orphan conversations beyond first 200 rows', () async {
      final repo = _EmptyTimelineChatRepository();
      final service = LocalChatSearchSyncService(
        contactRepository: repo.contact,
        conversationRepository: repo.conversation,
        messageRepository: repo.message,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const SilentCacheTelemetrySink(),
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      final orphanConversations = List<ConversationCacheRecord>.generate(205, (
        index,
      ) {
        final id = 'orphan_$index';
        return ConversationCacheRecord(
          id: id,
          title: '孤儿会话 $index',
          type: 'group',
          updatedAt: DateTime.utc(2026, 4, 23, 10, 0, index).toIso8601String(),
        );
      });
      await store.upsertConversationRecords(
        namespace: namespace,
        conversations: orphanConversations,
      );

      expect(
        await store.listConversationIds(namespace: namespace),
        hasLength(205),
      );

      expect(await service.sync(force: true), isTrue);
      expect(await store.listConversationIds(namespace: namespace), isEmpty);
    });

    test(
      'sync pages every contact then atomically removes stale contacts',
      () async {
        final repo = _PagedContactsChatRepository();
        final service = LocalChatSearchSyncService(
          contactRepository: repo.contact,
          conversationRepository: repo.conversation,
          messageRepository: repo.message,
          conversationCache: cache,
          store: store,
          personaContextLoader: () async => currentContext,
          telemetrySink: const SilentCacheTelemetrySink(),
        );
        final namespace = LocalSearchNamespace.fromActivePersonaContext(
          currentContext,
        );
        await store.upsertContacts(
          namespace: namespace,
          contacts: const <LocalChatSearchContactRecord>[
            LocalChatSearchContactRecord(
              contactId: 'stale-contact',
              displayName: 'Stale contact',
            ),
          ],
        );

        expect(await service.sync(force: true), isTrue);
        expect(repo.requestedCursors, <String?>[null, 'contacts-2']);
        expect(repo.requestedLimits, everyElement(100));
        expect(
          (await store.searchContacts(
            namespace: namespace,
            query: 'friend',
            limit: 200,
          )).map((contact) => contact.contactId),
          hasLength(100),
        );
        expect(
          (await store.searchContacts(
            namespace: namespace,
            query: 'survivor',
          )).single.contactId,
          'survivor-contact',
        );
        expect(
          await store.searchContacts(namespace: namespace, query: 'Stale'),
          isEmpty,
        );
      },
    );
  });
}

final class _ChatContactAdapter implements ChatContactRepository {
  const _ChatContactAdapter(this._delegate, {this.listContactsOverride});

  final ChatContactRepository _delegate;
  final Future<CursorPage<ChatContactRowViewData>> Function(
    String? cursor,
    int limit,
  )?
  listContactsOverride;

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = 20,
  }) {
    final override = listContactsOverride;
    return override == null
        ? _delegate.listContacts(cursor: cursor, limit: limit)
        : override(cursor, limit);
  }

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) => _delegate.listContactHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = 100,
  }) => _delegate.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );
}

final class _ChatConversationAdapter implements ChatConversationRepository {
  const _ChatConversationAdapter(
    this._delegate, {
    this.getConversationOverride,
    this.getConversationTimestampsOverride,
  });

  final ChatConversationRepository _delegate;
  final Future<ConversationViewData> Function(String conversationId)?
  getConversationOverride;
  final Future<List<ChatConversationTimestamp>> Function()?
  getConversationTimestampsOverride;

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) => _delegate.listMessageHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 20,
  }) => _delegate.listConversations(cursor: cursor, limit: limit);

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) => _delegate.createConversation(
    type: type,
    title: title,
    maxGroupSize: maxGroupSize,
    initialMemberIds: initialMemberIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<ConversationViewData> getConversation(String conversationId) {
    final override = getConversationOverride;
    return override == null
        ? _delegate.getConversation(conversationId)
        : override(conversationId);
  }

  @override
  Future<void> updateConversationTitle(String conversationId, String title) =>
      _delegate.updateConversationTitle(conversationId, title);

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) => _delegate.updateConversationSettings(
    conversationId: conversationId,
    muted: muted,
    pinned: pinned,
  );

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() {
    final override = getConversationTimestampsOverride;
    return override == null
        ? _delegate.getConversationTimestamps()
        : override();
  }

  @override
  Future<List<ConversationViewData>> batchGetConversations(List<String> ids) =>
      _delegate.batchGetConversations(ids);
}

final class _ChatMessageAdapter implements ChatMessageRepository {
  const _ChatMessageAdapter(this._delegate, {this.syncMessagesOverride});

  final ChatMessageRepository _delegate;
  final Future<ChatMessageSyncViewData> Function(
    String conversationId,
    int lastSeq,
    int limit,
  )?
  syncMessagesOverride;

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) => _delegate.listMessages(
    conversationId: conversationId,
    before: before,
    limit: limit,
  );

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) => _delegate.recallMessage(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 200,
  }) {
    final override = syncMessagesOverride;
    return override == null
        ? _delegate.syncMessages(
            conversationId: conversationId,
            lastSeq: lastSeq,
            limit: limit,
          )
        : override(conversationId, lastSeq, limit);
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) => _delegate.markAsRead(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  }) => _delegate.getReceipts(
    conversationId: conversationId,
    messageId: messageId,
  );
}

class _CountingChatRepository {
  _CountingChatRepository() {
    final facets = ChatTestFacets();
    contact = _ChatContactAdapter(
      facets.contact,
      listContactsOverride: (cursor, limit) {
        listContactsCalls += 1;
        return facets.contact.listContacts(cursor: cursor, limit: limit);
      },
    );
    conversation = facets.conversation;
    message = facets.message;
  }

  late final ChatContactRepository contact;
  late final ChatConversationRepository conversation;
  late final ChatMessageRepository message;
  int listContactsCalls = 0;
}

class _RecordingCacheTelemetrySink implements CacheTelemetrySink {
  final List<Map<String, Object?>> events = <Map<String, Object?>>[];

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    events.add(<String, Object?>{'eventName': eventName, ...attributes});
  }
}

class _FlakyChatRepository {
  _FlakyChatRepository() {
    final facets = ChatTestFacets();
    contact = _ChatContactAdapter(
      facets.contact,
      listContactsOverride: (cursor, limit) {
        listContactsCalls += 1;
        if (_shouldFail) {
          _shouldFail = false;
          throw StateError('weak network');
        }
        return facets.contact.listContacts(cursor: cursor, limit: limit);
      },
    );
    conversation = facets.conversation;
    message = facets.message;
  }

  late final ChatContactRepository contact;
  late final ChatConversationRepository conversation;
  late final ChatMessageRepository message;
  int listContactsCalls = 0;
  bool _shouldFail = true;
}

class _StableChatRepository {
  _StableChatRepository() {
    final facets = ChatTestFacets();
    contact = facets.contact;
    conversation = _ChatConversationAdapter(
      facets.conversation,
      getConversationOverride: _getConversation,
    );
    message = _ChatMessageAdapter(
      facets.message,
      syncMessagesOverride: _syncMessages,
    );
  }

  late final ChatContactRepository contact;
  late final ChatConversationRepository conversation;
  late final ChatMessageRepository message;
  int getConversationCalls = 0;

  Future<ConversationViewData> _getConversation(String id) async {
    getConversationCalls += 1;
    final timestamp = DateTime.utc(2026, 3, 27, 10);
    return ConversationViewData(
      id: id,
      title: '摄影讨论组',
      type: 'group',
      creatorId: 'creator',
      maxSeq: 0,
      memberCount: 2,
      maxGroupSize: 1000,
      receiptEnabled: true,
      lastMessageType: MessageType.text,
      messageCount: 0,
      status: 'active',
      createdAt: timestamp,
      updatedAt: timestamp,
      lastMessagePreview: '',
    );
  }

  Future<ChatMessageSyncViewData> _syncMessages(
    String conversationId,
    int lastSeq,
    int limit,
  ) async {
    return ChatMessageSyncViewData(messages: [], hasMore: false);
  }
}

class _EmptyTimelineChatRepository {
  _EmptyTimelineChatRepository() {
    final facets = ChatTestFacets();
    contact = _ChatContactAdapter(
      facets.contact,
      listContactsOverride: (cursor, limit) async =>
          const CursorPage<ChatContactRowViewData>(
            items: <ChatContactRowViewData>[],
          ),
    );
    conversation = _ChatConversationAdapter(
      facets.conversation,
      getConversationTimestampsOverride: () async =>
          const <ChatConversationTimestamp>[],
    );
    message = facets.message;
  }

  late final ChatContactRepository contact;
  late final ChatConversationRepository conversation;
  late final ChatMessageRepository message;
}

class _PagedContactsChatRepository {
  _PagedContactsChatRepository() {
    final facets = ChatTestFacets();
    contact = _ChatContactAdapter(
      facets.contact,
      listContactsOverride: _listContacts,
    );
    conversation = _ChatConversationAdapter(
      facets.conversation,
      getConversationTimestampsOverride: () async =>
          const <ChatConversationTimestamp>[],
    );
    message = facets.message;
  }

  late final ChatContactRepository contact;
  late final ChatConversationRepository conversation;
  late final ChatMessageRepository message;
  final List<String?> requestedCursors = <String?>[];
  final List<int> requestedLimits = <int>[];

  Future<CursorPage<ChatContactRowViewData>> _listContacts(
    String? cursor,
    int limit,
  ) async {
    requestedCursors.add(cursor);
    requestedLimits.add(limit);
    return switch (cursor) {
      null => CursorPage<ChatContactRowViewData>(
        items: List<ChatContactRowViewData>.generate(
          100,
          (index) => ChatContactRowViewData(
            userId: 'friend-$index',
            userHandle: 'friend_handle_$index',
            displayName: 'friend $index',
            avatarUrl: '',
            bio: '',
            metFrom: '',
            lastInteraction: '',
            relationState: 'mutual',
            source: 'mutual',
            isStarred: false,
          ),
        ),
        nextCursor: 'contacts-2',
      ),
      'contacts-2' => CursorPage<ChatContactRowViewData>(
        items: <ChatContactRowViewData>[
          ChatContactRowViewData(
            userId: 'survivor-contact',
            userHandle: 'survivor_handle',
            displayName: 'survivor',
            avatarUrl: '',
            bio: '',
            metFrom: '',
            lastInteraction: '',
            relationState: 'mutual',
            source: 'mutual',
            isStarred: false,
          ),
        ],
      ),
      _ => throw StateError('unexpected contacts cursor: $cursor'),
    };
  }
}
