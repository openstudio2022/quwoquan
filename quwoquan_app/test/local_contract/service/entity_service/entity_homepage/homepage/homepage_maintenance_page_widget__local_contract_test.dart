import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/entity/entity_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_facets.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart'
    show AppFormErrorCard, AppPageErrorState;
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_maintenance_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ObjectHomepageText, SearchText;
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryReporterProvider;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';

const String _homepageId = 'homepage_sight_west_lake';
const String _ownerId = 'homepage-owner';

void main() {
  setUp(AuthGate.resetDebounce);

  testWidgets('主页维护页 owner 成功保存基础信息', (tester) async {
    final repository = _MaintenanceRepository(ownerId: _ownerId);
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        viewerOwnerId: _ownerId,
        telemetry: telemetry,
        child: const _MaintenanceHost(),
      ),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-maintenance')));
    await _pumpUi(tester);

    await tester.enterText(find.byType(CupertinoTextField).first, '新的主页名称');
    await tester.tap(find.text(ObjectHomepageText.homepageMaintenanceSave));
    await _pumpUi(tester);

    expect(repository.updateCalls, 1);
    expect(repository.lastDraft?.title, '新的主页名称');
    expect(find.text('MAINTENANCE_RESULT:true'), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'maintenance_submit' &&
            event.extensions['result'] == 'success',
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('非 owner fail-closed 展示权限页且不渲染表单', (tester) async {
    final repository = _MaintenanceRepository(ownerId: 'another-owner');
    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        viewerOwnerId: _ownerId,
        telemetry: RecordingAppTelemetryRecorder(),
        child: HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await _pumpUi(tester);

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SearchText.recoveryNoAccessTitle), findsOneWidget);
    expect(find.byType(CupertinoTextField), findsNothing);
    expect(repository.updateCalls, 0);
  });

  testWidgets('主页维护页提交失败展示表单错误并记录失败动作', (tester) async {
    final repository = _MaintenanceRepository(
      ownerId: _ownerId,
      failSubmit: true,
    );
    final telemetry = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        viewerOwnerId: _ownerId,
        telemetry: telemetry,
        child: HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await _pumpUi(tester);
    await tester.enterText(find.byType(CupertinoTextField).first, '新的主页名称');
    await tester.tap(find.text(ObjectHomepageText.homepageMaintenanceSave));
    await _pumpUi(tester);

    expect(find.byType(AppFormErrorCard), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'maintenance_submit' &&
            event.extensions['result'] == 'failure',
      ),
      isTrue,
    );
  });

  testWidgets('版本冲突展示结构化错误并刷新服务端最新资料', (tester) async {
    final repository = _MaintenanceRepository(
      ownerId: _ownerId,
      submitError: CloudException(
        type: CloudErrorType.unknown,
        message: 'stale homepage version',
        statusCode: 409,
        code: EntityErrorCode.versionConflict.code,
        runtimeFailure: testRuntimeFailure(
          code: EntityErrorCode.versionConflict.code,
          kind: RuntimeFailureKind.unavailable,
          nature: RuntimeFailureNature.transient,
        ),
      ),
    );
    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        viewerOwnerId: _ownerId,
        telemetry: RecordingAppTelemetryRecorder(),
        child: HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await _pumpUi(tester);

    await tester.enterText(find.byType(CupertinoTextField).first, '过期资料');
    await tester.tap(find.text(ObjectHomepageText.homepageMaintenanceSave));
    await _pumpUi(tester);

    final errorCard = tester.widget<AppFormErrorCard>(
      find.byType(AppFormErrorCard),
    );
    expect(errorCard.semantic.sourceCode, EntityErrorCode.versionConflict.code);
    expect(errorCard.semantic.primaryAction, isNotNull);
    await tester.tap(find.text(errorCard.semantic.primaryAction!.label));
    await _pumpUi(tester);

    expect(repository.updateCalls, 1);
    expect(repository.detailLoadCalls, 2);
    expect(find.byType(AppFormErrorCard), findsNothing);
    expect(
      tester
          .widget<CupertinoTextField>(find.byType(CupertinoTextField).first)
          .controller
          ?.text,
      isNot('过期资料'),
    );
  });

  testWidgets('主页维护页加载失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        repository: _LoadFailingHomepageRepository(),
        viewerOwnerId: _ownerId,
        telemetry: RecordingAppTelemetryRecorder(),
        child: HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await _pumpUi(tester);

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);
  });

  testWidgets('游客关闭维护登录页回详情且不循环', (tester) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageMaintenance(id: _homepageId),
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
          builder: (_, _) => const Text('MAINTENANCE_SAFE_DETAIL'),
        ),
        GoRoute(
          path: AppRoutePaths.homepageMaintenancePathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, _) => HomepageMaintenancePage(homepageId: _homepageId),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => TextButton(
            key: const ValueKey<String>('maintenance-login-close'),
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
            _MaintenanceRepository(ownerId: _ownerId),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await _pumpUi(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('maintenance-login-close')),
    );
    await _pumpUi(tester);
    await tester.pump();

    expect(find.text('MAINTENANCE_SAFE_DETAIL'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('maintenance-login-close')),
      findsNothing,
    );
  });
}

