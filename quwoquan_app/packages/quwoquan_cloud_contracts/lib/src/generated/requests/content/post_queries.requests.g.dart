// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/post_queries.dart';

final class ContentFootprintQuery {
  const ContentFootprintQuery({
    String? type,
    String? cursor,
    int limit = 20,
  }) : type = type,
       cursor = cursor,
       limit = limit;

  final String? type;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.type != null) "type": this.type!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class EntityWishlistStateQuery {
  const EntityWishlistStateQuery({
    required String objectId,
    required String objectKind,
  }) : objectId = objectId,
       objectKind = objectKind;

  final String objectId;
  final String objectKind;

  Map<String, Object?> toJson() => <String, Object?>{
    "objectId": this.objectId,
    "objectKind": this.objectKind,
  };
}

CloudOperationRequestPayload encodeContentPostGetEntityWishlistStateGeneratedRequest(EntityWishlistStateQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "objectId": request.objectId,
      "objectKind": request.objectKind,
    },
  );
}

CloudOperationRequestPayload encodeContentPostGetMyFootprintGeneratedRequest(ContentFootprintQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.type != null) "type": request.type!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

