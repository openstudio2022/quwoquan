// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
/// User 身份账号域 API Contract Runner。
///
/// 覆盖真实 gamma 环境的登录 → UserSettings 20 字段读写 → 登出主链路，
/// 验证 AccountSession、UserSettings 与鉴权 operation.Context 端到端闭环。
/// 社交登录受 R-AUTH-001 正式凭据阻断，不在本 runner 伪造 provider 结果。
///
/// 执行：
/// ```
/// flutter test test/api_integration/cloud/user/user_api_contract_runner.dart \
///   --dart-define=API_CONTRACT_ENV=gamma \
///   --dart-define=API_CONTRACT_BASE_URL=https://gamma-api.quwoquan.com
/// ```
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/user/account/account_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/account_session/account_session_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/api_contract/local_bad_certificate_overrides.dart';
import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _allowBadCertificateForLocalApiContract = bool.fromEnvironment(
  'API_CONTRACT_ALLOW_BAD_CERT',
);
const _deviceId = 'user-identity-api-contract-device';

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _UserApiClientContext implements CloudClientContextProvider {
  const _UserApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'user-identity-api-contract',
      deviceActorId: _deviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

late CloudHttpClient _httpClient;
late _MutableAccessTokenProvider _tokenProvider;
late RecordingCloudOperationTelemetrySink _telemetry;
late RemoteAccountSessionCommandWriter _accountSessions;
late RemoteAccountLifecycleCommandWriter _accountLifecycle;
late RemoteUserSettingsQueryReader _settingsReader;
late RemoteUserSettingsCommandWriter _settingsCommands;
late AuthSessionGrant _session;
var _httpClientInitialized = false;
String? _ownerId;
String? _personaId;

CloudOperationInvocationContext _invocationContext(String clientPageId) {
  final surface = _surfaceForClientPage(clientPageId);
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: CloudOperationActorContext(
      accountId: _ownerId,
      personaId: _personaId,
      deviceActorId: _deviceId,
    ),
  );
}

AppUiSurface _surfaceForClientPage(String clientPageId) {
  if (clientPageId == UserRequestPageIds.loginAnonymous ||
      clientPageId == UserRequestPageIds.refreshToken) {
    return AppUiSurfaces.appShell;
  }
  if (clientPageId == UserRequestPageIds.getNotificationSettings ||
      clientPageId == UserRequestPageIds.updateNotificationSettings) {
    return AppUiSurfaces.settingsNotifications;
  }
  if (clientPageId == UserRequestPageIds.getCallSettings ||
      clientPageId == UserRequestPageIds.updateCallSettings) {
    return AppUiSurfaces.settingsCalls;
  }
  if (clientPageId == UserRequestPageIds.logout) {
    return AppUiSurfaces.settingsAccountSecurity;
  }
  if (clientPageId == UserRequestPageIds.closeAccount) {
    return AppUiSurfaces.settingsAccountSecurity;
  }
  throw StateError('unsupported User API contract clientPageId: $clientPageId');
}

Future<AuthSessionGrant> _loginDisposableAccount(String purpose) async {
  final subject =
      'user-identity-$purpose-${DateTime.now().microsecondsSinceEpoch}';
  final session = await _accountSessions.loginAnonymous(
    LoginAnonymousCommand(
      installId: 'api-contract-$subject',
      deviceFingerprintHash: 'api-contract-$subject',
      platform: 'web',
      appVersion: 'api-integration',
    ),
  );
  _session = session;
  _ownerId = session.ownerId;
  _personaId = session.activeSub?.subAccountId;
  _tokenProvider.accessToken = session.accessToken;
  return session;
}

