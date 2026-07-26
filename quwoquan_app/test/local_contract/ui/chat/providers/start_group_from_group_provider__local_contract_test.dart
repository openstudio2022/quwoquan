import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_from_group_provider.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import '../../../../support/fixtures/chat/chat_mock_seed_refs.dart';

void main() {
  group('从群聊中选择联系人 · Provider local_contract', () {
    test('缺少 media endpoint 时预合成头像引用 fail-closed', () {
      const raw =
          'media/avatar/s/archived-avatar/group/fixture_conv_group/composite.png';
      final resolved = resolveSelectableGroupAvatar(raw, avatarCdnBaseUrl: '');
      expect(resolved, isEmpty);
    });

    test('startGroupFromGroupProvider 保留 canonical 群身份并呈现头像空态', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final groups = (await loadStartGroupSourcePage(
        repo,
        source: StartGroupSource.group,
        avatarCdnBaseUrl: '',
      )).groups;
      expect(groups, isNotEmpty);

      final canonicalGroup = groups.firstWhere(
        (g) => g.conversationId == 'fixture_conv_group',
        orElse: () => throw StateError(
          'fixture_conv_group missing from selectable groups',
        ),
      );
      expect(canonicalGroup.title, '契约周末群');
      expect(canonicalGroup.avatarUrl, isEmpty);
      expect(
        resolveSelectableGroupAvatar(
          'media/avatar/s/archived-avatar/group/fixture_conv_group/composite.png',
          avatarCdnBaseUrl: '',
        ),
        canonicalGroup.avatarUrl,
      );
    });

    test('图四群列表只暴露含 mutual 成员的群且 friendCount = 成员交集大小', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final groups = (await loadStartGroupSourcePage(
        repo,
        source: StartGroupSource.group,
      )).groups;

      // 云侧/Mock 已过滤 friendMemberCount == 0 的群。
      expect(groups, isNotEmpty);
      expect(groups.every((g) => g.friendCount > 0), isTrue);

      // 关键契约：每个群的「N 个朋友」必须等于图五真实可选成员数（计数↔交集一致）。
      for (final group in groups) {
        final members = (await loadGroupContactMemberPage(
          repo,
          group: group,
          lockedMemberIds: <String>{},
        )).members;
        expect(
          members.length,
          group.friendCount,
          reason: '群 ${group.conversationId} 的 friendCount 与成员交集不一致',
        );
      }
    });

    test('私建群与圈子绑定群由服务端 source 分流且共享成员交集链', () async {
      final repo = _SourceAwareGroupSelectionRepository();
      final container = ProviderContainer(
        overrides: [
          chatGroupSelectionRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      final groups = (await container.read(
        startGroupSourcePageProvider(
          const StartGroupSourcePageRequest(source: StartGroupSource.group),
        ).future,
      )).groups;
      final circles = (await container.read(
        startGroupSourcePageProvider(
          const StartGroupSourcePageRequest(source: StartGroupSource.circle),
        ).future,
      )).groups;

      expect(groups.map((row) => row.conversationId), <String>[
        'conversation_private',
      ]);
      expect(groups.single.circleId, isEmpty);
      expect(circles.map((row) => row.conversationId), <String>[
        'conversation_circle',
      ]);
      expect(circles.single.circleId, 'circle_photo');
      expect(repo.requestedSources, <ChatSelectableGroupSource>[
        ChatSelectableGroupSource.group,
        ChatSelectableGroupSource.circle,
      ]);

      final members = (await loadGroupContactMemberPage(
        repo,
        group: circles.single,
        lockedMemberIds: <String>{},
      )).members;
      expect(members.map((member) => member.userId), <String>['friend_circle']);
    });

    test('图五成员交集排除当前用户、按名排序且锁定成员被过滤', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final groups = (await loadStartGroupSourcePage(
        repo,
        source: StartGroupSource.group,
      )).groups;
      final group = groups.first;

      final members = (await loadGroupContactMemberPage(
        repo,
        group: group,
        lockedMemberIds: <String>{},
      )).members;
      expect(members, isNotEmpty);

      // 排除当前用户。
      final currentUserId = chatCurrentUserProfileId();
      expect(members.any((m) => m.userId == currentUserId), isFalse);

      // userId 非空、无重复。
      expect(members.every((m) => m.userId.isNotEmpty), isTrue);
      expect(members.map((m) => m.userId).toSet().length, members.length);

      // 按 displayName 升序。
      final names = members.map((m) => m.displayName).toList();
      final sorted = List<String>.from(names)..sort();
      expect(names, sorted);

      // 锁定首个成员后，应从交集中剔除且总数 -1。
      final lockedId = members.first.userId;
      final afterLock = (await loadGroupContactMemberPage(
        repo,
        group: group,
        lockedMemberIds: <String>{lockedId},
      )).members;
      expect(afterLock.any((m) => m.userId == lockedId), isFalse);
      expect(afterLock.length, members.length - 1);
    });

    test('群与成员分页保序追加去重，并将搜索词逐页传给 repository', () async {
      final repo = _PagedGroupSelectionRepository();

      final firstGroups = await loadStartGroupSourcePage(
        repo,
        source: StartGroupSource.group,
        query: '旅行',
      );
      final secondGroups = await loadStartGroupSourcePage(
        repo,
        source: StartGroupSource.group,
        query: '旅行',
        cursor: firstGroups.nextCursor,
      );
      final groups = mergeStartGroupSourcePages(
        firstGroups.groups,
        secondGroups.groups,
      );
      expect(groups.map((group) => group.conversationId), <String>[
        'conversation_1',
        'conversation_2',
        'conversation_3',
      ]);

      final firstMembers = await loadGroupContactMemberPage(
        repo,
        group: groups.first,
        lockedMemberIds: <String>{},
        query: '旅行',
      );
      final secondMembers = await loadGroupContactMemberPage(
        repo,
        group: groups.first,
        lockedMemberIds: <String>{},
        query: '旅行',
        cursor: firstMembers.nextCursor,
      );
      final members = mergeStartGroupContactMemberPages(
        firstMembers.members,
        secondMembers.members,
      );
      expect(members.map((member) => member.userId), <String>[
        'user_1',
        'user_2',
        'user_3',
      ]);
      expect(repo.groupRequests, <({String? cursor, String? query})>[
        (cursor: null, query: '旅行'),
        (cursor: 'groups-2', query: '旅行'),
      ]);
      expect(repo.memberRequests, <({String? cursor, String? query})>[
        (cursor: null, query: '旅行'),
        (cursor: 'members-2', query: '旅行'),
      ]);
    });
  });
}

