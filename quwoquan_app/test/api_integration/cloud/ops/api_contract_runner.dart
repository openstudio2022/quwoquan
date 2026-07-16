library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';

import '../../../support/api_contract/local_bad_certificate_overrides.dart';
import '../../../support/api_contract/local_gamma_anonymous_session.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBase = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);
const _authBase = String.fromEnvironment('API_CONTRACT_AUTH_BASE_URL');
const _allowBadCertificateForLocalApiContract = bool.fromEnvironment(
  'API_CONTRACT_ALLOW_BAD_CERT',
);

late http.Client _client;
late LocalGammaAnonymousSession _session;
bool _clientInitialized = false;

Map<String, String> _headers(String pageId) => <String, String>{
  ...CloudRequestHeaders.forPage(pageId),
  'Content-Type': 'application/json',
  'Authorization': _session.authorizationHeader,
};

void main() {
  setUpAll(() async {
    installLocalApiContractBadCertificateOverride(
      enabled: _allowBadCertificateForLocalApiContract,
    );
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
      subject: 'product-ops-api-contract-v1',
    );
    _clientInitialized = true;
  });

  tearDownAll(() {
    if (_clientInitialized) _client.close();
    restoreLocalApiContractBadCertificateOverride();
  });

  group('ops_event_ingestion_end_to_end', () {
    test('POST /v1/ops/events 仅接受已验证主体并返回写入回执', () async {
      final pageName = 'contract_page_${DateTime.now().millisecondsSinceEpoch}';
      final eventId = 'evt_${DateTime.now().microsecondsSinceEpoch}';
      final body = <String, dynamic>{
        'events': <Map<String, dynamic>>[
          <String, dynamic>{
            'eventId': eventId,
            'eventType': 'experience',
            'eventName': 'page_open',
            'eventVersion': 'v1',
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

      final postResp = await _client
          .post(
            Uri.parse('$_productOpsBase/v1/ops/events'),
            headers: _headers('ops.contract.events.report'),
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));
      expect(postResp.statusCode, 200);
      final ack = jsonDecode(postResp.body) as Map<String, dynamic>;
      expect((ack['acceptedCount'] as num?)?.toInt() ?? 0, 1);
    });
  });

  group('ops_visit_record_end_to_end', () {
    test('POST /v1/ops/visits 从已验证主体派生访问 actor', () async {
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
            Uri.parse('$_productOpsBase/v1/ops/visits'),
            headers: _headers('ops.contract.visit.record'),
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
}
