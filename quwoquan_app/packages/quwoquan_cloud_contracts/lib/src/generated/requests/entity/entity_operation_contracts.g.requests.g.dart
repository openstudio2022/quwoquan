// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: fab62e2fdbd44afc23fe0c42c057f85e6ee36b06af3fa9889ffa9a7a1bc0c2f1

part of '../../../entity/entity_operation_contracts.g.dart';

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

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}

void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}

List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class CreateHomepageClaimRequestCommand {
  CreateHomepageClaimRequestCommand({
    required String homepageId,
    required String claimTier,
    String? businessLicenseUrl,
    String? contactPhone,
    String? identityCardFrontUrl,
    String? identityCardBackUrl,
    String? note,
  }) : homepageId = homepageId.trim(),
       claimTier = claimTier.trim(),
       businessLicenseUrl = _normalizeGeneratedOptionalText(businessLicenseUrl),
       contactPhone = _normalizeGeneratedOptionalText(contactPhone),
       identityCardFrontUrl = _normalizeGeneratedOptionalText(
         identityCardFrontUrl,
       ),
       identityCardBackUrl = _normalizeGeneratedOptionalText(
         identityCardBackUrl,
       ),
       note = _normalizeGeneratedOptionalText(note) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
    if (this.claimTier.isEmpty) {
      throw ArgumentError.value(
        this.claimTier,
        "claimTier",
        'must not be blank',
      );
    }
  }

  final String homepageId;
  final String claimTier;
  final String? businessLicenseUrl;
  final String? contactPhone;
  final String? identityCardFrontUrl;
  final String? identityCardBackUrl;
  final String? note;

  factory CreateHomepageClaimRequestCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateHomepageClaimRequestCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "claimTier",
      "businessLicenseUrl",
      "contactPhone",
      "identityCardFrontUrl",
      "identityCardBackUrl",
      "note",
    }, path);
    return CreateHomepageClaimRequestCommand(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      claimTier: _generatedRequestString(map["claimTier"], '$path.claimTier'),
      businessLicenseUrl: map["businessLicenseUrl"] == null
          ? null
          : _generatedRequestString(
              map["businessLicenseUrl"],
              '$path.businessLicenseUrl',
            ),
      contactPhone: map["contactPhone"] == null
          ? null
          : _generatedRequestString(map["contactPhone"], '$path.contactPhone'),
      identityCardFrontUrl: map["identityCardFrontUrl"] == null
          ? null
          : _generatedRequestString(
              map["identityCardFrontUrl"],
              '$path.identityCardFrontUrl',
            ),
      identityCardBackUrl: map["identityCardBackUrl"] == null
          ? null
          : _generatedRequestString(
              map["identityCardBackUrl"],
              '$path.identityCardBackUrl',
            ),
      note: map["note"] == null
          ? null
          : _generatedRequestString(map["note"], '$path.note'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    "claimTier": this.claimTier,
    if (this.businessLicenseUrl != null)
      "businessLicenseUrl": this.businessLicenseUrl!,
    if (this.contactPhone != null) "contactPhone": this.contactPhone!,
    if (this.identityCardFrontUrl != null)
      "identityCardFrontUrl": this.identityCardFrontUrl!,
    if (this.identityCardBackUrl != null)
      "identityCardBackUrl": this.identityCardBackUrl!,
    if (this.note != null) "note": this.note!,
  };
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
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(
         authorDisplayNameSnapshot,
       ),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(
         authorAvatarUrlSnapshot,
       ) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
  }

  final String homepageId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;

  factory CreateHomepageReviewCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateHomepageReviewCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "rating",
      "body",
      "tagRefs",
      "authorDisplayNameSnapshot",
      "authorAvatarUrlSnapshot",
    }, path);
    return CreateHomepageReviewCommand(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      rating: _generatedRequestInt(map["rating"], '$path.rating'),
      body: map["body"] == null
          ? null
          : _generatedRequestString(map["body"], '$path.body'),
      tagRefs: map.containsKey("tagRefs")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["tagRefs"],
                '$path.tagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.tagRefs' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorDisplayNameSnapshot"],
              '$path.authorDisplayNameSnapshot',
            ),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorAvatarUrlSnapshot"],
              '$path.authorAvatarUrlSnapshot',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    "rating": this.rating,
    if (this.body != null) "body": this.body!,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    if (this.authorDisplayNameSnapshot != null)
      "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null)
      "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
  };
}

