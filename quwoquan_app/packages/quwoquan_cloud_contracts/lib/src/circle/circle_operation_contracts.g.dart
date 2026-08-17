// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 31a5d2ebc0bdd89d6d8160a349ad3a93782574b2abc17e5fb44b34c1b5720c1a

library;

import '../operation_request_payload.dart';
import "../generated/shared_operation_enums.g.dart";
import "../recommendation/recommendation_operation_contracts.g.dart";

export "../generated/shared_operation_enums.g.dart";
export "../recommendation/recommendation_operation_contracts.g.dart";

part '../generated/requests/circle/circle_operation_contracts.g.requests.g.dart';

enum CircleDiscoveryFeedScope {
  recommended("recommended"),
  mine("mine");

  const CircleDiscoveryFeedScope(this.wireName);

  final String wireName;

  static CircleDiscoveryFeedScope fromWire(Object? value, String path) {
    return switch (value) {
      "recommended" => CircleDiscoveryFeedScope.recommended,
      "mine" => CircleDiscoveryFeedScope.mine,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleDisplaySubjectType {
  circle("circle"),
  school("school"),
  college("college"),
  grade("grade"),
  classroom("classroom"),
  company("company"),
  department("department"),
  team("team");

  const CircleDisplaySubjectType(this.wireName);

  final String wireName;

  static CircleDisplaySubjectType fromWire(Object? value, String path) {
    return switch (value) {
      "circle" => CircleDisplaySubjectType.circle,
      "school" => CircleDisplaySubjectType.school,
      "college" => CircleDisplaySubjectType.college,
      "grade" => CircleDisplaySubjectType.grade,
      "classroom" => CircleDisplaySubjectType.classroom,
      "company" => CircleDisplaySubjectType.company,
      "department" => CircleDisplaySubjectType.department,
      "team" => CircleDisplaySubjectType.team,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleFileStatus {
  active("active"),
  deleted("deleted");

  const CircleFileStatus(this.wireName);

  final String wireName;

  static CircleFileStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => CircleFileStatus.active,
      "deleted" => CircleFileStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleFileType {
  file("file"),
  folder("folder");

  const CircleFileType(this.wireName);

  final String wireName;

  static CircleFileType fromWire(Object? value, String path) {
    return switch (value) {
      "file" => CircleFileType.file,
      "folder" => CircleFileType.folder,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupJoinPolicy {
  applyOnly("apply_only"),
  inviteOnly("invite_only");

  const CircleGroupJoinPolicy(this.wireName);

  final String wireName;

  static CircleGroupJoinPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "apply_only" => CircleGroupJoinPolicy.applyOnly,
      "invite_only" => CircleGroupJoinPolicy.inviteOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupMembershipRole {
  owner("owner"),
  manager("manager"),
  member("member");

  const CircleGroupMembershipRole(this.wireName);

  final String wireName;

  static CircleGroupMembershipRole fromWire(Object? value, String path) {
    return switch (value) {
      "owner" => CircleGroupMembershipRole.owner,
      "manager" => CircleGroupMembershipRole.manager,
      "member" => CircleGroupMembershipRole.member,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupMembershipState {
  pending("pending"),
  active("active"),
  rejected("rejected"),
  left("left"),
  removed("removed");

  const CircleGroupMembershipState(this.wireName);

  final String wireName;

  static CircleGroupMembershipState fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => CircleGroupMembershipState.pending,
      "active" => CircleGroupMembershipState.active,
      "rejected" => CircleGroupMembershipState.rejected,
      "left" => CircleGroupMembershipState.left,
      "removed" => CircleGroupMembershipState.removed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupStatus {
  active("active"),
  archived("archived");

  const CircleGroupStatus(this.wireName);

  final String wireName;

  static CircleGroupStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => CircleGroupStatus.active,
      "archived" => CircleGroupStatus.archived,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupType {
  publicGroup("public_group"),
  selfBuilt("self_built"),
  orgNode("org_node");

  const CircleGroupType(this.wireName);

  final String wireName;

  static CircleGroupType fromWire(Object? value, String path) {
    return switch (value) {
      "public_group" => CircleGroupType.publicGroup,
      "self_built" => CircleGroupType.selfBuilt,
      "org_node" => CircleGroupType.orgNode,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleGroupVisibility {
  public("public"),
  private("private");

  const CircleGroupVisibility(this.wireName);

  final String wireName;

  static CircleGroupVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "public" => CircleGroupVisibility.public,
      "private" => CircleGroupVisibility.private,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleJoinPolicy {
  open("open"),
  approval("approval"),
  inviteOnly("invite_only");

  const CircleJoinPolicy(this.wireName);

  final String wireName;

  static CircleJoinPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "open" => CircleJoinPolicy.open,
      "approval" => CircleJoinPolicy.approval,
      "invite_only" => CircleJoinPolicy.inviteOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleKind {
  interest("interest"),
  organization("organization");

  const CircleKind(this.wireName);

  final String wireName;

  static CircleKind fromWire(Object? value, String path) {
    return switch (value) {
      "interest" => CircleKind.interest,
      "organization" => CircleKind.organization,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleMemberRole {
  owner("owner"),
  admin("admin"),
  member("member");

  const CircleMemberRole(this.wireName);

  final String wireName;

  static CircleMemberRole fromWire(Object? value, String path) {
    return switch (value) {
      "owner" => CircleMemberRole.owner,
      "admin" => CircleMemberRole.admin,
      "member" => CircleMemberRole.member,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleMembershipState {
  pending("pending"),
  active("active"),
  rejected("rejected"),
  left("left"),
  removed("removed");

  const CircleMembershipState(this.wireName);

  final String wireName;

  static CircleMembershipState fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => CircleMembershipState.pending,
      "active" => CircleMembershipState.active,
      "rejected" => CircleMembershipState.rejected,
      "left" => CircleMembershipState.left,
      "removed" => CircleMembershipState.removed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleSectionType {
  works("works"),
  members("members"),
  chat("chat"),
  storage("storage"),
  custom("custom");

  const CircleSectionType(this.wireName);

  final String wireName;

  static CircleSectionType fromWire(Object? value, String path) {
    return switch (value) {
      "works" => CircleSectionType.works,
      "members" => CircleSectionType.members,
      "chat" => CircleSectionType.chat,
      "storage" => CircleSectionType.storage,
      "custom" => CircleSectionType.custom,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleStatus {
  active("active"),
  archived("archived"),
  deleted("deleted");

  const CircleStatus(this.wireName);

  final String wireName;

  static CircleStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => CircleStatus.active,
      "archived" => CircleStatus.archived,
      "deleted" => CircleStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CircleVisibility {
  public("public"),
  private("private"),
  inviteOnly("invite_only");

  const CircleVisibility(this.wireName);

  final String wireName;

  static CircleVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "public" => CircleVisibility.public,
      "private" => CircleVisibility.private,
      "invite_only" => CircleVisibility.inviteOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringAdmissionControlStatus {
  open("open"),
  paused("paused");

  const GatheringAdmissionControlStatus(this.wireName);

  final String wireName;

  static GatheringAdmissionControlStatus fromWire(Object? value, String path) {
    return switch (value) {
      "open" => GatheringAdmissionControlStatus.open,
      "paused" => GatheringAdmissionControlStatus.paused,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringAdmissionPolicy {
  open("open"),
  approval("approval"),
  inviteOnly("invite_only");

  const GatheringAdmissionPolicy(this.wireName);

  final String wireName;

  static GatheringAdmissionPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "open" => GatheringAdmissionPolicy.open,
      "approval" => GatheringAdmissionPolicy.approval,
      "invite_only" => GatheringAdmissionPolicy.inviteOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringAdmissionState {
  accepting("accepting"),
  full("full"),
  paused("paused"),
  closed("closed");

  const GatheringAdmissionState(this.wireName);

  final String wireName;

  static GatheringAdmissionState fromWire(Object? value, String path) {
    return switch (value) {
      "accepting" => GatheringAdmissionState.accepting,
      "full" => GatheringAdmissionState.full,
      "paused" => GatheringAdmissionState.paused,
      "closed" => GatheringAdmissionState.closed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringApplicationQuestionKind {
  text("text"),
  singleSelect("single_select"),
  multiSelect("multi_select");

  const GatheringApplicationQuestionKind(this.wireName);

  final String wireName;

  static GatheringApplicationQuestionKind fromWire(Object? value, String path) {
    return switch (value) {
      "text" => GatheringApplicationQuestionKind.text,
      "single_select" => GatheringApplicationQuestionKind.singleSelect,
      "multi_select" => GatheringApplicationQuestionKind.multiSelect,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringApplicationReviewDecision {
  approve("approve"),
  reject("reject");

  const GatheringApplicationReviewDecision(this.wireName);

  final String wireName;

  static GatheringApplicationReviewDecision fromWire(Object? value, String path) {
    return switch (value) {
      "approve" => GatheringApplicationReviewDecision.approve,
      "reject" => GatheringApplicationReviewDecision.reject,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringAudiencePolicy {
  public("public"),
  unlisted("unlisted"),
  communityMembers("community_members"),
  inviteOnly("invite_only");

  const GatheringAudiencePolicy(this.wireName);

  final String wireName;

  static GatheringAudiencePolicy fromWire(Object? value, String path) {
    return switch (value) {
      "public" => GatheringAudiencePolicy.public,
      "unlisted" => GatheringAudiencePolicy.unlisted,
      "community_members" => GatheringAudiencePolicy.communityMembers,
      "invite_only" => GatheringAudiencePolicy.inviteOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringCostNotice {
  free("free"),
  estimated("estimated"),
  externalPaymentRequired("external_payment_required");

  const GatheringCostNotice(this.wireName);

  final String wireName;

  static GatheringCostNotice fromWire(Object? value, String path) {
    return switch (value) {
      "free" => GatheringCostNotice.free,
      "estimated" => GatheringCostNotice.estimated,
      "external_payment_required" => GatheringCostNotice.externalPaymentRequired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringHostSubjectKind {
  persona("persona"),
  entityHomepage("entity_homepage"),
  circle("circle");

  const GatheringHostSubjectKind(this.wireName);

  final String wireName;

  static GatheringHostSubjectKind fromWire(Object? value, String path) {
    return switch (value) {
      "persona" => GatheringHostSubjectKind.persona,
      "entity_homepage" => GatheringHostSubjectKind.entityHomepage,
      "circle" => GatheringHostSubjectKind.circle,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringLifecycleStatus {
  draft("draft"),
  published("published"),
  cancelled("cancelled"),
  completed("completed");

  const GatheringLifecycleStatus(this.wireName);

  final String wireName;

  static GatheringLifecycleStatus fromWire(Object? value, String path) {
    return switch (value) {
      "draft" => GatheringLifecycleStatus.draft,
      "published" => GatheringLifecycleStatus.published,
      "cancelled" => GatheringLifecycleStatus.cancelled,
      "completed" => GatheringLifecycleStatus.completed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringOrganizerRole {
  primaryOrganizer("primary_organizer"),
  coHost("co_host");

  const GatheringOrganizerRole(this.wireName);

  final String wireName;

  static GatheringOrganizerRole fromWire(Object? value, String path) {
    return switch (value) {
      "primary_organizer" => GatheringOrganizerRole.primaryOrganizer,
      "co_host" => GatheringOrganizerRole.coHost,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringOutcomeStatus {
  occurred("occurred"),
  didNotHappen("did_not_happen"),
  endedEarly("ended_early"),
  safetyTerminated("safety_terminated"),
  disputed("disputed"),
  unverified("unverified");

  const GatheringOutcomeStatus(this.wireName);

  final String wireName;

  static GatheringOutcomeStatus fromWire(Object? value, String path) {
    return switch (value) {
      "occurred" => GatheringOutcomeStatus.occurred,
      "did_not_happen" => GatheringOutcomeStatus.didNotHappen,
      "ended_early" => GatheringOutcomeStatus.endedEarly,
      "safety_terminated" => GatheringOutcomeStatus.safetyTerminated,
      "disputed" => GatheringOutcomeStatus.disputed,
      "unverified" => GatheringOutcomeStatus.unverified,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringParticipationState {
  invitedPending("invited_pending"),
  applicationPending("application_pending"),
  active("active"),
  closed("closed");

  const GatheringParticipationState(this.wireName);

  final String wireName;

  static GatheringParticipationState fromWire(Object? value, String path) {
    return switch (value) {
      "invited_pending" => GatheringParticipationState.invitedPending,
      "application_pending" => GatheringParticipationState.applicationPending,
      "active" => GatheringParticipationState.active,
      "closed" => GatheringParticipationState.closed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringPlaceDisclosure {
  exact("exact"),
  coarse("coarse"),
  afterJoin("after_join");

  const GatheringPlaceDisclosure(this.wireName);

  final String wireName;

  static GatheringPlaceDisclosure fromWire(Object? value, String path) {
    return switch (value) {
      "exact" => GatheringPlaceDisclosure.exact,
      "coarse" => GatheringPlaceDisclosure.coarse,
      "after_join" => GatheringPlaceDisclosure.afterJoin,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringPlaceMode {
  physical("physical"),
  online("online"),
  hybrid("hybrid");

  const GatheringPlaceMode(this.wireName);

  final String wireName;

  static GatheringPlaceMode fromWire(Object? value, String path) {
    return switch (value) {
      "physical" => GatheringPlaceMode.physical,
      "online" => GatheringPlaceMode.online,
      "hybrid" => GatheringPlaceMode.hybrid,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringRoomBindingStatus {
  pending("pending"),
  ready("ready"),
  failed("failed");

  const GatheringRoomBindingStatus(this.wireName);

  final String wireName;

  static GatheringRoomBindingStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => GatheringRoomBindingStatus.pending,
      "ready" => GatheringRoomBindingStatus.ready,
      "failed" => GatheringRoomBindingStatus.failed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringRosterDisclosure {
  countOnly("count_only"),
  joinedMembers("joined_members"),
  publicOptIn("public_opt_in");

  const GatheringRosterDisclosure(this.wireName);

  final String wireName;

  static GatheringRosterDisclosure fromWire(Object? value, String path) {
    return switch (value) {
      "count_only" => GatheringRosterDisclosure.countOnly,
      "joined_members" => GatheringRosterDisclosure.joinedMembers,
      "public_opt_in" => GatheringRosterDisclosure.publicOptIn,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringTemporalPhase {
  upcoming("upcoming"),
  inProgress("in_progress"),
  ended("ended");

  const GatheringTemporalPhase(this.wireName);

  final String wireName;

  static GatheringTemporalPhase fromWire(Object? value, String path) {
    return switch (value) {
      "upcoming" => GatheringTemporalPhase.upcoming,
      "in_progress" => GatheringTemporalPhase.inProgress,
      "ended" => GatheringTemporalPhase.ended,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum GatheringTimeDisclosure {
  exact("exact"),
  dateOnly("date_only"),
  afterJoin("after_join");

  const GatheringTimeDisclosure(this.wireName);

  final String wireName;

  static GatheringTimeDisclosure fromWire(Object? value, String path) {
    return switch (value) {
      "exact" => GatheringTimeDisclosure.exact,
      "date_only" => GatheringTimeDisclosure.dateOnly,
      "after_join" => GatheringTimeDisclosure.afterJoin,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OrganizationNodeType {
  generic("generic"),
  college("college"),
  grade("grade"),
  classroom("classroom"),
  department("department"),
  team("team");

  const OrganizationNodeType(this.wireName);

  final String wireName;

  static OrganizationNodeType fromWire(Object? value, String path) {
    return switch (value) {
      "generic" => OrganizationNodeType.generic,
      "college" => OrganizationNodeType.college,
      "grade" => OrganizationNodeType.grade,
      "classroom" => OrganizationNodeType.classroom,
      "department" => OrganizationNodeType.department,
      "team" => OrganizationNodeType.team,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class AppendResult {
  const AppendResult({
    required this.factId,
    required this.idempotentReplay,
  });

  final String factId;
  final bool idempotentReplay;

  factory AppendResult.fromWire(Map<String, Object?> map, [String path = "AppendResult"]) {
    _rejectUnknownFields(map, const <String>{"factId", "idempotentReplay"}, path);
    return AppendResult(
      factId: _requiredString(map["factId"], '$path.factId'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "factId": factId,
    "idempotentReplay": idempotentReplay,
  };
}

final class CanonicalObjectRef {
  const CanonicalObjectRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory CanonicalObjectRef.fromWire(Map<String, Object?> map, [String path = "CanonicalObjectRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return CanonicalObjectRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class Circle {
  const Circle({
    required this.id,
    required this.name,
    this.description,
    this.rulesText,
    this.welcomeMessage,
    this.coverUrl,
    this.iconUrl,
    required this.ownerId,
    this.ownerDisplayNameSnapshot,
    this.category,
    this.subCategory,
    this.tags,
    required this.memberCount,
    required this.postCount,
    required this.weeklyActiveCount,
    required this.version,
    required this.status,
    required this.visibility,
    required this.joinPolicy,
    required this.kind,
    required this.displaySubjectType,
    required this.followEnabled,
    this.defaultPublicGroupId,
    required this.autoSyncChat,
    this.sectionConfig,
    required this.storageUsedBytes,
    required this.storageQuotaBytes,
    this.domainId,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String ownerId;
  final String? ownerDisplayNameSnapshot;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final int version;
  final CircleStatus status;
  final CircleVisibility visibility;
  final CircleJoinPolicy joinPolicy;
  final CircleKind kind;
  final CircleDisplaySubjectType displaySubjectType;
  final bool followEnabled;
  final String? defaultPublicGroupId;
  final bool autoSyncChat;
  final List<CircleSectionConfig>? sectionConfig;
  final int storageUsedBytes;
  final int storageQuotaBytes;
  final String? domainId;
  final String? linkedHomepageId;
  final HomepageType? linkedHomepageType;
  final String? linkedHomepageTitle;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory Circle.fromWire(Map<String, Object?> map, [String path = "Circle"]) {
    _rejectUnknownFields(map, const <String>{"id", "name", "description", "rulesText", "welcomeMessage", "coverUrl", "iconUrl", "ownerId", "ownerDisplayNameSnapshot", "category", "subCategory", "tags", "memberCount", "postCount", "weeklyActiveCount", "version", "status", "visibility", "joinPolicy", "kind", "displaySubjectType", "followEnabled", "defaultPublicGroupId", "autoSyncChat", "sectionConfig", "storageUsedBytes", "storageQuotaBytes", "domainId", "linkedHomepageId", "linkedHomepageType", "linkedHomepageTitle", "createdAt", "updatedAt"}, path);
    return Circle(
      id: _requiredString(map["id"], '$path.id'),
      name: _requiredString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      rulesText: map["rulesText"] == null ? null : _requiredString(map["rulesText"], '$path.rulesText'),
      welcomeMessage: map["welcomeMessage"] == null ? null : _requiredString(map["welcomeMessage"], '$path.welcomeMessage'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      iconUrl: map["iconUrl"] == null ? null : _requiredString(map["iconUrl"], '$path.iconUrl'),
      ownerId: _requiredString(map["ownerId"], '$path.ownerId'),
      ownerDisplayNameSnapshot: map["ownerDisplayNameSnapshot"] == null ? null : _requiredString(map["ownerDisplayNameSnapshot"], '$path.ownerDisplayNameSnapshot'),
      category: map["category"] == null ? null : _requiredString(map["category"], '$path.category'),
      subCategory: map["subCategory"] == null ? null : _requiredString(map["subCategory"], '$path.subCategory'),
      tags: map["tags"] == null ? null : List<String>.unmodifiable(_requiredList(map["tags"], '$path.tags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tags' + '[${entry.key}]'))),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
      weeklyActiveCount: _requiredInt(map["weeklyActiveCount"], '$path.weeklyActiveCount'),
      version: _requiredInt(map["version"], '$path.version'),
      status: CircleStatus.fromWire(map["status"], '$path.status'),
      visibility: CircleVisibility.fromWire(map["visibility"], '$path.visibility'),
      joinPolicy: CircleJoinPolicy.fromWire(map["joinPolicy"], '$path.joinPolicy'),
      kind: CircleKind.fromWire(map["kind"], '$path.kind'),
      displaySubjectType: CircleDisplaySubjectType.fromWire(map["displaySubjectType"], '$path.displaySubjectType'),
      followEnabled: _requiredBool(map["followEnabled"], '$path.followEnabled'),
      defaultPublicGroupId: map["defaultPublicGroupId"] == null ? null : _requiredString(map["defaultPublicGroupId"], '$path.defaultPublicGroupId'),
      autoSyncChat: _requiredBool(map["autoSyncChat"], '$path.autoSyncChat'),
      sectionConfig: map["sectionConfig"] == null ? null : List<CircleSectionConfig>.unmodifiable(_requiredList(map["sectionConfig"], '$path.sectionConfig').asMap().entries.map((entry) => CircleSectionConfig.fromWire(_requiredObject(entry.value, '$path.sectionConfig' + '[${entry.key}]'), '$path.sectionConfig' + '[${entry.key}]'))),
      storageUsedBytes: _requiredInt(map["storageUsedBytes"], '$path.storageUsedBytes'),
      storageQuotaBytes: _requiredInt(map["storageQuotaBytes"], '$path.storageQuotaBytes'),
      domainId: map["domainId"] == null ? null : _requiredString(map["domainId"], '$path.domainId'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _requiredString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageType: map["linkedHomepageType"] == null ? null : HomepageType.fromWire(map["linkedHomepageType"], '$path.linkedHomepageType'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _requiredString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "name": name,
    if (description != null) "description": description!,
    if (rulesText != null) "rulesText": rulesText!,
    if (welcomeMessage != null) "welcomeMessage": welcomeMessage!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (iconUrl != null) "iconUrl": iconUrl!,
    "ownerId": ownerId,
    if (ownerDisplayNameSnapshot != null) "ownerDisplayNameSnapshot": ownerDisplayNameSnapshot!,
    if (category != null) "category": category!,
    if (subCategory != null) "subCategory": subCategory!,
    if (tags != null) "tags": tags!.map((value) => value).toList(growable: false),
    "memberCount": memberCount,
    "postCount": postCount,
    "weeklyActiveCount": weeklyActiveCount,
    "version": version,
    "status": status.wireName,
    "visibility": visibility.wireName,
    "joinPolicy": joinPolicy.wireName,
    "kind": kind.wireName,
    "displaySubjectType": displaySubjectType.wireName,
    "followEnabled": followEnabled,
    if (defaultPublicGroupId != null) "defaultPublicGroupId": defaultPublicGroupId!,
    "autoSyncChat": autoSyncChat,
    if (sectionConfig != null) "sectionConfig": sectionConfig!.map((value) => value.toWire()).toList(growable: false),
    "storageUsedBytes": storageUsedBytes,
    "storageQuotaBytes": storageQuotaBytes,
    if (domainId != null) "domainId": domainId!,
    if (linkedHomepageId != null) "linkedHomepageId": linkedHomepageId!,
    if (linkedHomepageType != null) "linkedHomepageType": linkedHomepageType!.wireName,
    if (linkedHomepageTitle != null) "linkedHomepageTitle": linkedHomepageTitle!,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CircleCommandResult {
  const CircleCommandResult({
    required this.circleId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String circleId;
  final int version;
  final CircleStatus status;
  final bool idempotentReplay;

  factory CircleCommandResult.fromWire(Map<String, Object?> map, [String path = "CircleCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "version", "status", "idempotentReplay"}, path);
    return CircleCommandResult(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      status: CircleStatus.fromWire(map["status"], '$path.status'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "version": version,
    "status": status.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleDiscoveryFeedPageSlice {
  const CircleDiscoveryFeedPageSlice({
    required this.circles,
    required this.items,
    this.cursor,
  });

  final List<Circle> circles;
  final List<CircleFeedItemView> items;
  final String? cursor;

  factory CircleDiscoveryFeedPageSlice.fromWire(Map<String, Object?> map, [String path = "CircleDiscoveryFeedPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"circles", "items", "cursor"}, path);
    return CircleDiscoveryFeedPageSlice(
      circles: List<Circle>.unmodifiable(_requiredList(map["circles"], '$path.circles').asMap().entries.map((entry) => Circle.fromWire(_requiredObject(entry.value, '$path.circles' + '[${entry.key}]'), '$path.circles' + '[${entry.key}]'))),
      items: List<CircleFeedItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleFeedItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circles": circles.map((value) => value.toWire()).toList(growable: false),
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleFacetBucketView {
  const CircleFacetBucketView({
    required this.facetKey,
    required this.label,
    this.categoryId,
    this.subCategory,
    required this.facetCount,
  });

  final String facetKey;
  final String label;
  final String? categoryId;
  final String? subCategory;
  final int facetCount;

  factory CircleFacetBucketView.fromWire(Map<String, Object?> map, [String path = "CircleFacetBucketView"]) {
    _rejectUnknownFields(map, const <String>{"facetKey", "label", "categoryId", "subCategory", "facetCount"}, path);
    return CircleFacetBucketView(
      facetKey: _requiredString(map["facetKey"], '$path.facetKey'),
      label: _requiredString(map["label"], '$path.label'),
      categoryId: map["categoryId"] == null ? null : _requiredString(map["categoryId"], '$path.categoryId'),
      subCategory: map["subCategory"] == null ? null : _requiredString(map["subCategory"], '$path.subCategory'),
      facetCount: _requiredInt(map["facetCount"], '$path.facetCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "facetKey": facetKey,
    "label": label,
    if (categoryId != null) "categoryId": categoryId!,
    if (subCategory != null) "subCategory": subCategory!,
    "facetCount": facetCount,
  };
}

final class CircleFeedItemView {
  const CircleFeedItemView({
    required this.circleId,
    required this.placementId,
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.assistantUsePolicy,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.authorBackgroundUrl,
    this.authorRoleLabel,
    this.authorIdentityTags,
    required this.authorVerified,
    this.title,
    this.body,
    this.summary,
    this.coverUrl,
    this.imageUrls,
    this.videoUrl,
    this.thumbnailUrl,
    this.width,
    this.height,
    this.durationMs,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.contentVertical,
    this.recallPath,
    this.supplySource,
    required this.pinned,
    required this.featured,
    this.pinnedAt,
    this.featuredAt,
  });

  final String circleId;
  final String placementId;
  final String postId;
  final String contentType;
  final String? contentIdentity;
  final AssistantUsePolicy? assistantUsePolicy;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? authorBackgroundUrl;
  final String? authorRoleLabel;
  final List<String>? authorIdentityTags;
  final bool authorVerified;
  final String? title;
  final String? body;
  final String? summary;
  final String? coverUrl;
  final List<String>? imageUrls;
  final String? videoUrl;
  final String? thumbnailUrl;
  final int? width;
  final int? height;
  final int? durationMs;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String? contentVertical;
  final String? recallPath;
  final String? supplySource;
  final bool pinned;
  final bool featured;
  final DateTime? pinnedAt;
  final DateTime? featuredAt;

  factory CircleFeedItemView.fromWire(Map<String, Object?> map, [String path = "CircleFeedItemView"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "placementId", "postId", "contentType", "contentIdentity", "assistantUsePolicy", "authorId", "authorDisplayName", "authorAvatarUrl", "authorBackgroundUrl", "authorRoleLabel", "authorIdentityTags", "authorVerified", "title", "body", "summary", "coverUrl", "imageUrls", "videoUrl", "thumbnailUrl", "width", "height", "durationMs", "likeCount", "commentCount", "shareCount", "createdAt", "updatedAt", "publishedAt", "contentVertical", "recallPath", "supplySource", "pinned", "featured", "pinnedAt", "featuredAt"}, path);
    return CircleFeedItemView(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      placementId: _requiredString(map["placementId"], '$path.placementId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      contentType: _requiredString(map["contentType"], '$path.contentType'),
      contentIdentity: map["contentIdentity"] == null ? null : _requiredString(map["contentIdentity"], '$path.contentIdentity'),
      assistantUsePolicy: map["assistantUsePolicy"] == null ? null : AssistantUsePolicy.fromWire(map["assistantUsePolicy"], '$path.assistantUsePolicy'),
      authorId: map["authorId"] == null ? null : _requiredString(map["authorId"], '$path.authorId'),
      authorDisplayName: map["authorDisplayName"] == null ? null : _requiredString(map["authorDisplayName"], '$path.authorDisplayName'),
      authorAvatarUrl: map["authorAvatarUrl"] == null ? null : _requiredString(map["authorAvatarUrl"], '$path.authorAvatarUrl'),
      authorBackgroundUrl: map["authorBackgroundUrl"] == null ? null : _requiredString(map["authorBackgroundUrl"], '$path.authorBackgroundUrl'),
      authorRoleLabel: map["authorRoleLabel"] == null ? null : _requiredString(map["authorRoleLabel"], '$path.authorRoleLabel'),
      authorIdentityTags: map["authorIdentityTags"] == null ? null : List<String>.unmodifiable(_requiredList(map["authorIdentityTags"], '$path.authorIdentityTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.authorIdentityTags' + '[${entry.key}]'))),
      authorVerified: _requiredBool(map["authorVerified"], '$path.authorVerified'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      body: map["body"] == null ? null : _requiredString(map["body"], '$path.body'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      imageUrls: map["imageUrls"] == null ? null : List<String>.unmodifiable(_requiredList(map["imageUrls"], '$path.imageUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.imageUrls' + '[${entry.key}]'))),
      videoUrl: map["videoUrl"] == null ? null : _requiredString(map["videoUrl"], '$path.videoUrl'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      commentCount: _requiredInt(map["commentCount"], '$path.commentCount'),
      shareCount: _requiredInt(map["shareCount"], '$path.shareCount'),
      createdAt: map["createdAt"] == null ? null : _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: map["updatedAt"] == null ? null : _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      publishedAt: map["publishedAt"] == null ? null : _requiredTimestamp(map["publishedAt"], '$path.publishedAt'),
      contentVertical: map["contentVertical"] == null ? null : _requiredString(map["contentVertical"], '$path.contentVertical'),
      recallPath: map["recallPath"] == null ? null : _requiredString(map["recallPath"], '$path.recallPath'),
      supplySource: map["supplySource"] == null ? null : _requiredString(map["supplySource"], '$path.supplySource'),
      pinned: _requiredBool(map["pinned"], '$path.pinned'),
      featured: _requiredBool(map["featured"], '$path.featured'),
      pinnedAt: map["pinnedAt"] == null ? null : _requiredTimestamp(map["pinnedAt"], '$path.pinnedAt'),
      featuredAt: map["featuredAt"] == null ? null : _requiredTimestamp(map["featuredAt"], '$path.featuredAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "placementId": placementId,
    "postId": postId,
    "contentType": contentType,
    if (contentIdentity != null) "contentIdentity": contentIdentity!,
    if (assistantUsePolicy != null) "assistantUsePolicy": assistantUsePolicy!.wireName,
    if (authorId != null) "authorId": authorId!,
    if (authorDisplayName != null) "authorDisplayName": authorDisplayName!,
    if (authorAvatarUrl != null) "authorAvatarUrl": authorAvatarUrl!,
    if (authorBackgroundUrl != null) "authorBackgroundUrl": authorBackgroundUrl!,
    if (authorRoleLabel != null) "authorRoleLabel": authorRoleLabel!,
    if (authorIdentityTags != null) "authorIdentityTags": authorIdentityTags!.map((value) => value).toList(growable: false),
    "authorVerified": authorVerified,
    if (title != null) "title": title!,
    if (body != null) "body": body!,
    if (summary != null) "summary": summary!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (imageUrls != null) "imageUrls": imageUrls!.map((value) => value).toList(growable: false),
    if (videoUrl != null) "videoUrl": videoUrl!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
    "likeCount": likeCount,
    "commentCount": commentCount,
    "shareCount": shareCount,
    if (createdAt != null) "createdAt": createdAt!.toUtc().toIso8601String(),
    if (updatedAt != null) "updatedAt": updatedAt!.toUtc().toIso8601String(),
    if (publishedAt != null) "publishedAt": publishedAt!.toUtc().toIso8601String(),
    if (contentVertical != null) "contentVertical": contentVertical!,
    if (recallPath != null) "recallPath": recallPath!,
    if (supplySource != null) "supplySource": supplySource!,
    "pinned": pinned,
    "featured": featured,
    if (pinnedAt != null) "pinnedAt": pinnedAt!.toUtc().toIso8601String(),
    if (featuredAt != null) "featuredAt": featuredAt!.toUtc().toIso8601String(),
  };
}

final class CircleFeedPageSlice {
  const CircleFeedPageSlice({
    required this.items,
    this.cursor,
  });

  final List<CircleFeedItemView> items;
  final String? cursor;

  factory CircleFeedPageSlice.fromWire(Map<String, Object?> map, [String path = "CircleFeedPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CircleFeedPageSlice(
      items: List<CircleFeedItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleFeedItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleFileCommandResult {
  const CircleFileCommandResult({
    required this.fileId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String fileId;
  final int version;
  final CircleFileStatus status;
  final bool idempotentReplay;

  factory CircleFileCommandResult.fromWire(Map<String, Object?> map, [String path = "CircleFileCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"fileId", "version", "status", "idempotentReplay"}, path);
    return CircleFileCommandResult(
      fileId: _requiredString(map["fileId"], '$path.fileId'),
      version: _requiredInt(map["version"], '$path.version'),
      status: CircleFileStatus.fromWire(map["status"], '$path.status'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "fileId": fileId,
    "version": version,
    "status": status.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleFilePageSlice {
  const CircleFilePageSlice({
    required this.items,
    this.cursor,
  });

  final List<CircleFileSlice> items;
  final String? cursor;

  factory CircleFilePageSlice.fromWire(Map<String, Object?> map, [String path = "CircleFilePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CircleFilePageSlice(
      items: List<CircleFileSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleFileSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleFileSlice {
  const CircleFileSlice({
    required this.fileId,
    required this.version,
    required this.circleId,
    this.groupId,
    this.parentFolderId,
    required this.name,
    required this.fileType,
    this.assetId,
    this.mimeType,
    required this.sizeBytes,
    required this.uploaderPersonaId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String fileId;
  final int version;
  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String name;
  final CircleFileType fileType;
  final String? assetId;
  final String? mimeType;
  final int sizeBytes;
  final String uploaderPersonaId;
  final CircleFileStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CircleFileSlice.fromWire(Map<String, Object?> map, [String path = "CircleFileSlice"]) {
    _rejectUnknownFields(map, const <String>{"fileId", "version", "circleId", "groupId", "parentFolderId", "name", "fileType", "assetId", "mimeType", "sizeBytes", "uploaderPersonaId", "status", "createdAt", "updatedAt"}, path);
    return CircleFileSlice(
      fileId: _requiredString(map["fileId"], '$path.fileId'),
      version: _requiredInt(map["version"], '$path.version'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      groupId: map["groupId"] == null ? null : _requiredString(map["groupId"], '$path.groupId'),
      parentFolderId: map["parentFolderId"] == null ? null : _requiredString(map["parentFolderId"], '$path.parentFolderId'),
      name: _requiredString(map["name"], '$path.name'),
      fileType: CircleFileType.fromWire(map["fileType"], '$path.fileType'),
      assetId: map["assetId"] == null ? null : _requiredString(map["assetId"], '$path.assetId'),
      mimeType: map["mimeType"] == null ? null : _requiredString(map["mimeType"], '$path.mimeType'),
      sizeBytes: _requiredInt(map["sizeBytes"], '$path.sizeBytes'),
      uploaderPersonaId: _requiredString(map["uploaderPersonaId"], '$path.uploaderPersonaId'),
      status: CircleFileStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "fileId": fileId,
    "version": version,
    "circleId": circleId,
    if (groupId != null) "groupId": groupId!,
    if (parentFolderId != null) "parentFolderId": parentFolderId!,
    "name": name,
    "fileType": fileType.wireName,
    if (assetId != null) "assetId": assetId!,
    if (mimeType != null) "mimeType": mimeType!,
    "sizeBytes": sizeBytes,
    "uploaderPersonaId": uploaderPersonaId,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CircleGroupCommandResult {
  const CircleGroupCommandResult({
    required this.groupId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String groupId;
  final int version;
  final CircleGroupStatus status;
  final bool idempotentReplay;

  factory CircleGroupCommandResult.fromWire(Map<String, Object?> map, [String path = "CircleGroupCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"groupId", "version", "status", "idempotentReplay"}, path);
    return CircleGroupCommandResult(
      groupId: _requiredString(map["groupId"], '$path.groupId'),
      version: _requiredInt(map["version"], '$path.version'),
      status: CircleGroupStatus.fromWire(map["status"], '$path.status'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "groupId": groupId,
    "version": version,
    "status": status.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleGroupMembershipCommandResult {
  const CircleGroupMembershipCommandResult({
    required this.membershipId,
    required this.version,
    required this.role,
    required this.state,
    required this.idempotentReplay,
  });

  final String membershipId;
  final int version;
  final CircleGroupMembershipRole role;
  final CircleGroupMembershipState state;
  final bool idempotentReplay;

  factory CircleGroupMembershipCommandResult.fromWire(Map<String, Object?> map, [String path = "CircleGroupMembershipCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"membershipId", "version", "role", "state", "idempotentReplay"}, path);
    return CircleGroupMembershipCommandResult(
      membershipId: _requiredString(map["membershipId"], '$path.membershipId'),
      version: _requiredInt(map["version"], '$path.version'),
      role: CircleGroupMembershipRole.fromWire(map["role"], '$path.role'),
      state: CircleGroupMembershipState.fromWire(map["state"], '$path.state'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "membershipId": membershipId,
    "version": version,
    "role": role.wireName,
    "state": state.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleGroupMembershipPageSlice {
  const CircleGroupMembershipPageSlice({
    required this.items,
    this.cursor,
  });

  final List<CircleGroupMembershipSlice> items;
  final String? cursor;

  factory CircleGroupMembershipPageSlice.fromWire(Map<String, Object?> map, [String path = "CircleGroupMembershipPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CircleGroupMembershipPageSlice(
      items: List<CircleGroupMembershipSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleGroupMembershipSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleGroupMembershipSlice {
  const CircleGroupMembershipSlice({
    required this.membershipId,
    required this.version,
    required this.groupId,
    required this.circleId,
    required this.personaId,
    required this.role,
    required this.state,
    this.joinedAt,
    this.leftAt,
    this.decidedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String membershipId;
  final int version;
  final String groupId;
  final String circleId;
  final String personaId;
  final CircleGroupMembershipRole role;
  final CircleGroupMembershipState state;
  final DateTime? joinedAt;
  final DateTime? leftAt;
  final DateTime? decidedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CircleGroupMembershipSlice.fromWire(Map<String, Object?> map, [String path = "CircleGroupMembershipSlice"]) {
    _rejectUnknownFields(map, const <String>{"membershipId", "version", "groupId", "circleId", "personaId", "role", "state", "joinedAt", "leftAt", "decidedAt", "createdAt", "updatedAt"}, path);
    return CircleGroupMembershipSlice(
      membershipId: _requiredString(map["membershipId"], '$path.membershipId'),
      version: _requiredInt(map["version"], '$path.version'),
      groupId: _requiredString(map["groupId"], '$path.groupId'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      role: CircleGroupMembershipRole.fromWire(map["role"], '$path.role'),
      state: CircleGroupMembershipState.fromWire(map["state"], '$path.state'),
      joinedAt: map["joinedAt"] == null ? null : _requiredTimestamp(map["joinedAt"], '$path.joinedAt'),
      leftAt: map["leftAt"] == null ? null : _requiredTimestamp(map["leftAt"], '$path.leftAt'),
      decidedAt: map["decidedAt"] == null ? null : _requiredTimestamp(map["decidedAt"], '$path.decidedAt'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "membershipId": membershipId,
    "version": version,
    "groupId": groupId,
    "circleId": circleId,
    "personaId": personaId,
    "role": role.wireName,
    "state": state.wireName,
    if (joinedAt != null) "joinedAt": joinedAt!.toUtc().toIso8601String(),
    if (leftAt != null) "leftAt": leftAt!.toUtc().toIso8601String(),
    if (decidedAt != null) "decidedAt": decidedAt!.toUtc().toIso8601String(),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CircleGroupPageSlice {
  const CircleGroupPageSlice({
    required this.items,
    this.cursor,
  });

  final List<CircleGroupSlice> items;
  final String? cursor;

  factory CircleGroupPageSlice.fromWire(Map<String, Object?> map, [String path = "CircleGroupPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CircleGroupPageSlice(
      items: List<CircleGroupSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleGroupSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleGroupSlice {
  const CircleGroupSlice({
    required this.groupId,
    required this.version,
    required this.circleId,
    this.parentGroupId,
    required this.groupType,
    this.nodeType,
    required this.name,
    this.description,
    required this.visibility,
    required this.joinPolicy,
    this.conversationId,
    required this.storageEnabled,
    required this.noticeEnabled,
    required this.isDefaultPublicGroup,
    required this.status,
    required this.memberCount,
    required this.createdAt,
    required this.updatedAt,
  });

  final String groupId;
  final int version;
  final String circleId;
  final String? parentGroupId;
  final CircleGroupType groupType;
  final OrganizationNodeType? nodeType;
  final String name;
  final String? description;
  final CircleGroupVisibility visibility;
  final CircleGroupJoinPolicy joinPolicy;
  final String? conversationId;
  final bool storageEnabled;
  final bool noticeEnabled;
  final bool isDefaultPublicGroup;
  final CircleGroupStatus status;
  final int memberCount;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CircleGroupSlice.fromWire(Map<String, Object?> map, [String path = "CircleGroupSlice"]) {
    _rejectUnknownFields(map, const <String>{"groupId", "version", "circleId", "parentGroupId", "groupType", "nodeType", "name", "description", "visibility", "joinPolicy", "conversationId", "storageEnabled", "noticeEnabled", "isDefaultPublicGroup", "status", "memberCount", "createdAt", "updatedAt"}, path);
    return CircleGroupSlice(
      groupId: _requiredString(map["groupId"], '$path.groupId'),
      version: _requiredInt(map["version"], '$path.version'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      parentGroupId: map["parentGroupId"] == null ? null : _requiredString(map["parentGroupId"], '$path.parentGroupId'),
      groupType: CircleGroupType.fromWire(map["groupType"], '$path.groupType'),
      nodeType: map["nodeType"] == null ? null : OrganizationNodeType.fromWire(map["nodeType"], '$path.nodeType'),
      name: _requiredString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      visibility: CircleGroupVisibility.fromWire(map["visibility"], '$path.visibility'),
      joinPolicy: CircleGroupJoinPolicy.fromWire(map["joinPolicy"], '$path.joinPolicy'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
      storageEnabled: _requiredBool(map["storageEnabled"], '$path.storageEnabled'),
      noticeEnabled: _requiredBool(map["noticeEnabled"], '$path.noticeEnabled'),
      isDefaultPublicGroup: _requiredBool(map["isDefaultPublicGroup"], '$path.isDefaultPublicGroup'),
      status: CircleGroupStatus.fromWire(map["status"], '$path.status'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "groupId": groupId,
    "version": version,
    "circleId": circleId,
    if (parentGroupId != null) "parentGroupId": parentGroupId!,
    "groupType": groupType.wireName,
    if (nodeType != null) "nodeType": nodeType!.wireName,
    "name": name,
    if (description != null) "description": description!,
    "visibility": visibility.wireName,
    "joinPolicy": joinPolicy.wireName,
    if (conversationId != null) "conversationId": conversationId!,
    "storageEnabled": storageEnabled,
    "noticeEnabled": noticeEnabled,
    "isDefaultPublicGroup": isDefaultPublicGroup,
    "status": status.wireName,
    "memberCount": memberCount,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CircleImpactItem {
  const CircleImpactItem({
    required this.helpType,
    required this.action,
    required this.intersectionDimension,
    required this.tagRef,
    required this.source,
    required this.count,
    required this.primaryText,
    required this.subtitleText,
    required this.impactId,
    required this.primarySpans,
    required this.sampleVisuals,
    this.representativeActor,
    required this.actionHints,
    this.countTarget,
    required this.evidenceSnapshotId,
    required this.countObjectKind,
    this.propagationPath,
    required this.iconKey,
  });

  final String helpType;
  final String action;
  final String intersectionDimension;
  final String tagRef;
  final String source;
  final int count;
  final String primaryText;
  final String subtitleText;
  final String impactId;
  final List<IntersectionTextSpan> primarySpans;
  final List<IntersectionVisual> sampleVisuals;
  final IntersectionRepresentativeActor? representativeActor;
  final List<IntersectionActionHint> actionHints;
  final IntersectionTarget? countTarget;
  final String evidenceSnapshotId;
  final String countObjectKind;
  final IntersectionPropagationPath? propagationPath;
  final String iconKey;

  factory CircleImpactItem.fromWire(Map<String, Object?> map, [String path = "CircleImpactItem"]) {
    _rejectUnknownFields(map, const <String>{"helpType", "action", "intersectionDimension", "tagRef", "source", "count", "primaryText", "subtitleText", "impactId", "primarySpans", "sampleVisuals", "representativeActor", "actionHints", "countTarget", "evidenceSnapshotId", "countObjectKind", "propagationPath", "iconKey"}, path);
    return CircleImpactItem(
      helpType: _requiredString(map["helpType"], '$path.helpType'),
      action: _requiredString(map["action"], '$path.action'),
      intersectionDimension: _requiredString(map["intersectionDimension"], '$path.intersectionDimension'),
      tagRef: _requiredString(map["tagRef"], '$path.tagRef'),
      source: _requiredString(map["source"], '$path.source'),
      count: _requiredInt(map["count"], '$path.count'),
      primaryText: _requiredString(map["primaryText"], '$path.primaryText'),
      subtitleText: _requiredString(map["subtitleText"], '$path.subtitleText'),
      impactId: _requiredString(map["impactId"], '$path.impactId'),
      primarySpans: List<IntersectionTextSpan>.unmodifiable(_requiredList(map["primarySpans"], '$path.primarySpans').asMap().entries.map((entry) => IntersectionTextSpan.fromWire(_requiredObject(entry.value, '$path.primarySpans' + '[${entry.key}]'), '$path.primarySpans' + '[${entry.key}]'))),
      sampleVisuals: List<IntersectionVisual>.unmodifiable(_requiredList(map["sampleVisuals"], '$path.sampleVisuals').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.sampleVisuals' + '[${entry.key}]'), '$path.sampleVisuals' + '[${entry.key}]'))),
      representativeActor: map["representativeActor"] == null ? null : IntersectionRepresentativeActor.fromWire(_requiredObject(map["representativeActor"], '$path.representativeActor'), '$path.representativeActor'),
      actionHints: List<IntersectionActionHint>.unmodifiable(_requiredList(map["actionHints"], '$path.actionHints').asMap().entries.map((entry) => IntersectionActionHint.fromWire(_requiredObject(entry.value, '$path.actionHints' + '[${entry.key}]'), '$path.actionHints' + '[${entry.key}]'))),
      countTarget: map["countTarget"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["countTarget"], '$path.countTarget'), '$path.countTarget'),
      evidenceSnapshotId: _requiredString(map["evidenceSnapshotId"], '$path.evidenceSnapshotId'),
      countObjectKind: _requiredString(map["countObjectKind"], '$path.countObjectKind'),
      propagationPath: map["propagationPath"] == null ? null : IntersectionPropagationPath.fromWire(_requiredObject(map["propagationPath"], '$path.propagationPath'), '$path.propagationPath'),
      iconKey: _requiredString(map["iconKey"], '$path.iconKey'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "helpType": helpType,
    "action": action,
    "intersectionDimension": intersectionDimension,
    "tagRef": tagRef,
    "source": source,
    "count": count,
    "primaryText": primaryText,
    "subtitleText": subtitleText,
    "impactId": impactId,
    "primarySpans": primarySpans.map((value) => value.toWire()).toList(growable: false),
    "sampleVisuals": sampleVisuals.map((value) => value.toWire()).toList(growable: false),
    if (representativeActor != null) "representativeActor": representativeActor!.toWire(),
    "actionHints": actionHints.map((value) => value.toWire()).toList(growable: false),
    if (countTarget != null) "countTarget": countTarget!.toWire(),
    "evidenceSnapshotId": evidenceSnapshotId,
    "countObjectKind": countObjectKind,
    if (propagationPath != null) "propagationPath": propagationPath!.toWire(),
    "iconKey": iconKey,
  };
}

final class CircleImpactSummary {
  const CircleImpactSummary({
    required this.circleId,
    required this.total,
    required this.items,
  });

  final String circleId;
  final int total;
  final List<CircleImpactItem> items;

  factory CircleImpactSummary.fromWire(Map<String, Object?> map, [String path = "CircleImpactSummary"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "total", "items"}, path);
    return CircleImpactSummary(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      total: _requiredInt(map["total"], '$path.total'),
      items: List<CircleImpactItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleImpactItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "total": total,
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class CircleMembershipCommandResult {
  const CircleMembershipCommandResult({
    required this.membershipId,
    required this.version,
    required this.state,
    required this.role,
    required this.idempotentReplay,
  });

  final String membershipId;
  final int version;
  final CircleMembershipState state;
  final CircleMemberRole role;
  final bool idempotentReplay;

  factory CircleMembershipCommandResult.fromWire(Map<String, Object?> map, [String path = "CircleMembershipCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"membershipId", "version", "state", "role", "idempotentReplay"}, path);
    return CircleMembershipCommandResult(
      membershipId: _requiredString(map["membershipId"], '$path.membershipId'),
      version: _requiredInt(map["version"], '$path.version'),
      state: CircleMembershipState.fromWire(map["state"], '$path.state'),
      role: CircleMemberRole.fromWire(map["role"], '$path.role'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "membershipId": membershipId,
    "version": version,
    "state": state.wireName,
    "role": role.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleMembershipPageSlice {
  const CircleMembershipPageSlice({
    required this.items,
    this.cursor,
  });

  final List<CircleMembershipSlice> items;
  final String? cursor;

  factory CircleMembershipPageSlice.fromWire(Map<String, Object?> map, [String path = "CircleMembershipPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CircleMembershipPageSlice(
      items: List<CircleMembershipSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleMembershipSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleMembershipSlice {
  const CircleMembershipSlice({
    required this.membershipId,
    required this.version,
    required this.circleId,
    required this.personaId,
    required this.role,
    required this.state,
    required this.joinedAt,
    this.leftAt,
    this.lastActiveAt,
    required this.contribution,
    required this.createdAt,
    required this.updatedAt,
  });

  final String membershipId;
  final int version;
  final String circleId;
  final String personaId;
  final CircleMemberRole role;
  final CircleMembershipState state;
  final DateTime joinedAt;
  final DateTime? leftAt;
  final DateTime? lastActiveAt;
  final int contribution;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CircleMembershipSlice.fromWire(Map<String, Object?> map, [String path = "CircleMembershipSlice"]) {
    _rejectUnknownFields(map, const <String>{"membershipId", "version", "circleId", "personaId", "role", "state", "joinedAt", "leftAt", "lastActiveAt", "contribution", "createdAt", "updatedAt"}, path);
    return CircleMembershipSlice(
      membershipId: _requiredString(map["membershipId"], '$path.membershipId'),
      version: _requiredInt(map["version"], '$path.version'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      role: CircleMemberRole.fromWire(map["role"], '$path.role'),
      state: CircleMembershipState.fromWire(map["state"], '$path.state'),
      joinedAt: _requiredTimestamp(map["joinedAt"], '$path.joinedAt'),
      leftAt: map["leftAt"] == null ? null : _requiredTimestamp(map["leftAt"], '$path.leftAt'),
      lastActiveAt: map["lastActiveAt"] == null ? null : _requiredTimestamp(map["lastActiveAt"], '$path.lastActiveAt'),
      contribution: _requiredInt(map["contribution"], '$path.contribution'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "membershipId": membershipId,
    "version": version,
    "circleId": circleId,
    "personaId": personaId,
    "role": role.wireName,
    "state": state.wireName,
    "joinedAt": joinedAt.toUtc().toIso8601String(),
    if (leftAt != null) "leftAt": leftAt!.toUtc().toIso8601String(),
    if (lastActiveAt != null) "lastActiveAt": lastActiveAt!.toUtc().toIso8601String(),
    "contribution": contribution,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class CirclePageSlice {
  const CirclePageSlice({
    required this.items,
    this.cursor,
  });

  final List<Circle> items;
  final String? cursor;

  factory CirclePageSlice.fromWire(Map<String, Object?> map, [String path = "CirclePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return CirclePageSlice(
      items: List<Circle>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => Circle.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CirclePostPlacementCommandResult {
  const CirclePostPlacementCommandResult({
    required this.placementId,
    required this.version,
    required this.state,
    required this.idempotentReplay,
  });

  final String placementId;
  final int version;
  final String state;
  final bool idempotentReplay;

  factory CirclePostPlacementCommandResult.fromWire(Map<String, Object?> map, [String path = "CirclePostPlacementCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"placementId", "version", "state", "idempotentReplay"}, path);
    return CirclePostPlacementCommandResult(
      placementId: _requiredString(map["placementId"], '$path.placementId'),
      version: _requiredInt(map["version"], '$path.version'),
      state: _requiredString(map["state"], '$path.state'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "placementId": placementId,
    "version": version,
    "state": state,
    "idempotentReplay": idempotentReplay,
  };
}

final class CircleSearchItemView {
  const CircleSearchItemView({
    required this.circleId,
    required this.name,
    this.description,
    this.coverUrl,
    this.categoryId,
    this.subCategory,
    this.domainId,
    this.kind,
    this.displaySubjectType,
    required this.memberCount,
    required this.postCount,
    this.highlightText,
    this.matchedField,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? categoryId;
  final String? subCategory;
  final String? domainId;
  final CircleKind? kind;
  final CircleDisplaySubjectType? displaySubjectType;
  final int memberCount;
  final int postCount;
  final String? highlightText;
  final String? matchedField;
  final String? linkedHomepageId;
  final HomepageType? linkedHomepageType;
  final String? linkedHomepageTitle;

  factory CircleSearchItemView.fromWire(Map<String, Object?> map, [String path = "CircleSearchItemView"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "name", "description", "coverUrl", "categoryId", "subCategory", "domainId", "kind", "displaySubjectType", "memberCount", "postCount", "highlightText", "matchedField", "linkedHomepageId", "linkedHomepageType", "linkedHomepageTitle"}, path);
    return CircleSearchItemView(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      name: _requiredString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      categoryId: map["categoryId"] == null ? null : _requiredString(map["categoryId"], '$path.categoryId'),
      subCategory: map["subCategory"] == null ? null : _requiredString(map["subCategory"], '$path.subCategory'),
      domainId: map["domainId"] == null ? null : _requiredString(map["domainId"], '$path.domainId'),
      kind: map["kind"] == null ? null : CircleKind.fromWire(map["kind"], '$path.kind'),
      displaySubjectType: map["displaySubjectType"] == null ? null : CircleDisplaySubjectType.fromWire(map["displaySubjectType"], '$path.displaySubjectType'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
      highlightText: map["highlightText"] == null ? null : _requiredString(map["highlightText"], '$path.highlightText'),
      matchedField: map["matchedField"] == null ? null : _requiredString(map["matchedField"], '$path.matchedField'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _requiredString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageType: map["linkedHomepageType"] == null ? null : HomepageType.fromWire(map["linkedHomepageType"], '$path.linkedHomepageType'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _requiredString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "name": name,
    if (description != null) "description": description!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (categoryId != null) "categoryId": categoryId!,
    if (subCategory != null) "subCategory": subCategory!,
    if (domainId != null) "domainId": domainId!,
    if (kind != null) "kind": kind!.wireName,
    if (displaySubjectType != null) "displaySubjectType": displaySubjectType!.wireName,
    "memberCount": memberCount,
    "postCount": postCount,
    if (highlightText != null) "highlightText": highlightText!,
    if (matchedField != null) "matchedField": matchedField!,
    if (linkedHomepageId != null) "linkedHomepageId": linkedHomepageId!,
    if (linkedHomepageType != null) "linkedHomepageType": linkedHomepageType!.wireName,
    if (linkedHomepageTitle != null) "linkedHomepageTitle": linkedHomepageTitle!,
  };
}

final class CircleSearchResultView {
  const CircleSearchResultView({
    this.items,
    this.facetBuckets,
    this.cursor,
  });

  final List<CircleSearchItemView>? items;
  final List<CircleFacetBucketView>? facetBuckets;
  final String? cursor;

  factory CircleSearchResultView.fromWire(Map<String, Object?> map, [String path = "CircleSearchResultView"]) {
    _rejectUnknownFields(map, const <String>{"items", "facetBuckets", "cursor"}, path);
    return CircleSearchResultView(
      items: map["items"] == null ? null : List<CircleSearchItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CircleSearchItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      facetBuckets: map["facetBuckets"] == null ? null : List<CircleFacetBucketView>.unmodifiable(_requiredList(map["facetBuckets"], '$path.facetBuckets').asMap().entries.map((entry) => CircleFacetBucketView.fromWire(_requiredObject(entry.value, '$path.facetBuckets' + '[${entry.key}]'), '$path.facetBuckets' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (items != null) "items": items!.map((value) => value.toWire()).toList(growable: false),
    if (facetBuckets != null) "facetBuckets": facetBuckets!.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class CircleSectionConfig {
  const CircleSectionConfig({
    required this.sectionType,
    required this.visible,
    required this.order,
    this.customTitle,
  });

  final CircleSectionType sectionType;
  final bool visible;
  final int order;
  final String? customTitle;

  factory CircleSectionConfig.fromWire(Map<String, Object?> map, [String path = "CircleSectionConfig"]) {
    _rejectUnknownFields(map, const <String>{"sectionType", "visible", "order", "customTitle"}, path);
    return CircleSectionConfig(
      sectionType: CircleSectionType.fromWire(map["sectionType"], '$path.sectionType'),
      visible: _requiredBool(map["visible"], '$path.visible'),
      order: _requiredInt(map["order"], '$path.order'),
      customTitle: map["customTitle"] == null ? null : _requiredString(map["customTitle"], '$path.customTitle'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sectionType": sectionType.wireName,
    "visible": visible,
    "order": order,
    if (customTitle != null) "customTitle": customTitle!,
  };
}

final class CircleStatsWire {
  const CircleStatsWire({
    required this.circleId,
    required this.memberCount,
    required this.postCount,
    required this.discussionCount,
    required this.weeklyActiveCount,
    required this.likeCount,
    required this.storageUsedBytes,
    required this.storageQuotaBytes,
  });

  final String circleId;
  final int memberCount;
  final int postCount;
  final int discussionCount;
  final int weeklyActiveCount;
  final int likeCount;
  final int storageUsedBytes;
  final int storageQuotaBytes;

  factory CircleStatsWire.fromWire(Map<String, Object?> map, [String path = "CircleStatsWire"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "memberCount", "postCount", "discussionCount", "weeklyActiveCount", "likeCount", "storageUsedBytes", "storageQuotaBytes"}, path);
    return CircleStatsWire(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
      discussionCount: _requiredInt(map["discussionCount"], '$path.discussionCount'),
      weeklyActiveCount: _requiredInt(map["weeklyActiveCount"], '$path.weeklyActiveCount'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      storageUsedBytes: _requiredInt(map["storageUsedBytes"], '$path.storageUsedBytes'),
      storageQuotaBytes: _requiredInt(map["storageQuotaBytes"], '$path.storageQuotaBytes'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "memberCount": memberCount,
    "postCount": postCount,
    "discussionCount": discussionCount,
    "weeklyActiveCount": weeklyActiveCount,
    "likeCount": likeCount,
    "storageUsedBytes": storageUsedBytes,
    "storageQuotaBytes": storageQuotaBytes,
  };
}

final class GatheringAdmissionControl {
  const GatheringAdmissionControl({
    required this.status,
    this.pausedByPersonaId,
    this.reasonRef,
    this.pausedAt,
    required this.version,
  });

  final GatheringAdmissionControlStatus status;
  final String? pausedByPersonaId;
  final String? reasonRef;
  final DateTime? pausedAt;
  final int version;

  factory GatheringAdmissionControl.fromWire(Map<String, Object?> map, [String path = "GatheringAdmissionControl"]) {
    _rejectUnknownFields(map, const <String>{"status", "pausedByPersonaId", "reasonRef", "pausedAt", "version"}, path);
    return GatheringAdmissionControl(
      status: GatheringAdmissionControlStatus.fromWire(map["status"], '$path.status'),
      pausedByPersonaId: map["pausedByPersonaId"] == null ? null : _requiredString(map["pausedByPersonaId"], '$path.pausedByPersonaId'),
      reasonRef: map["reasonRef"] == null ? null : _requiredString(map["reasonRef"], '$path.reasonRef'),
      pausedAt: map["pausedAt"] == null ? null : _requiredTimestamp(map["pausedAt"], '$path.pausedAt'),
      version: _requiredInt(map["version"], '$path.version'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status.wireName,
    if (pausedByPersonaId != null) "pausedByPersonaId": pausedByPersonaId!,
    if (reasonRef != null) "reasonRef": reasonRef!,
    if (pausedAt != null) "pausedAt": pausedAt!.toUtc().toIso8601String(),
    "version": version,
  };
}

final class GatheringAdmissionStateSlice {
  const GatheringAdmissionStateSlice({
    required this.admissionState,
    this.reasonRef,
    required this.evaluatedAt,
  });

  final GatheringAdmissionState admissionState;
  final String? reasonRef;
  final DateTime evaluatedAt;

  factory GatheringAdmissionStateSlice.fromWire(Map<String, Object?> map, [String path = "GatheringAdmissionStateSlice"]) {
    _rejectUnknownFields(map, const <String>{"admissionState", "reasonRef", "evaluatedAt"}, path);
    return GatheringAdmissionStateSlice(
      admissionState: GatheringAdmissionState.fromWire(map["admissionState"], '$path.admissionState'),
      reasonRef: map["reasonRef"] == null ? null : _requiredString(map["reasonRef"], '$path.reasonRef'),
      evaluatedAt: _requiredTimestamp(map["evaluatedAt"], '$path.evaluatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "admissionState": admissionState.wireName,
    if (reasonRef != null) "reasonRef": reasonRef!,
    "evaluatedAt": evaluatedAt.toUtc().toIso8601String(),
  };
}

final class GatheringApplicationQuestion {
  const GatheringApplicationQuestion({
    required this.questionId,
    required this.prompt,
    required this.kind,
    required this.options,
    required this.required,
  });

  final String questionId;
  final String prompt;
  final GatheringApplicationQuestionKind kind;
  final List<GatheringApplicationQuestionOption> options;
  final bool required;

  factory GatheringApplicationQuestion.fromWire(Map<String, Object?> map, [String path = "GatheringApplicationQuestion"]) {
    _rejectUnknownFields(map, const <String>{"questionId", "prompt", "kind", "options", "required"}, path);
    return GatheringApplicationQuestion(
      questionId: _requiredNonBlankString(map["questionId"], '$path.questionId'),
      prompt: _requiredNonBlankString(map["prompt"], '$path.prompt'),
      kind: GatheringApplicationQuestionKind.fromWire(map["kind"], '$path.kind'),
      options: List<GatheringApplicationQuestionOption>.unmodifiable(_requiredBoundedList(map["options"], '$path.options', max: 10).asMap().entries.map((entry) => GatheringApplicationQuestionOption.fromWire(_requiredObject(entry.value, '$path.options' + '[${entry.key}]'), '$path.options' + '[${entry.key}]'))),
      required: _requiredBool(map["required"], '$path.required'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "questionId": questionId,
    "prompt": prompt,
    "kind": kind.wireName,
    "options": options.map((value) => value.toWire()).toList(growable: false),
    "required": required,
  };
}

final class GatheringApplicationQuestionOption {
  const GatheringApplicationQuestionOption({
    required this.optionId,
    required this.label,
  });

  final String optionId;
  final String label;

  factory GatheringApplicationQuestionOption.fromWire(Map<String, Object?> map, [String path = "GatheringApplicationQuestionOption"]) {
    _rejectUnknownFields(map, const <String>{"optionId", "label"}, path);
    return GatheringApplicationQuestionOption(
      optionId: _requiredNonBlankString(map["optionId"], '$path.optionId'),
      label: _requiredNonBlankString(map["label"], '$path.label'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "optionId": optionId,
    "label": label,
  };
}

final class GatheringByHostPageSlice {
  const GatheringByHostPageSlice({
    required this.items,
    this.nextCursor,
    required this.hasMore,
  });

  final List<GatheringPublicCardSlice> items;
  final String? nextCursor;
  final bool hasMore;

  factory GatheringByHostPageSlice.fromWire(Map<String, Object?> map, [String path = "GatheringByHostPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "hasMore"}, path);
    return GatheringByHostPageSlice(
      items: List<GatheringPublicCardSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => GatheringPublicCardSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class GatheringBySourcePageSlice {
  const GatheringBySourcePageSlice({
    required this.items,
    this.nextCursor,
    required this.hasMore,
  });

  final List<GatheringPublicCardSlice> items;
  final String? nextCursor;
  final bool hasMore;

  factory GatheringBySourcePageSlice.fromWire(Map<String, Object?> map, [String path = "GatheringBySourcePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "hasMore"}, path);
    return GatheringBySourcePageSlice(
      items: List<GatheringPublicCardSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => GatheringPublicCardSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class GatheringCapacityPolicy {
  const GatheringCapacityPolicy({
    required this.maxParticipants,
  });

  final int maxParticipants;

  factory GatheringCapacityPolicy.fromWire(Map<String, Object?> map, [String path = "GatheringCapacityPolicy"]) {
    _rejectUnknownFields(map, const <String>{"maxParticipants"}, path);
    return GatheringCapacityPolicy(
      maxParticipants: _requiredInt(map["maxParticipants"], '$path.maxParticipants'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "maxParticipants": maxParticipants,
  };
}

final class GatheringCapacitySlice {
  const GatheringCapacitySlice({
    required this.maxParticipants,
    required this.activeSeatCount,
    required this.invitedSeatHoldCount,
    required this.occupiedSeats,
    required this.remainingSeats,
    required this.full,
  });

  final int maxParticipants;
  final int activeSeatCount;
  final int invitedSeatHoldCount;
  final int occupiedSeats;
  final int remainingSeats;
  final bool full;

  factory GatheringCapacitySlice.fromWire(Map<String, Object?> map, [String path = "GatheringCapacitySlice"]) {
    _rejectUnknownFields(map, const <String>{"maxParticipants", "activeSeatCount", "invitedSeatHoldCount", "occupiedSeats", "remainingSeats", "full"}, path);
    return GatheringCapacitySlice(
      maxParticipants: _requiredInt(map["maxParticipants"], '$path.maxParticipants'),
      activeSeatCount: _requiredInt(map["activeSeatCount"], '$path.activeSeatCount'),
      invitedSeatHoldCount: _requiredInt(map["invitedSeatHoldCount"], '$path.invitedSeatHoldCount'),
      occupiedSeats: _requiredInt(map["occupiedSeats"], '$path.occupiedSeats'),
      remainingSeats: _requiredInt(map["remainingSeats"], '$path.remainingSeats'),
      full: _requiredBool(map["full"], '$path.full'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "maxParticipants": maxParticipants,
    "activeSeatCount": activeSeatCount,
    "invitedSeatHoldCount": invitedSeatHoldCount,
    "occupiedSeats": occupiedSeats,
    "remainingSeats": remainingSeats,
    "full": full,
  };
}

final class GatheringCommandResult {
  const GatheringCommandResult({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.lifecycleStatus,
    this.participationState,
    this.participationVersion,
    this.currentGatheringRevisionId,
    required this.currentGatheringRevisionNumber,
    this.outcomeStatus,
    this.conversationId,
    required this.roomBindingStatus,
    required this.idempotentReplay,
  });

  final String gatheringId;
  final int aggregateVersion;
  final GatheringLifecycleStatus lifecycleStatus;
  final GatheringParticipationState? participationState;
  final int? participationVersion;
  final String? currentGatheringRevisionId;
  final int currentGatheringRevisionNumber;
  final GatheringOutcomeStatus? outcomeStatus;
  final String? conversationId;
  final GatheringRoomBindingStatus roomBindingStatus;
  final bool idempotentReplay;

  factory GatheringCommandResult.fromWire(Map<String, Object?> map, [String path = "GatheringCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"gatheringId", "aggregateVersion", "lifecycleStatus", "participationState", "participationVersion", "currentGatheringRevisionId", "currentGatheringRevisionNumber", "outcomeStatus", "conversationId", "roomBindingStatus", "idempotentReplay"}, path);
    return GatheringCommandResult(
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      aggregateVersion: _requiredInt(map["aggregateVersion"], '$path.aggregateVersion'),
      lifecycleStatus: GatheringLifecycleStatus.fromWire(map["lifecycleStatus"], '$path.lifecycleStatus'),
      participationState: map["participationState"] == null ? null : GatheringParticipationState.fromWire(map["participationState"], '$path.participationState'),
      participationVersion: map["participationVersion"] == null ? null : _requiredInt(map["participationVersion"], '$path.participationVersion'),
      currentGatheringRevisionId: map["currentGatheringRevisionId"] == null ? null : _requiredString(map["currentGatheringRevisionId"], '$path.currentGatheringRevisionId'),
      currentGatheringRevisionNumber: _requiredInt(map["currentGatheringRevisionNumber"], '$path.currentGatheringRevisionNumber'),
      outcomeStatus: map["outcomeStatus"] == null ? null : GatheringOutcomeStatus.fromWire(map["outcomeStatus"], '$path.outcomeStatus'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
      roomBindingStatus: GatheringRoomBindingStatus.fromWire(map["roomBindingStatus"], '$path.roomBindingStatus'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": gatheringId,
    "aggregateVersion": aggregateVersion,
    "lifecycleStatus": lifecycleStatus.wireName,
    if (participationState != null) "participationState": participationState!.wireName,
    if (participationVersion != null) "participationVersion": participationVersion!,
    if (currentGatheringRevisionId != null) "currentGatheringRevisionId": currentGatheringRevisionId!,
    "currentGatheringRevisionNumber": currentGatheringRevisionNumber,
    if (outcomeStatus != null) "outcomeStatus": outcomeStatus!.wireName,
    if (conversationId != null) "conversationId": conversationId!,
    "roomBindingStatus": roomBindingStatus.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class GatheringDisclosurePolicy {
  const GatheringDisclosurePolicy({
    required this.timeDisclosure,
    required this.placeDisclosure,
    required this.rosterDisclosure,
  });

  final GatheringTimeDisclosure timeDisclosure;
  final GatheringPlaceDisclosure placeDisclosure;
  final GatheringRosterDisclosure rosterDisclosure;

  factory GatheringDisclosurePolicy.fromWire(Map<String, Object?> map, [String path = "GatheringDisclosurePolicy"]) {
    _rejectUnknownFields(map, const <String>{"timeDisclosure", "placeDisclosure", "rosterDisclosure"}, path);
    return GatheringDisclosurePolicy(
      timeDisclosure: GatheringTimeDisclosure.fromWire(map["timeDisclosure"], '$path.timeDisclosure'),
      placeDisclosure: GatheringPlaceDisclosure.fromWire(map["placeDisclosure"], '$path.placeDisclosure'),
      rosterDisclosure: GatheringRosterDisclosure.fromWire(map["rosterDisclosure"], '$path.rosterDisclosure'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "timeDisclosure": timeDisclosure.wireName,
    "placeDisclosure": placeDisclosure.wireName,
    "rosterDisclosure": rosterDisclosure.wireName,
  };
}

final class GatheringHostSummarySlice {
  const GatheringHostSummarySlice({
    required this.hostSubjectKind,
    required this.hostSubjectId,
    required this.hostDigest,
  });

  final GatheringHostSubjectKind hostSubjectKind;
  final String hostSubjectId;
  final String hostDigest;

  factory GatheringHostSummarySlice.fromWire(Map<String, Object?> map, [String path = "GatheringHostSummarySlice"]) {
    _rejectUnknownFields(map, const <String>{"hostSubjectKind", "hostSubjectId", "hostDigest"}, path);
    return GatheringHostSummarySlice(
      hostSubjectKind: GatheringHostSubjectKind.fromWire(map["hostSubjectKind"], '$path.hostSubjectKind'),
      hostSubjectId: _requiredString(map["hostSubjectId"], '$path.hostSubjectId'),
      hostDigest: _requiredString(map["hostDigest"], '$path.hostDigest'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hostSubjectKind": hostSubjectKind.wireName,
    "hostSubjectId": hostSubjectId,
    "hostDigest": hostDigest,
  };
}

final class GatheringOutcome {
  const GatheringOutcome({
    required this.status,
    required this.independentEvidenceCount,
    required this.evidenceRefs,
    required this.calculatedAt,
    required this.calculationDigest,
  });

  final GatheringOutcomeStatus status;
  final int independentEvidenceCount;
  final List<CanonicalObjectRef> evidenceRefs;
  final DateTime calculatedAt;
  final String calculationDigest;

  factory GatheringOutcome.fromWire(Map<String, Object?> map, [String path = "GatheringOutcome"]) {
    _rejectUnknownFields(map, const <String>{"status", "independentEvidenceCount", "evidenceRefs", "calculatedAt", "calculationDigest"}, path);
    return GatheringOutcome(
      status: GatheringOutcomeStatus.fromWire(map["status"], '$path.status'),
      independentEvidenceCount: _requiredInt(map["independentEvidenceCount"], '$path.independentEvidenceCount'),
      evidenceRefs: List<CanonicalObjectRef>.unmodifiable(_requiredBoundedList(map["evidenceRefs"], '$path.evidenceRefs', max: 32).asMap().entries.map((entry) => CanonicalObjectRef.fromWire(_requiredObject(entry.value, '$path.evidenceRefs' + '[${entry.key}]'), '$path.evidenceRefs' + '[${entry.key}]'))),
      calculatedAt: _requiredTimestamp(map["calculatedAt"], '$path.calculatedAt'),
      calculationDigest: _requiredNonBlankString(map["calculationDigest"], '$path.calculationDigest'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status.wireName,
    "independentEvidenceCount": independentEvidenceCount,
    "evidenceRefs": evidenceRefs.map((value) => value.toWire()).toList(growable: false),
    "calculatedAt": calculatedAt.toUtc().toIso8601String(),
    "calculationDigest": calculationDigest,
  };
}

final class GatheringPlace {
  const GatheringPlace({
    required this.mode,
    this.coarsePlaceRef,
    this.coarsePlaceLabel,
    this.exactMeetingPoint,
    this.onlineLocationRef,
  });

  final GatheringPlaceMode mode;
  final CanonicalObjectRef? coarsePlaceRef;
  final String? coarsePlaceLabel;
  final String? exactMeetingPoint;
  final String? onlineLocationRef;

  factory GatheringPlace.fromWire(Map<String, Object?> map, [String path = "GatheringPlace"]) {
    _rejectUnknownFields(map, const <String>{"mode", "coarsePlaceRef", "coarsePlaceLabel", "exactMeetingPoint", "onlineLocationRef"}, path);
    return GatheringPlace(
      mode: GatheringPlaceMode.fromWire(map["mode"], '$path.mode'),
      coarsePlaceRef: map["coarsePlaceRef"] == null ? null : CanonicalObjectRef.fromWire(_requiredObject(map["coarsePlaceRef"], '$path.coarsePlaceRef'), '$path.coarsePlaceRef'),
      coarsePlaceLabel: map["coarsePlaceLabel"] == null ? null : _requiredString(map["coarsePlaceLabel"], '$path.coarsePlaceLabel'),
      exactMeetingPoint: map["exactMeetingPoint"] == null ? null : _requiredString(map["exactMeetingPoint"], '$path.exactMeetingPoint'),
      onlineLocationRef: map["onlineLocationRef"] == null ? null : _requiredString(map["onlineLocationRef"], '$path.onlineLocationRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mode": mode.wireName,
    if (coarsePlaceRef != null) "coarsePlaceRef": coarsePlaceRef!.toWire(),
    if (coarsePlaceLabel != null) "coarsePlaceLabel": coarsePlaceLabel!,
    if (exactMeetingPoint != null) "exactMeetingPoint": exactMeetingPoint!,
    if (onlineLocationRef != null) "onlineLocationRef": onlineLocationRef!,
  };
}

final class GatheringPolicySet {
  const GatheringPolicySet({
    required this.audiencePolicy,
    required this.admissionPolicy,
    required this.capacityPolicy,
    required this.disclosurePolicy,
    required this.applicationQuestions,
    required this.riskControlPolicyRef,
    this.policyDecisionRef,
    this.policyDigest,
    this.obligationDigest,
  });

  final GatheringAudiencePolicy audiencePolicy;
  final GatheringAdmissionPolicy admissionPolicy;
  final GatheringCapacityPolicy capacityPolicy;
  final GatheringDisclosurePolicy disclosurePolicy;
  final List<GatheringApplicationQuestion> applicationQuestions;
  final String riskControlPolicyRef;
  final String? policyDecisionRef;
  final String? policyDigest;
  final String? obligationDigest;

  factory GatheringPolicySet.fromWire(Map<String, Object?> map, [String path = "GatheringPolicySet"]) {
    _rejectUnknownFields(map, const <String>{"audiencePolicy", "admissionPolicy", "capacityPolicy", "disclosurePolicy", "applicationQuestions", "riskControlPolicyRef", "policyDecisionRef", "policyDigest", "obligationDigest"}, path);
    return GatheringPolicySet(
      audiencePolicy: GatheringAudiencePolicy.fromWire(map["audiencePolicy"], '$path.audiencePolicy'),
      admissionPolicy: GatheringAdmissionPolicy.fromWire(map["admissionPolicy"], '$path.admissionPolicy'),
      capacityPolicy: GatheringCapacityPolicy.fromWire(_requiredObject(map["capacityPolicy"], '$path.capacityPolicy'), '$path.capacityPolicy'),
      disclosurePolicy: GatheringDisclosurePolicy.fromWire(_requiredObject(map["disclosurePolicy"], '$path.disclosurePolicy'), '$path.disclosurePolicy'),
      applicationQuestions: List<GatheringApplicationQuestion>.unmodifiable(_requiredBoundedList(map["applicationQuestions"], '$path.applicationQuestions', max: 5).asMap().entries.map((entry) => GatheringApplicationQuestion.fromWire(_requiredObject(entry.value, '$path.applicationQuestions' + '[${entry.key}]'), '$path.applicationQuestions' + '[${entry.key}]'))),
      riskControlPolicyRef: _requiredNonBlankString(map["riskControlPolicyRef"], '$path.riskControlPolicyRef'),
      policyDecisionRef: map["policyDecisionRef"] == null ? null : _requiredString(map["policyDecisionRef"], '$path.policyDecisionRef'),
      policyDigest: map["policyDigest"] == null ? null : _requiredString(map["policyDigest"], '$path.policyDigest'),
      obligationDigest: map["obligationDigest"] == null ? null : _requiredString(map["obligationDigest"], '$path.obligationDigest'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "audiencePolicy": audiencePolicy.wireName,
    "admissionPolicy": admissionPolicy.wireName,
    "capacityPolicy": capacityPolicy.toWire(),
    "disclosurePolicy": disclosurePolicy.toWire(),
    "applicationQuestions": applicationQuestions.map((value) => value.toWire()).toList(growable: false),
    "riskControlPolicyRef": riskControlPolicyRef,
    if (policyDecisionRef != null) "policyDecisionRef": policyDecisionRef!,
    if (policyDigest != null) "policyDigest": policyDigest!,
    if (obligationDigest != null) "obligationDigest": obligationDigest!,
  };
}

final class GatheringPrivateDetailSlice {
  const GatheringPrivateDetailSlice({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.createdByPersonaId,
    required this.hostBinding,
    required this.organizerAssignments,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.policySet,
    required this.admissionControl,
    required this.lifecycleStatus,
    this.outcome,
    this.conversationId,
    required this.roomBindingStatus,
    this.currentGatheringRevisionId,
    required this.currentGatheringRevisionNumber,
    required this.capacity,
    required this.temporal,
    required this.admission,
    required this.createdAt,
    required this.updatedAt,
  });

  final String gatheringId;
  final int aggregateVersion;
  final String createdByPersonaId;
  final HostBinding hostBinding;
  final List<OrganizerAssignment> organizerAssignments;
  final GatheringPurpose purpose;
  final GatheringSchedule schedule;
  final GatheringPlace place;
  final GatheringPolicySet policySet;
  final GatheringAdmissionControl admissionControl;
  final GatheringLifecycleStatus lifecycleStatus;
  final GatheringOutcome? outcome;
  final String? conversationId;
  final GatheringRoomBindingStatus roomBindingStatus;
  final String? currentGatheringRevisionId;
  final int currentGatheringRevisionNumber;
  final GatheringCapacitySlice capacity;
  final GatheringTemporalPhaseSlice temporal;
  final GatheringAdmissionStateSlice admission;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory GatheringPrivateDetailSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPrivateDetailSlice"]) {
    _rejectUnknownFields(map, const <String>{"gatheringId", "aggregateVersion", "createdByPersonaId", "hostBinding", "organizerAssignments", "purpose", "schedule", "place", "policySet", "admissionControl", "lifecycleStatus", "outcome", "conversationId", "roomBindingStatus", "currentGatheringRevisionId", "currentGatheringRevisionNumber", "capacity", "temporal", "admission", "createdAt", "updatedAt"}, path);
    return GatheringPrivateDetailSlice(
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      aggregateVersion: _requiredInt(map["aggregateVersion"], '$path.aggregateVersion'),
      createdByPersonaId: _requiredString(map["createdByPersonaId"], '$path.createdByPersonaId'),
      hostBinding: HostBinding.fromWire(_requiredObject(map["hostBinding"], '$path.hostBinding'), '$path.hostBinding'),
      organizerAssignments: List<OrganizerAssignment>.unmodifiable(_requiredList(map["organizerAssignments"], '$path.organizerAssignments').asMap().entries.map((entry) => OrganizerAssignment.fromWire(_requiredObject(entry.value, '$path.organizerAssignments' + '[${entry.key}]'), '$path.organizerAssignments' + '[${entry.key}]'))),
      purpose: GatheringPurpose.fromWire(_requiredObject(map["purpose"], '$path.purpose'), '$path.purpose'),
      schedule: GatheringSchedule.fromWire(_requiredObject(map["schedule"], '$path.schedule'), '$path.schedule'),
      place: GatheringPlace.fromWire(_requiredObject(map["place"], '$path.place'), '$path.place'),
      policySet: GatheringPolicySet.fromWire(_requiredObject(map["policySet"], '$path.policySet'), '$path.policySet'),
      admissionControl: GatheringAdmissionControl.fromWire(_requiredObject(map["admissionControl"], '$path.admissionControl'), '$path.admissionControl'),
      lifecycleStatus: GatheringLifecycleStatus.fromWire(map["lifecycleStatus"], '$path.lifecycleStatus'),
      outcome: map["outcome"] == null ? null : GatheringOutcome.fromWire(_requiredObject(map["outcome"], '$path.outcome'), '$path.outcome'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
      roomBindingStatus: GatheringRoomBindingStatus.fromWire(map["roomBindingStatus"], '$path.roomBindingStatus'),
      currentGatheringRevisionId: map["currentGatheringRevisionId"] == null ? null : _requiredString(map["currentGatheringRevisionId"], '$path.currentGatheringRevisionId'),
      currentGatheringRevisionNumber: _requiredInt(map["currentGatheringRevisionNumber"], '$path.currentGatheringRevisionNumber'),
      capacity: GatheringCapacitySlice.fromWire(_requiredObject(map["capacity"], '$path.capacity'), '$path.capacity'),
      temporal: GatheringTemporalPhaseSlice.fromWire(_requiredObject(map["temporal"], '$path.temporal'), '$path.temporal'),
      admission: GatheringAdmissionStateSlice.fromWire(_requiredObject(map["admission"], '$path.admission'), '$path.admission'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": gatheringId,
    "aggregateVersion": aggregateVersion,
    "createdByPersonaId": createdByPersonaId,
    "hostBinding": hostBinding.toWire(),
    "organizerAssignments": organizerAssignments.map((value) => value.toWire()).toList(growable: false),
    "purpose": purpose.toWire(),
    "schedule": schedule.toWire(),
    "place": place.toWire(),
    "policySet": policySet.toWire(),
    "admissionControl": admissionControl.toWire(),
    "lifecycleStatus": lifecycleStatus.wireName,
    if (outcome != null) "outcome": outcome!.toWire(),
    if (conversationId != null) "conversationId": conversationId!,
    "roomBindingStatus": roomBindingStatus.wireName,
    if (currentGatheringRevisionId != null) "currentGatheringRevisionId": currentGatheringRevisionId!,
    "currentGatheringRevisionNumber": currentGatheringRevisionNumber,
    "capacity": capacity.toWire(),
    "temporal": temporal.toWire(),
    "admission": admission.toWire(),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class GatheringPublicCardSlice {
  const GatheringPublicCardSlice({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.cardDigest,
    required this.host,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.capacity,
    required this.temporal,
    required this.admission,
    required this.lifecycleStatus,
    this.outcomeStatus,
    required this.currentGatheringRevisionId,
    required this.currentGatheringRevisionNumber,
    required this.updatedAt,
  });

  final String gatheringId;
  final int aggregateVersion;
  final String cardDigest;
  final GatheringHostSummarySlice host;
  final GatheringPublicPurposeSlice purpose;
  final GatheringPublicScheduleSlice schedule;
  final GatheringPublicPlaceSlice place;
  final GatheringCapacitySlice capacity;
  final GatheringTemporalPhaseSlice temporal;
  final GatheringAdmissionStateSlice admission;
  final GatheringLifecycleStatus lifecycleStatus;
  final GatheringOutcomeStatus? outcomeStatus;
  final String currentGatheringRevisionId;
  final int currentGatheringRevisionNumber;
  final DateTime updatedAt;

  factory GatheringPublicCardSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPublicCardSlice"]) {
    _rejectUnknownFields(map, const <String>{"gatheringId", "aggregateVersion", "cardDigest", "host", "purpose", "schedule", "place", "capacity", "temporal", "admission", "lifecycleStatus", "outcomeStatus", "currentGatheringRevisionId", "currentGatheringRevisionNumber", "updatedAt"}, path);
    return GatheringPublicCardSlice(
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      aggregateVersion: _requiredInt(map["aggregateVersion"], '$path.aggregateVersion'),
      cardDigest: _requiredString(map["cardDigest"], '$path.cardDigest'),
      host: GatheringHostSummarySlice.fromWire(_requiredObject(map["host"], '$path.host'), '$path.host'),
      purpose: GatheringPublicPurposeSlice.fromWire(_requiredObject(map["purpose"], '$path.purpose'), '$path.purpose'),
      schedule: GatheringPublicScheduleSlice.fromWire(_requiredObject(map["schedule"], '$path.schedule'), '$path.schedule'),
      place: GatheringPublicPlaceSlice.fromWire(_requiredObject(map["place"], '$path.place'), '$path.place'),
      capacity: GatheringCapacitySlice.fromWire(_requiredObject(map["capacity"], '$path.capacity'), '$path.capacity'),
      temporal: GatheringTemporalPhaseSlice.fromWire(_requiredObject(map["temporal"], '$path.temporal'), '$path.temporal'),
      admission: GatheringAdmissionStateSlice.fromWire(_requiredObject(map["admission"], '$path.admission'), '$path.admission'),
      lifecycleStatus: GatheringLifecycleStatus.fromWire(map["lifecycleStatus"], '$path.lifecycleStatus'),
      outcomeStatus: map["outcomeStatus"] == null ? null : GatheringOutcomeStatus.fromWire(map["outcomeStatus"], '$path.outcomeStatus'),
      currentGatheringRevisionId: _requiredString(map["currentGatheringRevisionId"], '$path.currentGatheringRevisionId'),
      currentGatheringRevisionNumber: _requiredInt(map["currentGatheringRevisionNumber"], '$path.currentGatheringRevisionNumber'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": gatheringId,
    "aggregateVersion": aggregateVersion,
    "cardDigest": cardDigest,
    "host": host.toWire(),
    "purpose": purpose.toWire(),
    "schedule": schedule.toWire(),
    "place": place.toWire(),
    "capacity": capacity.toWire(),
    "temporal": temporal.toWire(),
    "admission": admission.toWire(),
    "lifecycleStatus": lifecycleStatus.wireName,
    if (outcomeStatus != null) "outcomeStatus": outcomeStatus!.wireName,
    "currentGatheringRevisionId": currentGatheringRevisionId,
    "currentGatheringRevisionNumber": currentGatheringRevisionNumber,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class GatheringPublicDetailSlice {
  const GatheringPublicDetailSlice({
    required this.card,
    required this.audiencePolicy,
    required this.admissionPolicy,
    required this.disclosurePolicy,
    required this.revisions,
    this.viewerParticipationState,
    this.conversationId,
  });

  final GatheringPublicCardSlice card;
  final GatheringAudiencePolicy audiencePolicy;
  final GatheringAdmissionPolicy admissionPolicy;
  final GatheringDisclosurePolicy disclosurePolicy;
  final List<GatheringRevisionSummarySlice> revisions;
  final GatheringParticipationState? viewerParticipationState;
  final String? conversationId;

  factory GatheringPublicDetailSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPublicDetailSlice"]) {
    _rejectUnknownFields(map, const <String>{"card", "audiencePolicy", "admissionPolicy", "disclosurePolicy", "revisions", "viewerParticipationState", "conversationId"}, path);
    return GatheringPublicDetailSlice(
      card: GatheringPublicCardSlice.fromWire(_requiredObject(map["card"], '$path.card'), '$path.card'),
      audiencePolicy: GatheringAudiencePolicy.fromWire(map["audiencePolicy"], '$path.audiencePolicy'),
      admissionPolicy: GatheringAdmissionPolicy.fromWire(map["admissionPolicy"], '$path.admissionPolicy'),
      disclosurePolicy: GatheringDisclosurePolicy.fromWire(_requiredObject(map["disclosurePolicy"], '$path.disclosurePolicy'), '$path.disclosurePolicy'),
      revisions: List<GatheringRevisionSummarySlice>.unmodifiable(_requiredList(map["revisions"], '$path.revisions').asMap().entries.map((entry) => GatheringRevisionSummarySlice.fromWire(_requiredObject(entry.value, '$path.revisions' + '[${entry.key}]'), '$path.revisions' + '[${entry.key}]'))),
      viewerParticipationState: map["viewerParticipationState"] == null ? null : GatheringParticipationState.fromWire(map["viewerParticipationState"], '$path.viewerParticipationState'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "card": card.toWire(),
    "audiencePolicy": audiencePolicy.wireName,
    "admissionPolicy": admissionPolicy.wireName,
    "disclosurePolicy": disclosurePolicy.toWire(),
    "revisions": revisions.map((value) => value.toWire()).toList(growable: false),
    if (viewerParticipationState != null) "viewerParticipationState": viewerParticipationState!.wireName,
    if (conversationId != null) "conversationId": conversationId!,
  };
}

final class GatheringPublicPlaceSlice {
  const GatheringPublicPlaceSlice({
    required this.mode,
    this.coarsePlaceRef,
    this.coarsePlaceLabel,
    this.exactMeetingPoint,
  });

  final GatheringPlaceMode mode;
  final CanonicalObjectRef? coarsePlaceRef;
  final String? coarsePlaceLabel;
  final String? exactMeetingPoint;

  factory GatheringPublicPlaceSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPublicPlaceSlice"]) {
    _rejectUnknownFields(map, const <String>{"mode", "coarsePlaceRef", "coarsePlaceLabel", "exactMeetingPoint"}, path);
    return GatheringPublicPlaceSlice(
      mode: GatheringPlaceMode.fromWire(map["mode"], '$path.mode'),
      coarsePlaceRef: map["coarsePlaceRef"] == null ? null : CanonicalObjectRef.fromWire(_requiredObject(map["coarsePlaceRef"], '$path.coarsePlaceRef'), '$path.coarsePlaceRef'),
      coarsePlaceLabel: map["coarsePlaceLabel"] == null ? null : _requiredString(map["coarsePlaceLabel"], '$path.coarsePlaceLabel'),
      exactMeetingPoint: map["exactMeetingPoint"] == null ? null : _requiredString(map["exactMeetingPoint"], '$path.exactMeetingPoint'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mode": mode.wireName,
    if (coarsePlaceRef != null) "coarsePlaceRef": coarsePlaceRef!.toWire(),
    if (coarsePlaceLabel != null) "coarsePlaceLabel": coarsePlaceLabel!,
    if (exactMeetingPoint != null) "exactMeetingPoint": exactMeetingPoint!,
  };
}

final class GatheringPublicPurposeSlice {
  const GatheringPublicPurposeSlice({
    required this.title,
    this.summary,
    this.coverRef,
    required this.topicRefs,
    required this.requirementRefs,
    required this.costNotice,
    this.costDescription,
  });

  final String title;
  final String? summary;
  final CanonicalObjectRef? coverRef;
  final List<String> topicRefs;
  final List<String> requirementRefs;
  final GatheringCostNotice costNotice;
  final String? costDescription;

  factory GatheringPublicPurposeSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPublicPurposeSlice"]) {
    _rejectUnknownFields(map, const <String>{"title", "summary", "coverRef", "topicRefs", "requirementRefs", "costNotice", "costDescription"}, path);
    return GatheringPublicPurposeSlice(
      title: _requiredString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      coverRef: map["coverRef"] == null ? null : CanonicalObjectRef.fromWire(_requiredObject(map["coverRef"], '$path.coverRef'), '$path.coverRef'),
      topicRefs: List<String>.unmodifiable(_requiredList(map["topicRefs"], '$path.topicRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.topicRefs' + '[${entry.key}]'))),
      requirementRefs: List<String>.unmodifiable(_requiredList(map["requirementRefs"], '$path.requirementRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.requirementRefs' + '[${entry.key}]'))),
      costNotice: GatheringCostNotice.fromWire(map["costNotice"], '$path.costNotice'),
      costDescription: map["costDescription"] == null ? null : _requiredString(map["costDescription"], '$path.costDescription'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "title": title,
    if (summary != null) "summary": summary!,
    if (coverRef != null) "coverRef": coverRef!.toWire(),
    "topicRefs": topicRefs.map((value) => value).toList(growable: false),
    "requirementRefs": requirementRefs.map((value) => value).toList(growable: false),
    "costNotice": costNotice.wireName,
    if (costDescription != null) "costDescription": costDescription!,
  };
}

final class GatheringPublicScheduleSlice {
  const GatheringPublicScheduleSlice({
    required this.timezone,
    this.startAt,
    this.endAt,
    this.dateLabel,
  });

  final String timezone;
  final DateTime? startAt;
  final DateTime? endAt;
  final String? dateLabel;

  factory GatheringPublicScheduleSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPublicScheduleSlice"]) {
    _rejectUnknownFields(map, const <String>{"timezone", "startAt", "endAt", "dateLabel"}, path);
    return GatheringPublicScheduleSlice(
      timezone: _requiredString(map["timezone"], '$path.timezone'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      dateLabel: map["dateLabel"] == null ? null : _requiredString(map["dateLabel"], '$path.dateLabel'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "timezone": timezone,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (dateLabel != null) "dateLabel": dateLabel!,
  };
}

final class GatheringPurpose {
  const GatheringPurpose({
    this.title,
    this.summary,
    this.coverRef,
    required this.topicRefs,
    required this.requirementRefs,
    required this.sourceObjectRefs,
    required this.costNotice,
    this.costDescription,
  });

  final String? title;
  final String? summary;
  final CanonicalObjectRef? coverRef;
  final List<String> topicRefs;
  final List<String> requirementRefs;
  final List<GatheringSourceRef> sourceObjectRefs;
  final GatheringCostNotice costNotice;
  final String? costDescription;

  factory GatheringPurpose.fromWire(Map<String, Object?> map, [String path = "GatheringPurpose"]) {
    _rejectUnknownFields(map, const <String>{"title", "summary", "coverRef", "topicRefs", "requirementRefs", "sourceObjectRefs", "costNotice", "costDescription"}, path);
    return GatheringPurpose(
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      coverRef: map["coverRef"] == null ? null : CanonicalObjectRef.fromWire(_requiredObject(map["coverRef"], '$path.coverRef'), '$path.coverRef'),
      topicRefs: List<String>.unmodifiable(_requiredBoundedList(map["topicRefs"], '$path.topicRefs', max: 32).asMap().entries.map((entry) => _requiredString(entry.value, '$path.topicRefs' + '[${entry.key}]'))),
      requirementRefs: List<String>.unmodifiable(_requiredBoundedList(map["requirementRefs"], '$path.requirementRefs', max: 32).asMap().entries.map((entry) => _requiredString(entry.value, '$path.requirementRefs' + '[${entry.key}]'))),
      sourceObjectRefs: List<GatheringSourceRef>.unmodifiable(_requiredBoundedList(map["sourceObjectRefs"], '$path.sourceObjectRefs', max: 16).asMap().entries.map((entry) => GatheringSourceRef.fromWire(_requiredObject(entry.value, '$path.sourceObjectRefs' + '[${entry.key}]'), '$path.sourceObjectRefs' + '[${entry.key}]'))),
      costNotice: GatheringCostNotice.fromWire(map["costNotice"], '$path.costNotice'),
      costDescription: map["costDescription"] == null ? null : _requiredString(map["costDescription"], '$path.costDescription'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (title != null) "title": title!,
    if (summary != null) "summary": summary!,
    if (coverRef != null) "coverRef": coverRef!.toWire(),
    "topicRefs": topicRefs.map((value) => value).toList(growable: false),
    "requirementRefs": requirementRefs.map((value) => value).toList(growable: false),
    "sourceObjectRefs": sourceObjectRefs.map((value) => value.toWire()).toList(growable: false),
    "costNotice": costNotice.wireName,
    if (costDescription != null) "costDescription": costDescription!,
  };
}

final class GatheringRevisionSummarySlice {
  const GatheringRevisionSummarySlice({
    required this.revisionId,
    required this.revisionNumber,
    required this.digest,
    required this.materialChange,
    required this.createdAt,
  });

  final String revisionId;
  final int revisionNumber;
  final String digest;
  final bool materialChange;
  final DateTime createdAt;

  factory GatheringRevisionSummarySlice.fromWire(Map<String, Object?> map, [String path = "GatheringRevisionSummarySlice"]) {
    _rejectUnknownFields(map, const <String>{"revisionId", "revisionNumber", "digest", "materialChange", "createdAt"}, path);
    return GatheringRevisionSummarySlice(
      revisionId: _requiredString(map["revisionId"], '$path.revisionId'),
      revisionNumber: _requiredInt(map["revisionNumber"], '$path.revisionNumber'),
      digest: _requiredString(map["digest"], '$path.digest'),
      materialChange: _requiredBool(map["materialChange"], '$path.materialChange'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "revisionId": revisionId,
    "revisionNumber": revisionNumber,
    "digest": digest,
    "materialChange": materialChange,
    "createdAt": createdAt.toUtc().toIso8601String(),
  };
}

final class GatheringSchedule {
  const GatheringSchedule({
    this.timezone,
    this.startAt,
    this.endAt,
    this.admissionClosesAt,
  });

  final String? timezone;
  final DateTime? startAt;
  final DateTime? endAt;
  final DateTime? admissionClosesAt;

  factory GatheringSchedule.fromWire(Map<String, Object?> map, [String path = "GatheringSchedule"]) {
    _rejectUnknownFields(map, const <String>{"timezone", "startAt", "endAt", "admissionClosesAt"}, path);
    return GatheringSchedule(
      timezone: map["timezone"] == null ? null : _requiredString(map["timezone"], '$path.timezone'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      admissionClosesAt: map["admissionClosesAt"] == null ? null : _requiredTimestamp(map["admissionClosesAt"], '$path.admissionClosesAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (timezone != null) "timezone": timezone!,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (admissionClosesAt != null) "admissionClosesAt": admissionClosesAt!.toUtc().toIso8601String(),
  };
}

final class GatheringSourceRef {
  const GatheringSourceRef({
    required this.objectRef,
    required this.routeId,
    required this.sourceDigest,
  });

  final CanonicalObjectRef objectRef;
  final String routeId;
  final String sourceDigest;

  factory GatheringSourceRef.fromWire(Map<String, Object?> map, [String path = "GatheringSourceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectRef", "routeId", "sourceDigest"}, path);
    return GatheringSourceRef(
      objectRef: CanonicalObjectRef.fromWire(_requiredObject(map["objectRef"], '$path.objectRef'), '$path.objectRef'),
      routeId: _requiredNonBlankString(map["routeId"], '$path.routeId'),
      sourceDigest: _requiredNonBlankString(map["sourceDigest"], '$path.sourceDigest'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectRef": objectRef.toWire(),
    "routeId": routeId,
    "sourceDigest": sourceDigest,
  };
}

final class GatheringTemporalPhaseSlice {
  const GatheringTemporalPhaseSlice({
    required this.temporalPhase,
    required this.evaluatedAt,
  });

  final GatheringTemporalPhase temporalPhase;
  final DateTime evaluatedAt;

  factory GatheringTemporalPhaseSlice.fromWire(Map<String, Object?> map, [String path = "GatheringTemporalPhaseSlice"]) {
    _rejectUnknownFields(map, const <String>{"temporalPhase", "evaluatedAt"}, path);
    return GatheringTemporalPhaseSlice(
      temporalPhase: GatheringTemporalPhase.fromWire(map["temporalPhase"], '$path.temporalPhase'),
      evaluatedAt: _requiredTimestamp(map["evaluatedAt"], '$path.evaluatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "temporalPhase": temporalPhase.wireName,
    "evaluatedAt": evaluatedAt.toUtc().toIso8601String(),
  };
}

final class HostBinding {
  const HostBinding({
    required this.hostSubjectKind,
    required this.hostSubjectId,
    required this.authorityEvidenceRef,
    required this.authorityVersion,
    this.authorityExpiresAt,
  });

  final GatheringHostSubjectKind hostSubjectKind;
  final String hostSubjectId;
  final String authorityEvidenceRef;
  final int authorityVersion;
  final DateTime? authorityExpiresAt;

  factory HostBinding.fromWire(Map<String, Object?> map, [String path = "HostBinding"]) {
    _rejectUnknownFields(map, const <String>{"hostSubjectKind", "hostSubjectId", "authorityEvidenceRef", "authorityVersion", "authorityExpiresAt"}, path);
    return HostBinding(
      hostSubjectKind: GatheringHostSubjectKind.fromWire(map["hostSubjectKind"], '$path.hostSubjectKind'),
      hostSubjectId: _requiredNonBlankString(map["hostSubjectId"], '$path.hostSubjectId'),
      authorityEvidenceRef: _requiredNonBlankString(map["authorityEvidenceRef"], '$path.authorityEvidenceRef'),
      authorityVersion: _requiredInt(map["authorityVersion"], '$path.authorityVersion'),
      authorityExpiresAt: map["authorityExpiresAt"] == null ? null : _requiredTimestamp(map["authorityExpiresAt"], '$path.authorityExpiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hostSubjectKind": hostSubjectKind.wireName,
    "hostSubjectId": hostSubjectId,
    "authorityEvidenceRef": authorityEvidenceRef,
    "authorityVersion": authorityVersion,
    if (authorityExpiresAt != null) "authorityExpiresAt": authorityExpiresAt!.toUtc().toIso8601String(),
  };
}

final class OrganizerAssignment {
  const OrganizerAssignment({
    required this.personaId,
    required this.role,
    required this.authorityEvidenceRef,
    required this.authorityVersion,
    required this.assignedAt,
    this.revokedAt,
    required this.version,
  });

  final String personaId;
  final GatheringOrganizerRole role;
  final String authorityEvidenceRef;
  final int authorityVersion;
  final DateTime assignedAt;
  final DateTime? revokedAt;
  final int version;

  factory OrganizerAssignment.fromWire(Map<String, Object?> map, [String path = "OrganizerAssignment"]) {
    _rejectUnknownFields(map, const <String>{"personaId", "role", "authorityEvidenceRef", "authorityVersion", "assignedAt", "revokedAt", "version"}, path);
    return OrganizerAssignment(
      personaId: _requiredNonBlankString(map["personaId"], '$path.personaId'),
      role: GatheringOrganizerRole.fromWire(map["role"], '$path.role'),
      authorityEvidenceRef: _requiredNonBlankString(map["authorityEvidenceRef"], '$path.authorityEvidenceRef'),
      authorityVersion: _requiredInt(map["authorityVersion"], '$path.authorityVersion'),
      assignedAt: _requiredTimestamp(map["assignedAt"], '$path.assignedAt'),
      revokedAt: map["revokedAt"] == null ? null : _requiredTimestamp(map["revokedAt"], '$path.revokedAt'),
      version: _requiredInt(map["version"], '$path.version'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": personaId,
    "role": role.wireName,
    "authorityEvidenceRef": authorityEvidenceRef,
    "authorityVersion": authorityVersion,
    "assignedAt": assignedAt.toUtc().toIso8601String(),
    if (revokedAt != null) "revokedAt": revokedAt!.toUtc().toIso8601String(),
    "version": version,
  };
}

final class PersonaCirclePageSlice {
  const PersonaCirclePageSlice({
    required this.items,
    this.cursor,
  });

  final List<PersonaCircleSlice> items;
  final String? cursor;

  factory PersonaCirclePageSlice.fromWire(Map<String, Object?> map, [String path = "PersonaCirclePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "cursor"}, path);
    return PersonaCirclePageSlice(
      items: List<PersonaCircleSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => PersonaCircleSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      cursor: map["cursor"] == null ? null : _requiredString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (cursor != null) "cursor": cursor!,
  };
}

final class PersonaCircleSlice {
  const PersonaCircleSlice({
    required this.circleId,
    required this.name,
    this.description,
    this.coverUrl,
    this.iconUrl,
    required this.ownerPersonaId,
    this.ownerDisplayNameSnapshot,
    this.category,
    this.subCategory,
    this.tags,
    required this.memberCount,
    required this.postCount,
    required this.weeklyActiveCount,
    required this.status,
    required this.visibility,
    required this.joinPolicy,
    required this.kind,
    required this.displaySubjectType,
    required this.followEnabled,
    this.defaultPublicGroupId,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
    required this.createdAt,
    required this.updatedAt,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? iconUrl;
  final String ownerPersonaId;
  final String? ownerDisplayNameSnapshot;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final CircleStatus status;
  final CircleVisibility visibility;
  final CircleJoinPolicy joinPolicy;
  final CircleKind kind;
  final CircleDisplaySubjectType displaySubjectType;
  final bool followEnabled;
  final String? defaultPublicGroupId;
  final String? linkedHomepageId;
  final HomepageType? linkedHomepageType;
  final String? linkedHomepageTitle;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory PersonaCircleSlice.fromWire(Map<String, Object?> map, [String path = "PersonaCircleSlice"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "name", "description", "coverUrl", "iconUrl", "ownerPersonaId", "ownerDisplayNameSnapshot", "category", "subCategory", "tags", "memberCount", "postCount", "weeklyActiveCount", "status", "visibility", "joinPolicy", "kind", "displaySubjectType", "followEnabled", "defaultPublicGroupId", "linkedHomepageId", "linkedHomepageType", "linkedHomepageTitle", "createdAt", "updatedAt"}, path);
    return PersonaCircleSlice(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      name: _requiredString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      iconUrl: map["iconUrl"] == null ? null : _requiredString(map["iconUrl"], '$path.iconUrl'),
      ownerPersonaId: _requiredString(map["ownerPersonaId"], '$path.ownerPersonaId'),
      ownerDisplayNameSnapshot: map["ownerDisplayNameSnapshot"] == null ? null : _requiredString(map["ownerDisplayNameSnapshot"], '$path.ownerDisplayNameSnapshot'),
      category: map["category"] == null ? null : _requiredString(map["category"], '$path.category'),
      subCategory: map["subCategory"] == null ? null : _requiredString(map["subCategory"], '$path.subCategory'),
      tags: map["tags"] == null ? null : List<String>.unmodifiable(_requiredList(map["tags"], '$path.tags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tags' + '[${entry.key}]'))),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      postCount: _requiredInt(map["postCount"], '$path.postCount'),
      weeklyActiveCount: _requiredInt(map["weeklyActiveCount"], '$path.weeklyActiveCount'),
      status: CircleStatus.fromWire(map["status"], '$path.status'),
      visibility: CircleVisibility.fromWire(map["visibility"], '$path.visibility'),
      joinPolicy: CircleJoinPolicy.fromWire(map["joinPolicy"], '$path.joinPolicy'),
      kind: CircleKind.fromWire(map["kind"], '$path.kind'),
      displaySubjectType: CircleDisplaySubjectType.fromWire(map["displaySubjectType"], '$path.displaySubjectType'),
      followEnabled: _requiredBool(map["followEnabled"], '$path.followEnabled'),
      defaultPublicGroupId: map["defaultPublicGroupId"] == null ? null : _requiredString(map["defaultPublicGroupId"], '$path.defaultPublicGroupId'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _requiredString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageType: map["linkedHomepageType"] == null ? null : HomepageType.fromWire(map["linkedHomepageType"], '$path.linkedHomepageType'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _requiredString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "name": name,
    if (description != null) "description": description!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (iconUrl != null) "iconUrl": iconUrl!,
    "ownerPersonaId": ownerPersonaId,
    if (ownerDisplayNameSnapshot != null) "ownerDisplayNameSnapshot": ownerDisplayNameSnapshot!,
    if (category != null) "category": category!,
    if (subCategory != null) "subCategory": subCategory!,
    if (tags != null) "tags": tags!.map((value) => value).toList(growable: false),
    "memberCount": memberCount,
    "postCount": postCount,
    "weeklyActiveCount": weeklyActiveCount,
    "status": status.wireName,
    "visibility": visibility.wireName,
    "joinPolicy": joinPolicy.wireName,
    "kind": kind.wireName,
    "displaySubjectType": displaySubjectType.wireName,
    "followEnabled": followEnabled,
    if (defaultPublicGroupId != null) "defaultPublicGroupId": defaultPublicGroupId!,
    if (linkedHomepageId != null) "linkedHomepageId": linkedHomepageId!,
    if (linkedHomepageType != null) "linkedHomepageType": linkedHomepageType!.wireName,
    if (linkedHomepageTitle != null) "linkedHomepageTitle": linkedHomepageTitle!,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

AppendResult decodeAppendResult(Object? response) =>
    AppendResult.fromWire(_requiredObject(response, "AppendResult"), "AppendResult");

Circle decodeCircle(Object? response) =>
    Circle.fromWire(_requiredObject(response, "Circle"), "Circle");

CircleCommandResult decodeCircleCommandResult(Object? response) =>
    CircleCommandResult.fromWire(_requiredObject(response, "CircleCommandResult"), "CircleCommandResult");

CircleDiscoveryFeedPageSlice decodeCircleDiscoveryFeedPageSlice(Object? response) =>
    CircleDiscoveryFeedPageSlice.fromWire(_requiredObject(response, "CircleDiscoveryFeedPageSlice"), "CircleDiscoveryFeedPageSlice");

CircleFeedPageSlice decodeCircleFeedPageSlice(Object? response) =>
    CircleFeedPageSlice.fromWire(_requiredObject(response, "CircleFeedPageSlice"), "CircleFeedPageSlice");

CircleFileCommandResult decodeCircleFileCommandResult(Object? response) =>
    CircleFileCommandResult.fromWire(_requiredObject(response, "CircleFileCommandResult"), "CircleFileCommandResult");

CircleFilePageSlice decodeCircleFilePageSlice(Object? response) =>
    CircleFilePageSlice.fromWire(_requiredObject(response, "CircleFilePageSlice"), "CircleFilePageSlice");

CircleFileSlice decodeCircleFileSlice(Object? response) =>
    CircleFileSlice.fromWire(_requiredObject(response, "CircleFileSlice"), "CircleFileSlice");

CircleGroupCommandResult decodeCircleGroupCommandResult(Object? response) =>
    CircleGroupCommandResult.fromWire(_requiredObject(response, "CircleGroupCommandResult"), "CircleGroupCommandResult");

CircleGroupMembershipCommandResult decodeCircleGroupMembershipCommandResult(Object? response) =>
    CircleGroupMembershipCommandResult.fromWire(_requiredObject(response, "CircleGroupMembershipCommandResult"), "CircleGroupMembershipCommandResult");

CircleGroupMembershipPageSlice decodeCircleGroupMembershipPageSlice(Object? response) =>
    CircleGroupMembershipPageSlice.fromWire(_requiredObject(response, "CircleGroupMembershipPageSlice"), "CircleGroupMembershipPageSlice");

CircleGroupMembershipSlice decodeCircleGroupMembershipSlice(Object? response) =>
    CircleGroupMembershipSlice.fromWire(_requiredObject(response, "CircleGroupMembershipSlice"), "CircleGroupMembershipSlice");

CircleGroupPageSlice decodeCircleGroupPageSlice(Object? response) =>
    CircleGroupPageSlice.fromWire(_requiredObject(response, "CircleGroupPageSlice"), "CircleGroupPageSlice");

CircleGroupSlice decodeCircleGroupSlice(Object? response) =>
    CircleGroupSlice.fromWire(_requiredObject(response, "CircleGroupSlice"), "CircleGroupSlice");

CircleImpactSummary decodeCircleImpactSummary(Object? response) =>
    CircleImpactSummary.fromWire(_requiredObject(response, "CircleImpactSummary"), "CircleImpactSummary");

CircleMembershipCommandResult decodeCircleMembershipCommandResult(Object? response) =>
    CircleMembershipCommandResult.fromWire(_requiredObject(response, "CircleMembershipCommandResult"), "CircleMembershipCommandResult");

CircleMembershipPageSlice decodeCircleMembershipPageSlice(Object? response) =>
    CircleMembershipPageSlice.fromWire(_requiredObject(response, "CircleMembershipPageSlice"), "CircleMembershipPageSlice");

CircleMembershipSlice decodeCircleMembershipSlice(Object? response) =>
    CircleMembershipSlice.fromWire(_requiredObject(response, "CircleMembershipSlice"), "CircleMembershipSlice");

CirclePageSlice decodeCirclePageSlice(Object? response) =>
    CirclePageSlice.fromWire(_requiredObject(response, "CirclePageSlice"), "CirclePageSlice");

CirclePostPlacementCommandResult decodeCirclePostPlacementCommandResult(Object? response) =>
    CirclePostPlacementCommandResult.fromWire(_requiredObject(response, "CirclePostPlacementCommandResult"), "CirclePostPlacementCommandResult");

CircleSearchResultView decodeCircleSearchResultView(Object? response) =>
    CircleSearchResultView.fromWire(_requiredObject(response, "CircleSearchResultView"), "CircleSearchResultView");

CircleStatsWire decodeCircleStatsWire(Object? response) =>
    CircleStatsWire.fromWire(_requiredObject(response, "CircleStatsWire"), "CircleStatsWire");

GatheringByHostPageSlice decodeGatheringByHostPageSlice(Object? response) =>
    GatheringByHostPageSlice.fromWire(_requiredObject(response, "GatheringByHostPageSlice"), "GatheringByHostPageSlice");

GatheringBySourcePageSlice decodeGatheringBySourcePageSlice(Object? response) =>
    GatheringBySourcePageSlice.fromWire(_requiredObject(response, "GatheringBySourcePageSlice"), "GatheringBySourcePageSlice");

GatheringCommandResult decodeGatheringCommandResult(Object? response) =>
    GatheringCommandResult.fromWire(_requiredObject(response, "GatheringCommandResult"), "GatheringCommandResult");

GatheringPrivateDetailSlice decodeGatheringPrivateDetailSlice(Object? response) =>
    GatheringPrivateDetailSlice.fromWire(_requiredObject(response, "GatheringPrivateDetailSlice"), "GatheringPrivateDetailSlice");

GatheringPublicDetailSlice decodeGatheringPublicDetailSlice(Object? response) =>
    GatheringPublicDetailSlice.fromWire(_requiredObject(response, "GatheringPublicDetailSlice"), "GatheringPublicDetailSlice");

PersonaCirclePageSlice decodePersonaCirclePageSlice(Object? response) =>
    PersonaCirclePageSlice.fromWire(_requiredObject(response, "PersonaCirclePageSlice"), "PersonaCirclePageSlice");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

int _requiredPositiveInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 1) {
    throw FormatException('$path must be positive');
  }
  return result;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}

List<Object?> _requiredBoundedList(
  Object? value,
  String path, {
  required int max,
}) {
  final result = _requiredList(value, path);
  if (result.length > max) {
    throw FormatException('$path must not contain more than $max items');
  }
  return result;
}
