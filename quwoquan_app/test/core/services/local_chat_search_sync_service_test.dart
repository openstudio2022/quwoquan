import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

void main() {
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
        profileSubjectId: 'user_owner',
        ownerUserId: 'user_owner',
        subAccountId: '',
        subjectType: 'owner',
        displayName: '主账号',
        avatarUrl: '',
        personaContextVersion: 'v1',
      );
      await store.ensureReady();
    });

    tearDown(() async {
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
      );

      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(1));

      currentContext = ActivePersonaContextViewData.fallback(
        profileSubjectId: 'subject_sub_001',
        ownerUserId: 'user_owner',
        subAccountId: 'sub_001',
        subjectType: 'sub_account',
        displayName: '子账号',
        avatarUrl: '',
        personaContextVersion: 'v2',
      );

      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(2));

      final ownerNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          profileSubjectId: 'user_owner',
          ownerUserId: 'user_owner',
          subAccountId: '',
          subjectType: 'owner',
          displayName: '主账号',
          avatarUrl: '',
          personaContextVersion: 'v1',
        ),
      );
      final subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      final ownerContacts = await store.searchContacts(
        namespace: ownerNamespace,
        query: '李',
      );
      final subContacts = await store.searchContacts(
        namespace: subNamespace,
        query: '李',
      );

      expect(ownerContacts, isNotEmpty);
      expect(subContacts, isNotEmpty);
    });

    test('failed sync can retry immediately without force', () async {
      final repo = _FlakyChatRepository();
      final service = LocalChatSearchSyncService(
        chatRepository: repo,
        conversationCache: cache,
        store: store,
        personaContextLoader: () async => currentContext,
      );

      expect(await service.sync(), isFalse);
      expect(await service.sync(), isTrue);
      expect(repo.listContactsCalls, equals(2));

      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );
      final contacts = await store.searchContacts(
        namespace: namespace,
        query: '李',
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
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      await store.upsertConversations(
        namespace: namespace,
        conversations: const <Map<String, dynamic>>[
          <String, dynamic>{
            'conversationId': 'conv_1',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: const <String, dynamic>{
          'conversationId': 'conv_1',
          'title': '摄影讨论组',
          'type': 'group',
        },
        messages: const <Map<String, dynamic>>[
          <String, dynamic>{
            'messageId': 'msg_1',
            'conversationId': 'conv_1',
            'content': '讨论布光技巧',
            'senderDisplayName': '小趣',
            'senderProfileSubjectId': 'u_1',
            'type': 'text',
            'seq': 1,
            'timestamp': '2026-03-27T10:00:00.000Z',
          },
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
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      await store.upsertConversations(
        namespace: namespace,
        conversations: const <Map<String, dynamic>>[
          <String, dynamic>{
            'conversationId': 'conv_1',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: const <String, dynamic>{
          'conversationId': 'conv_1',
          'title': '摄影讨论组',
          'type': 'group',
        },
        messages: const <Map<String, dynamic>>[
          <String, dynamic>{
            'messageId': 'msg_1',
            'conversationId': 'conv_1',
            'content': '讨论布光技巧',
            'senderDisplayName': '小趣',
            'senderProfileSubjectId': 'u_1',
            'type': 'text',
            'seq': 1,
            'timestamp': '2026-03-27T10:00:00.000Z',
          },
        ],
      );

      expect(
        await store.listConversationPayloads(namespace: namespace),
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
      );
      final namespace = LocalSearchNamespace.fromActivePersonaContext(
        currentContext,
      );

      final orphanConversations = List<Map<String, dynamic>>.generate(205, (
        index,
      ) {
        final id = 'orphan_$index';
        return <String, dynamic>{
          'conversationId': id,
          'id': id,
          '_id': id,
          'title': '孤儿会话 $index',
          'type': 'group',
          'updatedAt': DateTime.utc(
            2026,
            4,
            23,
            10,
            0,
            index,
          ).toIso8601String(),
        };
      });
      await store.upsertConversations(
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
  });
}

class _CountingChatRepository extends MockChatRepository {
  int listContactsCalls = 0;

  @override
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    listContactsCalls += 1;
    return super.listContacts(cursor: cursor, limit: limit);
  }
}

class _FlakyChatRepository extends MockChatRepository {
  int listContactsCalls = 0;
  bool _shouldFail = true;

  @override
  Future<List<ChatContactRowDto>> listContacts({
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
      '_id': id,
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
      'lastMessageAt': '2026-03-27T10:00:00.000Z',
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
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return const <ChatContactRowDto>[];
  }

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    return const <ChatConversationTimestampDto>[];
  }
}
