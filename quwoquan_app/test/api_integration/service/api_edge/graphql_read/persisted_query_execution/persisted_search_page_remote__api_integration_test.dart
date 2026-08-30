// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-002
// readiness_case: persisted_query_execution_search_page_app_api
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/api_edge/graphql_read/persisted_query_execution/adapters/persisted_search_page_query_remote.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _environmentName = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _gatewayUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _query = String.fromEnvironment(
  'PERSISTED_SEARCH_PROBE_QUERY',
  defaultValue: '西湖',
);
const _definedEvidencePath = String.fromEnvironment(
  'PERSISTED_QUERY_EXECUTION_REMOTE_EVIDENCE_PATH',
);
final _evidencePath = _definedEvidencePath.trim().isNotEmpty
    ? _definedEvidencePath
    : Platform.environment['PERSISTED_QUERY_EXECUTION_REMOTE_EVIDENCE_PATH']
              ?.trim() ??
          '';

final class _GatewayClientContext implements CloudClientContextProvider {
  const _GatewayClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-persisted-query-execution-api-integration',
      deviceActorId: 'gamma-persisted-query-execution-runner',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  setUpAll(() {
    if (_environmentName != 'gamma') {
      fail('PersistedQueryExecution App API integration only permits gamma.');
    }
    final gateway = Uri.tryParse(_gatewayUrl);
    if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
      fail(
        'PersistedQueryExecution requires API_CONTRACT_BASE_URL over HTTPS.',
      );
    }
    if (_query.trim().isEmpty) {
      fail('PERSISTED_SEARCH_PROBE_QUERY must be non-empty.');
    }
  });

  test('generated persisted GraphQL Remote decodes SearchPage', () async {
    final httpClient = CloudHttpClient();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: const _GatewayClientContext(),
    );
    addTearDown(httpClient.close);
    addTearDown(telemetry.dispose);
    final executor = buildGeneratedCloudOperationExecutor(
      httpClient: httpClient,
      clientContextProvider: const _GatewayClientContext(),
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: Uri.parse(_gatewayUrl),
      ),
    );
    final remote = RemotePersistedSearchPageQuery(
      client: GeneratedSearchPageGraphQLClient(executor),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(
          deviceActorId: 'gamma-persisted-query-execution-runner',
        ),
      ),
    );

    final page = await remote.searchPage(
      SearchPageInput(query: _query.trim(), first: 1),
    );

    expect(page.searchRequestId, isNotEmpty);
    expect(page.items, isA<List<SearchPageItem>>());
    expect(page.facets, isA<List<SearchPageFacet>>());
    expect(page.degradeSignals, isA<List<SearchPageDegradeSignal>>());
    final events = await telemetry.waitForEvents(minimumCount: 1);
    expect(
      events.single.canonicalOperationId,
      'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery',
    );
    expect(events.single.succeeded, isTrue);
    await _writeEvidence(<String, Object?>{
      'schema': 'persisted-query-execution-remote-api-evidence',
      'status': 'passed',
      'searchRequestId': page.searchRequestId,
      'itemCount': page.items.length,
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
