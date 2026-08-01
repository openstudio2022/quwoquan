// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/group_contracts.dart';

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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class CircleGroupListQuery {
  CircleGroupListQuery({
    required String circleId,
    CircleGroupType? groupType,
    CircleGroupVisibility? visibility,
    String? parentGroupId,
    CircleGroupNodeType? nodeType,
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
  }

  final String circleId;
  final CircleGroupType? groupType;
  final CircleGroupVisibility? visibility;
  final String? parentGroupId;
  final CircleGroupNodeType? nodeType;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupType != null) "groupType": switch (this.groupType!) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", },
    if (this.visibility != null) "visibility": switch (this.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    if (this.nodeType != null) "nodeType": switch (this.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", },
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class CircleGroupSearchQuery {
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
  }

  final String circleId;
  final String query;
  final CircleGroupVisibility? visibility;
  final CircleGroupType? groupType;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "query": this.query,
    if (this.visibility != null) "visibility": switch (this.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
    if (this.groupType != null) "groupType": switch (this.groupType!) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", },
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CreateCircleGroupCommand {
  CreateCircleGroupCommand({
    required String circleId,
    String? parentGroupId,
    required CircleGroupType groupType,
    CircleGroupNodeType? nodeType,
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
  final CircleGroupNodeType? nodeType;
  final String name;
  final String description;
  final CircleGroupVisibility visibility;
  final CircleGroupJoinPolicy joinPolicy;
  final bool storageEnabled;
  final bool noticeEnabled;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    "groupType": switch (this.groupType) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", },
    if (this.nodeType != null) "nodeType": switch (this.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", },
    "name": this.name,
    "description": this.description,
    "visibility": switch (this.visibility) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
    "joinPolicy": switch (this.joinPolicy) { CircleGroupJoinPolicy.applyOnly => "apply_only", CircleGroupJoinPolicy.inviteOnly => "invite_only", },
    "storageEnabled": this.storageEnabled,
    "noticeEnabled": this.noticeEnabled,
  };
}

final class UpdateCircleGroupCommand {
  UpdateCircleGroupCommand({
    required String circleId,
    required String groupId,
    required int expectedVersion,
    String? parentGroupId,
    CircleGroupNodeType? nodeType,
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
  final CircleGroupNodeType? nodeType;
  final String? name;
  final String? description;
  final CircleGroupVisibility? visibility;
  final CircleGroupJoinPolicy? joinPolicy;
  final bool? storageEnabled;
  final bool? noticeEnabled;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "expectedVersion": '"${this.expectedVersion}"',
    if (this.parentGroupId != null) "parentGroupId": this.parentGroupId!,
    if (this.nodeType != null) "nodeType": switch (this.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", },
    if (this.name != null) "name": this.name!,
    if (this.description != null) "description": this.description!,
    if (this.visibility != null) "visibility": switch (this.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
    if (this.joinPolicy != null) "joinPolicy": switch (this.joinPolicy!) { CircleGroupJoinPolicy.applyOnly => "apply_only", CircleGroupJoinPolicy.inviteOnly => "invite_only", },
    if (this.storageEnabled != null) "storageEnabled": this.storageEnabled!,
    if (this.noticeEnabled != null) "noticeEnabled": this.noticeEnabled!,
  };
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
      "groupType": switch (request.groupType) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", },
      if (request.nodeType != null) "nodeType": switch (request.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", },
      "name": request.name,
      "description": request.description,
      "visibility": switch (request.visibility) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
      "joinPolicy": switch (request.joinPolicy) { CircleGroupJoinPolicy.applyOnly => "apply_only", CircleGroupJoinPolicy.inviteOnly => "invite_only", },
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
      if (request.groupType != null) "groupType": (switch (request.groupType!) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", }).toString(),
      if (request.visibility != null) "visibility": (switch (request.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", }).toString(),
      if (request.parentGroupId != null) "parentGroupId": request.parentGroupId!,
      if (request.nodeType != null) "nodeType": (switch (request.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", }).toString(),
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
      if (request.visibility != null) "visibility": (switch (request.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", }).toString(),
      if (request.groupType != null) "groupType": (switch (request.groupType!) { CircleGroupType.publicGroup => "public_group", CircleGroupType.selfBuilt => "self_built", CircleGroupType.orgNode => "org_node", }).toString(),
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
      if (request.nodeType != null) "nodeType": switch (request.nodeType!) { CircleGroupNodeType.generic => "generic", CircleGroupNodeType.college => "college", CircleGroupNodeType.grade => "grade", CircleGroupNodeType.classroom => "classroom", CircleGroupNodeType.department => "department", CircleGroupNodeType.team => "team", },
      if (request.name != null) "name": request.name!,
      if (request.description != null) "description": request.description!,
      if (request.visibility != null) "visibility": switch (request.visibility!) { CircleGroupVisibility.public => "public", CircleGroupVisibility.private => "private", },
      if (request.joinPolicy != null) "joinPolicy": switch (request.joinPolicy!) { CircleGroupJoinPolicy.applyOnly => "apply_only", CircleGroupJoinPolicy.inviteOnly => "invite_only", },
      if (request.storageEnabled != null) "storageEnabled": request.storageEnabled!,
      if (request.noticeEnabled != null) "noticeEnabled": request.noticeEnabled!,
    },
  );
}

