// Code generated from the canonical intersection registry. DO NOT EDIT.
// Source: recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml

library;

enum IntersectionDimension {
  identity("identity"),
  location("location"),
  content("content"),
  interest("interest"),
  relationship("relationship");

  const IntersectionDimension(this.wireName);

  final String wireName;

  static IntersectionDimension fromWire(Object? value, String path) {
    return switch (value) {
      "identity" => IntersectionDimension.identity,
      "location" => IntersectionDimension.location,
      "content" => IntersectionDimension.content,
      "interest" => IntersectionDimension.interest,
      "relationship" => IntersectionDimension.relationship,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionLifecycleState {
  newValue("new"),
  strengthened("strengthened"),
  stable("stable"),
  weakened("weakened"),
  reactivated("reactivated"),
  archived("archived"),
  expired("expired");

  const IntersectionLifecycleState(this.wireName);

  final String wireName;

  static IntersectionLifecycleState fromWire(Object? value, String path) {
    return switch (value) {
      "new" => IntersectionLifecycleState.newValue,
      "strengthened" => IntersectionLifecycleState.strengthened,
      "stable" => IntersectionLifecycleState.stable,
      "weakened" => IntersectionLifecycleState.weakened,
      "reactivated" => IntersectionLifecycleState.reactivated,
      "archived" => IntersectionLifecycleState.archived,
      "expired" => IntersectionLifecycleState.expired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionVertical {
  general("general"),
  travelPhotography("travel_photography");

  const IntersectionVertical(this.wireName);

  final String wireName;

  static IntersectionVertical fromWire(Object? value, String path) {
    return switch (value) {
      "general" => IntersectionVertical.general,
      "travel_photography" => IntersectionVertical.travelPhotography,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionMoment {
  retrospective("retrospective"),
  current("current"),
  prospective("prospective");

  const IntersectionMoment(this.wireName);

  final String wireName;

  static IntersectionMoment fromWire(Object? value, String path) {
    return switch (value) {
      "retrospective" => IntersectionMoment.retrospective,
      "current" => IntersectionMoment.current,
      "prospective" => IntersectionMoment.prospective,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionGateKey {
  login("login"),
  realName("realName"),
  minorMode("minorMode"),
  blocked("blocked"),
  greetPreference("greetPreference"),
  mutualConsent("mutualConsent"),
  fuzzyLocation("fuzzyLocation"),
  rateLimit("rateLimit");

  const IntersectionGateKey(this.wireName);

  final String wireName;

  static IntersectionGateKey fromWire(Object? value, String path) {
    return switch (value) {
      "login" => IntersectionGateKey.login,
      "realName" => IntersectionGateKey.realName,
      "minorMode" => IntersectionGateKey.minorMode,
      "blocked" => IntersectionGateKey.blocked,
      "greetPreference" => IntersectionGateKey.greetPreference,
      "mutualConsent" => IntersectionGateKey.mutualConsent,
      "fuzzyLocation" => IntersectionGateKey.fuzzyLocation,
      "rateLimit" => IntersectionGateKey.rateLimit,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionActionDispatch {
  assistant("assistant"),
  navigate("navigate"),
  message("message"),
  gathering("gathering");

  const IntersectionActionDispatch(this.wireName);

  final String wireName;

  static IntersectionActionDispatch fromWire(Object? value, String path) {
    return switch (value) {
      "assistant" => IntersectionActionDispatch.assistant,
      "navigate" => IntersectionActionDispatch.navigate,
      "message" => IntersectionActionDispatch.message,
      "gathering" => IntersectionActionDispatch.gathering,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionActionKey {
  askAssistant("ask_assistant"),
  createFollowup("create_followup"),
  followObject("follow_object"),
  followPerson("follow_person"),
  greetPerson("greet_person"),
  joinCircle("join_circle"),
  messagePerson("message_person"),
  openContent("open_content"),
  openDiscussion("open_discussion"),
  openObject("open_object"),
  openRoute("open_route"),
  startGathering("start_gathering"),
  viewSharedPeople("view_shared_people");

  const IntersectionActionKey(this.wireName);

  final String wireName;

  static IntersectionActionKey fromWire(Object? value, String path) {
    return switch (value) {
      "ask_assistant" => IntersectionActionKey.askAssistant,
      "create_followup" => IntersectionActionKey.createFollowup,
      "follow_object" => IntersectionActionKey.followObject,
      "follow_person" => IntersectionActionKey.followPerson,
      "greet_person" => IntersectionActionKey.greetPerson,
      "join_circle" => IntersectionActionKey.joinCircle,
      "message_person" => IntersectionActionKey.messagePerson,
      "open_content" => IntersectionActionKey.openContent,
      "open_discussion" => IntersectionActionKey.openDiscussion,
      "open_object" => IntersectionActionKey.openObject,
      "open_route" => IntersectionActionKey.openRoute,
      "start_gathering" => IntersectionActionKey.startGathering,
      "view_shared_people" => IntersectionActionKey.viewSharedPeople,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionActionTier {
  light("light"),
  heavy("heavy");

  const IntersectionActionTier(this.wireName);

  final String wireName;

  static IntersectionActionTier fromWire(Object? value, String path) {
    return switch (value) {
      "light" => IntersectionActionTier.light,
      "heavy" => IntersectionActionTier.heavy,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum IntersectionObjectKind {
  person("person"),
  circle("circle"),
  school("school"),
  place("place"),
  enterprise("enterprise"),
  route("route"),
  photoSpot("photo_spot"),
  gear("gear"),
  content("content"),
  entity("entity"),
  tag("tag"),
  gathering("gathering");

  const IntersectionObjectKind(this.wireName);

  final String wireName;

  static IntersectionObjectKind fromWire(Object? value, String path) {
    return switch (value) {
      "person" => IntersectionObjectKind.person,
      "circle" => IntersectionObjectKind.circle,
      "school" => IntersectionObjectKind.school,
      "place" => IntersectionObjectKind.place,
      "enterprise" => IntersectionObjectKind.enterprise,
      "route" => IntersectionObjectKind.route,
      "photo_spot" => IntersectionObjectKind.photoSpot,
      "gear" => IntersectionObjectKind.gear,
      "content" => IntersectionObjectKind.content,
      "entity" => IntersectionObjectKind.entity,
      "tag" => IntersectionObjectKind.tag,
      "gathering" => IntersectionObjectKind.gathering,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}
