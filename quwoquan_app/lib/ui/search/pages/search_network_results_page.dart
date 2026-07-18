import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/content/models/content_route_models.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/ui/discovery/services/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/search/models/search_result_tab_spec.dart';
import 'package:quwoquan_app/ui/search/pages/location_place_landing_page.dart';
import 'package:quwoquan_app/ui/search/services/search_network_results_media_wiring.dart';
part 'search_network_results_page_state.dart';
part 'search_network_results_page_state_helpers.dart';

class _SearchResultTokens {
  _SearchResultTokens._();

  static const double sectionTitleSize = AppTypography.iosBody;
  static const FontWeight sectionTitleWeight = AppTypography.semiBold;
  static const double bodySize = AppTypography.iosCallout;
  static const FontWeight bodyWeight = AppTypography.regular;
  static const double cardTitleSize = AppTypography.iosFootnote;
  static const double captionSize = AppTypography.iosCaption1;
}

class SearchNetworkResultsPage extends ConsumerStatefulWidget {
  const SearchNetworkResultsPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<SearchNetworkResultsPage> createState() =>
      _SearchNetworkResultsPageState();
}

class _XiaoquSummaryCard extends StatelessWidget {
  const _XiaoquSummaryCard({
    required this.query,
    required this.result,
    required this.isDark,
  });

  final String query;
  final AssistantSearchResultView? result;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(
          color: AppColors.primaryColor.withValues(alpha: 0.18),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  CupertinoIcons.sparkles,
                  color: AppColors.assistantMarkColor,
                  size: AppSpacing.iconMedium,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Text(
                  '小趣',
                  style: TextStyle(
                    fontSize: _SearchResultTokens.sectionTitleSize,
                    fontWeight: _SearchResultTokens.sectionTitleWeight,
                    color: fgPrimary,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              query.trim().isEmpty ? '为你整理了当前热门网络结果' : '正在为你整理“$query”的网络结果',
              style: TextStyle(
                fontSize: _SearchResultTokens.bodySize,
                fontWeight: _SearchResultTokens.bodyWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              (result?.summary?.trim().isNotEmpty == true)
                  ? result!.summary!.trim()
                  : '先按圈子讨论分类聚合内容，再把最相关的创作和讨论铺开，方便继续筛选。',
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgSecondary,
              ),
            ),
            if ((result?.citations?.length ?? 0) > 0) ...[
              SizedBox(height: AppSpacing.containerSm),
              Text(
                '已整理 ${result!.citations!.length} 条可继续查看的引用线索',
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: fgSecondary,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusMessage extends StatelessWidget {
  const _StatusMessage({required this.text, required this.isDark});

  final String text;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerLg),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              text,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: fgSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CategorySummaryCard extends StatelessWidget {
  const _CategorySummaryCard({
    required this.title,
    required this.description,
    required this.count,
    required this.isDark,
  });

  final String title;
  final String description;
  final int count;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.containerMd),
      child: Text(
        '$title · $count 条结果${description.isEmpty ? '' : ' · $description'}',
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: fgSecondary,
        ),
      ),
    );
  }
}

class _SearchResultSectionHeader extends StatelessWidget {
  const _SearchResultSectionHeader({
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontSize: _SearchResultTokens.sectionTitleSize,
                  fontWeight: _SearchResultTokens.sectionTitleWeight,
                  color: fgPrimary,
                ),
              ),
              if (subtitle != null && subtitle!.trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  subtitle!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: fgSecondary,
                  ),
                ),
              ],
            ],
          ),
        ),
        if (actionLabel != null && onAction != null)
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onAction,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  actionLabel!,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs / 2),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: fgSecondary,
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _MediaCategoryBadge extends StatelessWidget {
  const _MediaCategoryBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.intraGroupSm,
          vertical: AppSpacing.intraGroupXs / 2,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            color: AppColors.white,
          ),
        ),
      ),
    );
  }
}

class _IntersectionCardPlaceholder extends StatelessWidget {
  const _IntersectionCardPlaceholder({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.primaryColor.withValues(alpha: 0.08),
      child: Center(
        child: Icon(
          icon,
          color: AppColors.primaryColor,
          size: AppSpacing.iconLarge,
        ),
      ),
    );
  }
}

class _IntersectionCard extends StatelessWidget {
  const _IntersectionCard({
    required this.model,
    required this.isDark,
    required this.onTap,
  });

