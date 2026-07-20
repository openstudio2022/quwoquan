import '../operation_request_payload.dart';

/// TagFeedback 不可变反馈事实的 typed append 契约。
/// 同一 actor 的相同 Idempotency-Key 重放返回首次结果（服务端唯一索引去重）。
final class ReportTagFeedbackCommand {
  ReportTagFeedbackCommand({
    required String tagRef,
    required String action,
    String? context,
  }) : tagRef = _required(tagRef, 'tagRef'),
       action = _requiredAction(action),
       context = _optional(context);

  final String tagRef;
  final String action;
  final String? context;

  static const Set<String> allowedActions = <String>{
    'click',
    'ignore',
    'correct',
  };
}

final class TagFeedbackAck {
  const TagFeedbackAck({required this.accepted});

  final bool accepted;
}

abstract interface class TagFeedbackCommandWriter {
  Future<TagFeedbackAck> reportTagFeedback(ReportTagFeedbackCommand command);
}

CloudOperationRequestPayload encodeReportTagFeedbackCommand(
  ReportTagFeedbackCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'tagRef': command.tagRef,
    'action': command.action,
    'context': ?command.context,
  },
);

TagFeedbackAck decodeTagFeedbackAck(Object? value) {
  if (value is! Map) {
    throw const FormatException('TagFeedbackAck must be an object');
  }
  return TagFeedbackAck(accepted: value['accepted'] == true);
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String _requiredAction(String value) {
  final normalized = value.trim();
  if (!ReportTagFeedbackCommand.allowedActions.contains(normalized)) {
    throw ArgumentError.value(value, 'action', 'unsupported feedback action');
  }
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
