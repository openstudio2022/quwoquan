// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/local-search-lifecycle-and-account-isolation/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

import '../../../support/sqflite_ffi_test_support.dart';

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
        chatRepository: repo,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const NoopCacheTelemetrySink(),
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
        chatRepository: repo,
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
        chatRepository: repo,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const NoopCacheTelemetrySink(),
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
      final service = LocalChatSearchSyncService(
        chatRepository: _StableChatRepository(),
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const NoopCacheTelemetrySink(),
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
      final service = LocalChatSearchSyncService(
        chatRepository: _EmptyTimelineChatRepository(),
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
        telemetrySink: const NoopCacheTelemetrySink(),
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
          chatRepository: repo,
          conversationCache: cache,
          store: store,
          personaContextLoader: () async => currentContext,
          telemetrySink: const NoopCacheTelemetrySink(),
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

class _CountingChatRepository extends MockChatRepository {
  int listContactsCalls = 0;

  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    listContactsCalls += 1;
    return super.listContacts(cursor: cursor, limit: limit);
  }
}

class _RecordingCacheTelemetrySink implements CacheTelemetrySink {
  final List<Map<String, Object?>> events = <Map<String, Object?>>[];

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    events.add(<String, Object?>{'eventName': eventName, ...attributes});
  }
}

class _FlakyChatRepository extends MockChatRepository {
  int listContactsCalls = 0;
  bool _shouldFail = true;

  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    listContactsCalls += 1;
    if (_shouldFail) {
      _shouldFail = false;
      throw StateError('weak network');
    }
    return super.listContacts(cursor: cursor, limit: limit);
  }
}

class _StableChatRepository extends MockChatRepository {
  int getConversationCalls = 0;

  @override
  Future<ConversationDto> getConversation(String id) async {
    getConversationCalls += 1;
    return ConversationDto.fromMap(<String, dynamic>{
      'id': id,
      'title': '摄影讨论组',
      'type': 'group',
      'creatorId': 'creator',
      'maxSeq': 0,
      'memberCount': 2,
      'maxGroupSize': 1000,
      'receiptEnabled': true,
      'messageCount': 0,
      'status': 'active',
      'createdAt': '2026-03-27T10:00:00.000Z',
      'updatedAt': '2026-03-27T10:00:00.000Z',
      'lastMessagePreview': '',
    });
  }

  @override
  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 200,
  }) async {
    return const SyncResponse(messages: [], hasMore: false);
  }
}

class _EmptyTimelineChatRepository extends MockChatRepository {
  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return const CursorPage<ChatContactRowDto>(items: <ChatContactRowDto>[]);
  }

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    return const <ChatConversationTimestampDto>[];
  }
}

class _PagedContactsChatRepository extends MockChatRepository {
  final List<String?> requestedCursors = <String?>[];
  final List<int> requestedLimits = <int>[];

  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    requestedCursors.add(cursor);
    requestedLimits.add(limit);
    return switch (cursor) {
      null => CursorPage<ChatContactRowDto>(
        items: List<ChatContactRowDto>.generate(
          100,
          (index) => ChatContactRowDto(
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
      'contacts-2' => CursorPage<ChatContactRowDto>(
        items: <ChatContactRowDto>[
          ChatContactRowDto(
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

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    return const <ChatConversationTimestampDto>[];
  }
}