  final _IntersectionCardModel model;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final hasCover = model.coverUrl.trim().isNotEmpty;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 16 / 10,
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.contentPreviewCornerRadius),
                ),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (hasCover)
                      AppCachedNetworkImage(
                        imageUrl: model.coverUrl,
                        fit: BoxFit.cover,
                        cdnPreset: CdnImagePreset.cover,
                        placeholder: _IntersectionCardPlaceholder(
                          icon: model.categoryIcon,
                        ),
                        errorWidget: _IntersectionCardPlaceholder(
                          icon: model.categoryIcon,
                        ),
                      )
                    else
                      _IntersectionCardPlaceholder(icon: model.categoryIcon),
                    Positioned(
                      top: AppSpacing.postPreviewCardPadding,
                      left: AppSpacing.postPreviewCardPadding,
                      child: _MediaCategoryBadge(label: model.categoryLabel),
                    ),
                    if (model.showVideoBadge)
                      Positioned(
                        top: AppSpacing.postPreviewCardPadding,
                        right: AppSpacing.postPreviewCardPadding,
                        child: Icon(
                          CupertinoIcons.play_circle_fill,
                          color: AppColors.white,
                          size: AppSpacing.iconLarge - AppSpacing.xs,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(AppSpacing.postPreviewCardPadding),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    model.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.medium,
                      color: fgPrimary,
                    ),
                  ),
                  // §3：交集句只在有云侧文案时展示；无 primaryText 不渲染句行、不占位。
                  if (model.reasonText.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Row(
                      children: [
                        Icon(
                          model.reasonIcon,
                          size: AppSpacing.iconSmall,
                          color: AppColors.primaryColor,
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs / 2),
                        Expanded(
                          child: Text(
                            model.reasonText,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption1,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          model.footerText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosCaption1,
                            color: fgSecondary,
                          ),
                        ),
                      ),
                      if (model.metricLabel != null) ...[
                        SizedBox(width: AppSpacing.intraGroupXs),
                        PostCardMetric(
                          icon: model.metricIcon ?? CupertinoIcons.heart,
                          label: model.metricLabel!,
                          color: fgSecondary,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EntityTopResultCard extends StatelessWidget {
  const _EntityTopResultCard({
    required this.entity,
    required this.isDark,
    required this.onTap,
  });

  final _EntityTopResultModel entity;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            Container(
              width: AppSpacing.avatarUserLg,
              height: AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.building_2_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.primaryColor,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          entity.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: _SearchResultTokens.sectionTitleSize,
                            fontWeight: _SearchResultTokens.sectionTitleWeight,
                            color: fgPrimary,
                          ),
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupSm),
                      Text(
                        entity.badge,
                        style: TextStyle(
                          fontSize: _SearchResultTokens.captionSize,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Text(
                    entity.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: fgSecondary,
                    ),
                  ),
                  if (entity.connectionReason != null &&
                      entity.connectionReason!.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.connectionReason!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ],
                  if (entity.description.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                  if (entity.meta.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.meta,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            if (entity.actionLabel != null) ...[
              DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  border: Border.all(color: AppColors.primaryColor),
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Text(
                    entity.actionLabel!,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
              ),
            ] else
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
          ],
        ),
      ),
    );
  }
}

class _RelatedSearchCard extends StatelessWidget {
  const _RelatedSearchCard({
    required this.card,
    required this.isDark,
    required this.onTap,
  });

  final RelatedSearchTermCardView card;
  final bool isDark;
  final ValueChanged<NetworkSearchSuggestion> onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              UITextConstants.searchRelatedTitle,
              style: TextStyle(
                fontSize: _SearchResultTokens.cardTitleSize,
                fontWeight: _SearchResultTokens.sectionTitleWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            for (var i = 0; i < card.terms.length; i++)
              Padding(
                padding: EdgeInsets.only(
                  bottom: i == card.terms.length - 1
                      ? 0
                      : AppSpacing.intraGroupSm,
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => onTap(card.terms[i]),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      card.terms[i].displayTitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.bodySize,
                        fontWeight: _SearchResultTokens.bodyWeight,
                        color: fgPrimary,
                      ),
                    ),
                  ),
                ),
              ),
            if (card.terms.isEmpty)
              Text(
                UITextConstants.searchRelatedEmpty,
                style: TextStyle(
                  fontSize: _SearchResultTokens.captionSize,
                  color: fgSecondary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

enum _IntersectionTargetType { circle, homepage, post, user, locationPlace }

class _IntersectionCardModel {
  const _IntersectionCardModel({
    required this.targetType,
    required this.targetId,
    required this.coverUrl,
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

  /// 是否携带任一云侧信号；无信号的命中（本地/mock）不入元信息表。
  bool get hasCloudSignal =>
      rankPosition != null ||
      coverWidth != null ||
      coverHeight != null ||
      rankReasons.isNotEmpty;

  /// 云侧封面真实宽高比；缺失任一维度则返回 null，由调用方回退默认比例。
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
    required this.footerLabel,
    required this.eyebrowText,
    required this.likeCount,
    required this.showVideoBadge,
  });

  final String postId;
  final String title;
  final String supportingText;
  final String coverUrl;
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
      title: item.title?.trim().isNotEmpty == true
          ? item.title!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : (item.summary?.trim().isNotEmpty == true
                      ? item.summary!.trim()
                      : (item.authorDisplayName?.trim().isNotEmpty == true
                            ? item.authorDisplayName!.trim()
                            : '网络结果'))),
      supportingText: item.summary?.trim().isNotEmpty == true
          ? item.summary!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : '打开相关内容'),
      coverUrl: item.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty ? '内容结果' : footerSegments.join(' · '),
      eyebrowText: item.subCategory?.trim().isNotEmpty == true
          ? item.subCategory!.trim()
          : '网络结果',
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
        hit.asCircleCircleItem ??
        CircleSearchItemView.fromMap(hit.payload.toWireMap());
    final circleId = isCircle
        ? hit.objectId
        : (view.circleId.isNotEmpty ? view.circleId : hit.objectId);
    final memberCount = view.memberCount;
    final postCount = view.postCount;
    final circleNameLabel = view.circleName?.trim() ?? '';
    final footerSegments = <String>[
      if (circleNameLabel.isNotEmpty) circleNameLabel,
      if (memberCount > 0) '$memberCount 人',
      if (postCount > 0) '$postCount 篇内容',
      if (hit.resolvedFrom == SearchResolvedFrom.localFallback) '本地回退',
    ];
    return _GroupResultCardModel(
      circleId: circleId,
      title: hit.title,
      supportingText: hit.snippet?.trim().isNotEmpty == true
          ? hit.snippet!.trim()
          : (hit.subtitle?.trim().isNotEmpty == true
                ? hit.subtitle!.trim()
                : '打开相关圈子'),
      coverUrl: view.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty ? '讨论结果' : footerSegments.join(' · '),
      eyebrowText: isCircle ? '圈子' : '讨论',
    );
  }
}