final class _SourceAwareGroupSelectionRepository
    implements ChatGroupSelectionRepository {
  final List<ChatSelectableGroupSource> requestedSources =
      <ChatSelectableGroupSource>[];

  @override
  Future<CursorPage<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = 20,
  }) async {
    requestedSources.add(source);
    final items = switch (source) {
      ChatSelectableGroupSource.group => <SelectableGroupConversationRowDto>[
        SelectableGroupConversationRowDto(
          conversationId: 'conversation_private',
          title: '周末同行群',
          circleId: '',
          friendMemberCount: 1,
          memberCount: 3,
        ),
      ],
      ChatSelectableGroupSource.circle => <SelectableGroupConversationRowDto>[
        SelectableGroupConversationRowDto(
          conversationId: 'conversation_circle',
          title: '摄影圈交流群',
          circleId: 'circle_photo',
          friendMemberCount: 1,
          memberCount: 8,
        ),
      ],
      ChatSelectableGroupSource.all => <SelectableGroupConversationRowDto>[],
    };
    return CursorPage<SelectableGroupConversationRowDto>(items: items);
  }

  @override
  Future<CursorPage<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async => CursorPage<ChatContactRowDto>(
    items: <ChatContactRowDto>[
      ChatContactRowDto(
        userId: conversationId == 'conversation_circle'
            ? 'friend_circle'
            : 'friend_private',
        displayName: conversationId == 'conversation_circle' ? '圈友' : '群友',
        relationState: 'mutual',
        source: 'mutual_follow',
      ),
    ],
  );
}

final class _PagedGroupSelectionRepository
    implements ChatGroupSelectionRepository {
  final List<({String? cursor, String? query})> groupRequests =
      <({String? cursor, String? query})>[];
  final List<({String? cursor, String? query})> memberRequests =
      <({String? cursor, String? query})>[];

  @override
  Future<CursorPage<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = 20,
  }) async {
    groupRequests.add((cursor: cursor, query: query));
    return switch (cursor) {
      null => CursorPage<SelectableGroupConversationRowDto>(
        items: <SelectableGroupConversationRowDto>[
          _groupRow('conversation_1'),
          _groupRow('conversation_2'),
        ],
        nextCursor: 'groups-2',
      ),
      'groups-2' => CursorPage<SelectableGroupConversationRowDto>(
        items: <SelectableGroupConversationRowDto>[
          _groupRow('conversation_2'),
          _groupRow('conversation_3'),
        ],
      ),
      _ => const CursorPage<SelectableGroupConversationRowDto>(items: []),
    };
  }

  @override
  Future<CursorPage<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    memberRequests.add((cursor: cursor, query: query));
    return switch (cursor) {
      null => CursorPage<ChatContactRowDto>(
        items: <ChatContactRowDto>[_memberRow('user_1'), _memberRow('user_2')],
        nextCursor: 'members-2',
      ),
      'members-2' => CursorPage<ChatContactRowDto>(
        items: <ChatContactRowDto>[_memberRow('user_2'), _memberRow('user_3')],
      ),
      _ => const CursorPage<ChatContactRowDto>(items: []),
    };
  }

  SelectableGroupConversationRowDto _groupRow(String conversationId) {
    return SelectableGroupConversationRowDto(
      conversationId: conversationId,
      title: conversationId,
      friendMemberCount: 2,
      memberCount: 3,
    );
  }

  ChatContactRowDto _memberRow(String userId) {
    return ChatContactRowDto(
      userId: userId,
      displayName: userId,
      relationState: 'mutual',
      source: 'group',
    );
  }
}
