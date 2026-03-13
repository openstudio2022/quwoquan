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

      expect(find.text('允许小趣使用我的创作内容'), findsOneWidget);
      expect(find.text('未允许'), findsOneWidget);

      await tester.tap(find.byType(Switch).at(1));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(AssistantManagementPage)),
      );
      expect(container.read(personalContentAccessProvider).granted, isTrue);
      expect(find.text('已允许'), findsOneWidget);
    },
  );
}
