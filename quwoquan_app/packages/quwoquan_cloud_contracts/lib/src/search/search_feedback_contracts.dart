import '../operation_request_payload.dart';

/// SearchFeedbackFact 的 typed append 契约：
/// 事实按 (searchRequestId, eventType, objectId) 语义键服务端去重，重放安全。
final class ReportSearchFeedbackCommand {
  ReportSearchFeedbackCommand({
    required String searchRequestId,
    required String eventType,
    String? objectId,
    String? target,
    this.rankPosition,
    String? referralSource,
    String? feedRequestId,
    this.dwellMs,
  }) : searchRequestId = _required(searchRequestId, 'searchRequestId'),
       eventType = _requiredEventType(eventType),
       objectId = _optional(objectId),
       target = _optional(target),
       referralSource = _optional(referralSource),
       feedRequestId = _optional(feedRequestId);

  final String searchRequestId;
  final String eventType;
  final String? objectId;
  final String? target;
  final int? rankPosition;
  final String? referralSource;
  final String? feedRequestId;
  final int? dwellMs;

  static const Set<String> allowedEventTypes = <String>{
    'impression',
    'click',
    'dwell',
    'refine',
    'zero_result',
    'degrade',
  };
}

final class SearchFeedbackAck {
  const SearchFeedbackAck({required this.accepted});

  final bool accepted;
}

abstract interface class SearchFeedbackCommandWriter {
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  );
}

CloudOperationRequestPayload encodeReportSearchFeedbackCommand(
  ReportSearchFeedbackCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'searchRequestId': command.searchRequestId,
    'eventType': command.eventType,
    'objectId': ?command.objectId,
    'target': ?command.target,
    'rankPosition': ?command.rankPosition,
    'referralSource': ?command.referralSource,
    'feedRequestId': ?command.feedRequestId,
    'dwellMs': ?command.dwellMs,
  },
);

SearchFeedbackAck decodeSearchFeedbackAck(Object? value) {
  if (value is! Map) {
    throw const FormatException('SearchFeedbackAck must be an object');
  }
  final accepted = value['accepted'];
  return SearchFeedbackAck(accepted: accepted == true);
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String _requiredEventType(String value) {
  final normalized = value.trim();
  if (!ReportSearchFeedbackCommand.allowedEventTypes.contains(normalized)) {
    throw ArgumentError.value(value, 'eventType', 'unsupported event type');
  }
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
