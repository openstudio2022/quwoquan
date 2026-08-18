// Code generated from canonical cross-domain enums. DO NOT EDIT.
// ContractGraph SHA256: d68dfe12604d5c5225ba691373427dc83221ebf23391ec8cf7c2432f88b2a76a

library;

enum AssistantUsePolicy {
  inherit("inherit"),
  exclude("exclude");

  const AssistantUsePolicy(this.wireName);

  final String wireName;

  static AssistantUsePolicy fromWire(Object? value, String path) {
    return switch (value) {
      "inherit" => AssistantUsePolicy.inherit,
      "exclude" => AssistantUsePolicy.exclude,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum BehaviorEventType {
  impression("impression"),
  click("click"),
  dwell("dwell"),
  like("like"),
  dislike("dislike"),
  undoDislike("undo_dislike"),
  hideAuthor("hide_author"),
  hideContentType("hide_content_type"),
  report("report"),
  share("share"),
  comment("comment"),
  intersectionExpand("intersection_expand"),
  intersectionFeedback("intersection_feedback"),
  wishlistAdd("wishlist_add"),
  wishlistRemove("wishlist_remove"),
  skip("skip"),
  follow("follow"),
  joinCircle("join_circle"),
  leaveCircle("leave_circle"),
  addContact("add_contact"),
  authorView("author_view"),
  entityPageView("entity_page_view"),
  tagClick("tag_click"),
  contentDepth("content_depth"),
  playProgress("play_progress"),
  effectivePlay("effective_play"),
  assistantInterest("assistant_interest"),
  onboardingInterest("onboarding_interest");

  const BehaviorEventType(this.wireName);

  final String wireName;

  static BehaviorEventType fromWire(Object? value, String path) {
    return switch (value) {
      "impression" => BehaviorEventType.impression,
      "click" => BehaviorEventType.click,
      "dwell" => BehaviorEventType.dwell,
      "like" => BehaviorEventType.like,
      "dislike" => BehaviorEventType.dislike,
      "undo_dislike" => BehaviorEventType.undoDislike,
      "hide_author" => BehaviorEventType.hideAuthor,
      "hide_content_type" => BehaviorEventType.hideContentType,
      "report" => BehaviorEventType.report,
      "share" => BehaviorEventType.share,
      "comment" => BehaviorEventType.comment,
      "intersection_expand" => BehaviorEventType.intersectionExpand,
      "intersection_feedback" => BehaviorEventType.intersectionFeedback,
      "wishlist_add" => BehaviorEventType.wishlistAdd,
      "wishlist_remove" => BehaviorEventType.wishlistRemove,
      "skip" => BehaviorEventType.skip,
      "follow" => BehaviorEventType.follow,
      "join_circle" => BehaviorEventType.joinCircle,
      "leave_circle" => BehaviorEventType.leaveCircle,
      "add_contact" => BehaviorEventType.addContact,
      "author_view" => BehaviorEventType.authorView,
      "entity_page_view" => BehaviorEventType.entityPageView,
      "tag_click" => BehaviorEventType.tagClick,
      "content_depth" => BehaviorEventType.contentDepth,
      "play_progress" => BehaviorEventType.playProgress,
      "effective_play" => BehaviorEventType.effectivePlay,
      "assistant_interest" => BehaviorEventType.assistantInterest,
      "onboarding_interest" => BehaviorEventType.onboardingInterest,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageType {
  vehicle("vehicle"),
  hotel("hotel"),
  restaurant("restaurant"),
  sight("sight"),
  university("university"),
  school("school"),
  travelPhoto("travel_photo"),
  museum("museum"),
  heritageSite("heritage_site"),
  ancientTown("ancient_town"),
  religiousSite("religious_site"),
  checkInSpot("check_in_spot"),
  naturalLandscape("natural_landscape"),
  park("park"),
  hotSpring("hot_spring"),
  themePark("theme_park"),
  transportHub("transport_hub"),
  city("city"),
  route("route"),
  photoSpot("photo_spot"),
  gear("gear");

  const HomepageType(this.wireName);

  final String wireName;

  static HomepageType fromWire(Object? value, String path) {
    return switch (value) {
      "vehicle" => HomepageType.vehicle,
      "hotel" => HomepageType.hotel,
      "restaurant" => HomepageType.restaurant,
      "sight" => HomepageType.sight,
      "university" => HomepageType.university,
      "school" => HomepageType.school,
      "travel_photo" => HomepageType.travelPhoto,
      "museum" => HomepageType.museum,
      "heritage_site" => HomepageType.heritageSite,
      "ancient_town" => HomepageType.ancientTown,
      "religious_site" => HomepageType.religiousSite,
      "check_in_spot" => HomepageType.checkInSpot,
      "natural_landscape" => HomepageType.naturalLandscape,
      "park" => HomepageType.park,
      "hot_spring" => HomepageType.hotSpring,
      "theme_park" => HomepageType.themePark,
      "transport_hub" => HomepageType.transportHub,
      "city" => HomepageType.city,
      "route" => HomepageType.route,
      "photo_spot" => HomepageType.photoSpot,
      "gear" => HomepageType.gear,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum RelationshipState {
  self("self"),
  notFollowing("not_following"),
  following("following"),
  followedBy("followed_by"),
  mutual("mutual");

  const RelationshipState(this.wireName);

  final String wireName;

  static RelationshipState fromWire(Object? value, String path) {
    return switch (value) {
      "self" => RelationshipState.self,
      "not_following" => RelationshipState.notFollowing,
      "following" => RelationshipState.following,
      "followed_by" => RelationshipState.followedBy,
      "mutual" => RelationshipState.mutual,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

