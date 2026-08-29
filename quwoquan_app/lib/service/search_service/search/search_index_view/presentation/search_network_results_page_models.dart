part of 'search_network_results_page.dart';

enum _IntersectionTargetType { circle, homepage, post, user, locationPlace }

class _IntersectionCardModel {
  const _IntersectionCardModel({
    required this.targetType,
    required this.targetId,
    required this.coverUrl,
    this.coverBinding = const MediaDeliveryBinding.absent(),
    required this.categoryLabel,
    required this.categoryIcon,
    required this.title,
    required this.reasonIcon,
    required this.reasonText,
    required this.footerText,
    this.metricLabel,
    this.metricIcon,
    this.showVideoBadge = false,
  });

  final _IntersectionTargetType targetType;
  final String targetId;
  final String coverUrl;

  /// 封面的 typed 交付绑定（DEC-033）；缺席时退回 [coverUrl] 的公开路。
  final MediaDeliveryBinding coverBinding;
  final String categoryLabel;
  final IconData categoryIcon;
  final String title;
  final IconData reasonIcon;
  final String reasonText;
  final String footerText;
  final String? metricLabel;
  final IconData? metricIcon;
  final bool showVideoBadge;
}

class _SearchNetworkTab {
  const _SearchNetworkTab({
    required this.id,
    required this.label,
    required this.description,
  });

  final String id;
  final String label;
  final String description;
}

class RelatedSearchTermCardView {
  const RelatedSearchTermCardView({required this.terms});

  final List<NetworkSearchSuggestion> terms;

  RelatedSearchTermCardView limited() {
    return RelatedSearchTermCardView(
      terms: terms.take(5).toList(growable: false),
    );
  }
}

/// 云侧内容命中的排序 / 封面 / 理由元信息（R-001/R-003）。
///
/// 与 [PostSearchItemView] 解耦：仅承载云侧透传字段，按 postId 旁挂到结果页状态，
/// 避免改动跨 tab 共享的 [PostSearchItemView] 字段表（其被交集 tab 等多处消费）。
class _ContentCloudMeta {
  const _ContentCloudMeta({
    this.rankPosition,
    this.coverWidth,
    this.coverHeight,
    this.rankReasons = const <String>[],
  });

  final int? rankPosition;
  final double? coverWidth;
  final double? coverHeight;
  final List<String> rankReasons;

  /// 是否携带任一云侧信号；未携带可选信号的命中不入元信息表。
  bool get hasCloudSignal =>
      rankPosition != null ||
      coverWidth != null ||
      coverHeight != null ||
      rankReasons.isNotEmpty;

  /// 云侧封面真实宽高比；缺失任一维度则返回 null，由调用方使用既定默认比例。
  double? get aspectRatio {
    final width = coverWidth;
    final height = coverHeight;
    if (width == null || height == null || width <= 0 || height <= 0) {
      return null;
    }
    return width / height;
  }

  /// 首条排序理由（人类可读标签），用于卡片排序透明化文案。
  String? get topRankReason => rankReasons.isEmpty ? null : rankReasons.first;
}

class _NetworkResultCardModel {
  const _NetworkResultCardModel({
    required this.postId,
    required this.title,
    required this.supportingText,
    required this.coverUrl,
    this.coverBinding = const MediaDeliveryBinding.absent(),
    required this.footerLabel,
    required this.eyebrowText,
    required this.likeCount,
    required this.showVideoBadge,
  });

  final String postId;
  final String title;
  final String supportingText;
  final String coverUrl;

  /// 封面的 typed 交付绑定（DEC-033）；缺席时退回 [coverUrl] 的公开路。
  final MediaDeliveryBinding coverBinding;
  final String footerLabel;
  final String eyebrowText;
  final int likeCount;
  final bool showVideoBadge;

