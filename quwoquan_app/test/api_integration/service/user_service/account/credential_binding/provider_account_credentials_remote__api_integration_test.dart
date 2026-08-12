// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
/// 真实 managed Gamma Provider 账号的只读凭证校验。
///
/// 访问令牌和 owner identity 仅从进程环境读取，不进入 dart-define、日志或失败
/// 文本。该 runner 只证明 production Remote 的脱敏 ListCredentials 路径；绑定、
/// 解绑、Provider 票据置换与双真机证据未闭合前不登记 readiness_case。
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/adapters/credential_binding_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  test(
    'production Remote reads a managed Provider account credential set',
    () async {
      final inputs = _CredentialProviderInputs.fromProcessEnvironment();
      final harness = await _CredentialProviderHarness.create(inputs);
      try {
        final result = await harness.reader.listCredentials(
          const ListCredentialsQuery(),
        );
        _validateManagedCredentialSet(result);

        final events = await harness.telemetry.waitForEvents(minimumCount: 1);
        if (events.length != 1 ||
            events.single.canonicalOperationId !=
                AppCloudOperationIds.userCredentialBindingListCredentials ||
            !events.single.succeeded ||
            events.single.statusCode != HttpStatus.ok) {
          throw StateError(
            'credential Provider read did not emit one successful canonical event',
          );
        }
      } finally {
        await harness.close();
      }
    },
  );
}

void _validateManagedCredentialSet(ListCredentialsSlice result) {
  if (result.credentials.isEmpty) {
    throw StateError('managed Provider account has no active credentials');
  }
  final ids = <String>{};
  var hasProviderCredential = false;
  final now = DateTime.now().toUtc();
  for (final credential in result.credentials) {
    final id = credential.id.trim();
    if (id.isEmpty || !ids.add(id)) {
      throw StateError('managed Provider credential identity is invalid');
    }
    if (!credential.isActive ||
        credential.version <= 0 ||
        credential.boundAt.toUtc().isAfter(now)) {
      throw StateError('managed Provider credential state is invalid');
    }
    if (credential.displayLabel?.trim().isEmpty == true) {
      throw StateError('managed Provider credential label is invalid');
    }
    hasProviderCredential =
        hasProviderCredential ||
        credential.credentialType != CredentialType.anonymousDevice;
  }
  if (!hasProviderCredential) {
    throw StateError('managed account does not expose a Provider credential');
  }
}

final class _CredentialProviderInputs {
  const _CredentialProviderInputs({
    required this.accessToken,
    required this.ownerId,
  });

  final String accessToken;
  final String ownerId;

  static _CredentialProviderInputs fromProcessEnvironment() {
    final accessToken =
        Platform.environment['QWQ_CREDENTIAL_PROVIDER_ACCESS_TOKEN']?.trim() ??
        '';
    final ownerId =
        Platform.environment['QWQ_CREDENTIAL_PROVIDER_OWNER_ID']?.trim() ?? '';
    if (accessToken.isEmpty || ownerId.isEmpty) {
      throw StateError(
        'managed credential Provider identity is not configured',
      );
    }
    return _CredentialProviderInputs(
      accessToken: accessToken,
      ownerId: ownerId,
    );
  }
}

final class _CredentialProviderHarness {
  const _CredentialProviderHarness({
    required this.reader,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteCredentialBindingQuery reader;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_CredentialProviderHarness> create(
    _CredentialProviderInputs inputs,
  ) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('credential Provider API runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty ||
        gateway.userInfo.isNotEmpty ||
        gateway.hasFragment) {
      throw StateError(
        'credential Provider API runner requires an HTTPS gateway',
      );
    }
    const clientContext = _CredentialProviderClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final httpClient = CloudHttpClient(
      authTokenProvider: _FixedTokenProvider(inputs.accessToken),
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
      return _CredentialProviderHarness(
        reader: RemoteCredentialBindingQuery(
          client: client,
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.settingsAccountSecurity.id,
            routeId: AppUiSurfaces.settingsAccountSecurity.routeId,
            clientPageId: clientPageId,
            actor: CloudOperationActorContext(accountId: inputs.ownerId),
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

final class _FixedTokenProvider implements CloudAuthTokenProvider {
  const _FixedTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _CredentialProviderClientContext
    implements CloudClientContextProvider {
  const _CredentialProviderClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'credential-provider-api-runner',
      deviceActorId: 'credential-provider-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
