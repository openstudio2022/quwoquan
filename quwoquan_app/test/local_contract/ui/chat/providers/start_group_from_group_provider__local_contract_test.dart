import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_from_group_provider.dart';
import '../../../../common/chat/chat_mock_seed_refs.dart';

void main() {
  group('从群聊中选择联系人 · Provider local_contract', () {
    test('图四群列表只暴露含 mutual 成员的群且 friendCount = 成员交集大小', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final groups = await container.read(startGroupFromGroupProvider.future);

      // 云侧/Mock 已过滤 friendMemberCount == 0 的群。
      expect(groups, isNotEmpty);
      expect(groups.every((g) => g.friendCount > 0), isTrue);

      // 关键契约：每个群的「N 个朋友」必须等于图五真实可选成员数（计数↔交集一致）。
      for (final group in groups) {
        final members = await loadGroupContactMembers(
          repo,
          group,
          <String>{},
        );
        expect(
          members.length,
          group.friendCount,
          reason: '群 ${group.conversationId} 的 friendCount 与成员交集不一致',
        );
      }
    });

    test('图五成员交集排除当前用户、按名排序且锁定成员被过滤', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final groups = await container.read(startGroupFromGroupProvider.future);
      final group = groups.first;

      final members = await loadGroupContactMembers(repo, group, <String>{});
      expect(members, isNotEmpty);

      // 排除当前用户。
      final currentUserId = chatCurrentUserProfileId();
      expect(members.any((m) => m.userId == currentUserId), isFalse);

      // userId 非空、无重复。
      expect(members.every((m) => m.userId.isNotEmpty), isTrue);
      expect(
        members.map((m) => m.userId).toSet().length,
        members.length,
      );

      // 按 displayName 升序。
      final names = members.map((m) => m.displayName).toList();
      final sorted = List<String>.from(names)..sort();
      expect(names, sorted);

      // 锁定首个成员后，应从交集中剔除且总数 -1。
      final lockedId = members.first.userId;
      final afterLock = await loadGroupContactMembers(
        repo,
        group,
        <String>{lockedId},
      );
      expect(afterLock.any((m) => m.userId == lockedId), isFalse);
      expect(afterLock.length, members.length - 1);
    });
  });
}
