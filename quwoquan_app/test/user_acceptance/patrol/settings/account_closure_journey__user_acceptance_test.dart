// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
/// Patrol UAT：真实 Remote 账号注销后回到不可重入的游客安全态。
///
/// 本用例会永久关闭测试账号，必须通过 `QWQ_PATROL_INSTALL_ID` 提供一次性 install
/// identity；禁止复用其他 UAT 的默认账号。Gamma 与 Prod 使用同一测试，只替换环境、
/// Gateway 与一次性 install identity，不注入 Mock、fixture 或数据源开关。
///
/// Gamma 示例：
///   patrol test --target \
///     test/user_acceptance/patrol/settings/account_closure_journey__user_acceptance_test.dart \
///     -d `<device-id>` \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=QWQ_PATROL_SESSION_MODE=gamma_local_anonymous_runtime \
///     --dart-define=QWQ_PATROL_INSTALL_ID=account-closure-`date +%s` \
///     --dart-define=CLOUD_GATEWAY_BASE_URL=https://api.gamma.quwoquan.com:19000
///
/// Prod 必须使用专门创建且允许永久注销的一次性账号，并注入 `TEST_AUTH_TOKEN`、
/// `TEST_REFRESH_TOKEN`、`APP_CURRENT_OWNER_ID` 与 `APP_CURRENT_PERSONA_ID`；
/// 同时显式设置 `QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK=true`。禁止使用
/// `prod_sim_anonymous_runtime` 或任何日常验收账号。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLifecycleCommandWriterProvider;
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_account_security_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _installId = String.fromEnvironment('QWQ_PATROL_INSTALL_ID');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _prodDisposableAccountConfirmed = bool.fromEnvironment(
  'QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK',
);
const _homeSearchChrome = ValueKey<String>('home-search-chrome');

final class _FixedAccessTokenProvider implements CloudAuthTokenProvider {
  const _FixedAccessTokenProvider(this.accessToken);

  final String accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _ClosureProbeClientContext implements CloudClientContextProvider {
  const _ClosureProbeClientContext();

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'account-closure-credential-probe',
    deviceActorId: _installId,
    platform: CloudRequestHeaders.platform(),
    appVersion: 'account-closure-uat',
    locale: 'zh-CN',
  );
}

final class _DiscardingTelemetrySink implements CloudOperationTelemetrySink {
  const _DiscardingTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}

