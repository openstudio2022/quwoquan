// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import '../../../../support/fakes/test_persona_facets.dart';

Widget _wrap(TestPersonaFacets facets) {
  return ProviderScope(
    overrides: [
      personaQueryProvider.overrideWith((ref, surface) => facets),
      personaCommandWriterProvider.overrideWithValue(facets),
    ],
    child: const CupertinoApp(home: PersonaManagementPage()),
  );
}

void main() {
  group('PersonaManagementPage', () {
    testWidgets('展示分身资料字段', (tester) async {
      await tester.pumpWidget(_wrap(TestPersonaFacets()));
      await tester.pumpAndSettle();

      expect(find.text('主分身'), findsWidgets);
      expect(find.textContaining('用户号: main_handle'), findsOneWidget);
      expect(
        find.textContaining(ProfileText.personaInheritanceDefault),
        findsOneWidget,
      );
    });

    testWidgets('分身首屏失败只保留顶栏返回与恢复动作', (tester) async {
      final facets = TestPersonaFacets(
        summaryFailure: StateError('persona summary unavailable'),
      );
      await tester.pumpWidget(_wrap(facets));
      await tester.pumpAndSettle();

      final errorState = tester.widget<AppPageErrorState>(
        find.byType(AppPageErrorState),
      );
      expect(errorState.semantic.primaryAction?.label, SearchText.reload);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
      expect(find.text(ContentText.back), findsNothing);
      expect(find.text(SearchText.reload), findsOneWidget);

      facets.summaryFailure = null;
      await tester.tap(find.text(SearchText.reload));
      await tester.pumpAndSettle();

      expect(facets.summaryLoadCount, 2);
      expect(find.text('主分身'), findsWidgets);
    });

    testWidgets('编辑资料后出现同步建议', (tester) async {
      final facets = TestPersonaFacets();
      await tester.pumpWidget(_wrap(facets));
      await tester.pumpAndSettle();

      await tester.tap(find.text(ProfileText.profileEditLabel).first);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(CupertinoTextField).at(0), '新主分身');
      await tester.tap(find.text(ProfileText.editProfileSaveAction));
      await tester.pumpAndSettle();

      expect(find.text(ProfileText.personaSyncSuggestionTitle), findsOneWidget);
    });

    testWidgets('同步建议可执行应用', (tester) async {
      final facets = TestPersonaFacets();
      await tester.pumpWidget(_wrap(facets));
      await tester.pumpAndSettle();

      await tester.tap(find.text(ProfileText.profileEditLabel).first);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(CupertinoTextField).first, '同步后的主分身');
      await tester.tap(find.text(ProfileText.editProfileSaveAction));
      await tester.pumpAndSettle();

      await tester.tap(find.text(ProfileText.personaSyncApplyAll));
      await tester.pumpAndSettle();

      expect(facets.syncAppliedCount, 1);
    });

    testWidgets('已退役分身展示退役态并隐藏重复退役操作', (tester) async {
      final seed = TestPersonaFacets.defaultSeed()
          .map(
            (item) => item.personaId == 'persona_photo'
                ? item.copyWith(
                    status: 'retired',
                    retiredAt: DateTime.utc(2026, 4, 23),
                  )
                : item,
          )
          .toList(growable: false);
      await tester.pumpWidget(_wrap(TestPersonaFacets(seed: seed)));
      await tester.pumpAndSettle();

      expect(find.text(ProfileText.personaRetired), findsWidgets);
      expect(find.text(ProfileText.personaRetire), findsNothing);
    });
  });
}
