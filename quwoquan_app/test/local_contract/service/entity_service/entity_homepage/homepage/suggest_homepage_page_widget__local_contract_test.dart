import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show CreationText;
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/suggest_homepage_page.dart';

void main() {
  setUp(AuthGate.resetDebounce);

  testWidgets('添加主页页切换车型后展示车型字段', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        child: const _SuggestHomepageHarness(
          sourcePlaceId: 'place_0123456789abcdef',
        ),
      ),
    );
    await tester.tap(find.text('打开添加主页'));
    await _pumpUi(tester);

    expect(find.text(CreationText.addHomepageCityLabel), findsOneWidget);

    await tester.tap(find.text(CreationText.homepageTypeVehicle));
    await _pumpUi(tester);

    expect(
      find.text(CreationText.addHomepageVehicleManufacturerLabel),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.addHomepageVehicleSeriesLabel),
      findsOneWidget,
    );
    expect(find.text(CreationText.addHomepageCityLabel), findsNothing);
  });

  testWidgets('添加主页页关闭时会提示放弃未提交修改', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(repository: repository, child: const _SuggestHomepageHarness()),
    );
    await tester.tap(find.text('打开添加主页'));
    await _pumpUi(tester);

    await tester.enterText(find.byType(CupertinoTextField).first, '西湖景区');
    await tester.pump();

    await tester.tap(find.byIcon(CupertinoIcons.xmark));
    await _pumpUi(tester);

    expect(find.text(CreationText.unsavedChangesTitle), findsOneWidget);
    expect(find.text(CreationText.continueEditing), findsOneWidget);

    await tester.tap(find.text(CreationText.discard));
    await _pumpUi(tester);

    expect(find.text('result:closed'), findsOneWidget);
  });

  testWidgets('添加主页页提交车型草稿时会按实体语义组合标题', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        child: const _SuggestHomepageHarness(
          sourcePlaceId: 'place_0123456789abcdef',
        ),
      ),
    );
    await tester.tap(find.text('打开添加主页'));
    await _pumpUi(tester);

    await tester.tap(find.text(CreationText.homepageTypeVehicle));
    await _pumpUi(tester);

    await tester.enterText(find.byType(CupertinoTextField).at(0), '丰田');
    await tester.enterText(find.byType(CupertinoTextField).at(1), 'RAV4');
    await tester.enterText(find.byType(CupertinoTextField).at(2), '2024 款');
    await tester.enterText(find.byType(CupertinoTextField).at(3), '双擎四驱');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.suggestHomepageSubmitButton));
    await _pumpUi(tester);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(repository.lastDraft?.homepageType, 'vehicle');
    expect(repository.lastDraft?.title, '丰田 RAV4');
    expect(repository.lastDraft?.subtitle, '2024 款 · 双擎四驱');
    expect(repository.lastDraft?.city, isEmpty);
    expect(repository.lastDraft?.address, isEmpty);
    expect(repository.lastDraft?.categoryTags, <String>['丰田']);
    expect(repository.lastDraft?.sourcePlaceId, 'place_0123456789abcdef');
  });

  testWidgets('游客关闭添加主页登录页回首页且不会循环', (tester) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.suggestHomepage(query: '西湖'),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (_, _) => const Text('SUGGEST_SAFE_HOME'),
        ),
        GoRoute(
          path: AppRoutePaths.suggestHomepagePathTemplate,
          builder: (_, _) => SuggestHomepagePage(initialQuery: '西湖'),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => TextButton(
            key: const ValueKey<String>('suggest-login-close'),
            onPressed: () => context.go(
              state.uri.queryParameters[loginDismissFallbackQueryParam] ??
                  AppRoutePaths.home,
            ),
            child: const Text('CLOSE_LOGIN'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestSession.new),
          homepageFacetSetProvider.overrideWithValue(
            _TrackingHomepageRepository(),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await _pumpUi(tester);

    final loginContext = tester.element(
      find.byKey(const ValueKey<String>('suggest-login-close')),
    );
    expect(
      GoRouterState.of(
        loginContext,
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );
    await tester.tap(find.byKey(const ValueKey<String>('suggest-login-close')));
    await _pumpUi(tester);
    await tester.pump();

    expect(find.text('SUGGEST_SAFE_HOME'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('suggest-login-close')),
      findsNothing,
    );
  });
}

Widget _buildApp({
  required _TrackingHomepageRepository repository,
  required Widget child,
}) {
  final router = GoRouter(
    initialLocation: AppRoutePaths.home,
    routes: <RouteBase>[
      GoRoute(path: AppRoutePaths.home, builder: (_, _) => child),
      GoRoute(
        path: AppRoutePaths.suggestHomepagePathTemplate,
        builder: (_, state) => SuggestHomepagePage(
          initialQuery: state.uri.queryParameters['query'] ?? '',
          sourcePlaceId: state.uri.queryParameters['sourcePlaceId'] ?? '',
        ),
      ),
      GoRoute(
        path: AppRoutePaths.loginPathTemplate,
        builder: (_, _) => const Text('UNEXPECTED_LOGIN'),
      ),
    ],
  );
  addTearDown(router.dispose);
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      homepageFacetSetProvider.overrideWithValue(repository),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

class _SuggestHomepageHarness extends StatefulWidget {
  const _SuggestHomepageHarness({this.sourcePlaceId = ''});

  final String sourcePlaceId;

  @override
  State<_SuggestHomepageHarness> createState() =>
      _SuggestHomepageHarnessState();
}

class _SuggestHomepageHarnessState extends State<_SuggestHomepageHarness> {
  String _resultText = 'result:none';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            ElevatedButton(
              onPressed: () async {
                final result = await context.push<bool>(
                  AppRoutePaths.suggestHomepage(
                    sourcePlaceId: widget.sourcePlaceId,
                  ),
                );
                if (!mounted) {
                  return;
                }
                setState(() {
                  _resultText = result == true
                      ? 'result:submitted'
                      : 'result:closed';
                });
              },
              child: const Text('打开添加主页'),
            ),
            const SizedBox(height: 12),
            Text(_resultText),
          ],
        ),
      ),
    );
  }
}

class _TrackingHomepageRepository extends MockHomepageRepository {
  HomepageSuggestionDraft? lastDraft;

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    lastDraft = draft;
    return super.suggestHomepageCandidate(draft: draft);
  }
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'entity-test-token',
    refreshToken: 'entity-test-refresh-token',
    ownerId: 'fixture_user_current',
    activePersonaId: 'fixture_user_current',
  );
}

class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}

Future<void> _pumpUi(WidgetTester tester) async {
  await tester.pump();
  for (var frame = 0; frame < 6; frame += 1) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
