// ignore_for_file: unnecessary_non_null_assertion
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorAction, ReferralSource;
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_layout_policy.dart';
import 'package:quwoquan_app/ui/discovery/providers/channel_intersection_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';
import 'package:quwoquan_app/ui/discovery/widgets/dual_column_discovery_post_card.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';
import 'package:quwoquan_app/ui/discovery/widgets/intersection_spotlight_module.dart';

const double _feedCardVerticalPadding = AppSpacing.fourteen;
const double _feedCardSectionGap = AppSpacing.interGroupSm;
const double _feedToolbarIconSize = AppSpacing.twenty;
const double _feedMediaGap = AppSpacing.xs;
const ArticleDistributionProfileConfig _followingArticleDistributionProfile =
    ArticleDistributionProfileConfig(
      id: 'follow_list_with_optional_cover',
      surface: 'following_feed',
      layout: 'cover_leading_title_summary',
      coverMode: 'optional_cover',
      summaryLineLimit: 2,
    );

/// 首页多形态信息流：按频道 layout policy 渲染单列关系流、双列发现流与交集模块。
///
/// `moment` 仅作为内容 identity / feed query 枚举保留；首页架构不再以 Moment 命名。
class HomeMultiFormFeed extends ConsumerWidget {
  const HomeMultiFormFeed({
    super.key,
    required this.isDark,
    required this.onUserTap,
    this.channelId = 'moment',
    this.template = '',
    this.inlineImageCarousel = false,
    this.disableImageViewerOnTap = false,
    this.onPostTap,
    this.onMoreTap,
    this.onIntersectionObjectOpen,
  });

  final bool isDark;
  final String channelId;

