import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';

class AssistantRoundToolCall {
  const AssistantRoundToolCall({
    required this.toolName,
    required this.toolCallId,
    required this.arguments,
  });

  final String toolName;
  final String toolCallId;
  final Map<String, Object?> arguments;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'toolName': toolName,
    'toolCallId': toolCallId,
    'arguments': arguments,
  };

  factory AssistantRoundToolCall.fromJson(Map<String, dynamic> json) {
    return AssistantRoundToolCall(
      toolName: (json['toolName'] as String?)?.trim() ?? '',
      toolCallId: (json['toolCallId'] as String?)?.trim() ?? '',
      arguments: (json['arguments'] as Map?)
              ?.cast<String, Object?>() ??
          const <String, Object?>{},
    );
  }
}

class AssistantRoundTrace {
  const AssistantRoundTrace({
    required this.domainId,
    required this.stateId,
    required this.event,
    required this.suggestedNextStateId,
    required this.nextStateCandidates,
    required this.requiredFieldsForNextState,
    required this.totalSubTotalRequired,
    required this.query,
    required this.assistantResponse,
    required this.toolCalls,
    required this.toolResultCount,
    required this.toolErrorCount,
    required this.timestamp,
  });

  final String domainId;
  final String stateId;
  final String event;
  final String suggestedNextStateId;
  final List<String> nextStateCandidates;
  final List<String> requiredFieldsForNextState;
  final bool totalSubTotalRequired;
  final String query;
  final String assistantResponse;
  final List<AssistantRoundToolCall> toolCalls;
  final int toolResultCount;
  final int toolErrorCount;
  final DateTime timestamp;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'domainId': domainId,
    'stateId': stateId,
    'event': event,
    'suggestedNextStateId': suggestedNextStateId,
    'nextStateCandidates': nextStateCandidates,
    'requiredFieldsForNextState': requiredFieldsForNextState,
    'totalSubTotalRequired': totalSubTotalRequired,
    'query': query,
    'assistantResponse': assistantResponse,
    'toolCalls': toolCalls.map((item) => item.toJson()).toList(growable: false),
    'toolResultCount': toolResultCount,
    'toolErrorCount': toolErrorCount,
    'timestamp': timestamp.toIso8601String(),
  };

  factory AssistantRoundTrace.fromJson(Map<String, dynamic> json) {
    return AssistantRoundTrace(
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      stateId: (json['stateId'] as String?)?.trim() ?? '',
      event: (json['event'] as String?)?.trim() ?? '',
      suggestedNextStateId:
          (json['suggestedNextStateId'] as String?)?.trim() ?? '',
      nextStateCandidates:
          (json['nextStateCandidates'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      requiredFieldsForNextState:
          (json['requiredFieldsForNextState'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      totalSubTotalRequired: json['totalSubTotalRequired'] == true,
      query: (json['query'] as String?)?.trim() ?? '',
      assistantResponse: (json['assistantResponse'] as String?)?.trim() ?? '',
      toolCalls: (json['toolCalls'] as List?)
              ?.whereType<Map>()
              .map((item) => AssistantRoundToolCall.fromJson(item.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <AssistantRoundToolCall>[],
      toolResultCount: (json['toolResultCount'] as num?)?.toInt() ?? 0,
      toolErrorCount: (json['toolErrorCount'] as num?)?.toInt() ?? 0,
      timestamp: DateTime.tryParse((json['timestamp'] as String?)?.trim() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
    );
  }
}

class AssistantRoundTraceCodec {
  const AssistantRoundTraceCodec();

  AssistantRoundTrace build({
    required AssistantRunRequest request,
    required ReactRuntimeResult result,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final toolCalls = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map(_toolCallFromTraceEvent)
        .toList(growable: false);
    final toolResultCount = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .length;
    final toolErrorCount = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolError)
        .length;
    return AssistantRoundTrace(
      domainId: dialogueRoundScript.domainId,
      stateId: dialogueRoundScript.currentStateId,
      event: dialogueRoundScript.detectedEvent,
      suggestedNextStateId: dialogueRoundScript.suggestedNextStateId,
      nextStateCandidates: dialogueRoundScript.nextStateCandidates,
      requiredFieldsForNextState: dialogueRoundScript.requiredFieldsForNextState,
      totalSubTotalRequired: dialogueRoundScript.totalSubTotalRequired,
      query: request.messages.isNotEmpty ? request.messages.last.content : '',
      assistantResponse: result.finalText,
      toolCalls: toolCalls,
      toolResultCount: toolResultCount,
      toolErrorCount: toolErrorCount,
      timestamp: DateTime.now(),
    );
  }
}

AssistantRoundToolCall _toolCallFromTraceEvent(AssistantTraceEvent event) {
  final data = event.data ?? const <String, dynamic>{};
  return AssistantRoundToolCall(
    toolName: (data['toolName'] as String?)?.trim() ?? '',
    toolCallId: event.toolCallId ?? '',
    arguments: Map<String, Object?>.from(data),
  );
}
