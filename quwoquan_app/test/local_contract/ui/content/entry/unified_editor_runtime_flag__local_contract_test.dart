// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/content/content/post/presentation/create_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/content/content/post/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('关闭 unified create editor flag 后进入回退模式但不恢复旧 taxonomy', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...mockContentFacetOverrides(MockContentRepository()),
          circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
          contentFeatureFlagProvider(
            'enable_unified_create_editor',
          ).overrideWith((ref) => false),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (context, _) => MaterialApp(
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const CreatePage(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createIdentityMoment), findsNothing);
    expect(find.byKey(TestKeys.createIdentityWork), findsNothing);
    expect(find.byKey(TestKeys.createWorkFormatImage), findsNothing);
    expect(find.textContaining('回退模式'), findsOneWidget);
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });
}
