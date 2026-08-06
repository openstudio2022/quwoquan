// Code generated from the canonical intersection registry. DO NOT EDIT.
// Source: recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show IntersectionActionDispatch, IntersectionActionKey, IntersectionActionTier, IntersectionGateKey, IntersectionObjectKind;

final class IntersectionActionPolicy {
  const IntersectionActionPolicy({
    required this.key,
    required this.tier,
    required this.requiredGates,
    required this.dispatch,
  });

  final IntersectionActionKey key;
  final IntersectionActionTier tier;
  final Set<IntersectionGateKey> requiredGates;
  final IntersectionActionDispatch dispatch;

  bool get isAssistant => dispatch == IntersectionActionDispatch.assistant;
  bool get isGathering => dispatch == IntersectionActionDispatch.gathering;

  static IntersectionActionPolicy of(IntersectionActionKey key) =>
      intersectionActionPolicies[key]!;
}

const Map<IntersectionActionKey, IntersectionActionPolicy>
    intersectionActionPolicies = <IntersectionActionKey, IntersectionActionPolicy>{
  IntersectionActionKey.askAssistant: IntersectionActionPolicy(
    key: IntersectionActionKey.askAssistant,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{},
    dispatch: IntersectionActionDispatch.assistant,
  ),
  IntersectionActionKey.createFollowup: IntersectionActionPolicy(
    key: IntersectionActionKey.createFollowup,
    tier: IntersectionActionTier.heavy,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login, IntersectionGateKey.realName},
    dispatch: IntersectionActionDispatch.assistant,
  ),
  IntersectionActionKey.followObject: IntersectionActionPolicy(
    key: IntersectionActionKey.followObject,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.followPerson: IntersectionActionPolicy(
    key: IntersectionActionKey.followPerson,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.greetPerson: IntersectionActionPolicy(
    key: IntersectionActionKey.greetPerson,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login, IntersectionGateKey.greetPreference, IntersectionGateKey.blocked},
    dispatch: IntersectionActionDispatch.message,
  ),
  IntersectionActionKey.joinCircle: IntersectionActionPolicy(
    key: IntersectionActionKey.joinCircle,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.messagePerson: IntersectionActionPolicy(
    key: IntersectionActionKey.messagePerson,
    tier: IntersectionActionTier.heavy,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login, IntersectionGateKey.mutualConsent, IntersectionGateKey.blocked, IntersectionGateKey.rateLimit},
    dispatch: IntersectionActionDispatch.message,
  ),
  IntersectionActionKey.openContent: IntersectionActionPolicy(
    key: IntersectionActionKey.openContent,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.openDiscussion: IntersectionActionPolicy(
    key: IntersectionActionKey.openDiscussion,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.openObject: IntersectionActionPolicy(
    key: IntersectionActionKey.openObject,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.openRoute: IntersectionActionPolicy(
    key: IntersectionActionKey.openRoute,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{},
    dispatch: IntersectionActionDispatch.navigate,
  ),
  IntersectionActionKey.startGathering: IntersectionActionPolicy(
    key: IntersectionActionKey.startGathering,
    tier: IntersectionActionTier.heavy,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login, IntersectionGateKey.realName, IntersectionGateKey.minorMode, IntersectionGateKey.blocked, IntersectionGateKey.rateLimit},
    dispatch: IntersectionActionDispatch.gathering,
  ),
  IntersectionActionKey.viewSharedPeople: IntersectionActionPolicy(
    key: IntersectionActionKey.viewSharedPeople,
    tier: IntersectionActionTier.light,
    requiredGates: <IntersectionGateKey>{IntersectionGateKey.login},
    dispatch: IntersectionActionDispatch.navigate,
  ),
};

const Map<IntersectionObjectKind, String> intersectionRouteIdByObjectKind =
    <IntersectionObjectKind, String>{
  IntersectionObjectKind.person: "userProfile",
  IntersectionObjectKind.circle: "circleDetail",
  IntersectionObjectKind.school: "homepageDetail",
  IntersectionObjectKind.place: "homepageDetail",
  IntersectionObjectKind.enterprise: "homepageDetail",
  IntersectionObjectKind.route: "homepageDetail",
  IntersectionObjectKind.photoSpot: "homepageDetail",
  IntersectionObjectKind.gear: "homepageDetail",
  IntersectionObjectKind.content: "workBrowser",
  IntersectionObjectKind.entity: "homepageDetail",
  IntersectionObjectKind.gathering: "gatheringDetail",
};

String intersectionRouteIdForObjectKind(IntersectionObjectKind kind) =>
    intersectionRouteIdByObjectKind[kind] ?? '';

IntersectionObjectKind? intersectionObjectKindForObjectType(
  String? objectType,
) {
  return switch (objectType?.trim()) {
    "ancient_town" => IntersectionObjectKind.place,
    "brand" => IntersectionObjectKind.enterprise,
    "check_in_spot" => IntersectionObjectKind.place,
    "circle" => IntersectionObjectKind.circle,
    "city" => IntersectionObjectKind.place,
    "company" => IntersectionObjectKind.enterprise,
    "enterprise" => IntersectionObjectKind.enterprise,
    "entity" => IntersectionObjectKind.place,
    "gear" => IntersectionObjectKind.gear,
    "heritage_site" => IntersectionObjectKind.place,
    "homepage" => IntersectionObjectKind.place,
    "hot_spring" => IntersectionObjectKind.place,
    "hotel" => IntersectionObjectKind.place,
    "museum" => IntersectionObjectKind.place,
    "natural_landscape" => IntersectionObjectKind.place,
    "park" => IntersectionObjectKind.place,
    "person" => IntersectionObjectKind.person,
    "photo_spot" => IntersectionObjectKind.photoSpot,
    "place" => IntersectionObjectKind.place,
    "religious_site" => IntersectionObjectKind.place,
    "restaurant" => IntersectionObjectKind.place,
    "route" => IntersectionObjectKind.route,
    "school" => IntersectionObjectKind.school,
    "sight" => IntersectionObjectKind.place,
    "theme_park" => IntersectionObjectKind.place,
    "transport_hub" => IntersectionObjectKind.place,
    "travel_photo" => IntersectionObjectKind.place,
    "university" => IntersectionObjectKind.school,
    "user" => IntersectionObjectKind.person,
    "vehicle" => IntersectionObjectKind.gear,
    _ => null,
  };
}
