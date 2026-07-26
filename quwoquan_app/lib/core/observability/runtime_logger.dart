import 'dart:async';
import 'dart:math';

import 'package:quwoquan_app/core/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_log_redactor.dart';

enum RuntimeLogFlushResult { empty, deferred, delivered, deadLettered }

/// 诊断日志的环境策略：alpha 只保留本地记录；beta/gamma/prod 仅上传 WARN/ERROR。
final class RuntimeLogPolicy {
  const RuntimeLogPolicy({this.uploadWarningsAndErrorsOnly = true});

  final bool uploadWarningsAndErrorsOnly;

  bool shouldUpload(RuntimeLogRecord record) =>
      !uploadWarningsAndErrorsOnly ||
      record.severity == RuntimeLogSeverity.warn ||
      record.severity == RuntimeLogSeverity.error;
}

/// App 运行诊断的唯一 typed 写入口。
///
/// 业务代码只能表达日志类别、已登记 signal 与结构化事实；资源、脱敏、缓冲、采样和
/// 上传边界都在此处集中处理，避免再次引入自由格式 `debugPrint` 日志链路。
final class RuntimeLogger {
  factory RuntimeLogger({
    required RuntimeLogResource resource,
    required RuntimeLogBuffer buffer,
    RuntimeLogTransport? transport,
    RuntimeLogPolicy policy = const RuntimeLogPolicy(),
    RuntimeLogRedactor redactor = const RuntimeLogRedactor(),
    DateTime Function()? now,
    Random? random,
  }) {
    return RuntimeLogger._(
      resource,
      buffer,
      transport,
      policy,
      redactor,
      now ?? DateTime.now,
      random ?? Random.secure(),
    );
  }

  RuntimeLogger._(
    this._resource,
    this._buffer,
    this._transport,
    this._policy,
    this._redactor,
    this._now,
    this._random,
  );

  final RuntimeLogResource _resource;
  final RuntimeLogBuffer _buffer;
  final RuntimeLogTransport? _transport;
  final RuntimeLogPolicy _policy;
  final RuntimeLogRedactor _redactor;
  final DateTime Function() _now;
  final Random _random;
  Future<RuntimeLogFlushResult>? _activeFlush;
  Timer? _retryTimer;

