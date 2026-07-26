import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

void main() {
  late Directory tempDirectory;
  late _MemoryActorQueueKeyStore keyStore;
  late ActorQueueStorage storage;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'actor_queue_storage_test_',
    );
    Hive.init(tempDirectory.path);
    HiveRuntime.debugEnsureInitializedHook = () async => true;
    keyStore = _MemoryActorQueueKeyStore();
    storage = ActorQueueStorage(keyStore: keyStore);
  });

  tearDown(() async {
    HiveRuntime.resetForTest();
    await Hive.deleteFromDisk();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test(
    'same actor rebuild preserves queue; account/persona transition purges queue and DLQ keys',
    () async {
      final previous = ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account-a',
        personaId: 'persona-a',
        deviceId: 'device-a',
      );
      final current = ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account-b',
        personaId: 'persona-b',
        deviceId: 'device-a',
      );
      final queue = await storage.open(previous, 'events');
      final dlq = await storage.open(previous, 'events_dlq');
      await queue!.put('event-1', 'sensitive-event');
      await dlq!.put('event-0', 'poison-event');
      final boundary = ActorQueueSessionBoundary(
        storage: storage,
        queueNames: const <String>['events'],
      );

      await boundary.transition(previous: previous, current: previous);
      expect(queue.length, 1);
      expect(dlq.length, 1);

      await boundary.transition(previous: previous, current: current);

      expect(await Hive.boxExists(previous.boxName('events')), isFalse);
      expect(await Hive.boxExists(previous.boxName('events_dlq')), isFalse);
      expect(keyStore.values, isEmpty);
    },
  );

  test('invalid secure-store key fails closed and emits drop signal', () async {
    final signals = <ActorQueueSignal>[];
    final partition = ActorQueuePartition(
      environment: 'prod',
      personaId: 'persona-a',
    );
    final observingStorage = ActorQueueStorage(
      keyStore: keyStore,
      signalObserver: signals.add,
    );
    await observingStorage.open(partition, 'events');
    await Hive.box<String>(partition.boxName('events')).close();
    keyStore.values.updateAll((_, _) => 'invalid-key');

    final reopened = await observingStorage.open(partition, 'events');

    expect(reopened, isNull);
    expect(signals.single.kind, ActorQueueSignalKind.dropped);
    expect(signals.single.reason, 'invalid_encryption_key');
  });

  test(
    'concurrent opens for one actor queue share one encrypted box',
    () async {
      final partition = ActorQueuePartition(
        environment: 'alpha',
        accountId: 'account-a',
        personaId: 'persona-a',
      );

      final opened = await Future.wait(
        List<Future<Box<String>?>>.generate(
          3,
          (_) => storage.open(partition, 'events'),
        ),
      );

      expect(opened, everyElement(isNotNull));
      expect(identical(opened[0], opened[1]), isTrue);
      expect(identical(opened[1], opened[2]), isTrue);
      await opened.first!.put('event-1', 'encrypted-event');
      expect(opened.last!.get('event-1'), 'encrypted-event');
    },
  );

  testWidgets('widget binding can open an encrypted actor queue', (
    tester,
  ) async {
    final partition = ActorQueuePartition(
      environment: 'alpha',
      accountId: 'account-widget',
      personaId: 'persona-widget',
    );

    await tester.runAsync(() async {
      final queue = await storage.open(partition, 'widget-events');

      expect(queue, isNotNull);
      await queue!.put('event-1', 'encrypted-event');
      expect(queue.get('event-1'), 'encrypted-event');
    });
  });
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
