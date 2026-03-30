// 手写维护：非机器 codegen。字段与契约对齐见：
// quwoquan_service/contracts/metadata/entity/homepage/fields.yaml
// 路由与 operation 常量：entity_api_metadata.g.dart、entity_request_page_ids.g.dart

class HomepageCanonicalReference {
  const HomepageCanonicalReference({
    required this.id,
    required this.homepageType,
    required this.title,
    this.subtitle,
    this.coverUrl,
    this.status,
  });

  final String id;
  final String homepageType;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final String? status;

  static HomepageCanonicalReference? fromOptionalMap(Map? map) {
    if (map == null) {
      return null;
    }
    return HomepageCanonicalReference.fromMap(Map<String, dynamic>.from(map));
  }

  factory HomepageCanonicalReference.fromMap(Map<String, dynamic> map) {
    return HomepageCanonicalReference(
      id: (map['_id'] ?? map['homepageId'] ?? map['id'] ?? '')
          .toString()
          .trim(),
      homepageType: (map['homepageType'] ?? '').toString().trim(),
      title: (map['title'] ?? '').toString().trim(),
      subtitle: (map['subtitle'] ?? '').toString().trim().isEmpty
          ? null
          : (map['subtitle'] ?? '').toString().trim(),
      coverUrl: (map['coverUrl'] ?? '').toString().trim().isEmpty
          ? null
          : (map['coverUrl'] ?? '').toString().trim(),
      status: (map['status'] ?? '').toString().trim().isEmpty
          ? null
          : (map['status'] ?? '').toString().trim(),
    );
  }

  Map<String, dynamic> toPayloadFields() {
    return <String, dynamic>{
      'primaryHomepageId': id,
      'primaryHomepageType': homepageType,
      'primaryHomepageSnapshot': <String, dynamic>{
        'title': title,
        if (subtitle != null && subtitle!.isNotEmpty) 'subtitle': subtitle,
        if (coverUrl != null && coverUrl!.isNotEmpty) 'coverUrl': coverUrl,
        if (status != null && status!.isNotEmpty) 'status': status,
      },
    };
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'homepageType': homepageType,
      'title': title,
      'subtitle': subtitle,
      'coverUrl': coverUrl,
      'status': status,
    };
  }

  HomepageCanonicalReference get canonicalReference {
    return HomepageCanonicalReference(
      id: id,
      homepageType: homepageType,
      title: title,
      subtitle: subtitle,
      coverUrl: coverUrl,
      status: status,
    );
  }
}

class HomepageSummary extends HomepageCanonicalReference {
  const HomepageSummary({
    required super.id,
    required super.homepageType,
    required super.title,
    super.subtitle,
    super.coverUrl,
    super.status,
    this.city,
    this.address,
    this.averageRating,
    this.ratingCount = 0,
  });

  final String? city;
  final String? address;
  final double? averageRating;
  final int ratingCount;

  factory HomepageSummary.fromMap(Map<String, dynamic> map) {
    return HomepageSummary(
      id: (map['homepageId'] ?? map['_id'] ?? map['id'] ?? '')
          .toString()
          .trim(),
      homepageType: (map['homepageType'] ?? '').toString().trim(),
      title: (map['title'] ?? '').toString().trim(),
      subtitle: _optionalString(map['subtitle']),
      coverUrl: _optionalString(map['coverUrl']),
      status: _optionalString(map['status']),
      city: _optionalString(map['city']),
      address: _optionalString(map['address']),
      averageRating: _optionalDouble(map['averageRating']),
      ratingCount: (map['ratingCount'] as num?)?.toInt() ?? 0,
    );
  }
}

class HomepageDetail extends HomepageCanonicalReference {
  const HomepageDetail({
    required super.id,
    required super.homepageType,
    required super.title,
    super.subtitle,
    super.coverUrl,
    super.status,
    this.sourceType,
    this.claimStatus,
    this.categoryTags = const <String>[],
    this.address,
    this.city,
    this.location,
    this.ownerUserId,
    this.averageRating,
    this.ratingCount = 0,
    this.reviewSummary,
    this.contentPreview = const <HomepageContentPreview>[],
    this.questionPreview = const <HomepageQuestionPreview>[],
    this.relatedGroups = const <HomepageRelatedGroupSummary>[],
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.offlineAt,
  });

  final String? sourceType;
  final String? claimStatus;
  final List<String> categoryTags;
  final String? address;
  final String? city;
  final HomepageGeoPoint? location;
  final String? ownerUserId;
  final double? averageRating;
  final int ratingCount;
  final HomepageReviewSummaryData? reviewSummary;
  final List<HomepageContentPreview> contentPreview;
  final List<HomepageQuestionPreview> questionPreview;
  final List<HomepageRelatedGroupSummary> relatedGroups;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final DateTime? offlineAt;

