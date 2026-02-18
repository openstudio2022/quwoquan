class AssistentAuditLog {
  const AssistentAuditLog({
    required this.event,
    required this.actor,
    required this.channel,
    required this.runId,
    required this.traceId,
    required this.statusCode,
    required this.timestamp,
    this.metadata = const <String, dynamic>{},
  });

  final String event;
  final String actor;
  final String channel;
  final String runId;
  final String traceId;
  final int statusCode;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'event': event,
      'actor': actor,
      'channel': channel,
      'runId': runId,
      'traceId': traceId,
      'statusCode': statusCode,
      'timestamp': timestamp.toIso8601String(),
      'metadata': metadata,
    };
  }
}

class AssistentAuditLogger {
  final List<AssistentAuditLog> _logs = <AssistentAuditLog>[];

  Future<void> write(AssistentAuditLog log) async {
    _logs.add(log);
  }

  Future<List<AssistentAuditLog>> recent({int limit = 200}) async {
    if (_logs.length <= limit) {
      return List<AssistentAuditLog>.from(_logs.reversed);
    }
    final start = _logs.length - limit;
    return _logs.sublist(start).reversed.toList(growable: false);
  }
}

