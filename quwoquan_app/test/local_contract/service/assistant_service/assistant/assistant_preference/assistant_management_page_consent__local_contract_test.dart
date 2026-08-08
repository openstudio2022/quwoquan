// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-003.t2

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/presentation/assistant_management_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}

class _AssistantPreferenceFacet implements AssistantPreferenceFacet {
  _AssistantPreferenceFacet({
    List<AssistantPreference> initial = const <AssistantPreference>[],
    this.listFailuresRemaining = 0,
    this.setFailuresRemaining = 0,
    this.revokeFailuresRemaining = 0,
    this.restoreFailuresRemaining = 0,
  }) : _items = <AssistantPreference>[...initial];

  final List<AssistantPreference> _items;
  int listFailuresRemaining;
  int setFailuresRemaining;
  int revokeFailuresRemaining;
  int restoreFailuresRemaining;
  final List<AssistantPreferenceStatus> requestedStatuses =
      <AssistantPreferenceStatus>[];
  final List<({AssistantPreferenceKind kind, String value})> setAttempts = [];
  final List<String> revokeAttempts = [];
  final List<String> restoreAttempts = [];

  @override
  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    if (listFailuresRemaining > 0) {
      listFailuresRemaining -= 1;
      throw StateError('preferences unavailable');
    }
    requestedStatuses.add(status);
    return _items
        .where(
          (item) =>
              item.status == status && (scope == null || item.scope == scope),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  }) async {
    setAttempts.add((kind: kind, value: value));
    if (setFailuresRemaining > 0) {
      setFailuresRemaining -= 1;
      throw StateError('set preference unavailable');
    }
    final existingIndex = _items.indexWhere(
      (item) =>
          item.scope == scope &&
          item.sessionId == (sessionId.isEmpty ? null : sessionId) &&
          item.kind == kind,
    );
    final existing = existingIndex < 0 ? null : _items[existingIndex];
    final preference = AssistantPreference(
      preferenceId: existing?.preferenceId ?? 'preference_${_items.length + 1}',
      userId: 'owner',
      scope: scope,
      sessionId: sessionId.isEmpty ? null : sessionId,
      kind: kind,
      value: value,
      sourceType: sourceType,
      sourceSessionId: sourceSessionId.isEmpty ? null : sourceSessionId,
      confirmedAt: confirmed ? '2026-07-20T08:00:00Z' : null,
      status: AssistantPreferenceStatus.active,
      createdAt: '2026-07-20T08:00:00Z',
      updatedAt: '2026-07-20T08:00:00Z',
      version: (existing?.version ?? 0) + 1,
    );
    _items
      ..removeWhere(
        (item) =>
            item.scope == preference.scope &&
            item.sessionId == preference.sessionId &&
            item.kind == preference.kind,
      )
      ..add(preference);
    return preference;
  }

  @override
  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    revokeAttempts.add(preferenceId);
    if (revokeFailuresRemaining > 0) {
      revokeFailuresRemaining -= 1;
      throw StateError('revoke preference unavailable');
    }
    final index = _items.indexWhere(
      (item) => item.preferenceId == preferenceId,
    );
    final current = _items[index];
    final revoked = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.revoked,
      revokedAt: '2026-07-20T08:01:00Z',
      revocationDeadline: '2099-07-20T08:11:00Z',
      createdAt: current.createdAt,
      updatedAt: '2026-07-20T08:01:00Z',
      version: current.version + 1,
    );
    _items[index] = revoked;
    return revoked;
  }

  @override
  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    restoreAttempts.add(preferenceId);
    if (restoreFailuresRemaining > 0) {
      restoreFailuresRemaining -= 1;
      throw StateError('restore preference unavailable');
    }
    final index = _items.indexWhere(
      (item) => item.preferenceId == preferenceId,
    );
    final current = _items[index];
    final restored = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.active,
      createdAt: current.createdAt,
      updatedAt: '2026-07-20T08:02:00Z',
      version: current.version + 1,
    );
    _items[index] = restored;
    return restored;
  }
}

