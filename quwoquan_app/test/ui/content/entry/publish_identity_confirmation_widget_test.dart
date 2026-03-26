import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';
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

Widget _buildRouterApp(_TrackingContentRepository repository) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => const _CreateHostApp()),
      GoRoute(
        path: AppRoutePaths.homepagePickerPathTemplate,
        builder: (context, state) {
          final extra = state.extra is HomepagePickerPageRouteExtra
              ? state.extra! as HomepagePickerPageRouteExtra
              : null;
          return HomepagePickerPage(
            initialQuery: state.uri.queryParameters['query'] ?? '',
            initialSelection: extra?.initialSelection,
          );
        },
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repository),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp.router(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        routerConfig: router,
      ),
    ),
  );
}

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
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

  testWidgets('发布设置页可进入统一返回页风格的主页与圈子选择', (tester) async {
    final repository = _TrackingContentRepository();

    await tester.pumpWidget(_buildRouterApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '测试发布设置');
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('发布设置'), findsOneWidget);

    await tester.tap(find.text('关联主页'));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.homepagePickerPage), findsOneWidget);
    expect(find.byKey(TestKeys.homepagePickerConfirmButton), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.homepagePickerCancelButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);

    await tester.tap(find.text('同步圈子'));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.publishCircleSelectPage), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);

    await tester.tap(find.byKey(TestKeys.publishCircleCancelButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