void main() {
  patrolTest(
    'account_closure_remote_returns_to_guest_safe_home',
    tags: ['t4', 'settings', 'account-closure', 'gamma-prod'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      if (_apiContractEnv != 'gamma' && _apiContractEnv != 'prod') {
        throw StateError(
          'Account closure UAT only accepts gamma or prod Remote composition',
        );
      }
      if (_appRuntimeEnv != _apiContractEnv) {
        throw StateError(
          'APP_RUNTIME_ENV=$_appRuntimeEnv must match '
          'API_CONTRACT_ENV=$_apiContractEnv',
        );
      }
      final gatewayUri = Uri.tryParse(_gatewayBaseUrl);
      if (gatewayUri == null ||
          gatewayUri.scheme != 'https' ||
          gatewayUri.host.isEmpty) {
        throw StateError(
          'Account closure UAT requires an absolute HTTPS '
          'CLOUD_GATEWAY_BASE_URL',
        );
      }
      if (_apiContractEnv == 'prod' && _patrolSessionMode.isNotEmpty) {
        throw StateError(
          'Prod account closure UAT requires an injected disposable session; '
          'runtime anonymous/prod-sim modes are not production evidence',
        );
      }
      if (_apiContractEnv == 'prod' && !_prodDisposableAccountConfirmed) {
        throw StateError(
          'Prod account closure UAT requires '
          'QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK=true',
        );
      }
      if (!_installId.startsWith('account-closure-') ||
          _installId == 'account-closure-') {
        throw StateError(
          'Account closure UAT requires a one-time '
          'QWQ_PATROL_INSTALL_ID=account-closure-<unique>',
        );
      }

      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.settingsAccountSecurity);
      await $(
        SettingsAccountSecurityPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
      final settingsContext = find
          .byType(SettingsAccountSecurityPage)
          .evaluate()
          .first;
      final container = ProviderScope.containerOf(settingsContext);
      final authenticatedSession = container.read(
        authSessionControllerProvider,
      );
      expect(authenticatedSession.status, AuthSessionStatus.authenticated);
      expect(authenticatedSession.accessToken, isNotEmpty);
      expect(authenticatedSession.refreshToken, isNotEmpty);

      final closeEntry = find.text(SettingsText.settingsCloseAccountEntry);
      final closeEntryReached = await _waitFor(
        $,
        closeEntry,
        timeout: const Duration(seconds: 30),
      );
      expect(closeEntryReached, isTrue, reason: '账号安全页必须展示注销入口');
      await $.tester.ensureVisible(closeEntry);
      await $.pump();
      await $.tester.tap(closeEntry);
      await $.pumpAndSettle();

      expect(
        find.text(SettingsText.settingsCloseAccountConfirmTitle),
        findsOneWidget,
      );
      expect(
        find.text(SettingsText.settingsCloseAccountConfirmMessage),
        findsOneWidget,
      );
      final confirm = find.descendant(
        of: find.byType(CupertinoAlertDialog),
        matching: find.text(SettingsText.settingsCloseAccountConfirmAction),
      );
      await $.tester.tap(confirm);

      final homeReached = await _waitFor(
        $,
        find.byKey(_homeSearchChrome),
        timeout: const Duration(seconds: 30),
      );
      expect(homeReached, isTrue, reason: '云端注销成功后必须进入首页安全态');

      final homeContext = find.byKey(_homeSearchChrome).evaluate().first;
      final session = container.read(authSessionControllerProvider);
      expect(session.status, AuthSessionStatus.guest);
      expect(session.accessToken, isEmpty);
      expect(session.refreshToken, isEmpty);
      expect(
        GoRouter.of(homeContext).routeInformationProvider.value.uri.path,
        AppRoutePaths.home,
      );
      await _expectClosedCredentialsRejected(
        container: container,
        closedSession: authenticatedSession,
      );

      await $.pump(const Duration(seconds: 4));
      expect(
        find.byType(SettingsAccountSecurityPage),
        findsNothing,
        reason: '游客安全首页不得重新进入已注销账号页或形成登录循环',
      );
    },
  );
}

Future<void> _expectClosedCredentialsRejected({
  required ProviderContainer container,
  required AuthSessionState closedSession,
}) async {
  await expectLater(
    container
        .read(accountSessionLifecycleCommandWriterProvider)
        .refreshToken(
          RefreshTokenCommand(refreshToken: closedSession.refreshToken),
        ),
    throwsA(isA<CloudException>()),
  );

  final tokenProvider = _FixedAccessTokenProvider(closedSession.accessToken);
  final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
  try {
    final environment = CloudRuntimeEnvironment(
      environment: CloudEnvironment.values.firstWhere(
        (candidate) => candidate.name == _apiContractEnv,
        orElse: () =>
            throw StateError('Unsupported API_CONTRACT_ENV: $_apiContractEnv'),
      ),
      gatewayBaseUri: Uri.parse(_gatewayBaseUrl),
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _ClosureProbeClientContext(),
      telemetrySink: const _DiscardingTelemetrySink(),
      environment: environment,
    );
    final settings = RemoteUserSettingsQueryReader(
      client: client,
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.settingsNotifications.id,
        routeId: AppUiSurfaces.settingsNotifications.routeId,
        clientPageId: clientPageId,
        actor: CloudOperationActorContext(
          accountId: closedSession.ownerId,
          personaId: closedSession.activePersonaId,
          deviceActorId: _installId,
        ),
      ),
    );
    await expectLater(
      settings.getNotificationSettings(),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'canonical closed credential error',
          anyOf('USER.AUTH.account_deleted', 'USER.AUTH.token_stale'),
        ),
      ),
    );
  } finally {
    httpClient.close();
  }
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  Finder finder, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
