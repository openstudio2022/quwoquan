import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract/production_cloud_operation_telemetry_evidence.dart';

const contentApiEnvironment = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const contentApiGatewayUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const contentApiAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const contentApiPersonaId = String.fromEnvironment('TEST_PERSONA_ID');

void requireContentApiRuntimeInputs() {
  if (contentApiGatewayUrl.trim().isEmpty ||
      contentApiAccessToken.trim().isEmpty ||
      contentApiPersonaId.trim().isEmpty) {
    fail(
      'Content API integration requires API_CONTRACT_BASE_URL, '
      'TEST_AUTH_TOKEN and TEST_PERSONA_ID from a candidate-bound identity.',
    );
  }
  CloudEnvironment.values.firstWhere(
    (candidate) => candidate.name == contentApiEnvironment,
    orElse: () => fail('Unsupported API_CONTRACT_ENV: $contentApiEnvironment'),
  );
}

CloudHttpClient newContentApiHttpClient() {
  return CloudHttpClient(
    authTokenProvider: const ContentApiTokenProvider(contentApiAccessToken),
  );
}

GeneratedCloudOperationClient buildContentApiClient({
  required CloudHttpClient httpClient,
  required CloudOperationTelemetrySink telemetrySink,
}) {
  return buildGeneratedCloudOperationClient(
    httpClient: httpClient,
    clientContextProvider: const ContentApiClientContext(),
    telemetrySink: telemetrySink,
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.values.firstWhere(
        (candidate) => candidate.name == contentApiEnvironment,
      ),
      gatewayBaseUri: Uri.parse(contentApiGatewayUrl),
    ),
  );
}

Future<ProductionCloudOperationTelemetryEvidence>
startContentApiTelemetryEvidence() =>
    ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: const ContentApiClientContext(),
    );

final class ContentApiTokenProvider implements CloudAuthTokenProvider {
  const ContentApiTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class ContentApiClientContext implements CloudClientContextProvider {
  const ContentApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() => const CloudClientContextSnapshot(
    sessionId: 'content-api-integration',
    deviceActorId: 'content-api-integration-device',
    platform: 'test',
    appVersion: 'api-integration',
    locale: 'zh-CN',
  );
}
