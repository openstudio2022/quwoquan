// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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
}

final class EntityWishlistStateQuery {
  const EntityWishlistStateQuery({
    required String objectId,
    required String objectKind,
  }) : objectId = objectId,
       objectKind = objectKind;

  final String objectId;
  final String objectKind;
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

