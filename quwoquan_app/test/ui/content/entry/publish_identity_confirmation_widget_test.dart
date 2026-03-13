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

class _TrackingContentRepository extends MockContentRepository {
  int createCallCount = 0;
  int publishCallCount = 0;
  Map<String, dynamic>? lastCreatePayload;
  Map<String, dynamic>? lastPublishPayload;

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    createCallCount += 1;
    lastCreatePayload = Map<String, dynamic>.from(payload);
    return <String, dynamic>{'_id': 'post_test_1', ...payload};
  }

  @override
  Future<Map<String, dynamic>> publishPost({
    required String postId,
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) async {
    publishCallCount += 1;
    lastPublishPayload = Map<String, dynamic>.from(payload);
    return <String, dynamic>{'postId': postId, ...payload};
  }
}

class _CreateHostApp extends StatelessWidget {
  const _CreateHostApp();

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

Widget _buildApp(_TrackingContentRepository repository) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repository),
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

  testWidgets('长文案发布前提示切换为作品，继续当前发布时仍按点滴发布', (tester) async {
    final repository = _TrackingContentRepository();

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final longText = '很长的点滴内容' * 20;
    await tester.enterText(find.byKey(TestKeys.createMomentInput), longText);
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    final dialog = find.byType(CupertinoAlertDialog);
    expect(dialog, findsOneWidget);
    expect(
      find.descendant(of: dialog, matching: find.text('当前内容更适合作为作品发布')),
      findsOneWidget,
    );

    await tester.tap(
      find.descendant(of: dialog, matching: find.text('仍按当前发布')),
    );
    await tester.pumpAndSettle();

    expect(repository.createCallCount, 1);
    expect(repository.publishCallCount, 1);
    expect(repository.lastCreatePayload?['contentIdentity'], 'moment');
    expect(find.text('打开创作'), findsOneWidget);
  });

  testWidgets('选择去调整时切到作品模式，且不立即发布', (tester) async {
    final repository = _TrackingContentRepository();

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final longText = '准备升级为作品的长文案' * 16;
    await tester.enterText(find.byKey(TestKeys.createMomentInput), longText);
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();
    final dialog = find.byType(CupertinoAlertDialog);
    expect(dialog, findsOneWidget);
    await tester.tap(find.descendant(of: dialog, matching: find.text('切到作品')));
    await tester.pumpAndSettle();

    expect(repository.createCallCount, 0);
    expect(repository.publishCallCount, 0);
    expect(find.text('作品·笔记'), findsOneWidget);

    final articleBody = tester.widget<TextFormField>(
      find.byKey(TestKeys.createArticleBodyInput),
    );
    expect(articleBody.initialValue, longText);
  });
}
