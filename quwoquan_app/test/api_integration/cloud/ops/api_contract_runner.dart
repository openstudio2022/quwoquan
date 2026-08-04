// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/app/startup/startup_telemetry.dart';
import 'package:quwoquan_app/cloud/remote/ops/startup_telemetry_remote.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/api_contract/local_gamma_anonymous_session.dart';
import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBase = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);
const _authBase = String.fromEnvironment('API_CONTRACT_AUTH_BASE_URL');

late http.Client _client;
late LocalGammaAnonymousSession _session;
bool _clientInitialized = false;

Map<String, String> _headers(String pageId, {String? idempotencyKey}) =>
    <String, String>{
      ...CloudRequestHeaders.forPage(pageId),
      'Content-Type': 'application/json',
      'Authorization': _session.authorizationHeader,
      'Idempotency-Key': ?idempotencyKey,
    };

void main() {
  setUpAll(() async {
    if (_productOpsBase.isEmpty || _authBase.isEmpty) {
      throw StateError(
        'L3: ${_apiContractEnv.toUpperCase()} product-ops or auth base URL not set',
      );
    }
    try {
      final probe = await http
          .get(Uri.parse('$_productOpsBase/healthz'))
          .timeout(const Duration(seconds: 5));
      if (probe.statusCode >= 500) {
        throw StateError(
          'L3: product-ops $_apiContractEnv returned ${probe.statusCode}',
        );
      }
    } catch (error) {
      throw StateError('L3: product-ops $_apiContractEnv unreachable ($error)');
    }
    _client = http.Client();
    _session = await LocalGammaAnonymousSession.login(
      client: _client,
      baseUrl: _authBase,
      subject: 'product-ops-api-contract',
    );
    _clientInitialized = true;
  });

  tearDownAll(() {
    if (_clientInitialized) _client.close();
  });

  group('ops_event_ingestion_end_to_end', () {
    test('POST /ops/events 仅接受已验证主体并返回写入回执', () async {
      final pageName = 'contract_page_${DateTime.now().millisecondsSinceEpoch}';
      final eventId = 'evt_${DateTime.now().microsecondsSinceEpoch}';
      final body = <String, dynamic>{
        'events': <Map<String, dynamic>>[
          <String, dynamic>{
            'eventId': eventId,
            'eventType': 'experience',
            'eventName': 'page_open',
            'priority': 'P0',
            'producer': 'app.contract_test',
            'source': 'page_access',
            'pageName': pageName,
            'surfaceId': pageName,
            'routeId': pageName,
            'targetType': 'page',
            'targetKey': 'page_$pageName',
            'occurredAt': DateTime.now().toUtc().toIso8601String(),
            'clientSentAt': DateTime.now().toUtc().toIso8601String(),
            'payload': <String, dynamic>{'route': '/$pageName'},
          },
        ],
      };
      final encodedBody = jsonEncode(body);
      final batchKey = sha256.convert(utf8.encode(encodedBody)).toString();

      final postResp = await _client
          .post(
            Uri.parse('$_productOpsBase/ops/events'),
            headers: _headers(
              'ops.contract.events.report',
              idempotencyKey: batchKey,
            ),
            body: encodedBody,
          )
          .timeout(const Duration(seconds: 10));
      expect(postResp.statusCode, 200);
      final ack = jsonDecode(postResp.body) as Map<String, dynamic>;
      expect((ack['acceptedCount'] as num?)?.toInt() ?? 0, 1);
    });
  });

  group('ops_visit_record_end_to_end', () {
    test('POST /ops/visits 从已验证主体派生访问 actor', () async {
      final targetKey =
          'page_contract_${DateTime.now().millisecondsSinceEpoch}';
      final payload = <String, dynamic>{
        'targetType': 'page',
        'targetKey': targetKey,
        'sessionId': CloudRequestHeaders.sessionId,
        'source': 'page_access',
      };

      final postResp = await _client
          .post(
            Uri.parse('$_productOpsBase/ops/visits'),
            headers: _headers(
              'ops.contract.visit.record',
              idempotencyKey:
                  'ops-visit-contract-${DateTime.now().microsecondsSinceEpoch}',
            ),
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 10));
      expect(postResp.statusCode, 200);
      final record = jsonDecode(postResp.body) as Map<String, dynamic>;
      expect(record['targetType'], 'page');
      expect(record['targetKey'], targetKey);
      expect(record.containsKey('userId'), isFalse);
    });
  });

  group('startup_recovery_end_to_end', () {
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
        recoverySurface: '',
        failureCode: '',
        failureSource: '',
        deadlineOrigin: 'android_process',
      );
      final transport = RemoteStartupTelemetryTransport(
        client: buildGeneratedCloudOperationClient(
          httpClient: CloudHttpClient(client: _client),
          clientContextProvider: const _ApiContractClientContextProvider(),
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.values.firstWhere(
              (candidate) => candidate.name == _apiContractEnv,
            ),
            gatewayBaseUri: Uri.parse(_productOpsBase),
          ),
          telemetrySink: RecordingCloudOperationTelemetrySink(),
        ),
        invocationContext: () => CloudOperationInvocationContext(
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

    test('公开版本恢复 API 对 Android/iOS 返回严格四字段事实', () async {
      final client = RecoveryVersionClient(client: _client);
      final android = await client.fetch(
        baseUrl: _productOpsBase,
        platform: 'android',
        appVersion: '0.0.0',
        buildNumber: 1,
      );
      final ios = await client.fetch(
        baseUrl: _productOpsBase,
        platform: 'ios',
        appVersion: '0.0.0',
        buildNumber: 1,
      );

      expect(android.latestBuild, greaterThan(0));
      expect(android.latestVersion, isNotEmpty);
      expect(Uri.parse(android.recoveryUrl).scheme, 'https');
      expect(Uri.parse(android.updateUrl).scheme, 'https');
      expect(ios.latestBuild, greaterThan(0));
      expect(ios.latestVersion, isNotEmpty);
      expect(Uri.parse(ios.recoveryUrl).scheme, 'https');
      expect(ios.updateUrl, isEmpty);
    });

    test('恢复异常 API 接收严格十字段并返回无内容回执', () async {
      final response = await _client
          .post(
            Uri.parse(
              '$_productOpsBase${OpsApiMetadata.reportRecoveryFailurePath}',
            ),
            headers: const <String, String>{
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            },
            body: jsonEncode(<String, Object>{
              'occurredAt': DateTime.now().toUtc().toIso8601String(),
              'appVersion': '0.0.0-api-contract',
              'buildNumber': '1',
              'platform': 'android',
              'osVersion': 'api-contract',
              'deviceModel': 'api-contract',
              'errorSource': 'runtime',
              'errorType': 'ApiIntegrationRecoveryProbe',
              'errorMessage': 'Synthetic recovery API integration probe',
              'stackTrace': 'Synthetic stack unavailable',
            }),
          )
          .timeout(const Duration(seconds: 10));

      expect(response.statusCode, 204);
      expect(response.body, isEmpty);
    });
  });
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
    );
  }
}
