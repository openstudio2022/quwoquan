import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
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
  Future<PostBaseDto> createPost({required CreatePostRequestWire body}) async {
    createCallCount += 1;
    lastCreatePayload = Map<String, dynamic>.from(body.toWire());
    const postId = 'post_test_1';
    return postBaseDtoFromMap(<String, dynamic>{
      '_id': postId,
      'postId': postId,
      ...lastCreatePayload!,
      'authorId': 'test_author',
      'displayName': 'Test',
      'authorAvatarUrl': 'https://example.com/a.jpg',
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
    });
  }

  @override
  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  }) async {
    publishCallCount += 1;
    final wire = body ?? PublishPostRequestWire();
    lastPublishPayload = Map<String, dynamic>.from(wire.toWire());
    return postBaseDtoFromMap(<String, dynamic>{
      'postId': postId,
      ...wire.toWire(),
      'authorId': 'test_author',
      'displayName': 'Test',
      'authorAvatarUrl': 'https://example.com/a.jpg',
      'contentType': 'micro',
      'body': '',
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
    });
  }
}

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activeSubAccountId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'user_001',
      activeSubAccountId: 'user_001',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
    );
  }
}

/// 在 pump 期间主动 watch 登录态，让创作页发布/选图的 requireLogin 在已登录态放行。
class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
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
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            _AuthWarmup(child: child ?? const SizedBox.shrink()),
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
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp.router(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            _AuthWarmup(child: child ?? const SizedBox.shrink()),
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
    expect(repository.lastCreatePayload?.containsKey('body'), isFalse);
    expect(
      repository.lastCreatePayload?.containsKey('articleTemplate'),
      isFalse,
    );
    expect(
      repository.lastCreatePayload?.containsKey('articleFontPreset'),
      isFalse,
    );
    expect(repository.lastCreatePayload?['articleMarkdown'], isA<String>());
    expect(
      repository.lastCreatePayload?['articleMarkdownVersion'],
      'qwq-rich-md/1',
    );
    expect(
      repository.lastCreatePayload?['articleAssetManifest'],
      isA<Map<String, dynamic>>(),
    );
    expect(
      repository.lastCreatePayload?['articleRenderProfile'],
      isA<Map<String, dynamic>>(),
    );
    final articleMarkdown =
        repository.lastCreatePayload?['articleMarkdown'] as String;
    expect(articleMarkdown.contains(longText), isTrue);
    final renderProfile =
        repository.lastCreatePayload?['articleRenderProfile']
            as Map<String, dynamic>;
    expect(renderProfile['template'], isNotNull);
    expect(renderProfile['fontPreset'], isNotNull);
    expect(repository.lastCreatePayload?.containsKey('articlePages'), isFalse);
    expect(repository.lastCreatePayload?.containsKey('articleBlocks'), isFalse);
    expect(repository.lastCreatePayload?.containsKey('cards'), isFalse);
    expect(
      repository.lastCreatePayload?.containsKey('articleDocument'),
      isFalse,
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
    const coverA = 'https://example.com/test/create/cover_a.jpg';
    const coverB = 'https://example.com/test/create/cover_b.jpg';

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      coverA,
      coverB,
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(1);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('当前封面'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    for (var i = 0; i < 10 && repository.lastCreatePayload == null; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }

    final payload = repository.lastCreatePayload;
    expect(payload, isNotNull);
    expect(payload?['contentType'] ?? payload?['type'], 'image');
    expect(payload?['mediaUrls'], isA<List<dynamic>>());
    final mediaUrls = List<String>.from(payload?['mediaUrls'] as List<dynamic>);
    expect(mediaUrls, hasLength(2));
    expect(mediaUrls.first, coverA);
    expect(mediaUrls.last, coverB);
    expect(payload?['coverUrl'], mediaUrls.first);
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

    await tester.tap(find.text('发布到圈子'));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.publishCircleSelectPage), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);

    await tester.tap(find.byKey(TestKeys.publishCircleCancelButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
