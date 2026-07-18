// ignore_for_file: prefer_initializing_formals

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

const String kAppTelemetryOutboxName = 'app_telemetry_outbox';

enum AppTelemetryFlushResult {
  empty,
  delivered,
  deferred,
  identityBlocked,
  deadLettered,
}

enum AppTelemetryDeliveryDegradation { dropped, deadLettered, retrying }

typedef AppTelemetryDeliveryObserver =
    void Function(AppTelemetryDeliveryDegradation kind, String reason);

final class AppTelemetryQueuedRecord {
  const AppTelemetryQueuedRecord({
    required this.wire,
    required this.logType,
    required this.eventType,
    required this.enqueuedAt,
    required this.expiresAt,
    required this.droppable,
  });

  final Map<String, Object?> wire;
  final String logType;
  final String eventType;
  final DateTime enqueuedAt;
  final DateTime expiresAt;
  final bool droppable;

  Map<String, Object?> toEnvelope(String actorPartitionKey) =>
      <String, Object?>{
        'actorPartitionKey': actorPartitionKey,
        'logType': logType,
        'eventType': eventType,
        'enqueuedAt': enqueuedAt.toUtc().toIso8601String(),
        'expiresAt': expiresAt.toUtc().toIso8601String(),
        'droppable': droppable,
        'wire': wire,
      };
}

/// actor-scoped 加密事件队列。只允许一个密封批次 in-flight；密封后 body/digest
/// 持久化，直至完整 ACK、dead-letter 或 actor boundary 清理。
final class AppTelemetryOutbox {
  AppTelemetryOutbox({
    required ActorQueuePartition partition,
    required ActorQueueStorage storage,
    required AppTelemetryTransport transport,
    AppTelemetryDeliveryObserver? deliveryObserver,
    DateTime Function()? now,
    this.maxRecords = 1000,
    this.maxBytes = 2 * 1024 * 1024,
    this.maxBatchRecords = 50,
    this.maxBatchBytes = 128 * 1024,
    String queueName = kAppTelemetryOutboxName,
  }) : _partition = partition,
       _storage = storage,
       _transport = transport,
       _deliveryObserver = deliveryObserver ?? _ignoreDeliverySignal,
       _now = now ?? DateTime.now,
       _queueName = queueName;

  static const _sealedKey = '_sealed_batch';
  final ActorQueuePartition _partition;
  final ActorQueueStorage _storage;
  final AppTelemetryTransport _transport;
  final AppTelemetryDeliveryObserver _deliveryObserver;
  final DateTime Function() _now;
  final String _queueName;
  final int maxRecords;
  final int maxBytes;
  final int maxBatchRecords;
  final int maxBatchBytes;
  bool _flushing = false;

  Future<void> enqueue(AppTelemetryQueuedRecord record) async {
    final box = await _storage.open(_partition, _queueName);
    if (box == null) {
      _deliveryObserver(
        AppTelemetryDeliveryDegradation.dropped,
        'encrypted_outbox_unavailable',
      );
      return;
    }
    final key = _nextEventKey(box, record.enqueuedAt);
    await box.put(key, canonicalJsonEncode(record.toEnvelope(_partition.key)));
    await _enforceCapacity(box);
  }

  Future<void> deadLetter(
    AppTelemetryQueuedRecord record, {
    required String reason,
  }) async {
    final box = await _storage.open(_partition, _queueName);
    if (box == null) {
      _deliveryObserver(
        AppTelemetryDeliveryDegradation.dropped,
        'encrypted_dlq_unavailable:$reason',
      );
      return;
    }
    final key = _nextEventKey(box, record.enqueuedAt);
    final raw = canonicalJsonEncode(record.toEnvelope(_partition.key));
    await box.put(key, raw);
    await _storage.moveToDlq(
      partition: _partition,
      queueName: _queueName,
      sourceKey: key,
      rawEnvelope: raw,
      reason: reason,
    );
    _deliveryObserver(AppTelemetryDeliveryDegradation.deadLettered, reason);
  }

  Future<int> pendingCount() async {
    final box = await _storage.open(_partition, _queueName);
    if (box == null) return 0;
    return _eventKeys(box).length;
  }

  Future<void> purge() => _storage.purge(_partition, _queueName);

