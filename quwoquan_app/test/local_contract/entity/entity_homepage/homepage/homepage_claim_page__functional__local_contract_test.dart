import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/application/entity/homepage_view_data.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_claim_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageClaimRequestView;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';

const String _homepageId = 'homepage_sight_west_lake';

void main() {
  setUp(AuthGate.resetDebounce);

  testWidgets('认领页校验联系电话后成功提交并记录 product_action', (tester) async {
    final repository = _ClaimRepository();
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _claimHost(repository: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-claim')));
    await _pumpUi(tester);

    await tester.tap(find.text(ObjectHomepageText.homepageClaimSubmit));
    await tester.pump();
    expect(
      find.text(ObjectHomepageText.homepageClaimPhoneRequired),
      findsOneWidget,
    );
    expect(repository.createCalls, 0);

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '13800000000',
    );
    await tester.tap(find.text(ObjectHomepageText.homepageClaimSubmit));
    await _pumpUi(tester);

    expect(repository.createCalls, 1);
    expect(repository.lastDraft?.contactPhone, '13800000000');
    expect(find.text('CLAIM_RESULT:true'), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'claim_request_submit' &&
            event.extensions['result'] == 'success',
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('认领页失败使用表单错误卡并记录脱敏失败码', (tester) async {
    final repository = _ClaimRepository(failSubmit: true);
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _claimHost(repository: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-claim')));
    await _pumpUi(tester);
    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '13800000000',
    );
    await tester.tap(find.text(ObjectHomepageText.homepageClaimSubmit));
    await _pumpUi(tester);

    expect(find.byType(AppFormErrorCard), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'claim_request_submit' &&
            event.extensions['result'] == 'failure' &&
            event.extensions['failReasonCode'] ==
                RuntimeFailureCodes.appContractInvalidResponse,
      ),
      isTrue,
    );
  });

  testWidgets('游客关闭认领登录页回公开详情且不会再次弹登录', (tester) async {
    final router = _guestRouter(
      restrictedPath: AppRoutePaths.homepageClaim(id: _homepageId),
      page: const HomepageClaimPage(homepageId: _homepageId),
      safeLabel: 'CLAIM_SAFE_DETAIL',
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestSession.new),
          homepageFacetSetProvider.overrideWithValue(_ClaimRepository()),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await _pumpUi(tester);

    final loginContext = tester.element(
      find.byKey(const ValueKey<String>('homepage-login-close')),
    );
    expect(
      GoRouterState.of(
        loginContext,
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-login-close')),
    );
    await _pumpUi(tester);
    await tester.pump();

    expect(find.text('CLAIM_SAFE_DETAIL'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('homepage-login-close')),
      findsNothing,
    );
  });
}

Widget _claimHost({
  required HomepageFacetSet repository,
  required RecordingAppTelemetryRecorder telemetry,
}) {
  final router = GoRouter(
    initialLocation: AppRoutePaths.home,
    routes: <RouteBase>[
      GoRoute(path: AppRoutePaths.home, builder: (_, _) => const _ClaimHost()),
      GoRoute(
        path: AppRoutePaths.homepageClaimPathTemplate.replaceAll('{id}', ':id'),
        builder: (_, _) => const HomepageClaimPage(homepageId: _homepageId),
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
      appTelemetryReporterProvider.overrideWithValue(telemetry),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

class _ClaimHost extends StatefulWidget {
  const _ClaimHost();

  @override
  State<_ClaimHost> createState() => _ClaimHostState();
}

class _ClaimHostState extends State<_ClaimHost> {
  bool? _result;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: <Widget>[
          TextButton(
            key: const ValueKey<String>('open-claim'),
            onPressed: () async {
              final result = await context.push<bool>(
                AppRoutePaths.homepageClaim(id: _homepageId),
              );
              if (mounted) {
                setState(() => _result = result);
              }
            },
            child: const Text('OPEN_CLAIM'),
          ),
          Text('CLAIM_RESULT:$_result'),
        ],
      ),
    );
  }
}

GoRouter _guestRouter({
  required String restrictedPath,
  required Widget page,
  required String safeLabel,
}) {
  return GoRouter(
    initialLocation: restrictedPath,
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutePaths.home,
        builder: (_, _) => const Text('HOME_SAFE'),
      ),
      GoRoute(
        path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (_, _) => Text(safeLabel),
      ),
      GoRoute(
        path: AppRoutePaths.homepageClaimPathTemplate.replaceAll('{id}', ':id'),
        builder: (_, _) => page,
      ),
      GoRoute(
        path: AppRoutePaths.loginPathTemplate,
        builder: (context, state) => TextButton(
          key: const ValueKey<String>('homepage-login-close'),
          onPressed: () => context.go(
            state.uri.queryParameters[loginDismissFallbackQueryParam] ??
                AppRoutePaths.home,
          ),
          child: const Text('CLOSE_LOGIN'),
        ),
      ),
    ],
  );
}

class _ClaimRepository extends MockHomepageRepository {
  _ClaimRepository({this.failSubmit = false});

  final bool failSubmit;
  int createCalls = 0;
  HomepageClaimRequestDraft? lastDraft;

  @override
  Future<HomepageClaimRequestView> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    createCalls += 1;
    lastDraft = draft;
    if (failSubmit) {
      throw StateError('redacted submit failure');
    }
    return super.createHomepageClaimRequest(
      homepageId: homepageId,
      draft: draft,
    );
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
