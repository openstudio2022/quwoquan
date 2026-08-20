// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 95157ba763f72d8c9ca28e2b2532be74f68e80772f601e4cef599f10d4d9e6dd

part of '../../../circle/circle_operation_contracts.g.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}


bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}


DateTime _generatedRequestTimestamp(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a timestamp');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be a timestamp');
  return parsed.toUtc();
}


List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class AppendCircleBehaviorFactCommand {
  AppendCircleBehaviorFactCommand({
    required String circleId,
    required BehaviorEventType eventType,
  }) : circleId = circleId.trim(),
       eventType = eventType {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;
  final BehaviorEventType eventType;

  factory AppendCircleBehaviorFactCommand.fromWire(Map<String, Object?> map, [String path = "AppendCircleBehaviorFactCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "eventType"}, path);
    return AppendCircleBehaviorFactCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      eventType: switch (map["eventType"]) { "impression" => BehaviorEventType.impression, "click" => BehaviorEventType.click, "dwell" => BehaviorEventType.dwell, "like" => BehaviorEventType.like, "dislike" => BehaviorEventType.dislike, "undo_dislike" => BehaviorEventType.undoDislike, "hide_author" => BehaviorEventType.hideAuthor, "hide_content_type" => BehaviorEventType.hideContentType, "report" => BehaviorEventType.report, "share" => BehaviorEventType.share, "comment" => BehaviorEventType.comment, "intersection_expand" => BehaviorEventType.intersectionExpand, "intersection_feedback" => BehaviorEventType.intersectionFeedback, "wishlist_add" => BehaviorEventType.wishlistAdd, "wishlist_remove" => BehaviorEventType.wishlistRemove, "skip" => BehaviorEventType.skip, "follow" => BehaviorEventType.follow, "join_circle" => BehaviorEventType.joinCircle, "leave_circle" => BehaviorEventType.leaveCircle, "add_contact" => BehaviorEventType.addContact, "author_view" => BehaviorEventType.authorView, "entity_page_view" => BehaviorEventType.entityPageView, "tag_click" => BehaviorEventType.tagClick, "content_depth" => BehaviorEventType.contentDepth, "play_progress" => BehaviorEventType.playProgress, "effective_play" => BehaviorEventType.effectivePlay, "assistant_interest" => BehaviorEventType.assistantInterest, "onboarding_interest" => BehaviorEventType.onboardingInterest, _ => throw FormatException('$path.eventType' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "eventType": this.eventType.wireName,
  };
}

final class ApplyCircleGroupMembershipCommand {
  ApplyCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;

  factory ApplyCircleGroupMembershipCommand.fromWire(Map<String, Object?> map, [String path = "ApplyCircleGroupMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId"}, path);
    return ApplyCircleGroupMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class ApplyToGatheringCommand {
  ApplyToGatheringCommand({
    required String gatheringId,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
    required List<GatheringApplicationAnswer> answers,
  }) : gatheringId = gatheringId,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion,
       answers = List.unmodifiable(answers) {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
  final List<GatheringApplicationAnswer> answers;

  factory ApplyToGatheringCommand.fromWire(Map<String, Object?> map, [String path = "ApplyToGatheringCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "expectedGatheringVersion", "expectedParticipationVersion", "answers"}, path);
    return ApplyToGatheringCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
      answers: List<GatheringApplicationAnswer>.unmodifiable(_generatedRequestList(map["answers"], '$path.answers').asMap().entries.map((entry) => GatheringApplicationAnswer.fromWire(_generatedRequestObject(entry.value, '$path.answers' + '[${entry.key}]'), '$path.answers' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
    "answers": this.answers.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ArchiveCircleCommand {
  ArchiveCircleCommand({
    required String circleId,
  }) : circleId = circleId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;

  factory ArchiveCircleCommand.fromWire(Map<String, Object?> map, [String path = "ArchiveCircleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return ArchiveCircleCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class ArchiveCircleGroupCommand {
  ArchiveCircleGroupCommand({
    required String circleId,
    required String groupId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;

  factory ArchiveCircleGroupCommand.fromWire(Map<String, Object?> map, [String path = "ArchiveCircleGroupCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId"}, path);
    return ArchiveCircleGroupCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class ChangeGatheringAdmissionCommand {
  ChangeGatheringAdmissionCommand({
    required String gatheringId,
    String? reasonRef,
    required int expectedGatheringVersion,
    required int expectedAdmissionControlVersion,
  }) : gatheringId = gatheringId,
       reasonRef = reasonRef,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedAdmissionControlVersion = expectedAdmissionControlVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final String? reasonRef;
  final int expectedGatheringVersion;
  final int expectedAdmissionControlVersion;

  factory ChangeGatheringAdmissionCommand.fromWire(Map<String, Object?> map, [String path = "ChangeGatheringAdmissionCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "reasonRef", "expectedGatheringVersion", "expectedAdmissionControlVersion"}, path);
    return ChangeGatheringAdmissionCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      reasonRef: map["reasonRef"] == null ? null : _generatedRequestString(map["reasonRef"], '$path.reasonRef'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedAdmissionControlVersion: _generatedRequestInt(map["expectedAdmissionControlVersion"], '$path.expectedAdmissionControlVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    if (this.reasonRef != null) "reasonRef": this.reasonRef!,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedAdmissionControlVersion": this.expectedAdmissionControlVersion,
  };
}

final class ChangeGatheringCapacityCommand {
  ChangeGatheringCapacityCommand({
    required String gatheringId,
    required int maxParticipants,
    required int expectedGatheringVersion,
    DateTime? acknowledgementDeadlineAt,
  }) : gatheringId = gatheringId,
       maxParticipants = maxParticipants,
       expectedGatheringVersion = expectedGatheringVersion,
       acknowledgementDeadlineAt = acknowledgementDeadlineAt {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int maxParticipants;
  final int expectedGatheringVersion;
  final DateTime? acknowledgementDeadlineAt;

  factory ChangeGatheringCapacityCommand.fromWire(Map<String, Object?> map, [String path = "ChangeGatheringCapacityCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "maxParticipants", "expectedGatheringVersion", "acknowledgementDeadlineAt"}, path);
    return ChangeGatheringCapacityCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      maxParticipants: _generatedRequestInt(map["maxParticipants"], '$path.maxParticipants'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      acknowledgementDeadlineAt: map["acknowledgementDeadlineAt"] == null ? null : _generatedRequestTimestamp(map["acknowledgementDeadlineAt"], '$path.acknowledgementDeadlineAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "maxParticipants": this.maxParticipants,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    if (this.acknowledgementDeadlineAt != null) "acknowledgementDeadlineAt": this.acknowledgementDeadlineAt!.toUtc().toIso8601String(),
  };
}

final class CircleDetailQuery {
  const CircleDetailQuery({
    required String circleId,
  }) : circleId = circleId;

  final String circleId;

  factory CircleDetailQuery.fromWire(Map<String, Object?> map, [String path = "CircleDetailQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return CircleDetailQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class CircleDiscoveryFeedQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  CircleDiscoveryFeedQuery({
    String? category,
    String? subCategory,
    CircleDiscoveryFeedScope scope = CircleDiscoveryFeedScope.recommended,
    String? cursor,
    int limit = 20,
    String sort = 'recommended',
  }) : category = category,
       subCategory = subCategory,
       scope = scope,
       cursor = cursor,
       limit = limit,
       sort = sort {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String? category;
  final String? subCategory;
  final CircleDiscoveryFeedScope scope;
  final String? cursor;
  final int limit;
  final String sort;

  factory CircleDiscoveryFeedQuery.fromWire(Map<String, Object?> map, [String path = "CircleDiscoveryFeedQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"category", "subCategory", "scope", "cursor", "limit", "sort"}, path);
    return CircleDiscoveryFeedQuery(
      category: map["category"] == null ? null : _generatedRequestString(map["category"], '$path.category'),
      subCategory: map["subCategory"] == null ? null : _generatedRequestString(map["subCategory"], '$path.subCategory'),
      scope: map.containsKey("scope") ? switch (map["scope"]) { "recommended" => CircleDiscoveryFeedScope.recommended, "mine" => CircleDiscoveryFeedScope.mine, _ => throw FormatException('$path.scope' + ' has an invalid enum value'), } : CircleDiscoveryFeedScope.recommended,
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
      sort: map.containsKey("sort") ? _generatedRequestString(map["sort"], '$path.sort') : 'recommended',
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    "scope": this.scope.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    "sort": this.sort,
  };
}

final class CircleFeedQuery {
  const CircleFeedQuery({
    required String circleId,
    String? identity,
    String? type,
    String? cursor,
    int limit = 20,
    String sort = 'latest',
  }) : circleId = circleId,
       identity = identity,
       type = type,
       cursor = cursor,
       limit = limit,
       sort = sort;

  final String circleId;
  final String? identity;
  final String? type;
  final String? cursor;
  final int limit;
  final String sort;

  factory CircleFeedQuery.fromWire(Map<String, Object?> map, [String path = "CircleFeedQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "identity", "type", "cursor", "limit", "sort"}, path);
    return CircleFeedQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      identity: map["identity"] == null ? null : _generatedRequestString(map["identity"], '$path.identity'),
      type: map["type"] == null ? null : _generatedRequestString(map["type"], '$path.type'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
      sort: map.containsKey("sort") ? _generatedRequestString(map["sort"], '$path.sort') : 'latest',
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    "sort": this.sort,
  };
}

final class CircleFileListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  CircleFileListQuery({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId),
       parentFolderId = _normalizeGeneratedOptionalText(parentFolderId),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String? cursor;
  final int limit;

  factory CircleFileListQuery.fromWire(Map<String, Object?> map, [String path = "CircleFileListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "parentFolderId", "cursor", "limit"}, path);
    return CircleFileListQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: map["groupId"] == null ? null : _generatedRequestString(map["groupId"], '$path.groupId'),
      parentFolderId: map["parentFolderId"] == null ? null : _generatedRequestString(map["parentFolderId"], '$path.parentFolderId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupId != null) "groupId": this.groupId!,
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleFileQuery {
  CircleFileQuery({
    required String circleId,
    required String fileId,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
  }

  final String circleId;
  final String fileId;

  factory CircleFileQuery.fromWire(Map<String, Object?> map, [String path = "CircleFileQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "fileId"}, path);
    return CircleFileQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      fileId: _generatedRequestString(map["fileId"], '$path.fileId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
  };
}

final class CircleGroupListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  CircleGroupListQuery({
    required String circleId,
    CircleGroupType? groupType,
    CircleGroupVisibility? visibility,
    String? parentGroupId,
    OrganizationNodeType? nodeType,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       groupType = groupType,
       visibility = visibility,
       parentGroupId = parentGroupId,
       nodeType = nodeType,
       cursor = cursor,
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final CircleGroupType? groupType;
  final CircleGroupVisibility? visibility;
  final String? parentGroupId;
  final OrganizationNodeType? nodeType;
  final String? cursor;
  final int limit;

  factory CircleGroupListQuery.fromWire(Map<String, Object?> map, [String path = "CircleGroupListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupType", "visibility", "parentGroupId", "nodeType", "cursor", "limit"}, path);
    return CircleGroupListQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupType: map["groupType"] == null ? null : switch (map["groupType"]) { "public_group" => CircleGroupType.publicGroup, "self_built" => CircleGroupType.selfBuilt, "org_node" => CircleGroupType.orgNode, _ => throw FormatException('$path.groupType' + ' has an invalid enum value'), },
      visibility: map["visibility"] == null ? null : switch (map["visibility"]) { "public" => CircleGroupVisibility.public, "private" => CircleGroupVisibility.private, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      parentGroupId: map["parentGroupId"] == null ? null : _generatedRequestString(map["parentGroupId"], '$path.parentGroupId'),
      nodeType: map["nodeType"] == null ? null : switch (map["nodeType"]) { "generic" => OrganizationNodeType.generic, "college" => OrganizationNodeType.college, "grade" => OrganizationNodeType.grade, "classroom" => OrganizationNodeType.classroom, "department" => OrganizationNodeType.department, "team" => OrganizationNodeType.team, _ => throw FormatException('$path.nodeType' + ' has an invalid enum value'), },
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupType != null) "groupType": this.groupType!.wireName,
    if (this.visibility != null) "visibility": this.visibility!.wireName,
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    if (this.nodeType != null) "nodeType": this.nodeType!.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleGroupMembershipListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  CircleGroupMembershipListQuery({
    required String circleId,
    required String groupId,
    CircleGroupMembershipState? state,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim(),
       state = state,
       cursor = cursor,
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final String groupId;
  final CircleGroupMembershipState? state;
  final String? cursor;
  final int limit;

  factory CircleGroupMembershipListQuery.fromWire(Map<String, Object?> map, [String path = "CircleGroupMembershipListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "state", "cursor", "limit"}, path);
    return CircleGroupMembershipListQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
      state: map["state"] == null ? null : switch (map["state"]) { "pending" => CircleGroupMembershipState.pending, "active" => CircleGroupMembershipState.active, "rejected" => CircleGroupMembershipState.rejected, "left" => CircleGroupMembershipState.left, "removed" => CircleGroupMembershipState.removed, _ => throw FormatException('$path.state' + ' has an invalid enum value'), },
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    if (this.state != null) "state": this.state!.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleGroupQuery {
  CircleGroupQuery({
    required String circleId,
    required String groupId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;

  factory CircleGroupQuery.fromWire(Map<String, Object?> map, [String path = "CircleGroupQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId"}, path);
    return CircleGroupQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class CircleGroupSearchQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  CircleGroupSearchQuery({
    required String circleId,
    required String query,
    CircleGroupVisibility? visibility,
    CircleGroupType? groupType,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       query = query.trim(),
       visibility = visibility,
       groupType = groupType,
       cursor = cursor,
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.query.isEmpty) {
      throw ArgumentError.value(this.query, "query", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final String query;
  final CircleGroupVisibility? visibility;
  final CircleGroupType? groupType;
  final String? cursor;
  final int limit;

  factory CircleGroupSearchQuery.fromWire(Map<String, Object?> map, [String path = "CircleGroupSearchQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "query", "visibility", "groupType", "cursor", "limit"}, path);
    return CircleGroupSearchQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      query: _generatedRequestString(map["query"], '$path.query'),
      visibility: map["visibility"] == null ? null : switch (map["visibility"]) { "public" => CircleGroupVisibility.public, "private" => CircleGroupVisibility.private, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      groupType: map["groupType"] == null ? null : switch (map["groupType"]) { "public_group" => CircleGroupType.publicGroup, "self_built" => CircleGroupType.selfBuilt, "org_node" => CircleGroupType.orgNode, _ => throw FormatException('$path.groupType' + ' has an invalid enum value'), },
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "query": this.query,
    if (this.visibility != null) "visibility": this.visibility!.wireName,
    if (this.groupType != null) "groupType": this.groupType!.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleImpactQuery {
  const CircleImpactQuery({
    required String circleId,
  }) : circleId = circleId;

  final String circleId;

  factory CircleImpactQuery.fromWire(Map<String, Object?> map, [String path = "CircleImpactQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return CircleImpactQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class CircleListQuery {
  const CircleListQuery({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
  }) : category = category,
       domainId = domainId,
       recommendFor = recommendFor,
       cursor = cursor,
       limit = limit,
       sort = sort;

  final String? category;
  final String? domainId;
  final String? recommendFor;
  final String? cursor;
  final int limit;
  final String? sort;

  factory CircleListQuery.fromWire(Map<String, Object?> map, [String path = "CircleListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"category", "domainId", "recommendFor", "cursor", "limit", "sort"}, path);
    return CircleListQuery(
      category: map["category"] == null ? null : _generatedRequestString(map["category"], '$path.category'),
      domainId: map["domainId"] == null ? null : _generatedRequestString(map["domainId"], '$path.domainId'),
      recommendFor: map["recommendFor"] == null ? null : _generatedRequestString(map["recommendFor"], '$path.recommendFor'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
      sort: map["sort"] == null ? null : _generatedRequestString(map["sort"], '$path.sort'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.category != null) "category": this.category!,
    if (this.domainId != null) "domainId": this.domainId!,
    if (this.recommendFor != null) "recommendFor": this.recommendFor!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.sort != null) "sort": this.sort!,
  };
}

final class CircleMembershipListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  CircleMembershipListQuery({
    required String circleId,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       cursor = cursor,
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final String? cursor;
  final int limit;

  factory CircleMembershipListQuery.fromWire(Map<String, Object?> map, [String path = "CircleMembershipListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "cursor", "limit"}, path);
    return CircleMembershipListQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleSearchQuery {
  const CircleSearchQuery({
    required String query,
    String? categoryId,
    String? subCategory,
    String? cursor,
    int limit = 20,
  }) : query = query,
       categoryId = categoryId,
       subCategory = subCategory,
       cursor = cursor,
       limit = limit;

  final String query;
  final String? categoryId;
  final String? subCategory;
  final String? cursor;
  final int limit;

  factory CircleSearchQuery.fromWire(Map<String, Object?> map, [String path = "CircleSearchQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"query", "categoryId", "subCategory", "cursor", "limit"}, path);
    return CircleSearchQuery(
      query: _generatedRequestString(map["query"], '$path.query'),
      categoryId: map["categoryId"] == null ? null : _generatedRequestString(map["categoryId"], '$path.categoryId'),
      subCategory: map["subCategory"] == null ? null : _generatedRequestString(map["subCategory"], '$path.subCategory'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    if (this.categoryId != null) "categoryId": this.categoryId!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleStatsQuery {
  const CircleStatsQuery({
    required String circleId,
  }) : circleId = circleId;

  final String circleId;

  factory CircleStatsQuery.fromWire(Map<String, Object?> map, [String path = "CircleStatsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return CircleStatsQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class CreateCircleCommand {
  CreateCircleCommand({
    required String name,
    String? description,
    String? rulesText,
    String? welcomeMessage,
    String? coverUrl,
    String? iconUrl,
    String? category,
    String? subCategory,
    List<String> tags = const <String>[],
    String? visibility,
    String? joinPolicy,
    String? kind,
    String? displaySubjectType,
    bool? followEnabled,
    bool? autoSyncChat,
    String? linkedHomepageId,
    String? linkedHomepageType,
    String? linkedHomepageTitle,
  }) : name = name.trim(),
       description = description,
       rulesText = rulesText,
       welcomeMessage = welcomeMessage,
       coverUrl = coverUrl,
       iconUrl = iconUrl,
       category = category,
       subCategory = subCategory,
       tags = _normalizeGeneratedTextList(tags, deduplicate: false),
       visibility = visibility,
       joinPolicy = joinPolicy,
       kind = kind,
       displaySubjectType = displaySubjectType,
       followEnabled = followEnabled,
       autoSyncChat = autoSyncChat,
       linkedHomepageId = linkedHomepageId,
       linkedHomepageType = linkedHomepageType,
       linkedHomepageTitle = linkedHomepageTitle {
    if (this.name.isEmpty) {
      throw ArgumentError.value(this.name, "name", 'must not be blank');
    }
  }

  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String> tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  factory CreateCircleCommand.fromWire(Map<String, Object?> map, [String path = "CreateCircleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"name", "description", "rulesText", "welcomeMessage", "coverUrl", "iconUrl", "category", "subCategory", "tags", "visibility", "joinPolicy", "kind", "displaySubjectType", "followEnabled", "autoSyncChat", "linkedHomepageId", "linkedHomepageType", "linkedHomepageTitle"}, path);
    return CreateCircleCommand(
      name: _generatedRequestString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _generatedRequestString(map["description"], '$path.description'),
      rulesText: map["rulesText"] == null ? null : _generatedRequestString(map["rulesText"], '$path.rulesText'),
      welcomeMessage: map["welcomeMessage"] == null ? null : _generatedRequestString(map["welcomeMessage"], '$path.welcomeMessage'),
      coverUrl: map["coverUrl"] == null ? null : _generatedRequestString(map["coverUrl"], '$path.coverUrl'),
      iconUrl: map["iconUrl"] == null ? null : _generatedRequestString(map["iconUrl"], '$path.iconUrl'),
      category: map["category"] == null ? null : _generatedRequestString(map["category"], '$path.category'),
      subCategory: map["subCategory"] == null ? null : _generatedRequestString(map["subCategory"], '$path.subCategory'),
      tags: map.containsKey("tags") ? List<String>.unmodifiable(_generatedRequestList(map["tags"], '$path.tags').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.tags' + '[${entry.key}]'))) : const <String>[],
      visibility: map["visibility"] == null ? null : _generatedRequestString(map["visibility"], '$path.visibility'),
      joinPolicy: map["joinPolicy"] == null ? null : _generatedRequestString(map["joinPolicy"], '$path.joinPolicy'),
      kind: map["kind"] == null ? null : _generatedRequestString(map["kind"], '$path.kind'),
      displaySubjectType: map["displaySubjectType"] == null ? null : _generatedRequestString(map["displaySubjectType"], '$path.displaySubjectType'),
      followEnabled: map["followEnabled"] == null ? null : _generatedRequestBool(map["followEnabled"], '$path.followEnabled'),
      autoSyncChat: map["autoSyncChat"] == null ? null : _generatedRequestBool(map["autoSyncChat"], '$path.autoSyncChat'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _generatedRequestString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageType: map["linkedHomepageType"] == null ? null : _generatedRequestString(map["linkedHomepageType"], '$path.linkedHomepageType'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _generatedRequestString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "name": this.name,
    if (this.description != null) "description": this.description!,
    if (this.rulesText != null) "rulesText": this.rulesText!,
    if (this.welcomeMessage != null) "welcomeMessage": this.welcomeMessage!,
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.iconUrl != null) "iconUrl": this.iconUrl!,
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.tags.isNotEmpty) "tags": this.tags.map((value) => value).toList(growable: false),
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.joinPolicy != null) "joinPolicy": this.joinPolicy!,
    if (this.kind != null) "kind": this.kind!,
    if (this.displaySubjectType != null) "displaySubjectType": this.displaySubjectType!,
    if (this.followEnabled != null) "followEnabled": this.followEnabled!,
    if (this.autoSyncChat != null) "autoSyncChat": this.autoSyncChat!,
    if (this.linkedHomepageId != null) "linkedHomepageId": this.linkedHomepageId!,
    if (this.linkedHomepageType != null) "linkedHomepageType": this.linkedHomepageType!,
    if (this.linkedHomepageTitle != null) "linkedHomepageTitle": this.linkedHomepageTitle!,
  };
}

final class CreateCircleFileCommand {
  CreateCircleFileCommand({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    required String name,
    required CircleFileType fileType,
    String? assetId,
  }) : circleId = circleId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId),
       parentFolderId = _normalizeGeneratedOptionalText(parentFolderId),
       name = name.trim(),
       fileType = fileType,
       assetId = _normalizeGeneratedOptionalText(assetId) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.name.isEmpty) {
      throw ArgumentError.value(this.name, "name", 'must not be blank');
    }
    if (this.fileType == CircleFileType.file && this.assetId == null) {
      throw ArgumentError.value(this.assetId, "assetId", "is required when fileType is file");
    }
    if (this.fileType != CircleFileType.file && this.assetId != null) {
      throw ArgumentError.value(this.assetId, "assetId", "is forbidden unless fileType is file");
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String name;
  final CircleFileType fileType;
  final String? assetId;

  factory CreateCircleFileCommand.fromWire(Map<String, Object?> map, [String path = "CreateCircleFileCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "parentFolderId", "name", "fileType", "assetId"}, path);
    return CreateCircleFileCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: map["groupId"] == null ? null : _generatedRequestString(map["groupId"], '$path.groupId'),
      parentFolderId: map["parentFolderId"] == null ? null : _generatedRequestString(map["parentFolderId"], '$path.parentFolderId'),
      name: _generatedRequestString(map["name"], '$path.name'),
      fileType: switch (map["fileType"]) { "file" => CircleFileType.file, "folder" => CircleFileType.folder, _ => throw FormatException('$path.fileType' + ' has an invalid enum value'), },
      assetId: map["assetId"] == null ? null : _generatedRequestString(map["assetId"], '$path.assetId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupId != null) "groupId": this.groupId!,
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    "name": this.name,
    "fileType": this.fileType.wireName,
    if (this.assetId != null) "assetId": this.assetId!,
  };
}

final class CreateCircleGroupCommand {
  CreateCircleGroupCommand({
    required String circleId,
    String? parentGroupId,
    required CircleGroupType groupType,
    OrganizationNodeType? nodeType,
    required String name,
    String description = '',
    required CircleGroupVisibility visibility,
    required CircleGroupJoinPolicy joinPolicy,
    required bool storageEnabled,
    required bool noticeEnabled,
  }) : circleId = circleId.trim(),
       parentGroupId = parentGroupId,
       groupType = groupType,
       nodeType = nodeType,
       name = name.trim(),
       description = description,
       visibility = visibility,
       joinPolicy = joinPolicy,
       storageEnabled = storageEnabled,
       noticeEnabled = noticeEnabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.name.isEmpty) {
      throw ArgumentError.value(this.name, "name", 'must not be blank');
    }
  }

  final String circleId;
  final String? parentGroupId;
  final CircleGroupType groupType;
  final OrganizationNodeType? nodeType;
  final String name;
  final String description;
  final CircleGroupVisibility visibility;
  final CircleGroupJoinPolicy joinPolicy;
  final bool storageEnabled;
  final bool noticeEnabled;

  factory CreateCircleGroupCommand.fromWire(Map<String, Object?> map, [String path = "CreateCircleGroupCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "parentGroupId", "groupType", "nodeType", "name", "description", "visibility", "joinPolicy", "storageEnabled", "noticeEnabled"}, path);
    return CreateCircleGroupCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      parentGroupId: map["parentGroupId"] == null ? null : _generatedRequestString(map["parentGroupId"], '$path.parentGroupId'),
      groupType: switch (map["groupType"]) { "public_group" => CircleGroupType.publicGroup, "self_built" => CircleGroupType.selfBuilt, "org_node" => CircleGroupType.orgNode, _ => throw FormatException('$path.groupType' + ' has an invalid enum value'), },
      nodeType: map["nodeType"] == null ? null : switch (map["nodeType"]) { "generic" => OrganizationNodeType.generic, "college" => OrganizationNodeType.college, "grade" => OrganizationNodeType.grade, "classroom" => OrganizationNodeType.classroom, "department" => OrganizationNodeType.department, "team" => OrganizationNodeType.team, _ => throw FormatException('$path.nodeType' + ' has an invalid enum value'), },
      name: _generatedRequestString(map["name"], '$path.name'),
      description: map.containsKey("description") ? _generatedRequestString(map["description"], '$path.description') : '',
      visibility: switch (map["visibility"]) { "public" => CircleGroupVisibility.public, "private" => CircleGroupVisibility.private, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      joinPolicy: switch (map["joinPolicy"]) { "apply_only" => CircleGroupJoinPolicy.applyOnly, "invite_only" => CircleGroupJoinPolicy.inviteOnly, _ => throw FormatException('$path.joinPolicy' + ' has an invalid enum value'), },
      storageEnabled: _generatedRequestBool(map["storageEnabled"], '$path.storageEnabled'),
      noticeEnabled: _generatedRequestBool(map["noticeEnabled"], '$path.noticeEnabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    "groupType": this.groupType.wireName,
    if (this.nodeType != null) "nodeType": this.nodeType!.wireName,
    "name": this.name,
    "description": this.description,
    "visibility": this.visibility.wireName,
    "joinPolicy": this.joinPolicy.wireName,
    "storageEnabled": this.storageEnabled,
    "noticeEnabled": this.noticeEnabled,
  };
}

final class CreateGatheringDraftCommand {
  const CreateGatheringDraftCommand({
    required HostBinding hostBinding,
    required bool creatorParticipates,
    required GatheringPurpose purpose,
    required GatheringSchedule schedule,
    required GatheringPlace place,
    required GatheringPolicySet policySet,
  }) : hostBinding = hostBinding,
       creatorParticipates = creatorParticipates,
       purpose = purpose,
       schedule = schedule,
       place = place,
       policySet = policySet;

  final HostBinding hostBinding;
  final bool creatorParticipates;
  final GatheringPurpose purpose;
  final GatheringSchedule schedule;
  final GatheringPlace place;
  final GatheringPolicySet policySet;

  factory CreateGatheringDraftCommand.fromWire(Map<String, Object?> map, [String path = "CreateGatheringDraftCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"hostBinding", "creatorParticipates", "purpose", "schedule", "place", "policySet"}, path);
    return CreateGatheringDraftCommand(
      hostBinding: HostBinding.fromWire(_generatedRequestObject(map["hostBinding"], '$path.hostBinding'), '$path.hostBinding'),
      creatorParticipates: _generatedRequestBool(map["creatorParticipates"], '$path.creatorParticipates'),
      purpose: GatheringPurpose.fromWire(_generatedRequestObject(map["purpose"], '$path.purpose'), '$path.purpose'),
      schedule: GatheringSchedule.fromWire(_generatedRequestObject(map["schedule"], '$path.schedule'), '$path.schedule'),
      place: GatheringPlace.fromWire(_generatedRequestObject(map["place"], '$path.place'), '$path.place'),
      policySet: GatheringPolicySet.fromWire(_generatedRequestObject(map["policySet"], '$path.policySet'), '$path.policySet'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hostBinding": this.hostBinding.toWire(),
    "creatorParticipates": this.creatorParticipates,
    "purpose": this.purpose.toWire(),
    "schedule": this.schedule.toWire(),
    "place": this.place.toWire(),
    "policySet": this.policySet.toWire(),
  };
}

final class DecideCircleGroupMembershipCommand {
  DecideCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
    required String personaId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim(),
       personaId = personaId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;
  final String personaId;

  factory DecideCircleGroupMembershipCommand.fromWire(Map<String, Object?> map, [String path = "DecideCircleGroupMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "personaId"}, path);
    return DecideCircleGroupMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
  };
}

final class DecideCircleMembershipCommand {
  DecideCircleMembershipCommand({
    required String circleId,
    required String personaId,
  }) : circleId = circleId.trim(),
       personaId = personaId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String circleId;
  final String personaId;

  factory DecideCircleMembershipCommand.fromWire(Map<String, Object?> map, [String path = "DecideCircleMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "personaId"}, path);
    return DecideCircleMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "personaId": this.personaId,
  };
}

final class DeclareGatheringAttendanceCommand {
  DeclareGatheringAttendanceCommand({
    required String gatheringId,
    required List<CanonicalObjectRef> evidenceRefs,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
  }) : gatheringId = gatheringId,
       evidenceRefs = List.unmodifiable(evidenceRefs),
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final List<CanonicalObjectRef> evidenceRefs;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory DeclareGatheringAttendanceCommand.fromWire(Map<String, Object?> map, [String path = "DeclareGatheringAttendanceCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "evidenceRefs", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return DeclareGatheringAttendanceCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      evidenceRefs: List<CanonicalObjectRef>.unmodifiable(_generatedRequestList(map["evidenceRefs"], '$path.evidenceRefs').asMap().entries.map((entry) => CanonicalObjectRef.fromWire(_generatedRequestObject(entry.value, '$path.evidenceRefs' + '[${entry.key}]'), '$path.evidenceRefs' + '[${entry.key}]'))),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "evidenceRefs": this.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
  };
}

final class DeleteCircleFileCommand {
  DeleteCircleFileCommand({
    required String circleId,
    required String fileId,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
  }

  final String circleId;
  final String fileId;

  factory DeleteCircleFileCommand.fromWire(Map<String, Object?> map, [String path = "DeleteCircleFileCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "fileId"}, path);
    return DeleteCircleFileCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      fileId: _generatedRequestString(map["fileId"], '$path.fileId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
  };
}

final class FeatureCirclePostCommand {
  FeatureCirclePostCommand({
    required String circleId,
    required String placementId,
    required bool enabled,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim(),
       enabled = enabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;
  final bool enabled;

  factory FeatureCirclePostCommand.fromWire(Map<String, Object?> map, [String path = "FeatureCirclePostCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "placementId", "enabled"}, path);
    return FeatureCirclePostCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      placementId: _generatedRequestString(map["placementId"], '$path.placementId'),
      enabled: _generatedRequestBool(map["enabled"], '$path.enabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
    "enabled": this.enabled,
  };
}

final class GatheringApplicationAnswer {
  GatheringApplicationAnswer({
    required String questionId,
    String? answerText,
    required List<String> selectedOptionIds,
  }) : questionId = questionId,
       answerText = answerText,
       selectedOptionIds = List.unmodifiable(selectedOptionIds) {
    if (this.questionId.isEmpty) {
      throw ArgumentError.value(this.questionId, "questionId", 'must not be blank');
    }
  }

  final String questionId;
  final String? answerText;
  final List<String> selectedOptionIds;

  factory GatheringApplicationAnswer.fromWire(Map<String, Object?> map, [String path = "GatheringApplicationAnswer"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"questionId", "answerText", "selectedOptionIds"}, path);
    return GatheringApplicationAnswer(
      questionId: _generatedRequestString(map["questionId"], '$path.questionId'),
      answerText: map["answerText"] == null ? null : _generatedRequestString(map["answerText"], '$path.answerText'),
      selectedOptionIds: List<String>.unmodifiable(_generatedRequestList(map["selectedOptionIds"], '$path.selectedOptionIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.selectedOptionIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "questionId": this.questionId,
    if (this.answerText != null) "answerText": this.answerText!,
    "selectedOptionIds": this.selectedOptionIds.map((value) => value).toList(growable: false),
  };
}

final class GatheringAvailabilityWatchCommand {
  GatheringAvailabilityWatchCommand({
    required String gatheringId,
    required int expectedGatheringVersion,
    required int expectedWatchVersion,
  }) : gatheringId = gatheringId,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedWatchVersion = expectedWatchVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int expectedGatheringVersion;
  final int expectedWatchVersion;

  factory GatheringAvailabilityWatchCommand.fromWire(Map<String, Object?> map, [String path = "GatheringAvailabilityWatchCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "expectedGatheringVersion", "expectedWatchVersion"}, path);
    return GatheringAvailabilityWatchCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedWatchVersion: _generatedRequestInt(map["expectedWatchVersion"], '$path.expectedWatchVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedWatchVersion": this.expectedWatchVersion,
  };
}

final class GatheringIDQuery {
  GatheringIDQuery({
    required String gatheringId,
  }) : gatheringId = gatheringId {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;

  factory GatheringIDQuery.fromWire(Map<String, Object?> map, [String path = "GatheringIDQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId"}, path);
    return GatheringIDQuery(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
  };
}

final class GatheringListByHostQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  GatheringListByHostQuery({
    required GatheringHostSubjectKind hostSubjectKind,
    required String hostSubjectId,
    String? cursor,
    int limit = 20,
  }) : hostSubjectKind = hostSubjectKind,
       hostSubjectId = hostSubjectId,
       cursor = cursor,
       limit = limit {
    if (this.hostSubjectId.isEmpty) {
      throw ArgumentError.value(this.hostSubjectId, "hostSubjectId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final GatheringHostSubjectKind hostSubjectKind;
  final String hostSubjectId;
  final String? cursor;
  final int limit;

  factory GatheringListByHostQuery.fromWire(Map<String, Object?> map, [String path = "GatheringListByHostQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"hostSubjectKind", "hostSubjectId", "cursor", "limit"}, path);
    return GatheringListByHostQuery(
      hostSubjectKind: switch (map["hostSubjectKind"]) { "persona" => GatheringHostSubjectKind.persona, "entity_homepage" => GatheringHostSubjectKind.entityHomepage, "circle" => GatheringHostSubjectKind.circle, _ => throw FormatException('$path.hostSubjectKind' + ' has an invalid enum value'), },
      hostSubjectId: _generatedRequestString(map["hostSubjectId"], '$path.hostSubjectId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hostSubjectKind": this.hostSubjectKind.wireName,
    "hostSubjectId": this.hostSubjectId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class GatheringListBySourceQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  GatheringListBySourceQuery({
    required String sourceObjectTypeRef,
    required String sourceObjectId,
    String? cursor,
    int limit = 20,
  }) : sourceObjectTypeRef = sourceObjectTypeRef,
       sourceObjectId = sourceObjectId,
       cursor = cursor,
       limit = limit {
    if (this.sourceObjectTypeRef.isEmpty) {
      throw ArgumentError.value(this.sourceObjectTypeRef, "sourceObjectTypeRef", 'must not be blank');
    }
    if (this.sourceObjectId.isEmpty) {
      throw ArgumentError.value(this.sourceObjectId, "sourceObjectId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String sourceObjectTypeRef;
  final String sourceObjectId;
  final String? cursor;
  final int limit;

  factory GatheringListBySourceQuery.fromWire(Map<String, Object?> map, [String path = "GatheringListBySourceQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"sourceObjectTypeRef", "sourceObjectId", "cursor", "limit"}, path);
    return GatheringListBySourceQuery(
      sourceObjectTypeRef: _generatedRequestString(map["sourceObjectTypeRef"], '$path.sourceObjectTypeRef'),
      sourceObjectId: _generatedRequestString(map["sourceObjectId"], '$path.sourceObjectId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sourceObjectTypeRef": this.sourceObjectTypeRef,
    "sourceObjectId": this.sourceObjectId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class GatheringMineListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  GatheringMineListQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String? cursor;
  final int limit;

  factory GatheringMineListQuery.fromWire(Map<String, Object?> map, [String path = "GatheringMineListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"cursor", "limit"}, path);
    return GatheringMineListQuery(
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class GatheringParticipationVersionCommand {
  GatheringParticipationVersionCommand({
    required String gatheringId,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
  }) : gatheringId = gatheringId,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory GatheringParticipationVersionCommand.fromWire(Map<String, Object?> map, [String path = "GatheringParticipationVersionCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return GatheringParticipationVersionCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
  };
}

final class GatheringReasonCommand {
  GatheringReasonCommand({
    required String gatheringId,
    required String reasonRef,
    required List<CanonicalObjectRef> evidenceRefs,
    required int expectedGatheringVersion,
  }) : gatheringId = gatheringId,
       reasonRef = reasonRef,
       evidenceRefs = List.unmodifiable(evidenceRefs),
       expectedGatheringVersion = expectedGatheringVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
    if (this.reasonRef.isEmpty) {
      throw ArgumentError.value(this.reasonRef, "reasonRef", 'must not be blank');
    }
  }

  final String gatheringId;
  final String reasonRef;
  final List<CanonicalObjectRef> evidenceRefs;
  final int expectedGatheringVersion;

  factory GatheringReasonCommand.fromWire(Map<String, Object?> map, [String path = "GatheringReasonCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "reasonRef", "evidenceRefs", "expectedGatheringVersion"}, path);
    return GatheringReasonCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      reasonRef: _generatedRequestString(map["reasonRef"], '$path.reasonRef'),
      evidenceRefs: List<CanonicalObjectRef>.unmodifiable(_generatedRequestList(map["evidenceRefs"], '$path.evidenceRefs').asMap().entries.map((entry) => CanonicalObjectRef.fromWire(_generatedRequestObject(entry.value, '$path.evidenceRefs' + '[${entry.key}]'), '$path.evidenceRefs' + '[${entry.key}]'))),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "reasonRef": this.reasonRef,
    "evidenceRefs": this.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
    "expectedGatheringVersion": this.expectedGatheringVersion,
  };
}

final class GatheringVersionCommand {
  GatheringVersionCommand({
    required String gatheringId,
    required int expectedGatheringVersion,
  }) : gatheringId = gatheringId,
       expectedGatheringVersion = expectedGatheringVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int expectedGatheringVersion;

  factory GatheringVersionCommand.fromWire(Map<String, Object?> map, [String path = "GatheringVersionCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "expectedGatheringVersion"}, path);
    return GatheringVersionCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "expectedGatheringVersion": this.expectedGatheringVersion,
  };
}

final class InviteToGatheringCommand {
  InviteToGatheringCommand({
    required String gatheringId,
    required String participantPersonaId,
    required DateTime seatHoldUntil,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
  }) : gatheringId = gatheringId,
       participantPersonaId = participantPersonaId,
       seatHoldUntil = seatHoldUntil,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
    if (this.participantPersonaId.isEmpty) {
      throw ArgumentError.value(this.participantPersonaId, "participantPersonaId", 'must not be blank');
    }
  }

  final String gatheringId;
  final String participantPersonaId;
  final DateTime seatHoldUntil;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory InviteToGatheringCommand.fromWire(Map<String, Object?> map, [String path = "InviteToGatheringCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "participantPersonaId", "seatHoldUntil", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return InviteToGatheringCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      participantPersonaId: _generatedRequestString(map["participantPersonaId"], '$path.participantPersonaId'),
      seatHoldUntil: _generatedRequestTimestamp(map["seatHoldUntil"], '$path.seatHoldUntil'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "participantPersonaId": this.participantPersonaId,
    "seatHoldUntil": this.seatHoldUntil.toUtc().toIso8601String(),
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
  };
}

final class JoinCircleMembershipCommand {
  JoinCircleMembershipCommand({
    required String circleId,
  }) : circleId = circleId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;

  factory JoinCircleMembershipCommand.fromWire(Map<String, Object?> map, [String path = "JoinCircleMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return JoinCircleMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class LeaveCircleGroupMembershipCommand {
  LeaveCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;

  factory LeaveCircleGroupMembershipCommand.fromWire(Map<String, Object?> map, [String path = "LeaveCircleGroupMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId"}, path);
    return LeaveCircleGroupMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class LeaveCircleMembershipCommand {
  LeaveCircleMembershipCommand({
    required String circleId,
  }) : circleId = circleId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;

  factory LeaveCircleMembershipCommand.fromWire(Map<String, Object?> map, [String path = "LeaveCircleMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return LeaveCircleMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class MyCircleGroupMembershipQuery {
  MyCircleGroupMembershipQuery({
    required String circleId,
    required String groupId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;

  factory MyCircleGroupMembershipQuery.fromWire(Map<String, Object?> map, [String path = "MyCircleGroupMembershipQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId"}, path);
    return MyCircleGroupMembershipQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class MyCircleMembershipQuery {
  MyCircleMembershipQuery({
    required String circleId,
  }) : circleId = circleId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;

  factory MyCircleMembershipQuery.fromWire(Map<String, Object?> map, [String path = "MyCircleMembershipQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId"}, path);
    return MyCircleMembershipQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class PendingCircleMembershipListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  PendingCircleMembershipListQuery({
    required String circleId,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       cursor = cursor,
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String circleId;
  final String? cursor;
  final int limit;

  factory PendingCircleMembershipListQuery.fromWire(Map<String, Object?> map, [String path = "PendingCircleMembershipListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "cursor", "limit"}, path);
    return PendingCircleMembershipListQuery(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class PersonaCircleListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  PersonaCircleListQuery({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       query = _normalizeGeneratedOptionalText(query),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String personaId;
  final String? query;
  final String? cursor;
  final int limit;

  factory PersonaCircleListQuery.fromWire(Map<String, Object?> map, [String path = "PersonaCircleListQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"personaId", "query", "cursor", "limit"}, path);
    return PersonaCircleListQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      query: map["query"] == null ? null : _generatedRequestString(map["query"], '$path.query'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    if (this.query != null) "query": this.query!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class PinCirclePostCommand {
  PinCirclePostCommand({
    required String circleId,
    required String placementId,
    required bool enabled,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim(),
       enabled = enabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;
  final bool enabled;

  factory PinCirclePostCommand.fromWire(Map<String, Object?> map, [String path = "PinCirclePostCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "placementId", "enabled"}, path);
    return PinCirclePostCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      placementId: _generatedRequestString(map["placementId"], '$path.placementId'),
      enabled: _generatedRequestBool(map["enabled"], '$path.enabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
    "enabled": this.enabled,
  };
}

final class PlaceCirclePostCommand {
  PlaceCirclePostCommand({
    required String circleId,
    required String postId,
    String? groupId,
  }) : circleId = circleId.trim(),
       postId = postId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String circleId;
  final String postId;
  final String? groupId;

  factory PlaceCirclePostCommand.fromWire(Map<String, Object?> map, [String path = "PlaceCirclePostCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "postId", "groupId"}, path);
    return PlaceCirclePostCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      groupId: map["groupId"] == null ? null : _generatedRequestString(map["groupId"], '$path.groupId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "postId": this.postId,
    if (this.groupId != null) "groupId": this.groupId!,
  };
}

final class RemoveCircleGroupMembershipCommand {
  RemoveCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
    required String personaId,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim(),
       personaId = personaId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;
  final String personaId;

  factory RemoveCircleGroupMembershipCommand.fromWire(Map<String, Object?> map, [String path = "RemoveCircleGroupMembershipCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "personaId"}, path);
    return RemoveCircleGroupMembershipCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
  };
}

final class RemoveCirclePostCommand {
  RemoveCirclePostCommand({
    required String circleId,
    required String placementId,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;

  factory RemoveCirclePostCommand.fromWire(Map<String, Object?> map, [String path = "RemoveCirclePostCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "placementId"}, path);
    return RemoveCirclePostCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      placementId: _generatedRequestString(map["placementId"], '$path.placementId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
  };
}

final class ReviewGatheringApplicationCommand {
  ReviewGatheringApplicationCommand({
    required String gatheringId,
    required String participantPersonaId,
    required GatheringApplicationReviewDecision decision,
    String? reasonRef,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
  }) : gatheringId = gatheringId,
       participantPersonaId = participantPersonaId,
       decision = decision,
       reasonRef = reasonRef,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
    if (this.participantPersonaId.isEmpty) {
      throw ArgumentError.value(this.participantPersonaId, "participantPersonaId", 'must not be blank');
    }
  }

  final String gatheringId;
  final String participantPersonaId;
  final GatheringApplicationReviewDecision decision;
  final String? reasonRef;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory ReviewGatheringApplicationCommand.fromWire(Map<String, Object?> map, [String path = "ReviewGatheringApplicationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "participantPersonaId", "decision", "reasonRef", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return ReviewGatheringApplicationCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      participantPersonaId: _generatedRequestString(map["participantPersonaId"], '$path.participantPersonaId'),
      decision: switch (map["decision"]) { "approve" => GatheringApplicationReviewDecision.approve, "reject" => GatheringApplicationReviewDecision.reject, _ => throw FormatException('$path.decision' + ' has an invalid enum value'), },
      reasonRef: map["reasonRef"] == null ? null : _generatedRequestString(map["reasonRef"], '$path.reasonRef'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "participantPersonaId": this.participantPersonaId,
    "decision": this.decision.wireName,
    if (this.reasonRef != null) "reasonRef": this.reasonRef!,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
  };
}

final class TargetGatheringParticipationCommand {
  TargetGatheringParticipationCommand({
    required String gatheringId,
    required String participantPersonaId,
    String? reasonRef,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
  }) : gatheringId = gatheringId,
       participantPersonaId = participantPersonaId,
       reasonRef = reasonRef,
       expectedGatheringVersion = expectedGatheringVersion,
       expectedParticipationVersion = expectedParticipationVersion {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
    if (this.participantPersonaId.isEmpty) {
      throw ArgumentError.value(this.participantPersonaId, "participantPersonaId", 'must not be blank');
    }
  }

  final String gatheringId;
  final String participantPersonaId;
  final String? reasonRef;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory TargetGatheringParticipationCommand.fromWire(Map<String, Object?> map, [String path = "TargetGatheringParticipationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "participantPersonaId", "reasonRef", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return TargetGatheringParticipationCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      participantPersonaId: _generatedRequestString(map["participantPersonaId"], '$path.participantPersonaId'),
      reasonRef: map["reasonRef"] == null ? null : _generatedRequestString(map["reasonRef"], '$path.reasonRef'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _generatedRequestInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "participantPersonaId": this.participantPersonaId,
    if (this.reasonRef != null) "reasonRef": this.reasonRef!,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "expectedParticipationVersion": this.expectedParticipationVersion,
  };
}

final class UpdateCircleCommand {
  UpdateCircleCommand({
    required String circleId,
    String? name,
    String? description,
    String? rulesText,
    String? welcomeMessage,
    String? coverUrl,
    String? iconUrl,
    String? category,
    String? subCategory,
    List<String>? tags,
    String? visibility,
    String? joinPolicy,
    String? kind,
    String? displaySubjectType,
    bool? followEnabled,
    bool? autoSyncChat,
    String? linkedHomepageId,
    String? linkedHomepageType,
    String? linkedHomepageTitle,
  }) : circleId = circleId.trim(),
       name = name,
       description = description,
       rulesText = rulesText,
       welcomeMessage = welcomeMessage,
       coverUrl = coverUrl,
       iconUrl = iconUrl,
       category = category,
       subCategory = subCategory,
       tags = tags == null ? null : List.unmodifiable(tags),
       visibility = visibility,
       joinPolicy = joinPolicy,
       kind = kind,
       displaySubjectType = displaySubjectType,
       followEnabled = followEnabled,
       autoSyncChat = autoSyncChat,
       linkedHomepageId = linkedHomepageId,
       linkedHomepageType = linkedHomepageType,
       linkedHomepageTitle = linkedHomepageTitle {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;
  final String? name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  factory UpdateCircleCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "name", "description", "rulesText", "welcomeMessage", "coverUrl", "iconUrl", "category", "subCategory", "tags", "visibility", "joinPolicy", "kind", "displaySubjectType", "followEnabled", "autoSyncChat", "linkedHomepageId", "linkedHomepageType", "linkedHomepageTitle"}, path);
    return UpdateCircleCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      name: map["name"] == null ? null : _generatedRequestString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _generatedRequestString(map["description"], '$path.description'),
      rulesText: map["rulesText"] == null ? null : _generatedRequestString(map["rulesText"], '$path.rulesText'),
      welcomeMessage: map["welcomeMessage"] == null ? null : _generatedRequestString(map["welcomeMessage"], '$path.welcomeMessage'),
      coverUrl: map["coverUrl"] == null ? null : _generatedRequestString(map["coverUrl"], '$path.coverUrl'),
      iconUrl: map["iconUrl"] == null ? null : _generatedRequestString(map["iconUrl"], '$path.iconUrl'),
      category: map["category"] == null ? null : _generatedRequestString(map["category"], '$path.category'),
      subCategory: map["subCategory"] == null ? null : _generatedRequestString(map["subCategory"], '$path.subCategory'),
      tags: map["tags"] == null ? null : List<String>.unmodifiable(_generatedRequestList(map["tags"], '$path.tags').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.tags' + '[${entry.key}]'))),
      visibility: map["visibility"] == null ? null : _generatedRequestString(map["visibility"], '$path.visibility'),
      joinPolicy: map["joinPolicy"] == null ? null : _generatedRequestString(map["joinPolicy"], '$path.joinPolicy'),
      kind: map["kind"] == null ? null : _generatedRequestString(map["kind"], '$path.kind'),
      displaySubjectType: map["displaySubjectType"] == null ? null : _generatedRequestString(map["displaySubjectType"], '$path.displaySubjectType'),
      followEnabled: map["followEnabled"] == null ? null : _generatedRequestBool(map["followEnabled"], '$path.followEnabled'),
      autoSyncChat: map["autoSyncChat"] == null ? null : _generatedRequestBool(map["autoSyncChat"], '$path.autoSyncChat'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _generatedRequestString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageType: map["linkedHomepageType"] == null ? null : _generatedRequestString(map["linkedHomepageType"], '$path.linkedHomepageType'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _generatedRequestString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    if (this.name != null) "name": this.name!,
    if (this.description != null) "description": this.description!,
    if (this.rulesText != null) "rulesText": this.rulesText!,
    if (this.welcomeMessage != null) "welcomeMessage": this.welcomeMessage!,
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.iconUrl != null) "iconUrl": this.iconUrl!,
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.tags != null) "tags": this.tags!.map((value) => value).toList(growable: false),
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.joinPolicy != null) "joinPolicy": this.joinPolicy!,
    if (this.kind != null) "kind": this.kind!,
    if (this.displaySubjectType != null) "displaySubjectType": this.displaySubjectType!,
    if (this.followEnabled != null) "followEnabled": this.followEnabled!,
    if (this.autoSyncChat != null) "autoSyncChat": this.autoSyncChat!,
    if (this.linkedHomepageId != null) "linkedHomepageId": this.linkedHomepageId!,
    if (this.linkedHomepageType != null) "linkedHomepageType": this.linkedHomepageType!,
    if (this.linkedHomepageTitle != null) "linkedHomepageTitle": this.linkedHomepageTitle!,
  };
}

final class UpdateCircleFileCommand {
  UpdateCircleFileCommand({
    required String circleId,
    required String fileId,
    required int expectedVersion,
    String? parentFolderId,
    String? name,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim(),
       expectedVersion = expectedVersion,
       parentFolderId = parentFolderId,
       name = name {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
    if (this.expectedVersion <= 0) {
      throw ArgumentError.value(this.expectedVersion, "expectedVersion", "must be positive");
    }
  }

  final String circleId;
  final String fileId;
  final int expectedVersion;
  final String? parentFolderId;
  final String? name;

  factory UpdateCircleFileCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleFileCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "fileId", "expectedVersion", "parentFolderId", "name"}, path);
    return UpdateCircleFileCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      fileId: _generatedRequestString(map["fileId"], '$path.fileId'),
      expectedVersion: int.parse(_generatedRequestString(map["expectedVersion"], '$path.expectedVersion')),
      parentFolderId: map["parentFolderId"] == null ? null : _generatedRequestString(map["parentFolderId"], '$path.parentFolderId'),
      name: map["name"] == null ? null : _generatedRequestString(map["name"], '$path.name'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
    "expectedVersion": '"${this.expectedVersion}"',
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    if (this.name != null) "name": this.name!,
  };
}

final class UpdateCircleGroupCommand {
  UpdateCircleGroupCommand({
    required String circleId,
    required String groupId,
    required int expectedVersion,
    String? parentGroupId,
    OrganizationNodeType? nodeType,
    String? name,
    String? description,
    CircleGroupVisibility? visibility,
    CircleGroupJoinPolicy? joinPolicy,
    bool? storageEnabled,
    bool? noticeEnabled,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim(),
       expectedVersion = expectedVersion,
       parentGroupId = parentGroupId,
       nodeType = nodeType,
       name = name,
       description = description,
       visibility = visibility,
       joinPolicy = joinPolicy,
       storageEnabled = storageEnabled,
       noticeEnabled = noticeEnabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
    if (this.expectedVersion <= 0) {
      throw ArgumentError.value(this.expectedVersion, "expectedVersion", "must be positive");
    }
  }

  final String circleId;
  final String groupId;
  final int expectedVersion;
  final String? parentGroupId;
  final OrganizationNodeType? nodeType;
  final String? name;
  final String? description;
  final CircleGroupVisibility? visibility;
  final CircleGroupJoinPolicy? joinPolicy;
  final bool? storageEnabled;
  final bool? noticeEnabled;

  factory UpdateCircleGroupCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleGroupCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "expectedVersion", "parentGroupId", "nodeType", "name", "description", "visibility", "joinPolicy", "storageEnabled", "noticeEnabled"}, path);
    return UpdateCircleGroupCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
      expectedVersion: int.parse(_generatedRequestString(map["expectedVersion"], '$path.expectedVersion')),
      parentGroupId: map["parentGroupId"] == null ? null : _generatedRequestString(map["parentGroupId"], '$path.parentGroupId'),
      nodeType: map["nodeType"] == null ? null : switch (map["nodeType"]) { "generic" => OrganizationNodeType.generic, "college" => OrganizationNodeType.college, "grade" => OrganizationNodeType.grade, "classroom" => OrganizationNodeType.classroom, "department" => OrganizationNodeType.department, "team" => OrganizationNodeType.team, _ => throw FormatException('$path.nodeType' + ' has an invalid enum value'), },
      name: map["name"] == null ? null : _generatedRequestString(map["name"], '$path.name'),
      description: map["description"] == null ? null : _generatedRequestString(map["description"], '$path.description'),
      visibility: map["visibility"] == null ? null : switch (map["visibility"]) { "public" => CircleGroupVisibility.public, "private" => CircleGroupVisibility.private, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      joinPolicy: map["joinPolicy"] == null ? null : switch (map["joinPolicy"]) { "apply_only" => CircleGroupJoinPolicy.applyOnly, "invite_only" => CircleGroupJoinPolicy.inviteOnly, _ => throw FormatException('$path.joinPolicy' + ' has an invalid enum value'), },
      storageEnabled: map["storageEnabled"] == null ? null : _generatedRequestBool(map["storageEnabled"], '$path.storageEnabled'),
      noticeEnabled: map["noticeEnabled"] == null ? null : _generatedRequestBool(map["noticeEnabled"], '$path.noticeEnabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "expectedVersion": '"${this.expectedVersion}"',
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    if (this.nodeType != null) "nodeType": this.nodeType!.wireName,
    if (this.name != null) "name": this.name!,
    if (this.description != null) "description": this.description!,
    if (this.visibility != null) "visibility": this.visibility!.wireName,
    if (this.joinPolicy != null) "joinPolicy": this.joinPolicy!.wireName,
    if (this.storageEnabled != null) "storageEnabled": this.storageEnabled!,
    if (this.noticeEnabled != null) "noticeEnabled": this.noticeEnabled!,
  };
}

final class UpdateCircleGroupMembershipRoleCommand {
  UpdateCircleGroupMembershipRoleCommand({
    required String circleId,
    required String groupId,
    required String personaId,
    required CircleGroupMembershipRole role,
  }) : circleId = circleId.trim(),
       groupId = groupId.trim(),
       personaId = personaId.trim(),
       role = role {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.groupId.isEmpty) {
      throw ArgumentError.value(this.groupId, "groupId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String circleId;
  final String groupId;
  final String personaId;
  final CircleGroupMembershipRole role;

  factory UpdateCircleGroupMembershipRoleCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleGroupMembershipRoleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "groupId", "personaId", "role"}, path);
    return UpdateCircleGroupMembershipRoleCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      groupId: _generatedRequestString(map["groupId"], '$path.groupId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      role: switch (map["role"]) { "owner" => CircleGroupMembershipRole.owner, "manager" => CircleGroupMembershipRole.manager, "member" => CircleGroupMembershipRole.member, _ => throw FormatException('$path.role' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
    "role": this.role.wireName,
  };
}

final class UpdateCircleMembershipRoleCommand {
  UpdateCircleMembershipRoleCommand({
    required String circleId,
    required String personaId,
    required CircleMemberRole role,
  }) : circleId = circleId.trim(),
       personaId = personaId.trim(),
       role = role {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String circleId;
  final String personaId;
  final CircleMemberRole role;

  factory UpdateCircleMembershipRoleCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleMembershipRoleCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "personaId", "role"}, path);
    return UpdateCircleMembershipRoleCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      role: switch (map["role"]) { "owner" => CircleMemberRole.owner, "admin" => CircleMemberRole.admin, "member" => CircleMemberRole.member, _ => throw FormatException('$path.role' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "personaId": this.personaId,
    "role": this.role.wireName,
  };
}

final class UpdateCircleSectionsCommand {
  UpdateCircleSectionsCommand({
    required String circleId,
    required List<CircleSectionConfig> sections,
  }) : circleId = circleId.trim(),
       sections = List.unmodifiable(sections) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.sections.isEmpty) {
      throw ArgumentError.value(this.sections, "sections", 'must not be blank');
    }
  }

  final String circleId;
  final List<CircleSectionConfig> sections;

  factory UpdateCircleSectionsCommand.fromWire(Map<String, Object?> map, [String path = "UpdateCircleSectionsCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"circleId", "sections"}, path);
    return UpdateCircleSectionsCommand(
      circleId: _generatedRequestString(map["circleId"], '$path.circleId'),
      sections: List<CircleSectionConfig>.unmodifiable(_generatedRequestList(map["sections"], '$path.sections').asMap().entries.map((entry) => CircleSectionConfig.fromWire(_generatedRequestObject(entry.value, '$path.sections' + '[${entry.key}]'), '$path.sections' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": this.circleId,
    "sections": this.sections.map((value) => value.toWire()).toList(growable: false),
  };
}

final class UpdateGatheringCommand {
  UpdateGatheringCommand({
    required String gatheringId,
    required int expectedGatheringVersion,
    required GatheringPurpose purpose,
    required GatheringSchedule schedule,
    required GatheringPlace place,
    required GatheringPolicySet policySet,
    required HostBinding hostBinding,
    DateTime? acknowledgementDeadlineAt,
  }) : gatheringId = gatheringId,
       expectedGatheringVersion = expectedGatheringVersion,
       purpose = purpose,
       schedule = schedule,
       place = place,
       policySet = policySet,
       hostBinding = hostBinding,
       acknowledgementDeadlineAt = acknowledgementDeadlineAt {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(this.gatheringId, "gatheringId", 'must not be blank');
    }
  }

  final String gatheringId;
  final int expectedGatheringVersion;
  final GatheringPurpose purpose;
  final GatheringSchedule schedule;
  final GatheringPlace place;
  final GatheringPolicySet policySet;
  final HostBinding hostBinding;
  final DateTime? acknowledgementDeadlineAt;

  factory UpdateGatheringCommand.fromWire(Map<String, Object?> map, [String path = "UpdateGatheringCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"gatheringId", "expectedGatheringVersion", "purpose", "schedule", "place", "policySet", "hostBinding", "acknowledgementDeadlineAt"}, path);
    return UpdateGatheringCommand(
      gatheringId: _generatedRequestString(map["gatheringId"], '$path.gatheringId'),
      expectedGatheringVersion: _generatedRequestInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      purpose: GatheringPurpose.fromWire(_generatedRequestObject(map["purpose"], '$path.purpose'), '$path.purpose'),
      schedule: GatheringSchedule.fromWire(_generatedRequestObject(map["schedule"], '$path.schedule'), '$path.schedule'),
      place: GatheringPlace.fromWire(_generatedRequestObject(map["place"], '$path.place'), '$path.place'),
      policySet: GatheringPolicySet.fromWire(_generatedRequestObject(map["policySet"], '$path.policySet'), '$path.policySet'),
      hostBinding: HostBinding.fromWire(_generatedRequestObject(map["hostBinding"], '$path.hostBinding'), '$path.hostBinding'),
      acknowledgementDeadlineAt: map["acknowledgementDeadlineAt"] == null ? null : _generatedRequestTimestamp(map["acknowledgementDeadlineAt"], '$path.acknowledgementDeadlineAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    "expectedGatheringVersion": this.expectedGatheringVersion,
    "purpose": this.purpose.toWire(),
    "schedule": this.schedule.toWire(),
    "place": this.place.toWire(),
    "policySet": this.policySet.toWire(),
    "hostBinding": this.hostBinding.toWire(),
    if (this.acknowledgementDeadlineAt != null) "acknowledgementDeadlineAt": this.acknowledgementDeadlineAt!.toUtc().toIso8601String(),
  };
}

CloudOperationRequestPayload encodeCircleCircleArchiveCircleGeneratedRequest(ArchiveCircleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleCreateCircleGeneratedRequest(CreateCircleCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "name": request.name,
      if (request.description != null) "description": request.description!,
      if (request.rulesText != null) "rulesText": request.rulesText!,
      if (request.welcomeMessage != null) "welcomeMessage": request.welcomeMessage!,
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.iconUrl != null) "iconUrl": request.iconUrl!,
      if (request.category != null) "category": request.category!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.tags.isNotEmpty) "tags": request.tags.map((value) => value).toList(growable: false),
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.joinPolicy != null) "joinPolicy": request.joinPolicy!,
      if (request.kind != null) "kind": request.kind!,
      if (request.displaySubjectType != null) "displaySubjectType": request.displaySubjectType!,
      if (request.followEnabled != null) "followEnabled": request.followEnabled!,
      if (request.autoSyncChat != null) "autoSyncChat": request.autoSyncChat!,
      if (request.linkedHomepageId != null) "linkedHomepageId": request.linkedHomepageId!,
      if (request.linkedHomepageType != null) "linkedHomepageType": request.linkedHomepageType!,
      if (request.linkedHomepageTitle != null) "linkedHomepageTitle": request.linkedHomepageTitle!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGetCircleGeneratedRequest(CircleDetailQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGetCircleFeedGeneratedRequest(CircleFeedQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.identity != null) "identity": request.identity!,
      if (request.type != null) "type": request.type!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      "sort": request.sort,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGetCircleImpactGeneratedRequest(CircleImpactQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGetCircleStatsGeneratedRequest(CircleStatsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleListCircleDiscoveryFeedGeneratedRequest(CircleDiscoveryFeedQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.category != null) "category": request.category!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      "scope": (request.scope.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      "sort": request.sort,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleListCirclesGeneratedRequest(CircleListQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.category != null) "category": request.category!,
      if (request.domainId != null) "domainId": request.domainId!,
      if (request.recommendFor != null) "recommendFor": request.recommendFor!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.sort != null) "sort": request.sort!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleSearchCirclesGeneratedRequest(CircleSearchQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "query": request.query,
      if (request.categoryId != null) "categoryId": request.categoryId!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleUpdateCircleGeneratedRequest(UpdateCircleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      if (request.name != null) "name": request.name!,
      if (request.description != null) "description": request.description!,
      if (request.rulesText != null) "rulesText": request.rulesText!,
      if (request.welcomeMessage != null) "welcomeMessage": request.welcomeMessage!,
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.iconUrl != null) "iconUrl": request.iconUrl!,
      if (request.category != null) "category": request.category!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.tags != null) "tags": request.tags!.map((value) => value).toList(growable: false),
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.joinPolicy != null) "joinPolicy": request.joinPolicy!,
      if (request.kind != null) "kind": request.kind!,
      if (request.displaySubjectType != null) "displaySubjectType": request.displaySubjectType!,
      if (request.followEnabled != null) "followEnabled": request.followEnabled!,
      if (request.autoSyncChat != null) "autoSyncChat": request.autoSyncChat!,
      if (request.linkedHomepageId != null) "linkedHomepageId": request.linkedHomepageId!,
      if (request.linkedHomepageType != null) "linkedHomepageType": request.linkedHomepageType!,
      if (request.linkedHomepageTitle != null) "linkedHomepageTitle": request.linkedHomepageTitle!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleUpdateCircleSectionsGeneratedRequest(UpdateCircleSectionsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      "sections": request.sections.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleBehaviorFactReportCircleBehaviorGeneratedRequest(AppendCircleBehaviorFactCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "circleId": request.circleId,
      "eventType": request.eventType.wireName,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileCreateCircleFileGeneratedRequest(CreateCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      if (request.groupId != null) "groupId": request.groupId!,
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      "name": request.name,
      "fileType": request.fileType.wireName,
      if (request.assetId != null) "assetId": request.assetId!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileDeleteCircleFileGeneratedRequest(DeleteCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileGetCircleFileGeneratedRequest(CircleFileQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileListCircleFilesGeneratedRequest(CircleFileListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.groupId != null) "groupId": request.groupId!,
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileUpdateCircleFileGeneratedRequest(UpdateCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
    headers: <String, String>{
      "If-Match": '"${request.expectedVersion}"',
    },
    body: <String, Object?>{
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      if (request.name != null) "name": request.name!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupArchiveCircleGroupGeneratedRequest(ArchiveCircleGroupCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupCreateCircleGroupGeneratedRequest(CreateCircleGroupCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      if (request.parentGroupId != null) "parentGroupId": request.parentGroupId!,
      "groupType": request.groupType.wireName,
      if (request.nodeType != null) "nodeType": request.nodeType!.wireName,
      "name": request.name,
      "description": request.description,
      "visibility": request.visibility.wireName,
      "joinPolicy": request.joinPolicy.wireName,
      "storageEnabled": request.storageEnabled,
      "noticeEnabled": request.noticeEnabled,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupGetCircleGroupGeneratedRequest(CircleGroupQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupListCircleGroupsGeneratedRequest(CircleGroupListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.groupType != null) "groupType": (request.groupType!.wireName).toString(),
      if (request.visibility != null) "visibility": (request.visibility!.wireName).toString(),
      if (request.parentGroupId != null) "parentGroupId": request.parentGroupId!,
      if (request.nodeType != null) "nodeType": (request.nodeType!.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupSearchCircleGroupsGeneratedRequest(CircleGroupSearchQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      "query": request.query,
      if (request.visibility != null) "visibility": (request.visibility!.wireName).toString(),
      if (request.groupType != null) "groupType": (request.groupType!.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupUpdateCircleGroupGeneratedRequest(UpdateCircleGroupCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
    headers: <String, String>{
      "If-Match": '"${request.expectedVersion}"',
    },
    body: <String, Object?>{
      if (request.parentGroupId != null) "parentGroupId": request.parentGroupId!,
      if (request.nodeType != null) "nodeType": request.nodeType!.wireName,
      if (request.name != null) "name": request.name!,
      if (request.description != null) "description": request.description!,
      if (request.visibility != null) "visibility": request.visibility!.wireName,
      if (request.joinPolicy != null) "joinPolicy": request.joinPolicy!.wireName,
      if (request.storageEnabled != null) "storageEnabled": request.storageEnabled!,
      if (request.noticeEnabled != null) "noticeEnabled": request.noticeEnabled!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipApplyJoinCircleGroupGeneratedRequest(ApplyCircleGroupMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipApproveCircleGroupMemberGeneratedRequest(DecideCircleGroupMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipGetMyCircleGroupMembershipGeneratedRequest(MyCircleGroupMembershipQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipLeaveCircleGroupGeneratedRequest(LeaveCircleGroupMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipListCircleGroupMembershipsGeneratedRequest(CircleGroupMembershipListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
    },
    queryParameters: <String, String>{
      if (request.state != null) "state": (request.state!.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipRejectCircleGroupMemberGeneratedRequest(DecideCircleGroupMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipRemoveCircleGroupMemberGeneratedRequest(RemoveCircleGroupMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleGroupMembershipUpdateCircleGroupMemberRoleGeneratedRequest(UpdateCircleGroupMembershipRoleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "groupId": request.groupId,
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "role": request.role.wireName,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipApproveCircleMemberGeneratedRequest(DecideCircleMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipGetMyCircleMembershipGeneratedRequest(MyCircleMembershipQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipJoinCircleGeneratedRequest(JoinCircleMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipLeaveCircleGeneratedRequest(LeaveCircleMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipListCircleMembershipsGeneratedRequest(CircleMembershipListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipListPendingCircleMembershipsGeneratedRequest(PendingCircleMembershipListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipListPersonaCirclesGeneratedRequest(PersonaCircleListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.query != null) "query": request.query!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipRejectCircleMemberGeneratedRequest(DecideCircleMembershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleMembershipUpdateCircleMembershipRoleGeneratedRequest(UpdateCircleMembershipRoleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "role": request.role.wireName,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementFeatureCirclePostGeneratedRequest(FeatureCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
    body: <String, Object?>{
      "enabled": request.enabled,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementPinCirclePostGeneratedRequest(PinCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
    body: <String, Object?>{
      "enabled": request.enabled,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementPlacePostInCircleGeneratedRequest(PlaceCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      "postId": request.postId,
      if (request.groupId != null) "groupId": request.groupId!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementRemovePostFromCircleGeneratedRequest(RemoveCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringAcceptGatheringInvitationGeneratedRequest(GatheringParticipationVersionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringApplyToGatheringGeneratedRequest(ApplyToGatheringCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
      "answers": request.answers.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringCancelGatheringGeneratedRequest(GatheringReasonCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "reasonRef": request.reasonRef,
      "evidenceRefs": request.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
      "expectedGatheringVersion": request.expectedGatheringVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringChangeGatheringCapacityGeneratedRequest(ChangeGatheringCapacityCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "maxParticipants": request.maxParticipants,
      "expectedGatheringVersion": request.expectedGatheringVersion,
      if (request.acknowledgementDeadlineAt != null) "acknowledgementDeadlineAt": request.acknowledgementDeadlineAt!.toUtc().toIso8601String(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringCompleteGatheringGeneratedRequest(GatheringVersionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringCompleteGatheringSelfGeneratedRequest(DeclareGatheringAttendanceCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "evidenceRefs": request.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringCreateGatheringDraftGeneratedRequest(CreateGatheringDraftCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "hostBinding": request.hostBinding.toWire(),
      "creatorParticipates": request.creatorParticipates,
      "purpose": request.purpose.toWire(),
      "schedule": request.schedule.toWire(),
      "place": request.place.toWire(),
      "policySet": request.policySet.toWire(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringDeclineGatheringInvitationGeneratedRequest(GatheringParticipationVersionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringEndGatheringEarlyGeneratedRequest(GatheringReasonCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "reasonRef": request.reasonRef,
      "evidenceRefs": request.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
      "expectedGatheringVersion": request.expectedGatheringVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringGetGatheringGeneratedRequest(GatheringIDQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringGetPublicGatheringGeneratedRequest(GatheringIDQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringInviteToGatheringGeneratedRequest(InviteToGatheringCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "participantPersonaId": request.participantPersonaId,
      "seatHoldUntil": request.seatHoldUntil.toUtc().toIso8601String(),
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringJoinOpenGatheringGeneratedRequest(GatheringParticipationVersionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringListGatheringsByHostGeneratedRequest(GatheringListByHostQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "hostSubjectKind": (request.hostSubjectKind.wireName).toString(),
      "hostSubjectId": request.hostSubjectId,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringListGatheringsBySourceGeneratedRequest(GatheringListBySourceQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "sourceObjectTypeRef": request.sourceObjectTypeRef,
      "sourceObjectId": request.sourceObjectId,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringListMyHostedGatheringsGeneratedRequest(GatheringMineListQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringPauseGatheringAdmissionGeneratedRequest(ChangeGatheringAdmissionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      if (request.reasonRef != null) "reasonRef": request.reasonRef!,
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedAdmissionControlVersion": request.expectedAdmissionControlVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringPublishGatheringGeneratedRequest(GatheringVersionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringRemoveGatheringParticipantGeneratedRequest(TargetGatheringParticipationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "participantPersonaId": request.participantPersonaId,
      if (request.reasonRef != null) "reasonRef": request.reasonRef!,
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringResumeGatheringAdmissionGeneratedRequest(ChangeGatheringAdmissionCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      if (request.reasonRef != null) "reasonRef": request.reasonRef!,
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedAdmissionControlVersion": request.expectedAdmissionControlVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringReviewGatheringApplicationGeneratedRequest(ReviewGatheringApplicationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "participantPersonaId": request.participantPersonaId,
      "decision": request.decision.wireName,
      if (request.reasonRef != null) "reasonRef": request.reasonRef!,
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedParticipationVersion": request.expectedParticipationVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringSafetyTerminateGatheringGeneratedRequest(GatheringReasonCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "reasonRef": request.reasonRef,
      "evidenceRefs": request.evidenceRefs.map((value) => value.toWire()).toList(growable: false),
      "expectedGatheringVersion": request.expectedGatheringVersion,
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringUpdateGatheringGeneratedRequest(UpdateGatheringCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "purpose": request.purpose.toWire(),
      "schedule": request.schedule.toWire(),
      "place": request.place.toWire(),
      "policySet": request.policySet.toWire(),
      "hostBinding": request.hostBinding.toWire(),
      if (request.acknowledgementDeadlineAt != null) "acknowledgementDeadlineAt": request.acknowledgementDeadlineAt!.toUtc().toIso8601String(),
    },
  );
}

CloudOperationRequestPayload encodeCircleGatheringWatchGatheringAvailabilityGeneratedRequest(GatheringAvailabilityWatchCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "gatheringId": request.gatheringId,
    },
    body: <String, Object?>{
      "expectedGatheringVersion": request.expectedGatheringVersion,
      "expectedWatchVersion": request.expectedWatchVersion,
    },
  );
}