final class CreateHomepageStatusReportCommand {
  CreateHomepageStatusReportCommand({
    required String homepageId,
    required String reason,
    String? description,
    List<String> evidenceUrls = const <String>[],
  }) : homepageId = homepageId.trim(),
       reason = reason.trim(),
       description = _normalizeGeneratedOptionalText(description),
       evidenceUrls = _normalizeGeneratedTextList(
         evidenceUrls,
         deduplicate: false,
       ) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String homepageId;
  final String reason;
  final String? description;
  final List<String> evidenceUrls;

  factory CreateHomepageStatusReportCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateHomepageStatusReportCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "reason",
      "description",
      "evidenceUrls",
    }, path);
    return CreateHomepageStatusReportCommand(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
      description: map["description"] == null
          ? null
          : _generatedRequestString(map["description"], '$path.description'),
      evidenceUrls: map.containsKey("evidenceUrls")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["evidenceUrls"],
                '$path.evidenceUrls',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.evidenceUrls' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    "reason": this.reason,
    if (this.description != null) "description": this.description!,
    if (this.evidenceUrls.isNotEmpty)
      "evidenceUrls": this.evidenceUrls
          .map((value) => value)
          .toList(growable: false),
  };
}

final class DeleteHomepageReviewCommand {
  DeleteHomepageReviewCommand({required String reviewId})
    : reviewId = reviewId.trim() {
    if (this.reviewId.isEmpty) {
      throw ArgumentError.value(this.reviewId, "reviewId", 'must not be blank');
    }
  }

  final String reviewId;

  factory DeleteHomepageReviewCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DeleteHomepageReviewCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"reviewId"}, path);
    return DeleteHomepageReviewCommand(
      reviewId: _generatedRequestString(map["reviewId"], '$path.reviewId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"reviewId": this.reviewId};
}

final class GetMyPendingHomepageClaimRequestQuery {
  GetMyPendingHomepageClaimRequestQuery({required String homepageId})
    : homepageId = homepageId.trim() {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
  }

  final String homepageId;

  factory GetMyPendingHomepageClaimRequestQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetMyPendingHomepageClaimRequestQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
    }, path);
    return GetMyPendingHomepageClaimRequestQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
  };
}

final class GetMyPendingHomepageStatusReportQuery {
  GetMyPendingHomepageStatusReportQuery({
    required String homepageId,
    required String reason,
  }) : homepageId = homepageId.trim(),
       reason = reason.trim() {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String homepageId;
  final String reason;

  factory GetMyPendingHomepageStatusReportQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetMyPendingHomepageStatusReportQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "reason",
    }, path);
    return GetMyPendingHomepageStatusReportQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    "reason": this.reason,
  };
}

final class HomepageByIdQuery {
  const HomepageByIdQuery({required String homepageId})
    : homepageId = homepageId;

  final String homepageId;

  factory HomepageByIdQuery.fromWire(
    Map<String, Object?> map, [
    String path = "HomepageByIdQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
    }, path);
    return HomepageByIdQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
  };
}

final class HomepageGeoPointInput {
  const HomepageGeoPointInput({required double lat, required double lng})
    : lat = lat,
      lng = lng;

  final double lat;
  final double lng;

