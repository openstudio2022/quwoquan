import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

void main() {
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
          profileSubjectId: 'user_001',
          ownerUserId: 'user_001',
          subAccountId: '',
          subjectType: 'owner',
          displayName: '测试用户',
          avatarUrl: '',
          personaContextVersion: 'v1',
        ),
      );
      subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          profileSubjectId: 'subject_sub_001',
          ownerUserId: 'user_001',
          subAccountId: 'sub_001',
          subjectType: 'sub_account',
          displayName: '子账号',
          avatarUrl: '',
          personaContextVersion: 'v2',
        ),
      );
      await store.ensureReady();
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('indexes message body and removes recalled message', () async {
      await store.upsertConversations(
        namespace: namespace,
        conversations: <Map<String, dynamic>>[
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
        messages: <Map<String, dynamic>>[
          <String, dynamic>{
            'messageId': 'msg_1',
            'conversationId': 'conv_1',
            'content': '今晚讨论摄影布光技巧',
            'senderDisplayName': '小趣',
            'senderProfileSubjectId': 'u_1',
            'type': 'text',
            'seq': 1,
            'timestamp': '2026-03-27T10:00:00.000Z',
          },
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
        contacts: const <Map<String, dynamic>>[
          <String, dynamic>{
            'contactId': 'u_owner_1',
            'displayName': '王芳',
            'subtitle': '主账号联系人',
          },
        ],
      );
      await store.upsertContacts(
        namespace: subNamespace,
        contacts: const <Map<String, dynamic>>[
          <String, dynamic>{
            'contactId': 'u_sub_1',
            'displayName': '李雷',
            'subtitle': '子账号联系人',
          },
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

      await store.upsertConversations(
        namespace: namespace,
        conversations: const <Map<String, dynamic>>[
          <String, dynamic>{
            'conversationId': 'conv_owner',
            'title': '摄影讨论组',
            'type': 'group',
          },
        ],
      );
      await store.upsertMessages(
        namespace: namespace,
        conversation: const <String, dynamic>{
          'conversationId': 'conv_owner',
          'title': '摄影讨论组',
          'type': 'group',
        },
        messages: const <Map<String, dynamic>>[
          <String, dynamic>{
            'messageId': 'msg_owner_1',
            'conversationId': 'conv_owner',
            'content': '今晚讨论摄影布光技巧',
            'senderDisplayName': '小趣',
            'senderProfileSubjectId': 'u_1',
            'type': 'text',
            'seq': 1,
            'timestamp': '2026-03-27T10:00:00.000Z',
          },
        ],
      );
      await store.upsertConversations(
        namespace: subNamespace,
        conversations: const <Map<String, dynamic>>[
          <String, dynamic>{
            'conversationId': 'conv_sub',
            'title': '旅行手账',
            'type': 'group',
          },
        ],
      );
      await store.upsertMessages(
        namespace: subNamespace,
        conversation: const <String, dynamic>{
          'conversationId': 'conv_sub',
          'title': '旅行手账',
          'type': 'group',
        },
        messages: const <Map<String, dynamic>>[
          <String, dynamic>{
            'messageId': 'msg_sub_1',
            'conversationId': 'conv_sub',
            'content': '本周末去西湖拍照',
            'senderDisplayName': '小趣',
            'senderProfileSubjectId': 'u_1',
            'type': 'text',
            'seq': 1,
            'timestamp': '2026-03-27T11:00:00.000Z',
          },
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
  });
}
