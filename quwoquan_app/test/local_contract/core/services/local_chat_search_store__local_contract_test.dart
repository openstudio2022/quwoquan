import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

import '../../../support/sqflite_ffi_test_support.dart';

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
        databasePath: '${tempDir.path}/chat_search.db',
      );
      namespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'user_001',
          ownerUserId: 'user_001',
          subjectType: 'owner',
          displayName: '测试用户',
          avatarUrl: '',
          personaContextVersion: 'v1',
        ),
      );
      subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'sub_001',
          ownerUserId: 'user_001',
          subjectType: 'sub_account',
          displayName: '子账号',
          avatarUrl: '',
          personaContextVersion: 'v2',
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
            displayName: '李雷',
            subtitle: '子账号联系人',
          ),
        ],
      );

      expect(
        await store.searchContacts(namespace: namespace, query: '王'),
        hasLength(1),
      );
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