  factory HomepageGeoPointInput.fromWire(
    Map<String, Object?> map, [
    String path = "HomepageGeoPointInput",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "lat",
      "lng",
    }, path);
    return HomepageGeoPointInput(
      lat: _generatedRequestDouble(map["lat"], '$path.lat'),
      lng: _generatedRequestDouble(map["lng"], '$path.lng'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "lat": this.lat,
    "lng": this.lng,
  };
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

  factory HomepageObjectPageBundleQuery.fromWire(
    Map<String, Object?> map, [
    String path = "HomepageObjectPageBundleQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "referralSource",
      "feedRequestId",
      "recommendationTraceId",
      "experimentBucket",
      "rolloutCohort",
    }, path);
    return HomepageObjectPageBundleQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      referralSource: map["referralSource"] == null
          ? null
          : _generatedRequestString(
              map["referralSource"],
              '$path.referralSource',
            ),
      feedRequestId: map["feedRequestId"] == null
          ? null
          : _generatedRequestString(
              map["feedRequestId"],
              '$path.feedRequestId',
            ),
      recommendationTraceId: map["recommendationTraceId"] == null
          ? null
          : _generatedRequestString(
              map["recommendationTraceId"],
              '$path.recommendationTraceId',
            ),
      experimentBucket: map["experimentBucket"] == null
          ? null
          : _generatedRequestString(
              map["experimentBucket"],
              '$path.experimentBucket',
            ),
      rolloutCohort: map["rolloutCohort"] == null
          ? null
          : _generatedRequestString(
              map["rolloutCohort"],
              '$path.rolloutCohort',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    if (this.referralSource != null) "referralSource": this.referralSource!,
    if (this.feedRequestId != null) "feedRequestId": this.feedRequestId!,
    if (this.recommendationTraceId != null)
      "recommendationTraceId": this.recommendationTraceId!,
    if (this.experimentBucket != null)
      "experimentBucket": this.experimentBucket!,
    if (this.rolloutCohort != null) "rolloutCohort": this.rolloutCohort!,
  };
}

final class HomepageReviewListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  HomepageReviewListQuery({
    required String homepageId,
    String? cursor,
    int limit = 20,
  }) : homepageId = homepageId.trim(),
       cursor = cursor,
       limit = limit {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String homepageId;
  final String? cursor;
  final int limit;

  factory HomepageReviewListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "HomepageReviewListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "cursor",
      "limit",
    }, path);
    return HomepageReviewListQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class HomepageSearchQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 500;

  HomepageSearchQuery({
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
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 500) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 500");
    }
  }

  final String query;
  final String? homepageType;
  final String? city;
  final String? status;
  final String? cursor;
  final int limit;

  factory HomepageSearchQuery.fromWire(
    Map<String, Object?> map, [
    String path = "HomepageSearchQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "query",
      "homepageType",
      "city",
      "status",
      "cursor",
      "limit",
    }, path);
    return HomepageSearchQuery(
      query: _generatedRequestString(map["query"], '$path.query'),
      homepageType: map["homepageType"] == null
          ? null
          : _generatedRequestString(map["homepageType"], '$path.homepageType'),
      city: map["city"] == null
          ? null
          : _generatedRequestString(map["city"], '$path.city'),
      status: map["status"] == null
          ? null
          : _generatedRequestString(map["status"], '$path.status'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    if (this.homepageType != null) "homepageType": this.homepageType!,
    if (this.city != null) "city": this.city!,
    if (this.status != null) "status": this.status!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class MyHomepageReviewQuery {
  MyHomepageReviewQuery({required String homepageId})
    : homepageId = homepageId.trim() {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
  }

  final String homepageId;

  factory MyHomepageReviewQuery.fromWire(
    Map<String, Object?> map, [
    String path = "MyHomepageReviewQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
    }, path);
    return MyHomepageReviewQuery(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
  };
}

final class SuggestHomepageCandidateCommand {
  SuggestHomepageCandidateCommand({
    required String title,
    required String homepageType,
    String? subtitle,
    List<String> categoryTags = const <String>[],
    String? coverUrl,
    String? address,
    String? city,
    String? sourcePlaceId,
    HomepageGeoPointInput? location,
  }) : title = title.trim(),
       homepageType = homepageType.trim(),
       subtitle = _normalizeGeneratedOptionalText(subtitle),
       categoryTags = _normalizeGeneratedTextList(
         categoryTags,
         deduplicate: false,
       ),
       coverUrl = _normalizeGeneratedOptionalText(coverUrl),
       address = _normalizeGeneratedOptionalText(address),
       city = _normalizeGeneratedOptionalText(city),
       sourcePlaceId = _normalizeGeneratedOptionalText(sourcePlaceId),
       location = location {
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
    if (this.homepageType.isEmpty) {
      throw ArgumentError.value(
        this.homepageType,
        "homepageType",
        'must not be blank',
      );
    }
  }

  final String title;
  final String homepageType;
  final String? subtitle;
  final List<String> categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final String? sourcePlaceId;
  final HomepageGeoPointInput? location;

  factory SuggestHomepageCandidateCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SuggestHomepageCandidateCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "title",
      "homepageType",
      "subtitle",
      "categoryTags",
      "coverUrl",
      "address",
      "city",
      "sourcePlaceId",
      "location",
    }, path);
    return SuggestHomepageCandidateCommand(
      title: _generatedRequestString(map["title"], '$path.title'),
      homepageType: _generatedRequestString(
        map["homepageType"],
        '$path.homepageType',
      ),
      subtitle: map["subtitle"] == null
          ? null
          : _generatedRequestString(map["subtitle"], '$path.subtitle'),
      categoryTags: map.containsKey("categoryTags")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["categoryTags"],
                '$path.categoryTags',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.categoryTags' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      coverUrl: map["coverUrl"] == null
          ? null
          : _generatedRequestString(map["coverUrl"], '$path.coverUrl'),
      address: map["address"] == null
          ? null
          : _generatedRequestString(map["address"], '$path.address'),
      city: map["city"] == null
          ? null
          : _generatedRequestString(map["city"], '$path.city'),
      sourcePlaceId: map["sourcePlaceId"] == null
          ? null
          : _generatedRequestString(
              map["sourcePlaceId"],
              '$path.sourcePlaceId',
            ),
      location: map["location"] == null
          ? null
          : HomepageGeoPointInput.fromWire(
              _generatedRequestObject(map["location"], '$path.location'),
              '$path.location',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "title": this.title,
    "homepageType": this.homepageType,
    if (this.subtitle != null) "subtitle": this.subtitle!,
    if (this.categoryTags.isNotEmpty)
      "categoryTags": this.categoryTags
          .map((value) => value)
          .toList(growable: false),
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.address != null) "address": this.address!,
    if (this.city != null) "city": this.city!,
    if (this.sourcePlaceId != null) "sourcePlaceId": this.sourcePlaceId!,
    if (this.location != null) "location": this.location!.toWire(),
  };
}

