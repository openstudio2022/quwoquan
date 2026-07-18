import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../../support/sqflite_ffi_test_support.dart';

void main() {
  group('Conversation avatar cloud chain', () {
    test('ConversationDto -> cache record preserves group avatar fields', () {
      final dto = ConversationDto.fromMap(const <String, dynamic>{
        'id': 'conv_cloud_group',
        'type': 'group',
        'title': '云侧群头像',
        'avatarUrl': 'https://cdn.example.com/groups/conv_cloud_group.png',
        'groupAvatarVersion': 7,
        'groupAvatarSourceHash': 'members-v7',
        'creatorId': 'user_001',
        'maxSeq': 12,
        'memberCount': 5,
        'maxGroupSize': 1000,
        'receiptEnabled': true,
        'messageCount': 12,
        'status': 'active',
        'createdAt': '2026-05-19T00:00:00Z',
        'updatedAt': '2026-05-19T01:00:00Z',
      });

      final record = ConversationCacheRecord.fromConversationDto(dto);

      expect(record.avatarUrl, dto.avatarUrl);
      expect(record.groupAvatarVersion, 7);
      expect(record.groupAvatarSourceHash, 'members-v7');
      expect(record.toChatInboxDto().avatarUrl, dto.avatarUrl);
      expect(record.toChatInboxDto().groupAvatarVersion, 7);
    });

    test(
      'avatar patch updates conversation cache and local search payload',
      () async {
        ensureSqfliteFfiInitialized();
        final namespace = LocalSearchNamespace(
          ownerUserId: 'user_owner',
          subAccountId: 'persona_001',
          subjectType: 'profile',
          personaContextVersion: 'v1',
        );
        final cache = ConversationCacheService()
          ..activateNamespace(namespace.key);
        final store = LocalChatSearchStore(
          databasePath: inMemoryDatabasePath,
          databaseFactory: databaseFactoryFfi,
        );
        final initial = ConversationCacheRecord(
          id: 'conv_patch_group',
          type: 'group',
          title: '待更新群头像',
          avatarUrl: 'https://cdn.example.com/groups/old.png',
          groupAvatarVersion: 1,
          groupAvatarSourceHash: 'members-v1',
        );
        cache.putAll(<ConversationCacheRecord>[initial]);
        await store.upsertConversationRecords(
          namespace: namespace,
          conversations: <ConversationCacheRecord>[initial],
        );

        const patch = ConversationAvatarPatch(
          avatarUrl: 'https://cdn.example.com/groups/new.png',
          groupAvatarVersion: 2,
          groupAvatarSourceHash: 'members-v2',
        );
        cache.applyAvatarPatch('conv_patch_group', patch);
        await store.updateConversationAvatar(
          namespace: namespace,
          conversationId: 'conv_patch_group',
          avatarUrl: patch.avatarUrl,
          groupAvatarVersion: patch.groupAvatarVersion,
          groupAvatarSourceHash: patch.groupAvatarSourceHash,
        );

        final cached = cache.get('conv_patch_group');
        final stored = await store.listConversationRecords(
          namespace: namespace,
        );

        expect(cached?.avatarUrl, patch.avatarUrl);
        expect(cached?.groupAvatarVersion, 2);
        expect(cached?.groupAvatarSourceHash, 'members-v2');
        expect(stored.single.avatarUrl, patch.avatarUrl);
        expect(stored.single.groupAvatarVersion, 2);
        expect(stored.single.groupAvatarSourceHash, 'members-v2');
      },
    );

    test(
      'listInbox refresh converges stale cache and local search avatar fields',
      () async {
        ensureSqfliteFfiInitialized();
        final namespace = LocalSearchNamespace(
          ownerUserId: 'user_owner',
          subAccountId: 'persona_001',
          subjectType: 'profile',
          personaContextVersion: 'v1',
        );
        final cache = ConversationCacheService()
          ..activateNamespace(namespace.key);
        final store = LocalChatSearchStore(
          databasePath: inMemoryDatabasePath,
          databaseFactory: databaseFactoryFfi,
        );
        final stale = ConversationCacheRecord(
          id: 'conv_list_group',
          type: 'group',
          title: '列表收敛群头像',
          avatarUrl: 'https://cdn.example.com/groups/old.png',
          groupAvatarVersion: 1,
          groupAvatarSourceHash: 'members-v1',
        );
        final fresh = stale.copyWith(
          avatarUrl: 'https://cdn.example.com/groups/new.png',
          groupAvatarVersion: 3,
          groupAvatarSourceHash: 'members-v3',
        );
        cache.put(stale);
        await store.upsertConversationRecords(
          namespace: namespace,
          conversations: <ConversationCacheRecord>[stale],
        );

        cache.putAll(<ConversationCacheRecord>[fresh]);
        await store.upsertConversationRecords(
          namespace: namespace,
          conversations: <ConversationCacheRecord>[fresh],
        );

        final cached = cache.get('conv_list_group');
        final stored = await store.listConversationRecords(
          namespace: namespace,
        );
        final storedTarget = stored.firstWhere(
          (record) => record.id == 'conv_list_group',
        );

        expect(cached?.avatarUrl, fresh.avatarUrl);
        expect(cached?.groupAvatarVersion, 3);
        expect(cached?.groupAvatarSourceHash, 'members-v3');
        expect(storedTarget.avatarUrl, fresh.avatarUrl);
        expect(storedTarget.groupAvatarVersion, 3);
        expect(storedTarget.groupAvatarSourceHash, 'members-v3');
      },
    );
  });
}
