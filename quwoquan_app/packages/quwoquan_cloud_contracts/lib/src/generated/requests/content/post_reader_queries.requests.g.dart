// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/post_reader_queries.dart';

final class ContentAuthorPostsQuery {
  const ContentAuthorPostsQuery({
    required String personaId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId,
       identity = identity,
       type = type,
       visibility = visibility,
       cursor = cursor,
       limit = limit;

  final String personaId;
  final String? identity;
  final String? type;
  final String? visibility;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentDiscoveryFeedQuery {
  ContentDiscoveryFeedQuery({
    String? identity,
    String? type,
    String? sort,
    String? cursor,
    String? subCategory,
    String? channelId,
    String? sessionId,
    String? feedRequestId,
    int limit = GeneratedContentPostGetFeedPolicy.defaultItems,
    Iterable<String> blockedKeywords = const <String>[],
  }) : identity = identity,
       type = type,
       sort = sort,
       cursor = cursor,
       subCategory = subCategory,
       channelId = channelId,
       sessionId = sessionId,
       feedRequestId = feedRequestId,
       limit = limit,
       blockedKeywords = List.unmodifiable(blockedKeywords) {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 20) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 20");
    }
  }

  final String? identity;
  final String? type;
  final String? sort;
  final String? cursor;
  final String? subCategory;
  final String? channelId;
  final String? sessionId;
  final String? feedRequestId;
  final int limit;
  final List<String> blockedKeywords;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.sort != null) "sort": this.sort!,
    if (this.cursor != null) "cursor": this.cursor!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.channelId != null) "channelId": this.channelId!,
    if (this.sessionId != null) "sessionId": this.sessionId!,
    if (this.feedRequestId != null) "feedRequestId": this.feedRequestId!,
    "limit": this.limit,
    if (this.blockedKeywords.isNotEmpty) "X-Blocked-Keywords": this.blockedKeywords.map(Uri.encodeQueryComponent).join(','),
  };
}

final class ContentPostDetailQuery {
  const ContentPostDetailQuery({
    required String postId,
  }) : postId = postId;

  final String postId;

  Map<String, Object?> toJson() => <String, Object?>{
    "postId": this.postId,
  };
}

CloudOperationRequestPayload encodeContentPostGetFeedGeneratedRequest(ContentDiscoveryFeedQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.identity != null) "identity": request.identity!,
      if (request.type != null) "type": request.type!,
      if (request.sort != null) "sort": request.sort!,
      if (request.cursor != null) "cursor": request.cursor!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.channelId != null) "channelId": request.channelId!,
      if (request.sessionId != null) "sessionId": request.sessionId!,
      if (request.feedRequestId != null) "feedRequestId": request.feedRequestId!,
      "limit": (request.limit).toString(),
    },
    headers: <String, String>{
      if (request.blockedKeywords.isNotEmpty) "X-Blocked-Keywords": request.blockedKeywords.map(Uri.encodeQueryComponent).join(','),
    },
  );
}

CloudOperationRequestPayload encodeContentPostGetPostGeneratedRequest(ContentPostDetailQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
  );
}

CloudOperationRequestPayload encodeContentPostListUserPostsGeneratedRequest(ContentAuthorPostsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      if (request.identity != null) "identity": request.identity!,
      if (request.type != null) "type": request.type!,
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

