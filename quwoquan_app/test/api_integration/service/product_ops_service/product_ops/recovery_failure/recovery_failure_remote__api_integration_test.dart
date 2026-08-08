// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
// readiness_case: recovery_failure_report_recovery_failure_app_api
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/adapters/remote_recovery_failure_writer.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/application/recovery_failure_writer.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_runtime_binding.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _environment = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBaseUrl = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);
const _runtimeConfigDigest = String.fromEnvironment(
  'API_CONTRACT_RUNTIME_CONFIG_DIGEST',
);
const _effectiveLaunchManifestDigest = String.fromEnvironment(
  'API_CONTRACT_EFFECTIVE_LAUNCH_MANIFEST_DIGEST',
);

http.Client? _httpClient;
late RecoveryRuntimeBinding _binding;

void main() {
  setUpAll(() async {
    _binding = RecoveryRuntimeBinding.fromLaunchManifest(
      environment: _environment,
      recoveryBaseUrl: _productOpsBaseUrl,
      runtimeConfigDigest: _runtimeConfigDigest,
      effectiveLaunchManifestDigest: _effectiveLaunchManifestDigest,
    );
    final httpClient = http.Client();
    _httpClient = httpClient;
    final probe = await httpClient
        .get(_binding.recoveryOrigin.resolve('/healthz'))
        .timeout(const Duration(seconds: 5));
    if (probe.statusCode >= 400) {
      throw StateError(
        'L3: ${_environment.toUpperCase()} product-ops health returned '
        '${probe.statusCode}, so recovery-failure API integration cannot execute',
      );
    }
  });

  tearDownAll(() => _httpClient?.close());

  test(
    'candidate-bound recovery failure accepts the strict ten-field record',
    () async {
      final writer = RemoteRecoveryFailureWriter(
        client: _generatedClient(),
        invocationContext: () => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: OpsRequestPageIds.reportRecoveryFailure,
          actor: const CloudOperationActorContext(),
        ),
      );

      await writer.write(
        RecoveryFailureRecord(
          occurredAt: DateTime.now().toUtc(),
          appVersion: '0.0.0-api-integration',
          buildNumber: '1',
          platform: 'android',
          osVersion: 'api-integration',
          deviceModel: 'api-integration',
          errorSource: 'runtime',
          errorType: 'ApiIntegrationRecoveryProbe',
          errorMessage: 'Synthetic recovery API integration probe',
          stackTrace: 'Synthetic stack unavailable',
        ),
      );
    },
  );
}

GeneratedCloudOperationClient _generatedClient() {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(client: _httpClient!),
    clientContextProvider: const _RecoveryApiClientContext(),
    telemetrySink: const AppCloudOperationTelemetrySink(
      clientContextProvider: _RecoveryApiClientContext(),
    ),
    environment: CloudRuntimeEnvironment(
      environment: _binding.environment,
      gatewayBaseUri: _binding.recoveryOrigin,
    ),
  );
}

final class _RecoveryApiClientContext implements CloudClientContextProvider {
  const _RecoveryApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'recovery-failure-api-integration',
      platform: 'api-integration',
      appVersion: 'contract',
      locale: 'zh-CN',
    );
  }
}
