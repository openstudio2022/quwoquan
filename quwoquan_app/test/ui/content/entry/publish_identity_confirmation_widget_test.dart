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
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
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

  testWidgets('短文本直接按 micro 契约发布，且不暴露旧 taxonomy', (tester) async {
    final repository = _TrackingContentRepository();

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '今天很开心');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('允许小趣使用'), findsNothing);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(repository.createCallCount, 1);
    expect(repository.publishCallCount, 1);
    expect(repository.lastCreatePayload?['contentType'], 'micro');
    expect(
      repository.lastCreatePayload?.containsKey('contentIdentity'),
      isFalse,
    );
    expect(find.text('当前内容更适合作为作品发布'), findsNothing);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('打开创作'), findsOneWidget);
  });

  testWidgets('长文本直接进入下一步并按 article 契约发布，且不暴露旧 taxonomy', (tester) async {
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
    expect(dialog, findsNothing);
    expect(find.text('当前内容更适合作为作品发布'), findsNothing);
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(repository.createCallCount, 1);
    expect(repository.publishCallCount, 1);
    expect(repository.lastCreatePayload?['contentType'], 'article');
    expect(
      (repository.lastCreatePayload?['body'] as String).replaceAll('\n', ''),
      longText,
    );
    expect(
      repository.lastCreatePayload?.containsKey('contentIdentity'),
      isFalse,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('打开创作'), findsOneWidget);
  });

  testWidgets('媒体编辑器对图片使用首图预览并写入 payload', (tester) async {
    final repository = _TrackingContentRepository();

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      '/tmp/cover_a.jpg',
      '/tmp/cover_b.jpg',
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(1);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('当前封面'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(repository.lastCreatePayload?['contentType'], 'image');
    expect(repository.lastCreatePayload?['coverUrl'], '/tmp/cover_a.jpg');
    expect(repository.lastCreatePayload?['mediaUrls'], <String>[
      '/tmp/cover_a.jpg',
      '/tmp/cover_b.jpg',
    ]);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });
}
