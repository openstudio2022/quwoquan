// ignore_for_file: unnecessary_non_null_assertion
import 'dart:async';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_cover_slot.dart';
import 'package:quwoquan_app/runtime/di/content_post_media_binding.dart';
import 'dart:math' show max, min;
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/design_system/formatters/compact_count_formatter.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_keyword_suggester.dart';
import 'package:quwoquan_app/runtime/shell/actions/blocked_keyword_confirmation_sheet.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/runtime/shell/actions/content_report_reason_sheet.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/runtime/di/presentation/home_feed_cross_object_composition.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/more_action_popup/media_post_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/more_action_popup/more_action_popup.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/design_system/content/post_preview_list_tile.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/media/media_aspect_ratio.dart';
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability_provider.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_actions.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/discovery_share_template.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/home_feed_layout_policy.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/home_feed_impression_sampling_clock.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/home_feed_scroll_anchor.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/home_feed_video_autoplay_policy.dart';
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_feed_video_focus_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/entity_wishlist_action.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart'
    show GatheringText;
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/feed_realtime_patch_provider.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/generated/homepage_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/home_feed_scroll_anchor_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/following_subject_strip.dart';
part 'home_multi_form_feed_scroll.dart';
part 'home_multi_form_feed_scroll_anchor.dart';
part 'home_multi_form_feed_local_actions.dart';
part 'home_multi_form_feed_channel_config.dart';
part 'home_multi_form_feed_post_cards.dart';
part 'home_multi_form_feed_states.dart';
part 'home_multi_form_feed_media.dart';
part 'home_multi_form_feed_media_autoplay.dart';
part 'home_multi_form_feed_media_grid.dart';
part 'home_multi_form_feed_actions.dart';
part 'home_multi_form_feed_report_actions.dart';
part 'home_multi_form_feed_object_cards.dart';

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
    ContentPostViewData post,
    int index, {
    List<ContentPostViewData>? feedPosts,
  })?
  onPostTap;
  final void Function(ContentPostViewData post)? onMoreTap;
  final VoidCallback? onInitialContentPainted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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

    final dtos = feedAsync.value?.items ?? const <ContentPostViewData>[];
    final moments = dtos
        .where((post) => post.identity == 'moment')
        .toList(growable: false);
    final articlesById = <String, ContentPostViewData>{
      for (final article in dtos.where((post) => post.isArticleLike))
        article.id: article,
    };
    final articles = articlesById.values.toList(growable: false);
    final feedPosts = shouldShowFollowingArticles
        ? <ContentPostViewData>[...moments, ...articles]
        : dtos;
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      _scheduleHomeReportContinuationResume(context, ref, feedPosts);
    }
    final blockingError = feedAsync.value?.blockingError;
    final appendError = feedAsync.value?.appendError;
    final staleDataError = feedAsync.value?.staleDataError;
    final emptyReason = feedAsync.value?.emptyReason;
    final isFeedLoading =
        feedAsync.isLoading || (feedAsync.value?.isLoading ?? false);
    final effectiveBlockingError =
        blockingError ??
        (!isFeedLoading &&
                feedAsync.value != null &&
                feedPosts.isEmpty &&
                emptyReason == null
            ? discoveryFeedInitialPageProtocolFailure(channelId)
            : null);
    final hasBlockingError = effectiveBlockingError != null;
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
              slowLabel: FoundationText.requestWaitSlow,
            ),
        ],
      );
    }

    if (hasBlockingError && feedPosts.isEmpty) {
      final semantic = runtimeErrorSemantic(
        context,
        error: effectiveBlockingError,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
        sourceOperationId: AppCloudOperationIds.contentPostGetFeed,
        sourceRouteId: AppUiSurfaces.homeFeed.routeId,
        sourceSurfaceId: AppUiSurfaces.homeFeed.id,
      );
      // 任务 B · 页面级异常可观测：首屏阻断态空内容上报加载失败归因（按因去重）。
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(feedPerformanceObservabilityProvider)
            .recordFeedLoadFailed(
              channelId: channelId,
              errorCode: semantic.sourceCode ?? 'APP.SYSTEM.unknown_error',
              operation:
                  semantic.sourceOperationId ??
                  AppCloudOperationIds.contentPostGetFeed,
              surface: semantic.sourceSurfaceId ?? AppUiSurfaces.homeFeed.id,
              hasCache: false,
              recovery: semantic.recoveryAction?.name,
              requestId: semantic.requestId,
              traceId: semantic.traceId,
            );
      });
      final handledActionTypes = <UiErrorActionType>{
        UiErrorActionType.login,
        UiErrorActionType.retry,
        UiErrorActionType.resubmit,
      };
      final hasHandledAction =
          <UiErrorAction?>[semantic.primaryAction, semantic.secondaryAction]
              .whereType<UiErrorAction>()
              .any((action) => handledActionTypes.contains(action.type));
      return AppPageErrorState(
        semantic: semantic,
        onRecovery: !hasHandledAction
            ? null
            : (action) async {
                if (action.type == UiErrorActionType.login) {
                  openLoginPage(
                    context,
                    reasonName: AuthGateReason.followingFeed.name,
                    redirect: AppRoutePaths.home,
                    dismissFallback: AppRoutePaths.home,
                  );
                  return UiRecoveryOutcome.handedOff;
                }
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  final result = await ref
                      .read(discoveryFeedMapProvider.notifier)
                      .load(channelId, force: true);
                  return switch (result.terminal) {
                    DiscoveryFeedLoadTerminal.content ||
                    DiscoveryFeedLoadTerminal.canonicalEmpty ||
                    DiscoveryFeedLoadTerminal.retainedContent =>
                      UiRecoveryOutcome.recovered,
                    DiscoveryFeedLoadTerminal.stillBlocked =>
                      UiRecoveryOutcome.stillBlocked,
                    DiscoveryFeedLoadTerminal.superseded =>
                      UiRecoveryOutcome.superseded,
                    DiscoveryFeedLoadTerminal.cancelled =>
                      UiRecoveryOutcome.cancelled,
                  };
                }
                return UiRecoveryOutcome.cancelled;
              },
      );
    }

    if (feedPosts.isEmpty && !isFeedLoading && !hasBlockingError) {
      if (channelId == 'following') {
        return _HomeFollowingFeedEmptyState(isDark: isDark);
      }
      if (emptyReason == ContentFeedEmptyReason.noActiveRelease) {
        return _HomeFeedNoActiveReleaseState(
          isDark: isDark,
          onRefresh: () async {
            await ref
                .read(discoveryFeedMapProvider.notifier)
                .load(channelId, force: true);
          },
        );
      }
      return _HomeFeedCompletedNotice(isDark: isDark);
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
    // tracker/频道归因快照，禁止在 deactivated element 的回调里再次通过 ref 查祖先。
    final behaviorTracker = ref.watch(contentBehaviorTrackerProvider);
    final impressionFeedRequestId = feedAsync.value?.feedRequestId;
    final impressionPolicyDigest = feedAsync.value?.policyDigest;

    Widget buildCard(
      ContentPostViewData dto,
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
              policyDigest: impressionPolicyDigest,
              recallPath: dto.recallPath,
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
              policyDigest: impressionPolicyDigest,
              recallPath: dto.recallPath,
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
                ref
                    .read(contentBehaviorTrackerProvider)
                    .trackClick(
                      dto.id,
                      contentType: dto.identity,
                      feedRequestId: impressionFeedRequestId,
                      position: index,
                      referralSource: ReferralSource.organicFeed,
                      channelId: channelId,
                      policyDigest: impressionPolicyDigest,
                      recallPath: dto.recallPath,
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
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackClick(
                    dto.id,
                    contentType: dto.identity,
                    feedRequestId: impressionFeedRequestId,
                    position: index,
                    referralSource: ReferralSource.organicFeed,
                    channelId: channelId,
                    policyDigest: impressionPolicyDigest,
                    recallPath: dto.recallPath,
                    supplySource: dto.supplySource,
                  );
              if (!(effectiveDisableViewerOnTap && dto.hasImages)) {
                onPostTap?.call(dto, imgIndex, feedPosts: feedPosts);
              }
            },
            onCommentTap: () {
              HomeFeedCrossObjectComposition.showComments(
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
    // 交集 spotlight 只在频道配置声明 spotlightSegment 且 viewer 已登录时出现：
    // 游客没有「我的交集」这个事实面，模块必须整体缺席而不是显示空壳。
    final shouldShowIntersectionSpotlight =
        layoutPolicy.hasIntersectionSpotlight &&
        ref.watch(authSessionControllerProvider).isAuthenticated;
    final Widget? headerSliver = switch (true) {
      _ when shouldShowFollowingSubjects => FollowingSubjectStrip(
        isDark: isDark,
      ),
      _ when shouldShowIntersectionSpotlight =>
        HomeFeedCrossObjectComposition.intersectionSpotlight(
          isDark: isDark,
          channelId: channelId,
        ),
      _ => null,
    };

    final topPad = isMultiColumn ? AppSpacing.sm : AppSpacing.zero;
    final resourceProfile = ref.watch(appResourceCacheProfileProvider);
    // 混合对象卡编织（B4 插卡模式）：anchorIndex 基于内容序位；post 的埋点
    // position 与 card key 仍用数据索引（postIndex），不受对象卡插入影响。
    final feedEntries = _weaveObjectCards(
      feedPosts,
      feedAsync.value?.objectCards ?? const <FeedObjectCard>[],
    );
    final feedEntryIdentities = feedEntries
        .map((entry) => entry.stableIdentity)
        .toList(growable: false);
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
        _HomeFeedObjectCardEntry(:final card) => _HomeDiscoverableTargetCard(
          key: ValueKey<String>(
            'home-object-card-entry-${entry.stableIdentity}',
          ),
          card: card,
          isDark: isDark,
          channelId: channelId,
          feedRequestId: impressionFeedRequestId,
          policyDigest: impressionPolicyDigest,
        ),
      };
    }

    final scrollView = _HomeFeedScrollView(
      key: ValueKey<String>('home-feed-scroll-$channelId'),
      channelId: channelId,
      anchorStore: ref.read(homeFeedScrollAnchorStoreProvider),
      entryIdentities: feedEntryIdentities,
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
      isLoadingMore: feedAsync.value?.isAppending ?? false,
      hasMore: feedAsync.value?.hasMore ?? false,
      canRestorePreviousPage: feedAsync.value?.canRestorePreviousPage ?? false,
      appendError: appendError,
      staleDataError: staleDataError,
      onRetryInitialLoad: () => ref
          .read(discoveryFeedMapProvider.notifier)
          .load(channelId, force: true),
      moodCopy: _resolveChannelMoodCopy(),
      headerSliver: headerSliver,
      onReachBottom: () =>
          ref.read(discoveryFeedMapProvider.notifier).appendNextPage(channelId),
      onReachTop: () => unawaited(
        ref
            .read(discoveryFeedMapProvider.notifier)
            .prependPreviousPage(channelId),
      ),
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

  void _showShare(
    BuildContext context,
    WidgetRef ref,
    ContentPostViewData post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.share, () {
      final template = buildDiscoveryShareTemplate(
        post: post,
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
    ContentPostViewData post, {
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
          final attribution = _currentFeedAttribution(ref);
          ref
              .read(contentBehaviorTrackerProvider)
              .trackDislike(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                feedRequestId: attribution.feedRequestId,
                referralSource: ReferralSource.organicFeed,
                channelId: channelId,
                policyDigest: attribution.policyDigest,
                recallPath: post.recallPath,
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
                    feedRequestId: attribution.feedRequestId,
                    referralSource: ReferralSource.organicFeed,
                    channelId: channelId,
                    policyDigest: attribution.policyDigest,
                    recallPath: post.recallPath,
                    supplySource: post.supplySource,
                  );
              AppToast.show(context, ContentText.notInterestedUndone);
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

  ({String? feedRequestId, String? policyDigest}) _currentFeedAttribution(
    WidgetRef ref,
  ) {
    final feed = ref.read(discoveryFeedProvider(channelId)).value;
    return (
      feedRequestId: feed?.feedRequestId,
      policyDigest: feed?.policyDigest,
    );
  }

  Future<void> _requestHomeBlockAuthor(
    BuildContext context,
    WidgetRef ref,
    ContentPostViewData post,
  ) async {
    final confirmed = await showAppActionSheet<bool>(
      context,
      title: ContentText.profileBlockConfirmTitle,
      message: ContentText.profileBlockConfirmMessage,
      sections: const <AppActionSheetSection<bool>>[
        AppActionSheetSection<bool>(
          items: <AppActionSheetItem<bool>>[
            AppActionSheetItem<bool>(
              value: true,
              label: ContentText.blockAuthor,
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
    ContentPostViewData post,
  ) async {
    try {
      await ref
          .read(personaRelationshipBlockWriterProvider(AppUiSurfaces.homeFeed))
          .blockUser(BlockUserCommand(targetPersonaId: post.authorId));
      final attribution = _currentFeedAttribution(ref);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideAuthor(
            post.id,
            authorId: post.authorId,
            contentType: post.type,
            feedRequestId: attribution.feedRequestId,
            referralSource: ReferralSource.organicFeed,
            channelId: channelId,
            policyDigest: attribution.policyDigest,
            recallPath: post.recallPath,
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
    ContentPostViewData post,
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
    ContentPostViewData post,
    String keyword,
  ) async {
    try {
      await ref.read(blockedKeywordWriterProvider).add(keyword);
      final attribution = _currentFeedAttribution(ref);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideContentType(
            post.id,
            contentType: post.type,
            authorId: post.authorId,
            feedRequestId: attribution.feedRequestId,
            referralSource: ReferralSource.organicFeed,
            channelId: channelId,
            policyDigest: attribution.policyDigest,
            recallPath: post.recallPath,
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
}
