// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/adapters/remote_app_release_recovery_reader.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/application/app_release_recovery_reader.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
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

late http.Client _httpClient;
late RecoveryRuntimeBinding _binding;

void main() {
  setUpAll(() async {
    _binding = RecoveryRuntimeBinding.fromLaunchManifest(
      environment: _environment,
      recoveryBaseUrl: _productOpsBaseUrl,
      runtimeConfigDigest: _runtimeConfigDigest,
      effectiveLaunchManifestDigest: _effectiveLaunchManifestDigest,
    );
    _httpClient = http.Client();
    final probe = await _httpClient
        .get(_binding.recoveryOrigin.resolve('/healthz'))
        .timeout(const Duration(seconds: 5));
    if (probe.statusCode >= 400) {
      throw StateError(
        'L3: ${_environment.toUpperCase()} product-ops health returned '
        '${probe.statusCode}, so app-release API integration cannot execute',
      );
    }
  });

  tearDownAll(() => _httpClient.close());

  test(
    'candidate-bound public recovery facts round-trip for Android and iOS',
    () async {
      final reader = RemoteAppReleaseRecoveryReader(
        client: _generatedClient(),
        invocationContext: () => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: OpsRequestPageIds.getAppRecoveryVersion,
          actor: const CloudOperationActorContext(),
        ),
      );

      final android = await reader.read(
        AppReleaseRecoveryQuery(
          platform: 'android',
          appVersion: '0.0.0-api-integration',
          buildNumber: 1,
        ),
      );
      final ios = await reader.read(
        AppReleaseRecoveryQuery(
          platform: 'ios',
          appVersion: '0.0.0-api-integration',
          buildNumber: 1,
        ),
      );

      expect(android.latestBuild, greaterThan(0));
      expect(android.latestVersion, isNotEmpty);
      expect(Uri.parse(android.recoveryUrl).scheme, 'https');
      expect(Uri.parse(android.updateUrl!).scheme, 'https');
      expect(ios.latestBuild, greaterThan(0));
      expect(ios.latestVersion, isNotEmpty);
      expect(Uri.parse(ios.recoveryUrl).scheme, 'https');
      expect(ios.updateUrl, isNull);
    },
  );
}

GeneratedCloudOperationClient _generatedClient() {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(client: _httpClient),
    clientContextProvider: const _RecoveryApiClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
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
      sessionId: 'app-release-recovery-api-integration',
      platform: 'api-integration',
      appVersion: 'contract',
      locale: 'zh-CN',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
