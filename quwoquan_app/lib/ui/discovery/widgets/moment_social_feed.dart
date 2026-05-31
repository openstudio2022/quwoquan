// ignore_for_file: unnecessary_non_null_assertion
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
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
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';
import 'package:quwoquan_app/ui/discovery/widgets/today_intersection_rail.dart';

const double _momentCellVerticalPadding = AppSpacing.fourteen;
const double _momentSectionGap = AppSpacing.interGroupSm;
const double _momentToolbarIconSize = AppSpacing.twenty;
const double _momentMediaGap = AppSpacing.xs;
const ArticleDistributionProfileConfig _followingArticleDistributionProfile =
    ArticleDistributionProfileConfig(
      id: 'follow_list_with_optional_cover',
      surface: 'following_feed',
      layout: 'cover_leading_title_summary',
      coverMode: 'optional_cover',
      summaryLineLimit: 2,
    );

/// 微趣频道：微博风格社交信息流
///
/// - 单列时间流
/// - 图片自适应：1 张全宽 4:3，2 张双列 1:1，3-9 张三列九宫格
/// - 文字超 5 行展示"展开"按钮，就地展开/收起
/// - 视频帖：内联视频卡片（静态封面 + 播放标识）
class MomentSocialFeed extends ConsumerWidget {
  const MomentSocialFeed({
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
    this.onIntersectionObjectAction,
  });

  final bool isDark;
  final String channelId;

  /// 频道模板（来自 homeChannels.template；驱动单列/多列/今日交集流/图片前置）。
  /// 取值：single_column_relations / masonry_recommend / intersection_rail_masonry。
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

  /// 今日交集对象卡卡体点击：跳转对应对象/聚合页（路由由宿主按 metadata 解析）。
  final void Function(IntersectionReason reason)? onIntersectionObjectOpen;

  /// 今日交集对象卡行动按钮点击：交集行动回流（trackFollow）由宿主处理。
  final void Function(IntersectionReason reason)? onIntersectionObjectAction;

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
    final hasError = feedAsync.value?.error != null;

    if (feedAsync.isLoading && feedPosts.isEmpty && !hasError) {
      return const Center(child: CupertinoActivityIndicator());
    }

