// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

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

/// 全局异常只负责稳定错误语义、去重和方法栈裁剪；排队、加密、重试、死信全部由
/// AppTelemetryOutbox 统一承担，不维护第二套 Hive 队列。
class AppExceptionTelemetryService {
  AppExceptionTelemetryService({AppTelemetryRecorder? reporter})
    : _reporter = reporter;

  static final AppExceptionTelemetryService instance =
      AppExceptionTelemetryService();

  AppTelemetryRecorder? _reporter;
  final Set<String> _recentFingerprints = <String>{};
  AppExceptionTelemetryFailureState? _lastFlushFailure;

  AppExceptionTelemetryFailureState? get lastFlushFailure => _lastFlushFailure;

  void bind({required AppTelemetryRecorder reporter}) {
    _reporter = reporter;
  }

  void unbind(AppTelemetryRecorder reporter) {
    if (identical(_reporter, reporter)) {
      _reporter = null;
    }
  }

  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {
    final reporter = _reporter;
    if (reporter == null) return;
    final fingerprint = _fingerprint(source, exceptionText, stackText);
    if (!_rememberFingerprint(fingerprint)) return;
    final resolvedPage = pageName.trim().isEmpty || pageName == 'app'
        ? AppPageContextStore.instance.pageName
        : pageName.trim();
    final result = await reporter.record(
      AppTelemetryPayload.runtimeException(
        errorCode: 'APP.RUNTIME.uncaught_exception',
        operationId: operationId.trim().isEmpty ? null : operationId.trim(),
        callStack: _methodStack(stackText),
      ),
      pageName: resolvedPage,
    );
    if (result != AppTelemetryRecordResult.accepted) {
      _lastFlushFailure = AppExceptionTelemetryFailureState(
        errorType: result.name,
        message: 'runtime_exception_not_queued',
        queueDepth: 0,
        occurredAt: DateTime.now().toUtc(),
      );
    } else {
      _lastFlushFailure = null;
    }
  }

  Future<void> flushPending() async {
    final reporter = _reporter;
    if (reporter == null) return;
    final result = await reporter.flush();
    if (result == AppTelemetryFlushResult.deferred ||
        result == AppTelemetryFlushResult.identityBlocked) {
      _lastFlushFailure = AppExceptionTelemetryFailureState(
        errorType: result.name,
        message: 'runtime_exception_flush_deferred',
        queueDepth: 0,
        occurredAt: DateTime.now().toUtc(),
      );
    } else {
      _lastFlushFailure = null;
    }
  }

  bool _rememberFingerprint(String fingerprint) {
    if (_recentFingerprints.contains(fingerprint)) return false;
    _recentFingerprints.add(fingerprint);
    while (_recentFingerprints.length > 100) {
      _recentFingerprints.remove(_recentFingerprints.first);
    }
    return true;
  }

  String _fingerprint(String source, String exceptionText, String stackText) =>
      sha256
          .convert(utf8.encode('$source\n$exceptionText\n$stackText'))
          .toString();

  List<String> _methodStack(String stackText) {
    final methods = <String>[];
    for (final line in const LineSplitter().convert(stackText)) {
      var value = line.trim();
      value = value.replaceFirst(RegExp(r'^#\d+\s+'), '');
      final paren = value.indexOf(' (');
      if (paren >= 0) value = value.substring(0, paren);
      value = value.replaceAll(RegExp(r'[/\\][^\s:()]+'), '<path>');
      value = value.replaceAll(RegExp(r'\b[A-Za-z0-9_-]{20,}\b'), '<redacted>');
      value = value.trim();
      if (value.isEmpty) continue;
      if (value.length > 256) value = value.substring(0, 256);
      methods.add(value);
      if (methods.length == 10) break;
    }
    return methods;
  }
}
