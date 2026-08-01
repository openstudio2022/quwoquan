// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "homepageId": this.homepageId,
    "rating": this.rating,
    if (this.body != null) "body": this.body!,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    if (this.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "reviewId": this.reviewId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "homepageId": this.homepageId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "homepageId": this.homepageId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "reviewId": this.reviewId,
    "rating": this.rating,
    if (this.body != null) "body": this.body!,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    if (this.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
  };
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

