import '../operation_request_payload.dart';
part '../generated/requests/tag/tag_feedback_fact_contracts.requests.g.dart';

enum TagFeedbackAction {
  click('click'),
  ignore('ignore'),
  correct('correct'),
  dislike('dislike');

  const TagFeedbackAction(this.wireValue);

  final String wireValue;
}

final class TagFeedbackAck {
  const TagFeedbackAck({required this.accepted});

  final bool accepted;
}

abstract interface class TagFeedbackCommandWriter {
  Future<TagFeedbackAck> reportTagFeedback(ReportTagFeedbackCommand command);
}

TagFeedbackAck decodeTagFeedbackAck(Object? value) {
  if (value is! Map) {
    throw const FormatException('TagFeedbackAck must be an object');
  }
  final accepted = value['accepted'];
  if (accepted is! bool) {
    throw const FormatException('TagFeedbackAck.accepted must be a bool');
  }
  return TagFeedbackAck(accepted: accepted);
}
