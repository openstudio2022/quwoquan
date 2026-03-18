import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_policy.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_redactor.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_writer.dart';

class AppLogContext {
  const AppLogContext({
    this.sessionId = '',
    this.journeyId = '',
    this.pageVisitId = '',
    this.runId = '',
    this.traceId = '',
    this.spanId = '',
    this.parentSpanId = '',
    this.requestId = '',
    this.cloudRequestId = '',
    this.pythonJobId = '',
    this.correlationId = '',
    this.turnId = '',
    this.sourceDomain = 'assistant',
    this.sourceService = 'quwoquan_app',
    this.component = '',
    this.target = '',
    this.action = '',
  });

  final String sessionId;
  final String journeyId;
  final String pageVisitId;
  final String runId;
  final String traceId;
  final String spanId;
  final String parentSpanId;
  final String requestId;
  final String cloudRequestId;
  final String pythonJobId;
  final String correlationId;
  final String turnId;
  final String sourceDomain;
  final String sourceService;
  final String component;
  final String target;
  final String action;
}

class AppLogService {
  AppLogService._({
    required AppLogWriter writer,
    required AppLogPolicy policy,
    required AppLogRedactor redactor,
  }) : _writer = writer,
       _policy = policy,
       _redactor = redactor;

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

  void boostSession(String sessionId) => _policy.boostSession(sessionId);
  void boostRun(String runId) => _policy.boostRun(runId);
  void clearBoosts() => _policy.clearBoosts();

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
    final redactedPayload = _redactor.redactMap(rawPayload);
    final envelope = AppLogEnvelope(
      ts: DateTime.now().toIso8601String(),
      env: kReleaseMode ? 'release' : 'debug',
      appVersion: '',
      platform: Platform.operatingSystem,
      logType: logType,
      level: level,
      sessionId: context.sessionId,
      journeyId: context.journeyId,
      pageVisitId: context.pageVisitId,
      runId: context.runId,
      traceId: context.traceId,
      spanId: context.spanId,
      parentSpanId: context.parentSpanId,
      requestId: context.requestId,
      cloudRequestId: context.cloudRequestId,
      pythonJobId: context.pythonJobId,
      correlationId: context.correlationId,
      turnId: context.turnId,
      sourceDomain: context.sourceDomain,
      sourceService: context.sourceService,
      component: context.component.isNotEmpty
          ? context.component
          : _defaultComponentFor(logType),
      target: context.target.isNotEmpty ? context.target : _defaultTargetFor(logType),
      action: context.action,
      payload: redactedPayload,
    );

    try {
      final target = _targetFor(logType);
      final path = await _writer.appendJsonLine(
        subDirectory: target.subDir,
        fileName: target.fileName,
        payload: envelope.toJson(),
      );
      return path;
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AppLogService] writeEvent failed: $error');
      }
      return null;
    }
  }

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

  _LogTarget _targetFor(AppLogType type) {
    switch (type) {
      case AppLogType.pageAccess:
        return const _LogTarget(
          subDir: 'page_access',
          fileName: 'events.jsonl',
        );
      case AppLogType.agentRun:
        return const _LogTarget(
          subDir: 'agent',
          fileName: 'interactions.jsonl',
        );
      case AppLogType.llm:
        return const _LogTarget(subDir: 'integrations', fileName: 'llm.jsonl');
      case AppLogType.search:
        return const _LogTarget(
          subDir: 'integrations',
          fileName: 'search.jsonl',
        );
      case AppLogType.cloudApi:
        return const _LogTarget(
          subDir: 'integrations',
          fileName: 'cloud_api.jsonl',
        );
      case AppLogType.perf:
        return const _LogTarget(subDir: 'perf', fileName: 'stats.jsonl');
      case AppLogType.error:
        return const _LogTarget(subDir: 'errors', fileName: 'errors.jsonl');
    }
  }

  String _defaultComponentFor(AppLogType type) {
    switch (type) {
      case AppLogType.pageAccess:
        return 'ui';
      case AppLogType.agentRun:
        return 'assistant_agent_loop';
      case AppLogType.llm:
        return 'llm_provider';
      case AppLogType.search:
        return 'search_tool';
      case AppLogType.cloudApi:
        return 'gateway_client';
      case AppLogType.perf:
        return 'perf_probe';
      case AppLogType.error:
        return 'runtime';
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
  const _LogTarget({required this.subDir, required this.fileName});

  final String subDir;
  final String fileName;
}