  /// 频道模板（来自 homeChannels.template；旧字段，仅作为 layout policy 缺省兼容）。
  final String template;
  final bool inlineImageCarousel;
  final bool disableImageViewerOnTap;
  final void Function(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  })
  onUserTap;

  /// 点击图片/视频时打开侵入式浏览器；若仅需埋点可传 (post, i) => _trackBehavior('click', post)
  final void Function(
    PostBaseDto post,
    int index, {
    List<PostBaseDto>? feedPosts,
  })?
  onPostTap;
  final void Function(PostBaseDto post)? onMoreTap;

  /// 发现交集对象卡卡体点击：跳转对应对象/聚合页（路由由宿主按 metadata 解析）。
  final void Function(IntersectionReason reason)? onIntersectionObjectOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(postInteractionStateProvider);
    // 交集曝光归因：频道交集就绪即上报曝光（驱动推荐冷却窗口）+ 漏斗 impression。
    ref.listen<AsyncValue<List<IntersectionReason>>>(
      channelIntersectionReasonsProvider(channelId),
      (previous, next) => _reportIntersectionExposure(ref, previous, next),
    );
    final feedAsync = ref.watch(discoveryFeedProvider(channelId));
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final articleDistributionEnabled = ref.watch(
      contentFeatureFlagProvider('enable_article_distribution_profiles'),
    );
    final embeddedCatalog = ref
        .watch(contentRepositoryProvider)
        .usesEmbeddedContentCatalog;
    final shouldShowFollowingArticles =
        channelId == 'following' &&
        articleDistributionEnabled &&
        embeddedCatalog;

    if (!feedMap.containsKey(channelId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(channelId);
      });
    }

    final dtos = feedAsync.value?.items ?? const <PostBaseDto>[];
    final moments = dtos
        .where((post) => post.identity == 'moment')
        .toList(growable: false);
    final articleFallback = shouldShowFollowingArticles
        ? ref
              .read(contentRepositoryProvider)
              .embeddedDiscoveryArticlePostsForFollowingMix()
        : const <PostBaseDto>[];
    final articlesById = <String, PostBaseDto>{
      for (final article in articleFallback) article.id: article,
      for (final article in dtos.where((post) => post.isArticleLike))
        article.id: article,
    };
    final articles = articlesById.values.toList(growable: false);
    final feedPosts = shouldShowFollowingArticles
        ? <PostBaseDto>[...moments, ...articles]
        : dtos;
    final blockingError = feedAsync.value?.blockingError;
    final appendError = feedAsync.value?.appendError;
    final staleDataError = feedAsync.value?.staleDataError;
    final hasBlockingError = blockingError != null;

    if (feedAsync.isLoading && feedPosts.isEmpty && !hasBlockingError) {
      return const Center(child: CupertinoActivityIndicator());
    }

    if (hasBlockingError && feedPosts.isEmpty) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: blockingError,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await ref
                .read(discoveryFeedMapProvider.notifier)
                .load(channelId, force: true);
          }
        },
      );
    }

    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final listDividerColor =
        SettingsSemanticConstants.conversationSheetDividerColor(
          isDark,
        ).withValues(alpha: 0.9);
    final channelConfig = _resolveChannelConfig();
    final layoutPolicy = HomeFeedLayoutPolicy.fromChannel(
      channelConfig,
      fallbackTemplate: template,
    );
    final imageForward = layoutPolicy.usesCompactDiscoveryCards;
    final effectiveInlineCarousel =
        inlineImageCarousel ||
        layoutPolicy.contentCardPolicy == 'compactVisual';
    final effectiveDisableViewerOnTap = disableImageViewerOnTap || imageForward;
    final columns = layoutPolicy.columnsFor(context);
    final isMultiColumn = columns > 1;
    final horizontalPad = isMultiColumn
        ? AppSpacing.feedContentHorizontal(context)
        : AppSpacing.zero;

    Widget buildCard(PostBaseDto dto, int index) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(contentBehaviorTrackerProvider)
            .trackImpression(
              dto.id,
              contentType: dto.identity,
              position: index,
              referralSource: ReferralSource.organicFeed,
            );
      });
      if (dto.isArticleLike && shouldShowFollowingArticles) {
        return _FollowingArticleCard(
          item: dto,
          isDark: isDark,
          summaryLineLimit:
              _followingArticleDistributionProfile.summaryLineLimit,
          sourceCircleName: _resolveSourceCircleName(ref, dto.id),
          onTap: () {
            final feedReqId = ref
                .read(feedSessionProvider.notifier)
                .newFeedRequestId();
            ref
                .read(contentBehaviorTrackerProvider)
                .trackClick(
                  dto.id,
                  contentType: dto.identity,
                  feedRequestId: feedReqId,
                  position: index,
                  referralSource: ReferralSource.organicFeed,
                );
            onPostTap?.call(dto, 0, feedPosts: feedPosts);
          },
          onMoreTap: () {
            if (onMoreTap != null) {
              onMoreTap!(dto);
            } else {
              _showMoreActions(context, ref, dto);
            }
          },
        );
      }
      if (layoutPolicy.usesCompactDiscoveryCards &&
          !layoutPolicy.shouldRenderFullSpan(dto)) {
        return DualColumnDiscoveryPostCard(
          key: ValueKey<String>('dual-discovery-card-$index'),
          item: dto,
          isDark: isDark,
          isLiked: effectivePostLiked(ref, dto.id),
          likeCount: effectivePostLikeCount(
            ref,
            dto.id,
            fallback: dto.likeCount,
          ),
          onTap: () {
            final feedReqId = ref
                .read(feedSessionProvider.notifier)
                .newFeedRequestId();
            ref
                .read(contentBehaviorTrackerProvider)
                .trackClick(
                  dto.id,
                  contentType: dto.identity,
                  feedRequestId: feedReqId,
                  position: index,
                  referralSource: ReferralSource.organicFeed,
                );
            onPostTap?.call(dto, 0, feedPosts: feedPosts);
          },
          onUserTap: () => onUserTap(
            dto.authorId,
            avatarUrl: dto.avatarUrl,
            displayName: dto.displayName,
            backgroundUrl: dto.authorBackgroundUrl,
          ),
          onLikeTap: () {
            runWhenLoggedIn(ref, context, AuthGateReason.like, () {
              final wasLiked = effectivePostLiked(ref, dto.id);
              final currentLikeCount = effectivePostLikeCount(
                ref,
                dto.id,
                fallback: dto.likeCount,
              );
              final nextLikeCount = wasLiked
                  ? (currentLikeCount - 1).clamp(0, 1 << 31).toInt()
                  : currentLikeCount + 1;
              syncPostLikeIntent(
                ref,
                postId: dto.id,
                isLiked: !wasLiked,
                likeCount: nextLikeCount,
              );
            });
          },
        );
      }
      return _HomeRelationPostCard(
        cardContainerKey: ValueKey<String>('home-feed-card-$index'),
        moreButtonKey: ValueKey<String>('home-feed-more-$index'),
        wideLayout: isMultiColumn,
        item: dto,
        isDark: isDark,
        isLiked: effectivePostLiked(ref, dto.id),
        likeCount: effectivePostLikeCount(ref, dto.id, fallback: dto.likeCount),
        sourceCircleName: _resolveSourceCircleName(ref, dto.id),
        inlineImageCarousel: effectiveInlineCarousel,
        onUserTap: (id) => onUserTap(
          id,
          avatarUrl: dto.avatarUrl,
          displayName: dto.displayName,
          backgroundUrl: dto.authorBackgroundUrl,
        ),
        onImageTap: (imgIndex) {
          final feedReqId = ref
              .read(feedSessionProvider.notifier)
              .newFeedRequestId();
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                dto.id,
                contentType: dto.identity,
                feedRequestId: feedReqId,
                position: index,
                referralSource: ReferralSource.organicFeed,
              );
          if (!(effectiveDisableViewerOnTap && dto.hasImages)) {
            onPostTap?.call(dto, imgIndex, feedPosts: feedPosts);
          }
        },
        onCommentTap: () {
          CommentViewer.showModal(context: context, postId: dto.id);
        },
        onShareTap: () => _showShare(
          context,
          ref,
          dto,
          enableIdentityTemplate: ref.read(
            contentFeatureFlagProvider('enable_identity_share_template'),
          ),
        ),
        onLikeTap: () {
          runWhenLoggedIn(ref, context, AuthGateReason.like, () {
            final wasLiked = effectivePostLiked(ref, dto.id);
            final currentLikeCount = effectivePostLikeCount(
              ref,
              dto.id,
              fallback: dto.likeCount,
            );
            final nextLikeCount = wasLiked
                ? (currentLikeCount - 1).clamp(0, 1 << 31).toInt()
                : currentLikeCount + 1;
            syncPostLikeIntent(
              ref,
              postId: dto.id,
              isLiked: !wasLiked,
              likeCount: nextLikeCount,
            );
          });
        },
        onMoreTap: () {
          if (onMoreTap != null) {
            onMoreTap!(dto);
          } else {
            _showMoreActions(context, ref, dto);
          }
        },
      );
    }

    final bottomPad =
        MediaQuery.of(context).padding.bottom + AppSpacing.bottomNavHeight;

    final todayReasons = layoutPolicy.hasIntersectionSpotlight
        ? (ref.watch(channelIntersectionReasonsProvider(channelId)).value ??
              const <IntersectionReason>[])
        : const <IntersectionReason>[];
    final shouldShowFollowingSubjects =
        channelId == 'following' && layoutPolicy.isSingleColumnRelations;
    final Widget? headerSliver = shouldShowFollowingSubjects
        ? FollowingSubjectStrip(isDark: isDark)
        : todayReasons.isEmpty
        ? null
        : IntersectionSpotlightModule(
            reasons: todayReasons,
            isDark: isDark,
            title: _intersectionSpotlightTitle(),
            onReasonTap: onIntersectionObjectOpen,
          );

    final topPad = isMultiColumn ? AppSpacing.sm : AppSpacing.zero;
    return _HomeFeedScrollView(
      pageBackground: pageBackground,
      isDark: isDark,
      isMultiColumn: isMultiColumn,
      columns: columns,
      horizontalPad: horizontalPad,
      topPad: topPad,
      bottomPad: isMultiColumn ? bottomPad + AppSpacing.sm : bottomPad,
      itemCount: feedPosts.length,
      itemBuilder: (index) => buildCard(feedPosts[index], index),
      isFullSpanItem: (index) =>
          layoutPolicy.shouldRenderFullSpan(feedPosts[index]),
      fullSpanBuilder: (index) => buildCard(feedPosts[index], index),
      segmentBuilder:
          layoutPolicy.insertsSegmentCards && todayReasons.isNotEmpty
          ? (segmentIndex) => IntersectionSpotlightModule(
              reasons: todayReasons
                  .skip(segmentIndex + 1)
                  .toList(growable: false),
              isDark: isDark,
              title: _intersectionSpotlightTitle(),
              onReasonTap: onIntersectionObjectOpen,
            )
          : null,
      dividerColor: listDividerColor,
      isLoadingMore: feedAsync.value?.isLoading ?? false,
      hasMore: feedAsync.value?.nextCursor?.isNotEmpty ?? false,
      appendError: appendError,
      staleDataError: staleDataError,
      onRetryInitialLoad: () => ref
          .read(discoveryFeedMapProvider.notifier)
          .load(channelId, force: true),
      moodCopy: _resolveChannelMoodCopy(),
      headerSliver: headerSliver,
      onReachBottom: () =>
          ref.read(discoveryFeedMapProvider.notifier).appendNextPage(channelId),
    );
  }

  /// 交集曝光上报：频道交集 Provider 首次产出非空数据时，
  /// 上报曝光给推荐冷却窗口（reportExposure）并补漏斗 impression（带 intersectionId/dimension/class）。
  /// trackImpression 按 objectId session 去重，故重复 build 不会重复上报。
  void _reportIntersectionExposure(
    WidgetRef ref,
    AsyncValue<List<IntersectionReason>>? previous,
    AsyncValue<List<IntersectionReason>> next,
  ) {
    final reasons = next.value;
    if (reasons == null || reasons.isEmpty) return;
    if (previous?.value != null && previous!.value!.isNotEmpty) return;
    final exposed = reasons
        .where((reason) => reason.actionTargetId.trim().isNotEmpty)
        .take(4)
        .toList(growable: false);
    if (exposed.isEmpty) return;
    final objectIds = exposed
        .map((reason) => reason.actionTargetId.trim())
        .toList(growable: false);
    unawaited(
      ref
          .read(intersectionRepositoryProvider)
          .reportExposure(objectIds: objectIds),
    );
    final tracker = ref.read(contentBehaviorTrackerProvider);
    for (final reason in exposed) {
      if (reason.intersectionId.isEmpty) continue;
      tracker.trackImpression(
        reason.actionTargetId.trim(),
        referralSource: ReferralSource.organicFeed,
        intersectionId: reason.intersectionId,
        intersectionDimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
      );
    }
  }

  String _intersectionSpotlightTitle() {
    switch (channelId) {
      case 'campus':
        return UITextConstants.intersectionCampusSpotlightTitle;
      case 'travel':
        return UITextConstants.intersectionTravelSpotlightTitle;
      default:
        return UITextConstants.intersectionRecommendSpotlightTitle;
    }
  }

  /// 从当前 feed 各帖聚合去重的交集理由，供首页 full-span 交集模块消费。
  /// 不引入第二套业务列表（数据来自已加载的 feed item），无来源时返回空。
  /// 频道气质文案：按 channelId 匹配运营下发的 [ContentUIConfig.homeChannels]
  /// 解析 moodCopyKey（真相源 = ui_config home_channels）；无匹配返回空串。
  String _resolveChannelMoodCopy() {
    for (final channel in ContentUIConfig.homeChannels) {
      if (channel.id == channelId) {
        return UITextConstants.homeChannelMoodCopy(channel.moodCopyKey);
      }
    }
    return '';
  }

  HomeChannelConfig? _resolveChannelConfig() {
    for (final channel in ContentUIConfig.homeChannels) {
      if (channel.id == channelId) {
        return channel;
      }
    }
    return null;
  }

  void _showShare(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.shareRecord, () {
      final template = _buildShareTemplate(
        ref: ref,
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      );
      ContentShareSheet.show(
        context,
        template: template,
        onActionCompleted: (result) async {
          await _recordShare(ref, post.id, result.actionId);
        },
      );
    });
  }

  void _showMoreActions(BuildContext context, WidgetRef ref, PostBaseDto post) {
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
        showShareAction: false,
        showViewOriginalAction: false,
        onCopyLink: () => _copyLink(
          context,
          ref,
          post,
          enableIdentityTemplate: ref.read(
            contentFeatureFlagProvider('enable_identity_share_template'),
          ),
        ),
        onShare: () => _showShare(
          context,
          ref,
          post,
          enableIdentityTemplate: ref.read(
            contentFeatureFlagProvider('enable_identity_share_template'),
          ),
        ),
        onNotInterested: () {
          ref.read(contentBehaviorTrackerProvider).trackDislike(post.id);
        },
        onBlockUser: () {
          ref.read(blockRepositoryProvider).blockUser(post.authorId);
        },
        onBlockWords: () async {
          final keyword = _extractKeyword(post.normalizedBody);
          if (keyword.isEmpty) return;
          await ref
              .read(keywordBlockRepositoryProvider)
              .addBlockedKeyword(keyword);
        },
        onReport: () {
          runWhenLoggedIn(ref, context, AuthGateReason.report, () {
            ref
                .read(behaviorRepositoryProvider)
                .reportSingle(
                  contentId: post.id,
                  action: BehaviorAction.report,
                );
            ref
                .read(reportRepositoryProvider)
                .createReport(
                  targetId: post.id,
                  targetType: 'post',
                  reason: 'inappropriate',
                );
          });
        },
      ),
    );
  }

  Future<void> _copyLink(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _buildShareTemplate(
        ref: ref,
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      const ContentShareAction(
        id: 'copy_link',
        label: UITextConstants.copyLink,
      ),
    );
    if (result.success) {
      await _recordShare(ref, post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required WidgetRef ref,
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final wire = _rawDiscoveryItem(ref, post.id);
    final circleName = wire?.circleName ?? '';
    final surfaceView = ContentSurfaceViewMapper.fromDto(
      post,
      wire: wire?.toWireMap(),
    );
    return ContentShareTemplateBuilder.build(
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: wire?.visibility ?? 'public',
      circleNames: circleName.isEmpty ? const <String>[] : <String>[circleName],
    );
  }

  Future<void> _recordShare(
    WidgetRef ref,
    String postId,
    String actionId,
  ) async {
    final raw = _rawDiscoveryItem(ref, postId)?.toWireMap();
    final rawShareCount = (raw?['shareCount'] as num?)?.toInt() ?? 0;
    final baselineShareCount = effectivePostShareCount(
      ref,
      postId,
      fallback: rawShareCount,
    );
    await syncPostShareIntent(
      ref,
      postId: postId,
      baselineShareCount: baselineShareCount,
    );
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }

  String _resolveSourceCircleName(WidgetRef ref, String postId) {
    return _rawDiscoveryItem(ref, postId)?.circleName ?? '';
  }

  DiscoveryPresentationWire? _rawDiscoveryItem(WidgetRef ref, String postId) {
    return ref
        .read(contentRepositoryProvider)
        .discoveryPresentationWireForPost(postId);
  }

  String _extractKeyword(String text) {
    final tokens = text
        .split(RegExp(r'[^\\u4e00-\\u9fa5A-Za-z0-9_]+'))
        .map((e) => e.trim())
        .where((e) => e.length >= 2)
        .toList();
    return tokens.isEmpty ? '' : tokens.first;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Feed 容器：CustomScrollView + 分段瀑布(多列) / SliverList(单列) + 触底分页
// ─────────────────────────────────────────────────────────────────────────────

/// 多列瀑布每段卡数：段尾由 sliver 边界天然两列齐平，段间可插入交集模块。
const int _kFeedSegmentSize = 10;

class _HomeFeedScrollView extends StatefulWidget {
  const _HomeFeedScrollView({
    required this.pageBackground,
    required this.isDark,
    required this.isMultiColumn,
    required this.columns,
    required this.horizontalPad,
    required this.topPad,
    required this.bottomPad,
    required this.itemCount,
    required this.itemBuilder,
    required this.isFullSpanItem,
    required this.fullSpanBuilder,
    required this.dividerColor,
    required this.isLoadingMore,
    required this.hasMore,
    required this.appendError,
    required this.staleDataError,
    required this.onRetryInitialLoad,
    required this.onReachBottom,
    this.moodCopy = '',
    this.headerSliver,
    this.segmentBuilder,
  });

  final Color pageBackground;
  final bool isDark;
  final bool isMultiColumn;
  final int columns;
  final double horizontalPad;
  final double topPad;
  final double bottomPad;
  final int itemCount;
  final Widget Function(int index) itemBuilder;
  final bool Function(int index) isFullSpanItem;
  final Widget Function(int index) fullSpanBuilder;
  final Color dividerColor;
  final bool isLoadingMore;
  final bool hasMore;
  final Object? appendError;
  final Object? staleDataError;
  final VoidCallback onRetryInitialLoad;
  final VoidCallback onReachBottom;

  /// 频道气质文案（来自 ContentUIConfig.homeChannels.moodCopyKey 解析，只读）；空则不展示。
  final String moodCopy;

  /// 顶部 sliver（发现交集横滑流）；null 不展示。
  final Widget? headerSliver;

  /// 多列段间插卡（交集 spotlight / 运营解释模块）；null 不展示。
  final Widget Function(int segmentIndex)? segmentBuilder;

  @override
  State<_HomeFeedScrollView> createState() => _HomeFeedScrollViewState();
}

class _HomeFeedScrollViewState extends State<_HomeFeedScrollView> {
  final ScrollController _controller = ScrollController();
  Timer? _staleNoticeTimer;
  Object? _visibleStaleDataError;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onScroll);
    _syncStaleNotice(previous: null);
  }

  @override
  void didUpdateWidget(covariant _HomeFeedScrollView oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncStaleNotice(previous: oldWidget.staleDataError);
  }

  @override
  void dispose() {
    _staleNoticeTimer?.cancel();
    _controller.removeListener(_onScroll);
    _controller.dispose();
    super.dispose();
  }

  void _syncStaleNotice({required Object? previous}) {
    final next = widget.staleDataError;
    if (next == null || identical(next, previous)) {
      return;
    }
    _staleNoticeTimer?.cancel();
    _visibleStaleDataError = next;
    _staleNoticeTimer = Timer(const Duration(milliseconds: 2200), () {
      if (!mounted) return;
      setState(() => _visibleStaleDataError = null);
    });
  }

  void _onScroll() {
    if (_visibleStaleDataError != null) {
      setState(() => _visibleStaleDataError = null);
    }
    if (!widget.hasMore || widget.isLoadingMore) return;
    if (!_controller.hasClients) return;
    final position = _controller.position;
    // 剩余不足半屏即预取下一页（比例系数，非像素间距）。
    if (position.extentAfter < position.viewportDimension * 0.5) {
      widget.onReachBottom();
    }
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: widget.pageBackground,
      child: CustomScrollView(
        controller: _controller,
        slivers: _buildSlivers(),
      ),
    );
  }

  List<Widget> _buildSlivers() {
    final slivers = <Widget>[];
    if (widget.headerSliver != null) {
      slivers.add(SliverToBoxAdapter(child: widget.headerSliver!));
    }
    if (widget.topPad > 0) {
      slivers.add(SliverToBoxAdapter(child: SizedBox(height: widget.topPad)));
    }
    final visibleStaleDataError = _visibleStaleDataError;
    if (visibleStaleDataError != null) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              widget.horizontalPad,
              0,
              widget.horizontalPad,
              AppSpacing.containerSm,
            ),
            child: AppTransientErrorNotice(
              semantic: runtimeErrorSemantic(
                context,
                error: visibleStaleDataError,
                category: UiErrorCategory.backgroundAction,
                scope: UiErrorScope.section,
                allowRetry: false,
                presentation: UiErrorPresentation.transientNotice,
              ),
              margin: EdgeInsets.zero,
            ),
          ),
        ),
      );
    }

    if (widget.isMultiColumn) {
      var start = 0;
      var segmentIndex = 0;
      while (start < widget.itemCount) {
        if (widget.isFullSpanItem(start)) {
          slivers.add(
            SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
                child: widget.fullSpanBuilder(start),
              ),
            ),
          );
          start += 1;
          continue;
        }

        var end = (start + _kFeedSegmentSize).clamp(0, widget.itemCount);
        for (var i = start + 1; i < end; i++) {
          if (widget.isFullSpanItem(i)) {
            end = i;
            break;
          }
        }
        final segStart = start;
        final segCount = end - segStart;
        if (segCount > 0) {
          slivers.add(
            SliverPadding(
              padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
              sliver: SliverMasonryGrid.count(
                crossAxisCount: widget.columns,
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                childCount: segCount,
                itemBuilder: (context, i) => widget.itemBuilder(segStart + i),
              ),
            ),
          );
        }
        start = end;
        final segment = widget.segmentBuilder?.call(segmentIndex);
        if (segment != null && start < widget.itemCount) {
          slivers.add(SliverToBoxAdapter(child: segment));
        }
        segmentIndex += 1;
        // 段间过渡留白：分段瀑布天然收齐后再进入下一组。
        if (start < widget.itemCount) {
          slivers.add(
            SliverToBoxAdapter(
              child: SizedBox(height: AppSpacing.interGroupMd),
            ),
          );
        }
      }
    } else {
      slivers.add(
        SliverList(
          delegate: SliverChildBuilderDelegate((context, index) {
            if (index.isOdd) {
              final dividerIndex = index ~/ 2;
              return Divider(
                key: ValueKey<String>('home-feed-divider-$dividerIndex'),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: widget.dividerColor,
              );
            }
            return widget.itemBuilder(index ~/ 2);
          }, childCount: widget.itemCount == 0 ? 0 : widget.itemCount * 2 - 1),
        ),
      );
    }

    slivers.add(
      SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.only(
            top: widget.isLoadingMore || widget.appendError != null
                ? AppSpacing.interGroupMd
                : AppSpacing.zero,
            bottom: widget.bottomPad,
          ),
          child: widget.isLoadingMore || widget.appendError != null
              ? _LoadMoreFooter(
                  moodCopy: widget.moodCopy,
                  isDark: widget.isDark,
                  appendError: widget.appendError,
                  onRetry: widget.onReachBottom,
                )
              : const SizedBox.shrink(),
        ),
      ),
    );
    return slivers;
  }
}

