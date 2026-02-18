enum AssistantTraceEventType {
  lifecycleStart,
  lifecycleEnd,
  assistantDelta,
  toolStart,
  toolResult,
  toolError,
  skillStart,
  skillResult,
  skillError,
}

AssistantTraceEventType parseAssistantTraceEventType(String raw) {
  return AssistantTraceEventType.values.firstWhere(
    (e) => e.name == raw,
    orElse: () => AssistantTraceEventType.assistantDelta,
  );
}

class AssistantTraceEvent {
  const AssistantTraceEvent({
    required this.type,
    required this.message,
    required this.timestamp,
    this.data,
    this.runId,
    this.traceId,
    this.toolCallId,
  });

  final AssistantTraceEventType type;
  final String message;
  final DateTime timestamp;
  final Map<String, dynamic>? data;
  final String? runId;
  final String? traceId;
  final String? toolCallId;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'type': type.name,
      'message': message,
      'timestamp': timestamp.toIso8601String(),
      'data': data,
      'runId': runId,
      'traceId': traceId,
      'toolCallId': toolCallId,
    };
  }

  factory AssistantTraceEvent.fromJson(Map<String, dynamic> json) {
    final ts = (json['timestamp'] as String?)?.trim() ?? '';
    return AssistantTraceEvent(
      type: parseAssistantTraceEventType((json['type'] as String?)?.trim() ?? ''),
      message: (json['message'] as String?) ?? '',
      timestamp: DateTime.tryParse(ts) ?? DateTime.fromMillisecondsSinceEpoch(0),
      data: (json['data'] as Map?)?.cast<String, dynamic>(),
      runId: json['runId'] as String?,
      traceId: json['traceId'] as String?,
      toolCallId: json['toolCallId'] as String?,
    );
  }
}