  factory HomepageDetail.fromMap(Map<String, dynamic> map) {
    return HomepageDetail(
      id: (map['_id'] ?? map['homepageId'] ?? map['id'] ?? '')
          .toString()
          .trim(),
      homepageType: (map['homepageType'] ?? '').toString().trim(),
      title: (map['title'] ?? '').toString().trim(),
      subtitle: _optionalString(map['subtitle']),
      coverUrl: _optionalString(map['coverUrl']),
      status: _optionalString(map['status']),
      sourceType: _optionalString(map['sourceType']),
      claimStatus: _optionalString(map['claimStatus']),
      categoryTags:
          (map['categoryTags'] as List?)
              ?.map((item) => item.toString())
              .toList(growable: false) ??
          const <String>[],
      address: _optionalString(map['address']),
      city: _optionalString(map['city']),
      location: map['location'] is Map
          ? HomepageGeoPoint.fromMap(
              (map['location'] as Map).cast<String, dynamic>(),
            )
          : null,
      ownerUserId: _optionalString(map['ownerUserId']),
      averageRating: _optionalDouble(map['averageRating']),
      ratingCount: (map['ratingCount'] as num?)?.toInt() ?? 0,
      reviewSummary: map['reviewSummary'] is Map
          ? HomepageReviewSummaryData.fromMap(
              (map['reviewSummary'] as Map).cast<String, dynamic>(),
            )
          : null,
      contentPreview:
          (map['contentPreview'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageContentPreview.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageContentPreview>[],
      questionPreview:
          (map['questionPreview'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageQuestionPreview.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageQuestionPreview>[],
      relatedGroups:
          (map['relatedGroups'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageRelatedGroupSummary.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageRelatedGroupSummary>[],
      createdAt: _optionalDateTime(map['createdAt']),
      updatedAt: _optionalDateTime(map['updatedAt']),
      publishedAt: _optionalDateTime(map['publishedAt']),
      offlineAt: _optionalDateTime(map['offlineAt']),
    );
  }
}

class HomepageGeoPoint {
  const HomepageGeoPoint({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;

  factory HomepageGeoPoint.fromMap(Map<String, dynamic> map) {
    return HomepageGeoPoint(
      latitude: (map['latitude'] as num?)?.toDouble() ?? 0,
      longitude: (map['longitude'] as num?)?.toDouble() ?? 0,
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
    'latitude': latitude,
    'longitude': longitude,
  };
}

class HomepageReviewDimensionScore {
  const HomepageReviewDimensionScore({
    required this.label,
    required this.score,
  });

  final String label;
  final double score;

  factory HomepageReviewDimensionScore.fromMap(Map<String, dynamic> map) {
    return HomepageReviewDimensionScore(
      label: (map['label'] ?? '').toString().trim(),
      score: (map['score'] as num?)?.toDouble() ?? 0,
    );
  }
}

class HomepageReviewSummaryData {
  const HomepageReviewSummaryData({
    this.averageRating,
    this.ratingCount = 0,
    this.highlightTags = const <String>[],
    this.dimensionScores = const <HomepageReviewDimensionScore>[],
  });

  final double? averageRating;
  final int ratingCount;
  final List<String> highlightTags;
  final List<HomepageReviewDimensionScore> dimensionScores;

  factory HomepageReviewSummaryData.fromMap(Map<String, dynamic> map) {
    return HomepageReviewSummaryData(
      averageRating: _optionalDouble(map['averageRating']),
      ratingCount: (map['ratingCount'] as num?)?.toInt() ?? 0,
      highlightTags:
          (map['highlightTags'] as List?)
              ?.map((item) => item.toString())
              .toList(growable: false) ??
          const <String>[],
      dimensionScores:
          (map['dimensionScores'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageReviewDimensionScore.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageReviewDimensionScore>[],
    );
  }
}

class HomepageContentPreview {
  const HomepageContentPreview({
    required this.postId,
    required this.title,
    this.summary,
    this.contentType,
    this.coverUrl,
  });

  final String postId;
  final String title;
  final String? summary;
  final String? contentType;
  final String? coverUrl;

  factory HomepageContentPreview.fromMap(Map<String, dynamic> map) {
    return HomepageContentPreview(
      postId: (map['postId'] ?? '').toString().trim(),
      title: (map['title'] ?? '').toString().trim(),
      summary: _optionalString(map['summary']),
      contentType: _optionalString(map['contentType']),
      coverUrl: _optionalString(map['coverUrl']),
    );
  }
}

class HomepageQuestionPreview {
  const HomepageQuestionPreview({
    required this.postId,
    required this.title,
    this.summary,
  });

  final String postId;
  final String title;
  final String? summary;

  factory HomepageQuestionPreview.fromMap(Map<String, dynamic> map) {
    return HomepageQuestionPreview(
      postId: (map['postId'] ?? '').toString().trim(),
      title: (map['title'] ?? '').toString().trim(),
      summary: _optionalString(map['summary']),
    );
  }
}

class HomepageRelatedGroupSummary {
  const HomepageRelatedGroupSummary({
    required this.circleId,
    required this.name,
    this.memberCount = 0,
    this.linkedHomepageId,
    this.linkedHomepageTitle,
  });

  final String circleId;
  final String name;
  final int memberCount;
  final String? linkedHomepageId;
  final String? linkedHomepageTitle;

  factory HomepageRelatedGroupSummary.fromMap(Map<String, dynamic> map) {
    return HomepageRelatedGroupSummary(
      circleId: (map['circleId'] ?? map['id'] ?? '').toString().trim(),
      name: (map['name'] ?? '').toString().trim(),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      linkedHomepageId: _optionalString(map['linkedHomepageId']),
      linkedHomepageTitle: _optionalString(map['linkedHomepageTitle']),
    );
  }
}

class HomepageShellData {
  const HomepageShellData({
    required this.homepage,
    this.reviewSummary,
    this.contentPreview = const <HomepageContentPreview>[],
    this.questionPreview = const <HomepageQuestionPreview>[],
    this.relatedGroups = const <HomepageRelatedGroupSummary>[],
  });

  final HomepageDetail homepage;
  final HomepageReviewSummaryData? reviewSummary;
  final List<HomepageContentPreview> contentPreview;
  final List<HomepageQuestionPreview> questionPreview;
  final List<HomepageRelatedGroupSummary> relatedGroups;

  factory HomepageShellData.fromMap(Map<String, dynamic> map) {
    return HomepageShellData(
      homepage: HomepageDetail.fromMap(
        (map['homepage'] as Map? ?? const <String, dynamic>{})
            .cast<String, dynamic>(),
      ),
      reviewSummary: map['reviewSummary'] is Map
          ? HomepageReviewSummaryData.fromMap(
              (map['reviewSummary'] as Map).cast<String, dynamic>(),
            )
          : null,
      contentPreview:
          (map['contentPreview'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageContentPreview.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageContentPreview>[],
      questionPreview:
          (map['questionPreview'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageQuestionPreview.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageQuestionPreview>[],
      relatedGroups:
          (map['relatedGroups'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => HomepageRelatedGroupSummary.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <HomepageRelatedGroupSummary>[],
    );
  }
}

class HomepageSuggestionDraft {
  const HomepageSuggestionDraft({
    required this.title,
    required this.homepageType,
    this.subtitle = '',
    this.categoryTags = const <String>[],
    this.coverUrl = '',
    this.address = '',
    this.city = '',
    this.location,
  });

  final String title;
  final String homepageType;
  final String subtitle;
  final List<String> categoryTags;
  final String coverUrl;
  final String address;
  final String city;
  final HomepageGeoPoint? location;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'title': title,
    'homepageType': homepageType,
    if (subtitle.trim().isNotEmpty) 'subtitle': subtitle.trim(),
    if (categoryTags.isNotEmpty) 'categoryTags': categoryTags,
    if (coverUrl.trim().isNotEmpty) 'coverUrl': coverUrl.trim(),
    if (address.trim().isNotEmpty) 'address': address.trim(),
    if (city.trim().isNotEmpty) 'city': city.trim(),
    if (location != null) 'location': location!.toMap(),
  };
}

class HomepageClaimRequestDraft {
  const HomepageClaimRequestDraft({
    required this.claimTier,
    required this.contactPhone,
    this.businessLicenseUrl = '',
    this.identityCardFrontUrl = '',
    this.identityCardBackUrl = '',
    this.note = '',
    this.requesterUserId = '',
  });

  final String claimTier;
  final String contactPhone;
  final String businessLicenseUrl;
  final String identityCardFrontUrl;
  final String identityCardBackUrl;
  final String note;
  final String requesterUserId;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'claimTier': claimTier,
    'contactPhone': contactPhone,
    if (businessLicenseUrl.trim().isNotEmpty)
      'businessLicenseUrl': businessLicenseUrl.trim(),
    if (identityCardFrontUrl.trim().isNotEmpty)
      'identityCardFrontUrl': identityCardFrontUrl.trim(),
    if (identityCardBackUrl.trim().isNotEmpty)
      'identityCardBackUrl': identityCardBackUrl.trim(),
    if (note.trim().isNotEmpty) 'note': note.trim(),
    if (requesterUserId.trim().isNotEmpty)
      'requesterUserId': requesterUserId.trim(),
  };
}

class HomepageClaimRequestRecord {
  const HomepageClaimRequestRecord({
    required this.id,
    required this.homepageId,
    required this.requesterUserId,
    required this.claimTier,
    required this.status,
    this.reviewNote,
    this.createdAt,
    this.reviewedAt,
  });

  final String id;
  final String homepageId;
  final String requesterUserId;
  final String claimTier;
  final String status;
  final String? reviewNote;
  final DateTime? createdAt;
  final DateTime? reviewedAt;

  factory HomepageClaimRequestRecord.fromMap(Map<String, dynamic> map) {
    return HomepageClaimRequestRecord(
      id: (map['_id'] ?? map['id'] ?? '').toString().trim(),
      homepageId: (map['homepageId'] ?? '').toString().trim(),
      requesterUserId: (map['requesterUserId'] ?? '').toString().trim(),
      claimTier: (map['claimTier'] ?? '').toString().trim(),
      status: (map['status'] ?? '').toString().trim(),
      reviewNote: _optionalString(map['reviewNote']),
      createdAt: _optionalDateTime(map['createdAt']),
      reviewedAt: _optionalDateTime(map['reviewedAt']),
    );
  }
}

class HomepageBasicDraft {
  const HomepageBasicDraft({
    this.title,
    this.subtitle,
    this.categoryTags,
    this.coverUrl,
    this.address,
    this.city,
    this.location,
  });

  final String? title;
  final String? subtitle;
  final List<String>? categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final HomepageGeoPoint? location;

  Map<String, dynamic> toMap() => <String, dynamic>{
    if (title != null && title!.trim().isNotEmpty) 'title': title!.trim(),
    if (subtitle != null && subtitle!.trim().isNotEmpty)
      'subtitle': subtitle!.trim(),
    if (categoryTags != null && categoryTags!.isNotEmpty)
      'categoryTags': categoryTags,
    if (coverUrl != null && coverUrl!.trim().isNotEmpty)
      'coverUrl': coverUrl!.trim(),
    if (address != null && address!.trim().isNotEmpty)
      'address': address!.trim(),
    if (city != null && city!.trim().isNotEmpty) 'city': city!.trim(),
    if (location != null) 'location': location!.toMap(),
  };
}

class HomepageStatusReportDraft {
  const HomepageStatusReportDraft({
    required this.reason,
    this.description = '',
    this.evidenceUrls = const <String>[],
    this.reporterUserId = '',
  });

  final String reason;
  final String description;
  final List<String> evidenceUrls;
  final String reporterUserId;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'reason': reason,
    if (description.trim().isNotEmpty) 'description': description.trim(),
    if (evidenceUrls.isNotEmpty) 'evidenceUrls': evidenceUrls,
    if (reporterUserId.trim().isNotEmpty)
      'reporterUserId': reporterUserId.trim(),
  };
}

class HomepageStatusReportRecord {
  const HomepageStatusReportRecord({
    required this.id,
    required this.homepageId,
    required this.reporterUserId,
    required this.reason,
    required this.status,
    this.description,
    this.evidenceUrls = const <String>[],
    this.reviewNote,
    this.createdAt,
    this.reviewedAt,
  });

  final String id;
  final String homepageId;
  final String reporterUserId;
  final String reason;
  final String status;
  final String? description;
  final List<String> evidenceUrls;
  final String? reviewNote;
  final DateTime? createdAt;
  final DateTime? reviewedAt;

  factory HomepageStatusReportRecord.fromMap(Map<String, dynamic> map) {
    return HomepageStatusReportRecord(
      id: (map['_id'] ?? map['id'] ?? '').toString().trim(),
      homepageId: (map['homepageId'] ?? '').toString().trim(),
      reporterUserId: (map['reporterUserId'] ?? '').toString().trim(),
      reason: (map['reason'] ?? '').toString().trim(),
      status: (map['status'] ?? '').toString().trim(),
      description: _optionalString(map['description']),
      evidenceUrls:
          (map['evidenceUrls'] as List?)
              ?.map((item) => item.toString())
              .toList(growable: false) ??
          const <String>[],
      reviewNote: _optionalString(map['reviewNote']),
      createdAt: _optionalDateTime(map['createdAt']),
      reviewedAt: _optionalDateTime(map['reviewedAt']),
    );
  }
}

String? _optionalString(Object? value) {
  final raw = (value ?? '').toString().trim();
  return raw.isEmpty ? null : raw;
}

double? _optionalDouble(Object? value) {
  return (value as num?)?.toDouble();
}

DateTime? _optionalDateTime(Object? value) {
  final raw = (value ?? '').toString().trim();
  if (raw.isEmpty) {
    return null;
  }
  return DateTime.tryParse(raw);
}
