import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/runtime/observability/app_log_policy.dart';
import 'package:quwoquan_app/runtime/observability/app_log_redactor.dart';
import 'package:quwoquan_app/runtime/observability/app_log_writer.dart';
import 'package:quwoquan_app/runtime/observability/operation_privacy_redactor.dart';

class AppLogContext {
  const AppLogContext({
    this.sessionId = '',
    this.pageVisitId = '',
    this.runId = '',
    this.traceId = '',
    this.requestId = '',
    this.turnId = '',
    this.sourceDomain = 'assistant',
    this.sourceService = 'quwoquan_app',
    this.component = '',
    this.target = '',
    this.action = '',
    this.operationId = '',
    this.operationDirection = OperationPayloadDirection.request,
  });

  final String sessionId;
  final String pageVisitId;
  final String runId;
  final String traceId;
  final String requestId;
  final String turnId;
  final String sourceDomain;
  final String sourceService;
  final String component;
  final String target;
  final String action;

  /// ContractGraph operation id。非空时该条日志的载荷额外受
  /// `operation.privacy` 约束；未登记的 operation 按 fail-closed 丢弃载荷。
  final String operationId;

  /// 载荷方向，决定取 request 还是 response 的密级。
  final OperationPayloadDirection operationDirection;
}

class AppLogService implements AppEventLogPort {
  AppLogService._({
    required this._writer,
    required this._policy,
    required this._redactor,
  });

  static final AppLogService instance = AppLogService._(
    writer: AppLogWriter(),
    policy: AppLogPolicy(),
    redactor: const AppLogRedactor(),
  );

  factory AppLogService.forTesting({
    required AppLogWriter writer,
    required AppLogPolicy policy,
    AppLogRedactor redactor = const AppLogRedactor(),
  }) {
    return AppLogService._(writer: writer, policy: policy, redactor: redactor);
  }

  final AppLogWriter _writer;
  final AppLogPolicy _policy;
  final AppLogRedactor _redactor;
  static const OperationPrivacyRedactor _privacyRedactor =
      OperationPrivacyRedactor();

  void boostSession(String sessionId) => _policy.boostSession(sessionId);
  void boostRun(String runId) => _policy.boostRun(runId);
  void clearBoosts() => _policy.clearBoosts();

