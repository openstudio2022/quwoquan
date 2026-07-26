import '../operation_request_payload.dart';
import '../generated/search_feedback_event_type.g.dart';

/// SearchFeedbackFact 的 typed append 契约：
/// 事实按 (searchRequestId, eventType, objectId) 语义键服务端去重，重放安全。
final class ReportSearchFeedbackCommand {
  ReportSearchFeedbackCommand({
    required String searchRequestId,
    required this.eventType,
    String? objectId,
    String? target,
    this.rankPosition,
    String? referralSource,
    String? feedRequestId,
    int? dwellMs,
  }) : searchRequestId = _required(searchRequestId, 'searchRequestId'),
       objectId = _optional(objectId),
       target = _optional(target),
       referralSource = _optional(referralSource),
       feedRequestId = _optional(feedRequestId),
       dwellMs = _validatedDwellMs(eventType, dwellMs);

  final String searchRequestId;
  final SearchFeedbackEventType eventType;
  final String? objectId;
  final String? target;
  final int? rankPosition;
  final String? referralSource;
  final String? feedRequestId;
  final int? dwellMs;
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
    'eventType': command.eventType.wireValue,
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
  if (accepted is! bool) {
    throw const FormatException('SearchFeedbackAck.accepted must be a bool');
  }
  return SearchFeedbackAck(accepted: accepted);
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

int? _validatedDwellMs(SearchFeedbackEventType eventType, int? dwellMs) {
  if (eventType == SearchFeedbackEventType.dwell) {
    if (dwellMs == null || dwellMs <= 0) {
      throw ArgumentError.value(
        dwellMs,
        'dwellMs',
        'dwell feedback requires a positive duration',
      );
    }
    return dwellMs;
  }
  if (dwellMs != null) {
    throw ArgumentError.value(
      dwellMs,
      'dwellMs',
      'only dwell feedback may carry a duration',
    );
  }
  return null;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