/// 触底加载 footer：加载指示 + 频道气质文案（只读，空文案不展示）。
class _LoadMoreFooter extends StatelessWidget {
  const _LoadMoreFooter({
    required this.moodCopy,
    required this.isDark,
    required this.appendError,
    required this.onRetry,
  });

  final String moodCopy;
  final bool isDark;
  final Object? appendError;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final hasError = appendError != null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (hasError)
          AppListAppendErrorFooter(
            semantic: runtimeErrorSemantic(
              context,
              error: appendError!,
              category: UiErrorCategory.listAppend,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.appendFooter,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                onRetry();
              }
            },
          )
        else
          const CupertinoActivityIndicator(),
        if (!hasError && moodCopy.isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            moodCopy,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: muted,
              letterSpacing: -0.04,
            ),
          ),
        ],
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 首页关系流卡片（社交图文风格）
// ─────────────────────────────────────────────────────────────────────────────

class _HomeRelationPostCard extends ConsumerStatefulWidget {
  const _HomeRelationPostCard({
    required this.cardContainerKey,
    required this.moreButtonKey,
    required this.wideLayout,
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.sourceCircleName,
    required this.inlineImageCarousel,
    required this.onUserTap,
    required this.onImageTap,
    required this.onCommentTap,
    required this.onShareTap,
    required this.onLikeTap,
    required this.onMoreTap,
  });

