import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

void main() {
  group('RemoteOpsEventRepository', () {
    late Directory tempDir;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('ops_event_repo_test_');
      Hive.init(tempDir.path);
    });

    tearDown(() async {
      await Hive.deleteFromDisk();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('失败后入队，后续上报会先重放 pending batch', () async {
      final client = _QueueingHttpClient();
      final repository = RemoteOpsEventRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://ops.example.com',
        queueBoxName: 'ops_event_queue_test',
      );

      await repository.reportEventBatch(
        events: const <OpsEventRecordInput>[
          OpsEventRecordInput(
            eventId: 'evt-1',
            eventType: 'experience',
            eventName: 'page_open',
            occurredAt: '2026-04-01T00:00:00Z',
          ),
        ],
      );

      expect(client.postCalls, equals(1));
      final queueBox = Hive.box<String>('ops_event_queue_test');
      expect(queueBox.length, equals(1));

      client.failPost = false;
      await repository.reportEventBatch(
        events: const <OpsEventRecordInput>[
          OpsEventRecordInput(
            eventId: 'evt-2',
            eventType: 'analytics',
            eventName: 'tap',
            occurredAt: '2026-04-01T00:00:01Z',
          ),
        ],
      );

      expect(client.postCalls, equals(3));
      expect(queueBox.length, equals(0));
      expect(client.postedEventIds, containsAll(<String>['evt-1', 'evt-2']));
    });
  });
}

class _QueueingHttpClient extends http.BaseClient {
  bool failPost = true;
  int postCalls = 0;
  final List<String> postedEventIds = <String>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request.method == 'POST') {
      postCalls++;
      final body = await request.finalize().bytesToString();
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      final events = (decoded['events'] as List?) ?? const <dynamic>[];
      postedEventIds.addAll(
        events
            .whereType<Map>()
            .map((item) => (item['eventId'] ?? '').toString())
            .where((id) => id.isNotEmpty),
      );
      if (failPost) {
        throw const SocketException('network down');
      }
      return http.StreamedResponse(
        Stream<List<int>>.value(
          utf8.encode('{"acceptedCount":1,"duplicateCount":0}'),
        ),
        200,
        headers: const <String, String>{'content-type': 'application/json'},
      );
    }
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode('{}')),
      200,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}
