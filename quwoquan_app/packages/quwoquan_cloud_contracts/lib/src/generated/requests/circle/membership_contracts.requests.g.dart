// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/membership_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class CircleMembershipListQuery {
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
  }

  final String circleId;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "personaId": this.personaId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class PendingCircleMembershipListQuery {
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
  }

  final String circleId;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class PersonaCircleListQuery {
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
  }

  final String personaId;
  final String? query;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    if (this.query != null) "query": this.query!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class UpdateCircleMembershipRoleCommand {
  UpdateCircleMembershipRoleCommand({
    required String circleId,
    required String personaId,
    required CircleMembershipRole role,
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
  final CircleMembershipRole role;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "personaId": this.personaId,
    "role": switch (this.role) { CircleMembershipRole.owner => "owner", CircleMembershipRole.admin => "admin", CircleMembershipRole.member => "member", },
  };
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
      "role": switch (request.role) { CircleMembershipRole.owner => "owner", CircleMembershipRole.admin => "admin", CircleMembershipRole.member => "member", },
    },
  );
}

