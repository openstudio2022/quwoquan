import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

class _FakeUserSyncRepository implements UserSyncRepository {
  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    if (afterSeq >= 1) {
      return const UserSyncPullResult(
        patches: <UserSyncPatch>[],
        latestSyncSeq: 1,
        hasMore: false,
        requiresResync: false,
      );
    }
    return const UserSyncPullResult(
      patches: <UserSyncPatch>[
        UserSyncPatch(
          syncSeq: 1,
          type: 'conversation.avatar.updated',
          userId: 'user_001',
          payload: <String, dynamic>{
            'conversationId': 'conv_001',
            'avatarUrl': 'https://cdn.example.com/group.png?v=2',
            'groupAvatarVersion': 2,
          },
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
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    return const UserSyncPullResult(
      patches: <UserSyncPatch>[],
      latestSyncSeq: 3,
      hasMore: false,
      requiresResync: true,
    );
  }
}

class _InvalidAvatarPatchRepository implements UserSyncRepository {
  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    return const UserSyncPullResult(
      patches: <UserSyncPatch>[
        UserSyncPatch(
          syncSeq: 4,
          type: 'conversation.avatar.updated',
          userId: 'user_001',
          payload: <String, dynamic>{
            'conversationId': 'conv_001',
            'avatarUrl': '',
            'groupAvatarVersion': 4,
          },
        ),
      ],
      latestSyncSeq: 4,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _CountingUserSyncRepository implements UserSyncRepository {
  int pullCount = 0;

  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = 200,
  }) async {
    pullCount += 1;
    return const UserSyncPullResult(
      patches: <UserSyncPatch>[],
      latestSyncSeq: 3,
      hasMore: false,
      requiresResync: false,
    );
  }
}

class _ResyncChatRepository extends MockChatRepository {
  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    return <ChatConversationTimestampDto>[
      ChatConversationTimestampDto(
        conversationId: 'conv_001',
        updatedAt: '2026-04-23T10:00:00.000Z',
      ),
    ];
  }

  @override
  Future<List<ConversationDto>> batchGetConversations(List<String> ids) async {
    return <ConversationDto>[
      ConversationDto.fromMap(<String, dynamic>{
        '_id': 'conv_001',
        'id': 'conv_001',
        'type': 'group',
        'title': '群聊',
        'avatarUrl': 'https://cdn.example.com/full-sync.png?v=3',
        'groupAvatarVersion': 3,
        'creatorId': 'user_001',
        'maxSeq': 0,
        'memberCount': 3,
        'maxGroupSize': 500,
        'receiptEnabled': true,
        'messageCount': 0,
        'status': 'active',
        'createdAt': '2026-04-23T09:00:00.000Z',
        'updatedAt': '2026-04-23T10:00:00.000Z',
      }),
    ];
  }
}

class _FakeLocalChatSearchStore extends LocalChatSearchStore {
  _FakeLocalChatSearchStore();

  final Map<String, Map<String, dynamic>> _conversations =
      <String, Map<String, dynamic>>{};
  int _lastUserSyncSeq = 0;

  void seedConversation(Map<String, dynamic> conversation) {
    final id =
        conversation['conversationId']?.toString() ??
        conversation['id']?.toString() ??
        conversation['_id']?.toString() ??
        '';
    if (id.isEmpty) {
      return;
    }
    _conversations[id] = Map<String, dynamic>.from(conversation);
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
    final updated = <String, dynamic>{...existing, 'avatarUrl': avatarUrl};
    if (groupAvatarVersion != null) {
      updated['groupAvatarVersion'] = groupAvatarVersion;
    }
    if (groupAvatarSourceHash != null) {
      updated['groupAvatarSourceHash'] = groupAvatarSourceHash;
    }
    _conversations[conversationId] = updated;
  }

  @override
  Future<void> updateContactAvatar({
    required LocalSearchNamespace namespace,
    required String userId,
    required String avatarUrl,
  }) async {}

  @override
  Future<List<Map<String, dynamic>>> listConversationPayloads({
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
        profileSubjectId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'id': 'conv_001',
      '_id': 'conv_001',
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
              profileSubjectId: 'user_001',
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
                  .put('conv_001', <String, dynamic>{
                    'id': 'conv_001',
                    '_id': 'conv_001',
                    'conversationId': 'conv_001',
                    'type': 'group',
                    'title': '群聊',
                    'groupAvatarVersion': 1,
                    'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                  });
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
      cache.get('conv_001')?['avatarUrl'],
      'https://cdn.example.com/group.png?v=2',
    );
    expect(cache.get('conv_001')?['groupAvatarVersion'], 2);

    final stored = await store.listConversationPayloads(namespace: namespace);
    expect(stored.single['avatarUrl'], 'https://cdn.example.com/group.png?v=2');
    expect(stored.single['groupAvatarVersion'], 2);
  });

  testWidgets('patch gap 触发全量修复并推进游标', (tester) async {
    final store = _FakeLocalChatSearchStore();
    final namespace = LocalSearchNamespace.fromActivePersonaContext(
      ActivePersonaContextViewData.fallback(
        profileSubjectId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'id': 'conv_001',
      '_id': 'conv_001',
      'title': '群聊',
      'type': 'group',
      'groupAvatarVersion': 1,
      'avatarUrl': 'https://cdn.example.com/old.png?v=1',
      'updatedAt': '2026-04-23T09:00:00.000Z',
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_ResyncChatRepository()),
          userSyncRepositoryProvider.overrideWithValue(
            _GapUserSyncRepository(),
          ),
          localChatSearchStoreProvider.overrideWithValue(store),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              profileSubjectId: 'user_001',
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
                  .put('conv_001', <String, dynamic>{
                    'id': 'conv_001',
                    '_id': 'conv_001',
                    'conversationId': 'conv_001',
                    'type': 'group',
                    'title': '群聊',
                    'groupAvatarVersion': 1,
                    'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                    'updatedAt': '2026-04-23T09:00:00.000Z',
                  });
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
      cache.get('conv_001')?['avatarUrl'],
      'https://cdn.example.com/full-sync.png?v=3',
    );
    expect(cache.get('conv_001')?['groupAvatarVersion'], 3);
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
              profileSubjectId: 'user_001',
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
        profileSubjectId: 'user_001',
        ownerUserId: 'user_001',
        displayName: '测试用户',
        avatarUrl: '',
      ),
    );
    store.seedConversation(<String, dynamic>{
      'conversationId': 'conv_001',
      'id': 'conv_001',
      '_id': 'conv_001',
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
              profileSubjectId: 'user_001',
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
                  .put('conv_001', <String, dynamic>{
                    'id': 'conv_001',
                    '_id': 'conv_001',
                    'conversationId': 'conv_001',
                    'type': 'group',
                    'title': '群聊',
                    'groupAvatarVersion': 1,
                    'avatarUrl': 'https://cdn.example.com/old.png?v=1',
                  });
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
      cache.get('conv_001')?['avatarUrl'],
      'https://cdn.example.com/old.png?v=1',
    );
  });
}
