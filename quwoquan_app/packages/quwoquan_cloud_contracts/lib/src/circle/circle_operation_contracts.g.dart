// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 93359367b8614f01bb5e1c51e37af383332b01f117cc1c6cf39e4fdf838e49d2

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
  final String? assistantUsePolicy;
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
      assistantUsePolicy: map["assistantUsePolicy"] == null ? null : _requiredString(map["assistantUsePolicy"], '$path.assistantUsePolicy'),
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
    if (assistantUsePolicy != null) "assistantUsePolicy": assistantUsePolicy!,
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
