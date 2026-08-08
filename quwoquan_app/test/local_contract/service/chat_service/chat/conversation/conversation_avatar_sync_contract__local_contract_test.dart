import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_search_namespace.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';

void main() {
  group('Conversation avatar cloud chain', () {
    test(
      'ConversationViewData -> cache record preserves group avatar fields',
      () {
        final dto = ConversationViewData.fromWire(
          decodeChatConversation(
            _conversationWire(const <String, Object?>{
              'id': 'conv_cloud_group',
              'conversationId': 'conv_cloud_group',
              'title': '云侧群头像',
              'avatarUrl':
                  'https://cdn.example.com/groups/conv_cloud_group.png',
              'groupAvatarVersion': 7,
              'groupAvatarSourceHash': 'members-current',
              'maxSeq': 12,
              'memberCount': 5,
              'messageCount': 12,
              'updatedAt': '2026-05-19T01:00:00Z',
            }),
          ),
        );

        final record = ConversationCacheRecord.fromConversationViewData(dto);

        expect(record.avatarUrl, dto.avatarUrl);
        expect(record.groupAvatarVersion, 7);
        expect(record.groupAvatarSourceHash, 'members-current');
        expect(record.toInboxEntry().avatarUrl, dto.avatarUrl);
        expect(record.toInboxEntry().groupAvatarVersion, 7);
      },
    );

    test(
      'avatar patch updates conversation cache and local search payload',
      () async {
        ensureSqfliteFfiInitialized();
        final namespace = LocalSearchNamespace(
          ownerUserId: 'user_owner',
          personaId: 'persona_001',
          subjectType: 'profile',
          personaContextVersion: '1',
        );
        const scope = SearchActorScope(
          ownerUserId: 'user_owner',
          personaId: 'persona_001',
          subjectType: 'profile',
          personaContextVersion: '1',
        );
        final cache = ConversationCacheService()
          ..activateNamespace(namespace.key);
        final store = LocalChatSearchStore(
          databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
          databasePath: inMemoryDatabasePath,
          databaseFactory: databaseFactoryFfi,
        );
        final initial = ConversationCacheRecord(
          id: 'conv_patch_group',
          type: 'group',
          title: '待更新群头像',
          avatarUrl: 'https://cdn.example.com/groups/old.png',
          groupAvatarVersion: 1,
          groupAvatarSourceHash: 'members-before-update',
        );
        cache.putAll(<ConversationCacheRecord>[initial]);
        await store.upsertConversationRecords(
          namespace: namespace,
          conversations: <ConversationCacheRecord>[initial],
        );
        final ConversationAvatarSearchIndex avatarIndex = store;
        await avatarIndex.ensureConversationAvatarIndexReady();
        await avatarIndex.saveConversationAvatarSyncSeq(
          scope: scope,
          syncSeq: 12,
        );

        const patch = ConversationAvatarPatch(
          avatarUrl: 'https://cdn.example.com/groups/new.png',
          groupAvatarVersion: 2,
          groupAvatarSourceHash: 'members-after-update',
        );
        cache.applyAvatarPatch('conv_patch_group', patch);
        await avatarIndex.updateConversationAvatarProjection(
          scope: scope,
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
        expect(cached?.groupAvatarSourceHash, 'members-after-update');
        expect(stored.single.avatarUrl, patch.avatarUrl);
        expect(stored.single.groupAvatarVersion, 2);
        expect(stored.single.groupAvatarSourceHash, 'members-after-update');
        expect(
          await avatarIndex.lastConversationAvatarSyncSeq(scope: scope),
          12,
        );
      },
    );

    test(
      'listInbox refresh converges stale cache and local search avatar fields',
      () async {
        ensureSqfliteFfiInitialized();
        final namespace = LocalSearchNamespace(
          ownerUserId: 'user_owner',
          personaId: 'persona_001',
          subjectType: 'profile',
          personaContextVersion: '1',
        );
        final cache = ConversationCacheService()
          ..activateNamespace(namespace.key);
        final store = LocalChatSearchStore(
          databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
          databasePath: inMemoryDatabasePath,
          databaseFactory: databaseFactoryFfi,
        );
        final stale = ConversationCacheRecord(
          id: 'conv_list_group',
          type: 'group',
          title: '列表收敛群头像',
          avatarUrl: 'https://cdn.example.com/groups/old.png',
          groupAvatarVersion: 1,
          groupAvatarSourceHash: 'members-stale',
        );
        final fresh = stale.copyWith(
          avatarUrl: 'https://cdn.example.com/groups/new.png',
          groupAvatarVersion: 3,
          groupAvatarSourceHash: 'members-fresh',
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
        expect(cached?.groupAvatarSourceHash, 'members-fresh');
        expect(storedTarget.avatarUrl, fresh.avatarUrl);
        expect(storedTarget.groupAvatarVersion, 3);
        expect(storedTarget.groupAvatarSourceHash, 'members-fresh');
      },
    );
  });
}

Map<String, Object?> _conversationWire([
  Map<String, Object?> overrides = const <String, Object?>{},
]) {
  return <String, Object?>{
    'id': 'conv_default',
    'conversationId': 'conv_default',
    'type': 'group',
    'title': '',
    'avatarUrl': '',
    'groupAvatarVersion': 0,
    'groupAvatarSourceHash': '',
    'creatorId': 'user_001',
    'circleId': '',
    'circleGroupId': '',
    'gatheringId': '',
    'gatheringSourceVersion': 0,
    'accessMode': 'active',
    'postingPolicy': 'member_chat',
    'entityId': '',
    'originType': 'direct_init',
    'maxSeq': 0,
    'memberCount': 0,
    'membersRosterRevision': 0,
    'maxGroupSize': 1000,
    'receiptEnabled': true,
    'announcement': '',
    'announcementUpdatedBy': '',
    'announcementUpdatedAt': '2026-05-19T00:00:00Z',
    'nameEditableByAdminOnly': true,
    'lastMessageId': '',
    'lastMessagePreview': '',
    'lastMessageType': 'text',
    'lastMessageTime': '2026-05-19T00:00:00Z',
    'messageCount': 0,
    'status': 'active',
    'createdAt': '2026-05-19T00:00:00Z',
    'updatedAt': '2026-05-19T00:00:00Z',
    ...overrides,
  };
}
