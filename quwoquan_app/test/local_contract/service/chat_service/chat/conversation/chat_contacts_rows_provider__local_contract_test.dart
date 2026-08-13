import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/runtime/di/chat_contacts_rows_dependencies.dart';

void main() {
  group('chatContactsRowsForSubTabProvider', () {
    test('全部 tab 消费 ContactHome 聚合行', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: chatTestRepositoryOverrides(contact: repo),
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(ChatContactHomeFilter.all).future,
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
        overrides: chatTestRepositoryOverrides(contact: repo),
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        chatContactsRowsForSubTabProvider(ChatContactHomeFilter.mutual).future,
      );

      expect(repo.requestedFilters, <String>['mutual']);
      expect(rows, hasLength(1));
      expect(rows.single.kind, ChatContactsRowKind.user);
      expect(rows.single.id, 'user_mutual_01');
      expect(rows.single.isMutualFollow, isTrue);
    });

    test('圈子和群聊 tab 使用 ContactHome kind，群聊仍请求 group filter', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: chatTestRepositoryOverrides(contact: repo),
      );
      addTearDown(container.dispose);

      final circleRows = await container.read(
        chatContactsRowsForSubTabProvider(ChatContactHomeFilter.circle).future,
      );
      final groupRows = await container.read(
        chatContactsRowsForSubTabProvider(ChatContactHomeFilter.group).future,
      );

      expect(repo.requestedFilters, <String>['circle', 'group']);
      expect(ChatText.contactsTabGroups, '群聊');
      expect(circleRows, hasLength(1));
      expect(circleRows.single.kind, ChatContactsRowKind.circle);
      expect(circleRows.single.id, 'circle_01');

      expect(groupRows, hasLength(1));
      expect(groupRows.single.kind, ChatContactsRowKind.group);
      expect(groupRows.single.id, 'group_01');
    });

    test('无服务端事实交集时不从关系态或标题本地合成摘要', () {
      final row = chatContactsRowFromContactHome(
        _contactHomeRow(
          id: 'user_without_intersection',
          kind: 'user',
          objectId: 'user_without_intersection',
          userId: 'user_without_intersection',
          title: '普通联系人',
          relationState: 'mutual',
          intersectionFacts: const <ContactIntersectionFact>[],
        ),
      );

      expect(row.subtitle, isEmpty);
    });
  });
}

final class _FakeChatRepository implements ChatContactRepository {
  final ChatContactRepository _delegate = ChatTestFacets().contact;

  final List<String> requestedFilters = <String>[];

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    requestedFilters.add(filter);
    final rows = switch (filter) {
      'mutual' => <ContactHomeRow>[
        _contactHomeRow(
          id: 'user_mutual_01',
          kind: 'user',
          objectId: 'user_mutual_01',
          userId: 'user_mutual_01',
          title: '互相关注用户',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
          relationState: 'mutual',
          intersectionFacts: _mutualIntersectionFacts,
        ),
      ],
      'circle' => <ContactHomeRow>[
        _contactHomeRow(
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
      'group' => <ContactHomeRow>[
        _contactHomeRow(
          id: 'group_01',
          kind: 'group',
          objectId: 'group_01',
          conversationId: 'group_01',
          title: '测试讨论',
          subtitle: '来自：九寨沟 · 摄影圈 · 368成员',
          avatarUrl:
              'media/avatar/s/archived-avatar/group/group_01/v1/composite.png',
        ),
      ],
      _ => <ContactHomeRow>[
        _contactHomeRow(
          userId: 'user_mutual_01',
          id: 'user_mutual_01',
          kind: 'user',
          objectId: 'user_mutual_01',
          title: '互相关注用户',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/user_mutual_01/v1/avatar.png',
          relationState: 'mutual',
          intersectionFacts: _mutualIntersectionFacts,
        ),
        _contactHomeRow(
          id: 'circle_01',
          kind: 'circle',
          objectId: 'circle_01',
          circleId: 'circle_01',
          title: '测试圈子',
          subtitle: '圈子摘要',
        ),
        _contactHomeRow(
          id: 'group_01',
          kind: 'group',
          objectId: 'group_01',
          conversationId: 'group_01',
          title: '测试讨论',
          subtitle: '来自：九寨沟 · 摄影圈 · 368成员',
        ),
      ],
    };
    return rows.take(limit).toList(growable: false);
  }

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = ChatListContactsQuery.defaultLimit,
  }) => _delegate.listContacts(cursor: cursor, limit: limit);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) => _delegate.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );
}

ContactHomeRow _contactHomeRow({
  required String id,
  required String kind,
  required String objectId,
  String? userId,
  String userHandle = '',
  String? conversationId,
  String? circleId,
  String? circleGroupId,
  String? entityId,
  required String title,
  String subtitle = '',
  String avatarUrl = '',
  String? relationState,
  List<ContactIntersectionFact> intersectionFacts =
      const <ContactIntersectionFact>[],
}) => ContactHomeRow(
  id: id,
  kind: kind,
  objectId: objectId,
  userId: userId,
  userHandle: userHandle,
  conversationId: conversationId,
  circleId: circleId,
  circleGroupId: circleGroupId,
  entityId: entityId,
  title: title,
  subtitle: subtitle,
  avatarUrl: avatarUrl,
  relationState: relationState,
  intersectionFacts: intersectionFacts,
  contactCount: 0,
  sortKey: '',
);

/// typed 交集事实：primaryText 是云侧结论句，端只透传（REQ-001 不拼句）。
const List<ContactIntersectionFact> _mutualIntersectionFacts =
    <ContactIntersectionFact>[
      ContactIntersectionFact(
        intersectionId: 'ix_shared_circle_photo',
        kind: 'sharedCircle',
        dimension: 'relationship',
        intersectionClass: 'fact',
        primaryText: '摄影圈',
      ),
      ContactIntersectionFact(
        intersectionId: 'ix_co_wishlist_jiuzhaigou',
        kind: 'coWishlistedEntity',
        dimension: 'location',
        intersectionClass: 'fact',
        primaryText: '九寨沟',
      ),
    ];
