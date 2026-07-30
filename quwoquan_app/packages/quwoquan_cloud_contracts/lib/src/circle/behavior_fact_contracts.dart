import '../operation_request_payload.dart';
part '../generated/requests/circle/behavior_fact_contracts.requests.g.dart';

enum CircleBehaviorEventType {
  impression('impression'),
  click('click'),
  dwell('dwell'),
  like('like'),
  dislike('dislike'),
  undoDislike('undo_dislike'),
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
  leaveCircle('leave_circle'),
  addContact('add_contact'),
  authorView('author_view'),
  entityPageView('entity_page_view'),
  tagClick('tag_click'),
  contentDepth('content_depth'),
  playProgress('play_progress'),
  effectivePlay('effective_play'),
  assistantInterest('assistant_interest'),
  onboardingInterest('onboarding_interest');

  const CircleBehaviorEventType(this.wireValue);
  final String wireValue;
}

abstract interface class CircleBehaviorFactWriter {
  Future<void> append(AppendCircleBehaviorFactCommand command);
}

void decodeEmptyCircleBehaviorFactResponse(Object? value) {
  if (value != null) {
    throw const FormatException(
      'CircleBehaviorFact append response must be empty',
    );
  }
}
