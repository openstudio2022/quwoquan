// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
// readiness_case: event_record_report_event_batch_app_api
// readiness_case: event_record_report_startup_event_batch_app_api
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/event_record_batch_writer.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/startup_telemetry_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/api_contract_anonymous_session.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBase = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);
const _authBase = String.fromEnvironment('API_CONTRACT_AUTH_BASE_URL');

late http.Client _client;
late ApiContractAnonymousSession _session;
bool _clientInitialized = false;

void main() {
  setUpAll(() async {
    if (_productOpsBase.isEmpty || _authBase.isEmpty) {
      throw StateError(
        'L3: ${_apiContractEnv.toUpperCase()} ops API candidate binding is incomplete',
      );
    }
    try {
      final probe = await http
          .get(Uri.parse('$_productOpsBase/healthz'))
          .timeout(const Duration(seconds: 5));
      if (probe.statusCode >= 400) {
        throw StateError(
          'L3: product-ops $_apiContractEnv returned ${probe.statusCode}',
        );
      }
    } catch (error) {
      throw StateError('L3: product-ops $_apiContractEnv unreachable ($error)');
    }
    _client = http.Client();
    _clientInitialized = true;
    _session = await ApiContractAnonymousSession.login(
      client: _client,
      baseUrl: _authBase,
      subject: 'product-ops-api-contract',
    );
  });

  tearDownAll(() {
    if (_clientInitialized) _client.close();
  });

  group('ops_event_ingestion_end_to_end', () {
    test('generated EventRecord Remote 仅接受已验证主体并返回写入回执', () async {
      final pageName = 'contract_page_${DateTime.now().millisecondsSinceEpoch}';
      final suffix = DateTime.now().microsecondsSinceEpoch;
      final writer = RemoteOpsEventRecordBatchWriter(
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
                deviceActorId: 'event-record-api-integration',
              ),
            ),
      );

      final receipt = await writer.reportEventBatch(
        ops.EventRecordBatchRequest(
          events: <ops.EventRecord>[
            ops.EventRecord(
              logType: 'experience',
              eventType: 'page_open',
              sessionId: 'event-record-api-integration-$suffix',
              pageName: pageName,
              occurredAt: DateTime.now().toUtc(),
              deviceManufacturer: 'api-integration',
              deviceModel: 'api-integration',
              appVersion: 'local-e2e',
              networkClass: 'test',
              surfaceId: AppUiSurfaces.appShell.id,
              targetType: 'page',
              targetId: 'page_$pageName',
            ),
          ],
        ),
        idempotencyKey: 'event-record-api-integration-$suffix',
      );

      expect(receipt.acceptedCount, 1);
      expect(receipt.duplicateBatch, isFalse);
    });
  });

  group('startup_telemetry_end_to_end', () {
    test('匿名启动遥测经 production Remote 写入并读回幂等 ACK', () async {
      final suffix = DateTime.now().microsecondsSinceEpoch;
      final attemptId = 'startup_attempt_$suffix';
      final event = StartupTelemetryEvent(
        eventId: '${attemptId}_1',
        attemptId: attemptId,
        sequence: 1,
        phase: StartupTelemetryPhase.terminal,
        phaseDurationMs: 25,
        elapsedMs: 1200,
        outcome: 'success',
        occurredAt: DateTime.now().toUtc(),
        platform: 'android',
        runtimeEnv: _apiContractEnv,
        appVersion: '1.0.0',
        networkClass: 'wifi',
        failureCode: '',
        failureSource: '',
        deadlineOrigin: 'android_process',
      );
      final transport = RemoteStartupTelemetryTransport(
        client: _generatedClient(),
        invocationContext: ({required bool recoveryBatch}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.appShell.id,
              routeId: AppUiSurfaces.appShell.routeId,
              clientPageId: OpsRequestPageIds.reportStartupEventBatch,
              actor: const CloudOperationActorContext(),
            ),
      );
      final proof = 'startup_proof_${suffix}_canonical';

      final first = await transport.report([event], proof: proof);
      expect(first.acknowledges(1), isTrue);
      expect(first.acceptedCount, 1);

      final duplicate = await transport.report([event], proof: proof);
      expect(duplicate.acknowledges(1), isTrue);
      expect(duplicate.duplicateCount, 1);
    });
  });
}

GeneratedCloudOperationClient _generatedClient() {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: _client,
      authTokenProvider: _SessionTokenProvider(_session.accessToken),
    ),
    clientContextProvider: const _ApiContractClientContextProvider(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.values.firstWhere(
        (candidate) => candidate.name == _apiContractEnv,
      ),
      gatewayBaseUri: Uri.parse(_productOpsBase),
    ),
    telemetrySink: const AppCloudOperationTelemetrySink(
      clientContextProvider: _ApiContractClientContextProvider(),
    ),
  );
}

final class _SessionTokenProvider implements CloudAuthTokenProvider {
  const _SessionTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}

final class _ApiContractClientContextProvider
    implements CloudClientContextProvider {
  const _ApiContractClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'ops-api-contract',
      platform: 'api-contract',
      appVersion: 'contract',
      locale: 'zh-CN',
      deviceActorId: 'ops-api-contract-device',
    );
  }
}
