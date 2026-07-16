import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

abstract interface class ActorQueueEncryptionKeyStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

final class SecureActorQueueEncryptionKeyStore
    implements ActorQueueEncryptionKeyStore {
  const SecureActorQueueEncryptionKeyStore()
    : _storage = const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

enum ActorQueueSignalKind { poisonMoved, overflowMoved, dropped }

final class ActorQueueSignal {
  const ActorQueueSignal({
    required this.kind,
    required this.queueName,
    required this.partitionKey,
    required this.reason,
  });

  final ActorQueueSignalKind kind;
  final String queueName;
  final String partitionKey;
  final String reason;
}

typedef ActorQueueSignalObserver = void Function(ActorQueueSignal signal);

/// Actor-scoped encrypted local queue and DLQ storage.
///
/// Queue contents never share an encryption key across environment/account/
/// persona/device partitions. The encryption key is random and stored only in
/// the platform secure store; neither raw actor identifiers nor the key are
/// written into the Hive directory.
final class ActorQueueStorage {
  ActorQueueStorage({
    ActorQueueEncryptionKeyStore? keyStore,
    Random? random,
    this.signalObserver = _recordActorQueueSignal,
  }) : _keyStore = keyStore ?? const SecureActorQueueEncryptionKeyStore(),
       _random = random ?? Random.secure();

  final ActorQueueEncryptionKeyStore _keyStore;
  final Random _random;
  final ActorQueueSignalObserver signalObserver;

  Future<Box<String>?> open(
    ActorQueuePartition partition,
    String queueName,
  ) async {
    if (!partition.canPersist) return null;
    final key = await _loadOrCreateKey(partition, queueName);
    if (key == null) return null;
    final box = await HiveRuntime.openEncryptedStringBoxOrNull(
      partition.boxName(queueName),
      encryptionKey: key,
    );
    if (box == null) {
      _emit(
        kind: ActorQueueSignalKind.dropped,
        partition: partition,
        queueName: queueName,
        reason: 'encrypted_queue_open_failed',
      );
    }
    return box;
  }

  Future<void> moveToDlq({
    required ActorQueuePartition partition,
    required String queueName,
    required String sourceKey,
    required String rawEnvelope,
    required String reason,
    ActorQueueSignalKind kind = ActorQueueSignalKind.poisonMoved,
  }) async {
    final source = await open(partition, queueName);
    if (source == null) {
      _emit(
        kind: ActorQueueSignalKind.dropped,
        partition: partition,
        queueName: queueName,
        reason: 'secure_queue_unavailable:$reason',
      );
      return;
    }
    final dlq = await open(partition, '${queueName}_dlq');
    if (dlq == null) {
      _emit(
        kind: ActorQueueSignalKind.dropped,
        partition: partition,
        queueName: queueName,
        reason: 'secure_dlq_unavailable:$reason',
      );
      return;
    }
    final dlqKey = '${DateTime.now().microsecondsSinceEpoch}:$sourceKey';
    await dlq.put(
      dlqKey,
      jsonEncode(<String, Object?>{
        'actorPartitionKey': partition.key,
        'sourceKey': sourceKey,
        'reason': reason,
        'failedAt': DateTime.now().toUtc().toIso8601String(),
        'envelope': rawEnvelope,
      }),
    );
    await source.delete(sourceKey);
    _emit(
      kind: kind,
      partition: partition,
      queueName: queueName,
      reason: reason,
    );
  }

  Future<void> purge(ActorQueuePartition partition, String queueName) async {
    if (!partition.canPersist) return;
    await _purgeBox(partition, queueName);
    await _purgeBox(partition, '${queueName}_dlq');
  }

  Future<void> _purgeBox(
    ActorQueuePartition partition,
    String queueName,
  ) async {
    final boxName = partition.boxName(queueName);
    if (Hive.isBoxOpen(boxName)) {
      await Hive.box<String>(boxName).close();
    }
    if (await Hive.boxExists(boxName)) {
      await Hive.deleteBoxFromDisk(boxName);
    }
    await _keyStore.delete(_keyName(partition, queueName));
  }

  Future<List<int>?> _loadOrCreateKey(
    ActorQueuePartition partition,
    String queueName,
  ) async {
    final keyName = _keyName(partition, queueName);
    final stored = await _keyStore.read(keyName);
    if (stored != null && stored.isNotEmpty) {
      try {
        final decoded = base64Url.decode(stored);
        if (decoded.length == 32) return decoded;
      } catch (_) {
        // Invalid secure-store material fails closed below.
      }
      _emit(
        kind: ActorQueueSignalKind.dropped,
        partition: partition,
        queueName: queueName,
        reason: 'invalid_encryption_key',
      );
      return null;
    }
    final generated = List<int>.generate(32, (_) => _random.nextInt(256));
    await _keyStore.write(keyName, base64Url.encode(generated));
    return generated;
  }

  String _keyName(ActorQueuePartition partition, String queueName) =>
      'qwq.actor_queue.v1.${partition.key}.'
      '${base64Url.encode(utf8.encode(queueName)).replaceAll('=', '')}';

  void _emit({
    required ActorQueueSignalKind kind,
    required ActorQueuePartition partition,
    required String queueName,
    required String reason,
  }) {
    signalObserver(
      ActorQueueSignal(
        kind: kind,
        queueName: queueName,
        partitionKey: partition.key,
        reason: reason,
      ),
    );
  }
}

void _recordActorQueueSignal(ActorQueueSignal signal) {
  developer.log(
    jsonEncode(<String, String>{
      'metric': 'app_actor_queue_transition_total',
      'kind': signal.kind.name,
      'queue': signal.queueName,
      'actorPartition': signal.partitionKey,
      'reason': signal.reason,
    }),
    name: 'ActorQueueStorage.metric',
    level: signal.kind == ActorQueueSignalKind.dropped ? 1000 : 900,
  );
}

/// Purges every queue owned by an actor when the authenticated boundary
/// changes. A same-actor rebuild does not discard pending work.
final class ActorQueueSessionBoundary {
  ActorQueueSessionBoundary({
    required this.storage,
    required Iterable<String> queueNames,
  }) : queueNames = List<String>.unmodifiable(queueNames);

  final ActorQueueStorage storage;
  final List<String> queueNames;

  Future<void> transition({
    ActorQueuePartition? previous,
    required ActorQueuePartition current,
  }) async {
    if (previous == null ||
        !previous.canPersist ||
        previous.key == current.key) {
      return;
    }
    await Future.wait<void>(
      queueNames.map((queueName) => storage.purge(previous, queueName)),
    );
  }
}
