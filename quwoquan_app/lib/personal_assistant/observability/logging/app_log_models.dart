import 'dart:convert';

enum AppLogType { pageAccess, agentRun, llm, search, cloudApi, perf, error }

enum AppLogLevel { debug, info, warn, error }

extension AppLogTypeName on AppLogType {
  String get value {
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
    this.requestId = '',
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
  final String requestId;
  final Map<String, dynamic> payload;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'ts': ts,
      'env': env,
      'appVersion': appVersion,
      'platform': platform,
      'logType': logType.value,
      'level': level.value,
      'sessionId': sessionId,
      'journeyId': journeyId,
      'pageVisitId': pageVisitId,
      'runId': runId,
      'traceId': traceId,
      'spanId': spanId,
      'requestId': requestId,
      'payload': payload,
    };
  }

  String toJsonLine() => jsonEncode(toJson());
}
