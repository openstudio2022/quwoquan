// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/group_membership_contracts.dart';

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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
  };
}

final class CircleGroupMembershipListQuery {
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
  }

  final String circleId;
  final String groupId;
  final CircleGroupMembershipState? state;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    if (this.state != null) "state": switch (this.state!) { CircleGroupMembershipState.pending => "pending", CircleGroupMembershipState.active => "active", CircleGroupMembershipState.rejected => "rejected", CircleGroupMembershipState.left => "left", CircleGroupMembershipState.removed => "removed", },
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "groupId": this.groupId,
    "personaId": this.personaId,
    "role": switch (this.role) { CircleGroupMembershipRole.owner => "owner", CircleGroupMembershipRole.manager => "manager", CircleGroupMembershipRole.member => "member", },
  };
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
      if (request.state != null) "state": (switch (request.state!) { CircleGroupMembershipState.pending => "pending", CircleGroupMembershipState.active => "active", CircleGroupMembershipState.rejected => "rejected", CircleGroupMembershipState.left => "left", CircleGroupMembershipState.removed => "removed", }).toString(),
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
      "role": switch (request.role) { CircleGroupMembershipRole.owner => "owner", CircleGroupMembershipRole.manager => "manager", CircleGroupMembershipRole.member => "member", },
    },
  );
}