void main() {
  setUpAll(() async {
    installLocalApiContractBadCertificateOverride(
      enabled: _allowBadCertificateForLocalApiContract,
    );
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    _tokenProvider = _MutableAccessTokenProvider();
    _httpClient = CloudHttpClient(authTokenProvider: _tokenProvider);
    _httpClientInitialized = true;
    _telemetry = RecordingCloudOperationTelemetrySink();
    final client = buildGeneratedCloudOperationClient(
      httpClient: _httpClient,
      clientContextProvider: const _UserApiClientContext(),
      telemetrySink: _telemetry,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.values.firstWhere(
          (candidate) => candidate.name == _apiContractEnv,
          orElse: () => throw StateError(
            'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
          ),
        ),
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );
    _accountSessions = RemoteAccountSessionCommandWriter(
      client: client,
      invocationContext: _invocationContext,
    );
    _accountLifecycle = RemoteAccountLifecycleCommandWriter(
      client: client,
      invocationContext: _invocationContext,
    );
    _settingsReader = RemoteUserSettingsQueryReader(
      client: client,
      invocationContext: _invocationContext,
    );
    _settingsCommands = RemoteUserSettingsCommandWriter(
      client: client,
      invocationContext: _invocationContext,
    );
    await _loginDisposableAccount('settings');
  });

  tearDownAll(() {
    if (_httpClientInitialized) _httpClient.close();
    restoreLocalApiContractBadCertificateOverride();
  });

  test('匿名登录签发完整 AccountSession', () {
    expect(_session.accessToken, isNotEmpty);
    expect(_session.refreshToken, isNotEmpty);
    expect(_session.ownerId, isNotEmpty);
    expect(_session.activeSub?.subAccountId, isNotEmpty);
  });

  test('UserSettings notification/call roundtrip 与稳定命令回执', () async {
    final notification = await _settingsReader.getNotificationSettings();
    expect(notification.userId, _session.ownerId);
    expect(notification.updatedAt, isNotNull);

    final originalMarketing = notification.enableMarketing;
    final notificationReceipt = await _settingsCommands
        .updateNotificationSettings(
          UpdateNotificationSettingsCommand(
            enableMarketing: !originalMarketing,
          ),
        );
    expect(notificationReceipt.userId, _session.ownerId);
    expect(notificationReceipt.version, greaterThanOrEqualTo(1));

    final notificationReadback = await _settingsReader
        .getNotificationSettings();
    expect(notificationReadback.enableMarketing, !originalMarketing);

    final call = await _settingsReader.getCallSettings();
    expect(call.userId, _session.ownerId);
    expect(call.updatedAt, isNotNull);

    final originalVibration = call.enableCallVibration;
    final callReceipt = await _settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: !originalVibration),
    );
    expect(callReceipt.userId, _session.ownerId);
    expect(callReceipt.version, greaterThanOrEqualTo(1));
    final callReadback = await _settingsReader.getCallSettings();
    expect(callReadback.enableCallVibration, !originalVibration);

    // 恢复环境状态，runner 可重复执行。
    await _settingsCommands.updateNotificationSettings(
      UpdateNotificationSettingsCommand(enableMarketing: originalMarketing),
    );
    await _settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: originalVibration),
    );
    expect(_telemetry.events.every((event) => event.succeeded), isTrue);
  });

  test('Logout 吊销 refresh session 且返回稳定 ack', () async {
    final ack = await _accountSessions.logout(
      LogoutCommand(refreshToken: _session.refreshToken, deviceId: _deviceId),
    );
    expect(ack.revoked, true);
  });

  test('CloseAccount 返回不可逆终态并拒绝 refresh 与旧 access', () async {
    final closingSession = await _loginDisposableAccount('close');
    final result = await _accountLifecycle.closeAccount(
      CloseAccountCommand(
        clientRequestId:
            'close-${DateTime.now().microsecondsSinceEpoch.toString()}',
      ),
    );

    expect(result.accountState, 'closed');
    expect(DateTime.tryParse(result.closedAt), isNotNull);
    expect(result.idempotentReplay, isFalse);
    await expectLater(
      _accountSessions.refreshToken(
        RefreshTokenCommand(refreshToken: closingSession.refreshToken),
      ),
      throwsA(isA<CloudException>()),
    );
    await expectLater(
      _settingsReader.getNotificationSettings(),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'canonical account security error',
          anyOf('USER.AUTH.account_deleted', 'USER.AUTH.token_stale'),
        ),
      ),
    );
    expect(_telemetry.events.every((event) => event.succeeded), isFalse);
  });
}