    if (hasError && feedPosts.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.interGroupLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                context.l10n.loadFailed,
                style: TextStyle(
                  color: AppColors.error,
                  fontSize: AppTypography.iosBody,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.interGroupMd),
              CupertinoButton(
                onPressed: () =>
                    ref.read(discoveryFeedMapProvider.notifier).load(channelId),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                  vertical: AppSpacing.intraGroupSm,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.arrow_clockwise,
                      size: AppSpacing.iconSmall,
                      color: AppColors.iosAccent(context),
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Text(
                      context.l10n.retry,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: AppColors.iosAccent(context),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final listDividerColor =
        SettingsSemanticConstants.conversationSheetDividerColor(
          isDark,
        ).withValues(alpha: 0.9);
    final forceSingleColumn = template == 'single_column_relations';
    final imageForward = template == 'masonry_recommend';
    final showIntersectionRail = template == 'intersection_rail_masonry';
    final effectiveInlineCarousel = inlineImageCarousel || imageForward;
    final effectiveDisableViewerOnTap = disableImageViewerOnTap || imageForward;
    final columns = forceSingleColumn
        ? 1
        : AppSpacing.feedResponsiveColumns(context);
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
      return _MomentWeiboCard(
        cardContainerKey: ValueKey<String>('moment-feed-card-$index'),
        moreButtonKey: ValueKey<String>('moment-feed-more-$index'),
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

    final todayReasons = showIntersectionRail
        ? _collectTodayIntersectionReasons(feedPosts)
        : const <IntersectionReason>[];
    final headerSliver = todayReasons.isEmpty
        ? null
        : TodayIntersectionRail(
            reasons: todayReasons,
            isDark: isDark,
            onReasonTap: onIntersectionObjectOpen,
            onReasonAction: onIntersectionObjectAction,
          );

    final topPad = isMultiColumn ? AppSpacing.sm : AppSpacing.zero;
    return _MomentFeedScrollView(
      pageBackground: pageBackground,
      isDark: isDark,
      isMultiColumn: isMultiColumn,
      columns: columns,
      horizontalPad: horizontalPad,
      topPad: topPad,
      bottomPad: isMultiColumn ? bottomPad + AppSpacing.sm : bottomPad,
      itemCount: feedPosts.length,
      itemBuilder: (index) => buildCard(feedPosts[index], index),
      dividerColor: listDividerColor,
      isLoadingMore: feedAsync.value?.isLoading ?? false,
      hasMore: feedAsync.value?.nextCursor?.isNotEmpty ?? false,
      moodCopy: _resolveChannelMoodCopy(),
      headerSliver: headerSliver,
      onReachBottom: () =>
          ref.read(discoveryFeedMapProvider.notifier).appendNextPage(channelId),
    );
  }

  /// 从当前 feed 各帖聚合去重的交集理由，供「今日交集」顶部流消费。
  /// 不引入第二套业务列表（数据来自已加载的 feed item），无来源时返回空。
  List<IntersectionReason> _collectTodayIntersectionReasons(
    List<PostBaseDto> feedPosts,
  ) {
    final collected = <IntersectionReason>[];
    final seenKeys = <String>{};
    for (final post in feedPosts) {
      final reasons = post.intersectionReasons;
      if (reasons == null) continue;
      for (final reason in reasons) {
        final text = reason.displayText.trim();
        if (text.isEmpty) continue;
        final key = '${reason.dimension}|$text';
        if (seenKeys.add(key)) {
          collected.add(reason);
        }
      }
    }
    return collected;
  }

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
    final surfaceView =
        ContentSurfaceViewMapper.fromDto(post, wire: wire?.toWireMap());
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

/// 多列瀑布每段卡数：段尾由 sliver 边界天然两列齐平，段间留过渡白（今日交集流注入点）。
const int _kFeedSegmentSize = 10;

class _MomentFeedScrollView extends StatefulWidget {
  const _MomentFeedScrollView({
    required this.pageBackground,
    required this.isDark,
    required this.isMultiColumn,
    required this.columns,
    required this.horizontalPad,
    required this.topPad,
    required this.bottomPad,
    required this.itemCount,
    required this.itemBuilder,
    required this.dividerColor,
    required this.isLoadingMore,
    required this.hasMore,
    required this.onReachBottom,
    this.moodCopy = '',
    this.headerSliver,
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
  final Color dividerColor;
  final bool isLoadingMore;
  final bool hasMore;
  final VoidCallback onReachBottom;

  /// 频道气质文案（来自 ContentUIConfig.homeChannels.moodCopyKey 解析，只读）；空则不展示。
  final String moodCopy;

  /// 顶部 sliver（今日交集横滑流）；null 不展示。
  final Widget? headerSliver;

  @override
  State<_MomentFeedScrollView> createState() => _MomentFeedScrollViewState();
}

class _MomentFeedScrollViewState extends State<_MomentFeedScrollView> {
  final ScrollController _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onScroll);
  }

  @override
  void dispose() {
    _controller.removeListener(_onScroll);
    _controller.dispose();
    super.dispose();
  }

  void _onScroll() {
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
      slivers.add(
        SliverToBoxAdapter(child: SizedBox(height: widget.topPad)),
      );
    }

    if (widget.isMultiColumn) {
      var start = 0;
      while (start < widget.itemCount) {
        final end = (start + _kFeedSegmentSize).clamp(0, widget.itemCount);
        final segStart = start;
        final segCount = end - segStart;
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
        start = end;
        // 段间过渡留白：今日交集横滑流(V1-D) 注入点。
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
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              if (index.isOdd) {
                final dividerIndex = index ~/ 2;
                return Divider(
                  key: ValueKey<String>('moment-feed-divider-$dividerIndex'),
                  height: AppSpacing.one,
                  thickness: AppSpacing.hairline,
                  color: widget.dividerColor,
                );
              }
              return widget.itemBuilder(index ~/ 2);
            },
            childCount:
                widget.itemCount == 0 ? 0 : widget.itemCount * 2 - 1,
          ),
        ),
      );
    }

    slivers.add(
      SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.only(
            top: widget.isLoadingMore
                ? AppSpacing.interGroupMd
                : AppSpacing.zero,
            bottom: widget.bottomPad,
          ),
          child: widget.isLoadingMore
              ? _LoadMoreFooter(moodCopy: widget.moodCopy, isDark: widget.isDark)
              : const SizedBox.shrink(),
        ),
      ),
    );
    return slivers;
  }
}

