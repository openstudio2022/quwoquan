// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
/// 真实 managed-nonprod SMS Provider source runner。
///
/// 手机号与 protected broker 凭据只从进程环境读取，不进入 dart-define、日志或失败
/// 文本；缺少 Provider、HTTPS loopback broker 或一次性 OTP readback 时必须 fail closed。
/// 当前未登记 readiness_case，直到候选绑定的 Provider receipt 与环境结果包完成。
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  test(
    'production Remote sends SMS and protected broker confirms delivery',
    () async {
      final inputs = _ProviderInputs.fromProcessEnvironment();
      final harness = await _SmsChallengeHarness.create();
      try {
        final result = await harness.writer.sendOtp(
          SendOtpCommand(
            phone: inputs.phone,
            deviceId: 'sms-provider-api-runner',
            platform: OtpClientPlatform.acceptance,
            appVersion: 'api-integration',
            sourceOperation: 'login',
          ),
          idempotencyKey: 'sms-provider-api-integration-000001',
        );
        if (result.maskedPhone.trim().isEmpty ||
            result.maskedPhone == inputs.phone ||
            result.expiresInSeconds <= 0 ||
            result.challengeId.trim().isEmpty) {
          throw StateError('SMS Provider returned an invalid typed challenge');
        }

        await _readProtectedOtp(inputs);
        final events = await harness.telemetry.waitForEvents(minimumCount: 1);
        expect(events, hasLength(1));
        expect(events.single.succeeded, isTrue);
      } finally {
        await harness.close();
      }
    },
  );
}

final class _ProviderInputs {
  const _ProviderInputs({
    required this.phone,
    required this.brokerUri,
    required this.brokerToken,
  });

  final String phone;
  final Uri brokerUri;
  final String brokerToken;

  static _ProviderInputs fromProcessEnvironment() {
    final phone =
        Platform.environment['QWQ_PROVIDER_API_SMS_PHONE']?.trim() ?? '';
    final brokerUrl =
        Platform.environment['QWQ_PROVIDER_API_OTP_BROKER_URL']?.trim() ?? '';
    final brokerToken =
        Platform.environment['QWQ_PROVIDER_API_OTP_BROKER_TOKEN']?.trim() ?? '';
    if (!RegExp(r'^\+?[0-9]{8,15}$').hasMatch(phone)) {
      throw StateError('managed SMS Provider phone is not configured');
    }
    if (brokerToken.isEmpty) {
      throw StateError('protected OTP broker credential is not configured');
    }
    final brokerUri = Uri.tryParse(brokerUrl);
    final loopback =
        brokerUri?.host == '127.0.0.1' || brokerUri?.host == 'localhost';
    if (brokerUri == null ||
        brokerUri.scheme != 'https' ||
        !brokerUri.hasAuthority ||
        !brokerUri.hasPort ||
        !loopback ||
        brokerUri.userInfo.isNotEmpty ||
        brokerUri.path != '/v1/otp' ||
        brokerUri.hasQuery ||
        brokerUri.hasFragment) {
      throw StateError(
        'protected OTP broker must be the canonical HTTPS loopback',
      );
    }
    return _ProviderInputs(
      phone: phone,
      brokerUri: brokerUri,
      brokerToken: brokerToken,
    );
  }
}

Future<void> _readProtectedOtp(_ProviderInputs inputs) async {
  final client = HttpClient();
  try {
    final request = await client.postUrl(inputs.brokerUri);
    request.headers.set(
      HttpHeaders.authorizationHeader,
      'Bearer ${inputs.brokerToken}',
    );
    request.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
    final response = await request.close().timeout(const Duration(seconds: 10));
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode != HttpStatus.ok) {
      throw StateError('protected OTP broker did not confirm delivery');
    }
    final payload = jsonDecode(body);
    final code = payload is Map<String, dynamic>
        ? (payload['code'] as String? ?? '')
        : '';
    if (!RegExp(r'^[0-9]{6}$').hasMatch(code)) {
      throw StateError(
        'protected OTP broker returned an invalid one-time code',
      );
    }
  } finally {
    client.close(force: true);
  }
}

final class _SmsChallengeHarness {
  const _SmsChallengeHarness({
    required this.writer,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteAuthenticationChallengeCommandWriter writer;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_SmsChallengeHarness> create() async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('SMS Provider API runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty) {
      throw StateError('SMS Provider API runner requires an HTTPS gateway');
    }
    const clientContext = _SmsApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final httpClient = CloudHttpClient(
      authTokenProvider: const _PublicTokenProvider(),
    );
    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: gateway,
        ),
      );
      return _SmsChallengeHarness(
        writer: RemoteAuthenticationChallengeCommandWriter(
          client: client,
          invocationContext: (clientPageId, {String? idempotencyKey}) =>
              CloudOperationInvocationContext(
                surfaceId: AppUiSurfaces.login.id,
                routeId: AppUiSurfaces.login.routeId,
                clientPageId: clientPageId,
                idempotencyKey: idempotencyKey,
                actor: const CloudOperationActorContext(
                  deviceActorId: 'sms-provider-api-runner',
                ),
              ),
        ),
        telemetry: telemetry,
        httpClient: httpClient,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  Future<void> close() async {
    _httpClient.close();
    await telemetry.dispose();
  }
}

final class _PublicTokenProvider implements CloudAuthTokenProvider {
  const _PublicTokenProvider();

  @override
  Future<String?> getAccessToken() async => null;
}

final class _SmsApiClientContext implements CloudClientContextProvider {
  const _SmsApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'sms-provider-api-runner',
      deviceActorId: 'sms-provider-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
