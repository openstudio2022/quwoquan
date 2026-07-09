import 'dart:convert';

enum AppLogType { pageAccess, agentRun, llm, search, cloudApi, perf, error }

enum AppLogLevel { debug, info, warn, error }

extension AppLogTypeName on AppLogType {
  /// Canonical log type for cross-stack observability.
  String get value {
    switch (this) {
      case AppLogType.pageAccess:
        return 'event';
      case AppLogType.agentRun:
        return 'event';
      case AppLogType.llm:
        return 'access';
      case AppLogType.search:
        return 'access';
      case AppLogType.cloudApi:
        return 'access';
      case AppLogType.perf:
        return 'event';
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
    required this.level,
    required this.msg,
    this.event = '',
    this.result = '',
    this.method = '',
    this.route = '',
    this.status,
    this.durMs,
    this.req = '',
    this.trace = '',
    this.span = '',
    this.err = '',
    this.attrs = const <String, dynamic>{},
  });

  final String ts;
  final AppLogLevel level;
  final String msg;
  final String event;
  final String result;
  final String method;
  final String route;
  final int? status;
  final int? durMs;
  final String req;
  final String trace;
  final String span;
  final String err;
  final Map<String, dynamic> attrs;

  String toLogLine(String kind) {
    final fields = switch (kind) {
      'access' => <String>[
        ts,
        level.value,
        method,
        route,
        status?.toString() ?? '',
        durMs?.toString() ?? '',
        req,
        trace,
        _messageWithAttrs(),
      ],
      'exception' => <String>[
        ts,
        level.value,
        err,
        req,
        trace,
        _messageWithAttrs(),
      ],
      'event' => <String>[
        ts,
        level.value,
        event,
        result,
        req,
        trace,
        _messageWithAttrs(),
      ],
      _ => <String>[ts, level.value, _messageWithAttrs()],
    };
    return _joinDelimited(fields);
  }

  String _messageWithAttrs() {
    if (attrs.isEmpty) return msg;
    final encoded = jsonEncode(attrs);
    if (msg.trim().isEmpty) return 'attrs=$encoded';
    return '$msg attrs=$encoded';
  }

  String _joinDelimited(List<String> fields) {
    final message = fields.last.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    final lines = message.split('\n');
    final prefix = fields.take(fields.length - 1).map(_prefixField).toList();
    final buffer = StringBuffer([...prefix, lines.first].join(','));
    for (final line in lines.skip(1)) {
      buffer.write('\n\t$line');
    }
    return buffer.toString();
  }

  String _prefixField(String value) {
    return value
        .replaceAll('\r\n', ' ')
        .replaceAll('\n', ' ')
        .replaceAll(',', '%2C');
  }
}
