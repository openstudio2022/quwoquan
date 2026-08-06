import 'dart:convert';
import 'dart:developer' as developer;

import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantLearningFactAppendCommand,
        encodeAssistantAssistantLearningFactAppendAssistantLearningFactGeneratedRequest;

/// Actor-scoped encrypted pending-confirmation queue for assistant learning
/// facts. A record is removed only after the server receipt confirms the exact
/// event identity and a canonical payload digest.
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

  Future<bool> enqueue(AssistantLearningFactAppendCommand fact) async {
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
          jsonEncode(_encodeFact(existing)) != jsonEncode(_encodeFact(fact))) {
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
        'fact': _encodeFact(fact),
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
            !_sha256DigestPattern.hasMatch(receipt.payloadDigest)) {
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

  AssistantLearningFactAppendCommand? _decodeFact(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map ||
          !_partition.acceptsEnvelope(decoded['actorPartitionKey'])) {
        return null;
      }
      final value = decoded['fact'];
      if (value is! Map) return null;
      final fact = value.cast<String, dynamic>();
      // Retired eventVersion records must be rejected; local persistence does
      // not keep a legacy-shape read path.
      if (fact.containsKey('eventVersion')) return null;
      return AssistantLearningFactAppendCommand(
        eventId: fact['eventId'] as String,
        factType: fact['factType'] as String,
        assistantTurnId: fact['assistantTurnId'] as String,
        triggerMessageId: fact['triggerMessageId'] as String?,
        referralSource: fact['referralSource'] as String,
        domainId: fact['domainId'] as String,
        eventType: fact['eventType'] as String?,
        feedbackType: fact['feedbackType'] as String?,
        feedbackScore: (fact['feedbackScore'] as num?)?.toDouble(),
        reasonCodes: ((fact['reasonCodes'] as List?) ?? const <Object?>[])
            .cast<String>(),
        actionType: fact['actionType'] as String?,
        suggestedActionId: fact['suggestedActionId'] as String?,
        durationMs: (fact['durationMs'] as num?)?.toInt(),
        queryText: fact['queryText'] as String?,
        answerText: fact['answerText'] as String?,
        feedbackText: fact['feedbackText'] as String?,
        correctionText: fact['correctionText'] as String?,
        trainingEligible: fact['trainingEligible'] as bool,
        occurredAt: DateTime.parse(fact['occurredAt'] as String),
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

  String _keyFor(AssistantLearningFactAppendCommand fact) =>
      'fact.${fact.eventId}';
}

final RegExp _sha256DigestPattern = RegExp(r'^[0-9a-f]{64}$');

Map<String, Object?> _encodeFact(AssistantLearningFactAppendCommand fact) {
  final body =
      encodeAssistantAssistantLearningFactAppendAssistantLearningFactGeneratedRequest(
        fact,
      ).body;
  if (body is! Map<String, Object?>) {
    throw StateError('Assistant learning fact encoder must produce an object');
  }
  return body;
}

final class _EnqueueOrder {
  const _EnqueueOrder({this.enqueuedAt = '', this.sequence = 0});

  final String enqueuedAt;
  final int sequence;
}
