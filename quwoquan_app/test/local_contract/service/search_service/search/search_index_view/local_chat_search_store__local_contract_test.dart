// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/local-search-lifecycle-and-account-isolation/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_message_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_search_namespace.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('LocalChatSearchStore', () {
    late Directory tempDir;
    late LocalChatSearchStore store;
    late LocalSearchNamespace namespace;
    late LocalSearchNamespace subNamespace;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('local_chat_store_test_');
      store = LocalChatSearchStore(
        databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
        databasePath: '${tempDir.path}/chat_search.db',
      );
      namespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          personaId: 'user_001',
          ownerUserId: 'user_001',
          subjectType: 'owner',
          displayName: '测试用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      );
      subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          personaId: 'sub_001',
          ownerUserId: 'user_001',
          subjectType: 'persona',
          displayName: 'Persona',
          avatarUrl: '',
          contextVersion: 2,
        ),
      );
      await store.ensureReady();
    });

    tearDown(() async {
      await store.close();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('indexes message body and removes recalled message', () async {
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
        messages: <LocalChatSearchMessageRecord>[
          const LocalChatSearchMessageRecord(
            messageId: 'msg_1',
            conversationId: 'conv_1',
            contentPreview: '今晚讨论摄影布光技巧',
            senderDisplayName: '小趣',
            senderPersonaId: 'u_1',
            messageType: 'text',
            seq: 1,
            timestamp: '2026-03-27T10:00:00.000Z',
          ),
        ],
      );

      final beforeRecall = await store.searchMessages(
        namespace: namespace,
        query: '布光',
      );
      expect(beforeRecall, hasLength(1));

      await store.removeMessage(namespace: namespace, messageId: 'msg_1');

      final afterRecall = await store.searchMessages(
        namespace: namespace,
        query: '布光',
      );
      expect(afterRecall, isEmpty);
    });

    test('isolates contacts and messages by namespace', () async {
      await store.upsertContacts(
        namespace: namespace,
        contacts: const <LocalChatSearchContactRecord>[
          LocalChatSearchContactRecord(
            contactId: 'u_owner_1',
            userHandle: 'owner_friend',
            displayName: '王芳',
            subtitle: '主账号联系人',
          ),
        ],
      );
      await store.upsertContacts(
        namespace: subNamespace,
        contacts: const <LocalChatSearchContactRecord>[
          LocalChatSearchContactRecord(
            contactId: 'u_sub_1',
            userHandle: 'persona_friend',
            displayName: '李雷',
            subtitle: 'Persona联系人',
          ),
        ],
      );

      final ownerContacts = await store.searchContacts(
        namespace: namespace,
        query: '王',
      );
      expect(ownerContacts, hasLength(1));
      expect(ownerContacts.single.userHandle, 'owner_friend');
      expect(
        await store.searchContacts(namespace: subNamespace, query: '王'),
        isEmpty,
      );

      await store.upsertConversationRecords(
        namespace: namespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(
            id: 'conv_owner',
            title: '摄影讨论组',
            type: 'group',
          ),
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: ConversationCacheRecord.fromCacheMap(
          const <String, dynamic>{
            'conversationId': 'conv_owner',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ),
        messages: const <LocalChatSearchMessageRecord>[
          LocalChatSearchMessageRecord(
            messageId: 'msg_owner_1',
            conversationId: 'conv_owner',
            contentPreview: '今晚讨论摄影布光技巧',
            senderDisplayName: '小趣',
            senderPersonaId: 'u_1',
            messageType: 'text',
            seq: 1,
            timestamp: '2026-03-27T10:00:00.000Z',
          ),
        ],
      );
      await store.upsertConversationRecords(
        namespace: subNamespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(id: 'conv_sub', title: '旅行手账', type: 'group'),
        ],
      );
      await store.upsertMessages(
        namespace: subNamespace,
        conversation: ConversationCacheRecord.fromCacheMap(
          const <String, dynamic>{
            'conversationId': 'conv_sub',
            'title': '旅行手账',
            'type': 'group',
          },
        ),
        messages: const <LocalChatSearchMessageRecord>[
          LocalChatSearchMessageRecord(
            messageId: 'msg_sub_1',
            conversationId: 'conv_sub',
            contentPreview: '本周末去西湖拍照',
            senderDisplayName: '小趣',
            senderPersonaId: 'u_1',
            messageType: 'text',
            seq: 1,
            timestamp: '2026-03-27T11:00:00.000Z',
          ),
        ],
      );

      expect(
        await store.searchMessages(namespace: namespace, query: '布光'),
        hasLength(1),
      );
      expect(
        await store.searchMessages(namespace: subNamespace, query: '布光'),
        isEmpty,
      );
    });

    test(
      'timeline read preserves canonical payload and beforeSeq order',
      () async {
        final messages = <ChatMessageViewData>[
          for (var seq = 1; seq <= 3; seq += 1)
            ChatMessageViewData(
              id: 'timeline_$seq',
              conversationId: 'conv_timeline',
              seq: seq,
              clientMsgId: 'client_$seq',
              senderId: 'persona_timeline',
              senderName: '旅行摄影师',
              type: seq == 3 ? 'image' : 'text',
              content: '消息 $seq',
              mediaAssetId: seq == 3 ? 'asset_3' : null,
              mediaDeliveryUrl: seq == 3
                  ? 'https://cdn.example.com/timeline_3.jpg'
                  : null,
              mediaType: seq == 3 ? 'image' : null,
              mediaContentType: seq == 3 ? 'image/jpeg' : null,
              status: 'sent',
              timestamp: DateTime.utc(2026, 7, 31, 10, seq),
            ),
        ];
        await store.upsertMessages(
          namespace: namespace,
          messages: messages
              .map(LocalChatSearchMessageRecord.fromMessageViewData)
              .toList(growable: false),
        );

        final latest = await store.readTimeline(
          namespace: namespace,
          conversationId: 'conv_timeline',
          limit: 2,
        );
        expect(latest.source, CacheReadSource.disk);
        expect(latest.value.map((item) => item.seq), <int>[2, 3]);
        expect(latest.value.last.mediaAssetId, 'asset_3');
        expect(latest.value.last.mediaContentType, 'image/jpeg');

        final older = await store.readTimeline(
          namespace: namespace,
          conversationId: 'conv_timeline',
          beforeSeq: 2,
          limit: 2,
        );
        expect(older.value.map((item) => item.seq), <int>[1]);
      },
    );

    test('账号 closed 终态物理清除全部 namespace', () async {
      await store.upsertConversationRecords(
        namespace: namespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(id: 'conv_owner_terminal', title: '主账号会话'),
        ],
      );
      await store.upsertConversationRecords(
        namespace: subNamespace,
        conversations: const <ConversationCacheRecord>[
          ConversationCacheRecord(
            id: 'conv_persona_terminal',
            title: 'Persona 会话',
          ),
        ],
      );

      await store.clearAllNamespaces();

      expect(
        await store.listConversationRecords(namespace: namespace),
        isEmpty,
      );
      expect(
        await store.listConversationRecords(namespace: subNamespace),
        isEmpty,
      );
    });

    test('current message projection codec rejects retired wire keys', () {
      const record = LocalChatSearchMessageRecord(
        messageId: 'msg_projection_1',
        conversationId: 'conv_projection_1',
        senderPersonaId: 'persona_1',
        messageType: 'text',
        contentPreview: 'typed projection',
        seq: 7,
        timestamp: '2026-07-16T00:00:00.000Z',
      );

      expect(
        LocalChatSearchMessageRecord.fromProjectionMap(
          record.toProjectionMap(),
        ).senderPersonaId,
        'persona_1',
      );
      expect(
        () => LocalChatSearchMessageRecord.fromProjectionMap(<String, dynamic>{
          ...record.toProjectionMap(),
          'senderSub'
                  'AccountId':
              'retired-persona-key',
        }),
        throwsFormatException,
      );
    });

    test('conversation cache codec only accepts conversationId', () {
      const canonical = <String, dynamic>{
        'conversationId': 'conv_cache_1',
        'type': 'group',
      };
      final record = ConversationCacheRecord.fromCacheMap(canonical);

      expect(record.id, 'conv_cache_1');
      expect(record.toCacheMap()['conversationId'], 'conv_cache_1');
      expect(record.toCacheMap().containsKey('id'), isFalse);
      expect(record.toCacheMap().containsKey('_id'), isFalse);
      expect(record.lastMessageType.wireName, 'text');
      expect(
        () => ConversationCacheRecord.fromCacheMap(const <String, dynamic>{
          'conversationId': 'conv_cache_retired_type',
          'lastMessageType': 'voice',
        }),
        throwsFormatException,
      );
      expect(
        () => ConversationCacheRecord.fromCacheMap(const <String, dynamic>{
          'id': 'retired-id',
        }),
        throwsFormatException,
      );
      expect(
        () => ConversationCacheRecord.fromCacheMap(const <String, dynamic>{
          '_id': 'retired-storage-id',
        }),
        throwsFormatException,
      );
    });
  });
}
