@Tags(<String>['serial'])
library;

// 消息首页（Inbox）打开首帧与滚动的性能预算契约（固定 seed 500 会话）。
//
// 预算数值唯一声明于 test/support/runtime/performance/performance_budget_probe.dart
// 的 MessageRuntimePerformanceBudgets；本测试不承载第二份预算值。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-001.t1
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/performance/performance_budget_probe.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

const _seededConversationCount = 500;
const _scrollSampleCount = 24;

/// 固定 seed 的 500 会话：标题、预览与成员全部确定性生成。
List<Map<String, dynamic>> _inboxConversations() {
  return <Map<String, dynamic>>[
    for (var index = 1; index <= _seededConversationCount; index++)
      <String, Object?>{
        'id': 'fixture_conv_inbox_$index',
        'type': 'direct',
        'conversationType': 'directConversation',
        'title': '收件箱预算会话 $index',
        'memberIds': <String>[
          chatCurrentUserProfileId(),
          'fixture_user_inbox_$index',
        ],
        'avatarUrl': '',
        'creatorId': chatCurrentUserProfileId(),
        'maxSeq': 1,
        'memberCount': 2,
        'maxGroupSize': 2,
        'receiptEnabled': true,
        'lastMessagePreview': '收件箱预算样本消息 $index',
        'lastMessageTime': '2026-06-10T10:00:00Z',
        'messageCount': 1,
        'status': 'active',
      },
  ];
}

Widget _inboxApp() {
  return ProviderScope(
    retry: (_, _) => null,
    overrides: [
      ...chatTestRepositoryOverrides(seedConversations: _inboxConversations()),
      greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
      visitRecorderServiceProvider.overrideWithValue(
        _NoopVisitRecorderService(),
      ),
      appMessageQueryProvider.overrideWithValue(_EmptyAppMessageFacet()),
      appMessageCommandWriterProvider.overrideWithValue(
        _EmptyAppMessageFacet(),
      ),
      isDarkProvider.overrideWithValue(false),
    ],
    child: MaterialApp.router(
      theme: AppTheme.lightTheme,
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('500 会话量级消息首页打开首帧与滚动在声明预算内', (tester) async {
    // —— 打开预算：pumpWidget → 首行会话可见 wall time。 ——
    final openProbe = PerformanceBudgetProbe();
    await openProbe.measure(() async {
      await tester.pumpWidget(_inboxApp());
      var firstRowVisible = false;
      for (var i = 0; i < 60 && !firstRowVisible; i++) {
        await tester.pump(const Duration(milliseconds: 50));
        firstRowVisible = find.textContaining('收件箱预算会话').evaluate().isNotEmpty;
      }
      expect(firstRowVisible, isTrue, reason: '消息首页必须渲染出首行会话');
    });
    expectWithinBudgetMs(
      label: '打开消息首页到首行会话可见',
      actualMs: openProbe.medianMs,
      budgetMs: MessageRuntimePerformanceBudgets.inboxOpenToFirstRowBudgetMs,
    );

    // —— 滚动预算：重复采样单次滚动交互（手势 + 一帧）wall time。 ——
    final scrollProbe = PerformanceBudgetProbe();
    final scrollable = find.byType(Scrollable).first;
    await tester.drag(scrollable, const Offset(0, -240));
    await tester.pump();
    for (var i = 0; i < _scrollSampleCount; i++) {
      final direction = i.isEven ? -240.0 : 240.0;
      await scrollProbe.measure(() async {
        await tester.drag(scrollable, Offset(0, direction));
        await tester.pump();
      });
    }
    expectWithinBudgetMs(
      label: '消息首页滚动中位帧',
      actualMs: scrollProbe.medianMs,
      budgetMs: MessageRuntimePerformanceBudgets.inboxScrollMedianPumpBudgetMs,
    );
    expectWithinRatioBudget(
      label: '消息首页滚动 jank 比',
      actualRatio: scrollProbe.jankRatio(
        MessageRuntimePerformanceBudgets.scrollJankFrameThresholdMs,
      ),
      budgetRatio: MessageRuntimePerformanceBudgets.scrollJankRatioBudget,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  _NoopVisitRecorderService() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

final class _EmptyAppMessageFacet
    implements AppMessageQuery, AppMessageCommandWriter {
  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async => AppMessageInboxSlice(items: const <AppMessage>[]);

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async =>
      throw StateError('empty app message inbox');

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async => AppMessageUnreadCountSlice(unreadCount: 0);

  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) async =>
      throw StateError('empty app message inbox');

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) async =>
      throw StateError('empty app message inbox');
}
