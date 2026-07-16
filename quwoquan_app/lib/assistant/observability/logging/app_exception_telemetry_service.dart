import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_redactor.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

const String kAppExceptionQueueBoxName = 'app_exception_queue';

class AppExceptionTelemetryFailureState {
  const AppExceptionTelemetryFailureState({
    required this.errorType,
    required this.message,
    required this.queueDepth,
    required this.occurredAt,
  });

  final String errorType;
  final String message;
  final int queueDepth;
  final DateTime occurredAt;
}

class AppExceptionTelemetryService {
  AppExceptionTelemetryService({
    this._eventRepository,
    this._queuePartition,
    this._queueBoxName = kAppExceptionQueueBoxName,
    ActorQueueStorage? queueStorage,
  }) : _queueStorage = queueStorage ?? ActorQueueStorage();

  static final AppExceptionTelemetryService instance =
      AppExceptionTelemetryService();

  OpsEventRepository? _eventRepository;
  ActorQueuePartition? _queuePartition;
  final String _queueBoxName;
  ActorQueueStorage _queueStorage;

  final Set<String> _recentFingerprints = <String>{};
  static const AppLogRedactor _redactor = AppLogRedactor();
  AppExceptionTelemetryFailureState? _lastFlushFailure;

  AppExceptionTelemetryFailureState? get lastFlushFailure => _lastFlushFailure;

  void bind({
    required OpsEventRepository eventRepository,
    required ActorQueuePartition queuePartition,
    ActorQueueStorage? queueStorage,
  }) {
    _eventRepository = eventRepository;
    _queuePartition = queuePartition;
    if (queueStorage != null) {
      _queueStorage = queueStorage;
    }
  }

  void unbind() {
    _eventRepository = null;
    _queuePartition = null;
  }

  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = 'app',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {
    final now = DateTime.now().toUtc();
    final fingerprint = _fingerprint(source, exceptionText, stackText);
    if (!_rememberFingerprint(fingerprint)) {
      return;
    }
    final trace = AppTraceContextStore.instance;
    final requestId = trace.newRequestId();
    final event = OpsEventRecordInput(
      eventId: 'app_exception:$requestId',
      eventType: 'exception',
      eventName: 'runtime_exception',
      eventVersion: 'v1',
      priority: 'P0',
      producer: 'app.exception',
      source: source,
      sessionId: trace.sessionId,
      pageVisitId: trace.newPageVisitId(),
      surfaceId: surfaceId,
      routeId: routeId,
      operationId: operationId,
      requestId: requestId,
      pageName: pageName,
      targetType: 'app_runtime',
      targetKey: pageId,
      entityType: 'app_runtime',
      entityId: fingerprint,
      occurredAt: now.toIso8601String(),
      clientSentAt: now.toIso8601String(),
      errorCode: 'APP.RUNTIME.uncaught_exception',
      errorModule: 'APP',
      errorKind: 'RUNTIME',
      errorReason: 'uncaught_exception',
      origin: 'localClient',
      nature: 'bug',
      failurePoint: source,
      stackHash: _stackHash(stackText),
      businessObject: 'app_runtime',
      functionModule: 'global_error_handler',
      appRuntimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      appVersion: CloudRequestHeaders.appVersion,
      platform: CloudRequestHeaders.platform(),
      networkClass: await _networkClass(),
      payload: {
        'exception': _truncate(_redactor.redactText(exceptionText), 2048),
        'stack': _truncate(_redactor.redactText(stackText), 8192),
      },
    );
    await _enqueue(event);
    unawaited(
      flushPending().catchError((Object error, StackTrace stackTrace) async {
        await _recordFlushFailure(error, stackTrace, phase: 'background_flush');
      }),
    );
  }

