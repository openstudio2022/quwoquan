import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';

import '../../../../support/cloud_services/assistant_facet_overrides.dart';

class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}

Widget _buildApp(
  AlphaAssistantFacets repository, {
  required VisitRecorderService visitRecorder,
  List<Override> extraOverrides = const <Override>[],
  List<AssistantConversationWire> recentSessions =
      const <AssistantConversationWire>[],
}) {
  return ProviderScope(
    overrides: [
      ...alphaAssistantFacetOverrides(repository),
      visitRecorderServiceProvider.overrideWithValue(visitRecorder),
      assistantRecentSessionsProvider.overrideWith(
        (ref) async => recentSessions,
      ),
      ...extraOverrides,
    ],
    child: MaterialApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: AssistantSkillCenterPage(onBack: () {}),
    ),
  );
}

class _FailingStatusAssistantFacets extends AlphaAssistantFacets {
  bool failStatusUpdates = false;

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  }) {
    if (failStatusUpdates) {
      throw StateError('status update failed');
    }
    return super.updateSkillSubscriptionStatus(
      subscriptionId: subscriptionId,
      status: status,
      clientRequestId: clientRequestId,
    );
  }
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    240,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('技能中心只展示真实订阅与进行中任务', (tester) async {
    final repository = AlphaAssistantFacets();
    final recorder = _CapturingVisitRecorder();
    await repository.createSkillSubscription(
      skillId: 'stock_sentinel',
      domainId: 'finance',
      rawText: '用户提交的订阅条件',
      clientRequestId: 'create-stock-sentinel-widget',
    );

    await tester.pumpWidget(
      _buildApp(
        repository,
        visitRecorder: recorder,
        extraOverrides: <Override>[
          assistantScheduleTasksProvider.overrideWith(
            (ref) async => const <AssistantUserTaskView>[
              AssistantUserTaskView(
                taskId: 'task_pending',
                title: '整理真实任务',
                description: '来自云端任务',
                status: 'pending',
              ),
              AssistantUserTaskView(
                taskId: 'task_done',
                title: '已完成任务',
                status: 'completed',
              ),
            ],
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('股票哨兵'), findsOneWidget);
    expect(
      find.text(
        '${AssistantText.assistantSkillCategoryKnowledge} · '
        '${AssistantText.assistantSkillSubscribed}',
      ),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantSkillCenterOngoingTasksTitle),
      findsOneWidget,
    );
    expect(find.text('整理真实任务'), findsOneWidget);
    expect(find.text('已完成任务'), findsNothing);
    expect(find.text('极简模式'), findsNothing);
    expect(find.text('风险策略'), findsNothing);
    expect(find.text('场景闸门'), findsNothing);
    expect(find.text('stock_sentinel'), findsNothing);
    expect(find.text('finance'), findsNothing);
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page('assistant_skills').targetKey),
    );
  });

  testWidgets('未配置订阅入口时给出结构化提示且不合成订阅', (tester) async {
    final repository = AlphaAssistantFacets();
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final travelToggle = find.byKey(
      const ValueKey<String>('assistant_skill_toggle_travel_journey_manager'),
    );
    await _scrollTo(tester, travelToggle);
    await tester.tap(travelToggle);
    await tester.pumpAndSettle();

    expect(
      find.text(AssistantText.assistantSkillSubscriptionUnavailableMessage),
      findsOneWidget,
    );
    expect(await repository.listSkillSubscriptions(), isEmpty);
  });

  testWidgets('任务区错误态可见', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        AlphaAssistantFacets(),
        visitRecorder: _CapturingVisitRecorder(),
        extraOverrides: <Override>[
          assistantScheduleTasksProvider.overrideWith(
            (ref) => Future<List<AssistantUserTaskView>>.error(
              StateError('tasks unavailable'),
            ),
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.sectionLoadFailedTitleDefault),
      findsWidgets,
    );
    expect(find.text(UITextConstants.tryAgain), findsWidgets);
  });

  testWidgets('技能切换失败可见且状态按远端值回弹', (tester) async {
    final repository = _FailingStatusAssistantFacets();
    await repository.createSkillSubscription(
      skillId: 'stock_sentinel',
      domainId: 'finance',
      rawText: '用户提交的订阅条件',
      clientRequestId: 'create-stock-sentinel-failure',
    );
    repository.failStatusUpdates = true;
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final toggleFinder = find.byKey(
      const ValueKey<String>('assistant_skill_toggle_stock_sentinel'),
    );
    await _scrollTo(tester, toggleFinder);
    expect(tester.widget<CupertinoSwitch>(toggleFinder).value, isTrue);

    await tester.tap(toggleFinder);
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(find.text(UITextConstants.submitNotCompleted), findsOneWidget);
    expect(
      (await repository.listSkillSubscriptions()).single.status,
      SkillSubscriptionStatus.active,
    );
    expect(tester.widget<CupertinoSwitch>(toggleFinder).value, isTrue);
  });

  testWidgets('最近会话来自云端会话列表且可展开收起', (tester) async {
    // R-ASSIST-001：最近会话唯一数据源是 ListAssistantConversations 云端查询面。
    final sessions = List<AssistantConversationWire>.generate(
      5,
      (index) => AssistantConversationWire(
        conversationId: 'conv_$index',
        userId: 'user_test',
        summary: '真实会话 ${index + 1}',
        createdAt: '2026-07-20T09:00:00Z',
        updatedAt: '2026-07-20T09:0$index:00Z',
      ),
    );
    await tester.pumpWidget(
      _buildApp(
        AlphaAssistantFacets(),
        visitRecorder: _CapturingVisitRecorder(),
        recentSessions: sessions,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('真实会话 4'), findsNothing);
    final sessionsToggle = find.byKey(
      const ValueKey<String>('assistant_recent_sessions_toggle'),
    );
    await _scrollTo(tester, sessionsToggle);
    await tester.tap(sessionsToggle);
    await tester.pump();
    expect(find.text('真实会话 4'), findsOneWidget);
    expect(find.text(UITextConstants.collapse), findsOneWidget);

    await tester.tap(sessionsToggle);
    await tester.pump();
    expect(find.text('真实会话 4'), findsNothing);
  });
}
