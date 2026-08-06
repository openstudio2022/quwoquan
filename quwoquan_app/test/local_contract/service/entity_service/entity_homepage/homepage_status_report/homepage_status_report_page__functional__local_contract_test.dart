import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/adapters/homepage_status_report_action_tracker_adapter.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_write_target_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/presentation/homepage_status_report_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageStatusReportView;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

const String _homepageId = 'homepage_sight_west_lake';

void main() {
  setUp(AuthGate.resetDebounce);

  testWidgets('状态上报页要求选择原因并成功提交', (tester) async {
    final repository = _StatusRepository();
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _statusHost(reader: repository, writer: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-status-report')));
    await _pumpUi(tester);

    await tester.tap(find.text(ObjectHomepageText.homepageStatusReportSubmit));
    await tester.pump();
    expect(
      find.text(ObjectHomepageText.homepageStatusReportReasonRequired),
      findsOneWidget,
    );
    expect(repository.createCalls, 0);

    await tester.tap(
      find.text(ObjectHomepageText.homepageStatusReportReasonIncorrectInfo),
    );
    await tester.enterText(find.byType(CupertinoTextField), '地址已经变更');
    await tester.tap(find.text(ObjectHomepageText.homepageStatusReportSubmit));
    await _pumpUi(tester);

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
      _statusHost(reader: repository, writer: repository, telemetry: telemetry),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-status-report')));
    await _pumpUi(tester);
    await tester.tap(
      find.text(ObjectHomepageText.homepageStatusReportReasonOffline),
    );
    await tester.tap(find.text(ObjectHomepageText.homepageStatusReportSubmit));
    await _pumpUi(tester);

    expect(find.byType(AppFormErrorCard), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'status_report_submit' &&
            event.extensions['result'] == 'failure' &&
            event.extensions['failReasonCode'] ==
                RuntimeFailureCodes.appContractInvalidResponse,
      ),
      isTrue,
    );
  });

  testWidgets('游客关闭状态上报登录页回详情且不会再次弹出', (tester) async {
    final repository = _StatusRepository();
    final actionTracker = _actionTracker(RecordingAppTelemetryRecorder());
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
          builder: (_, _) => HomepageStatusReportPage(
            homepageId: _homepageId,
            writeTargetReader: repository,
            commandWriter: repository,
            actionTracker: actionTracker,
          ),
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
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await _pumpUi(tester);

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
    await _pumpUi(tester);
    await tester.pump();

    expect(find.text('STATUS_SAFE_DETAIL'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('status-login-close')),
      findsNothing,
    );
  });
}

Widget _statusHost({
  required HomepageWriteTargetReader reader,
  required HomepageStatusReportCommandWriter writer,
  required RecordingAppTelemetryRecorder telemetry,
}) {
  final router = GoRouter(
    initialLocation: AppRoutePaths.home,
    routes: <RouteBase>[
      GoRoute(path: AppRoutePaths.home, builder: (_, _) => const _StatusHost()),
      GoRoute(
        path: AppRoutePaths.homepageStatusReportPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (_, _) => HomepageStatusReportPage(
          homepageId: _homepageId,
          writeTargetReader: reader,
          commandWriter: writer,
          actionTracker: _actionTracker(telemetry),
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
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

HomepageStatusReportActionTrackerAdapter _actionTracker(
  RecordingAppTelemetryRecorder telemetry,
) {
  return HomepageStatusReportActionTrackerAdapter(
    journeyEventTracker: JourneyEventTracker(telemetryReporter: telemetry),
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
              final result = await context.push<bool>(
                AppRoutePaths.homepageStatusReport(id: _homepageId),
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
  Future<HomepageStatusReportView> createStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    createCalls += 1;
    lastDraft = draft;
    if (failSubmit) {
      throw StateError('redacted status failure');
    }
    return super.createStatusReport(homepageId: homepageId, draft: draft);
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