  Future<AppTelemetryFlushResult> flush() async {
    if (_flushing) return AppTelemetryFlushResult.deferred;
    _flushing = true;
    try {
      final box = await _storage.open(_partition, _queueName);
      if (box == null) return AppTelemetryFlushResult.deferred;
      await _removeExpired(box);
      var sealed = _readSealed(box.get(_sealedKey));
      sealed ??= await _sealNextBatch(box);
      if (sealed == null) return AppTelemetryFlushResult.empty;
      try {
        final ack = await _transport.sendSealedBatch(
          canonicalBody: sealed.canonicalBody,
          idempotencyKey: sealed.digest,
        );
        if (ack.acceptedCount != sealed.eventKeys.length) {
          _deliveryObserver(
            AppTelemetryDeliveryDegradation.retrying,
            'incomplete_ack',
          );
          return AppTelemetryFlushResult.deferred;
        }
        await box.deleteAll(<dynamic>[...sealed.eventKeys, _sealedKey]);
        return AppTelemetryFlushResult.delivered;
      } on CloudException catch (error) {
        final status = error.statusCode ?? 0;
        if (status == 400 || status == 422) {
          await _deadLetterSealed(box, sealed, 'http_$status');
          return AppTelemetryFlushResult.deadLettered;
        }
        if (status == 401 || status == 403) {
          return AppTelemetryFlushResult.identityBlocked;
        }
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.retrying,
          status == 0 ? 'network' : 'http_$status',
        );
        return AppTelemetryFlushResult.deferred;
      } catch (_) {
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.retrying,
          'transport_exception',
        );
        return AppTelemetryFlushResult.deferred;
      }
    } finally {
      _flushing = false;
    }
  }

  Future<_SealedTelemetryBatch?> _sealNextBatch(Box<String> box) async {
    final keys = _eventKeys(box);
    if (keys.isEmpty) return null;
    final selectedKeys = <String>[];
    final events = <Map<String, Object?>>[];
    for (final key in keys) {
      final raw = box.get(key);
      final envelope = _readEnvelope(raw);
      if (envelope == null) {
        if (raw != null) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: _queueName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'poison_envelope',
          );
        } else {
          await box.delete(key);
        }
        continue;
      }
      final nextEvents = <Map<String, Object?>>[...events, envelope.wire];
      final nextBody = canonicalJsonEncode(<String, Object?>{
        'events': nextEvents,
      });
      if (utf8.encode(nextBody).length > maxBatchBytes) {
        if (events.isEmpty) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: _queueName,
            sourceKey: key,
            rawEnvelope: raw!,
            reason: 'event_exceeds_batch_bytes',
          );
          continue;
        }
        break;
      }
      selectedKeys.add(key);
      events.add(envelope.wire);
      if (selectedKeys.length == maxBatchRecords) break;
    }
    if (selectedKeys.isEmpty) return null;
    final canonicalBody = canonicalJsonEncode(<String, Object?>{
      'events': events,
    });
    final digest = sha256.convert(utf8.encode(canonicalBody)).toString();
    final sealed = _SealedTelemetryBatch(
      eventKeys: selectedKeys,
      canonicalBody: canonicalBody,
      digest: digest,
      sealedAt: _now().toUtc(),
    );
    await box.put(
      _sealedKey,
      canonicalJsonEncode(sealed.toJson(_partition.key)),
    );
    return sealed;
  }

  Future<void> _deadLetterSealed(
    Box<String> box,
    _SealedTelemetryBatch sealed,
    String reason,
  ) async {
    for (final key in sealed.eventKeys) {
      final raw = box.get(key);
      if (raw == null) continue;
      await _storage.moveToDlq(
        partition: _partition,
        queueName: _queueName,
        sourceKey: key,
        rawEnvelope: raw,
        reason: reason,
      );
    }
    await box.delete(_sealedKey);
    _deliveryObserver(AppTelemetryDeliveryDegradation.deadLettered, reason);
  }

  Future<void> _removeExpired(Box<String> box) async {
    final now = _now().toUtc();
    for (final key in _eventKeys(box)) {
      final raw = box.get(key);
      final envelope = _readEnvelope(raw);
      if (envelope == null || !envelope.expiresAt.isAfter(now)) {
        await box.delete(key);
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.dropped,
          envelope == null ? 'invalid_envelope' : 'ttl_expired',
        );
      }
    }
  }

  Future<void> _enforceCapacity(Box<String> box) async {
    while (true) {
      final sealedKeys =
          _readSealed(box.get(_sealedKey))?.eventKeys.toSet() ??
          const <String>{};
      final keys = _eventKeys(box);
      final bytes = keys.fold<int>(
        0,
        (sum, key) => sum + utf8.encode(box.get(key) ?? '').length,
      );
      if (keys.length <= maxRecords && bytes <= maxBytes) return;
      final removableKeys = keys
          .where((key) => !sealedKeys.contains(key))
          .toList(growable: false);
      if (removableKeys.isEmpty) {
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.retrying,
          'sealed_batch_holds_capacity',
        );
        return;
      }
      String? victim;
      for (final key in removableKeys) {
        final envelope = _readEnvelope(box.get(key));
        if (envelope != null &&
            envelope.logType == 'event' &&
            envelope.droppable) {
          victim = key;
          break;
        }
      }
      for (final key in removableKeys) {
        if (_readEnvelope(box.get(key))?.logType == 'event') {
          victim = key;
          break;
        }
      }
      if (victim != null) {
        await box.delete(victim);
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.dropped,
          'outbox_overflow_event',
        );
        continue;
      }
      final errorKey = removableKeys.first;
      final raw = box.get(errorKey);
      if (raw == null) {
        await box.delete(errorKey);
        continue;
      }
      await _storage.moveToDlq(
        partition: _partition,
        queueName: _queueName,
        sourceKey: errorKey,
        rawEnvelope: raw,
        reason: 'outbox_overflow_error',
        kind: ActorQueueSignalKind.overflowMoved,
      );
      _deliveryObserver(
        AppTelemetryDeliveryDegradation.deadLettered,
        'outbox_overflow_error',
      );
    }
  }

  List<String> _eventKeys(Box<String> box) =>
      box.keys
          .map((key) => key.toString())
          .where((key) => key.startsWith('e.'))
          .toList(growable: false)
        ..sort();

  String _nextEventKey(Box<String> box, DateTime enqueuedAt) {
    final prefix = 'e.${enqueuedAt.toUtc().microsecondsSinceEpoch}';
    var suffix = 0;
    var key = '$prefix.${suffix.toString().padLeft(3, '0')}';
    while (box.containsKey(key)) {
      suffix++;
      key = '$prefix.${suffix.toString().padLeft(3, '0')}';
    }
    return key;
  }

  _QueuedEnvelope? _readEnvelope(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map ||
          !_partition.acceptsEnvelope(decoded['actorPartitionKey'])) {
        return null;
      }
      final wireValue = decoded['wire'];
      if (wireValue is! Map) return null;
      final expiresAt = DateTime.tryParse(
        (decoded['expiresAt'] ?? '').toString(),
      );
      if (expiresAt == null) return null;
      return _QueuedEnvelope(
        wire: wireValue.cast<String, Object?>(),
        logType: (decoded['logType'] ?? '').toString(),
        expiresAt: expiresAt.toUtc(),
        droppable: decoded['droppable'] == true,
      );
    } catch (_) {
      return null;
    }
  }

  _SealedTelemetryBatch? _readSealed(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map ||
          !_partition.acceptsEnvelope(decoded['actorPartitionKey'])) {
        return null;
      }
      final keys = (decoded['eventKeys'] as List?)
          ?.map((value) => value.toString())
          .toList(growable: false);
      final sealedAt = DateTime.tryParse(
        (decoded['sealedAt'] ?? '').toString(),
      );
      final body = (decoded['canonicalBody'] ?? '').toString();
      final digest = (decoded['digest'] ?? '').toString();
      if (keys == null ||
          keys.isEmpty ||
          sealedAt == null ||
          body.isEmpty ||
          digest.length != 64) {
        return null;
      }
      return _SealedTelemetryBatch(
        eventKeys: keys,
        canonicalBody: body,
        digest: digest,
        sealedAt: sealedAt.toUtc(),
      );
    } catch (_) {
      return null;
    }
  }
}

final class _QueuedEnvelope {
  const _QueuedEnvelope({
    required this.wire,
    required this.logType,
    required this.expiresAt,
    required this.droppable,
  });

  final Map<String, Object?> wire;
  final String logType;
  final DateTime expiresAt;
  final bool droppable;
}

final class _SealedTelemetryBatch {
  const _SealedTelemetryBatch({
    required this.eventKeys,
    required this.canonicalBody,
    required this.digest,
    required this.sealedAt,
  });

  final List<String> eventKeys;
  final String canonicalBody;
  final String digest;
  final DateTime sealedAt;

  Map<String, Object?> toJson(String actorPartitionKey) => <String, Object?>{
    'actorPartitionKey': actorPartitionKey,
    'eventKeys': eventKeys,
    'canonicalBody': canonicalBody,
    'digest': digest,
    'sealedAt': sealedAt.toIso8601String(),
  };
}

void _ignoreDeliverySignal(
  AppTelemetryDeliveryDegradation kind,
  String reason,
) {}
