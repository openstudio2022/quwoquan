// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../entity/homepage_queries.dart';

final class HomepageByIdQuery {
  const HomepageByIdQuery({
    required String homepageId,
  }) : homepageId = homepageId;

  final String homepageId;
}

final class HomepageObjectPageBundleQuery {
  const HomepageObjectPageBundleQuery({
    required String homepageId,
    String? referralSource,
    String? feedRequestId,
    String? recommendationTraceId,
    String? experimentBucket,
    String? rolloutCohort,
  }) : homepageId = homepageId,
       referralSource = referralSource,
       feedRequestId = feedRequestId,
       recommendationTraceId = recommendationTraceId,
       experimentBucket = experimentBucket,
       rolloutCohort = rolloutCohort;

  final String homepageId;
  final String? referralSource;
  final String? feedRequestId;
  final String? recommendationTraceId;
  final String? experimentBucket;
  final String? rolloutCohort;
}

final class HomepageSearchQuery {
  const HomepageSearchQuery({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    String? cursor,
    int limit = 20,
  }) : query = query,
       homepageType = homepageType,
       city = city,
       status = status,
       cursor = cursor,
       limit = limit;

  final String query;
  final String? homepageType;
  final String? city;
  final String? status;
  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeEntityHomepageGetEntityImpactGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetHomepageDetailGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetHomepageIntroductionGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetHomepageRelatedGroupsGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetHomepageReviewSummaryGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetHomepageShellGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageGetObjectPageBundleGeneratedRequest(HomepageObjectPageBundleQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    queryParameters: <String, String>{
      if (request.referralSource != null) "referralSource": request.referralSource!,
      if (request.feedRequestId != null) "feedRequestId": request.feedRequestId!,
      if (request.recommendationTraceId != null) "recommendationTraceId": request.recommendationTraceId!,
      if (request.experimentBucket != null) "experimentBucket": request.experimentBucket!,
      if (request.rolloutCohort != null) "rolloutCohort": request.rolloutCohort!,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageSearchHomepagesGeneratedRequest(HomepageSearchQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "query": request.query,
      if (request.homepageType != null) "homepageType": request.homepageType!,
      if (request.city != null) "city": request.city!,
      if (request.status != null) "status": request.status!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

