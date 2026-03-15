library;

import 'dart:convert';

import 'package:flutter/cupertino.dart';
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

class _CreateJourneyHost extends StatelessWidget {
  const _CreateJourneyHost();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.of(context).push<void>(
              MaterialPageRoute<void>(builder: (_) => const CreatePage()),
            );
          },
          child: const Text('打开创作'),
        ),
      ),
    );
  }
}

Widget _buildApp() {
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
        home: const _CreateJourneyHost(),
      ),
    ),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  group('统一编辑器草稿往返旅程', () {
    testWidgets('保存并退出后，可从草稿箱恢复作品草稿', (tester) async {
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('打开创作'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(TestKeys.createMomentInput),
        '东京三日行程整理',
      );
      await tester.pump();
      await tester.tap(find.byKey(TestKeys.createIdentityWork));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(TestKeys.createCloseButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(TestKeys.createSaveAndExitButton));
      await tester.pumpAndSettle();

      expect(find.text('打开创作'), findsOneWidget);

      await tester.tap(find.text('打开创作'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(TestKeys.createDraftsButton));
      await tester.pumpAndSettle();
      await tester.tap(find.text('作品草稿').first);
      await tester.pumpAndSettle();

      expect(find.text('作品·笔记'), findsOneWidget);
      final articleBody = tester.widget<CupertinoTextField>(
        find.descendant(
          of: find.byKey(TestKeys.createArticleBodyInput),
          matching: find.byType(CupertinoTextField),
        ),
      );
      expect(articleBody.controller?.text, '东京三日行程整理');
    });

    testWidgets('有内容时 10 秒自动保存草稿到本地缓存', (tester) async {
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('打开创作'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(TestKeys.createMomentInput),
        '自动保存的点滴内容',
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 11));

      final prefs = await SharedPreferences.getInstance();
      final rawDrafts = prefs.getString('create_drafts_list');
      expect(rawDrafts, isNotNull);

      final drafts = jsonDecode(rawDrafts!) as List<dynamic>;
      expect(drafts, isNotEmpty);
      expect(rawDrafts, contains('自动保存的点滴内容'));
    });
  });
}
