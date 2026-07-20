import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/cloud_services/user_typed_facet_test_support.dart';

/// 消息页`通知`维度契约（interaction-notification-inbox GWT2）：
/// 通知行只来自 ListAppMessages；点击按 target 路由并 ReadAppMessage；
/// 未读徽标来自 GetAppMessageUnreadCount；无通知走独立空态。
final class _FakeAppMessageFacet
    implements AppMessageQuery, AppMessageCommandWriter {
  _FakeAppMessageFacet(this._messages);

  final List<AppMessage> _messages;
  final List<String> readMessageIds = <String>[];
  int listCalls = 0;
  int unreadCalls = 0;

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    listCalls++;
    return AppMessageInboxSlice(items: _messages);
  }

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    return _messages.firstWhere(
      (message) => message.messageId == query.messageId,
    );
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    unreadCalls++;
    return AppMessageUnreadCountSlice(
      unreadCount: _messages.where((message) => !message.read).length,
    );
  }

  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) async {
    return getAppMessage(GetAppMessageQuery(messageId: command.messageId));
  }

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) async {
    readMessageIds.add(command.messageId);
    final index = _messages.indexWhere(
      (message) => message.messageId == command.messageId,
    );
    final current = _messages[index];
    final updated = AppMessage(
      messageId: current.messageId,
      userId: current.userId,
      messageType: current.messageType,
      source: current.source,
      sourceId: current.sourceId,
      destination: current.destination,
      title: current.title,
      summary: current.summary,
      target: current.target,
      read: true,
      createdAt: current.createdAt,
      readAt: DateTime.utc(2026, 7, 19, 9),
    );
    _messages[index] = updated;
    return updated;
  }
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  _NoopVisitRecorderService() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

AppMessage _interactionMessage({
  required String messageId,
  required String title,
  required String summary,
  bool read = false,
  String routePath = '/content/posts/post-1',
}) {
  return AppMessage(
    messageId: messageId,
    userId: 'recipient-1',
    messageType: 'content',
    source: 'comment',
    sourceId: 'cmt-1',
    destination: const AppMessageDestination(type: 'user', id: 'recipient-1'),
    title: title,
    summary: summary,
    target: AppMessageTarget(
      targetType: 'post',
      targetId: 'post-1',
      routePath: routePath,
    ),
    read: read,
    createdAt: DateTime.utc(2026, 7, 19, 8),
  );
}

Widget _scopedApp(_FakeAppMessageFacet facet) {
  return ProviderScope(
    overrides: [
      chatRepositoryCompositionProvider.overrideWithValue(MockChatRepository()),
      greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
      visitRecorderServiceProvider.overrideWithValue(
        _NoopVisitRecorderService(),
      ),
      appMessageQueryProvider.overrideWithValue(facet),
      appMessageCommandWriterProvider.overrideWithValue(facet),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(
            path: '/content/posts/:id',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('post-detail-page')),
          ),
        ],
      ),
    ),
  );
}

Future<void> _openNotificationTab(WidgetTester tester) async {
  await tester.tap(find.text(ChatText.chatNotifications));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('通知维度只渲染云端 AppMessage inbox 行', (tester) async {
    final facet = _FakeAppMessageFacet(<AppMessage>[
      _interactionMessage(
        messageId: 'msg-1',
        title: '新的评论',
        summary: '评论了你的作品',
      ),
      _interactionMessage(
        messageId: 'msg-2',
        title: '收到点赞',
        summary: '赞了你的作品',
        read: true,
      ),
    ]);
    await tester.pumpWidget(_scopedApp(facet));
    await tester.pumpAndSettle();

    await _openNotificationTab(tester);

    expect(facet.listCalls, greaterThan(0));
    expect(find.text('新的评论'), findsOneWidget);
    expect(find.text('评论了你的作品'), findsOneWidget);
    expect(find.text('收到点赞'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('chat-notification-row-msg-1')),
      findsOneWidget,
    );
  });

  testWidgets('点击通知行按 target 路由并推进已读', (tester) async {
    final facet = _FakeAppMessageFacet(<AppMessage>[
      _interactionMessage(
        messageId: 'msg-1',
        title: '新的评论',
        summary: '评论了你的作品',
      ),
    ]);
    await tester.pumpWidget(_scopedApp(facet));
    await tester.pumpAndSettle();
    await _openNotificationTab(tester);

    await tester.tap(
      find.byKey(const ValueKey<String>('chat-notification-row-msg-1')),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('post-detail-page')), findsOneWidget);
    expect(facet.readMessageIds, contains('msg-1'));
  });

  testWidgets('已读通知点击不重复调用 ReadAppMessage', (tester) async {
    final facet = _FakeAppMessageFacet(<AppMessage>[
      _interactionMessage(
        messageId: 'msg-read',
        title: '收到点赞',
        summary: '赞了你的作品',
        read: true,
      ),
    ]);
    await tester.pumpWidget(_scopedApp(facet));
    await tester.pumpAndSettle();
    await _openNotificationTab(tester);

    await tester.tap(
      find.byKey(const ValueKey<String>('chat-notification-row-msg-read')),
    );
    await tester.pumpAndSettle();

    expect(facet.readMessageIds, isEmpty);
  });

  testWidgets('通知胶囊未读徽标来自 GetAppMessageUnreadCount', (tester) async {
    final facet = _FakeAppMessageFacet(<AppMessage>[
      _interactionMessage(
        messageId: 'msg-1',
        title: '新的评论',
        summary: '评论了你的作品',
      ),
      _interactionMessage(messageId: 'msg-2', title: '收到点赞', summary: '赞了你的作品'),
    ]);
    await tester.pumpWidget(_scopedApp(facet));
    await tester.pumpAndSettle();

    expect(facet.unreadCalls, greaterThan(0));
    expect(find.text('2'), findsWidgets);
  });

  testWidgets('无通知时展示独立空态而非回退拼接', (tester) async {
    final facet = _FakeAppMessageFacet(<AppMessage>[]);
    await tester.pumpWidget(_scopedApp(facet));
    await tester.pumpAndSettle();
    await _openNotificationTab(tester);

    expect(find.text(ChatText.noReminderMessages), findsOneWidget);
  });
}
