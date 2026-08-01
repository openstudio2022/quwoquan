// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/persona_relationship_contracts.dart';

final class BlockUserCommand {
  BlockUserCommand({
    required String targetPersonaId,
  }) : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
  }

  final String targetPersonaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
  };
}

final class FollowUserCommand {
  FollowUserCommand({
    required String targetPersonaId,
    String? source,
    String? clientRequestId,
  }) : targetPersonaId = targetPersonaId.trim(),
       source = source,
       clientRequestId = clientRequestId {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
  }

  final String targetPersonaId;
  final String? source;
  final String? clientRequestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.source?.isNotEmpty == true) "source": this.source!,
    if (this.clientRequestId?.isNotEmpty == true) "clientRequestId": this.clientRequestId!,
  };
}

final class GetRelationshipCapabilityQuery {
  GetRelationshipCapabilityQuery({
    required String targetPersonaId,
  }) : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
  }

  final String targetPersonaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.targetPersonaId,
  };
}

final class ListBlockedUsersQuery {
  const ListBlockedUsersQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class PersonaRelationshipListQuery {
  PersonaRelationshipListQuery({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       query = query,
       cursor = cursor,
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
    if (this.query?.isNotEmpty == true) "query": this.query!,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class UnblockUserCommand {
  UnblockUserCommand({
    required String targetPersonaId,
  }) : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
  }

  final String targetPersonaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
  };
}

final class UnfollowUserCommand {
  UnfollowUserCommand({
    required String targetPersonaId,
    String? clientRequestId,
  }) : targetPersonaId = targetPersonaId.trim(),
       clientRequestId = clientRequestId {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
  }

  final String targetPersonaId;
  final String? clientRequestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.clientRequestId?.isNotEmpty == true) "clientRequestId": this.clientRequestId!,
  };
}

CloudOperationRequestPayload encodeUserPersonaRelationshipBlockUserGeneratedRequest(BlockUserCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipFollowUserGeneratedRequest(FollowUserCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
    body: <String, Object?>{
      if (request.source?.isNotEmpty == true) "source": request.source!,
      if (request.clientRequestId?.isNotEmpty == true) "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipGetRelationshipCapabilityGeneratedRequest(GetRelationshipCapabilityQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.targetPersonaId,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipListBlockedUsersGeneratedRequest(ListBlockedUsersQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipListFollowersGeneratedRequest(PersonaRelationshipListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      if (request.query?.isNotEmpty == true) "query": request.query!,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipListFollowingGeneratedRequest(PersonaRelationshipListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      if (request.query?.isNotEmpty == true) "query": request.query!,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipUnblockUserGeneratedRequest(UnblockUserCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRelationshipUnfollowUserGeneratedRequest(UnfollowUserCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
    body: <String, Object?>{
      if (request.clientRequestId?.isNotEmpty == true) "clientRequestId": request.clientRequestId!,
    },
  );
}

