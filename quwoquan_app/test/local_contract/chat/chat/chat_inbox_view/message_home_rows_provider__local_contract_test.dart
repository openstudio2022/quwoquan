// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/message-home-commercial-ia/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';

void main() {
  group('messageHomeRowsStateProvider', () {
    test('透传 filter 并映射 conversation 行', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        messageHomeRowsStateProvider('group').future,
      );
      final rows = state.items;

      expect(repo.requestedFilters, <String>['group']);
      expect(rows, hasLength(1));
      expect(rows.single.id, 'conv_group_01');
      expect(rows.single.isGroup, isTrue);
      expect(rows.single.hasUnread, isTrue);
    });

    test('notification 行生成 notification id，不当作会话', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        messageHomeRowsStateProvider('notification').future,
      );
      final rows = state.items;

      expect(repo.requestedFilters, <String>['notification']);
      expect(rows.single.id, 'notification:app_msg_01');
      expect(rows.single.isNotification, isTrue);
      expect(rows.single.isGroup, isFalse);
    });

    test('未读角标数汇总 unread filter 的 unreadCount', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final resolved = await container.read(
        messageHomeRowsStateProvider('unread').future,
      );
      expect(totalUnreadMessages(resolved.items), 2);
    });

    test('会话已读刷新会失效所有 MessageHome filter', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsStateProvider(filter).future);
      }
      expect(repo.requestedFilters, messageHomeFilters);

      repo.markConversationRead('conv_group_01');
      for (final filter in messageHomeFilters) {
        container.invalidate(messageHomeRowsStateProvider(filter));
      }
      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsStateProvider(filter).future);
      }

      expect(repo.requestedFilters, <String>[
        ...messageHomeFilters,
        ...messageHomeFilters,
      ]);
      final allState = await container.read(
        messageHomeRowsStateProvider('all').future,
      );
      final directState = await container.read(
        messageHomeRowsStateProvider('direct').future,
      );
      expect(allState.items.single.unreadCount, 0);
      expect(directState.items.single.unreadCount, 0);
    });

    test('远端失败时用本机最近聊天兜底并标记 copyKey', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(messageHomeRowsStateProvider('all').future);
      repo.failRequests = true;
      container.invalidate(messageHomeRowsStateProvider('all'));

      final state = await container.read(
        messageHomeRowsStateProvider('all').future,
      );

      expect(state.items.single.id, 'conv_group_01');
      expect(state.isCacheFallback, isTrue);
      expect(state.copyKey, 'chatListCacheFallback');
      expect(state.cacheFallbackError, isA<StateError>());
    });
  });
}

final class _FakeChatRepository extends MockChatRepository {
  final List<String> requestedFilters = <String>[];
  final Set<String> _readConversationIds = <String>{};
  bool failRequests = false;

  void markConversationRead(String conversationId) {
    _readConversationIds.add(conversationId);
  }

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 100,
  }) async {
    requestedFilters.add(filter);
    if (failRequests) {
      throw StateError('message home offline');
    }
    if (filter == 'notification') {
      return <MessageHomeRow>[
        _messageHomeRow(
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
      return const <MessageHomeRow>[];
    }
    return <MessageHomeRow>[
      _messageHomeRow(
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

MessageHomeRow _messageHomeRow({
  required String id,
  required String kind,
  String conversationId = '',
  String notificationId = '',
  String conversationType = '',
  required String title,
  required String summary,
  int unreadCount = 0,
}) => MessageHomeRow(
  id: id,
  kind: kind,
  conversationId: conversationId,
  notificationId: notificationId,
  conversationType: conversationType,
  title: title,
  summary: summary,
  avatarUrl: '',
  groupAvatarVersion: 0,
  unreadCount: unreadCount,
  mentionUnreadCount: 0,
  muted: false,
  pinned: false,
  notificationType: '',
  read: unreadCount == 0,
);
