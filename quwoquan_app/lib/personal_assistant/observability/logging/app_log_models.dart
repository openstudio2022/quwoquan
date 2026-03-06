import 'dart:convert';

enum AppLogType { pageAccess, agentRun, llm, search, cloudApi, perf, error }

enum AppLogLevel { debug, info, warn, error }

extension AppLogTypeName on AppLogType {
  /// Canonical log type for cross-stack observability.
  String get value {
    switch (this) {
      case AppLogType.pageAccess:
        return 'business';
      case AppLogType.agentRun:
        return 'runtime';
      case AppLogType.llm:
        return 'api';
      case AppLogType.search:
        return 'api';
      case AppLogType.cloudApi:
        return 'api';
      case AppLogType.perf:
        return 'metric';
      case AppLogType.error:
        return 'exception';
    }
  }

  /// Legacy log type retained for backward-compatible dashboards.
  String get legacyValue {
    switch (this) {
      case AppLogType.pageAccess:
        return 'page_access';
      case AppLogType.agentRun:
        return 'agent_run';
      case AppLogType.llm:
        return 'llm';
      case AppLogType.search:
        return 'search';
      case AppLogType.cloudApi:
        return 'cloud_api';
      case AppLogType.perf:
        return 'perf';
      case AppLogType.error:
        return 'error';
    }
  }
}

extension AppLogLevelName on AppLogLevel {
  String get value {
    switch (this) {
      case AppLogLevel.debug:
        return 'DEBUG';
      case AppLogLevel.info:
        return 'INFO';
      case AppLogLevel.warn:
        return 'WARN';
      case AppLogLevel.error:
        return 'ERROR';
    }
  }
}

class AppLogEnvelope {
  const AppLogEnvelope({
    required this.ts,
    required this.env,
    required this.logType,
    required this.level,
    required this.payload,
    this.appVersion = '',
    this.platform = '',
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
    this.sourceDomain = '',
    this.sourceService = '',
    this.component = '',
    this.target = '',
    this.action = '',
  });

  final String ts;
  final String env;
  final AppLogType logType;
  final AppLogLevel level;
  final String appVersion;
  final String platform;
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
  final Map<String, dynamic> payload;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'ts': ts,
      'env': env,
      'appVersion': appVersion,
      'platform': platform,
      'logType': logType.value,
      'legacyLogType': logType.legacyValue,
      'level': level.value,
      'sourceDomain': sourceDomain,
      'sourceService': sourceService,
      'component': component,
      'target': target,
      'action': action,
      'sessionId': sessionId,
      'journeyId': journeyId,
      'pageVisitId': pageVisitId,
      'runId': runId,
      'traceId': traceId,
      'spanId': spanId,
      'parentSpanId': parentSpanId,
      'requestId': requestId,
      'cloudRequestId': cloudRequestId,
      'pythonJobId': pythonJobId,
      'correlationId': correlationId,
      'turnId': turnId,
      'payload': payload,
    };
  }

  String toJsonLine() => jsonEncode(toJson());
}
