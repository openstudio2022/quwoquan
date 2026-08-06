// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/assistant_schedule_tasks_provider.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/application/connector_management_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/presentation/assistant_skill_center_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/runtime/codec/canonical_digest_fixture.dart';

final _calendarReleaseDigest = canonicalFixtureSha256(const <String, Object?>{
  'connectorId': 'system_calendar',
  'capabilities': <String>['calendar.event.create'],
  'authorizationMode': 'device_native',
});

class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}

Widget _buildApp(
  InMemoryAssistantFacets repository, {
  required VisitRecorderService visitRecorder,
  List<Override> extraOverrides = const <Override>[],
  List<AssistantSessionWire> recentSessions = const <AssistantSessionWire>[],
  AssistantConnectorCenterState connectorState =
      const AssistantConnectorCenterState(
        definitions: <ConnectorDefinition>[],
        connections: <ConnectorConnectionView>[],
        invocations: <ConnectorInvocationView>[],
      ),
}) {
  return ProviderScope(
    overrides: [
      ...assistantFacetOverrides(repository),
      visitRecorderServiceProvider.overrideWithValue(visitRecorder),
      assistantRecentSessionsProvider.overrideWith(
        (ref) async => recentSessions,
      ),
      assistantConnectorCenterProvider.overrideWith(
        (ref) async => connectorState,
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

class _FailingSettingAssistantFacets extends InMemoryAssistantFacets {
  bool failSettingUpdates = false;

  @override
  Future<PutSkillUserSettingReceipt> putSkillUserSetting({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
    required String clientRequestId,
  }) {
    if (failSettingUpdates) {
      throw StateError('setting update failed');
    }
    return super.putSkillUserSetting(
      skillId: skillId,
      status: status,
      configurationData: configurationData,
      configurationSchemaDigest: configurationSchemaDigest,
      memoryPolicy: memoryPolicy,
      connectorConnectionRefs: connectorConnectionRefs,
      expectedRevision: expectedRevision,
      clientRequestId: clientRequestId,
    );
  }
}

class _RecordingConnectorManagementFacet implements ConnectorManagementFacet {
  String? revokedConnectionId;
  int? revokedExpectedRevision;

  @override
  Future<ConnectorConnectionView> revokeConnectorConnection({
    required String connectionId,
    required int expectedRevision,
    required String idempotencyKey,
  }) async {
    revokedConnectionId = connectionId;
    revokedExpectedRevision = expectedRevision;
    return ConnectorConnectionView(
      connectionId: connectionId,
      connectorId: 'system_calendar',
      grantedCapabilities: const <String>['calendar.event.create'],
      status: ConnectorConnectionStatus.revoked,
      freshnessAt: DateTime.utc(2026, 8, 2, 9),
      revokedAt: DateTime.utc(2026, 8, 2, 9, 1),
      revision: expectedRevision + 1,
      createdAt: DateTime.utc(2026, 8, 1, 8),
      updatedAt: DateTime.utc(2026, 8, 2, 9, 1),
    );
  }

  @override
  Future<ConnectorConnectionView> createConnectorConnection({
    required String connectorId,
    required List<String> requestedCapabilities,
    required String grantReceiptRef,
    required String idempotencyKey,
  }) => throw UnsupportedError('not used by this test');

  @override
  Future<ConnectorConnectionView> getConnectorConnection({
    required String connectionId,
  }) => throw UnsupportedError('not used by this test');

  @override
  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  }) => throw UnsupportedError('not used by this test');

  @override
  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  }) => throw UnsupportedError('not used by this test');

  @override
  Future<List<ConnectorConnectionView>> listConnectorConnections({
    int limit = 64,
  }) async => const <ConnectorConnectionView>[];

  @override
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = 64,
  }) async => const <ConnectorDefinition>[];

  @override
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = 32,
  }) async => const <ConnectorInvocationView>[];
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
  testWidgets('技能启用状态与主动订阅分别展示且任务只保留进行中', (tester) async {
    final repository = InMemoryAssistantFacets();
    final stockCatalog = (await repository.listSkillCatalog()).singleWhere(
      (item) => item.skillId == 'stock_sentinel',
    );
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
            (ref) async => const <AssistantTaskItemView>[
              AssistantTaskItemView(
                taskId: 'task_pending',
                title: '整理真实任务',
                description: '来自云端任务',
                status: 'pending',
                updatedAt: '2026-08-02T12:00:00Z',
              ),
              AssistantTaskItemView(
                taskId: 'task_done',
                title: '已完成任务',
                status: 'completed',
                updatedAt: '2026-08-02T12:00:00Z',
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
        '${stockCatalog.catalogGroup.displayText} · '
        '${AssistantText.assistantSkillEnabled}',
      ),
      findsWidgets,
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
      find.byKey(const ValueKey<String>('assistant_skill_data_control_action')),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantSkillDataControlAction),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>('assistant_skill_lifecycle_stock_sentinel'),
      ),
      findsOneWidget,
    );
    expect(
      (await repository.listSkillSubscriptions()).single.status,
      SkillSubscriptionStatus.active,
    );
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page('assistant_skills').targetKey),
    );
  });

  testWidgets('连接的应用只展示脱敏状态与最近活动', (tester) async {
    final connectorState = AssistantConnectorCenterState(
      definitions: <ConnectorDefinition>[
        ConnectorDefinition(
          connectorId: 'system_calendar',
          displayName: '系统日历',
          description: '在用户确认后写入行程事件',
          capabilities: const <String>['calendar.event.create'],
          authorizationMode: ConnectorAuthorizationMode.deviceNative,
          confirmationPolicy: ConnectorConfirmationPolicy.userConfirmation,
          dataClassification: ConnectorDataClassification.private,
          supportedSurfaceKinds: const <String>['personal'],
          status: ConnectorDefinitionStatus.active,
          releaseDigest: _calendarReleaseDigest,
          publishedAt: DateTime.utc(2026, 8, 2, 8),
        ),
      ],
      connections: <ConnectorConnectionView>[
        ConnectorConnectionView(
          connectionId: 'connection_calendar',
          connectorId: 'system_calendar',
          grantedCapabilities: const <String>['calendar.event.create'],
          status: ConnectorConnectionStatus.active,
          freshnessAt: DateTime.utc(2026, 8, 2, 9),
          revision: 3,
          createdAt: DateTime.utc(2026, 8, 1, 8),
          updatedAt: DateTime.utc(2026, 8, 2, 9),
        ),
      ],
      invocations: <ConnectorInvocationView>[
        ConnectorInvocationView(
          invocationId: 'invocation_calendar',
          connectionId: 'connection_calendar',
          capability: 'calendar.event.create',
          status: ConnectorInvocationStatus.completed,
          recoveryAction: 'none',
          revision: 2,
          createdAt: DateTime.utc(2026, 8, 2, 8, 59),
          updatedAt: DateTime.utc(2026, 8, 2, 9),
          completedAt: DateTime.utc(2026, 8, 2, 9),
        ),
      ],
    );
    await tester.pumpWidget(
      _buildApp(
        InMemoryAssistantFacets(),
        visitRecorder: _CapturingVisitRecorder(),
        connectorState: connectorState,
      ),
    );
    await tester.pumpAndSettle();

    await _scrollTo(tester, find.text('系统日历'));
    expect(
      find.text(AssistantText.assistantConnectorConnected),
      findsOneWidget,
    );
    expect(find.textContaining('calendar.event.create'), findsOneWidget);
    expect(
      find.byKey(
        const ValueKey<String>('assistant_connector_revoke_system_calendar'),
      ),
      findsOneWidget,
    );
    expect(find.textContaining('credential'), findsNothing);
    expect(find.textContaining('grantReceipt'), findsNothing);
  });

  testWidgets('断开连接确认后按当前 revision 调用 typed revoke', (tester) async {
    final facet = _RecordingConnectorManagementFacet();
    final connectorState = AssistantConnectorCenterState(
      definitions: <ConnectorDefinition>[
        ConnectorDefinition(
          connectorId: 'system_calendar',
          displayName: '系统日历',
          description: '在用户确认后写入行程事件',
          capabilities: const <String>['calendar.event.create'],
          authorizationMode: ConnectorAuthorizationMode.deviceNative,
          confirmationPolicy: ConnectorConfirmationPolicy.userConfirmation,
          dataClassification: ConnectorDataClassification.private,
          supportedSurfaceKinds: const <String>['personal'],
          status: ConnectorDefinitionStatus.active,
          releaseDigest: _calendarReleaseDigest,
          publishedAt: DateTime.utc(2026, 8, 2, 8),
        ),
      ],
      connections: <ConnectorConnectionView>[
        ConnectorConnectionView(
          connectionId: 'connection_calendar',
          connectorId: 'system_calendar',
          grantedCapabilities: const <String>['calendar.event.create'],
          status: ConnectorConnectionStatus.active,
          freshnessAt: DateTime.utc(2026, 8, 2, 9),
          revision: 3,
          createdAt: DateTime.utc(2026, 8, 1, 8),
          updatedAt: DateTime.utc(2026, 8, 2, 9),
        ),
      ],
      invocations: const <ConnectorInvocationView>[],
    );
    await tester.pumpWidget(
      _buildApp(
        InMemoryAssistantFacets(),
        visitRecorder: _CapturingVisitRecorder(),
        connectorState: connectorState,
        extraOverrides: <Override>[
          assistantConnectorManagementFacetProvider.overrideWithValue(facet),
        ],
      ),
    );
    await tester.pumpAndSettle();

    final revoke = find.byKey(
      const ValueKey<String>('assistant_connector_revoke_system_calendar'),
    );
    await _scrollTo(tester, revoke);
    await tester.tap(revoke);
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantConnectorDisconnectConfirmTitle),
      findsOneWidget,
    );
    await tester.tap(
      find.widgetWithText(
        CupertinoDialogAction,
        AssistantText.assistantConnectorDisconnect,
      ),
    );
    await tester.pumpAndSettle();

    expect(facet.revokedConnectionId, 'connection_calendar');
    expect(facet.revokedExpectedRevision, 3);
  });

  testWidgets('缺少 Setting 时按 package 默认启用，主开关只写 Setting', (tester) async {
    final repository = InMemoryAssistantFacets();
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final travelToggle = find.byKey(
      const ValueKey<String>('assistant_skill_toggle_travel_journey_manager'),
    );
    await _scrollTo(tester, travelToggle);
    expect(tester.widget<CupertinoSwitch>(travelToggle).value, isTrue);
    await tester.tap(travelToggle);
    await tester.pumpAndSettle();

    final settings = await repository.listSkillUserSettings();
    expect(settings.single.skillId, 'travel_journey_manager');
    expect(settings.single.status, SkillUserSettingStatus.disabled);
    expect(await repository.listSkillSubscriptions(), isEmpty);
  });

  testWidgets('任务区错误态可见', (tester) async {
    var taskLoadCount = 0;
    await tester.pumpWidget(
      _buildApp(
        InMemoryAssistantFacets(),
        visitRecorder: _CapturingVisitRecorder(),
        extraOverrides: <Override>[
          assistantScheduleTasksProvider.overrideWith((ref) {
            taskLoadCount += 1;
            if (taskLoadCount == 1) {
              return Future<List<AssistantTaskItemView>>.error(
                StateError('tasks unavailable'),
              );
            }
            return Future<List<AssistantTaskItemView>>.value(
              const <AssistantTaskItemView>[],
            );
          }),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorCard), findsWidgets);

    await tester.tap(find.text(SearchText.reload).first);
    await tester.pumpAndSettle();

    expect(taskLoadCount, 2);
    expect(
      find.text(AssistantText.assistantSkillCenterNoOngoingTasks),
      findsOneWidget,
    );
  });

  testWidgets('技能切换失败可见且状态按远端值回弹', (tester) async {
    final repository = _FailingSettingAssistantFacets();
    repository.failSettingUpdates = true;
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
    expect(find.text(ContentText.submitNotCompleted), findsOneWidget);
    expect(await repository.listSkillUserSettings(), isEmpty);
    expect(tester.widget<CupertinoSwitch>(toggleFinder).value, isTrue);
  });

  testWidgets('主动提醒开关只更新既有 Subscription', (tester) async {
    final repository = InMemoryAssistantFacets();
    final first = await repository.createSkillSubscription(
      skillId: 'stock_sentinel',
      domainId: 'finance',
      rawText: '关注公司公告',
      clientRequestId: 'create-stock-proactive-first',
    );
    final second = await repository.createSkillSubscription(
      skillId: 'stock_sentinel',
      domainId: 'finance',
      rawText: '关注价格变化',
      clientRequestId: 'create-stock-proactive-second',
    );
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final firstToggle = find.byKey(
      ValueKey<String>('assistant_skill_subscription_${first.subscriptionId}'),
    );
    final secondToggle = find.byKey(
      ValueKey<String>('assistant_skill_subscription_${second.subscriptionId}'),
    );
    await _scrollTo(tester, firstToggle);
    expect(tester.widget<CupertinoSwitch>(firstToggle).value, isTrue);
    expect(tester.widget<CupertinoSwitch>(secondToggle).value, isTrue);
    await tester.tap(firstToggle);
    await tester.pumpAndSettle();

    final subscriptions = await repository.listSkillSubscriptions();
    expect(
      subscriptions
          .singleWhere((item) => item.subscriptionId == first.subscriptionId)
          .status,
      SkillSubscriptionStatus.paused,
    );
    expect(
      subscriptions
          .singleWhere((item) => item.subscriptionId == second.subscriptionId)
          .status,
      SkillSubscriptionStatus.active,
    );
    expect(await repository.listSkillUserSettings(), isEmpty);
  });

  testWidgets('未配置主动规则时按用户输入创建带时区的 Subscription', (tester) async {
    final repository = InMemoryAssistantFacets();
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final addReminder = find.byKey(
      const ValueKey<String>(
        'assistant_skill_subscription_add_travel_journey_manager',
      ),
    );
    await _scrollTo(tester, addReminder);
    await tester.tap(addReminder);
    await tester.pumpAndSettle();

    expect(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_sheet'),
      ),
      findsOneWidget,
    );
    await tester.enterText(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_topic'),
      ),
      '关注杭州行程天气、交通和集合变化',
    );
    final save = find.byKey(
      const ValueKey<String>('assistant_skill_subscription_setup_save'),
    );
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();

    final subscription = (await repository.listSkillSubscriptions()).single;
    expect(subscription.skillId, 'travel_journey_manager');
    expect(subscription.domainId, 'travel');
    expect(subscription.searchQueryPlan.rawText, '关注杭州行程天气、交通和集合变化');
    expect(subscription.trigger.cron, '0 8 * * *');
    expect(subscription.trigger.timezone, 'Asia/Shanghai');
    expect(subscription.status, SkillSubscriptionStatus.active);
  });

  testWidgets('旅行 Skill 按目录声明一次授权完整 scope 集合', (tester) async {
    final repository = InMemoryAssistantFacets();
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final consentButton = find.byKey(
      const ValueKey<String>('assistant_skill_consent_travel_journey_manager'),
    );
    await _scrollTo(tester, consentButton);
    await tester.tap(consentButton);
    await tester.pumpAndSettle();

    final consent = (await repository.listConsents()).single;
    expect(consent.grantedScopes, <String>[
      'assistant.memory.preferences.read',
      'travel.trip.read',
    ]);
  });

  testWidgets('点开 Skill 后按需读取 package schema 并保存设置', (tester) async {
    final repository = InMemoryAssistantFacets();
    final travelCatalog = (await repository.listSkillCatalog()).singleWhere(
      (item) => item.skillId == 'travel_journey_manager',
    );
    await tester.pumpWidget(
      _buildApp(repository, visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    final detailButton = find.byKey(
      const ValueKey<String>('assistant_skill_detail_travel_journey_manager'),
    );
    await _scrollTo(tester, detailButton);
    await tester.tap(detailButton);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('assistant_skill_detail_sheet')),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantSkillRequiredConsentScopes),
      findsOneWidget,
    );
    for (final label in travelCatalog.consentScopeLabels) {
      expect(find.textContaining(label.displayText), findsWidgets);
    }
    if (travelCatalog.consentScopeLabels.any(
      (label) => !travelCatalog.requiredConsentScopes.contains(label.id),
    )) {
      expect(
        find.text(AssistantText.assistantSkillOptionalConsentScopes),
        findsOneWidget,
      );
    }
    expect(
      find.textContaining('assistant.memory.preferences.read'),
      findsNothing,
    );
    expect(find.textContaining('travel.trip.read'), findsNothing);
    expect(find.text('旅行偏好'), findsOneWidget);
    await tester.tap(
      find.byKey(
        const ValueKey<String>('assistant_skill_setup_travelPace_balanced'),
      ),
    );
    await tester.enterText(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_setup_input_reminderLeadMinutes',
        ),
      ),
      '30',
    );
    final saveButton = find.byKey(
      const ValueKey<String>('assistant_skill_setup_save'),
    );
    await tester.ensureVisible(saveButton);
    await tester.pumpAndSettle();
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    final setting = await repository.getSkillUserSetting(
      skillId: 'travel_journey_manager',
    );
    expect(setting.configurationData, <String, Object?>{
      'travelPace': 'balanced',
      'reminderLeadMinutes': 30,
    });
    expect(setting.status, SkillUserSettingStatus.enabled);
  });

  testWidgets('最近会话来自云端会话列表且可展开收起', (tester) async {
    // R-ASSIST-001：最近会话唯一数据源是 ListAssistantSessions 云端查询面。
    final sessions = List<AssistantSessionWire>.generate(
      5,
      (index) => AssistantSessionWire(
        sessionId: 'conv_$index',
        userId: 'user_test',
        summary: '真实会话 ${index + 1}',
        createdAt: '2026-07-20T09:00:00Z',
        updatedAt: '2026-07-20T09:0$index:00Z',
      ),
    );
    await tester.pumpWidget(
      _buildApp(
        InMemoryAssistantFacets(),
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
    expect(find.text(CommunityText.collapse), findsOneWidget);

    await tester.tap(sessionsToggle);
    await tester.pump();
    expect(find.text('真实会话 4'), findsNothing);
  });
}