final class UpdateClaimedHomepageBasicsCommand {
  UpdateClaimedHomepageBasicsCommand({
    required String homepageId,
    String? title,
    String? subtitle,
    List<String>? categoryTags,
    String? coverUrl,
    String? address,
    String? city,
    HomepageGeoPointInput? location,
  }) : homepageId = homepageId.trim(),
       title = _normalizeGeneratedOptionalText(title),
       subtitle = _normalizeGeneratedOptionalText(subtitle),
       categoryTags = categoryTags == null
           ? null
           : _normalizeGeneratedTextList(categoryTags, deduplicate: false),
       coverUrl = _normalizeGeneratedOptionalText(coverUrl),
       address = _normalizeGeneratedOptionalText(address),
       city = _normalizeGeneratedOptionalText(city),
       location = location {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(
        this.homepageId,
        "homepageId",
        'must not be blank',
      );
    }
  }

  final String homepageId;
  final String? title;
  final String? subtitle;
  final List<String>? categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final HomepageGeoPointInput? location;

  factory UpdateClaimedHomepageBasicsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateClaimedHomepageBasicsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "homepageId",
      "title",
      "subtitle",
      "categoryTags",
      "coverUrl",
      "address",
      "city",
      "location",
    }, path);
    return UpdateClaimedHomepageBasicsCommand(
      homepageId: _generatedRequestString(
        map["homepageId"],
        '$path.homepageId',
      ),
      title: map["title"] == null
          ? null
          : _generatedRequestString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null
          ? null
          : _generatedRequestString(map["subtitle"], '$path.subtitle'),
      categoryTags: map["categoryTags"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["categoryTags"],
                '$path.categoryTags',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.categoryTags' + '[${entry.key}]',
                ),
              ),
            ),
      coverUrl: map["coverUrl"] == null
          ? null
          : _generatedRequestString(map["coverUrl"], '$path.coverUrl'),
      address: map["address"] == null
          ? null
          : _generatedRequestString(map["address"], '$path.address'),
      city: map["city"] == null
          ? null
          : _generatedRequestString(map["city"], '$path.city'),
      location: map["location"] == null
          ? null
          : HomepageGeoPointInput.fromWire(
              _generatedRequestObject(map["location"], '$path.location'),
              '$path.location',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": this.homepageId,
    if (this.title != null) "title": this.title!,
    if (this.subtitle != null) "subtitle": this.subtitle!,
    if (this.categoryTags != null)
      "categoryTags": this.categoryTags!
          .map((value) => value)
          .toList(growable: false),
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.address != null) "address": this.address!,
    if (this.city != null) "city": this.city!,
    if (this.location != null) "location": this.location!.toWire(),
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
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(
         authorDisplayNameSnapshot,
       ),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(
         authorAvatarUrlSnapshot,
       ) {
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

  factory UpdateHomepageReviewCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateHomepageReviewCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "reviewId",
      "rating",
      "body",
      "tagRefs",
      "authorDisplayNameSnapshot",
      "authorAvatarUrlSnapshot",
    }, path);
    return UpdateHomepageReviewCommand(
      reviewId: _generatedRequestString(map["reviewId"], '$path.reviewId'),
      rating: _generatedRequestInt(map["rating"], '$path.rating'),
      body: map["body"] == null
          ? null
          : _generatedRequestString(map["body"], '$path.body'),
      tagRefs: map.containsKey("tagRefs")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["tagRefs"],
                '$path.tagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.tagRefs' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorDisplayNameSnapshot"],
              '$path.authorDisplayNameSnapshot',
            ),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorAvatarUrlSnapshot"],
              '$path.authorAvatarUrlSnapshot',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "reviewId": this.reviewId,
    "rating": this.rating,
    if (this.body != null) "body": this.body!,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    if (this.authorDisplayNameSnapshot != null)
      "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null)
      "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
  };
}

