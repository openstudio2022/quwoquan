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

Widget _buildCreatePageApp() {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(MockContentRepository()),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
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
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('点滴与作品身份切换时保留文本内容', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp());
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '今天的旅行记录');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createIdentityWork));
    await tester.pumpAndSettle();

    expect(find.text('作品·笔记'), findsOneWidget);
    final articleBody = tester.widget<TextFormField>(
      find.byKey(TestKeys.createArticleBodyInput),
    );
    expect(articleBody.initialValue, '今天的旅行记录');

    await tester.tap(find.byKey(TestKeys.createIdentityMoment));
    await tester.pumpAndSettle();

    final momentInput = tester.widget<TextFormField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(momentInput.controller?.text, '今天的旅行记录');
  });

  testWidgets('作品模式支持格式切换，且沿用当前文本内容', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(TestKeys.createMomentInput),
      '准备整理成作品的内容',
    );
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.createIdentityWork));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createWorkFormatImage));
    await tester.pumpAndSettle();
    expect(find.text('作品·图片'), findsOneWidget);

    final photoBody = tester.widget<TextFormField>(
      find.byKey(TestKeys.createPhotoBodyInput),
    );
    expect(photoBody.initialValue, '准备整理成作品的内容');

    await tester.tap(find.byKey(TestKeys.createWorkFormatVideo));
    await tester.pumpAndSettle();
    expect(find.text('作品·视频'), findsOneWidget);

    final videoBody = tester.widget<TextFormField>(
      find.byKey(TestKeys.createVideoBodyInput),
    );
    expect(videoBody.initialValue, '准备整理成作品的内容');
  });
}
