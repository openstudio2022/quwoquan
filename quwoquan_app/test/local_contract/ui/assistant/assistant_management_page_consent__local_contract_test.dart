import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_management_page.dart';

class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}

class _AssistantConsentFacet implements AssistantSkillConsentFacet {
  _AssistantConsentFacet(this._granted, {this.listFailuresRemaining = 0});

  bool _granted;
  int listFailuresRemaining;
  int listCallCount = 0;

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    _granted = true;
    return AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.utc(2026, 3, 12, 10),
    );
  }

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    listCallCount += 1;
    if (listFailuresRemaining > 0) {
      listFailuresRemaining -= 1;
      throw StateError('consent unavailable');
    }
    if (!_granted) {
      return const <AssistantSkillConsent>[];
    }
    return <AssistantSkillConsent>[
      AssistantSkillConsent(
        skillId: kPersonalContentAccessSkillId,
        grantedScope: kPersonalContentAccessSkillId,
        granted: true,
        updatedAt: DateTime.utc(2026, 3, 12, 9),
      ),
    ];
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    _granted = false;
  }
}

class _AssistantPreferenceFacet implements AssistantPreferenceFactFacet {
  _AssistantPreferenceFacet({
    List<AssistantPreferenceFact> initial = const <AssistantPreferenceFact>[],
    this.listFailuresRemaining = 0,
  }) : _items = <AssistantPreferenceFact>[...initial];

  final List<AssistantPreferenceFact> _items;
  int listFailuresRemaining;
  final List<AssistantPreferenceStatus> requestedStatuses =
      <AssistantPreferenceStatus>[];

  @override
  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
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
              item.status == status.wireName &&
              (scope == null || item.scope == scope.wireName),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  }) async {
    final fact = AssistantPreferenceFact(
      preferenceId: 'preference_${_items.length + 1}',
      userId: 'owner',
      scope: scope.wireName,
      conversationId: conversationId.isEmpty ? null : conversationId,
      kind: kind.wireName,
      value: value,
      sourceType: sourceType.wireName,
      status: AssistantPreferenceStatus.active.wireName,
      createdAt: '2026-07-20T08:00:00Z',
      updatedAt: '2026-07-20T08:00:00Z',
      version: 1,
    );
    _items
      ..removeWhere(
        (item) =>
            item.scope == fact.scope &&
            item.conversationId == fact.conversationId &&
            item.kind == fact.kind,
      )
      ..add(fact);
    return fact;
  }

  @override
  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _items.indexWhere(
      (item) => item.preferenceId == preferenceId,
    );
    final current = _items[index];
    final revoked = AssistantPreferenceFact(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      conversationId: current.conversationId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.revoked.wireName,
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
  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _items.indexWhere(
      (item) => item.preferenceId == preferenceId,
    );
    final current = _items[index];
    final restored = AssistantPreferenceFact(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      conversationId: current.conversationId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.active.wireName,
      createdAt: current.createdAt,
      updatedAt: '2026-07-20T08:02:00Z',
      version: current.version + 1,
    );
    _items[index] = restored;
    return restored;
  }
}