  final Key cardContainerKey;
  final Key moreButtonKey;
  final bool wideLayout;
  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final String sourceCircleName;
  final bool inlineImageCarousel;
  final void Function(String) onUserTap;
  final void Function(int imageIndex) onImageTap;
  final VoidCallback onCommentTap;
  final VoidCallback onShareTap;
  final VoidCallback onLikeTap;
  final VoidCallback onMoreTap;

  @override
  ConsumerState<_HomeRelationPostCard> createState() =>
      _HomeRelationPostCardState();
}

class _HomeRelationPostCardState extends ConsumerState<_HomeRelationPostCard>
    with SingleTickerProviderStateMixin {
  static const int _maxLines = 5;

  bool _isExpanded = false;
  late AnimationController _likeCtrl;

  @override
  void initState() {
    super.initState();
    _likeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
  }

  @override
  void dispose() {
    _likeCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final isDark = widget.isDark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final cardBg = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final cardBorder = widget.wideLayout
        ? SettingsSemanticConstants.conversationSheetCardBorderColor(isDark)
        : AppColors.transparent;
    final borderRadius = widget.wideLayout
        ? BorderRadius.circular(AppSpacing.contentPreviewCornerRadius)
        : BorderRadius.zero;

    return DecoratedBox(
      key: widget.cardContainerKey,
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: borderRadius,
        border: Border.all(color: cardBorder, width: AppSpacing.hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          _feedCardVerticalPadding,
          AppSpacing.containerMd,
          _feedCardVerticalPadding,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => widget.onUserTap(item.authorId),
                  child: RoundedSquareAvatar(
                    size: AppSpacing.avatarUserSm,
                    imageUrl: item.avatarUrl,
                    name: item.displayName,
                    borderRadius: AppSpacing.avatarUserSm / 2,
                    backgroundColor: AppColors.iosSecondaryFill(context),
                    fallbackIcon: CupertinoIcons.person_crop_circle_fill,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupMd),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Expanded(
                            child: Text(
                              item.displayName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize:
                                    AppTypography.feedAuthorNameResponsive(
                                      context,
                                    ),
                                fontWeight: AppTypography.medium,
                                color: fg,
                                letterSpacing: -0.08,
                                height: AppSpacing.textLineHeightDense,
                              ),
                            ),
                          ),
                          SizedBox(width: AppSpacing.intraGroupXs),
                          _HomeFeedMoreButton(
                            key: widget.moreButtonKey,
                            isDark: isDark,
                            color: muted,
                            onPressed: widget.onMoreTap,
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.two),
                      Text(
                        _buildMetaLine(context),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          color: muted,
                          letterSpacing: -0.04,
                          height: AppSpacing.one,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),

            // 交集理由位（一行 displayText，只读；无来源不展示）
            if (_intersectionReasonText != null) ...[
              const SizedBox(height: _feedCardSectionGap),
              IntersectionReasonChip(
                text: _intersectionReasonText!,
                isDark: isDark,
              ),
            ],

            // 正文（5 行截断 + 就地展开）
            if (item.normalizedBody.isNotEmpty) ...[
              const SizedBox(height: _feedCardSectionGap),
              _ExpandableText(
                text: item.normalizedBody,
                maxLines: _maxLines,
                isDark: isDark,
                expanded: _isExpanded,
                onToggle: () => setState(() => _isExpanded = !_isExpanded),
              ),
            ],

            // 图片区域（自适应宫格）
            if (item.hasImages) ...[
              const SizedBox(height: _feedCardSectionGap),
              widget.inlineImageCarousel
                  ? _HomeFeedImageCarousel(
                      urls: item.imageUrls,
                      isDark: isDark,
                      onTap: widget.onImageTap,
                    )
                  : _HomeFeedImageGrid(
                      urls: item.imageUrls,
                      isDark: isDark,
                      onTap: widget.onImageTap,
                    ),
            ],

            // 视频卡片
            if (item.hasVideo && !item.hasImages) ...[
              const SizedBox(height: _feedCardSectionGap),
              _HomeFeedVideoCard(
                dto: item,
                isDark: isDark,
                onTap: () => widget.onImageTap(0),
              ),
            ],

            // 互动栏
            const SizedBox(height: _feedCardSectionGap),
            _ActionRow(
              item: item,
              isDark: isDark,
              isLiked: widget.isLiked,
              likeCount: widget.likeCount,
              likeCtrl: _likeCtrl,
              onLike: () {
                HapticFeedback.lightImpact();
                _likeCtrl.forward(from: 0);
                widget.onLikeTap();
              },
              onComment: widget.onCommentTap,
              onShare: widget.onShareTap,
            ),
          ],
        ),
      ),
    );
  }

  /// 交集理由首条 displayText（只读）；无来源/空文案返回 null → 不展示。
  /// 口径真相源 = [IntersectionReasonChip.primaryText]，与沉浸/转发/详情同源。
  String? get _intersectionReasonText =>
      IntersectionReasonChip.primaryText(widget.item.intersectionReasons);

  String _buildMetaLine(BuildContext context) {
    final time = _timeAgo(context, widget.item.createdAt);
    if (widget.sourceCircleName.isEmpty) return time;
    return '$time · ${UITextConstants.sourceFromPrefix}${widget.sourceCircleName}';
  }

  static String _timeAgo(BuildContext context, DateTime t) {
    final l10n = Localizations.of<AppLocalizations>(context, AppLocalizations);
    final delta = DateTime.now().difference(t).inHours;
    if (delta < 1) return l10n?.justNow ?? '刚刚';
    if (delta < 24) return l10n?.hoursAgoTemplate(delta) ?? '$delta 小时前';
    return l10n?.monthDayTemplate(t.month, t.day) ?? '${t.month}/${t.day}';
  }
}

