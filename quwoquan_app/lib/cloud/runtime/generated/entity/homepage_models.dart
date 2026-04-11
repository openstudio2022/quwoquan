// 混合维护：壳层预览/认领记录等由 entity/homepage/projections/*.yaml 生成（*.g.dart）再 export；
// 继承链（CanonicalReference/Summary/Detail）、HomepageShellData、Draft 仍手写；wire 收窄见 [HomepageWireCodec]。
// 字段与 quwoquan_service/contracts/metadata/entity/homepage/fields.yaml 对齐。
// 路由与 operation 常量：entity_api_metadata.g.dart、entity_request_page_ids.g.dart
// 审核类写请求体：entity_homepage_mutation_wires.g.dart（由 service.yaml writable_fields 生成）。
// 契约测试：test/cloud/entity/contract/homepage_repository_contract_test.dart

import 'package:quwoquan_app/cloud/runtime/codec/homepage_wire_codec.dart';

import 'homepage_content_preview.g.dart';
import 'homepage_geo_point.g.dart';
import 'homepage_question_preview.g.dart';
import 'homepage_related_group_summary.g.dart';
import 'homepage_review_summary_data.g.dart';

export 'homepage_claim_request_record.g.dart';
export 'homepage_content_preview.g.dart';
export 'homepage_geo_point.g.dart';
export 'homepage_question_preview.g.dart';
export 'homepage_related_group_summary.g.dart';
export 'homepage_review_dimension_score.g.dart';
export 'homepage_review_summary_data.g.dart';
export 'homepage_status_report_record.g.dart';

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

  static HomepageCanonicalReference? fromOptionalMap(
    Map<String, dynamic>? map,
  ) {
    if (map == null) {
      return null;
    }
    return HomepageCanonicalReference.fromMap(map);
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
      subtitle: HomepageWireCodec.optionalTrimmedString(map['subtitle']),
      coverUrl: HomepageWireCodec.optionalTrimmedString(map['coverUrl']),
      status: HomepageWireCodec.optionalTrimmedString(map['status']),
      city: HomepageWireCodec.optionalTrimmedString(map['city']),
      address: HomepageWireCodec.optionalTrimmedString(map['address']),
      averageRating: HomepageWireCodec.optionalDouble(map['averageRating']),
      ratingCount: (map['ratingCount'] as num?)?.toInt() ?? 0,
    );
  }

  /// Mock / 本地聚合：由 [HomepageDetail] 投影为搜索列表行（与 [fromMap] 字段一致）。
  factory HomepageSummary.fromDetail(HomepageDetail detail) {
    return HomepageSummary(
      id: detail.id,
      homepageType: detail.homepageType,
      title: detail.title,
      subtitle: detail.subtitle,
      coverUrl: detail.coverUrl,
      status: detail.status,
      city: detail.city,
      address: detail.address,
      averageRating: detail.averageRating,
      ratingCount: detail.ratingCount,
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
      subtitle: HomepageWireCodec.optionalTrimmedString(map['subtitle']),
      coverUrl: HomepageWireCodec.optionalTrimmedString(map['coverUrl']),
      status: HomepageWireCodec.optionalTrimmedString(map['status']),
      sourceType: HomepageWireCodec.optionalTrimmedString(map['sourceType']),
      claimStatus: HomepageWireCodec.optionalTrimmedString(map['claimStatus']),
      categoryTags:
          (map['categoryTags'] as List?)
              ?.map((item) => item.toString())
              .toList(growable: false) ??
          const <String>[],
      address: HomepageWireCodec.optionalTrimmedString(map['address']),
      city: HomepageWireCodec.optionalTrimmedString(map['city']),
      location: () {
        final loc = map['location'];
        return loc is Map
            ? HomepageGeoPoint.fromMap(
                Map<String, dynamic>.from(loc),
              )
            : null;
      }(),
      ownerUserId: HomepageWireCodec.optionalTrimmedString(map['ownerUserId']),
      averageRating: HomepageWireCodec.optionalDouble(map['averageRating']),
      ratingCount: (map['ratingCount'] as num?)?.toInt() ?? 0,
      reviewSummary: () {
        final rs = map['reviewSummary'];
        return rs is Map
            ? HomepageReviewSummaryData.fromMap(
                Map<String, dynamic>.from(rs),
              )
            : null;
      }(),
      contentPreview: HomepageWireCodec.mapList(
        map['contentPreview'],
        HomepageContentPreview.fromMap,
      ),
      questionPreview: HomepageWireCodec.mapList(
        map['questionPreview'],
        HomepageQuestionPreview.fromMap,
      ),
      relatedGroups: HomepageWireCodec.mapList(
        map['relatedGroups'],
        HomepageRelatedGroupSummary.fromMap,
      ),
      createdAt: HomepageWireCodec.optionalDateTime(map['createdAt']),
      updatedAt: HomepageWireCodec.optionalDateTime(map['updatedAt']),
      publishedAt: HomepageWireCodec.optionalDateTime(map['publishedAt']),
      offlineAt: HomepageWireCodec.optionalDateTime(map['offlineAt']),
    );
  }

  /// 深拷贝 / Mock 可变状态：未传入的字段沿用当前值。
  HomepageDetail copyWith({
    String? id,
    String? homepageType,
    String? title,
    String? subtitle,
    String? coverUrl,
    String? status,
    String? sourceType,
    String? claimStatus,
    List<String>? categoryTags,
    String? address,
    String? city,
    HomepageGeoPoint? location,
    String? ownerUserId,
    double? averageRating,
    int? ratingCount,
    HomepageReviewSummaryData? reviewSummary,
    List<HomepageContentPreview>? contentPreview,
    List<HomepageQuestionPreview>? questionPreview,
    List<HomepageRelatedGroupSummary>? relatedGroups,
    DateTime? createdAt,
    DateTime? updatedAt,
    DateTime? publishedAt,
    DateTime? offlineAt,
  }) {
    return HomepageDetail(
      id: id ?? this.id,
      homepageType: homepageType ?? this.homepageType,
      title: title ?? this.title,
      subtitle: subtitle ?? this.subtitle,
      coverUrl: coverUrl ?? this.coverUrl,
      status: status ?? this.status,
      sourceType: sourceType ?? this.sourceType,
      claimStatus: claimStatus ?? this.claimStatus,
      categoryTags: categoryTags ?? this.categoryTags,
      address: address ?? this.address,
      city: city ?? this.city,
      location: location ?? this.location,
      ownerUserId: ownerUserId ?? this.ownerUserId,
      averageRating: averageRating ?? this.averageRating,
      ratingCount: ratingCount ?? this.ratingCount,
      reviewSummary: reviewSummary ?? this.reviewSummary,
      contentPreview: contentPreview ?? this.contentPreview,
      questionPreview: questionPreview ?? this.questionPreview,
      relatedGroups: relatedGroups ?? this.relatedGroups,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      publishedAt: publishedAt ?? this.publishedAt,
      offlineAt: offlineAt ?? this.offlineAt,
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
      homepage: HomepageDetail.fromMap(HomepageWireCodec.stringKeyMapOrEmpty(map['homepage'])),
      reviewSummary: () {
        final rs = map['reviewSummary'];
        return rs is Map
            ? HomepageReviewSummaryData.fromMap(
                Map<String, dynamic>.from(rs),
              )
            : null;
      }(),
      contentPreview: HomepageWireCodec.mapList(
        map['contentPreview'],
        HomepageContentPreview.fromMap,
      ),
      questionPreview: HomepageWireCodec.mapList(
        map['questionPreview'],
        HomepageQuestionPreview.fromMap,
      ),
      relatedGroups: HomepageWireCodec.mapList(
        map['relatedGroups'],
        HomepageRelatedGroupSummary.fromMap,
      ),
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
