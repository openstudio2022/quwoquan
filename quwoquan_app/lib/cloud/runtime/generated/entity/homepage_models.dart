// App ViewData：只消费 canonical Entity generated contracts；不拥有 Cloud wire decoder。
// 继承链（CanonicalReference/Summary/Detail）、HomepageShellData、Draft 只表达页面状态。
// 字段与 quwoquan_service/contracts/metadata/entity/entity_homepage/homepage/fields.yaml 对齐。
// 路由与 operation 常量：entity_api_metadata.g.dart、entity_request_page_ids.g.dart
// 契约测试：test/cloud/entity/contract/homepage_repository_contract_test.dart

import 'package:quwoquan_app/cloud/runtime/codec/homepage_wire_codec.dart';
import 'package:quwoquan_cloud_contracts/generated/entity_contracts.dart'
    show
        HomepageContentPreview,
        HomepageGeoPoint,
        HomepageQuestionPreview,
        HomepageRelatedGroupSummary,
        HomepageReviewSummaryData;

export 'package:quwoquan_cloud_contracts/generated/entity_contracts.dart'
    show
        HomepageContentPreview,
        HomepageGeoPoint,
        HomepageQuestionPreview,
        HomepageRelatedGroupSummary,
        HomepageReviewSummaryData;

class HomepageCanonicalReference {
  const HomepageCanonicalReference({
    required this.id,
    required this.homepageType,
    required this.title,
    this.subtitle,
    this.coverUrl,
    this.status,
    this.canonicalEntityId,
  });

  final String id;
  final String homepageType;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final String? status;
  final String? canonicalEntityId;

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
      id: (map['homepageId'] ?? '').toString().trim(),
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
      canonicalEntityId: HomepageWireCodec.optionalTrimmedString(
        map['canonicalEntityId'],
      ),
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
        if (canonicalEntityId != null && canonicalEntityId!.isNotEmpty)
          'canonicalEntityId': canonicalEntityId,
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
      'canonicalEntityId': canonicalEntityId,
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
      canonicalEntityId: canonicalEntityId,
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
    super.canonicalEntityId,
    this.city,
    this.address,
    this.averageRating,
    this.ratingCount = 0,
  });

  final String? city;
  final String? address;
  final double? averageRating;
  final int ratingCount;

  /// Mock / 本地聚合：由 [HomepageDetail] 投影为搜索列表行。
  factory HomepageSummary.fromDetail(HomepageDetail detail) {
    return HomepageSummary(
      id: detail.id,
      homepageType: detail.homepageType,
      title: detail.title,
      subtitle: detail.subtitle,
      coverUrl: detail.coverUrl,
      status: detail.status,
      canonicalEntityId: detail.canonicalEntityId,
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
    super.canonicalEntityId,
    this.sourceType,
    this.claimStatus,
    this.categoryTags = const <String>[],
    this.address,
    this.city,
    this.location,
    this.ownerUserId,
    this.ownerPersonaId,
    this.viewerFollowsHomepage = false,
    this.followerCount = 0,
    this.verified = false,
    this.establishedYear,
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
  final String? ownerPersonaId;
  final bool viewerFollowsHomepage;
  final int followerCount;

  /// 实体主页官方认证标识（头部认证 badge）；缺省 false 不展示。
  final bool verified;

  /// 成立年份（基础信息行展示）；缺省不展示。
  final int? establishedYear;
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
    String? canonicalEntityId,
    List<String>? categoryTags,
    String? address,
    String? city,
    HomepageGeoPoint? location,
    String? ownerUserId,
    String? ownerPersonaId,
    bool? viewerFollowsHomepage,
    int? followerCount,
    bool? verified,
    int? establishedYear,
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
      canonicalEntityId: canonicalEntityId ?? this.canonicalEntityId,
      categoryTags: categoryTags ?? this.categoryTags,
      address: address ?? this.address,
      city: city ?? this.city,
      location: location ?? this.location,
      ownerUserId: ownerUserId ?? this.ownerUserId,
      ownerPersonaId: ownerPersonaId ?? this.ownerPersonaId,
      viewerFollowsHomepage:
          viewerFollowsHomepage ?? this.viewerFollowsHomepage,
      followerCount: followerCount ?? this.followerCount,
      verified: verified ?? this.verified,
      establishedYear: establishedYear ?? this.establishedYear,
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
    this.sourcePlaceId = '',
    this.location,
  });

  final String title;
  final String homepageType;
  final String subtitle;
  final List<String> categoryTags;
  final String coverUrl;
  final String address;
  final String city;
  final String sourcePlaceId;
  final HomepageGeoPoint? location;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'title': title,
    'homepageType': homepageType,
    if (subtitle.trim().isNotEmpty) 'subtitle': subtitle.trim(),
    if (categoryTags.isNotEmpty) 'categoryTags': categoryTags,
    if (coverUrl.trim().isNotEmpty) 'coverUrl': coverUrl.trim(),
    if (address.trim().isNotEmpty) 'address': address.trim(),
    if (city.trim().isNotEmpty) 'city': city.trim(),
    if (sourcePlaceId.trim().isNotEmpty) 'sourcePlaceId': sourcePlaceId.trim(),
    if (location != null) 'location': location!.toWire(),
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
    this.requesterPersonaId = '',
  });

  final String claimTier;
  final String contactPhone;
  final String businessLicenseUrl;
  final String identityCardFrontUrl;
  final String identityCardBackUrl;
  final String note;
  final String requesterPersonaId;

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
    if (location != null) 'location': location!.toWire(),
  };
}

class HomepageStatusReportDraft {
  const HomepageStatusReportDraft({
    required this.reason,
    this.description = '',
    this.evidenceUrls = const <String>[],
    this.reporterPersonaId = '',
  });

  final String reason;
  final String description;
  final List<String> evidenceUrls;
  final String reporterPersonaId;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'reason': reason,
    if (description.trim().isNotEmpty) 'description': description.trim(),
    if (evidenceUrls.isNotEmpty) 'evidenceUrls': evidenceUrls,
  };
}
