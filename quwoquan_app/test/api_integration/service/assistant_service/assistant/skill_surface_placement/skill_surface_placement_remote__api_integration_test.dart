// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
// readiness_case: skill_surface_placement_app_api
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/adapters/skill_surface_placement_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _environmentName = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _gatewayUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _definedAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _surfaceKindValue = String.fromEnvironment(
  'SKILL_SURFACE_KIND',
  defaultValue: 'conversation',
);
const _surfaceId = String.fromEnvironment('SKILL_SURFACE_ID');
const _definedEvidencePath = String.fromEnvironment(
  'SKILL_SURFACE_PLACEMENT_REMOTE_EVIDENCE_PATH',
);

final _accessToken = _definedAccessToken.trim().isNotEmpty
    ? _definedAccessToken
    : Platform.environment['TEST_AUTH_TOKEN']?.trim() ?? '';
final _evidencePath = _definedEvidencePath.trim().isNotEmpty
    ? _definedEvidencePath
    : Platform.environment['SKILL_SURFACE_PLACEMENT_REMOTE_EVIDENCE_PATH']
              ?.trim() ??
          '';

final class _PlacementClientContext implements CloudClientContextProvider {
  const _PlacementClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-skill-surface-placement-api-integration',
      deviceActorId: 'gamma-skill-surface-placement-runner',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  setUpAll(() {
    if (_environmentName != 'gamma') {
      fail('SkillSurfacePlacement App API integration only permits gamma.');
    }
    final gateway = Uri.tryParse(_gatewayUrl);
    if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
      fail('SkillSurfacePlacement requires API_CONTRACT_BASE_URL over HTTPS.');
    }
    if (_accessToken.isEmpty || _surfaceId.trim().isEmpty) {
      fail(
        'SkillSurfacePlacement requires TEST_AUTH_TOKEN and '
        'SKILL_SURFACE_ID from the candidate-bound nonprod identity.',
      );
    }
  });

  test('generated Remote reads the authoritative shared placement', () async {
    final httpClient = CloudHttpClient(
      authTokenProvider: _StaticTokenProvider(_accessToken),
    );
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: const _PlacementClientContext(),
    );
    addTearDown(httpClient.close);
    addTearDown(telemetry.dispose);
    final generatedClient = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _PlacementClientContext(),
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: Uri.parse(_gatewayUrl),
      ),
    );
    final remote = RemoteAssistantSkillSurfacePlacementAdapter(
      client: generatedClient,
      invocationContext: (clientPageId, {String? idempotencyKey}) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.assistantSkills.id,
            routeId: AppUiSurfaces.assistantSkills.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              deviceActorId: 'gamma-skill-surface-placement-runner',
            ),
            idempotencyKey: idempotencyKey,
          ),
    );
    final surfaceKind = parseSkillSurfaceKindStrict(_surfaceKindValue);

    final placement = await remote.getSkillSurfacePlacement(
      surfaceKind: surfaceKind,
      surfaceId: _surfaceId,
    );

    expect(placement.id, isNotEmpty);
    expect(placement.surfaceKind, surfaceKind);
    expect(placement.surfaceId, _surfaceId);
    expect(placement.revision, greaterThanOrEqualTo(1));
    expect(
      placement.disabledSkillIds.toSet(),
      hasLength(placement.disabledSkillIds.length),
    );
    final events = await telemetry.waitForEvents(minimumCount: 1);
    expect(
      events.single.canonicalOperationId,
      'assistant.skill_surface_placement.GetSkillSurfacePlacement',
    );
    expect(events.single.succeeded, isTrue);
    await _writeEvidence(<String, Object?>{
      'schema': 'skill-surface-placement-remote-api-evidence',
      'status': 'passed',
      'surfaceKind': placement.surfaceKind.wireName,
      'surfaceId': placement.surfaceId,
      'placementId': placement.id,
      'revision': placement.revision,
      'requestId': events.single.requestId,
      'traceId': events.single.traceId,
    });
  });
}

Future<void> _writeEvidence(Map<String, Object?> evidence) async {
  if (_evidencePath.isEmpty) return;
  final output = File(_evidencePath);
  await output.parent.create(recursive: true);
  await output.writeAsString('${jsonEncode(evidence)}\n');
}

final class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}