  Future<void> runtime({
    required String signal,
    required String event,
    required String result,
    required String message,
    RuntimeLogSeverity severity = RuntimeLogSeverity.info,
    RuntimeLogCorrelation correlation = const RuntimeLogCorrelation(),
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) => _write(
    kind: RuntimeLogKind.runtime,
    severity: severity,
    signal: signal,
    message: message,
    correlation: correlation,
    event: event,
    result: result,
    attributes: attributes,
    occurredAt: occurredAt,
  );

  Future<void> access({
    required String signal,
    required String method,
    required String route,
    required String status,
    required int durationMs,
    required String message,
    RuntimeLogSeverity severity = RuntimeLogSeverity.info,
    RuntimeLogCorrelation correlation = const RuntimeLogCorrelation(),
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) => _write(
    kind: RuntimeLogKind.access,
    severity: severity,
    signal: signal,
    message: message,
    correlation: correlation,
    method: method,
    route: route,
    status: status,
    durationMs: durationMs,
    attributes: attributes,
    occurredAt: occurredAt,
  );

  Future<void> exception({
    required String signal,
    required String errorCode,
    required String message,
    required String fingerprint,
    RuntimeLogCorrelation correlation = const RuntimeLogCorrelation(),
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) => _write(
    kind: RuntimeLogKind.exception,
    severity: RuntimeLogSeverity.error,
    signal: signal,
    message: message,
    correlation: correlation,
    errorCode: errorCode,
    fingerprint: fingerprint,
    attributes: attributes,
    occurredAt: occurredAt,
  );

  Future<void> event({
    required String signal,
    required String event,
    required String result,
    required String message,
    RuntimeLogSeverity severity = RuntimeLogSeverity.info,
    RuntimeLogCorrelation correlation = const RuntimeLogCorrelation(),
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) => _write(
    kind: RuntimeLogKind.event,
    severity: severity,
    signal: signal,
    message: message,
    correlation: correlation,
    event: event,
    result: result,
    attributes: attributes,
    occurredAt: occurredAt,
  );

  Future<void> audit({
    required String signal,
    required String action,
    required String target,
    required String result,
    required String message,
    RuntimeLogCorrelation correlation = const RuntimeLogCorrelation(),
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) => _write(
    kind: RuntimeLogKind.audit,
    severity: RuntimeLogSeverity.info,
    signal: signal,
    message: message,
    correlation: correlation,
    action: action,
    target: target,
    result: result,
    attributes: attributes,
    occurredAt: occurredAt,
  );

  Future<void> _write({
    required RuntimeLogKind kind,
    required RuntimeLogSeverity severity,
    required String signal,
    required String message,
    required RuntimeLogCorrelation correlation,
    String event = '',
    String result = '',
    String method = '',
    String route = '',
    String status = '',
    int? durationMs,
    String action = '',
    String target = '',
    String errorCode = '',
    String fingerprint = '',
    Map<String, String> attributes = const <String, String>{},
    DateTime? occurredAt,
  }) async {
    final timestamp = (occurredAt ?? _now()).toUtc();
    final signalContract = RuntimeLogCatalog.signalRegistry[signal];
    final redactedAttributes = _redactor.redactAttributes(attributes);
    final registeredAttributes = signalContract == null
        ? redactedAttributes
        : <String, String>{
            for (final entry in redactedAttributes.entries)
              if (signalContract.attributeAllowlist.contains(entry.key))
                entry.key: entry.value,
          };
    final record = RuntimeLogRecord(
      recordId: _nextRecordId(timestamp),
      occurredAt: timestamp,
      observedAt: _now().toUtc(),
      kind: kind,
      severity: severity,
      signal: signal,
      message: _redactor.redactText(message),
      resource: _resource,
      correlation: correlation,
      event: event,
      result: result,
      method: method,
      route: route,
      status: status,
      durationMs: durationMs,
      action: action,
      target: target,
      errorCode: errorCode,
      fingerprint: fingerprint,
      attributes: RuntimeLogAttributes.fromMap(registeredAttributes),
    );
    await _buffer.append(record);
    if (_transport != null && _policy.shouldUpload(record)) {
      unawaited(flush());
    }
  }

  Future<RuntimeLogFlushResult> flush() {
    final active = _activeFlush;
    if (active != null) return active;
    final task = _flush();
    _activeFlush = task;
    return task.whenComplete(() {
      if (identical(_activeFlush, task)) {
        _activeFlush = null;
      }
    });
  }

  Future<RuntimeLogFlushResult> _flush() async {
    final transport = _transport;
    if (transport == null) return RuntimeLogFlushResult.deferred;
    final reliableBuffer = _buffer is ReliableRuntimeLogBuffer ? _buffer : null;
    final now = _now().toUtc();
    await reliableBuffer?.expire(now: now);
    final pending = await _buffer.pending();
    final uploadable = pending
        .where(_policy.shouldUpload)
        .toList(growable: false);
    if (uploadable.isEmpty) {
      await _scheduleNextDelivery(reliableBuffer);
      return RuntimeLogFlushResult.empty;
    }
    final ids = uploadable.map((record) => record.recordId).toList();
    try {
      final accepted = await transport.send(uploadable);
      if (accepted <= 0) {
        await reliableBuffer?.retryLater(ids, now: now);
        await _scheduleNextDelivery(reliableBuffer);
        return RuntimeLogFlushResult.deferred;
      }
      final acceptedCount = min<int>(accepted, uploadable.length);
      await _buffer.remove(
        uploadable.take(acceptedCount).map((record) => record.recordId),
      );
      final remaining = uploadable
          .skip(acceptedCount)
          .map((record) => record.recordId)
          .toList(growable: false);
      if (remaining.isNotEmpty) {
        await reliableBuffer?.retryLater(remaining, now: now);
      }
      await _scheduleNextDelivery(reliableBuffer);
      return RuntimeLogFlushResult.delivered;
    } on RuntimeLogTransportException catch (error) {
      if (error.permanent && reliableBuffer != null) {
        await reliableBuffer.deadLetter(ids, reason: error.reason, now: now);
        await _scheduleNextDelivery(reliableBuffer);
        return RuntimeLogFlushResult.deadLettered;
      }
      await reliableBuffer?.retryLater(ids, now: now);
      await _scheduleNextDelivery(reliableBuffer);
      return RuntimeLogFlushResult.deferred;
    } catch (_) {
      await reliableBuffer?.retryLater(ids, now: now);
      await _scheduleNextDelivery(reliableBuffer);
      return RuntimeLogFlushResult.deferred;
    }
  }

  /// 网络恢复时调用 [flush] 会立即重试；即使没有外部网络回调，失败后也按
  /// 缓冲中的 nextDeliveryAt 自动唤醒，避免记录永久滞留。
  Future<void> _scheduleNextDelivery(
    ReliableRuntimeLogBuffer? reliableBuffer,
  ) async {
    _retryTimer?.cancel();
    _retryTimer = null;
    if (reliableBuffer == null || _transport == null) return;
    final next = await reliableBuffer.nextDeliveryAt();
    if (next == null) return;
    final now = _now().toUtc();
    final delay = next.isAfter(now) ? next.difference(now) : Duration.zero;
    _retryTimer = Timer(delay, () => unawaited(flush()));
  }

  void dispose() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  String _nextRecordId(DateTime timestamp) {
    final random = List<int>.generate(
      8,
      (_) => _random.nextInt(256),
    ).map((value) => value.toRadixString(16).padLeft(2, '0')).join();
    return 'r.${timestamp.microsecondsSinceEpoch.toRadixString(36)}.$random';
  }
}
