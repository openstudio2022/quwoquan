import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/design_system/media/media_reorderable_view.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show circlesListQueryProvider;
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart'
    show LoginDismissPolicy, loginGuestDismissPopQueryParam;
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_editor_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';

Widget _buildCreatePageApp({String? initialTabKey}) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      circlesListQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CreatePage(initialTabKey: initialTabKey),
      ),
    ),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('图片创作页使用统一标题 token，首屏标题不再淡化', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final title = tester.widget<Text>(find.text('图片创作'));
    expect(
      title.style?.color,
      AppNavigationSemanticConstants.barTitleColor(false),
    );

    final opacity = tester.widget<Opacity>(
      find
          .ancestor(of: find.text('图片创作'), matching: find.byType(Opacity))
          .first,
    );
    expect(opacity.opacity, 1);
  });

  testWidgets('图片网格拖拽悬停时目标区间即时移位，松手后 provider 顺序提交', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      '/tmp/a.jpg',
      '/tmp/b.jpg',
      '/tmp/c.jpg',
      '/tmp/d.jpg',
    ], editorKind: CreateEditorKind.media);
    await tester.pumpAndSettle();

    expect(find.byType(MediaReorderableView), findsOneWidget);

    final aRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/a.jpg')),
    );
    final bRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/b.jpg')),
    );
    final start = tester.getCenter(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/a.jpg')),
    );
    final target = tester.getCenter(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/c.jpg')),
    );

    final gesture = await tester.startGesture(start);
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 80));
    await gesture.moveBy(target - start);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final bRect = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/b.jpg')),
    );
    final cRect = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/c.jpg')),
    );
    expect(bRect.topLeft.dx, closeTo(aRectBefore.left, 1));
    expect(bRect.topLeft.dy, closeTo(aRectBefore.top, 1));
    expect(cRect.topLeft.dx, closeTo(bRectBefore.left, 1));
    expect(cRect.topLeft.dy, closeTo(bRectBefore.top, 1));

    await gesture.up();
    await tester.pumpAndSettle();

    final state = container.read(createEditorProvider);
    expect(state.imagePaths, <String>[
      '/tmp/b.jpg',
      '/tmp/c.jpg',
      '/tmp/a.jpg',
      '/tmp/d.jpg',
    ]);
  });

  testWidgets('创作页会话失效后登录成功续接原图片选择动作', (tester) async {
    var pickerLaunches = 0;
    final router = GoRouter(
      initialLocation: '/create-test',
      routes: <RouteBase>[
        GoRoute(
          path: '/create-test',
          builder: (context, state) => CreatePage(
            initialTabKey: 'photo',
            mediaPickerLauncher:
                (
                  context, {
                  required mode,
                  required maxSelection,
                  initialPaths = const <String>[],
                }) async {
                  pickerLaunches += 1;
                  return null;
                },
          ),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => const Scaffold(
            body: SizedBox(key: ValueKey<String>('create-login-sentinel')),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
          circlesListQueryProvider.overrideWithValue(
            InMemoryCircleQueryReader(),
          ),
          authSessionControllerProvider.overrideWith(
            _FlippableCreateSession.new,
          ),
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
      ),
    );
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );

    await tester.tap(find.byKey(TestKeys.createMediaAddButton).first);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('create-login-sentinel')),
      findsOneWidget,
    );
    expect(pickerLaunches, 0);
    final pending = container.read(authContinuationProvider);
    expect(pending, isA<ResumeCreateActionContinuation>());
    expect(
      (pending! as ResumeCreateActionContinuation).action,
      CreateActionContinuationKind.pickImages,
    );
    expect(
      GoRouterState.of(
        tester.element(
          find.byKey(const ValueKey<String>('create-login-sentinel')),
        ),
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableCreateSession)
        .loginNow();
    router.pop();
    await tester.pumpAndSettle();

    expect(pickerLaunches, 1);
    expect(container.read(authContinuationProvider), isNull);
  });
}

class _FlippableCreateSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'create-test-token',
      refreshToken: 'create-test-refresh-token',
      ownerId: 'create-test-owner',
      activePersonaId: 'create-test-persona',
    );
  }
}
