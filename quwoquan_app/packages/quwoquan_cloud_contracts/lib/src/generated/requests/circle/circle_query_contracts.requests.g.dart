// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/circle_query_contracts.dart';

final class CircleDetailQuery {
  const CircleDetailQuery({
    required String circleId,
  }) : circleId = circleId;

  final String circleId;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class CircleDiscoveryFeedQuery {
  const CircleDiscoveryFeedQuery({
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
       sort = sort;

  final String? category;
  final String? subCategory;
  final CircleDiscoveryFeedScope scope;
  final String? cursor;
  final int limit;
  final String sort;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    "scope": switch (this.scope) { CircleDiscoveryFeedScope.recommended => "recommended", CircleDiscoveryFeedScope.mine => "mine", },
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    "sort": this.sort,
  };
}

final class CircleImpactQuery {
  const CircleImpactQuery({
    required String circleId,
  }) : circleId = circleId;

  final String circleId;

  Map<String, Object?> toJson() => <String, Object?>{
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

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.category != null) "category": this.category!,
    if (this.domainId != null) "domainId": this.domainId!,
    if (this.recommendFor != null) "recommendFor": this.recommendFor!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.sort != null) "sort": this.sort!,
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

  Map<String, Object?> toJson() => <String, Object?>{
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
  };
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
      "scope": (switch (request.scope) { CircleDiscoveryFeedScope.recommended => "recommended", CircleDiscoveryFeedScope.mine => "mine", }).toString(),
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