class _FollowingArticleCard extends StatelessWidget {
  const _FollowingArticleCard({
    required this.item,
    required this.isDark,
    required this.summaryLineLimit,
    required this.sourceCircleName,
    required this.onTap,
    required this.onMoreTap,
  });

  final PostBaseDto item;
  final bool isDark;
  final int summaryLineLimit;
  final String sourceCircleName;
  final VoidCallback onTap;
  final VoidCallback onMoreTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final eyebrowSegments = <String>[
      '文章',
      _articleTemplateLabel,
      if (sourceCircleName.isNotEmpty) sourceCircleName,
    ];

    return PostPreviewListTile(
      key: ValueKey<String>('following-article-card-${item.id}'),
      isDark: isDark,
      eyebrowText: eyebrowSegments.join(' · '),
      eyebrowColor: AppColors.primaryColor,
      title: _headlineText,
      supportingText: _supportingText,
      supportingTextMaxLines: summaryLineLimit,
      coverUrl: item.mediaCoverUrl,
      hideThumbnailWhenNoCover: true,
      thumbnailKey: item.mediaCoverUrl.isNotEmpty
          ? ValueKey<String>('following-article-thumbnail-${item.id}')
          : null,
      onTap: onTap,
      footer: Row(
        children: [
          Expanded(
            child: Text(
              item.displayName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Text(
            _HomeRelationPostCardState._timeAgo(context, item.createdAt),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: _HomeFeedMoreButton(
        isDark: isDark,
        color: fgSecondary,
        onPressed: onMoreTap,
      ),
    );
  }

  String get _articleTemplateLabel {
    final templateId = item is ArticlePostDto
        ? (item as ArticlePostDto).articleTemplate
        : '';
    switch (templateId) {
      case 'ritual':
        return '礼记';
      case 'diffuse':
        return '弥散';
      case 'journal':
        return '手帐';
      case 'tech':
        return '科技';
      default:
        return '柔和';
    }
  }

  String get _headlineText {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    if (title.isNotEmpty) return title;
    if (body.isNotEmpty) return body;
    return '文章';
  }

  String get _supportingText {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    if (title.isEmpty || body.isEmpty || title == body) {
      return '';
    }
    return body;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 可展开文字
// ─────────────────────────────────────────────────────────────────────────────

class _ExpandableText extends StatelessWidget {
  const _ExpandableText({
    required this.text,
    required this.maxLines,
    required this.isDark,
    required this.expanded,
    required this.onToggle,
  });

  final String text;
  final int maxLines;
  final bool isDark;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final textStyle = TextStyle(
      fontSize: AppTypography.feedBodyResponsive(context),
      color: fg,
      height: AppSpacing.textLineHeightBodyRelaxed,
      letterSpacing: -0.18,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final tp = TextPainter(
          text: TextSpan(text: text, style: textStyle),
          maxLines: maxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = tp.didExceedMaxLines;

        if (!isOverflow) {
          return Text(text, style: textStyle);
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: textStyle,
              maxLines: expanded ? null : maxLines,
              overflow: expanded ? null : TextOverflow.ellipsis,
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: onToggle,
              child: Text(
                expanded ? UITextConstants.collapse : UITextConstants.fullText,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 自适应图片宫格：1=全宽 4:3 / 2=双列 1:1 / 3~9=三列九宫格
// ─────────────────────────────────────────────────────────────────────────────

class _HomeFeedImageGrid extends StatelessWidget {
  const _HomeFeedImageGrid({
    required this.urls,
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;
  final bool isDark;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    if (urls.isEmpty) return const SizedBox.shrink();
    if (urls.length == 1) return _singleImage(context, urls.first, 0);
    if (urls.length == 2) return _doubleImages(context);
    return _nineGrid(context);
  }

  Widget _singleImage(BuildContext context, String url, int index) {
    return GestureDetector(
      onTap: () => onTap(index),
      child: AspectRatio(aspectRatio: 4 / 3, child: _img(url)),
    );
  }

  Widget _doubleImages(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTap: () => onTap(0),
            child: AspectRatio(aspectRatio: 1, child: _img(urls[0])),
          ),
        ),
        const SizedBox(width: _feedMediaGap),
        Expanded(
          child: GestureDetector(
            onTap: () => onTap(1),
            child: AspectRatio(aspectRatio: 1, child: _img(urls[1])),
          ),
        ),
      ],
    );
  }

  Widget _nineGrid(BuildContext context) {
    final count = urls.length.clamp(1, 9);
    final crossAxisCount = count == 4 ? 2 : 3;

    return GridView.builder(
      shrinkWrap: true,
      primary: false,
      padding: EdgeInsets.zero,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: count,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        crossAxisSpacing: _feedMediaGap,
        mainAxisSpacing: _feedMediaGap,
        childAspectRatio: 1,
      ),
      itemBuilder: (context, index) {
        return GestureDetector(
          onTap: () => onTap(index),
          child: _img(urls[index]),
        );
      },
    );
  }

  Widget _img(String url) {
    if (url.isEmpty) {
      return _placeholder();
    }
    return AppCachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      placeholder: _placeholder(),
      errorWidget: _placeholder(),
    );
  }

  Widget _placeholder() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted),
      ),
    );
  }
}

class _HomeFeedImageCarousel extends StatefulWidget {
  const _HomeFeedImageCarousel({
    required this.urls,
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;
  final bool isDark;
  final void Function(int index) onTap;

  @override
  State<_HomeFeedImageCarousel> createState() => _HomeFeedImageCarouselState();
}

class _HomeFeedImageCarouselState extends State<_HomeFeedImageCarousel> {
  late final PageController _controller;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final urls = widget.urls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
    if (urls.isEmpty) return const SizedBox.shrink();

    return AspectRatio(
      aspectRatio: 4 / 3,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.md),
        child: Stack(
          fit: StackFit.expand,
          children: [
            PageView.builder(
              controller: _controller,
              itemCount: urls.length,
              onPageChanged: (next) => setState(() => _index = next),
              itemBuilder: (context, index) {
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => widget.onTap(index),
                  child: AppCachedNetworkImage(
                    imageUrl: urls[index],
                    fit: BoxFit.cover,
                    placeholder: _placeholder(),
                    errorWidget: _placeholder(),
                  ),
                );
              },
            ),
            if (urls.length > 1)
              Positioned(
                left: 0,
                right: 0,
                bottom: AppSpacing.intraGroupSm,
                child: _CarouselDots(
                  total: urls.length,
                  activeIndex: _index,
                  isDark: widget.isDark,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _placeholder() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          widget.isDark,
          ColorType.surfaceMuted,
        ),
      ),
    );
  }
}

class _CarouselDots extends StatelessWidget {
  const _CarouselDots({
    required this.total,
    required this.activeIndex,
    required this.isDark,
  });

  final int total;
  final int activeIndex;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final visibleTotal = total.clamp(1, 7).toInt();
    final active = total <= visibleTotal
        ? activeIndex
        : ((activeIndex / (total - 1)) * (visibleTotal - 1)).round();
    final color = isDark ? AppColors.white : AppColors.black;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 0; i < visibleTotal; i++) ...[
          if (i > 0) const SizedBox(width: AppSpacing.xs),
          AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            width: i == active ? AppSpacing.containerSm : AppSpacing.xs,
            height: AppSpacing.xs,
            decoration: BoxDecoration(
              color: color.withValues(alpha: i == active ? 0.86 : 0.42),
              borderRadius: BorderRadius.circular(AppSpacing.xs),
            ),
          ),
        ],
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 视频卡片（静态封面 + 时长 + 播放标识）
// ─────────────────────────────────────────────────────────────────────────────

class _HomeFeedVideoCard extends StatelessWidget {
  const _HomeFeedVideoCard({
    required this.dto,
    required this.isDark,
    required this.onTap,
  });

  final PostBaseDto dto;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surfaceMuted = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    return GestureDetector(
      onTap: onTap,
      child: AspectRatio(
        aspectRatio: 16 / 9,
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(decoration: BoxDecoration(color: surfaceMuted)),
            // 中央播放按钮
            Center(
              child: Container(
                width: AppSpacing.videoPlayOverlaySize,
                height: AppSpacing.videoPlayOverlaySize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.overlayMedium,
                ),
                child: Icon(
                  CupertinoIcons.play_fill,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.mediaThumbnailOverlayForeground,
                  ),
                  size: AppSpacing.videoPlayOverlayIconSize,
                ),
              ),
            ),
            // 时长
            if (dto.durationMs != null)
              Positioned(
                right: AppSpacing.intraGroupMd,
                bottom: AppSpacing.intraGroupSm,
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.intraGroupSm,
                    vertical: AppSpacing.xs / 2,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.overlayStrong,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.smallBorderRadius,
                    ),
                  ),
                  child: Text(
                    _formatDuration(dto.durationMs!),
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.mediaThumbnailOverlayForeground,
                      ),
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  static String _formatDuration(int ms) {
    final s = ms ~/ 1000;
    final m = s ~/ 60;
    final sec = s % 60;
    return '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 互动操作行（赞/藏/评/分享）
// ─────────────────────────────────────────────────────────────────────────────

/// Action row for moment (微趣) posts.
/// 赞 / 转 / 评三列等宽，数字变化不挤压图标位置。
class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.likeCtrl,
    required this.onLike,
    required this.onComment,
    required this.onShare,
  });

  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final AnimationController likeCtrl;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onShare;