  @override
  Future<String?> writeEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required Map<String, dynamic> payload,
    required AppLogContext context,
    bool hasError = false,
    Map<String, dynamic>? summaryPayload,
  }) async {
    final shouldEmit =
        hasError ||
        _policy.shouldEmitSuccessLog(
          sessionId: context.sessionId,
          runId: context.runId,
          type: logType,
        );
    if (!shouldEmit) return null;

    final includeFull = _policy.shouldIncludeFullPayload(
      sessionId: context.sessionId,
      runId: context.runId,
      hasError: hasError,
      type: logType,
    );
    final rawPayload = includeFull
        ? payload
        : (summaryPayload ?? _toSummary(payload));
    // 键名黑名单先兜底，再由 `operation.privacy` 做最终裁决：契约声明的密级
    // 是唯一权威，键名规则只覆盖它没枚举到的常见敏感键。
    final redactedPayload = _applyOperationPrivacy(
      context: context,
      payload: _redactor.redactMap(rawPayload),
    );
    final envelope = _buildEnvelope(
      ts: DateTime.now().toIso8601String(),
      logType: logType,
      level: level,
      payload: redactedPayload,
      context: context,
      hasError: hasError,
    );

    try {
      final target = _targetFor(logType);
      final path = await _writer.appendLogLine(
        subDirectory: target.subDir,
        fileName: target.fileName,
        line: envelope.toLogLine(target.kind),
      );
      return path;
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AppLogService] writeEvent failed: $error');
      }
      return null;
    }
  }

  @override
  Future<String?> writeRunFile({
    required String runId,
    required Map<String, dynamic> payload,
  }) async {
    try {
      return await _writer.writeJsonFile(
        subDirectory: 'agent',
        fileName: 'run_${_sanitize(runId)}.json',
        payload: _redactor.redactMap(payload),
      );
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AppLogService] writeRunFile failed: $error');
      }
      return null;
    }
  }

  /// 对声明了 operation 的日志套用 `operation.privacy`。
  ///
  /// `operationId` 为空表示这不是 operation 作用域的日志（生命周期、导航等），
  /// 不进入契约表；一旦声明了 operation 就必须 fail-closed，未登记的 operation
  /// 载荷整条丢弃，避免「契约没覆盖到」变成「运行时泄漏」。
  Map<String, dynamic> _applyOperationPrivacy({
    required AppLogContext context,
    required Map<String, dynamic> payload,
  }) {
    final operationId = context.operationId.trim();
    if (operationId.isEmpty) return payload;
    return _privacyRedactor.redactLogPayload(
      operationId: operationId,
      direction: context.operationDirection,
      payload: payload,
    );
  }

  Map<String, dynamic> _toSummary(Map<String, dynamic> payload) {
    final keys = payload.keys.take(8).toList(growable: false);
    final summary = <String, dynamic>{};
    for (final key in keys) {
      final value = payload[key];
      if (value is String && value.length > 180) {
        summary[key] = '${value.substring(0, 180)}...';
      } else {
        summary[key] = value;
      }
    }
    summary['truncated'] = payload.length > keys.length;
    return summary;
  }

  AppLogEnvelope _buildEnvelope({
    required String ts,
    required AppLogType logType,
    required AppLogLevel level,
    required Map<String, dynamic> payload,
    required AppLogContext context,
    required bool hasError,
  }) {
    final attrs = Map<String, dynamic>.from(payload);
    final msg =
        _takeString(attrs, const ['msg', 'message', 'summary']) ??
        _defaultMessageFor(logType, context);
    final result =
        _takeString(attrs, const ['result', 'statusText']) ??
        (hasError ? 'failed' : 'ok');
    final event =
        _takeString(attrs, const ['event', 'eventName', 'action']) ??
        context.action;
    final method = _takeString(attrs, const ['method', 'httpMethod']) ?? '';
    final route = _takeString(attrs, const ['route', 'path', 'url']) ?? '';
    final status = _takeInt(attrs, const ['status', 'statusCode']);
    final durMs = _takeInt(attrs, const ['durMs', 'durationMs', 'elapsedMs']);
    final err =
        _takeString(attrs, const ['err', 'error', 'exception']) ??
        (hasError ? msg : '');
    final target = context.target.isNotEmpty
        ? context.target
        : (_takeString(attrs, const ['target']) ?? _defaultTargetFor(logType));
    if (target.isNotEmpty && logType == AppLogType.error) {
      attrs['target'] = target;
    }

    return AppLogEnvelope(
      ts: ts,
      level: level,
      msg: msg,
      event: logType.value == 'event' ? _fallbackEvent(logType, event) : '',
      result: logType.value == 'event' ? result : '',
      method: logType.value == 'access'
          ? _fallbackAccessMethod(logType, method)
          : '',
      route: logType.value == 'access'
          ? _fallbackAccessRoute(logType, route)
          : '',
      status: logType.value == 'access'
          ? (status ?? (hasError ? 500 : 200))
          : null,
      durMs: logType.value == 'access' ? (durMs ?? 0) : null,
      req: context.requestId,
      trace: context.traceId,
      err: logType == AppLogType.error ? err : '',
      attrs: _boundedAttrs(attrs),
    );
  }

  String? _takeString(Map<String, dynamic> payload, List<String> keys) {
    for (final key in keys) {
      final value = payload.remove(key);
      if (value == null) continue;
      final text = value.toString().trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  int? _takeInt(Map<String, dynamic> payload, List<String> keys) {
    for (final key in keys) {
      final value = payload.remove(key);
      if (value is int) return value;
      if (value is num) return value.toInt();
      if (value is String) {
        final parsed = int.tryParse(value);
        if (parsed != null) return parsed;
      }
    }
    return null;
  }

  String _fallbackEvent(AppLogType type, String value) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) return trimmed;
    switch (type) {
      case AppLogType.pageAccess:
        return 'page_access';
      case AppLogType.agentRun:
        return 'agent_run';
      case AppLogType.perf:
        return 'perf_sample';
      case AppLogType.llm:
      case AppLogType.search:
      case AppLogType.cloudApi:
      case AppLogType.error:
        return type.name;
    }
  }

  String _fallbackAccessMethod(AppLogType type, String value) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) return trimmed.toUpperCase();
    switch (type) {
      case AppLogType.llm:
        return 'LLM';
      case AppLogType.search:
        return 'SEARCH';
      case AppLogType.cloudApi:
        return 'HTTP';
      case AppLogType.pageAccess:
      case AppLogType.agentRun:
      case AppLogType.perf:
      case AppLogType.error:
        return 'APP';
    }
  }

  String _fallbackAccessRoute(AppLogType type, String value) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) return trimmed;
    return _defaultTargetFor(type);
  }

  Map<String, dynamic> _boundedAttrs(Map<String, dynamic> payload) {
    if (payload.isEmpty) return const <String, dynamic>{};
    final attrs = <String, dynamic>{};
    for (final entry in payload.entries.take(12)) {
      final value = entry.value;
      if (value is String && value.length > 240) {
        attrs[entry.key] = '${value.substring(0, 240)}...';
      } else if (value is Map || value is Iterable) {
        attrs[entry.key] = value.toString().length > 240
            ? '${value.toString().substring(0, 240)}...'
            : value.toString();
      } else {
        attrs[entry.key] = value;
      }
    }
    return attrs;
  }

  _LogTarget _targetFor(AppLogType type) {
    switch (type) {
      case AppLogType.pageAccess:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'event.log',
          kind: 'event',
        );
      case AppLogType.agentRun:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'event.log',
          kind: 'event',
        );
      case AppLogType.llm:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'access.log',
          kind: 'access',
        );
      case AppLogType.search:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'access.log',
          kind: 'access',
        );
      case AppLogType.cloudApi:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'access.log',
          kind: 'access',
        );
      case AppLogType.perf:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'event.log',
          kind: 'event',
        );
      case AppLogType.error:
        return const _LogTarget(
          subDir: 'app',
          fileName: 'exception.log',
          kind: 'exception',
        );
    }
  }

  String _defaultMessageFor(AppLogType type, AppLogContext context) {
    final action = context.action.trim();
    if (action.isNotEmpty) return action;
    switch (type) {
      case AppLogType.pageAccess:
        return 'page access';
      case AppLogType.agentRun:
        return 'agent run';
      case AppLogType.llm:
        return 'llm request';
      case AppLogType.search:
        return 'search request';
      case AppLogType.cloudApi:
        return 'cloud api request';
      case AppLogType.perf:
        return 'performance sample';
      case AppLogType.error:
        return 'app exception';
    }
  }

  String _defaultTargetFor(AppLogType type) {
    switch (type) {
      case AppLogType.pageAccess:
        return 'ui_context';
      case AppLogType.agentRun:
        return 'session';
      case AppLogType.llm:
        return 'llm';
      case AppLogType.search:
        return 'search_provider';
      case AppLogType.cloudApi:
        return 'cloud_service';
      case AppLogType.perf:
        return 'runtime';
      case AppLogType.error:
        return 'runtime';
    }
  }

  String _sanitize(String value) {
    return value.replaceAll(RegExp(r'[^a-zA-Z0-9_\-]'), '_');
  }
}

class _LogTarget {
  const _LogTarget({
    required this.subDir,
    required this.fileName,
    required this.kind,
  });

  final String subDir;
  final String fileName;
  final String kind;
}