Widget _buildApp({
  required VisitRecorderService visitRecorder,
  _AssistantPreferenceFacet? preferenceFacet,
}) {
  final resolvedPreferenceFacet =
      preferenceFacet ?? _AssistantPreferenceFacet();
  return ProviderScope(
    overrides: [
      assistantPreferenceFacetProvider.overrideWithValue(
        resolvedPreferenceFacet,
      ),
      visitRecorderServiceProvider.overrideWithValue(visitRecorder),
    ],
    child: MaterialApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: AssistantManagementPage(onBack: () {}),
    ),
  );
}

AssistantPreference _testPreference({
  String preferenceId = 'preference_retry',
  String value = 'concise',
  AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
}) {
  return AssistantPreference(
    preferenceId: preferenceId,
    userId: 'owner',
    scope: AssistantPreferenceScope.longTerm,
    kind: AssistantPreferenceKind.replyLength,
    value: value,
    sourceType: AssistantPreferenceSourceType.management,
    status: status,
    revokedAt: status == AssistantPreferenceStatus.revoked
        ? '2026-07-20T08:01:00Z'
        : null,
    revocationDeadline: status == AssistantPreferenceStatus.revoked
        ? '2099-07-20T08:11:00Z'
        : null,
    createdAt: '2026-07-20T08:00:00Z',
    updatedAt: '2026-07-20T08:01:00Z',
    version: 1,
  );
}

