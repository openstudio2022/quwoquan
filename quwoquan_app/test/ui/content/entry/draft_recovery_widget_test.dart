import 'dart:convert';

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
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _CreateHostApp extends StatelessWidget {
  const _CreateHostApp();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(builder: (_) => const CreatePage()),
              );
            },
            child: const Text('打开创作'),
          ),
          ElevatedButton(
            onPressed: () async {
              final prefs = await SharedPreferences.getInstance();
              final raw = prefs.getString(CreateDraftLocalStorage.draftsKey);
              String? draftId;
              if (raw != null && raw.isNotEmpty) {
                try {
                  final list = jsonDecode(raw) as List<dynamic>;
                  if (list.isNotEmpty && list.first is Map) {
                    draftId =
                        (list.first as Map<dynamic, dynamic>)['id'] as String?;
                  }
                } catch (_) {}
              }
              if (!context.mounted) {
                return;
              }
              await Navigator.of(context).push<void>(
                MaterialPageRoute<void>(
                  builder: (_) => CreatePage(initialDraftId: draftId),
                ),
              );
            },
            child: const Text('从草稿继续'),
          ),
        ],
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
        home: const _CreateHostApp(),
      ),
    ),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('退出保存草稿后可从草稿箱恢复', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '待会继续写的内容');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createCloseButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createSaveAndExitButton));
    await tester.pumpAndSettle();

    expect(find.text('打开创作'), findsOneWidget);

    await tester.tap(find.text('从草稿继续'));
    await tester.pumpAndSettle();

    // 恢复后，文本在 node 级 TextField 中（非占位输入框）
    expect(find.text('待会继续写的内容'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });
}
