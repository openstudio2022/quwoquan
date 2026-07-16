import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';
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

    test('失败后入队，后续上报不阻塞当前 batch，flushPending 再后台重放', () async {
      final client = _QueueingHttpClient();
      final keyStore = _MemoryActorQueueKeyStore();
      final signals = <ActorQueueSignal>[];
      final queueStorage = ActorQueueStorage(
        keyStore: keyStore,
        signalObserver: signals.add,
      );
      final partition = ActorQueuePartition(
        environment: 'alpha',
        personaId: 'persona-a',
        deviceId: 'device-a',
      );
      final repository = RemoteOpsEventRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://ops.example.com',
        queueBoxName: 'ops_event_queue_test',
        queuePartition: partition,
        queueStorage: queueStorage,
      );
      addTearDown(repository.dispose);

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
      final queueBox = Hive.box<String>(
        partition.boxName('ops_event_queue_test'),
      );
      expect(queueBox.length, equals(1));
      final persistedBytes = await _readPersistedBytes(tempDir);
      expect(
        utf8.decode(persistedBytes, allowMalformed: true),
        isNot(contains('evt-1')),
      );

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

      expect(client.postCalls, equals(2));
      expect(queueBox.length, equals(1));
      expect(client.postedEventIds, containsAll(<String>['evt-1', 'evt-2']));

      await repository.flushPending();

      expect(client.postCalls, equals(3));
      expect(queueBox.length, equals(0));

      await queueBox.put('poison', '{not-json');
      await repository.flushPending();

      expect(queueBox.length, equals(0));
      final dlq = Hive.box<String>(
        partition.boxName('ops_event_queue_test_dlq'),
      );
      expect(dlq.length, equals(1));
      expect(signals.single.kind, ActorQueueSignalKind.poisonMoved);

      await repository.clearPendingForLogout();

      expect(
        await Hive.boxExists(partition.boxName('ops_event_queue_test')),
        isFalse,
      );
      expect(
        await Hive.boxExists(partition.boxName('ops_event_queue_test_dlq')),
        isFalse,
      );
      expect(keyStore.values, isEmpty);
    });
  });
}

Future<List<int>> _readPersistedBytes(Directory directory) async {
  final bytes = <int>[];
  await for (final entity in directory.list(recursive: true)) {
    if (entity is File) {
      bytes.addAll(await entity.readAsBytes());
    }
  }
  return bytes;
}

final class _MemoryActorQueueKeyStore implements ActorQueueEncryptionKeyStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }
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
