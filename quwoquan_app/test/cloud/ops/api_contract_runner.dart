library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _productOpsBase = String.fromEnvironment(
  'API_CONTRACT_PRODUCT_OPS_BASE_URL',
);

late http.Client _client;

Map<String, String> _headers(String pageId) => <String, String>{
  ...CloudRequestHeaders.forPage(pageId),
  'Content-Type': 'application/json',
};

void main() {
  setUpAll(() async {
    if (_productOpsBase.isEmpty) {
      throw StateError(
        'L3: ${_apiContractEnv.toUpperCase()}_PRODUCT_OPS_BASE_URL not set',
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
  });

  tearDownAll(() {
    _client.close();
  });

  group('ops_event_ingestion_end_to_end', () {
    test('POST /v1/ops/events 后 summary / drilldown 可读', () async {
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

      final summaryResp = await _client
          .get(
            Uri.parse(
              '$_productOpsBase/v1/ops/events/summary?source=page_access&pageName=$pageName',
            ),
            headers: _headers('ops.contract.events.summary'),
          )
          .timeout(const Duration(seconds: 10));
      expect(summaryResp.statusCode, 200);
      final summaryBody = jsonDecode(summaryResp.body) as Map<String, dynamic>;
      expect((summaryBody['totalCount'] as num?)?.toInt() ?? 0, greaterThan(0));
      final dimensions =
          (summaryBody['dimensions'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final pageCounts =
          (dimensions['pageName'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect((pageCounts[pageName] as num?)?.toInt() ?? 0, greaterThan(0));

      final drilldownResp = await _client
          .get(
            Uri.parse(
              '$_productOpsBase/v1/ops/events/drilldown?pageName=$pageName&eventName=page_open&limit=5',
            ),
            headers: _headers('ops.contract.events.drilldown'),
          )
          .timeout(const Duration(seconds: 10));
      expect(drilldownResp.statusCode, 200);
      final drilldownBody =
          jsonDecode(drilldownResp.body) as Map<String, dynamic>;
      final items = (drilldownBody['items'] as List?) ?? const <dynamic>[];
      expect(
        items.any(
          (item) => (item as Map<String, dynamic>)['eventId'] == eventId,
        ),
        isTrue,
      );
    });
  });

  group('ops_visit_record_end_to_end', () {
    test('POST /v1/ops/visits 后 stats 可读', () async {
      final targetKey =
          'page_contract_${DateTime.now().millisecondsSinceEpoch}';
      final payload = <String, dynamic>{
        'targetType': 'page',
        'targetKey': targetKey,
        'userId': 'contract_user',
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

      final statsResp = await _client
          .get(
            Uri.parse(
              '$_productOpsBase/v1/ops/visits/stats?targetType=page&targetKey=$targetKey',
            ),
            headers: _headers('ops.contract.visit.stats'),
          )
          .timeout(const Duration(seconds: 10));
      expect(statsResp.statusCode, 200);
      final statsBody = jsonDecode(statsResp.body) as Map<String, dynamic>;
      expect((statsBody['totalVisits'] as num?)?.toInt() ?? 0, greaterThan(0));
    });
  });
}
