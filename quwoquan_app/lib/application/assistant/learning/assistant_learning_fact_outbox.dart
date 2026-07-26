import 'dart:convert';
import 'dart:developer' as developer;

import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

/// Actor-scoped encrypted pending-confirmation queue for assistant learning
/// facts. A record is removed only after the server receipt confirms the exact
/// event identity and version.
final class AssistantLearningFactOutbox {
  AssistantLearningFactOutbox(
    this._partition,
    this._storage,
    this._remote, {
    this.maxRecords = 256,
  }) : assert(maxRecords > 0);

  final ActorQueuePartition _partition;
  final ActorQueueStorage _storage;
  final AssistantLearningFactAppendFacet _remote;
  final int maxRecords;
  Future<void>? _flushInFlight;
  bool _disposed = false;
  int _nextEnqueueSequence = 0;

  Future<bool> enqueue(AppendAssistantLearningFactRequest fact) async {
    if (_disposed) return false;
    final enqueueSequence = ++_nextEnqueueSequence;
    final box = await _storage.open(
      _partition,
      kAssistantLearningFactOutboxName,
    );
    if (_disposed || box == null) return false;
    final key = _keyFor(fact);
    final existingRaw = box.get(key);
    if (existingRaw != null) {
      final existing = _decodeFact(existingRaw);
      if (existing == null ||
          jsonEncode(existing.toJson()) != jsonEncode(fact.toJson())) {
        developer.log(
          'learning fact local identity conflict',
          name: 'AssistantLearningFactOutbox',
          error: 'local_identity_conflict',
        );
        return false;
      }
      return true;
    }
    if (_eventKeys(box).length >= maxRecords) {
      return false;
    }
    await box.put(
      key,
      jsonEncode(<String, Object?>{
        'actorPartitionKey': _partition.key,
        'enqueuedAt': DateTime.now().toUtc().toIso8601String(),
        'enqueueSequence': enqueueSequence,
        'fact': fact.toJson(),
      }),
    );
    return box.containsKey(key);
  }

  Future<int> pendingCount() async {
    if (_disposed) return 0;
    final box = await _storage.open(
      _partition,
      kAssistantLearningFactOutboxName,
    );
    return _disposed || box == null ? 0 : _eventKeys(box).length;
  }

  Future<void> flush() {
    if (_disposed) return Future<void>.value();
    final inFlight = _flushInFlight;
    if (inFlight != null) {
      return inFlight;
    }
    final pending = _flushPending();
    _flushInFlight = pending;
    return pending.whenComplete(() {
      _flushInFlight = null;
    });
  }

  /// Stops background work when the owning provider is disposed.
  ///
  /// Hive is process-global; application shutdown can close a box while a
  /// remote append is in flight. Async continuations must not touch that box
  /// after their Riverpod owner has gone away.
  void dispose() {
    _disposed = true;
  }

  Future<void> _flushPending() async {
    final box = await _storage.open(
      _partition,
      kAssistantLearningFactOutboxName,
    );
    if (_disposed || box == null) return;
    for (final key in _eventKeys(box)) {
      if (_disposed) return;
      final raw = box.get(key);
      final fact = _decodeFact(raw);
      if (raw == null || fact == null) {
        if (raw != null) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: kAssistantLearningFactOutboxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'poison_learning_fact',
          );
        } else {
          await box.delete(key);
        }
        continue;
      }
      try {
        final receipt = await _remote.appendUserFact(request: fact);
        if (_disposed) return;
        if (!receipt.accepted ||
            receipt.eventId != fact.eventId ||
            receipt.eventVersion != fact.eventVersion) {
          developer.log(
            'learning fact receipt mismatch',
            name: 'AssistantLearningFactOutbox',
            error: 'receipt_identity_mismatch',
          );
          await _storage.moveToDlq(
            partition: _partition,
            queueName: kAssistantLearningFactOutboxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'receipt_identity_mismatch',
          );
          continue;
        }
        await box.delete(key);
      } on CloudException catch (error) {
        final status = error.statusCode ?? 0;
        if (status == 400 ||
            status == 403 ||
            status == 404 ||
            status == 409 ||
            status == 422) {
          await _storage.moveToDlq(
            partition: _partition,
            queueName: kAssistantLearningFactOutboxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'terminal_http_$status',
          );
          continue;
        }
        return;
      } catch (_) {
        return;
      }
    }
  }

  AppendAssistantLearningFactRequest? _decodeFact(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map ||
          !_partition.acceptsEnvelope(decoded['actorPartitionKey'])) {
        return null;
      }
      final value = decoded['fact'];
      if (value is! Map) return null;
      return AppendAssistantLearningFactRequest.fromJson(
        value.cast<String, dynamic>(),
      );
    } catch (_) {
      return null;
    }
  }

  List<String> _eventKeys(Box<String> box) {
    final keys =
        box.keys
            .map((key) => key.toString())
            .where((key) => key.startsWith('fact.'))
            .toList(growable: false)
          ..sort((left, right) {
            final leftOrder = _enqueueOrder(box.get(left));
            final rightOrder = _enqueueOrder(box.get(right));
            final byTime = leftOrder.enqueuedAt.compareTo(
              rightOrder.enqueuedAt,
            );
            if (byTime != 0) return byTime;
            final bySequence = leftOrder.sequence.compareTo(
              rightOrder.sequence,
            );
            if (bySequence != 0) return bySequence;
            return left.compareTo(right);
          });
    return keys;
  }

  _EnqueueOrder _enqueueOrder(String? raw) {
    if (raw == null || raw.isEmpty) return const _EnqueueOrder();
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return const _EnqueueOrder();
      final enqueuedAt = decoded['enqueuedAt'];
      final enqueueSequence = decoded['enqueueSequence'];
      return _EnqueueOrder(
        enqueuedAt: enqueuedAt is String ? enqueuedAt : '',
        sequence: enqueueSequence is num ? enqueueSequence.toInt() : 0,
      );
    } catch (_) {
      return const _EnqueueOrder();
    }
  }

  String _keyFor(AppendAssistantLearningFactRequest fact) =>
      'fact.${fact.eventId}:${fact.eventVersion}';
}

final class _EnqueueOrder {
  const _EnqueueOrder({this.enqueuedAt = '', this.sequence = 0});

  final String enqueuedAt;
  final int sequence;
}
