// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_sync_repository.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ConversationAvatarSyncPatchPayload,
        UserAvatarSyncPatchPayload,
        PullUserSyncSlice,
        UserSyncPatch,
        UserSyncPatchKind;

import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';

class _FakeUserSyncRepository implements UserSyncRepository {
  @override
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    if (afterSeq >= 1) {
      return PullUserSyncSlice(
        patches: <UserSyncPatch>[],
        latestSyncSeq: 1,
        hasMore: false,
        requiresResync: false,
      );
    }
    return PullUserSyncSlice(
      patches: <UserSyncPatch>[
        UserSyncPatch(
          syncSeq: 1,
          kind: UserSyncPatchKind.conversationAvatarUpdated,
          conversationAvatarUpdated: ConversationAvatarSyncPatchPayload(
            conversationId: 'conv_001',
            avatarUrl: 'https://cdn.example.com/group.png?v=2',
            groupAvatarVersion: 2,
          ),
          occurredAt: DateTime.utc(2026, 4, 23, 10),
        ),
      ],
      latestSyncSeq: 1,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _GapUserSyncRepository implements UserSyncRepository {
  @override
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    return PullUserSyncSlice(
      patches: <UserSyncPatch>[],
      latestSyncSeq: 3,
      hasMore: false,
      requiresResync: true,
    );
  }
}

class _InvalidAvatarPatchRepository implements UserSyncRepository {
  @override
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    return PullUserSyncSlice(
      patches: <UserSyncPatch>[
        UserSyncPatch(
          syncSeq: 4,
          kind: UserSyncPatchKind.conversationAvatarUpdated,
          conversationAvatarUpdated: ConversationAvatarSyncPatchPayload(
            conversationId: 'conv_001',
            avatarUrl: '',
            groupAvatarVersion: 4,
          ),
          occurredAt: DateTime.utc(2026, 4, 23, 10),
        ),
      ],
      latestSyncSeq: 4,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _UserAvatarPatchRepository implements UserSyncRepository {
  @override
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    if (afterSeq >= 2) {
      return PullUserSyncSlice(
        patches: <UserSyncPatch>[],
        latestSyncSeq: 2,
        hasMore: false,
        requiresResync: false,
      );
    }
    return PullUserSyncSlice(
      patches: <UserSyncPatch>[
        UserSyncPatch(
          syncSeq: 2,
          kind: UserSyncPatchKind.userAvatarUpdated,
          userAvatarUpdated: UserAvatarSyncPatchPayload(
            userId: 'user_002',
            avatarUrl:
                'media/avatar/s/archived-avatar/user/user_002/v1/profile.png',
            avatarVersion: 14,
          ),
          occurredAt: DateTime.utc(2026, 4, 23, 10),
        ),
      ],
      latestSyncSeq: 2,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _CountingUserSyncRepository implements UserSyncRepository {
  int pullCount = 0;

  @override
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    pullCount += 1;
    return PullUserSyncSlice(
      patches: <UserSyncPatch>[],
      latestSyncSeq: 3,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _ResyncChatRepository extends MockChatRepository {
  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() async {
    final timestamp = DateTime.utc(2026, 4, 23, 10);
    return <ChatConversationTimestamp>[
      ChatConversationTimestamp(
        conversationId: 'conv_001',
        type: 'group',
        updatedAt: timestamp,
        settingsUpdatedAt: timestamp,
        lastMessageAt: timestamp,
        lastMessageTime: timestamp,
        lastMessagePreview: '',
        unreadCount: 0,
      ),
    ];
  }

  @override
  Future<List<ConversationViewData>> batchGetConversations(
    List<String> ids,
  ) async {
    final createdAt = DateTime.utc(2026, 4, 23, 9);
    final updatedAt = DateTime.utc(2026, 4, 23, 10);
    return <ConversationViewData>[
      ConversationViewData(
        id: 'conv_001',
        type: 'group',
        title: '群聊',
        avatarUrl: 'https://cdn.example.com/full-sync.png?v=3',
        groupAvatarVersion: 3,
        creatorId: 'user_001',
        maxSeq: 0,
        memberCount: 3,
        maxGroupSize: 500,
        receiptEnabled: true,
        lastMessageType: MessageType.text,
        messageCount: 0,
        status: 'active',
        createdAt: createdAt,
        updatedAt: updatedAt,
      ),
    ];
  }
}

class _FakeLocalChatSearchStore extends LocalChatSearchStore {
  _FakeLocalChatSearchStore()
    : super(
        databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      );

  final Map<String, ConversationCacheRecord> _conversations =
      <String, ConversationCacheRecord>{};
  int _lastUserSyncSeq = 0;
  String? lastContactAvatarUserId;
  String? lastContactAvatarUrl;
  int? lastContactAvatarVersion;

  void seedConversation(Map<String, dynamic> conversation) {
    final record = ConversationCacheRecord.fromCacheMap(conversation);
    final id = record.id;
    if (id.isEmpty) {
      return;
    }
    _conversations[id] = record;
  }

  @override
  Future<void> ensureReady() async {}

  @override
  Future<int> lastUserSyncSeq({required LocalSearchNamespace namespace}) async {
    return _lastUserSyncSeq;
  }

  @override
  Future<void> saveUserSyncSeq({
    required LocalSearchNamespace namespace,
    required int syncSeq,
  }) async {
    _lastUserSyncSeq = syncSeq;
  }

  @override
  Future<void> updateConversationAvatar({
    required LocalSearchNamespace namespace,
    required String conversationId,
    required String avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
    bool propagateToMessages = false,
  }) async {
    final existing = _conversations[conversationId];
    if (existing == null) {
      return;
    }
    _conversations[conversationId] = existing.copyWith(
      avatarUrl: avatarUrl,
      groupAvatarVersion: groupAvatarVersion,
      groupAvatarSourceHash: groupAvatarSourceHash,
    );
  }

  @override
  Future<void> updateContactAvatar({
    required LocalSearchNamespace namespace,
    required String userId,
    required String avatarUrl,
    int? avatarVersion,
  }) async {
    lastContactAvatarUserId = userId;
    lastContactAvatarUrl = avatarUrl;
    lastContactAvatarVersion = avatarVersion;
  }

  @override
  Future<List<ConversationCacheRecord>> listConversationRecords({
    required LocalSearchNamespace namespace,
    int? limit = 200,
  }) async {
    return _conversations.values.toList(growable: false);
  }
}

void main() {
  testWidgets('sync_hint 触发 patch 拉取并更新本地头像缓存', (tester) async {
    final store = _FakeLocalChatSearchStore();
    final namespace = LocalSearchNamespace.fromActivePersonaContext(
      ActivePersonaContextViewData.fallback(
        personaId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'title': '群聊',
      'type': 'group',
      'groupAvatarVersion': 1,
      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
      'updatedAt': DateTime.now().toIso8601String(),
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userSyncRepositoryProvider.overrideWithValue(
            _FakeUserSyncRepository(),
          ),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '测试用户',
              avatarUrl: '',
            ),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ref
                  .read(conversationCacheProvider)
                  .put(
                    ConversationCacheRecord.fromCacheMap(<String, dynamic>{
                      'conversationId': 'conv_001',
                      'type': 'group',
                      'title': '群聊',
                      'groupAvatarVersion': 1,
                      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                    }),
                  );
              RealtimeMessageHandler(ref.read).handle(<String, dynamic>{
                'type': 'sync_hint',
                'latestSyncSeq': 1,
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final container = ProviderScope.containerOf(
      tester.element(find.byType(SizedBox)),
    );
    final cache = container.read(conversationCacheProvider);
    expect(
      cache.get('conv_001')?.avatarUrl,
      'https://cdn.example.com/group.png?v=2',
    );
    expect(cache.get('conv_001')?.groupAvatarVersion, 2);

    final stored = await store.listConversationRecords(namespace: namespace);
    expect(stored.single.avatarUrl, 'https://cdn.example.com/group.png?v=2');
    expect(stored.single.groupAvatarVersion, 2);
  });

  testWidgets('UserAvatarUpdated patch 把 avatarVersion 传入联系人头像缓存更新', (
    tester,
  ) async {
    final store = _FakeLocalChatSearchStore();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userSyncRepositoryProvider.overrideWithValue(
            _UserAvatarPatchRepository(),
          ),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '测试用户',
              avatarUrl: '',
            ),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle(<String, dynamic>{
                'type': 'UserAvatarUpdated',
                'latestSyncSeq': 2,
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    expect(store.lastContactAvatarUserId, 'user_002');
    expect(
      store.lastContactAvatarUrl,
      'media/avatar/s/archived-avatar/user/user_002/v1/profile.png',
    );
    expect(store.lastContactAvatarVersion, 14);
  });

  testWidgets('patch gap 触发全量修复并推进游标', (tester) async {
    final store = _FakeLocalChatSearchStore();
    final namespace = LocalSearchNamespace.fromActivePersonaContext(
      ActivePersonaContextViewData.fallback(
        personaId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'title': '群聊',
      'type': 'group',
      'groupAvatarVersion': 1,
      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
      'updatedAt': '2026-04-23T09:00:00.000Z',
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            _ResyncChatRepository(),
          ),
          userSyncRepositoryProvider.overrideWithValue(
            _GapUserSyncRepository(),
          ),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '测试用户',
              avatarUrl: '',
            ),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ref
                  .read(conversationCacheProvider)
                  .put(
                    ConversationCacheRecord.fromCacheMap(<String, dynamic>{
                      'conversationId': 'conv_001',
                      'type': 'group',
                      'title': '群聊',
                      'groupAvatarVersion': 1,
                      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                      'updatedAt': '2026-04-23T09:00:00.000Z',
                    }),
                  );
              RealtimeMessageHandler(ref.read).handle(<String, dynamic>{
                'type': 'sync_hint',
                'latestSyncSeq': 3,
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final container = ProviderScope.containerOf(
      tester.element(find.byType(SizedBox)),
    );
    final cache = container.read(conversationCacheProvider);
    expect(
      cache.get('conv_001')?.avatarUrl,
      'https://cdn.example.com/full-sync.png?v=3',
    );
    expect(cache.get('conv_001')?.groupAvatarVersion, 3);
    expect(await store.lastUserSyncSeq(namespace: namespace), 3);
  });

  testWidgets('高频 sync_hint 会被防抖合并为一次 patch 拉取', (tester) async {
    final store = _FakeLocalChatSearchStore();
    final syncRepository = _CountingUserSyncRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userSyncRepositoryProvider.overrideWithValue(syncRepository),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '测试用户',
              avatarUrl: '',
            ),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              final handler = RealtimeMessageHandler(ref.read);
              handler.handle(<String, dynamic>{
                'type': 'sync_hint',
                'latestSyncSeq': 1,
              });
              handler.handle(<String, dynamic>{
                'type': 'ConversationAvatarUpdated',
                'latestSyncSeq': 2,
              });
              handler.handle(<String, dynamic>{
                'type': 'sync_hint',
                'latestSyncSeq': 3,
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    expect(syncRepository.pullCount, 1);
  });

  testWidgets('avatar patch 应用失败时不推进游标并暴露失败状态', (tester) async {
    final store = _FakeLocalChatSearchStore();
    final namespace = LocalSearchNamespace.fromActivePersonaContext(
      ActivePersonaContextViewData.fallback(
        personaId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'title': '群聊',
      'type': 'group',
      'groupAvatarVersion': 1,
      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
      'updatedAt': DateTime.now().toIso8601String(),
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userSyncRepositoryProvider.overrideWithValue(
            _InvalidAvatarPatchRepository(),
          ),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '测试用户',
              avatarUrl: '',
            ),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ref
                  .read(conversationCacheProvider)
                  .put(
                    ConversationCacheRecord.fromCacheMap(<String, dynamic>{
                      'conversationId': 'conv_001',
                      'type': 'group',
                      'title': '群聊',
                      'groupAvatarVersion': 1,
                      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                    }),
                  );
              RealtimeMessageHandler(ref.read).handle(<String, dynamic>{
                'type': 'sync_hint',
                'latestSyncSeq': 4,
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final container = ProviderScope.containerOf(
      tester.element(find.byType(SizedBox)),
    );
    final syncService = container.read(conversationSyncProvider);
    final cache = container.read(conversationCacheProvider);
    expect(await store.lastUserSyncSeq(namespace: namespace), 0);
    expect(syncService.hasAvatarPatchSyncFailure, isTrue);
    expect(
      cache.get('conv_001')?.avatarUrl,
      'https://cdn.example.com/old.png?v=1',
    );
  });
}
