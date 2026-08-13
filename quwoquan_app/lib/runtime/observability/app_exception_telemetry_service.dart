// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/runtime/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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

/// 全局异常只负责稳定错误语义与去重；写入由统一 RuntimeLogger 的加密环形缓冲
/// 承担，不再向产品行为遥测或助手本地文件双写。
class AppExceptionTelemetryService implements ExceptionTelemetryPort {
  AppExceptionTelemetryService({RuntimeLogger? logger}) : _logger = logger;

  static final AppExceptionTelemetryService instance =
      AppExceptionTelemetryService();

  RuntimeLogger? _logger;
  final Set<String> _recentFingerprints = <String>{};
  AppExceptionTelemetryFailureState? _lastFlushFailure;

  AppExceptionTelemetryFailureState? get lastFlushFailure => _lastFlushFailure;

  void bind({required RuntimeLogger logger}) {
    _logger = logger;
  }

  void unbind(RuntimeLogger logger) {
    if (identical(_logger, logger)) {
      _logger = null;
    }
  }

  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {
    final logger = _logger;
    if (logger == null) return;
    final fingerprint = _fingerprint(source, exceptionText, stackText);
    if (!_rememberFingerprint(fingerprint)) return;
    final resolvedPage = pageName.trim().isEmpty || pageName == 'app'
        ? AppPageContextStore.instance.pageName
        : pageName.trim();
    await logger.exception(
      signal: 'app.exception.flutter',
      errorCode: RuntimeLogCatalog.failureCodes['app_uncaught_flutter']!,
      fingerprint: fingerprint,
      message: 'unhandled app exception',
      correlation: RuntimeLogCorrelation(
        operationId: operationId.trim().isEmpty
            ? 'app.runtime.capture_exception'
            : operationId.trim(),
        pageName: resolvedPage,
        surfaceId: surfaceId,
      ),
      attributes: <String, String>{
        'source': source.trim(),
        'stackFrameCount': '${_methodStack(stackText).length}',
        if (exceptionType.trim().isNotEmpty)
          'exceptionType': exceptionType.trim(),
        if (runtimeFailure != null) ...<String, String>{
          'kind': runtimeFailure.kind.name,
          'reason': runtimeFailure.semanticReason.trim().isEmpty
              ? runtimeFailure.code
              : runtimeFailure.semanticReason.trim(),
          'failurePoint': runtimeFailure.code,
        },
      },
    );
    _lastFlushFailure = null;
  }

  /// 已捕获、已降级处理的异常入口。
  ///
  /// 与全局未捕获入口共用稳定指纹和缓冲，但额外把
  /// [CloudErrorMapper.runtimeFailureFromException] 的 code/kind/reason 写入
  /// runtime log allowlist 字段，避免只有 `error.toString()` 而无法聚合恢复语义。
  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) {
    final failure = CloudErrorMapper.runtimeFailureFromException(error);
    return recordGlobalException(
      source: source,
      exceptionText: error.toString(),
      stackText: stackTrace.toString(),
      pageId: pageId,
      pageName: pageName,
      surfaceId: surfaceId,
      routeId: routeId,
      operationId: operationId,
      runtimeFailure: failure,
      exceptionType: error.runtimeType.toString(),
    );
  }

  @override
  Future<void> flushPending() async {
    final logger = _logger;
    if (logger == null) return;
    try {
      await logger.flush();
      _lastFlushFailure = null;
    } catch (_) {
      _lastFlushFailure = AppExceptionTelemetryFailureState(
        errorType: 'runtime_log_flush_failed',
        message: 'runtime_exception_flush_deferred',
        queueDepth: 0,
        occurredAt: DateTime.now().toUtc(),
      );
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

  /// 指纹基于脱敏归一化后的方法栈（而非原始 stack 文本），使同一故障在不同
  /// 时刻/路径/内存地址下聚合为同一指纹，与 AppRuntimeDiagnostics 的
  /// stack-identity 语义对齐。
  String _fingerprint(String source, String exceptionText, String stackText) =>
      sha256
          .convert(
            utf8.encode(
              '$source\n$exceptionText\n${_methodStack(stackText).join('\n')}',
            ),
          )
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
