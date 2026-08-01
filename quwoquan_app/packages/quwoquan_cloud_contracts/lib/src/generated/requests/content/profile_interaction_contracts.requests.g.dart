// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "interactionId": this.activityId,
    "state": switch (this.state) { ContentProfileInteractionReadState.seen => "seen", ContentProfileInteractionReadState.read => "read", },
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "type": switch (this.type) { ContentProfileInteractionType.like => "like", ContentProfileInteractionType.comment => "comment", ContentProfileInteractionType.share => "share", },
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
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

