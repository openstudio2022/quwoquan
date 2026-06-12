import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';

void main() {
  group('chatContactsRowsForSubTabProvider', () {
    test('全部 tab 消费 ContactHome 聚合行', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(
          UITextConstants.contactsTabAll,
        ).future,
      );

      expect(repo.requestedFilters, <String>['all']);
      expect(rows, hasLength(3));
      expect(rows.map((row) => row.kind), <ChatContactsRowKind>[
        ChatContactsRowKind.user,
        ChatContactsRowKind.circle,
        ChatContactsRowKind.group,
      ]);
      expect(rows.first.subtitle, '摄影圈 · 九寨沟');
    });

    test('互相关注 tab 传递 mutual filter', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(
          UITextConstants.contactsTabMutualFollow,
        ).future,
      );

      expect(repo.requestedFilters, <String>['mutual']);
      expect(rows, hasLength(1));
      expect(rows.single.kind, ChatContactsRowKind.user);
      expect(rows.single.id, 'user_mutual_01');
      expect(rows.single.isMutualFollow, isTrue);
    });

    test('圈子和群聊 tab 使用 ContactHome kind', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final circleRows = await container.read(
        chatContactsRowsForSubTabProvider(
          UITextConstants.contactsTabCircles,
        ).future,
      );
      final groupRows = await container.read(
        chatContactsRowsForSubTabProvider(
          UITextConstants.contactsTabGroups,
        ).future,
      );

      expect(repo.requestedFilters, <String>['circle', 'group']);
      expect(circleRows, hasLength(1));
      expect(circleRows.single.kind, ChatContactsRowKind.circle);
      expect(circleRows.single.id, 'circle_01');

      expect(groupRows, hasLength(1));
      expect(groupRows.single.kind, ChatContactsRowKind.group);
      expect(groupRows.single.id, 'group_01');
    });
  });
}

final class _FakeChatRepository extends MockChatRepository {
  _FakeChatRepository() : super();

  final List<String> requestedFilters = <String>[];

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    requestedFilters.add(filter);
    final rows = switch (filter) {
      'mutual' => <ContactHomeRowDto>[
        ContactHomeRowDto(
          id: 'user_mutual_01',
          kind: 'user',
          objectId: 'user_mutual_01',
          userId: 'user_mutual_01',
          title: '互相关注用户',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
          relationState: 'mutual',
          summaryIntersections: const <String>['摄影圈', '九寨沟'],
        ),
      ],
      'circle' => <ContactHomeRowDto>[
        ContactHomeRowDto(
          id: 'circle_01',
          kind: 'circle',
          objectId: 'circle_01',
          circleId: 'circle_01',
          title: '测试圈子',
          subtitle: '圈子摘要',
          avatarUrl:
              'media/avatar/s/archived-avatar/group/circle_01/v1/composite.png',
        ),
      ],
      'group' => <ContactHomeRowDto>[
        ContactHomeRowDto(
          id: 'group_01',
          kind: 'group',
          objectId: 'group_01',
          conversationId: 'group_01',
          title: '测试群聊',
          subtitle: '来自：九寨沟 · 摄影圈 · 368成员',
          avatarUrl:
              'media/avatar/s/archived-avatar/group/group_01/v1/composite.png',
        ),
      ],
      _ => <ContactHomeRowDto>[
        ContactHomeRowDto(
          userId: 'user_mutual_01',
          id: 'user_mutual_01',
          kind: 'user',
          objectId: 'user_mutual_01',
          title: '互相关注用户',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
          relationState: 'mutual',
          summaryIntersections: const <String>['摄影圈', '九寨沟'],
        ),
        ContactHomeRowDto(
          id: 'circle_01',
          kind: 'circle',
          objectId: 'circle_01',
          circleId: 'circle_01',
          title: '测试圈子',
          subtitle: '圈子摘要',
        ),
        ContactHomeRowDto(
          id: 'group_01',
          kind: 'group',
          objectId: 'group_01',
          conversationId: 'group_01',
          title: '测试群聊',
          subtitle: '来自：九寨沟 · 摄影圈 · 368成员',
        ),
      ],
    };
    return rows.take(limit).toList(growable: false);
  }
}