CloudOperationRequestPayload
encodeEntityHomepageGetEntityImpactGeneratedRequest(HomepageByIdQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetHomepageDetailGeneratedRequest(
  HomepageByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetHomepageIntroductionGeneratedRequest(
  HomepageByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetHomepageRelatedGroupsGeneratedRequest(
  HomepageByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetHomepageReviewSummaryGeneratedRequest(
  HomepageByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetHomepageShellGeneratedRequest(
  HomepageByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageGetObjectPageBundleGeneratedRequest(
  HomepageObjectPageBundleQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    queryParameters: <String, String>{
      if (request.referralSource != null)
        "referralSource": request.referralSource!,
      if (request.feedRequestId != null)
        "feedRequestId": request.feedRequestId!,
      if (request.recommendationTraceId != null)
        "recommendationTraceId": request.recommendationTraceId!,
      if (request.experimentBucket != null)
        "experimentBucket": request.experimentBucket!,
      if (request.rolloutCohort != null)
        "rolloutCohort": request.rolloutCohort!,
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageSearchHomepagesGeneratedRequest(
  HomepageSearchQuery request,
) {
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

CloudOperationRequestPayload
encodeEntityHomepageSuggestHomepageCandidateGeneratedRequest(
  SuggestHomepageCandidateCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "title": request.title,
      "homepageType": request.homepageType,
      if (request.subtitle != null) "subtitle": request.subtitle!,
      if (request.categoryTags.isNotEmpty)
        "categoryTags": request.categoryTags
            .map((value) => value)
            .toList(growable: false),
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.address != null) "address": request.address!,
      if (request.city != null) "city": request.city!,
      if (request.sourcePlaceId != null)
        "sourcePlaceId": request.sourcePlaceId!,
      if (request.location != null) "location": request.location!.toWire(),
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageUpdateClaimedHomepageBasicsGeneratedRequest(
  UpdateClaimedHomepageBasicsCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    body: <String, Object?>{
      if (request.title != null) "title": request.title!,
      if (request.subtitle != null) "subtitle": request.subtitle!,
      if (request.categoryTags != null)
        "categoryTags": request.categoryTags!
            .map((value) => value)
            .toList(growable: false),
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.address != null) "address": request.address!,
      if (request.city != null) "city": request.city!,
      if (request.location != null) "location": request.location!.toWire(),
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageClaimRequestCreateHomepageClaimRequestGeneratedRequest(
  CreateHomepageClaimRequestCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    body: <String, Object?>{
      "claimTier": request.claimTier,
      if (request.businessLicenseUrl != null)
        "businessLicenseUrl": request.businessLicenseUrl!,
      if (request.contactPhone != null) "contactPhone": request.contactPhone!,
      if (request.identityCardFrontUrl != null)
        "identityCardFrontUrl": request.identityCardFrontUrl!,
      if (request.identityCardBackUrl != null)
        "identityCardBackUrl": request.identityCardBackUrl!,
      if (request.note != null) "note": request.note!,
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageClaimRequestGetMyPendingHomepageClaimRequestGeneratedRequest(
  GetMyPendingHomepageClaimRequestQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageReviewCreateHomepageReviewGeneratedRequest(
  CreateHomepageReviewCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    body: <String, Object?>{
      "rating": request.rating,
      if (request.body != null) "body": request.body!,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      if (request.authorDisplayNameSnapshot != null)
        "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null)
        "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageReviewDeleteHomepageReviewGeneratedRequest(
  DeleteHomepageReviewCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"reviewId": request.reviewId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageReviewGetMyHomepageReviewGeneratedRequest(
  MyHomepageReviewQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
  );
}

CloudOperationRequestPayload
encodeEntityHomepageReviewListHomepageReviewsGeneratedRequest(
  HomepageReviewListQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageReviewUpdateHomepageReviewGeneratedRequest(
  UpdateHomepageReviewCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"reviewId": request.reviewId},
    body: <String, Object?>{
      "rating": request.rating,
      if (request.body != null) "body": request.body!,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      if (request.authorDisplayNameSnapshot != null)
        "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null)
        "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageStatusReportCreateHomepageStatusReportGeneratedRequest(
  CreateHomepageStatusReportCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    body: <String, Object?>{
      "reason": request.reason,
      if (request.description != null) "description": request.description!,
      if (request.evidenceUrls.isNotEmpty)
        "evidenceUrls": request.evidenceUrls
            .map((value) => value)
            .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeEntityHomepageStatusReportGetMyPendingHomepageStatusReportGeneratedRequest(
  GetMyPendingHomepageStatusReportQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"homepageId": request.homepageId},
    queryParameters: <String, String>{"reason": request.reason},
  );
}
