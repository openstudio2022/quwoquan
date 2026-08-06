// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/adapters/ops_visit_append_writer.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/local_gamma_anonymous_session.dart';

const _environment = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBaseUrl = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);
const _authBaseUrl = String.fromEnvironment('API_CONTRACT_AUTH_BASE_URL');

late http.Client _httpClient;
late LocalGammaAnonymousSession _session;
bool _clientInitialized = false;

void main() {
  setUpAll(() async {
    if (_productOpsBaseUrl.trim().isEmpty || _authBaseUrl.trim().isEmpty) {
      throw StateError(
        'L3: ${_environment.toUpperCase()} visit-record candidate binding is incomplete',
      );
    }
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == _environment,
    );
    final gateway = Uri.parse(_productOpsBaseUrl);
    if (gateway.scheme != 'https' || gateway.host.isEmpty) {
      throw StateError(
        'L3: visit-record API requires a canonical HTTPS gateway',
      );
    }
    final probe = await http
        .get(gateway.resolve('/healthz'))
        .timeout(const Duration(seconds: 5));
    if (probe.statusCode >= 400) {
      throw StateError(
        'L3: ${_environment.toUpperCase()} product-ops health returned '
        '${probe.statusCode}, so visit-record API integration cannot execute',
      );
    }
    _httpClient = http.Client();
    _clientInitialized = true;
    _session = await LocalGammaAnonymousSession.login(
      client: _httpClient,
      baseUrl: _authBaseUrl,
      subject: 'visit-record-api-integration',
    );
    _resolvedEnvironment = environment;
    _gateway = gateway;
  });

  tearDownAll(() {
    if (_clientInitialized) _httpClient.close();
  });

  test(
    'generated VisitRecord Remote derives actor from the verified principal',
    () async {
      final suffix = DateTime.now().microsecondsSinceEpoch;
      final targetKey = 'page_contract_$suffix';
      final writer = RemoteOpsVisitAppendWriter(
        client: _generatedClient(),
        invocationContext: (clientPageId, {required idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.appShell.id,
              routeId: AppUiSurfaces.appShell.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: CloudOperationActorContext(
                accountId: _session.ownerId,
                personaId: _session.personaId,
                deviceActorId: 'visit-record-api-integration',
              ),
            ),
      );

      await writer.recordVisit(
        RecordVisitRequest(
          targetType: VisitTargetType.page,
          targetKey: targetKey,
        ),
        idempotencyKey: 'visit-record-api-integration-$suffix',
      );
    },
  );
}

late CloudEnvironment _resolvedEnvironment;
late Uri _gateway;

GeneratedCloudOperationClient _generatedClient() {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: _httpClient,
      authTokenProvider: _SessionTokenProvider(_session.accessToken),
    ),
    clientContextProvider: const _VisitApiClientContext(),
    telemetrySink: const AppCloudOperationTelemetrySink(
      clientContextProvider: _VisitApiClientContext(),
    ),
    environment: CloudRuntimeEnvironment(
      environment: _resolvedEnvironment,
      gatewayBaseUri: _gateway,
    ),
  );
}

final class _SessionTokenProvider implements CloudAuthTokenProvider {
  const _SessionTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}

final class _VisitApiClientContext implements CloudClientContextProvider {
  const _VisitApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'visit-record-api-integration',
      platform: 'api-integration',
      appVersion: 'contract',
      locale: 'zh-CN',
      deviceActorId: 'visit-record-api-integration',
    );
  }
}
