import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';

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
  subagentStart,
  subagentResult,
  subagentError,

  /// Real-time streaming token delta from synthesis LLM (SSE).
  streamDelta,

  // v2 semantic event types for granular UI rendering
  planStarted,
  planCompleted,
  searchQueryGenerated,
  searchStarted,
  searchCompleted,
  thinkingStarted,
  thinkingProgress,
  answerStarted,
  answerDelta,
  answerCompleted,
  replanTriggered,
  selfCheckResult,
}

/// User-facing phase events, decoupled from internal trace types.
/// Used by the event translation layer (capability_gateway) and UI rendering.
enum UserPhaseEventType {
  // Fixed phases
  understandingStarted,
  understandingThinking,
  analyzingStarted,
  analyzingThinking,
  answeringStarted,
  answeringDelta,
  answeringCompleted,

  // Generic tool phases (tool-agnostic, specific labels from metadata)
  toolReasoningStarted,
  toolReasoningThinking,
  toolExecutionStarted,
  toolExecutionProgress,
  toolExecutionCompleted,

  // Assessment phase (post-tool evaluation)
  toolAssessmentStarted,
  toolAssessmentResult,
  loopDegraded,
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
    this.visibility = TraceVisibility.userVisible,
  });

  final AssistantTraceEventType type;
  final String message;
  final DateTime timestamp;
  final Map<String, dynamic>? data;
  final String? runId;
  final String? traceId;
  final String? toolCallId;
  final TraceVisibility visibility;

  AssistantTraceEvent copyWith({
    AssistantTraceEventType? type,
    String? message,
    DateTime? timestamp,
    Map<String, dynamic>? data,
    String? runId,
    String? traceId,
    String? toolCallId,
    TraceVisibility? visibility,
  }) {
    return AssistantTraceEvent(
      type: type ?? this.type,
      message: message ?? this.message,
      timestamp: timestamp ?? this.timestamp,
      data: data ?? this.data,
      runId: runId ?? this.runId,
      traceId: traceId ?? this.traceId,
      toolCallId: toolCallId ?? this.toolCallId,
      visibility: visibility ?? this.visibility,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'type': type.name,
      'message': message,
      'timestamp': timestamp.toIso8601String(),
      'data': data,
      'runId': runId,
      'traceId': traceId,
      'toolCallId': toolCallId,
      'visibility': visibility.wireName,
    };
  }

  factory AssistantTraceEvent.fromJson(Map<String, dynamic> json) {
    final ts = (json['timestamp'] as String?)?.trim() ?? '';
    return AssistantTraceEvent(
      type: parseAssistantTraceEventType(
        (json['type'] as String?)?.trim() ?? '',
      ),
      message: (json['message'] as String?) ?? '',
      timestamp:
          DateTime.tryParse(ts) ?? DateTime.fromMillisecondsSinceEpoch(0),
      data: (json['data'] as Map?)?.cast<String, dynamic>(),
      runId: json['runId'] as String?,
      traceId: json['traceId'] as String?,
      toolCallId: json['toolCallId'] as String?,
      visibility: parseTraceVisibility(
        (json['visibility'] as String?)?.trim() ?? '',
      ),
    );
  }
}
