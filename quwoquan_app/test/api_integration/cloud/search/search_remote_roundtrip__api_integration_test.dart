// spec_ref: specs/feature-tree/global-search-experience/spec.md#dom-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/search/search_feedback_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/search_query_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'GAMMA_GATEWAY_URL',
  defaultValue: '',
);
const _definedAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _definedEvidencePath = String.fromEnvironment(
  'SEARCH_REMOTE_EVIDENCE_PATH',
);
final _accessToken =
    _definedAccessToken.trim().isNotEmpty
        ? _definedAccessToken
        : Platform.environment['TEST_AUTH_TOKEN']?.trim() ?? '';
final _evidencePath =
    _definedEvidencePath.trim().isNotEmpty
        ? _definedEvidencePath
        : Platform.environment['SEARCH_REMOTE_EVIDENCE_PATH']?.trim() ?? '';

final class _GammaSearchClientContext implements CloudClientContextProvider {
  const _GammaSearchClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-search-api-integration',
      deviceActorId: 'gamma-search-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  setUpAll(() {
    if (_accessToken.trim().isEmpty) {
      fail(
        'Search feedback Remote API verification requires TEST_AUTH_TOKEN. '
        'Use the local Gamma acceptance-session issuer.',
      );
    }
  });

  test(
    'generated RemoteSearchRepository 通过 gateway 返回真实 canonical hits',
    () async {
      final httpClient = _buildGammaHttpClient();
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaSearchClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final remote = RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'gamma-search-device',
          ),
        ),
      );
      final repository = RemoteSearchRepository(remoteQuery: remote);

      final response = await repository.search(
        const SearchRequest(
          query: '西湖',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{
            SearchObjectType.contentPost,
            SearchObjectType.entityHomepage,
            SearchObjectType.locationPlace,
            SearchObjectType.userProfile,
          },
          limit: 20,
        ),
      );

      expect(response.searchRequestId, isNotEmpty);
      expect(response.hits, isNotEmpty);
      expect(
        response.hits.every(
          (hit) => hit.objectId.isNotEmpty && hit.title.isNotEmpty,
        ),
        isTrue,
      );
      expect(
        response.hits.any(
          (hit) =>
              hit.objectType == SearchObjectType.contentPost ||
              hit.objectType == SearchObjectType.entityHomepage ||
              hit.objectType == SearchObjectType.locationPlace,
        ),
        isTrue,
      );
      final feedback = RemoteSearchFeedbackAdapter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'gamma-search-device',
          ),
        ),
      );
      final feedbackHit = response.hits.firstWhere(
        (hit) => _searchFeedbackTarget(hit.objectType) != null,
      );
      final feedbackTarget = _searchFeedbackTarget(feedbackHit.objectType)!;
      final feedbackCommands = <ReportSearchFeedbackCommand>[
        ReportSearchFeedbackCommand(
          searchRequestId: response.searchRequestId!,
          eventType: SearchFeedbackEventType.impression,
          objectId: feedbackHit.objectId,
          rankPosition: feedbackHit.rankPosition,
          referralSource: 'api_integration',
        ),
        ReportSearchFeedbackCommand(
          searchRequestId: response.searchRequestId!,
          eventType: SearchFeedbackEventType.click,
          objectId: feedbackHit.objectId,
          target: feedbackTarget,
          rankPosition: feedbackHit.rankPosition,
          referralSource: 'api_integration',
        ),
        ReportSearchFeedbackCommand(
          searchRequestId: response.searchRequestId!,
          eventType: SearchFeedbackEventType.dwell,
          objectId: feedbackHit.objectId,
          target: feedbackTarget,
          rankPosition: feedbackHit.rankPosition,
          referralSource: 'api_integration',
          dwellMs: 3000,
        ),
      ];
      final feedbackAcks = await Future.wait<SearchFeedbackAck>(
        feedbackCommands.map(feedback.reportSearchFeedback),
      );
      expect(
        feedbackAcks.every((ack) => ack.accepted),
        isTrue,
      );
      expect(telemetry.events, hasLength(4));
      expect(telemetry.events.every((event) => event.succeeded), isTrue);
      expect(
        telemetry.events.every(
          (event) =>
              (event.requestId?.isNotEmpty ?? false) &&
              (event.traceId?.isNotEmpty ?? false),
        ),
        isTrue,
      );
      await _writeRemoteEvidence(
        <String, Object?>{
          'schema': 'search-remote-api-evidence-v1',
          'status': 'passed',
          'searchRequestId': response.searchRequestId,
          'events':
              telemetry.events
                  .map(
                    (event) => <String, Object?>{
                      'operationId': event.canonicalOperationId,
                      'requestId': event.requestId,
                      'traceId': event.traceId,
                      'succeeded': event.succeeded,
                    },
                  )
                  .toList(growable: false),
          'feedbackEvents':
              feedbackCommands
                  .map(
                    (command) => <String, Object?>{
                      'eventType': command.eventType.wireValue,
                      'objectId': command.objectId,
                      'target': command.target,
                      'rankPosition': command.rankPosition,
                      'dwellMs': command.dwellMs,
                    },
                  )
                  .toList(growable: false),
        },
      );
    },
  );
}

String? _searchFeedbackTarget(SearchObjectType objectType) {
  return switch (objectType) {
    SearchObjectType.contentPost => 'posts',
    SearchObjectType.entityHomepage => 'homepages',
    SearchObjectType.locationPlace => 'locations',
    SearchObjectType.userProfile => 'users',
    _ => null,
  };
}

Future<void> _writeRemoteEvidence(Map<String, Object?> evidence) async {
  if (_evidencePath.isEmpty) {
    return;
  }
  final output = File(_evidencePath);
  await output.parent.create(recursive: true);
  await output.writeAsString('${jsonEncode(evidence)}\n');
}

CloudHttpClient _buildGammaHttpClient() => CloudHttpClient();

final class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}
