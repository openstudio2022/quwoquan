// App ViewData：只消费 canonical Entity generated contracts；不拥有 Cloud wire decoder。
// Remote wire 只允许经下方 fromWire(generatedType) factories 进入页面状态。

import 'package:quwoquan_cloud_contracts/generated/entity_contracts.dart'
    as wire;

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
    this.coverAssetId,
    this.coverAccessMode,
    this.city,
    this.address,
    this.averageRating,
    this.ratingCount = 0,
  });

  /// 封面的配对媒体资产标识与交付访问模式（DEC-033）；research 相位的
  /// coverUrl 是相对私有 CAS 引用，消费面按 coverAssetId 换短签。
  final String? coverAssetId;
  final wire.MediaDeliveryAccessMode? coverAccessMode;

  final String? city;
  final String? address;
  final double? averageRating;
  final int ratingCount;

  factory HomepageSummary.fromWire(wire.HomepageSearchItemView source) {
    return HomepageSummary(
      id: source.homepageId,
      homepageType: source.homepageType.wireName,
      title: source.title,
      canonicalEntityId: source.canonicalEntityId,
      subtitle: source.subtitle,
      coverUrl: source.coverUrl,
      coverAssetId: source.coverAssetId,
      coverAccessMode: source.coverAccessMode,
      city: source.city,
      address: source.address,
      status: source.status.wireName,
      averageRating: source.averageRating,
      ratingCount: source.ratingCount,
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
    this.coverAssetId,
    this.coverAccessMode,
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
    this.contentPreview = const <wire.HomepageContentPreview>[],
    this.questionPreview = const <wire.HomepageQuestionPreview>[],
    this.relatedGroups = const <wire.HomepageRelatedGroupSummary>[],
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.offlineAt,
  });

  /// hero 封面的配对媒体资产标识与交付访问模式（DEC-033）。
  /// signed_grant 时按 coverAssetId 换取短签；两者缺席即存量 public 交付，
  /// 不得按 coverUrl 形态反推交付形态。
  final String? coverAssetId;
  final wire.MediaDeliveryAccessMode? coverAccessMode;

  final String? sourceType;
  final String? claimStatus;
  final List<String> categoryTags;
  final String? address;
  final String? city;
  final wire.HomepageGeoPoint? location;
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
  final wire.HomepageReviewSummaryData? reviewSummary;
  final List<wire.HomepageContentPreview> contentPreview;
  final List<wire.HomepageQuestionPreview> questionPreview;
  final List<wire.HomepageRelatedGroupSummary> relatedGroups;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final DateTime? offlineAt;

  factory HomepageDetail.fromWire(wire.HomepageDetailView source) {
    return HomepageDetail(
      id: source.homepageId,
      homepageType: source.homepageType,
      title: source.title,
      subtitle: source.subtitle,
      coverUrl: source.coverUrl,
      coverAssetId: source.coverAssetId,
      coverAccessMode: source.coverAccessMode,
      status: source.status,
      claimStatus: source.claimStatus,
      categoryTags: source.categoryTags,
      address: source.address,
      city: source.city,
      location: source.location,
      ownerUserId: source.ownerUserId,
      ownerPersonaId: source.ownerPersonaId,
      viewerFollowsHomepage: source.viewerFollow.viewerFollowsHomepage,
      followerCount: source.viewerFollow.followerCount,
      verified: source.verified,
      establishedYear: source.establishedYear,
      averageRating: source.averageRating,
      ratingCount: source.ratingCount,
      reviewSummary: source.reviewSummary == null
          ? null
          : _reviewSummaryFromWire(source.reviewSummary!),
      contentPreview: source.contentPreview,
      questionPreview: source.questionPreview,
      relatedGroups: source.relatedGroups,
      createdAt: source.createdAt,
      updatedAt: source.updatedAt,
      publishedAt: source.publishedAt,
      offlineAt: source.offlineAt,
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
    String? canonicalEntityId,
    List<String>? categoryTags,
    String? address,
    String? city,
    wire.HomepageGeoPoint? location,
    String? ownerUserId,
    String? ownerPersonaId,
    bool? viewerFollowsHomepage,
    int? followerCount,
    bool? verified,
    int? establishedYear,
    double? averageRating,
    int? ratingCount,
    wire.HomepageReviewSummaryData? reviewSummary,
    List<wire.HomepageContentPreview>? contentPreview,
    List<wire.HomepageQuestionPreview>? questionPreview,
    List<wire.HomepageRelatedGroupSummary>? relatedGroups,
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
    this.contentPreview = const <wire.HomepageContentPreview>[],
    this.questionPreview = const <wire.HomepageQuestionPreview>[],
    this.relatedGroups = const <wire.HomepageRelatedGroupSummary>[],
  });

  final HomepageDetail homepage;
  final wire.HomepageReviewSummaryData? reviewSummary;
  final List<wire.HomepageContentPreview> contentPreview;
  final List<wire.HomepageQuestionPreview> questionPreview;
  final List<wire.HomepageRelatedGroupSummary> relatedGroups;

  factory HomepageShellData.fromWire(wire.HomepageShellView source) {
    return HomepageShellData(
      homepage: HomepageDetail.fromWire(source.homepage),
      reviewSummary: source.reviewSummary,
      contentPreview:
          source.contentPreview ?? const <wire.HomepageContentPreview>[],
      questionPreview:
          source.questionPreview ?? const <wire.HomepageQuestionPreview>[],
      relatedGroups:
          source.relatedGroups ?? const <wire.HomepageRelatedGroupSummary>[],
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
  final wire.HomepageGeoPoint? location;
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
  final wire.HomepageGeoPoint? location;
}

wire.HomepageReviewSummaryData _reviewSummaryFromWire(
  wire.HomepageReviewSummaryView source,
) {
  return wire.HomepageReviewSummaryData(
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
    highlightTags: source.highlightTags ?? const <String>[],
  );
}
