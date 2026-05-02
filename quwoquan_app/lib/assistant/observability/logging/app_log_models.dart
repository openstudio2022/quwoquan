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
    this.pageVisitId = '',
    this.runId = '',
    this.traceId = '',
    this.requestId = '',
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
  final Map<String, dynamic> payload;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'ts': ts,
      'env': env,
      'appVersion': appVersion,
      'platform': platform,
      'logType': logType.value,
      'level': level.value,
      'sourceDomain': sourceDomain,
      'sourceService': sourceService,
      'component': component,
      'target': target,
      'action': action,
      'sessionId': sessionId,
      'pageVisitId': pageVisitId,
      'runId': runId,
      'traceId': traceId,
      'requestId': requestId,
      'turnId': turnId,
      'payload': payload,
    };
  }

  String toJsonLine() => jsonEncode(toJson());
}
