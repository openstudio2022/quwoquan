import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('关闭 unified create editor flag 后进入回退模式但不恢复旧 taxonomy', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(MockContentRepository()),
          circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
          contentFeatureFlagProvider('enable_unified_create_editor').overrideWith(
            (ref) => false,
          ),
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
