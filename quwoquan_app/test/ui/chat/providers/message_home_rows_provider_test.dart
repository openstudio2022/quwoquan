import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';

void main() {
  group('messageHomeRowsProvider', () {
    test('透传 filter 并映射 conversation 行', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        messageHomeRowsProvider('group').future,
      );

      expect(repo.requestedFilters, <String>['group']);
      expect(rows, hasLength(1));
      expect(rows.single.id, 'conv_group_01');
      expect(rows.single.isGroup, isTrue);
      expect(rows.single.hasUnread, isTrue);
    });

    test('notification 行生成 notification id，不当作会话', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final rows = await container.read(
        messageHomeRowsProvider('notification').future,
      );

      expect(repo.requestedFilters, <String>['notification']);
      expect(rows.single.id, 'notification:app_msg_01');
      expect(rows.single.isNotification, isTrue);
      expect(rows.single.isGroup, isFalse);
    });

    test('未读角标数汇总 unread filter 的 unreadCount', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final count = container.read(messageHomeUnreadBadgeCountProvider);
      expect(count, isNull);

      final resolved = await container.read(
        messageHomeRowsProvider('unread').future,
      );
      expect(totalUnreadMessages(resolved), 2);
      expect(container.read(messageHomeUnreadBadgeCountProvider), 2);
    });

    test('会话已读刷新会失效所有 MessageHome filter', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsProvider(filter).future);
      }
      expect(repo.requestedFilters, messageHomeFilters);

      repo.markConversationRead('conv_group_01');
      for (final filter in messageHomeFilters) {
        container.invalidate(messageHomeRowsProvider(filter));
      }
      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsProvider(filter).future);
      }

      expect(repo.requestedFilters, <String>[
        ...messageHomeFilters,
        ...messageHomeFilters,
      ]);
      final allRows = await container.read(
        messageHomeRowsProvider('all').future,
      );
      final directRows = await container.read(
        messageHomeRowsProvider('direct').future,
      );
      expect(allRows.single.unreadCount, 0);
      expect(directRows.single.unreadCount, 0);
    });
  });
}

final class _FakeChatRepository extends MockChatRepository {
  final List<String> requestedFilters = <String>[];
  final Set<String> _readConversationIds = <String>{};

  void markConversationRead(String conversationId) {
    _readConversationIds.add(conversationId);
  }

  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 100,
  }) async {
    requestedFilters.add(filter);
    if (filter == 'notification') {
      return <MessageHomeRowDto>[
        MessageHomeRowDto(
          id: 'app_msg_01',
          kind: 'notification',
          notificationId: 'app_msg_01',
          title: '小趣提醒',
          summary: '你关注的圈子有新动态',
          unreadCount: 1,
        ),
      ];
    }
    if (filter == 'unread' && _readConversationIds.contains('conv_group_01')) {
      return const <MessageHomeRowDto>[];
    }
    return <MessageHomeRowDto>[
      MessageHomeRowDto(
        id: 'conv_group_01',
        kind: 'conversation',
        conversationId: 'conv_group_01',
        conversationType: 'group',
        title: '九寨沟摄影群',
        summary: '新的活动安排已同步',
        unreadCount: _readConversationIds.contains('conv_group_01') ? 0 : 2,
      ),
    ];
  }
}
