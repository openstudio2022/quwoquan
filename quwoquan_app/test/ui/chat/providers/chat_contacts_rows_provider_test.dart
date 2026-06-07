import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';

void main() {
  group('chatContactsRowsForSubTabProvider', () {
    test('全部 tab 合并用户、圈子和趣群并去重', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _FakeChatRepository(withDuplicateUserRow: true),
          ),
        ],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(UITextConstants.contactsTabAll).future,
      );

      expect(rows, hasLength(4));
      expect(
        rows.map((row) => row.kind),
        containsAll(<ChatContactsRowKind>[
          ChatContactsRowKind.user,
          ChatContactsRowKind.circle,
          ChatContactsRowKind.group,
        ]),
      );
      expect(
        rows.where(
          (row) =>
              row.kind == ChatContactsRowKind.user &&
              row.id == 'user_mutual_01',
        ),
        hasLength(1),
      );
      expect(
        rows.where(
          (row) =>
              row.kind == ChatContactsRowKind.user &&
              row.id == 'user_following_01',
        ),
        hasLength(1),
      );
      expect(
        rows.where((row) => row.kind == ChatContactsRowKind.circle).single.id,
        'circle_01',
      );
      expect(
        rows.where((row) => row.kind == ChatContactsRowKind.group).single.id,
        'group_01',
      );
    });

    test('互相关注 tab 只保留 mutual rows', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_FakeChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(
          UITextConstants.contactsTabMutualFollow,
        ).future,
      );

      expect(rows, hasLength(1));
      expect(rows.single.kind, ChatContactsRowKind.user);
      expect(rows.single.id, 'user_mutual_01');
      expect(rows.single.isMutualFollow, isTrue);
    });

    test('圈子和趣群 tab 使用各自的强类型行', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_FakeChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final circleRows = await container.read(
        chatContactsRowsForSubTabProvider(UITextConstants.contactsTabCircles)
            .future,
      );
      final groupRows = await container.read(
        chatContactsRowsForSubTabProvider(UITextConstants.contactsTabFunGroup)
            .future,
      );

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
  _FakeChatRepository({this.withDuplicateUserRow = false}) : super();

  final bool withDuplicateUserRow;

  @override
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 500,
  }) async {
    final rows = <ChatContactRowDto>[
      ChatContactRowDto(
        userId: 'user_mutual_01',
        displayName: '互相关注用户',
        avatarUrl: 'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
        relationState: 'mutual',
        source: 'conversation',
        bio: '来自会话',
      ),
      if (withDuplicateUserRow)
        ChatContactRowDto(
          userId: 'user_mutual_01',
          displayName: '互相关注用户重复行',
          avatarUrl: 'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
          relationState: 'mutual',
          source: 'follow',
          bio: '重复行',
        ),
      ChatContactRowDto(
        userId: 'user_following_01',
        displayName: '单向关注用户',
        avatarUrl:
            'media/avatar/s/archived-avatar/user/user_following_01/v1/avatar.png',
        relationState: 'following',
        source: 'follow',
        bio: '来自关注',
      ),
    ];
    return rows.take(limit).toList(growable: false);
  }

  @override
  Future<List<ChatContactTabCircleRowDto>> listContactTabCircles({
    int limit = 500,
  }) async {
    return [
      const ChatContactTabCircleRowDto(
        circleId: 'circle_01',
        displayName: '测试圈子',
        avatarUrl:
            'media/avatar/s/archived-avatar/group/circle_01/v1/composite.png',
        subtitle: '圈子摘要',
      ),
    ].take(limit).toList(growable: false);
  }

  @override
  Future<List<ChatContactTabFunGroupRowDto>> listContactTabFunGroups({
    int limit = 500,
  }) async {
    return [
      const ChatContactTabFunGroupRowDto(
        conversationId: 'group_01',
        displayName: '测试趣群',
        avatarUrl:
            'media/avatar/s/archived-avatar/group/group_01/v1/composite.png',
        subtitle: '趣群摘要',
      ),
    ].take(limit).toList(growable: false);
  }
}