Widget _buildApp({
  required _AssistantConsentFacet consentFacet,
  required VisitRecorderService visitRecorder,
  _AssistantPreferenceFacet? preferenceFacet,
}) {
  final resolvedPreferenceFacet =
      preferenceFacet ?? _AssistantPreferenceFacet();
  return ProviderScope(
    overrides: [
      assistantSkillConsentFacetProvider.overrideWithValue(consentFacet),
      assistantPreferenceFactFacetProvider.overrideWithValue(
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

void main() {
  testWidgets('管理页使用真实内容授权开关', (tester) async {
    final consentFacet = _AssistantConsentFacet(false);
    final recorder = _CapturingVisitRecorder();
    await tester.pumpWidget(
      _buildApp(consentFacet: consentFacet, visitRecorder: recorder),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(AssistantText.assistantContentAccessPermission),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantContentAccessNotGranted),
      findsOneWidget,
    );
    expect(find.byType(CupertinoSwitch), findsOneWidget);
    expect(find.text('性格选择'), findsNothing);
    expect(find.text('允许读取聊天'), findsNothing);
    expect(find.text('允许访问位置'), findsNothing);
    expect(find.text('系统通知'), findsNothing);

    await tester.tap(find.byType(CupertinoSwitch));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(AssistantManagementPage)),
    );
    expect(container.read(personalContentAccessProvider).granted, isTrue);
    expect(
      find.text(AssistantText.assistantContentAccessGranted),
      findsOneWidget,
    );
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page('assistant_management').targetKey),
    );
  });

  testWidgets('管理页展示真实显式偏好数据', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        consentFacet: _AssistantConsentFacet(false),
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: _AssistantPreferenceFacet(
          initial: const <AssistantPreferenceFact>[
            AssistantPreferenceFact(
              preferenceId: 'preference_1',
              userId: 'owner',
              scope: 'long_term',
              kind: 'tone',
              value: 'warm',
              sourceType: 'management',
              status: 'active',
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

  testWidgets('管理页记忆空态明确', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        consentFacet: _AssistantConsentFacet(false),
        visitRecorder: _CapturingVisitRecorder(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(AssistantText.assistantMemoryEmpty), findsOneWidget);
  });

  testWidgets('管理页可设置长期回答偏好', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        consentFacet: _AssistantConsentFacet(false),
        visitRecorder: _CapturingVisitRecorder(),
      ),
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
        consentFacet: _AssistantConsentFacet(false),
        visitRecorder: _CapturingVisitRecorder(),
        preferenceFacet: _AssistantPreferenceFacet(listFailuresRemaining: 1),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.sectionLoadFailedTitleDefault),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });

  testWidgets('管理页遗忘偏好后可撤销恢复', (tester) async {
    final preferenceFacet = _AssistantPreferenceFacet(
      initial: const <AssistantPreferenceFact>[
        AssistantPreferenceFact(
          preferenceId: 'preference_undo',
          userId: 'owner',
          scope: 'long_term',
          kind: 'reply_length',
          value: 'concise',
          sourceType: 'management',
          status: 'active',
          createdAt: '2026-07-20T08:00:00Z',
          updatedAt: '2026-07-20T08:00:00Z',
          version: 1,
        ),
      ],
    );
    await tester.pumpWidget(
      _buildApp(
        consentFacet: _AssistantConsentFacet(false),
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
    // 已撤销的事实不进入管理列表；仅当前操作保留临时恢复入口。
    expect(find.text(AssistantText.assistantPreferenceConcise), findsOneWidget);
    expect(find.text(AssistantText.assistantPreferenceForgot), findsOneWidget);
    expect(find.text(AssistantText.assistantPreferenceUndo), findsOneWidget);
    expect(find.text(AssistantText.assistantPreferenceForget), findsNothing);
    expect(
      preferenceFacet.requestedStatuses,
      everyElement(AssistantPreferenceStatus.active),
    );

    await tester.tap(find.text(AssistantText.assistantPreferenceUndo));
    await tester.pumpAndSettle();
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
    );
    expect(find.text(AssistantText.assistantPreferenceForget), findsOneWidget);
  });

  testWidgets('授权加载失败可见且可重试', (tester) async {
    final consentFacet = _AssistantConsentFacet(
      false,
      listFailuresRemaining: 1,
    );
    await tester.pumpWidget(
      _buildApp(
        consentFacet: consentFacet,
        visitRecorder: _CapturingVisitRecorder(),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(AssistantText.assistantConsentLoadFailedTitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);

    await tester.tap(find.text(UITextConstants.tryAgain));
    await tester.pumpAndSettle();

    expect(consentFacet.listCallCount, 2);
    expect(
      find.text(AssistantText.assistantConsentLoadFailedTitle),
      findsNothing,
    );
    expect(
      find.text(AssistantText.assistantContentAccessNotGranted),
      findsOneWidget,
    );
  });
}
