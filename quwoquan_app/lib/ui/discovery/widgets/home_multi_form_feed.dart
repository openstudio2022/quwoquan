// ignore_for_file: unnecessary_non_null_assertion
import 'dart:async';
import 'dart:math' show max, min;
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
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
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/media/media_aspect_ratio.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/discovery/services/discovery_share_template.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_layout_policy.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_video_autoplay_policy.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_video_focus_coordinator.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_state.dart';
import 'package:quwoquan_app/ui/discovery/providers/feed_realtime_patch_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';

part 'home_multi_form_feed_scroll.dart';
part 'home_multi_form_feed_post_cards.dart';
part 'home_multi_form_feed_states.dart';
part 'home_multi_form_feed_media.dart';
part 'home_multi_form_feed_media_grid.dart';
part 'home_multi_form_feed_actions.dart';

const double _feedCardVerticalPadding = AppSpacing.fourteen;
const double _feedCardSectionGap =
    DiscoveryFeedSpacing.homeFeedCardSectionGapCompact;
const double _feedToolbarIconSize = AppSpacing.twenty;
const double _feedMediaGap = AppSpacing.xs;
typedef _HomeFeedItemBuilder =
    Widget Function(
      int index,
      ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal,
    );
const ArticleDistributionProfileConfig _followingArticleDistributionProfile =
    ArticleDistributionProfileConfig(
      id: 'follow_list_with_optional_cover',
      surface: 'following_feed',
      layout: 'cover_leading_title_summary',
      coverMode: 'optional_cover',
      summaryLineLimit: 2,
    );

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
  });

  final bool isDark;
  final String channelId;

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

  final void Function(
    PostBaseDto post,
    int index, {
    List<PostBaseDto>? feedPosts,
  })?
  onPostTap;
  final void Function(PostBaseDto post)? onMoreTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(postInteractionStateProvider);
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
      // 任务 B · 首屏 TTI：在触发首屏加载时起算（仅 widget 层旁路采集）。
      ref
          .read(feedPerformanceObservabilityProvider)
          .markFeedRequested(channelId);
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
      // 任务 A · 加载态：用占位渐显的骨架屏代替裸 spinner，避免白屏并提示版式。
      return _HomeFeedSkeleton(isDark: isDark);
    }

    if (hasBlockingError && feedPosts.isEmpty) {
      // 任务 B · 页面级异常可观测：首屏阻断态空内容上报加载失败归因（按因去重）。
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(feedPerformanceObservabilityProvider)
            .recordFeedLoadFailed(channelId: channelId, reason: 'page_load');
      });
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

    if (feedPosts.isEmpty && !feedAsync.isLoading && !hasBlockingError) {
      // 任务 A · 空态：加载完成但无内容时给运营兜底文案 + 再试，禁止落到空白滚动视图。
      return _HomeFeedEmptyState(
        isDark: isDark,
        onRetry: () => ref
            .read(discoveryFeedMapProvider.notifier)
            .load(channelId, force: true),
      );
    }

    // 任务 B · 首屏 TTI：内容首帧落地时上报首屏可交互耗时（每 channel 一次）。
    final firstScreenItemCount = feedPosts.length;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref
          .read(feedPerformanceObservabilityProvider)
          .markFirstContentReady(channelId, itemCount: firstScreenItemCount);
    });

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
    final effectiveInlineCarousel = inlineImageCarousel;
    final effectiveDisableViewerOnTap = disableImageViewerOnTap;
    final columns = layoutPolicy.columnsFor(context);
    final isMultiColumn = columns > 1;
    final horizontalPad = isMultiColumn
        ? AppSpacing.feedContentHorizontal(context)
        : AppSpacing.zero;

    Widget buildCard(
      PostBaseDto dto,
      int index,
      ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal,
    ) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final feedSession = ref.read(feedSessionProvider.notifier);
        ref
            .read(contentBehaviorTrackerProvider)
            .trackImpression(
              dto.id,
              contentType: dto.identity,
              position: index,
              referralSource: ReferralSource.organicFeed,
              feedRequestId: feedSession.currentFeedRequestId,
              channelId: channelId,
              rankingVersion: feedSession.currentRankingVersion,
            );
      });
      if (dto.isArticleLike && shouldShowFollowingArticles) {
        return _FeedPatchVisibilityReporter(
          key: ValueKey<String>('feed-patch-reporter-$index'),
          postId: dto.id,
          child: _FollowingArticleCard(
            item: dto,
            isDark: isDark,
            summaryLineLimit:
                _followingArticleDistributionProfile.summaryLineLimit,
            sourceCircleName: _resolveSourceCircleName(ref, dto.id),
            onTap: () {
              final feedSession = ref.read(feedSessionProvider.notifier);
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackClick(
                    dto.id,
                    contentType: dto.identity,
                    feedRequestId: feedSession.currentFeedRequestId,
                    position: index,
                    referralSource: ReferralSource.organicFeed,
                    channelId: channelId,
                    rankingVersion: feedSession.currentRankingVersion,
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
          ),
        );
      }
      return _FeedPatchVisibilityReporter(
        key: ValueKey<String>('feed-patch-reporter-$index'),
        postId: dto.id,
        child: _HomeRelationPostCard(
          cardContainerKey: ValueKey<String>('home-feed-card-$index'),
          moreButtonKey: ValueKey<String>('home-feed-more-$index'),
          wideLayout: isMultiColumn,
          item: dto,
          isDark: isDark,
          isLiked: effectivePostLiked(ref, dto.id),
          likeCount: effectivePostLikeCount(
            ref,
            dto.id,
            fallback: dto.likeCount,
          ),
          shareCount: effectivePostShareCount(
            ref,
            dto.id,
            fallback: dto.shareCount,
          ),
          commentCount: effectivePostCommentCount(
            ref,
            dto.id,
            fallback: dto.commentCount,
          ),
          sourceCircleName: _resolveSourceCircleName(ref, dto.id),
          inlineImageCarousel: effectiveInlineCarousel,
          videoScrollSignal: videoScrollSignal,
          isFocused: index == 0,
          onUserTap: (id) => onUserTap(
            id,
            avatarUrl: dto.avatarUrl,
            displayName: dto.displayName,
            backgroundUrl: dto.authorBackgroundUrl,
          ),
          onImageTap: (imgIndex) {
            final feedSession = ref.read(feedSessionProvider.notifier);
            ref
                .read(contentBehaviorTrackerProvider)
                .trackClick(
                  dto.id,
                  contentType: dto.identity,
                  feedRequestId: feedSession.currentFeedRequestId,
                  position: index,
                  referralSource: ReferralSource.organicFeed,
                  channelId: channelId,
                  rankingVersion: feedSession.currentRankingVersion,
                );
            if (!(effectiveDisableViewerOnTap && dto.hasImages)) {
              onPostTap?.call(dto, imgIndex, feedPosts: feedPosts);
            }
          },
          onCommentTap: () {
            CommentViewer.showModal(
              context: context,
              postId: dto.id,
              onShareTap: () => _showShare(
                context,
                ref,
                dto,
                enableIdentityTemplate: ref.read(
                  contentFeatureFlagProvider('enable_identity_share_template'),
                ),
              ),
            );
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
              final nextLiked = !wasLiked;
              final nextLikeCount = wasLiked
                  ? (currentLikeCount - 1).clamp(0, 1 << 31).toInt()
                  : currentLikeCount + 1;
              syncPostLikeIntent(
                ref,
                postId: dto.id,
                previousLiked: wasLiked,
                isLiked: nextLiked,
                likeCount: nextLikeCount,
              );
            });
          },
          onMoreTap: (cardWidth) {
            if (onMoreTap != null) {
              onMoreTap!(dto);
            } else {
              _showMoreActions(context, ref, dto, panelMaxWidth: cardWidth);
            }
          },
        ),
      );
    }

    final bottomPad =
        MediaQuery.of(context).padding.bottom + AppSpacing.bottomNavHeight;

    final shouldShowFollowingSubjects =
        channelId == 'following' && layoutPolicy.isSingleColumnRelations;
    final Widget? headerSliver = shouldShowFollowingSubjects
        ? FollowingSubjectStrip(isDark: isDark)
        : null;

    final topPad = isMultiColumn ? AppSpacing.sm : AppSpacing.zero;
    final scrollView = _HomeFeedScrollView(
      pageBackground: pageBackground,
      isDark: isDark,
      isMultiColumn: isMultiColumn,
      columns: columns,
      horizontalPad: horizontalPad,
      topPad: topPad,
      bottomPad: isMultiColumn ? bottomPad + AppSpacing.sm : bottomPad,
      itemCount: feedPosts.length,
      itemBuilder: (index, videoScrollSignal) =>
          buildCard(feedPosts[index], index, videoScrollSignal),
      isFullSpanItem: (index) =>
          layoutPolicy.shouldRenderFullSpan(feedPosts[index]),
      fullSpanBuilder: (index, videoScrollSignal) =>
          buildCard(feedPosts[index], index, videoScrollSignal),
      segmentBuilder: null,
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

    // 顶部「有更新」轻量入口：浮于 feed 之上，不挤占版式、不打断阅读位置；
    // 仅在有实时 patch 提示时出现，点击触发用户主动刷新（force load）。
    return Stack(
      children: [
        Positioned.fill(child: scrollView),
        Positioned(
          top: topPad + AppSpacing.sm,
          left: AppSpacing.md,
          right: AppSpacing.md,
          child: Align(
            alignment: Alignment.topCenter,
            child: _FeedRealtimeUpdatePill(
              channelId: channelId,
              onRefresh: () {
                ref
                    .read(feedRealtimePatchProvider.notifier)
                    .acknowledgeRefresh(channelId);
                ref
                    .read(discoveryFeedMapProvider.notifier)
                    .load(channelId, force: true);
              },
            ),
          ),
        ),
      ],
    );
  }

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
      final template = buildDiscoveryShareTemplate(
        post: post,
        wire: _rawDiscoveryItem(ref, post.id),
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

  void _showMoreActions(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post, {
    double? panelMaxWidth,
  }) {
    MoreActionPopup.show(
      context: context,
      panelMaxWidth: panelMaxWidth,
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
          final feedSession = ref.read(feedSessionProvider.notifier);
          ref
              .read(contentBehaviorTrackerProvider)
              .trackDislike(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                feedRequestId: feedSession.currentFeedRequestId,
                referralSource: ReferralSource.organicFeed,
                channelId: channelId,
                rankingVersion: feedSession.currentRankingVersion,
              );
          // 任务 A · 负反馈即时反馈：卡片立即从信息流消失并给出降级提示。
          _dismissFeedPost(
            context,
            ref,
            post.id,
            toast: DiscoveryFeedText.feedNegativeFeedbackNotInterested,
          );
        },
        onBlockUser: () {
          final feedSession = ref.read(feedSessionProvider.notifier);
          ref.read(blockRepositoryProvider).blockUser(post.authorId);
          ref
              .read(contentBehaviorTrackerProvider)
              .trackHideAuthor(
                post.id,
                authorId: post.authorId,
                contentType: post.type,
                feedRequestId: feedSession.currentFeedRequestId,
                referralSource: ReferralSource.organicFeed,
                channelId: channelId,
                rankingVersion: feedSession.currentRankingVersion,
              );
          _dismissFeedPost(
            context,
            ref,
            post.id,
            toast: DiscoveryFeedText.feedNegativeFeedbackAuthorReduced,
          );
        },
        onBlockWords: () async {
          final keyword = _extractKeyword(post.normalizedBody);
          if (keyword.isEmpty) return;
          final feedSession = ref.read(feedSessionProvider.notifier);
          await ref
              .read(keywordBlockRepositoryProvider)
              .addBlockedKeyword(keyword);
          if (!context.mounted) return;
          ref
              .read(contentBehaviorTrackerProvider)
              .trackHideContentType(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                feedRequestId: feedSession.currentFeedRequestId,
                referralSource: ReferralSource.organicFeed,
                channelId: channelId,
                rankingVersion: feedSession.currentRankingVersion,
              );
          _dismissFeedPost(
            context,
            ref,
            post.id,
            toast: DiscoveryFeedText.feedNegativeFeedbackContentReduced,
          );
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
            // 任务 A · 举报成功后立即移除卡片，避免重复举报与停留干扰。
            _dismissFeedPost(
              context,
              ref,
              post.id,
              toast: UITextConstants.commentReportSubmitted,
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
      buildDiscoveryShareTemplate(
        post: post,
        wire: _rawDiscoveryItem(ref, post.id),
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      ContentShareAction(id: 'copy_link', label: UITextConstants.copyLink),
    );
    if (result.success) {
      await _recordShare(ref, post.id, result.actionId);
    }
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

  /// 任务 A · 负反馈即时反馈统一收口：本地移除卡片 + 降级提示 toast。
  ///
  /// 仅做本地乐观移除（`removePostLocally`），不改 discovery_feed_provider 的
  /// 实时补丁逻辑；负反馈行为事件已在调用点单独上报。
  void _dismissFeedPost(
    BuildContext context,
    WidgetRef ref,
    String postId, {
    required String toast,
  }) {
    ref.read(discoveryFeedMapProvider.notifier).removePostLocally(postId);
    if (context.mounted) {
      AppToast.show(context, toast);
    }
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
