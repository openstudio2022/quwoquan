// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/profile_interaction_contracts.dart';

final class AppendContentProfileInteractionReadFactCommand {
  AppendContentProfileInteractionReadFactCommand({
    required String personaId,
    required String activityId,
    required ContentProfileInteractionReadState state,
  }) : personaId = personaId.trim(),
       activityId = activityId.trim(),
       state = state {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
    if (this.activityId.isEmpty) {
      throw ArgumentError.value(this.activityId, "activityId", 'must not be blank');
    }
  }

  final String personaId;
  final String activityId;
  final ContentProfileInteractionReadState state;
}

final class ContentProfileInteractionPageQuery {
  ContentProfileInteractionPageQuery({
    required String personaId,
    required ContentProfileInteractionType type,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       type = type,
       cursor = cursor,
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String personaId;
  final ContentProfileInteractionType type;
  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesReceivedGeneratedRequest(ContentProfileInteractionPageQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      "type": (switch (request.type) { ContentProfileInteractionType.like => "like", ContentProfileInteractionType.comment => "comment", ContentProfileInteractionType.share => "share", }).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesSentGeneratedRequest(ContentProfileInteractionPageQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      "type": (switch (request.type) { ContentProfileInteractionType.like => "like", ContentProfileInteractionType.comment => "comment", ContentProfileInteractionType.share => "share", }).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentProfileInteractionReadFactUpdateProfileInteractionStateGeneratedRequest(AppendContentProfileInteractionReadFactCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
      "interactionId": request.activityId,
    },
    body: <String, Object?>{
      "state": switch (request.state) { ContentProfileInteractionReadState.seen => "seen", ContentProfileInteractionReadState.read => "read", },
    },
  );
}

