// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/content/filter_catalog/filter_catalog_remote.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'GAMMA_GATEWAY_URL',
  defaultValue: '',
);

final class _GammaFilterCatalogClientContext
    implements CloudClientContextProvider {
  const _GammaFilterCatalogClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-filter-catalog-api-integration',
      deviceActorId: 'gamma-filter-catalog-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  test(
    'generated RemoteFilterCatalogQuery 读取真实 active canonical release',
    () async {
      final httpClient = _buildGammaHttpClient();
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaFilterCatalogClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final remote = RemoteFilterCatalogQuery(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.imageEditor.id,
          routeId: AppUiSurfaces.imageEditor.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'gamma-filter-catalog-device',
          ),
        ),
      );

      final stopwatch = Stopwatch()..start();
      final catalog = await remote.getActiveFilterCatalog();
      stopwatch.stop();

      expect(catalog.status, FilterCatalogReleaseStatus.active);
      expect(catalog.releaseId, isNotEmpty);
      expect(catalog.canonicalDigest, matches(RegExp(r'^[0-9a-f]{64}$')));
      expect(catalog.categoryCount, catalog.categories.length);
      expect(catalog.presetCount, catalog.presets.length);
      expect(catalog.categories, isNotEmpty);
      expect(catalog.presets, isNotEmpty);
      expect(
        catalog.presets
            .singleWhere((preset) => preset.presetId == 'original')
            .adjustments
            .isIdentity,
        isTrue,
      );
      final presetIds = catalog.presets
          .map((preset) => preset.presetId)
          .toSet();
      expect(
        catalog.recommendedFallbackPresetIds.every(presetIds.contains),
        isTrue,
      );
      expect(
        stopwatch.elapsed,
        lessThan(const Duration(milliseconds: 800)),
        reason: 'generated GetActiveFilterCatalog timeout/SLO budget',
      );
      expect(telemetry.events, hasLength(1));
      expect(telemetry.events.single.succeeded, isTrue);
      expect(telemetry.events.single.requestId, isNotEmpty);
      expect(telemetry.events.single.traceId, isNotEmpty);
    },
  );
}

CloudHttpClient _buildGammaHttpClient() => CloudHttpClient();
