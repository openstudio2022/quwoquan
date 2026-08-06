import 'dart:async';

import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';

/// 断开 CloudHttpClient 与组合根的依赖环，同时将 HTTP 延迟接入统一 runtime 日志。
///
/// CloudHttpClient 在 RuntimeLogger 初始化期间就会被装配；因此客户端只依赖这个
/// 中性 dispatcher，而由 DI 在 logger 就绪后绑定实际实现。
final class RuntimeApiLatencyDispatcher {
  RuntimeLogger? _logger;

  void bind(RuntimeLogger logger) {
    _logger = logger;
  }

  void unbind(RuntimeLogger logger) {
    if (identical(_logger, logger)) {
      _logger = null;
    }
  }

  void record(String method, String path, int elapsedMs, int statusCode) {
    final logger = _logger;
    if (logger == null) return;
    final severity = statusCode >= 500 || statusCode < 0
        ? RuntimeLogSeverity.error
        : statusCode >= 400
        ? RuntimeLogSeverity.warn
        : RuntimeLogSeverity.info;
    unawaited(
      logger.access(
        signal: 'app.access.http',
        method: method,
        route: _routeTemplate(path),
        status: '$statusCode',
        durationMs: elapsedMs < 0 ? 0 : elapsedMs,
        message: 'cloud HTTP request completed',
        severity: severity,
      ),
    );
  }

  String _routeTemplate(String path) {
    final noQuery = path.split('?').first;
    final segments = noQuery.split('/');
    return segments
        .map(
          (segment) => segment.isEmpty
              ? segment
              : _isVariableSegment(segment)
              ? ':id'
              : segment,
        )
        .join('/');
  }

  bool _isVariableSegment(String value) =>
      RegExp(r'^\d+$').hasMatch(value) ||
      RegExp(
        r'^[0-9a-f]{8}-[0-9a-f-]{27,}$',
        caseSensitive: false,
      ).hasMatch(value) ||
      RegExp(r'^[A-Za-z0-9_-]{20,}$').hasMatch(value);
}
