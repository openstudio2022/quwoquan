// ignore_for_file: prefer_initializing_formals

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';

const String kAppTelemetryOutboxName = 'app_telemetry_outbox';

enum AppTelemetryFlushResult {
  empty,
  delivered,
  deferred,
  identityBlocked,
  deadLettered,
}

/// 仅在事件已写入加密 outbox 后返回 [persisted]。平台 ANR marker 只能以此
/// 作为确认前提，不能把一次写入尝试误称为可靠入队。
enum AppTelemetryEnqueueResult { persisted, unavailable, evicted }

enum AppTelemetryDeliveryDegradation { dropped, deadLettered, retrying }

typedef AppTelemetryDeliveryObserver = void Function(
  AppTelemetryDeliveryDegradation kind,
  String reason,
);

final class AppTelemetryQueuedRecord {
  const AppTelemetryQueuedRecord({
    required this.wire,
    required this.logType,
    required this.eventType,
    required this.enqueuedAt,
    required this.expiresAt,
    required this.droppable,
    this.critical = false,
  });

  final Map<String, Object?> wire;
  final String logType;
  final String eventType;
  final DateTime enqueuedAt;
  final DateTime expiresAt;
  final bool droppable;
  final bool critical;

  Map<String, Object?> toEnvelope(String actorPartitionKey) =>
      <String, Object?>{
        'actorPartitionKey': actorPartitionKey,
        'logType': logType,
        'eventType': eventType,
        'enqueuedAt': enqueuedAt.toUtc().toIso8601String(),
        'expiresAt': expiresAt.toUtc().toIso8601String(),
        'droppable': droppable,
        'critical': critical,
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

  Future<AppTelemetryEnqueueResult> enqueue(
    AppTelemetryQueuedRecord record,
  ) async {
    try {
      final box = await _storage.open(_partition, _queueName);
      if (box == null) {
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.dropped,
          'encrypted_outbox_unavailable',
        );
        return AppTelemetryEnqueueResult.unavailable;
      }
      final key = _nextEventKey(box, record.enqueuedAt);
      await box.put(
        key,
        canonicalJsonEncode(record.toEnvelope(_partition.key)),
      );
      await _enforceCapacity(box);
      return box.containsKey(key)
          ? AppTelemetryEnqueueResult.persisted
          : AppTelemetryEnqueueResult.evicted;
    } on Object {
      _deliveryObserver(
        AppTelemetryDeliveryDegradation.retrying,
        'encrypted_outbox_write_failed',
      );
      return AppTelemetryEnqueueResult.unavailable;
    }
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
      var sealed = _tryReadSealed(box.get(_sealedKey));
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
          return _isolateRejectedSealedBatch(
            box,
            sealed,
            reason: 'http_$status',
          );
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
      final envelope = _tryReadEnvelope(raw);
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

  /// 事件目录校验属于单条事实的语义错误，不能让一个坏事件拖入同批已封存的
  /// 合法事件。原批次收到 400/422 后按原顺序拆为单事件幂等请求：已确认的记录
  /// 删除，仍被目录拒绝的记录单独进入 DLQ，依赖/鉴权故障则保持未确认记录重试。
  ///
  /// 单事件发送期间原始 queue key 一直保留；进程中断时下一轮会重新密封尚未确认
  /// 的 key，因此不会以“先删除再发送”的方式丢失关键商业事件。
  Future<AppTelemetryFlushResult> _isolateRejectedSealedBatch(
    Box<String> box,
    _SealedTelemetryBatch sealed, {
    required String reason,
  }) async {
    await box.delete(_sealedKey);
    var deadLettered = false;
    for (final key in sealed.eventKeys) {
      final raw = box.get(key);
      final envelope = _tryReadEnvelope(raw);
      if (raw == null || envelope == null) {
        if (raw != null) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: _queueName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'poison_envelope',
          );
          deadLettered = true;
          continue;
        }
        continue;
      }
      final canonicalBody = canonicalJsonEncode(<String, Object?>{
        'events': <Map<String, Object?>>[envelope.wire],
      });
      final digest = sha256.convert(utf8.encode(canonicalBody)).toString();
      try {
        final ack = await _transport.sendSealedBatch(
          canonicalBody: canonicalBody,
          idempotencyKey: digest,
        );
        if (ack.acceptedCount != 1) {
          _deliveryObserver(
            AppTelemetryDeliveryDegradation.retrying,
            'incomplete_ack',
          );
          return AppTelemetryFlushResult.deferred;
        }
        await box.delete(key);
      } on CloudException catch (error) {
        final status = error.statusCode ?? 0;
        if (status == 400 || status == 422) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: _queueName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'isolated_http_$status',
          );
          if (box.containsKey(key)) {
            _deliveryObserver(
              AppTelemetryDeliveryDegradation.retrying,
              'dlq_move_failed',
            );
            return AppTelemetryFlushResult.deferred;
          }
          deadLettered = true;
          continue;
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
    }
    if (deadLettered) {
      _deliveryObserver(AppTelemetryDeliveryDegradation.deadLettered, reason);
      return AppTelemetryFlushResult.deadLettered;
    }
    return AppTelemetryFlushResult.delivered;
  }

  Future<void> _removeExpired(Box<String> box) async {
    final now = _now().toUtc();
    for (final key in _eventKeys(box)) {
      final raw = box.get(key);
      final envelope = _tryReadEnvelope(raw);
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
          _tryReadSealed(box.get(_sealedKey))?.eventKeys.toSet() ??
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
        final envelope = _tryReadEnvelope(box.get(key));
        if (envelope != null &&
            !envelope.critical &&
            envelope.logType == 'event' &&
            envelope.droppable) {
          victim = key;
          break;
        }
      }
      for (final key in removableKeys) {
        final envelope = _tryReadEnvelope(box.get(key));
        if (envelope?.logType == 'event' && !envelope!.critical) {
          victim = key;
          break;
        }
      }
      if (victim != null) {
        final raw = box.get(victim);
        if (raw == null) {
          await box.delete(victim);
          continue;
        }
        await _storage.moveToDlq(
          partition: _partition,
          queueName: _queueName,
          sourceKey: victim,
          rawEnvelope: raw,
          reason: 'outbox_overflow_event',
          kind: ActorQueueSignalKind.overflowMoved,
        );
        if (box.containsKey(victim)) {
          _deliveryObserver(
            AppTelemetryDeliveryDegradation.retrying,
            'overflow_dlq_move_failed',
          );
          return;
        }
        _deliveryObserver(
          AppTelemetryDeliveryDegradation.deadLettered,
          'outbox_overflow_event',
        );
        continue;
      }
      _deliveryObserver(
        AppTelemetryDeliveryDegradation.retrying,
        'outbox_capacity_preserves_critical',
      );
      return;
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

  _QueuedEnvelope? _tryReadEnvelope(String? raw) {
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
        critical: decoded['critical'] == true,
      );
    } catch (_) {
      return null;
    }
  }

  _SealedTelemetryBatch? _tryReadSealed(String? raw) {
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
    required this.critical,
  });

  final Map<String, Object?> wire;
  final String logType;
  final DateTime expiresAt;
  final bool droppable;
  final bool critical;
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
