// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../entity/homepage_review_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class CreateHomepageReviewCommand {
  CreateHomepageReviewCommand({
    required String homepageId,
    required int rating,
    String? body,
    List<String> tagRefs = const <String>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
  }) : homepageId = homepageId.trim(),
       rating = rating,
       body = _normalizeGeneratedOptionalText(body),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: true),
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(authorAvatarUrlSnapshot) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
  }

  final String homepageId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
}

final class DeleteHomepageReviewCommand {
  DeleteHomepageReviewCommand({
    required String reviewId,
  }) : reviewId = reviewId.trim() {
    if (this.reviewId.isEmpty) {
      throw ArgumentError.value(this.reviewId, "reviewId", 'must not be blank');
    }
  }

  final String reviewId;
}

final class HomepageReviewListQuery {
  HomepageReviewListQuery({
    required String homepageId,
    String? cursor,
    int limit = 20,
  }) : homepageId = homepageId.trim(),
       cursor = cursor,
       limit = limit {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
  }

  final String homepageId;
  final String? cursor;
  final int limit;
}

final class MyHomepageReviewQuery {
  MyHomepageReviewQuery({
    required String homepageId,
  }) : homepageId = homepageId.trim() {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
  }

  final String homepageId;
}

final class UpdateHomepageReviewCommand {
  UpdateHomepageReviewCommand({
    required String reviewId,
    required int rating,
    String? body,
    List<String> tagRefs = const <String>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
  }) : reviewId = reviewId.trim(),
       rating = rating,
       body = _normalizeGeneratedOptionalText(body),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: true),
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(authorAvatarUrlSnapshot) {
    if (this.reviewId.isEmpty) {
      throw ArgumentError.value(this.reviewId, "reviewId", 'must not be blank');
    }
  }

  final String reviewId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
}

CloudOperationRequestPayload encodeEntityHomepageReviewCreateHomepageReviewGeneratedRequest(CreateHomepageReviewCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    body: <String, Object?>{
      "rating": request.rating,
      if (request.body != null) "body": request.body!,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      if (request.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageReviewDeleteHomepageReviewGeneratedRequest(DeleteHomepageReviewCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "reviewId": request.reviewId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageReviewGetMyHomepageReviewGeneratedRequest(MyHomepageReviewQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageReviewListHomepageReviewsGeneratedRequest(HomepageReviewListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageReviewUpdateHomepageReviewGeneratedRequest(UpdateHomepageReviewCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "reviewId": request.reviewId,
    },
    body: <String, Object?>{
      "rating": request.rating,
      if (request.body != null) "body": request.body!,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      if (request.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
    },
  );
}

