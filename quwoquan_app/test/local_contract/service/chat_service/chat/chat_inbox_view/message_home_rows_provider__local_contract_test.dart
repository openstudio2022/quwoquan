// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/message-home-commercial-ia/spec.md#gwt-001
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_rows.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';

void main() {
  group('messageHomeRowsProvider', () {
    test('透传 filter 并映射 conversation 行', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        messageHomeRowsProvider('group').future,
      );
      final rows = state.rows;

      expect(repo.requestedFilters, <String>['group']);
      expect(rows, hasLength(1));
      expect(rows.single.conversationId, 'conv_group_01');
      expect(rows.single.conversationType, 'group');
      expect(rows.single.unreadCount, greaterThan(0));
    });

    test('notification 行生成 notification id，不当作会话', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        messageHomeRowsProvider('notification').future,
      );
      final rows = state.rows;

      expect(repo.requestedFilters, <String>['notification']);
      expect(rows.single.notificationId, 'app_msg_01');
      expect(rows.single.conversationId, isEmpty);
      expect(rows.single.conversationType, isEmpty);
    });

    test('未读角标数汇总 unread filter 的 unreadCount', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final resolved = await container.read(
        messageHomeRowsProvider('unread').future,
      );
      expect(totalUnreadMessages(resolved.rows), 2);
    });

    test('会话已读刷新会失效所有 MessageHome filter', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsProvider(filter).future);
      }
      expect(repo.requestedFilters, messageHomeFilters);

      repo.markConversationRead('conv_group_01');
      for (final filter in messageHomeFilters) {
        container.read(messageHomeRowsRefreshProvider(filter))();
      }
      for (final filter in messageHomeFilters) {
        await container.read(messageHomeRowsProvider(filter).future);
      }

      expect(repo.requestedFilters, <String>[
        ...messageHomeFilters,
        ...messageHomeFilters,
      ]);
      final allState = await container.read(
        messageHomeRowsProvider('all').future,
      );
      final directState = await container.read(
        messageHomeRowsProvider('direct').future,
      );
      expect(allState.rows.single.unreadCount, 0);
      expect(directState.rows.single.unreadCount, 0);
    });

    test('远端刷新失败保留 last-confirmed 并进入错误态', () async {
      final repo = _FakeChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(messageHomeRowsProvider('all').future);
      repo.failRequests = true;
      container.read(messageHomeRowsRefreshProvider('all'))();

      await expectLater(
        container.read(messageHomeRowsProvider('all').future),
        throwsA(isA<StateError>()),
      );
      final state = container.read(messageHomeRowsProvider('all'));

      expect(state.hasError, isTrue);
      expect(state.hasValue, isTrue);
      expect(state.value?.rows.single.conversationId, 'conv_group_01');
      expect(state.value?.isCacheFallback, isFalse);
    });

    test('被失效的迟到响应不能覆盖较新的 authoritative 结果', () async {
      final repo = _ControlledChatRepository();
      final container = ProviderContainer(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final stale = Completer<List<MessageHomeRow>>();
      final fresh = Completer<List<MessageHomeRow>>();
      repo.responses.addAll(<Completer<List<MessageHomeRow>>>[stale, fresh]);

      final staleFuture = container.read(messageHomeRowsProvider('all').future);
      await Future<void>.delayed(Duration.zero);
      container.read(messageHomeRowsRefreshProvider('all'))();
      final freshFuture = container.read(messageHomeRowsProvider('all').future);
      fresh.complete(<MessageHomeRow>[
        _messageHomeRow(
          id: 'conv_fresh',
          kind: 'conversation',
          conversationId: 'conv_fresh',
          title: '最新会话',
          summary: 'authoritative',
        ),
      ]);
      expect((await freshFuture).rows.single.conversationId, 'conv_fresh');

      stale.complete(<MessageHomeRow>[
        _messageHomeRow(
          id: 'conv_stale',
          kind: 'conversation',
          conversationId: 'conv_stale',
          title: '迟到会话',
          summary: 'stale',
        ),
      ]);
      await staleFuture;
      await Future<void>.delayed(Duration.zero);

      expect(
        container
            .read(messageHomeRowsProvider('all'))
            .value
            ?.rows
            .single
            .conversationId,
        'conv_fresh',
      );
    });
  });
}

final class _ControlledChatRepository extends MockChatRepository {
  final List<Completer<List<MessageHomeRow>>> responses =
      <Completer<List<MessageHomeRow>>>[];

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 100,
  }) {
    if (responses.isEmpty) {
      throw StateError('missing controlled response');
    }
    return responses.removeAt(0).future;
  }
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
