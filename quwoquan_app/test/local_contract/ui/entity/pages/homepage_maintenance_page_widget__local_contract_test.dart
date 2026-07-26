import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_maintenance_page.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';
import '../../../../support/runtime_failure_fixtures.dart';

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
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(CupertinoTextField).first, '新的主页名称');
    await tester.tap(find.text(UITextConstants.homepageMaintenanceSave));
    await tester.pumpAndSettle();

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
        child: const HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(
      find.text(UITextConstants.homepageMaintenanceUnavailableTitle),
      findsOneWidget,
    );
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
        child: const HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField).first, '新的主页名称');
    await tester.tap(find.text(UITextConstants.homepageMaintenanceSave));
    await tester.pumpAndSettle();

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
        child: const HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(CupertinoTextField).first, '过期资料');
    await tester.tap(find.text(UITextConstants.homepageMaintenanceSave));
    await tester.pumpAndSettle();

    final errorCard = tester.widget<AppFormErrorCard>(
      find.byType(AppFormErrorCard),
    );
    expect(errorCard.semantic.sourceCode, EntityErrorCode.versionConflict.code);
    expect(errorCard.semantic.primaryAction, isNotNull);
    await tester.tap(find.text(errorCard.semantic.primaryAction!.label));
    await tester.pumpAndSettle();

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
        child: const HomepageMaintenancePage(homepageId: _homepageId),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
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
          builder: (_, _) =>
              const HomepageMaintenancePage(homepageId: _homepageId),
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
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('maintenance-login-close')),
    );
    await tester.pumpAndSettle();
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
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      homepageFacetSetProvider.overrideWithValue(repository),
      appTelemetryReporterProvider.overrideWithValue(telemetry),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          subAccountId: 'viewer-persona',
          ownerUserId: viewerOwnerId,
          displayName: '主页维护者',
          avatarUrl: '',
        ),
      ),
    ],
    child: MaterialApp(home: child),
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
              final result = await Navigator.of(context).push<bool>(
                CupertinoPageRoute<bool>(
                  builder: (_) =>
                      const HomepageMaintenancePage(homepageId: _homepageId),
                ),
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
      ownerSubAccountId: 'owner-persona',
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
    ownerId: _ownerId,
    activeSubAccountId: 'viewer-persona',
  );
}

class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
