import '../operation_request_payload.dart';
import '../generated/search_feedback_event_type.g.dart';
part '../generated/requests/search/search_feedback_contracts.requests.g.dart';

final class SearchFeedbackAck {
  const SearchFeedbackAck({required this.accepted});

  final bool accepted;
}

abstract interface class SearchFeedbackCommandWriter {
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  );
}

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
