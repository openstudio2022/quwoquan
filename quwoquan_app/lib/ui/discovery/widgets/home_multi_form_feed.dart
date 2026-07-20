// ignore_for_file: unnecessary_non_null_assertion
import 'dart:async';
import 'dart:math' show max, min;
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/utils/content_keyword_suggester.dart';
import 'package:quwoquan_app/core/widgets/blocked_keyword_confirmation_sheet.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/core/widgets/content_report_reason_sheet.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_aspect_ratio.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/discovery/services/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/discovery/services/discovery_share_template.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_center_glyph.dart';
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
part 'home_multi_form_feed_media_autoplay.dart';
part 'home_multi_form_feed_media_grid.dart';
part 'home_multi_form_feed_actions.dart';
part 'home_multi_form_feed_report_actions.dart';
part 'home_multi_form_feed_object_cards.dart';

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
    this.onInitialContentPainted,
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
  final VoidCallback? onInitialContentPainted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(postInteractionStateProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(channelId));
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final articleDistributionEnabled = ref.watch(
      contentFeatureFlagProvider('enable_article_distribution_profiles'),
    );
    final shouldShowFollowingArticles =
        channelId == 'following' && articleDistributionEnabled;

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
    final articlesById = <String, PostBaseDto>{
      for (final article in dtos.where((post) => post.isArticleLike))
        article.id: article,
    };
    final articles = articlesById.values.toList(growable: false);
    final feedPosts = shouldShowFollowingArticles
        ? <PostBaseDto>[...moments, ...articles]
        : dtos;
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      _scheduleHomeReportContinuationResume(context, ref, feedPosts);
    }
    final blockingError = feedAsync.value?.blockingError;
    final appendError = feedAsync.value?.appendError;
    final staleDataError = feedAsync.value?.staleDataError;
    final hasBlockingError = blockingError != null;

    final isFeedLoading =
        feedAsync.isLoading || (feedAsync.value?.isLoading ?? false);
    if (isFeedLoading && feedPosts.isEmpty && !hasBlockingError) {
      // 任务 A · 加载态：用占位渐显的骨架屏代替裸 spinner，避免白屏并提示版式。
      return Column(
        children: <Widget>[
          Expanded(child: _HomeFeedSkeleton(isDark: isDark)),
          if (feedAsync.value?.isSlow ?? false)
            AppRequestFeedback.inline(
              key: const ValueKey<String>('home_feed_slow_hint'),
              showSlowHint: true,
              showIndicator: false,
              slowLabel: UITextConstants.requestWaitSlow,
            ),
        ],
      );
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

    if (feedPosts.isEmpty && !isFeedLoading && !hasBlockingError) {
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
      if (!context.mounted) {
        return;
      }
      ref
          .read(feedPerformanceObservabilityProvider)
          .markFirstContentReady(channelId, itemCount: firstScreenItemCount);
      onInitialContentPainted?.call();
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
    // Impression gate 可能在子树 dispose 时补报弱曝光。此处捕获与本批卡片同源的
    // tracker/session 快照，禁止在 deactivated element 的回调里再次通过 ref 查祖先。
    final behaviorTracker = ref.read(contentBehaviorTrackerProvider);
    final feedSession = ref.read(feedSessionProvider.notifier);
    final impressionFeedRequestId = feedSession.currentFeedRequestId;
    final impressionRankingVersion = feedSession.currentRankingVersion;
    final impressionReasonVersion = feedSession.currentReasonVersion;

    Widget buildCard(
      PostBaseDto dto,
      int index,
      ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal,
    ) {
      // N0-4 七态语义：impressed 必须来自真实视口可见性（50%+1s 门控），
      // 由 _QualifiedImpressionGate 驱动；build 帧不再直接上报（预构建卡片
      // 曾被误记 impressed → 拉黑 7 天 + CTR 分母污染）。
      Widget withImpressionGate(Widget child) {
        return _QualifiedImpressionGate(
          key: ValueKey<String>('home-feed-impression-${dto.id}'),
          contentId: dto.id,
          onQualified: (visibleFraction, visibleDuration) {
            behaviorTracker.trackQualifiedImpression(
              dto.id,
              visibleFraction: visibleFraction,
              visibleDuration: visibleDuration,
              contentType: dto.identity,
              position: index,
              referralSource: ReferralSource.organicFeed,
              feedRequestId: impressionFeedRequestId,
              channelId: channelId,
              rankingVersion: impressionRankingVersion,
              reasonVersion: impressionReasonVersion,
              recallPath: dto.recallPath,
              contentVertical: dto.contentVertical,
              supplySource: dto.supplySource,
            );
          },
          onWeakVisible: () {
            behaviorTracker.trackVisible(
              dto.id,
              contentType: dto.identity,
              position: index,
              referralSource: ReferralSource.organicFeed,
              feedRequestId: impressionFeedRequestId,
              channelId: channelId,
              rankingVersion: impressionRankingVersion,
              reasonVersion: impressionReasonVersion,
              recallPath: dto.recallPath,
              contentVertical: dto.contentVertical,
              supplySource: dto.supplySource,
            );
          },
          child: child,
        );
      }

      if (dto.isArticleLike && shouldShowFollowingArticles) {
        return withImpressionGate(
          _FeedPatchVisibilityReporter(
            key: ValueKey<String>('feed-patch-reporter-$index'),
            postId: dto.id,
            child: _FollowingArticleCard(
              item: dto,
              isDark: isDark,
              summaryLineLimit:
                  _followingArticleDistributionProfile.summaryLineLimit,
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
                      reasonVersion: feedSession.currentReasonVersion,
                      recallPath: dto.recallPath,
                      contentVertical: dto.contentVertical,
                      supplySource: dto.supplySource,
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
          ),
        );
      }
      return withImpressionGate(
        _FeedPatchVisibilityReporter(
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
                    reasonVersion: feedSession.currentReasonVersion,
                    recallPath: dto.recallPath,
                    contentVertical: dto.contentVertical,
                    supplySource: dto.supplySource,
                  );
              if (!(effectiveDisableViewerOnTap && dto.hasImages)) {
                onPostTap?.call(dto, imgIndex, feedPosts: feedPosts);
              }
            },
            onCommentTap: () {
              CommentViewer.showModal(
                context: context,
                postId: dto.id,
                entryObservedCommentCount: ref
                    .read(postInteractionStateProvider)
                    .commentCountFor(dto.id, fallback: dto.commentCount),
                onShareTap: () => _showShare(
                  context,
                  ref,
                  dto,
                  enableIdentityTemplate: ref.read(
                    contentFeatureFlagProvider(
                      'enable_identity_share_template',
                    ),
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
    final resourceProfile = ref.watch(appResourceCacheProfileProvider);
    // 混合对象卡编织（B4 插卡模式）：anchorIndex 基于内容序位；post 的埋点
    // position 与 card key 仍用数据索引（postIndex），不受对象卡插入影响。
    final feedEntries = _weaveObjectCards(
      feedPosts,
      feedAsync.value?.objectCards ?? const <FeedObjectCardDto>[],
    );
    Widget buildEntry(
      int entryIndex,
      ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal,
    ) {
      final entry = feedEntries[entryIndex];
      return switch (entry) {
        _HomeFeedPostEntry(:final post, :final postIndex) => buildCard(
          post,
          postIndex,
          videoScrollSignal,
        ),
        _HomeFeedObjectCardEntry(:final card) => _HomeEntityObjectCard(
          key: ValueKey<String>('home-object-card-entry-$entryIndex'),
          card: card,
          isDark: isDark,
          channelId: channelId,
        ),
      };
    }

    final scrollView = _HomeFeedScrollView(
      pageBackground: pageBackground,
      isDark: isDark,
      resourceProfile: resourceProfile,
      isMultiColumn: isMultiColumn,
      columns: columns,
      horizontalPad: horizontalPad,
      topPad: topPad,
      bottomPad: isMultiColumn ? bottomPad + AppSpacing.sm : bottomPad,
      itemCount: feedEntries.length,
      itemBuilder: buildEntry,
      isFullSpanItem: (index) => switch (feedEntries[index]) {
        _HomeFeedPostEntry(:final post) => layoutPolicy.shouldRenderFullSpan(
          post,
        ),
        _HomeFeedObjectCardEntry() => true,
      },
      fullSpanBuilder: buildEntry,
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
      onResourceSample: () {
        final imageCache = PaintingBinding.instance.imageCache;
        final downloadCache = ref.read(mediaDownloadCacheProvider);
        final observability = ref.read(feedPerformanceObservabilityProvider);
        observability.recordImageCacheBudget(
          profile: resourceProfile.name,
          currentSizeBytes: imageCache.currentSizeBytes,
          maxSizeBytes: imageCache.maximumSizeBytes,
        );
        observability.recordMediaDownloadQueue(
          profile: resourceProfile.name,
          activeDownloads: downloadCache.activeDownloadCount,
          queuedDownloads: downloadCache.queuedDownloadCount,
          inflightDownloads: downloadCache.inflightDownloadCount,
          cacheSizeBytes: downloadCache.currentCacheSizeBytes,
        );
      },
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
    runWhenLoggedIn(ref, context, AuthGateReason.share, () {
      final template = buildDiscoveryShareTemplate(
        post: post,
        wire: _rawDiscoveryItem(post),
        enableIdentityTemplate: enableIdentityTemplate,
      );
      ContentShareSheet.show(
        context,
        template: template,
        circlePostPlacementWriter: ref.read(
          homeFeedCirclePostPlacementWriterProvider,
        ),
        circleMembershipQuery: ref.read(homeFeedCircleMembershipQueryProvider),
        outboundShareWriter: ref.read(
          homeFeedContentOutboundShareWriterProvider,
        ),
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
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    unawaited(
      journeyTracker.trackAction(
        journey: 'content_more_actions',
        action: 'open',
        pageName: 'home_multi_form_feed',
        targetType: 'post',
        targetKey: post.id,
      ),
    );
    MoreActionPopup.show(
      context: context,
      panelMaxWidth: panelMaxWidth,
      config: MediaPostMoreActionConfig(
        onActionInvoked: (actionId) => unawaited(
          journeyTracker.trackAction(
            journey: 'content_more_actions',
            action: 'invoke',
            pageName: 'home_multi_form_feed',
            targetType: 'post',
            targetKey: post.id,
            payload: <String, Object?>{'actionId': actionId},
          ),
        ),
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
                reasonVersion: feedSession.currentReasonVersion,
                recallPath: post.recallPath,
                contentVertical: post.contentVertical,
                supplySource: post.supplySource,
              );
          // 任务 A · 负反馈即时反馈：卡片立即从信息流消失并给出降级提示。
          _dismissFeedPost(
            context,
            ref,
            post.id,
            toast: DiscoveryFeedText.feedNegativeFeedbackNotInterested,
            onUndo: () {
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackUndoDislike(
                    post.id,
                    contentType: post.type,
                    authorId: post.authorId,
                    feedRequestId: feedSession.currentFeedRequestId,
                    referralSource: ReferralSource.organicFeed,
                    channelId: channelId,
                    rankingVersion: feedSession.currentRankingVersion,
                    reasonVersion: feedSession.currentReasonVersion,
                    recallPath: post.recallPath,
                    contentVertical: post.contentVertical,
                    supplySource: post.supplySource,
                  );
              AppToast.show(context, UITextConstants.notInterestedUndone);
            },
          );
        },
        onBlockUser: () =>
            unawaited(_requestHomeBlockAuthor(context, ref, post)),
        onBlockWords: () =>
            unawaited(_requestHomeBlockKeyword(context, ref, post)),
        onReport: () => unawaited(_requestHomePostReport(context, ref, post)),
      ),
    );
  }

  Future<void> _requestHomeBlockAuthor(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post,
  ) async {
    final confirmed = await showAppActionSheet<bool>(
      context,
      title: UITextConstants.profileBlockConfirmTitle,
      message: UITextConstants.profileBlockConfirmMessage,
      sections: const <AppActionSheetSection<bool>>[
        AppActionSheetSection<bool>(
          items: <AppActionSheetItem<bool>>[
            AppActionSheetItem<bool>(
              value: true,
              label: UITextConstants.blockAuthor,
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (confirmed != true || !context.mounted) return;
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _applyHomeBlockAuthor(context, ref, post);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ContentModerationContinuation(
            postId: post.id,
            surface: ContentModerationContinuationSurface.homeFeed,
            action: ContentModerationContinuationAction.blockAuthor,
            authorId: post.authorId,
          ),
          ownerToken: 'home-feed-block-author:${post.id}',
        );
    if (!accepted) return;
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.blockUser,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _applyHomeBlockAuthor(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post,
  ) async {
    try {
      await ref
          .read(personaRelationshipBlockWriterProvider(AppUiSurfaces.homeFeed))
          .blockUser(BlockUserCommand(targetSubAccountId: post.authorId));
      final feedSession = ref.read(feedSessionProvider.notifier);
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
            reasonVersion: feedSession.currentReasonVersion,
            recallPath: post.recallPath,
            contentVertical: post.contentVertical,
            supplySource: post.supplySource,
          );
      if (!context.mounted) return;
      _dismissFeedPost(
        context,
        ref,
        post.id,
        toast: DiscoveryFeedText.feedNegativeFeedbackAuthorReduced,
      );
    } catch (error) {
      if (!context.mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _applyHomeBlockAuthor(context, ref, post);
          }
        },
      );
    }
  }

  Future<void> _requestHomeBlockKeyword(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post,
  ) async {
    final suggested = suggestContentBlockedKeyword(<String>[
      post.title,
      post.normalizedBody,
    ]);
    final keyword = await showBlockedKeywordConfirmationSheet(
      context,
      suggestedKeyword: suggested,
    );
    if (keyword == null || !context.mounted) return;
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _applyHomeBlockKeyword(context, ref, post, keyword);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ContentModerationContinuation(
            postId: post.id,
            surface: ContentModerationContinuationSurface.homeFeed,
            action: ContentModerationContinuationAction.blockKeyword,
            keyword: keyword,
          ),
          ownerToken: 'home-feed-block-keyword:${post.id}',
        );
    if (!accepted) return;
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.settingsAccount,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _applyHomeBlockKeyword(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post,
    String keyword,
  ) async {
    try {
      await ref.read(blockedKeywordWriterProvider).add(keyword);
      final feedSession = ref.read(feedSessionProvider.notifier);
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
            reasonVersion: feedSession.currentReasonVersion,
            recallPath: post.recallPath,
            contentVertical: post.contentVertical,
            supplySource: post.supplySource,
          );
      if (!context.mounted) return;
      _dismissFeedPost(
        context,
        ref,
        post.id,
        toast: DiscoveryFeedText.feedNegativeFeedbackContentReduced,
      );
    } catch (error) {
      if (!context.mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _applyHomeBlockKeyword(context, ref, post, keyword);
          }
        },
      );
    }
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
        wire: _rawDiscoveryItem(post),
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
    VoidCallback? onUndo,
  }) {
    final notifier = ref.read(discoveryFeedMapProvider.notifier);
    final removed = notifier.removePostLocally(postId);
    if (context.mounted) {
      AppToast.show(
        context,
        toast,
        actionLabel: onUndo == null ? null : UITextConstants.undo,
        onAction: onUndo == null
            ? null
            : () {
                notifier.restorePostsLocally(removed);
                onUndo();
              },
      );
    }
  }

  DiscoveryPresentationWire _rawDiscoveryItem(PostBaseDto post) {
    return DiscoveryPresentationWire(post.toMap());
  }
}