  Future<void> flushPending() async {
    final eventRepository = _eventRepository;
    if (eventRepository == null) {
      return;
    }
    final box = await _ensureBox();
    if (box == null) {
      return;
    }
    final events = <OpsEventRecordInput>[];
    final processedKeys = <String>[];
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final envelope = (jsonDecode(raw) as Map).cast<String, Object?>();
        final partition = _queuePartition;
        if (partition == null ||
            !partition.acceptsEnvelope(envelope['actorPartitionKey'])) {
          if (partition != null) {
            await _queueStorage.moveToDlq(
              partition: partition,
              queueName: _queueBoxName,
              sourceKey: key,
              rawEnvelope: raw,
              reason: 'actor_partition_mismatch',
            );
          }
          continue;
        }
        final event = (envelope['event'] as Map).cast<String, Object?>();
        events.add(OpsEventRecordInput.fromJsonObject(event));
        processedKeys.add(key);
      } catch (error) {
        developer.log(
          'app exception telemetry drops corrupt queue item: $error',
          name: 'AppExceptionTelemetryService',
        );
        final partition = _queuePartition;
        if (partition != null) {
          await _queueStorage.moveToDlq(
            partition: partition,
            queueName: _queueBoxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'poison_${error.runtimeType}',
          );
        }
      }
    }
    if (events.isEmpty) {
      return;
    }
    try {
      final ack = await eventRepository.reportEventBatch(events: events);
      if (ack.acceptedCount + ack.duplicateCount >= events.length) {
        await box.deleteAll(processedKeys);
      }
    } catch (error, stackTrace) {
      await _recordFlushFailure(error, stackTrace, phase: 'report_batch');
    }
  }

  Future<Box<String>?> _ensureBox() async {
    final partition = _queuePartition;
    if (partition == null || !partition.canPersist) {
      return null;
    }
    return _queueStorage.open(partition, _queueBoxName);
  }

  Future<void> _enqueue(OpsEventRecordInput event) async {
    final box = await _ensureBox();
    if (box == null) {
      return;
    }
    final partition = _queuePartition;
    if (partition == null) return;
    await box.put(
      event.eventId,
      jsonEncode(<String, Object?>{
        'actorPartitionKey': partition.key,
        'event': event.toJson(),
      }),
    );
    if (box.length > 100) {
      final keys = box.keys.map((key) => key.toString()).toList(growable: false)
        ..sort();
      final overflow = box.length - 100;
      for (var i = 0; i < overflow; i++) {
        final overflowKey = keys[i];
        final raw = box.get(overflowKey);
        if (raw == null) {
          await box.delete(overflowKey);
          continue;
        }
        await _queueStorage.moveToDlq(
          partition: partition,
          queueName: _queueBoxName,
          sourceKey: overflowKey,
          rawEnvelope: raw,
          reason: 'queue_capacity_exceeded',
          kind: ActorQueueSignalKind.overflowMoved,
        );
      }
    }
  }

  Future<void> clearPendingForLogout() async {
    final partition = _queuePartition;
    if (partition == null) return;
    await _queueStorage.purge(partition, _queueBoxName);
  }

  Future<void> _recordFlushFailure(
    Object error,
    StackTrace stackTrace, {
    required String phase,
  }) async {
    final queueDepth = await _queueDepth();
    _lastFlushFailure = AppExceptionTelemetryFailureState(
      errorType: error.runtimeType.toString(),
      message: _truncate(error.toString(), 512),
      queueDepth: queueDepth,
      occurredAt: DateTime.now().toUtc(),
    );
    developer.log(
      'app exception telemetry flush failed',
      name: 'AppExceptionTelemetryService',
      error: error,
      stackTrace: stackTrace,
      time: _lastFlushFailure?.occurredAt,
      level: 900,
      sequenceNumber: queueDepth,
    );
    developer.log(
      jsonEncode(<String, dynamic>{
        'phase': phase,
        'errorType': _lastFlushFailure?.errorType,
        'queueDepth': queueDepth,
        'lastFailureAt': _lastFlushFailure?.occurredAt.toIso8601String(),
      }),
      name: 'AppExceptionTelemetryService.state',
    );
  }

  Future<int> _queueDepth() async {
    final box = await _ensureBox();
    return box?.length ?? 0;
  }

  bool _rememberFingerprint(String fingerprint) {
    if (_recentFingerprints.contains(fingerprint)) {
      return false;
    }
    _recentFingerprints.add(fingerprint);
    if (_recentFingerprints.length > 32) {
      _recentFingerprints.remove(_recentFingerprints.first);
    }
    return true;
  }

  Future<String> _networkClass() async {
    try {
      final values = await Connectivity().checkConnectivity();
      if (values.contains(ConnectivityResult.wifi)) {
        return 'wifi';
      }
      if (values.contains(ConnectivityResult.mobile)) {
        return 'mobile';
      }
      if (values.contains(ConnectivityResult.none)) {
        return 'none';
      }
      return 'other';
    } catch (_) {
      return 'other';
    }
  }

  String _fingerprint(String source, String exceptionText, String stackText) {
    return sha256
        .convert(
          utf8.encode(
            '$source|${_truncate(exceptionText, 512)}|${_stackHead(stackText)}',
          ),
        )
        .toString()
        .substring(0, 16);
  }

  String _stackHash(String stackText) {
    return sha256
        .convert(utf8.encode(_stackHead(stackText)))
        .toString()
        .substring(0, 16);
  }

  String _stackHead(String stackText) {
    return stackText.split('\n').take(8).join('\n');
  }

  String _truncate(String value, int maxLength) {
    if (value.length <= maxLength) {
      return value;
    }
    return value.substring(0, maxLength);
  }
}