  factory _NetworkResultCardModel.fromSearchItem(PostSearchItemView item) {
    final footerSegments = <String>[
      if ((item.authorDisplayName ?? '').trim().isNotEmpty)
        item.authorDisplayName!.trim(),
    ];
    return _NetworkResultCardModel(
      postId: item.postId,
      // 交付形态取自搜索投影声明（DEC-033），不从 URL 形态反推。
      coverBinding: MediaDeliveryBinding(
        assetId: item.coverAssetId?.trim() ?? '',
        accessMode: item.coverAccessMode,
        publicUrl: item.coverUrl ?? '',
      ),
      title: item.title?.trim().isNotEmpty == true
          ? item.title!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : (item.summary?.trim().isNotEmpty == true
                      ? item.summary!.trim()
                      : (item.authorDisplayName?.trim().isNotEmpty == true
                            ? item.authorDisplayName!.trim()
                            : SearchText.searchNetworkResults))),
      supportingText: item.summary?.trim().isNotEmpty == true
          ? item.summary!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : SearchText.searchOpenRelatedContent),
      coverUrl: item.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty
          ? SearchText.searchContentResults
          : footerSegments.join(' · '),
      eyebrowText: item.subCategory?.trim().isNotEmpty == true
          ? item.subCategory!.trim()
          : SearchText.searchNetworkResults,
      likeCount: item.likeCount,
      showVideoBadge: item.contentType == 'video',
    );
  }
}

class _EntityTopResultModel {
  const _EntityTopResultModel({
    required this.homepageId,
    required this.title,
    required this.badge,
    required this.subtitle,
    required this.description,
    required this.meta,
    this.connectionReason,
    this.actionLabel,
  });

  final String homepageId;
  final String title;
  final String badge;
  final String subtitle;
  final String description;
  final String meta;
  final String? connectionReason;
  final String? actionLabel;
}

class _LocationPlaceTopResultModel {
  const _LocationPlaceTopResultModel({required this.place});

  final SearchLocationPlaceHitView place;
}

class _GroupResultCardModel {
  const _GroupResultCardModel({
    required this.circleId,
    required this.title,
    required this.supportingText,
    required this.coverUrl,
    required this.footerLabel,
    required this.eyebrowText,
  });

  final String circleId;
  final String title;
  final String supportingText;
  final String coverUrl;
  final String footerLabel;
  final String eyebrowText;

  factory _GroupResultCardModel.fromHit(SearchHit hit) {
    final isCircle = hit.objectType == SearchObjectType.circleCircle;
    final view =
        (isCircle ? hit.asCircleCircleItem : hit.asCircleGroupItem) ??
        CircleSearchHitViewData(
          circleId: hit.objectId,
          name: hit.title,
          description: hit.snippet,
          memberCount: 0,
          postCount: 0,
        );
    final circleId = isCircle
        ? hit.objectId
        : (view.circleId.isNotEmpty ? view.circleId : hit.objectId);
    final memberCount = view.memberCount;
    final postCount = view.postCount;
    final circleNameLabel = view.circleName?.trim() ?? '';
    final footerSegments = <String>[
      if (circleNameLabel.isNotEmpty) circleNameLabel,
      if (memberCount > 0) UITextConstants.searchMemberCount(memberCount),
      if (postCount > 0) UITextConstants.searchPostCount(postCount),
      if (hit.resolvedFrom == SearchResolvedFrom.localFallback)
        SearchText.searchLocalFallback,
    ];
    return _GroupResultCardModel(
      circleId: circleId,
      title: hit.title,
      supportingText: hit.snippet?.trim().isNotEmpty == true
          ? hit.snippet!.trim()
          : (hit.subtitle?.trim().isNotEmpty == true
                ? hit.subtitle!.trim()
                : SearchText.searchOpenRelatedCircle),
      coverUrl: view.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty
          ? SearchText.searchDiscussionResults
          : footerSegments.join(' · '),
      eyebrowText: isCircle
          ? SearchText.searchCategoryCircle
          : SearchText.searchCategoryDiscussion,
    );
  }
}
