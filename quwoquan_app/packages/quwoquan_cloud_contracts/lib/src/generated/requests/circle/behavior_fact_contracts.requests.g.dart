// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/behavior_fact_contracts.dart';

final class AppendCircleBehaviorFactCommand {
  AppendCircleBehaviorFactCommand({
    required String circleId,
    required CircleBehaviorEventType eventType,
  }) : circleId = circleId.trim(),
       eventType = eventType {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;
  final CircleBehaviorEventType eventType;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "eventType": switch (this.eventType) { CircleBehaviorEventType.impression => "impression", CircleBehaviorEventType.click => "click", CircleBehaviorEventType.dwell => "dwell", CircleBehaviorEventType.like => "like", CircleBehaviorEventType.dislike => "dislike", CircleBehaviorEventType.undoDislike => "undo_dislike", CircleBehaviorEventType.hideAuthor => "hide_author", CircleBehaviorEventType.hideContentType => "hide_content_type", CircleBehaviorEventType.report => "report", CircleBehaviorEventType.share => "share", CircleBehaviorEventType.comment => "comment", CircleBehaviorEventType.intersectionExpand => "intersection_expand", CircleBehaviorEventType.intersectionFeedback => "intersection_feedback", CircleBehaviorEventType.wishlistAdd => "wishlist_add", CircleBehaviorEventType.wishlistRemove => "wishlist_remove", CircleBehaviorEventType.skip => "skip", CircleBehaviorEventType.follow => "follow", CircleBehaviorEventType.joinCircle => "join_circle", CircleBehaviorEventType.leaveCircle => "leave_circle", CircleBehaviorEventType.addContact => "add_contact", CircleBehaviorEventType.authorView => "author_view", CircleBehaviorEventType.entityPageView => "entity_page_view", CircleBehaviorEventType.tagClick => "tag_click", CircleBehaviorEventType.contentDepth => "content_depth", CircleBehaviorEventType.playProgress => "play_progress", CircleBehaviorEventType.effectivePlay => "effective_play", CircleBehaviorEventType.assistantInterest => "assistant_interest", CircleBehaviorEventType.onboardingInterest => "onboarding_interest", },
  };
}

CloudOperationRequestPayload encodeCircleCircleBehaviorFactReportCircleBehaviorGeneratedRequest(AppendCircleBehaviorFactCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "circleId": request.circleId,
      "eventType": switch (request.eventType) { CircleBehaviorEventType.impression => "impression", CircleBehaviorEventType.click => "click", CircleBehaviorEventType.dwell => "dwell", CircleBehaviorEventType.like => "like", CircleBehaviorEventType.dislike => "dislike", CircleBehaviorEventType.undoDislike => "undo_dislike", CircleBehaviorEventType.hideAuthor => "hide_author", CircleBehaviorEventType.hideContentType => "hide_content_type", CircleBehaviorEventType.report => "report", CircleBehaviorEventType.share => "share", CircleBehaviorEventType.comment => "comment", CircleBehaviorEventType.intersectionExpand => "intersection_expand", CircleBehaviorEventType.intersectionFeedback => "intersection_feedback", CircleBehaviorEventType.wishlistAdd => "wishlist_add", CircleBehaviorEventType.wishlistRemove => "wishlist_remove", CircleBehaviorEventType.skip => "skip", CircleBehaviorEventType.follow => "follow", CircleBehaviorEventType.joinCircle => "join_circle", CircleBehaviorEventType.leaveCircle => "leave_circle", CircleBehaviorEventType.addContact => "add_contact", CircleBehaviorEventType.authorView => "author_view", CircleBehaviorEventType.entityPageView => "entity_page_view", CircleBehaviorEventType.tagClick => "tag_click", CircleBehaviorEventType.contentDepth => "content_depth", CircleBehaviorEventType.playProgress => "play_progress", CircleBehaviorEventType.effectivePlay => "effective_play", CircleBehaviorEventType.assistantInterest => "assistant_interest", CircleBehaviorEventType.onboardingInterest => "onboarding_interest", },
    },
  );
}

