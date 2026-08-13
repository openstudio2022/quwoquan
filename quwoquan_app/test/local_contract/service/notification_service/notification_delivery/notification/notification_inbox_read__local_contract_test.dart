// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

/// UA 旅程（interaction-notification-inbox GWT-001）：
/// 用户打开消息页 → 看到通知未读徽标 → 切通知维度 → 点击通知行 →
/// 跳转目标对象且已读推进 → 未读徽标收敛。
final class _JourneyAppMessageFacet
    implements AppMessageQuery, AppMessageCommandWriter {
  final List<AppMessage> _messages = <AppMessage>[
    AppMessage(
      messageId: 'ua-msg-1',
      userId: 'ua-user',
      messageType: NotificationType.content,
      source: 'comment',
      sourceId: 'cmt-ua-1',
      destination: const AppMessageDestination(type: 'user', id: 'ua-user'),
      title: '新的评论',
      summary: '评论了你的作品',
      target: const AppMessageTarget(
        targetType: 'post',
        targetId: 'post-ua-1',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 7, 19, 8),
    ),
  ];

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('user_acceptance.page.chatList.notification_inbox_read_journey', (
    tester,
  ) async {
    final facet = _JourneyAppMessageFacet();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...chatTestRepositoryOverrides(),
          greetingRepositoryProvider.overrideWithValue(
            alphaGreetingRepository(),
          ),
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
                path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
                  '{workId}',
                  ':workId',
                ),
                builder: (_, state) => Scaffold(
                  key: const ValueKey('ua-post-detail'),
                  body: Text('post ${state.pathParameters['workId']}'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 未读徽标可见（通知胶囊数字 1）。
    expect(find.text('1'), findsWidgets);

    // 进入通知维度并看到真实通知行。
    await tester.tap(find.text(ChatText.chatNotifications));
    await tester.pumpAndSettle();
    expect(find.text('新的评论'), findsOneWidget);

    // 点击通知行：跳转目标对象详情。
    await tester.tap(
      find.byKey(const ValueKey<String>('chat-notification-row-ua-msg-1')),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('ua-post-detail')), findsOneWidget);

    // 已读状态持久推进：inbox 中该行已读，未读数收敛为 0。
    final unread = await facet.getUnreadCount(GetAppMessageUnreadCountQuery());
    expect(unread.unreadCount, 0);
    final message = await facet.getAppMessage(
      GetAppMessageQuery(messageId: 'ua-msg-1'),
    );
    expect(message.read, isTrue);
    expect(message.readAt, isNotNull);
  });
}
