import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class AssistantToolResultRow {
  const AssistantToolResultRow({
    required this.toolName,
    required this.toolCallId,
    required this.message,
    required this.data,
  });

  final String toolName;
  final String toolCallId;
  final String message;
  final Map<String, dynamic> data;

  Map<String, dynamic> get dataPayload => data;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'toolName': toolName,
    'toolCallId': toolCallId,
    'message': message,
    'data': data,
  };

  factory AssistantToolResultRow.fromJson(Map<String, dynamic> json) {
    return AssistantToolResultRow(
      toolName: (json['toolName'] as String?)?.trim() ?? '',
      toolCallId: (json['toolCallId'] as String?)?.trim() ?? '',
      message: (json['message'] as String?)?.trim() ?? '',
      data: (json['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }

  factory AssistantToolResultRow.fromTraceEvent(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    return AssistantToolResultRow(
      toolName: (data['toolName'] as String?)?.trim() ?? '',
      toolCallId: event.toolCallId ?? '',
      message: event.message,
      data: data,
    );
  }
}