Future<void> _retryVisiblePreferenceMutation(WidgetTester tester) async {
  final errorCard = tester.widget<AppSectionErrorCard>(
    find.byType(AppSectionErrorCard).first,
  );
  expect(errorCard.semantic.primaryAction?.type, UiErrorActionType.retry);
  await errorCard.onAction!(errorCard.semantic.primaryAction!);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('管理页不维护特殊 Skill 授权开关并指向 Skill Center', (tester) async {
    final recorder = _CapturingVisitRecorder();
    await tester.pumpWidget(_buildApp(visitRecorder: recorder));
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoSwitch), findsNothing);
    expect(find.text(AssistantText.assistantSkillCenter), findsOneWidget);
    expect(find.text('性格选择'), findsNothing);
    expect(find.text('允许读取聊天'), findsNothing);
    expect(find.text('允许访问位置'), findsNothing);
    expect(find.text('系统通知'), findsNothing);
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page('assistant_management').targetKey),
    );
  });

  testWidgets('管理页展示真实显式偏好数据', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: _AssistantPreferenceFacet(
          initial: const <AssistantPreference>[
            AssistantPreference(
              preferenceId: 'preference_1',
              userId: 'owner',
              scope: AssistantPreferenceScope.longTerm,
              kind: AssistantPreferenceKind.tone,
              value: 'warm',
              sourceType: AssistantPreferenceSourceType.management,
              status: AssistantPreferenceStatus.active,
              createdAt: '2026-07-20T08:00:00Z',
              updatedAt: '2026-07-20T08:00:00Z',
              version: 1,
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(AssistantText.assistantMemorySectionTitle),
      findsOneWidget,
    );
    expect(find.text(AssistantText.assistantPreferenceWarm), findsOneWidget);
    expect(
      find.textContaining(AssistantText.assistantPreferenceLongTermScope),
      findsOneWidget,
    );
    expect(find.text('preference_1'), findsNothing);
    expect(find.text('owner'), findsNothing);
  });

  testWidgets('需确认的偏好展示用户确认内容、类型、来源与生效范围', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: _AssistantPreferenceFacet(
          initial: const <AssistantPreference>[
            AssistantPreference(
              preferenceId: 'preference_memory_location',
              userId: 'owner',
              scope: AssistantPreferenceScope.longTerm,
              kind: AssistantPreferenceKind.frequentLocations,
              value: '常从深圳北站出发',
              sourceType: AssistantPreferenceSourceType.sessionConfirmed,
              sourceSessionId: 'asn_private_source',
              confirmedAt: '2026-07-20T07:59:00Z',
              status: AssistantPreferenceStatus.active,
              createdAt: '2026-07-20T08:00:00Z',
              updatedAt: '2026-07-20T08:00:00Z',
              version: 1,
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('常从深圳北站出发'), findsOneWidget);
    expect(
      find.textContaining(AssistantText.assistantMemoryFrequentLocations),
      findsOneWidget,
    );
    expect(
      find.textContaining(AssistantText.assistantMemorySourceConfirmedSession),
      findsOneWidget,
    );
    expect(
      find.textContaining(AssistantText.assistantPreferenceLongTermScope),
      findsOneWidget,
    );
    expect(find.text('asn_private_source'), findsNothing);
  });

  testWidgets('管理页记忆空态明确', (tester) async {
    await tester.pumpWidget(
      _buildApp(visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();

    expect(find.text(AssistantText.assistantMemoryEmpty), findsOneWidget);
  });

  testWidgets('管理页可设置长期回答偏好', (tester) async {
    await tester.pumpWidget(
      _buildApp(visitRecorder: _CapturingVisitRecorder()),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantPreferenceDetailed),
      findsOneWidget,
    );

    await tester.tap(find.text(AssistantText.assistantPreferenceDetailed));
    await tester.pumpAndSettle();

    expect(
      find.text(AssistantText.assistantPreferenceDetailed),
      findsNWidgets(2),
    );
    expect(
      find.textContaining(AssistantText.assistantPreferenceLongTermScope),
      findsOneWidget,
    );
  });

  testWidgets('管理页偏好错误态提供统一重试', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: _AssistantPreferenceFacet(listFailuresRemaining: 1),
      ),
    );
    await tester.pumpAndSettle();

    final errorCard = tester.widget<AppSectionErrorCard>(
      find.byType(AppSectionErrorCard),
    );
    expect(errorCard.semantic.primaryAction, isNotNull);
    await errorCard.onAction!(errorCard.semantic.primaryAction!);
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(find.text(AssistantText.assistantMemoryEmpty), findsOneWidget);
  });

  testWidgets('管理页遗忘偏好后可撤销恢复', (tester) async {
    final preferenceFacet = _AssistantPreferenceFacet(
      initial: const <AssistantPreference>[
        AssistantPreference(
          preferenceId: 'preference_undo',
          userId: 'owner',
          scope: AssistantPreferenceScope.longTerm,
          kind: AssistantPreferenceKind.replyLength,
          value: 'concise',
          sourceType: AssistantPreferenceSourceType.management,
          status: AssistantPreferenceStatus.active,
          createdAt: '2026-07-20T08:00:00Z',
          updatedAt: '2026-07-20T08:00:00Z',
          version: 1,
        ),
      ],
    );
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: preferenceFacet,
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
    );

    await tester.tap(find.text(AssistantText.assistantPreferenceForget));
    await tester.pumpAndSettle();
    // 撤销状态由 Remote 重新查询，刷新或重启后仍保留恢复入口。
    expect(find.text(AssistantText.assistantPreferenceConcise), findsOneWidget);
    expect(
      find.textContaining(AssistantText.assistantPreferenceForgot),
      findsOneWidget,
    );
    expect(find.text(AssistantText.assistantPreferenceUndo), findsOneWidget);
    expect(find.text(AssistantText.assistantPreferenceForget), findsNothing);
    expect(
      preferenceFacet.requestedStatuses.toSet(),
      containsAll(<AssistantPreferenceStatus>{
        AssistantPreferenceStatus.active,
        AssistantPreferenceStatus.revoked,
      }),
    );

    await tester.tap(find.text(AssistantText.assistantPreferenceUndo));
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
    );
    expect(find.text(AssistantText.assistantPreferenceForget), findsOneWidget);
  });

  testWidgets('设置失败保留已确认列表和exact意图，重新读取后可重试同一参数', (tester) async {
    final facet = _AssistantPreferenceFacet(
      initial: [_testPreference()],
      setFailuresRemaining: 1,
    );
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: facet,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(AssistantText.assistantPreferenceDetailed));
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorCard), findsOneWidget);
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
      reason: '失败不得覆盖最后一次已确认列表',
    );
    expect(facet.setAttempts, [
      (kind: AssistantPreferenceKind.replyLength, value: 'detailed'),
    ]);
    final unrelatedAction = tester.widget<CupertinoButton>(
      find.widgetWithText(
        CupertinoButton,
        AssistantText.assistantPreferenceCasual,
      ),
    );
    expect(unrelatedAction.onPressed, isNull, reason: 'pending期间不得覆盖意图');

    await tester.tap(
      find.byKey(
        const ValueKey<String>('assistant_preference_reread_after_failure'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AppSectionErrorCard), findsOneWidget);
    expect(facet.setAttempts, hasLength(1), reason: '重新读取不得重放mutation');

    await _retryVisiblePreferenceMutation(tester);
    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(
      find.text(AssistantText.assistantPreferenceDetailed),
      findsNWidgets(2),
    );
    expect(facet.setAttempts, [
      (kind: AssistantPreferenceKind.replyLength, value: 'detailed'),
      (kind: AssistantPreferenceKind.replyLength, value: 'detailed'),
    ], reason: '重试必须复用exact typed参数');
  });

  testWidgets('typed设置成功但权威回读失败时保留pending直到同意图重试闭合', (tester) async {
    final facet = _AssistantPreferenceFacet(initial: [_testPreference()]);
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: facet,
      ),
    );
    await tester.pumpAndSettle();
    facet.listFailuresRemaining = 1;

    await tester.tap(find.text(AssistantText.assistantPreferenceDetailed));
    await tester.pumpAndSettle();
    expect(find.byType(AppSectionErrorCard), findsOneWidget);
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
      reason: 'mutation ACK不能在authoritative read失败时替换已确认列表',
    );

    await tester.tap(
      find.byKey(
        const ValueKey<String>('assistant_preference_reread_after_failure'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantPreferenceDetailed),
      findsNWidgets(2),
      reason: '只读恢复可以刷新canonical列表',
    );
    expect(
      find.byType(AppSectionErrorCard),
      findsOneWidget,
      reason: '缺typed mutation闭环时pending仍不得静默清除',
    );

    await _retryVisiblePreferenceMutation(tester);
    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(facet.setAttempts, hasLength(2));
  });

  testWidgets('遗忘失败后只允许同preferenceId重试并以revoked列表收敛', (tester) async {
    final facet = _AssistantPreferenceFacet(
      initial: [_testPreference(preferenceId: 'preference_revoke')],
      revokeFailuresRemaining: 1,
    );
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: facet,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(AssistantText.assistantPreferenceForget));
    await tester.pumpAndSettle();
    expect(find.text(AssistantText.assistantPreferenceForget), findsOneWidget);
    expect(facet.revokeAttempts, ['preference_revoke']);

    await _retryVisiblePreferenceMutation(tester);
    expect(facet.revokeAttempts, ['preference_revoke', 'preference_revoke']);
    expect(find.text(AssistantText.assistantPreferenceForget), findsNothing);
    expect(find.text(AssistantText.assistantPreferenceUndo), findsOneWidget);
  });

  testWidgets('恢复失败后只允许同preferenceId重试并以active列表收敛', (tester) async {
    final facet = _AssistantPreferenceFacet(
      initial: [
        _testPreference(
          preferenceId: 'preference_restore',
          status: AssistantPreferenceStatus.revoked,
        ),
      ],
      restoreFailuresRemaining: 1,
    );
    await tester.pumpWidget(
      _buildApp(
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: facet,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(AssistantText.assistantPreferenceUndo));
    await tester.pumpAndSettle();
    expect(find.text(AssistantText.assistantPreferenceUndo), findsOneWidget);
    expect(facet.restoreAttempts, ['preference_restore']);

    await _retryVisiblePreferenceMutation(tester);
    expect(facet.restoreAttempts, ['preference_restore', 'preference_restore']);
    expect(find.text(AssistantText.assistantPreferenceUndo), findsNothing);
    expect(find.text(AssistantText.assistantPreferenceForget), findsOneWidget);
  });
}