  @override
  Widget build(BuildContext context) {
    final actionIconColor = AppColors.feedActionIcon(context);
    final likeColor = isLiked ? AppColors.worksLike : actionIconColor;

    final likeScale = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.0,
          end: 1.25,
        ).chain(CurveTween(curve: Curves.easeOut)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.25,
          end: 1.0,
        ).chain(CurveTween(curve: Curves.easeIn)),
        weight: 50,
      ),
    ]).animate(likeCtrl);

    return Row(
      children: [
        Expanded(
          child: _chip(
            context: context,
            selected: isLiked,
            child: ScaleTransition(
              scale: likeScale,
              child: AppMediaHeartIcon(
                size: _feedToolbarIconSize,
                color: likeColor,
                filled: isLiked,
              ),
            ),
            label: formatCompactActionCount(likeCount),
            muted: actionIconColor,
            onTap: onLike,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            child: AppMediaShareIcon(
              size: _feedToolbarIconSize,
              color: actionIconColor,
            ),
            label: formatCompactActionCount(item.shareCount),
            muted: actionIconColor,
            onTap: onShare,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            child: AppMediaCommentIcon(
              size: _feedToolbarIconSize,
              color: actionIconColor,
            ),
            label: formatCompactActionCount(item.commentCount),
            muted: actionIconColor,
            onTap: onComment,
          ),
        ),
      ],
    );
  }

  Widget _chip({
    required BuildContext context,
    required Widget child,
    required String label,
    required Color muted,
    required VoidCallback onTap,
    bool selected = false,
  }) {
    final foreground = selected ? AppColors.worksLike : muted;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        height: AppSpacing.buttonHeightMdCompact,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            child,
            SizedBox(width: AppSpacing.intraGroupXs),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.fade,
              softWrap: false,
              style: TextStyle(
                fontSize: AppTypography.feedActionCountResponsive(context),
                color: foreground,
                fontWeight: AppTypography.regular,
                height: AppSpacing.one,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HomeFeedMoreButton extends StatelessWidget {
  const _HomeFeedMoreButton({
    super.key,
    required this.isDark,
    required this.color,
    required this.onPressed,
  });

  final bool isDark;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onPressed,
      child: SizedBox(
        width: AppSpacing.iconMedium,
        height: AppSpacing.iconMedium,
        child: Center(
          child: Icon(
            Icons.more_horiz_rounded,
            size: AppSpacing.twenty,
            color: color.withValues(alpha: isDark ? 0.8 : 0.68),
          ),
        ),
      ),
    );
  }
}
