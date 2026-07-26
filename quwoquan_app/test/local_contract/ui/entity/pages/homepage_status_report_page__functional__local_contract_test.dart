import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_status_report_page.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';

const String _homepageId = 'homepage_sight_west_lake';

void main() {
  setUp(AuthGate.resetDebounce);

  testWidgets('状态上报页要求选择原因并成功提交', (tester) async {
    final repository = _StatusRepository();
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _statusHost(repository: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-status-report')));
    await tester.pumpAndSettle();

    await tester.tap(find.text(UITextConstants.homepageStatusReportSubmit));
    await tester.pump();
    expect(
      find.text(UITextConstants.homepageStatusReportReasonRequired),
      findsOneWidget,
    );
    expect(repository.createCalls, 0);

    await tester.tap(
      find.text(UITextConstants.homepageStatusReportReasonIncorrectInfo),
    );
    await tester.enterText(find.byType(CupertinoTextField), '地址已经变更');
    await tester.tap(find.text(UITextConstants.homepageStatusReportSubmit));
    await tester.pumpAndSettle();

    expect(repository.createCalls, 1);
    expect(repository.lastDraft?.reason, 'incorrect_info');
    expect(repository.lastDraft?.description, '地址已经变更');
    expect(find.text('STATUS_RESULT:true'), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'status_report_submit' &&
            event.extensions['result'] == 'success',
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('状态上报失败展示表单错误并记录失败动作', (tester) async {
    final repository = _StatusRepository(failSubmit: true);
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _statusHost(repository: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-status-report')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.text(UITextConstants.homepageStatusReportReasonOffline),
    );
    await tester.tap(find.text(UITextConstants.homepageStatusReportSubmit));
    await tester.pumpAndSettle();

    expect(find.byType(AppFormErrorCard), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'status_report_submit' &&
            event.extensions['result'] == 'failure' &&
            event.extensions['failReasonCode'] == 'StateError',
      ),
      isTrue,
    );
  });

  testWidgets('游客关闭状态上报登录页回详情且不会再次弹出', (tester) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageStatusReport(id: _homepageId),
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
          builder: (_, _) => const Text('STATUS_SAFE_DETAIL'),
        ),
        GoRoute(
          path: AppRoutePaths.homepageStatusReportPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, _) =>
              const HomepageStatusReportPage(homepageId: _homepageId),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => TextButton(
            key: const ValueKey<String>('status-login-close'),
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
          homepageFacetSetProvider.overrideWithValue(_StatusRepository()),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final loginContext = tester.element(
      find.byKey(const ValueKey<String>('status-login-close')),
    );
    expect(
      GoRouterState.of(
        loginContext,
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );
    await tester.tap(find.byKey(const ValueKey<String>('status-login-close')));
    await tester.pumpAndSettle();
    await tester.pump();

    expect(find.text('STATUS_SAFE_DETAIL'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('status-login-close')),
      findsNothing,
    );
  });
}

Widget _statusHost({
  required HomepageFacetSet repository,
  required RecordingAppTelemetryRecorder telemetry,
}) {
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      homepageFacetSetProvider.overrideWithValue(repository),
      appTelemetryReporterProvider.overrideWithValue(telemetry),
    ],
    child: const MaterialApp(home: _StatusHost()),
  );
}

class _StatusHost extends StatefulWidget {
  const _StatusHost();

  @override
  State<_StatusHost> createState() => _StatusHostState();
}

class _StatusHostState extends State<_StatusHost> {
  bool? _result;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: <Widget>[
          TextButton(
            key: const ValueKey<String>('open-status-report'),
            onPressed: () async {
              final result = await Navigator.of(context).push<bool>(
                CupertinoPageRoute<bool>(
                  builder: (_) =>
                      const HomepageStatusReportPage(homepageId: _homepageId),
                ),
              );
              if (mounted) {
                setState(() => _result = result);
              }
            },
            child: const Text('OPEN_STATUS'),
          ),
          Text('STATUS_RESULT:$_result'),
        ],
      ),
    );
  }
}

class _StatusRepository extends MockHomepageRepository {
  _StatusRepository({this.failSubmit = false});

  final bool failSubmit;
  int createCalls = 0;
  HomepageStatusReportDraft? lastDraft;

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    createCalls += 1;
    lastDraft = draft;
    if (failSubmit) {
      throw StateError('redacted status failure');
    }
    return super.createHomepageStatusReport(
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
    ownerId: 'fixture_user_current',
    activeSubAccountId: 'fixture_user_current',
  );
}

class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