/// 触底加载 footer：加载指示 + 频道气质文案（只读，空文案不展示）。
class _LoadMoreFooter extends StatelessWidget {
  const _LoadMoreFooter({required this.moodCopy, required this.isDark});

  final String moodCopy;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CupertinoActivityIndicator(),
        if (moodCopy.isNotEmpty) ...[
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
// 单条微趣卡片（微博风格）
// ─────────────────────────────────────────────────────────────────────────────

class _MomentWeiboCard extends ConsumerStatefulWidget {
  const _MomentWeiboCard({
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
  ConsumerState<_MomentWeiboCard> createState() => _MomentWeiboCardState();
}

class _MomentWeiboCardState extends ConsumerState<_MomentWeiboCard>
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
          _momentCellVerticalPadding,
          AppSpacing.containerMd,
          _momentCellVerticalPadding,
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
                          _MomentMoreButton(
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
              const SizedBox(height: _momentSectionGap),
              IntersectionReasonChip(
                text: _intersectionReasonText!,
                isDark: isDark,
              ),
            ],

            // 正文（5 行截断 + 就地展开）
            if (item.normalizedBody.isNotEmpty) ...[
              const SizedBox(height: _momentSectionGap),
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
              const SizedBox(height: _momentSectionGap),
              widget.inlineImageCarousel
                  ? _MomentImageCarousel(
                      urls: item.imageUrls,
                      isDark: isDark,
                      onTap: widget.onImageTap,
                    )
                  : _MomentImageGrid(
                      urls: item.imageUrls,
                      isDark: isDark,
                      onTap: widget.onImageTap,
                    ),
            ],

            // 视频卡片
            if (item.hasVideo && !item.hasImages) ...[
              const SizedBox(height: _momentSectionGap),
              _MomentVideoCard(
                dto: item,
                isDark: isDark,
                onTap: () => widget.onImageTap(0),
              ),
            ],

            // 互动栏
            const SizedBox(height: _momentSectionGap),
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
            _MomentWeiboCardState._timeAgo(context, item.createdAt),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: _MomentMoreButton(
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

class _MomentImageGrid extends StatelessWidget {
  const _MomentImageGrid({
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
        const SizedBox(width: _momentMediaGap),
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
        crossAxisSpacing: _momentMediaGap,
        mainAxisSpacing: _momentMediaGap,
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
    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      placeholder: (context, url) => _placeholder(),
      errorWidget: (context, url, err) => _placeholder(),
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

class _MomentImageCarousel extends StatefulWidget {
  const _MomentImageCarousel({
    required this.urls,
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;
  final bool isDark;
  final void Function(int index) onTap;

  @override
  State<_MomentImageCarousel> createState() => _MomentImageCarouselState();
}

class _MomentImageCarouselState extends State<_MomentImageCarousel> {
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
                  child: CachedNetworkImage(
                    imageUrl: urls[index],
                    fit: BoxFit.cover,
                    placeholder: (context, url) => _placeholder(),
                    errorWidget: (context, url, err) => _placeholder(),
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

class _MomentVideoCard extends StatelessWidget {
  const _MomentVideoCard({
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
                size: _momentToolbarIconSize,
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
              size: _momentToolbarIconSize,
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
              size: _momentToolbarIconSize,
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

class _MomentMoreButton extends StatelessWidget {
  const _MomentMoreButton({
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