Widget _buildApp({
  required HomepageFacetSet repository,
  required String viewerOwnerId,
  required RecordingAppTelemetryRecorder telemetry,
  required Widget child,
}) {
  final router = GoRouter(
    initialLocation: AppRoutePaths.home,
    routes: <RouteBase>[
      GoRoute(path: AppRoutePaths.home, builder: (_, _) => child),
      GoRoute(
        path: AppRoutePaths.homepageMaintenancePathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (_, _) => HomepageMaintenancePage(homepageId: _homepageId),
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
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          personaId: 'viewer-persona',
          ownerUserId: viewerOwnerId,
          displayName: '主页维护者',
          avatarUrl: '',
        ),
      ),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

class _MaintenanceHost extends StatefulWidget {
  const _MaintenanceHost();

  @override
  State<_MaintenanceHost> createState() => _MaintenanceHostState();
}

class _MaintenanceHostState extends State<_MaintenanceHost> {
  bool? _result;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: <Widget>[
          TextButton(
            key: const ValueKey<String>('open-maintenance'),
            onPressed: () async {
              final result = await context.push<bool>(
                AppRoutePaths.homepageMaintenance(id: _homepageId),
              );
              if (mounted) {
                setState(() => _result = result);
              }
            },
            child: const Text('OPEN_MAINTENANCE'),
          ),
          Text('MAINTENANCE_RESULT:$_result'),
        ],
      ),
    );
  }
}

class _MaintenanceRepository extends MockHomepageRepository {
  _MaintenanceRepository({
    required this.ownerId,
    this.failSubmit = false,
    this.submitError,
  });

  final String ownerId;
  final bool failSubmit;
  final Object? submitError;
  int detailLoadCalls = 0;
  int updateCalls = 0;
  HomepageBasicDraft? lastDraft;

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    detailLoadCalls += 1;
    final detail = await super.getHomepageDetail(homepageId);
    return detail.copyWith(
      claimStatus: 'claimed',
      ownerUserId: ownerId,
      ownerPersonaId: 'owner-persona',
    );
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    updateCalls += 1;
    lastDraft = draft;
    if (failSubmit) {
      throw StateError('redacted maintenance failure');
    }
    if (submitError case final error?) {
      throw error;
    }
    final detail = await getHomepageDetail(homepageId);
    return detail.copyWith(
      title: draft.title,
      subtitle: draft.subtitle,
      city: draft.city,
      address: draft.address,
      categoryTags: draft.categoryTags,
    );
  }
}

class _LoadFailingHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    throw StateError('load failed');
  }
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'entity-test-token',
    refreshToken: 'entity-test-refresh-token',
    ownerId: _ownerId,
    activePersonaId: 'viewer-persona',
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
