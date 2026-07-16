import '../operation_request_payload.dart';

enum CircleBehaviorEventType {
  impression('impression'),
  click('click'),
  dwell('dwell'),
  like('like'),
  dislike('dislike'),
  hideAuthor('hide_author'),
  hideContentType('hide_content_type'),
  report('report'),
  share('share'),
  comment('comment'),
  intersectionExpand('intersection_expand'),
  intersectionFeedback('intersection_feedback'),
  wishlistAdd('wishlist_add'),
  wishlistRemove('wishlist_remove'),
  skip('skip'),
  follow('follow'),
  joinCircle('join_circle'),
  addContact('add_contact'),
  authorView('author_view'),
  tagClick('tag_click'),
  contentDepth('content_depth'),
  playProgress('play_progress'),
  assistantInterest('assistant_interest');

  const CircleBehaviorEventType(this.wireValue);
  final String wireValue;
}

final class AppendCircleBehaviorFactCommand {
  AppendCircleBehaviorFactCommand({
    required String circleId,
    required this.eventType,
  }) : circleId = _required(circleId, 'circleId');

  final String circleId;
  final CircleBehaviorEventType eventType;
}

abstract interface class CircleBehaviorFactWriter {
  Future<void> append(AppendCircleBehaviorFactCommand command);
}

CloudOperationRequestPayload encodeAppendCircleBehaviorFactCommand(
  AppendCircleBehaviorFactCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'circleId': command.circleId,
    'eventType': command.eventType.wireValue,
  },
);

void decodeEmptyCircleBehaviorFactResponse(Object? value) {
  if (value != null) {
    throw const FormatException(
      'CircleBehaviorFact append response must be empty',
    );
  }
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}
