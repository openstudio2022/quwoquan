import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_management_page.dart';

class _AssistantRepo implements AssistantRepository {
  _AssistantRepo(this._granted);

  bool _granted;

  @override
  Future<Map<String, dynamic>> getPolicySnapshot({
    String policyVersionHint = '',
  }) async => <String, dynamic>{
    'version': policyVersionHint.isEmpty ? 'test' : policyVersionHint,
    'grantedScopes': _granted
        ? const <String>[kPersonalContentAccessSkillId]
        : const <String>[],
  };

  @override
  Future<Map<String, dynamic>> reportInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async => <String, dynamic>{'accepted': true, 'count': events.length};

  @override
  Future<Map<String, dynamic>> reportScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async => <String, dynamic>{
    'accepted': true,
    'count': scorecards.length,
  };

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

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) async {
    return AssistantSearchResultView(
      queryEcho: query,
      searchIntensity: searchIntensity,
    );
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = 32,
    String? status,
  }) async =>
      const <AssistantUserTaskView>[];

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = 32,
  }) async =>
      const <AssistantUserMemoryView>[];

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = 64,
  }) async =>
      const <AssistantSkillCatalogItemView>[];
}

void main() {
  testWidgets(
    'assistant management page uses real personal content access switch',
    (tester) async {
      final repo = _AssistantRepo(false);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [assistantRepositoryProvider.overrideWithValue(repo)],
          child: MaterialApp(home: AssistantManagementPage(onBack: () {})),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('允许私助使用我的创作内容'), findsOneWidget);
      expect(find.text('未允许'), findsOneWidget);

      await tester.tap(find.byType(CupertinoSwitch).at(1));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(AssistantManagementPage)),
      );
      expect(container.read(personalContentAccessProvider).granted, isTrue);
      expect(find.text('已允许'), findsOneWidget);
    },
  );
}
