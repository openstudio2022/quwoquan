// ignore_for_file: unnecessary_non_null_assertion, unused_element, unused_element_parameter
import 'dart:async';
import 'dart:math' show max;
import 'dart:ui' show ImageFilter;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

class WorksImmersiveViewer extends ConsumerStatefulWidget {
  const WorksImmersiveViewer({
    super.key,
    required this.showWorksToolbar,
    required this.onUserTap,
    required this.onAssistantTap,
    this.onSwitchToFollowing,
    this.onSwitchToCircles,
    this.onSwitchToMoment, // Deprecated/Fallback
    this.onRevealSystemNav,
    this.onHideSystemNav,
  });

  final bool showWorksToolbar;
  final void Function(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  })
  onUserTap;
  final VoidCallback onAssistantTap;
  final VoidCallback? onSwitchToFollowing;
  final VoidCallback? onSwitchToCircles;
  final VoidCallback? onSwitchToMoment;
  final VoidCallback? onRevealSystemNav;
  final VoidCallback? onHideSystemNav;

  @override
  ConsumerState<WorksImmersiveViewer> createState() =>
      _WorksImmersiveViewerState();
}

class _WorksImmersiveViewerState extends ConsumerState<WorksImmersiveViewer>
    with TickerProviderStateMixin {
  static bool _didAutoExpandInSession = false;
  static const double _toolbarReservedHeight = 108;

  String? _filterType;
  bool _isFilterExpanded = false;
  int _currentPage = 0;

  final Set<String> _likedPosts = <String>{};
  final Set<String> _savedPosts = <String>{};
  final Set<String> _followingUsers = <String>{};
  final Map<String, int> _shareCountDelta = <String, int>{};
  final Map<String, int> _photoInnerIndex = <String, int>{};
  final Map<String, int> _articleInnerIndex = <String, int>{};
  final Map<String, int> _videoInnerIndex = <String, int>{};

  // Dwell tracking：记录当前帖子进入时间
  DateTime? _pageEnterTime;

  Timer? _autoCollapseTimer;
  // Follow-button delayed reveal: 3 s for photos, 5 s for video/article.
  Timer? _followButtonTimer;
  bool _showFollowButton = false;

  late final PageController _pageController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      for (final tabId in <String>['photo', 'video', 'article']) {
        final feedMap = ref.read(discoveryFeedMapProvider);
        if (!feedMap.containsKey(tabId)) {
          ref.read(discoveryFeedMapProvider.notifier).load(tabId);
        }
      }
      _runOneTimeAutoExpand();
      // Kick off the follow-button timer for the first visible post.
      final posts = _buildFeed();
      if (posts.isNotEmpty) {
        _startFollowButtonTimer(posts[0]);
        // Track impression for the first post
        _trackImpressionForPost(posts[0]);
        _pageEnterTime = DateTime.now();
      }
    });
  }

  @override
  void dispose() {
    _autoCollapseTimer?.cancel();
    _followButtonTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  /// Resets follow-button visibility and starts the appropriate reveal strategy:
  /// - Already following: show immediately (state is established, no discovery needed).
  /// - Not following: delayed reveal — 3 s for photos, 5 s for video / article.
  void _startFollowButtonTimer(PostBaseDto post) {
    _followButtonTimer?.cancel();
    if (_followingUsers.contains(post.authorId)) {
      // Already following → show right away, no animation delay.
      if (!_showFollowButton) setState(() => _showFollowButton = true);
      return;
    }
    if (_showFollowButton) setState(() => _showFollowButton = false);
    final delay = post is PhotoPostDto
        ? const Duration(seconds: 3)
        : const Duration(seconds: 5);
    _followButtonTimer = Timer(delay, () {
      if (mounted) setState(() => _showFollowButton = true);
    });
  }

  void _runOneTimeAutoExpand() {
    if (_didAutoExpandInSession) return;
    _didAutoExpandInSession = true;
    setState(() => _isFilterExpanded = true);
    _autoCollapseTimer?.cancel();
    _autoCollapseTimer = Timer(const Duration(milliseconds: 1500), () {
      if (!mounted) return;
      setState(() => _isFilterExpanded = false);
    });
  }

  void _toggleFilterPanel() {
    _autoCollapseTimer?.cancel();
    setState(() => _isFilterExpanded = !_isFilterExpanded);
  }

  void _collapseFilterPanel() {
    if (!_isFilterExpanded) return;
    _autoCollapseTimer?.cancel();
    setState(() => _isFilterExpanded = false);
  }

  /// Opens the post-level more-options sheet for the currently visible post.
  /// Uses dev1.1 MoreActionPopup (MediaPostMoreActionConfig) for parity.
  /// Deliberately does NOT open the assistant — that remains the assistant
  /// avatar button on the primary tab bar.
  void _showWorksMoreSheet(BuildContext context) {
    final posts = _buildFeed();
    final post = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)] as PostBaseDto?;
    if (post == null) return;
    final enableIdentityTemplate = ref.read(
      contentFeatureFlagProvider('enable_identity_share_template'),
    );
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
        post: post,
        onSave: () => _onFavorite(post),
        onCopyLink: () => _copyLink(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onShare: () => _sharePost(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onNotInterested: () {
          ref.read(contentBehaviorTrackerProvider).trackDislike(post.id);
        },
        onBlockUser: () {
          ref.read(blockRepositoryProvider).blockUser(post.authorId);
        },
        onBlockWords: () async {
          final keyword = _keywordForPost(post);
          if (keyword.isEmpty) return;
          await ref
              .read(keywordBlockRepositoryProvider)
              .addBlockedKeyword(keyword);
        },
        onReport: () {
          ref
              .read(behaviorRepositoryProvider)
              .reportSingle(contentId: post.id, action: 'report');
          ref
              .read(reportRepositoryProvider)
              .createReport(
                targetId: post.id,
                targetType: 'post',
                reason: 'inappropriate',
              );
        },
      ),
    );
  }

  List<PostBaseDto> _buildFeed() {
    final photos = ref.watch(discoveryFeedProvider('photo')).value?.items ?? [];
    final videos = ref.watch(discoveryFeedProvider('video')).value?.items ?? [];
    final articles =
        ref.watch(discoveryFeedProvider('article')).value?.items ?? [];

    if (_filterType == 'image') return photos;
    if (_filterType == 'video') return videos;
    if (_filterType == 'article') return articles;

    final result = <PostBaseDto>[];
    final maxLen = max(photos.length, max(videos.length, articles.length));
    for (var i = 0; i < maxLen; i++) {
      if (i < photos.length) result.add(photos[i]);
      if (i < videos.length) result.add(videos[i]);
      if (i < articles.length) result.add(articles[i]);
    }
    return result;
  }

  int _articleCardCount(String postId) {
    final raw = ref.watch(appContentRepositoryProvider).discoveryArticleData;
    final target = raw.cast<Map<String, dynamic>?>().firstWhere(
      (item) => item?['postId']?.toString() == postId,
      orElse: () => null,
    );
    final cards = target?['cards'];
    if (cards is List) return cards.length.clamp(1, 99);
    return 1;
  }

  List<Map<String, dynamic>> _articleCardsForPost(String postId) {
    final raw = ref.watch(appContentRepositoryProvider).discoveryArticleData;
    final target = raw.cast<Map<String, dynamic>?>().firstWhere(
      (item) => item?['postId']?.toString() == postId,
      orElse: () => null,
    );
    final cards = target?['cards'];
    if (cards is List) {
      return cards.whereType<Map<String, dynamic>>().toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }

  ({int current, int total}) _innerProgress(List<PostBaseDto> posts) {
    if (posts.isEmpty) return (current: 1, total: 1);
    final idx = _currentPage.clamp(0, posts.length - 1);
    final current = posts[idx];
    if (current is PhotoPostDto) {
      final total = current.imageUrls.isEmpty ? 1 : current.imageUrls.length;
      final currentIndex =
          (_photoInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentIndex, total: total);
    }
    if (current is ArticlePostDto) {
      final total = (_articleCardCount(current.id) + 1).clamp(1, 99);
      final currentCard =
          (_articleInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentCard, total: total);
    }
    if (current is VideoPostDto) {
      final episodes = _videoEpisodesForCurrent(current, posts);
      final total = episodes.length.clamp(1, 99);
      final currentEpisode =
          (_videoInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentEpisode, total: total);
    }
    return (current: 1, total: 1);
  }

  List<VideoPostDto> _videoEpisodesForCurrent(
    VideoPostDto current,
    List<PostBaseDto> posts,
  ) {
    final episodes = posts
        .whereType<VideoPostDto>()
        .where((v) => v.authorId == current.authorId)
        .toList(growable: false);
    if (episodes.isEmpty) return <VideoPostDto>[current];
    return episodes;
  }

  void _applyFilter(String? type) {
    setState(() {
      _filterType = type;
      _currentPage = 0;
      _pageController.jumpToPage(0);
    });
  }

  String _formatCount(int n) {
    if (n < 10000) return '$n';
    if (n >= 100000) return '10万+';
    // 10 000 ≤ n < 100 000: show as x.y万+ floored to one decimal.
    // e.g. 32 999 → 3.2万+  |  10 001 → 1万+  |  15 000 → 1.5万+
    final tenK = (n / 10000 * 10).floor() / 10;
    final s = (tenK * 10).round() % 10 == 0
        ? '${tenK.truncate()}万+'
        : '$tenK万+';
    return s;
  }

  Map<String, dynamic>? _rawPostById(String postId) {
    final repo = ref.watch(appContentRepositoryProvider);
    final all = <Map<String, dynamic>>[
      ...repo.discoveryPhotoData,
      ...repo.discoveryVideoData,
      ...repo.discoveryArticleData,
      ...repo.discoveryMomentData,
    ];
    return all.cast<Map<String, dynamic>?>().firstWhere(
      (item) => item?['postId']?.toString() == postId,
      orElse: () => null,
    );
  }

  String _circleIdForPost(PostBaseDto post) {
    final raw = _rawPostById(post.id);
    final rawCircleId = raw?['circleId']?.toString();
    if (rawCircleId != null && rawCircleId.isNotEmpty) return rawCircleId;
    return post.authorId;
  }

  String _circleNameForPost(PostBaseDto post) {
    final raw = _rawPostById(post.id);
    final circleName = raw?['circleName']?.toString();
    if (circleName != null && circleName.isNotEmpty) return circleName;
    return '圈子${_circleIdForPost(post)}';
  }

  // ── 行为追踪辅助 ──────────────────────────────────────────────

  void _trackImpressionForPost(PostBaseDto post) {
    final tracker = ref.read(contentBehaviorTrackerProvider);
    tracker.trackImpression(post.id);
  }

  void _flushDwell(PostBaseDto post) {
    final enterTime = _pageEnterTime;
    if (enterTime == null) return;
    final durationSec =
        DateTime.now().difference(enterTime).inMilliseconds / 1000.0;
    final tracker = ref.read(contentBehaviorTrackerProvider);
    tracker.trackDwell(post.id, durationSeconds: durationSec);
    _pageEnterTime = null;
  }

  // ── 互动操作（乐观 UI + 云侧 API 同步）────────────────────────

  void _onLike(PostBaseDto post) {
    final isLiked = _likedPosts.contains(post.id);
    setState(() {
      if (isLiked) {
        _likedPosts.remove(post.id);
      } else {
        _likedPosts.add(post.id);
      }
    });
    final repo = ref.read(contentInteractionRepositoryProvider);
    if (isLiked) {
      repo.unlike(post.id);
    } else {
      repo.like(post.id);
    }
  }

  void _onFavorite(PostBaseDto post) {
    final isSaved = _savedPosts.contains(post.id);
    setState(() {
      if (isSaved) {
        _savedPosts.remove(post.id);
      } else {
        _savedPosts.add(post.id);
      }
    });
    final repo = ref.read(contentInteractionRepositoryProvider);
    if (isSaved) {
      repo.unfavorite(post.id);
    } else {
      repo.favorite(post.id);
    }
  }

  void _onFollow(PostBaseDto post) {
    setState(() {
      if (_followingUsers.contains(post.authorId)) {
        _followingUsers.remove(post.authorId);
      } else {
        _followingUsers.add(post.authorId);
      }
    });
  }

  String _keywordForPost(PostBaseDto post) {
    final raw = _rawPostById(post.id);
    final source = [
      raw?['title']?.toString() ?? '',
      raw?['body']?.toString() ?? '',
    ].where((e) => e.trim().isNotEmpty).join(' ');
    final tokens = source
        .split(RegExp(r'[^\\u4e00-\\u9fa5A-Za-z0-9_]+'))
        .map((e) => e.trim())
        .where((e) => e.length >= 2)
        .toList();
    return tokens.isEmpty ? '' : tokens.first;
  }

  @override
  Widget build(BuildContext context) {
    final posts = _buildFeed();
    final currentPost = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)];
    final progress = _innerProgress(posts);
    return GestureDetector(
      behavior: HitTestBehavior.deferToChild,
      onTap: () {
        if (!widget.showWorksToolbar) widget.onHideSystemNav?.call();
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            child: PageView.builder(
              controller: _pageController,
              scrollDirection: Axis.vertical,
              physics: const PageScrollPhysics(),
              itemCount: posts.isEmpty ? 1 : posts.length,
              onPageChanged: (index) {
                if (_currentPage != index) {
                  // Flush dwell time for the previous post
                  final prevPost =
                      posts[_currentPage.clamp(0, posts.length - 1)];
                  _flushDwell(prevPost);

                  setState(() => _currentPage = index);
                  // Reset + restart the follow-button timer for the new post.
                  final newPost = posts[index.clamp(0, posts.length - 1)];
                  _startFollowButtonTimer(newPost);
                  _trackImpressionForPost(newPost);
                  _pageEnterTime = DateTime.now();
                }
              },
              itemBuilder: (context, index) {
                if (posts.isEmpty) {
                  return Center(
                    child: CircularProgressIndicator(
                      color: AppColors.worksAccent,
                    ),
                  );
                }
                return _buildPostCanvas(posts[index]);
              },
            ),
          ),

          if (_isFilterExpanded)
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: _collapseFilterPanel,
                child: const SizedBox.expand(),
              ),
            ),

          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _WorksPrimaryTopBar(
                    isFilterExpanded: _isFilterExpanded,
                    onTapMore: () => _showWorksMoreSheet(context),
                    onTapWorksArrow: _toggleFilterPanel,
                    onTapFollowing: widget.onSwitchToFollowing,
                    onTapCircles: widget.onSwitchToCircles,
                  ),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 420),
                    switchInCurve: Curves.elasticOut,
                    switchOutCurve: Curves.easeInCubic,
                    transitionBuilder: (child, animation) => SizeTransition(
                      sizeFactor: animation,
                      axisAlignment: -1,
                      child: FadeTransition(opacity: animation, child: child),
                    ),
                    child: _isFilterExpanded
                        ? _WorksSecondaryFilterBar(
                            key: const ValueKey<String>('works-filter-open'),
                            activeFilter: _filterType,
                            onFilterChange: _applyFilter,
                          )
                        : const SizedBox.shrink(
                            key: ValueKey<String>('works-filter-close'),
                          ),
                  ),
                ],
              ),
            ),
          ),

          if (currentPost != null && progress.total > 1)
            Positioned(
              left: AppSpacing.containerLg,
              right: AppSpacing.containerLg,
              bottom: _toolbarReservedHeight + AppSpacing.containerSm,
              child: Center(
                child: _WorksCapsuleIndicator(
                  total: progress.total,
                  current: progress.current,
                ),
              ),
            ),

          if (currentPost != null && widget.showWorksToolbar)
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: ImmersiveEngagementBar(
                avatarUrl: currentPost.avatarUrl,
                displayName: currentPost.displayName,
                circleName: _circleNameForPost(currentPost),
                likeCount:
                    currentPost.likeCount +
                    (_likedPosts.contains(currentPost.id) ? 1 : 0),
                shareCount:
                    currentPost.shareCount +
                    (_shareCountDelta[currentPost.id] ?? 0),
                favoriteCount:
                    currentPost.favoriteCount +
                    (_savedPosts.contains(currentPost.id) ? 1 : 0),
                commentCount: currentPost.commentCount,
                isLiked: _likedPosts.contains(currentPost.id),
                isSaved: _savedPosts.contains(currentPost.id),
                isFollowing: _followingUsers.contains(currentPost.authorId),
                showFollowButton: _showFollowButton,
                onUserTap: () => widget.onUserTap(
                  currentPost.authorId,
                  avatarUrl: currentPost.avatarUrl,
                  displayName: currentPost.displayName,
                  backgroundUrl: currentPost.authorBackgroundUrl,
                ),
                onCircleTap: () => context.push(
                  AppRoutePaths.circleDetail(id: _circleIdForPost(currentPost)),
                ),
                onFollowTap: () => _onFollow(currentPost),
                onLikeTap: () => _onLike(currentPost),
                onFavoriteTap: () => _onFavorite(currentPost),
                onCommentTap: () => _openCommentFor(context, currentPost.id),
                onShareTap: () => _sharePost(
                  context,
                  currentPost,
                  enableIdentityTemplate: ref.read(
                    contentFeatureFlagProvider(
                      'enable_identity_share_template',
                    ),
                  ),
                ),
                onRevealSystemNav: widget.onRevealSystemNav,
                formatCount: _formatCount,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPostCanvas(PostBaseDto post) {
    return _buildTypedCanvas(post);
  }

  Widget _buildTypedCanvas(PostBaseDto post) {
    if (post is PhotoPostDto) {
      return _WorksPhotoCanvas(
        post: post,
        onImageChanged: (index) =>
            setState(() => _photoInnerIndex[post.id] = index),
      );
    }
    if (post is VideoPostDto) {
      final episodes = _videoEpisodesForCurrent(post, _buildFeed());
      return _WorksVideoCanvas(
        post: post,
        episodes: episodes,
        onEpisodeChanged: (idx) =>
            setState(() => _videoInnerIndex[post.id] = idx),
      );
    }
    if (post is ArticlePostDto) {
      final cards = _articleCardsForPost(post.id);
      return _WorksArticleCanvas(
        post: post,
        cards: cards,
        onPageChanged: (index) =>
            setState(() => _articleInnerIndex[post.id] = index),
      );
    }
    return Container(color: AppColors.worksBackground);
  }

  void _openCommentFor(BuildContext ctx, String postId) {
    CommentViewer.showModal(context: ctx, postId: postId);
  }

  void _sharePost(
    BuildContext ctx,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    final template = _buildShareTemplate(
      post: post,
      enableIdentityTemplate: enableIdentityTemplate,
    );
    ContentShareSheet.show(
      ctx,
      template: template,
      onActionCompleted: (result) async {
        _recordShare(post.id, result.actionId);
      },
    );
  }

  Future<void> _copyLink(
    BuildContext context,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _buildShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      const ContentShareAction(
        id: 'copy_link',
        label: UITextConstants.copyLink,
      ),
    );
    if (result.success) {
      _recordShare(post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final raw = _rawPostById(post.id);
    final visibility = raw?['visibility']?.toString() ?? 'public';
    final tags =
        (raw?['tags'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    return ContentShareTemplateBuilder.build(
      post: post,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
      tags: tags,
      circleNames: <String>[_circleNameForPost(post)],
    );
  }

  void _recordShare(String postId, String actionId) {
    setState(() {
      _shareCountDelta[postId] = (_shareCountDelta[postId] ?? 0) + 1;
    });
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }
}

class _WorksPrimaryTopBar extends StatelessWidget {
  const _WorksPrimaryTopBar({
    required this.isFilterExpanded,
    required this.onTapWorksArrow,
    this.onTapClose,
    this.onTapMore,
    this.onTapFollowing,
    this.onTapCircles,
  });

  final bool isFilterExpanded;
  final VoidCallback onTapWorksArrow;
  final VoidCallback? onTapClose;
  final VoidCallback? onTapMore;
  final VoidCallback? onTapFollowing;
  final VoidCallback? onTapCircles;

  @override
  Widget build(BuildContext context) {
    // Height is pinned to tabNavigationHeight (48px) — identical to
    // _DiscoveryPage._buildHeader — so tabs never jump vertically on switch.

    // Responsive font size and tab gap follow the same breakpoints used by
    // AppTypography.responsive / AppSpacing.responsiveValue everywhere else:
    //   compact  < 360 px → lg (16px) / gap 16px
    //   regular  360–599  → xl (18px) / gap 24px
    //   expanded ≥ 600 px → xxl(20px) / gap 32px
    final tabFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.base,
      regular: AppTypography.lg,
      expanded: AppTypography.xl,
    );
    final tabGap = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.interGroupSm,
      regular: AppSpacing.interGroupMd,
      expanded: AppSpacing.interGroupLg,
    );

    return SizedBox(
      height: AppSpacing.tabNavigationHeight,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        child: Stack(
          children: [
            Positioned.fill(
              child: Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Following (Left)
                    GestureDetector(
                      onTap: onTapFollowing,
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        UITextConstants.homeTabFollowing,
                        style: TextStyle(
                          color: AppColors.worksBodyText.withValues(
                            alpha: 0.74,
                          ),
                          fontSize: tabFontSize,
                          fontWeight: AppTypography.bold,
                        ),
                      ),
                    ),
                    
                    // Gap
                    SizedBox(width: tabGap),
                    
                    // Featured (Center, with optional arrow if needed, but text is key)
                    GestureDetector(
                      onTap: onTapWorksArrow,
                      behavior: HitTestBehavior.opaque,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Invisible counter-weight spacer to balance the arrow
                          SizedBox(
                            width: AppSpacing.iconSmall + 2 + AppSpacing.intraGroupXs / 2,
                          ),
                          Text(
                            UITextConstants.homeTabFeatured,
                            style: TextStyle(
                              color: AppColors.worksTitle,
                              fontSize: tabFontSize,
                              fontWeight: AppTypography.bold,
                            ),
                          ),
                          // Keep arrow for filter toggling
                          const SizedBox(width: AppSpacing.intraGroupXs / 2),
                          SizedBox(
                            width: AppSpacing.iconSmall + 2,
                            child: Icon(
                              isFilterExpanded
                                  ? Icons.keyboard_arrow_up
                                  : Icons.keyboard_arrow_down,
                              color: AppColors.worksBodyText.withValues(
                                alpha: 0.8,
                              ),
                              size: AppSpacing.iconSmall + 1,
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                    // Gap
                    SizedBox(width: tabGap),
                    
                    // Circles (Right)
                    GestureDetector(
                      onTap: onTapCircles,
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        UITextConstants.homeTabCircles,
                        style: TextStyle(
                          color: AppColors.worksBodyText.withValues(
                            alpha: 0.74,
                          ),
                          fontSize: tabFontSize,
                          fontWeight: AppTypography.bold,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            
            // More Button (Right)
            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: SizedBox(
                  width: AppSpacing.iconButtonMinSizeSm,
                  child: IconButton(
                    onPressed: onTapMore,
                    icon: Icon(
                      Icons.more_horiz_rounded,
                      color: AppColors.worksBodyText,
                      size: AppSpacing.iconMedium,
                    ),
                    style: IconButton.styleFrom(
                      minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WorksSecondaryFilterBar extends StatelessWidget {
  const _WorksSecondaryFilterBar({
    super.key,
    required this.activeFilter,
    required this.onFilterChange,
  });

  final String? activeFilter;
  final void Function(String?) onFilterChange;

  @override
  Widget build(BuildContext context) {
    final filters = ContentUIConfig.workFormatFilters;
    return Align(
      alignment: Alignment.center,
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.intraGroupSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            decoration: BoxDecoration(
              color: AppColors.worksDrawerBg.withValues(alpha: 0.54),
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
              border: Border.all(
                color: AppColors.worksBodyText.withValues(alpha: 0.22),
                width: AppSpacing.toolPanelItemBorderWidthUnselected,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: filters
                  .asMap()
                  .entries
                  .map((entry) {
                    final filter = entry.value;
                    final chip = _chip(
                      filter.contentType,
                      UITextConstants.contentLabelForKey(filter.labelKey),
                    );
                    if (entry.key == filters.length - 1) {
                      return chip;
                    }
                    return Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        chip,
                        SizedBox(width: AppSpacing.intraGroupSm),
                      ],
                    );
                  })
                  .toList(growable: false),
            ),
          ),
        ),
      ),
    );
  }

  Widget _chip(String? type, String label) {
    final selected = activeFilter == type;
    return GestureDetector(
      onTap: () => onFilterChange(type),
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.worksTitle.withValues(alpha: 0.14)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
          border: Border.all(
            color: selected
                ? AppColors.worksTitle.withValues(alpha: 0.5)
                : AppColors.worksBodyText.withValues(alpha: 0.2),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.base,
            color: selected ? AppColors.worksTitle : AppColors.worksBodyText,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
    );
  }
}

class _WorksPhotoCanvas extends StatefulWidget {
  const _WorksPhotoCanvas({required this.post, required this.onImageChanged});

  final PhotoPostDto post;
  final void Function(int index) onImageChanged;

  @override
  State<_WorksPhotoCanvas> createState() => _WorksPhotoCanvasState();
}

class _WorksPhotoCanvasState extends State<_WorksPhotoCanvas> {
  late final PageController _imgController;

  @override
  void initState() {
    super.initState();
    _imgController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      widget.onImageChanged(0);
    });
  }

  @override
  void dispose() {
    _imgController.dispose();
    super.dispose();
  }

  List<String> get _images {
    if (widget.post.imageUrls.isNotEmpty) return widget.post.imageUrls;
    if (widget.post.coverUrl.isNotEmpty) return <String>[widget.post.coverUrl];
    return const <String>[];
  }

  // ── Horizontal gesture handlers ───────────────────────────────────────────
  // The photo canvas lives inside an outer *vertical* PageView. Flutter's
  // gesture arena separates vertical vs. horizontal recognisers, but the
  // overlay DecoratedBox (full-screen, no child) can still introduce hit-test
  // timing ambiguity in some runtime conditions. To guarantee reliable swipe:
  //   1. Outer GestureDetector (opaque) explicitly owns horizontal drags.
  //   2. It drives _imgController directly so the page follows the finger.
  //   3. Inner PageView uses NeverScrollableScrollPhysics — no gesture
  //      competition from a second HorizontalDragGestureRecognizer.
  //   4. The gradient overlay is wrapped in IgnorePointer so it is fully
  //      removed from hit-test consideration.

  void _onHorizontalDragUpdate(DragUpdateDetails details) {
    final images = _images;
    if (images.length <= 1) return;
    final pageWidth = MediaQuery.of(context).size.width;
    final maxOffset = (images.length - 1) * pageWidth;
    _imgController.jumpTo(
      (_imgController.offset - details.delta.dx).clamp(0.0, maxOffset),
    );
  }

  void _onHorizontalDragEnd(DragEndDetails details) {
    final images = _images;
    if (images.length <= 1) return;
    final velocity = details.primaryVelocity ?? 0;
    final currentPage = _imgController.page ?? 0;
    final int targetPage;
    if (velocity < -500) {
      targetPage = (currentPage.round() + 1).clamp(0, images.length - 1);
    } else if (velocity > 500) {
      targetPage = (currentPage.round() - 1).clamp(0, images.length - 1);
    } else {
      targetPage = currentPage.round().clamp(0, images.length - 1);
    }
    _imgController.animateToPage(
      targetPage,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    final images = _images;
    final multiImage = images.length > 1;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onHorizontalDragUpdate: multiImage ? _onHorizontalDragUpdate : null,
      onHorizontalDragEnd: multiImage ? _onHorizontalDragEnd : null,
      child: Stack(
        fit: StackFit.expand,
        children: [
          PageView.builder(
            controller: _imgController,
            // NeverScrollableScrollPhysics — gestures handled by the outer
            // GestureDetector above; this removes the second competing
            // HorizontalDragGestureRecognizer from the arena entirely.
            physics: const NeverScrollableScrollPhysics(),
            itemCount: images.isEmpty ? 1 : images.length,
            onPageChanged: (i) {
              widget.onImageChanged(i);
            },
            itemBuilder: (context, i) {
              if (images.isEmpty)
                return Container(color: AppColors.worksBackground);
              return CachedNetworkImage(
                imageUrl: images[i],
                fit: BoxFit.cover,
                placeholder: (context, url) =>
                    Container(color: AppColors.worksBackground),
                errorWidget: (context, url, error) =>
                    Container(color: AppColors.worksBackground),
              );
            },
          ),
          Positioned.fill(
            // IgnorePointer removes the gradient box from hit testing entirely,
            // so it can never compete with the GestureDetector above.
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withValues(alpha: 0.06),
                      Colors.black.withValues(alpha: 0.58),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WorksVideoCanvas extends StatefulWidget {
  const _WorksVideoCanvas({
    required this.post,
    required this.episodes,
    required this.onEpisodeChanged,
  });

  final VideoPostDto post;
  final List<VideoPostDto> episodes;
  final ValueChanged<int> onEpisodeChanged;

  @override
  State<_WorksVideoCanvas> createState() => _WorksVideoCanvasState();
}

class _WorksVideoCanvasState extends State<_WorksVideoCanvas> {
  late final PageController _episodeController;

  int get _initialIndex {
    final idx = widget.episodes.indexWhere((e) => e.id == widget.post.id);
    return idx < 0 ? 0 : idx;
  }

  @override
  void initState() {
    super.initState();
    _episodeController = PageController(initialPage: _initialIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onEpisodeChanged(_initialIndex);
    });
  }

  @override
  void dispose() {
    _episodeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final episodes = widget.episodes.isEmpty
        ? <VideoPostDto>[widget.post]
        : widget.episodes;
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _episodeController,
          scrollDirection: Axis.horizontal,
          itemCount: episodes.length,
          onPageChanged: widget.onEpisodeChanged,
          itemBuilder: (context, index) {
            final episode = episodes[index];
            if (episode.thumbnailUrl.isNotEmpty) {
              return CachedNetworkImage(
                imageUrl: episode.thumbnailUrl,
                fit: BoxFit.cover,
                placeholder: (context, url) =>
                    Container(color: AppColors.worksBackground),
                errorWidget: (context, url, error) =>
                    Container(color: AppColors.worksBackground),
              );
            }
            return Container(color: AppColors.worksBackground);
          },
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.08),
                  Colors.black.withValues(alpha: 0.62),
                ],
              ),
            ),
          ),
        ),
        Center(
          child: Container(
            width: AppSpacing.largeButtonSize,
            height: AppSpacing.largeButtonSize,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              shape: BoxShape.circle,
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.5),
                width: AppSpacing.toolPanelItemBorderWidthSelected,
              ),
            ),
            child: Icon(
              CupertinoIcons.play_fill,
              color: Colors.white.withValues(alpha: 0.9),
              size: AppSpacing.iconLarge,
            ),
          ),
        ),
      ],
    );
  }
}

class _WorksArticleCanvas extends StatelessWidget {
  const _WorksArticleCanvas({
    required this.post,
    required this.cards,
    required this.onPageChanged,
  });

  final ArticlePostDto post;
  final List<Map<String, dynamic>> cards;
  final ValueChanged<int> onPageChanged;

  @override
  Widget build(BuildContext context) {
    final pages = <Map<String, dynamic>>[
      <String, dynamic>{'__guide__': true},
      ...cards,
    ];
    return Stack(
      fit: StackFit.expand,
      children: [
        Container(color: AppColors.worksBackground),
        if (post.coverUrl.isNotEmpty)
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
              child: CachedNetworkImage(
                imageUrl: post.coverUrl,
                fit: BoxFit.cover,
                placeholder: (context, url) =>
                    Container(color: AppColors.worksBackground),
                errorWidget: (context, url, error) =>
                    Container(color: AppColors.worksBackground),
              ),
            ),
          ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.08),
                  AppColors.worksBackground.withValues(alpha: 0.92),
                ],
              ),
            ),
          ),
        ),
        Positioned(
          left: AppSpacing.containerMd,
          right: AppSpacing.containerMd,
          top: MediaQuery.of(context).padding.top + AppSpacing.containerLg,
          bottom:
              _WorksImmersiveViewerState._toolbarReservedHeight +
              AppSpacing.containerMd,
          child: PageView.builder(
            itemCount: pages.length,
            onPageChanged: onPageChanged,
            itemBuilder: (context, index) {
              if (index == 0) {
                return _ArticleGuideCard(post: post);
              }
              final card = pages[index];
              final title = card['title']?.toString() ?? post.title;
              final body = card['body']?.toString() ?? post.body;
              return _ArticleReadingCard(
                title: title,
                body: body,
                imageUrl: card['imageUrl']?.toString(),
                caption: card['caption']?.toString(),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _WorksCapsuleIndicator extends StatelessWidget {
  const _WorksCapsuleIndicator({required this.total, required this.current});

  final int total;
  final int current;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        // 中性黑背景，避免 worksDrawerBg 海军蓝在暖色图片上产生色相冲突
        color: Colors.black.withValues(alpha: 0.26),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(total.clamp(1, 10), (i) {
          final selected = i == current - 1;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 260),
            curve: Curves.easeOutCubic,
            margin: EdgeInsets.symmetric(horizontal: AppSpacing.xs / 2),
            width: selected ? AppSpacing.containerSm : AppSpacing.intraGroupSm,
            height: AppSpacing.intraGroupSm,
            decoration: BoxDecoration(
              color: selected
                  ? AppColors.worksTitle.withValues(alpha: 0.72)
                  : AppColors.worksTitle.withValues(alpha: 0.32),
              borderRadius: BorderRadius.circular(AppSpacing.intraGroupSm),
            ),
          );
        }),
      ),
    );
  }
}

class _ArticleGuideCard extends StatelessWidget {
  const _ArticleGuideCard({required this.post});

  final ArticlePostDto post;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerLg),
      decoration: BoxDecoration(
        color: AppColors.worksDrawerBg.withValues(alpha: 0.74),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius + 4),
        border: Border.all(
          color: AppColors.worksBodyText.withValues(alpha: 0.16),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  post.title,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.xl + 4,
                    fontWeight: AppTypography.bold,
                    color: AppColors.worksTitle,
                    height: AppTypography.bodyLineHeight,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  post.body,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.medium,
                    color: AppColors.worksBodyText,
                    height: AppTypography.lineHeightRelaxed,
                    letterSpacing: 0.4,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          SizedBox(
            width: MediaQuery.of(context).size.width * 0.28,
            child: _GuideThumb(imageUrl: post.coverUrl),
          ),
        ],
      ),
    );
  }
}

class _GuideThumb extends StatelessWidget {
  const _GuideThumb({required this.imageUrl});

  final String imageUrl;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        boxShadow: [
          BoxShadow(
            color: AppColors.worksAccent.withValues(alpha: 0.22),
            blurRadius: 16,
            spreadRadius: 1,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: AspectRatio(
          aspectRatio: 3 / 4,
          child: imageUrl.isEmpty
              ? Container(color: AppColors.worksBackground)
              : CachedNetworkImage(
                  imageUrl: imageUrl,
                  fit: BoxFit.cover,
                  placeholder: (context, url) =>
                      Container(color: AppColors.worksBackground),
                  errorWidget: (context, url, error) =>
                      Container(color: AppColors.worksBackground),
                ),
        ),
      ),
    );
  }
}

class _ArticleReadingCard extends StatelessWidget {
  const _ArticleReadingCard({
    required this.title,
    required this.body,
    this.imageUrl,
    this.caption,
  });

  final String title;
  final String body;
  final String? imageUrl;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.worksDrawerBg.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(
          color: AppColors.worksBodyText.withValues(alpha: 0.16),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.xl,
              color: AppColors.worksTitle,
              fontWeight: AppTypography.bold,
              height: AppTypography.bodyLineHeight,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          if ((imageUrl ?? '').isNotEmpty) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: CachedNetworkImage(
                  imageUrl: imageUrl!,
                  fit: BoxFit.cover,
                  placeholder: (context, url) =>
                      Container(color: AppColors.worksBackground),
                  errorWidget: (context, url, error) =>
                      Container(color: AppColors.worksBackground),
                ),
              ),
            ),
            if ((caption ?? '').isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                caption!,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: AppColors.worksCaption,
                  height: AppTypography.lineHeightRelaxed,
                ),
              ),
            ],
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          Expanded(
            child: Text(
              body,
              maxLines: 9,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: AppColors.worksBodyText,
                height: AppTypography.lineHeightRelaxed,
                letterSpacing: 0.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WorksBottomToolbar extends StatelessWidget {
  const _WorksBottomToolbar({
    required this.post,
    required this.circleName,
    required this.isLiked,
    required this.isSaved,
    required this.isFollowing,
    required this.showFollowButton,
    required this.onUserTap,
    required this.onCircleTap,
    required this.onFollowTap,
    required this.onLikeTap,
    required this.onFavoriteTap,
    required this.formatCount,
    this.onRevealSystemNav,
    this.onCommentTap,
    this.onShareTap,
  });

  final PostBaseDto post;
  final String circleName;
  final bool isLiked;
  final bool isSaved;
  final bool isFollowing;

  /// Whether the follow button has been "unlocked" for this post view.
  /// Managed by the parent timer: 3 s for photos, 5 s for video/article.
  /// Already-following authors skip the timer and show the button immediately.
  final bool showFollowButton;
  final VoidCallback onUserTap;
  final VoidCallback onCircleTap;
  final VoidCallback onFollowTap;
  final VoidCallback onLikeTap;
  final VoidCallback onFavoriteTap;
  final String Function(int n) formatCount;
  final VoidCallback? onRevealSystemNav;
  final VoidCallback? onCommentTap;
  final VoidCallback? onShareTap;

  static const double _kFollowBtnWidth = AppSpacing.followButtonWidthCompact;

  // ── Responsive action dimensions ────────────────────────────────────────
  // All three tiers align with AppSpacing.compactBreakpoint (360)
  // and AppSpacing.expandedBreakpoint (600), matching the existing
  // semantic breakpoint system used across the design system.

  /// Action cell width per tier:
  ///   compact  < 360 px → 40 px  (icon 24 px + 8 px each side)
  ///   regular  360–599  → 44 px  (icon 24 px + 10 px each side)
  ///   expanded ≥ 600 px → 52 px  (icon 24 px + 14 px each side)
  static double _cellWidth(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: 40.0,
    regular: 44.0,
    expanded: 52.0,
  );

  /// Gap between adjacent action icons:
  ///   compact  → intraGroupXs (4 px)
  ///   regular  → intraGroupSm (6 px)
  ///   expanded → intraGroupMd (8 px)
  static double _actionGap(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: AppSpacing.intraGroupXs,
    regular: AppSpacing.intraGroupSm,
    expanded: AppSpacing.intraGroupMd,
  );

  /// Gap between author area and action group (≈ actionGap × 1.33,
  /// one semantic step wider to signal cross-group boundary):
  ///   compact  → intraGroupSm  (6 px)
  ///   regular  → intraGroupMd  (8 px)
  ///   expanded → intraGroupLg  (12 px)
  static double _dividerGap(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: AppSpacing.intraGroupSm,
    regular: AppSpacing.intraGroupMd,
    expanded: AppSpacing.intraGroupLg,
  );

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    final cellWidth = _cellWidth(context);
    final actionGap = _actionGap(context);
    final divider = _dividerGap(context);

    // Text compression: triggered only when the follow CTA is newly appearing
    // AND the author is not yet followed.  Already-following shows immediately
    // with no layout shift (the muted chip is visually lighter).
    final compressText = showFollowButton && !isFollowing;

    return GestureDetector(
      onVerticalDragUpdate: (details) {
        if (details.delta.dy < -4) onRevealSystemNav?.call();
      },
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          child: Container(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
              AppSpacing.containerMd,
              AppSpacing.containerMd + bottomInset,
            ),
            color: AppColors.worksBackground.withValues(alpha: 0.88),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                // ── Author avatar ────────────────────────────────────────
                GestureDetector(
                  onTap: onUserTap,
                  behavior: HitTestBehavior.opaque,
                  child: CircleAvatar(
                    radius: AppSpacing.avatarUserMd * 0.5,
                    backgroundImage: post.avatarUrl.isNotEmpty
                        ? NetworkImage(post.avatarUrl)
                        : null,
                    backgroundColor: AppColors.worksCaption,
                  ),
                ),
                const SizedBox(width: AppSpacing.intraGroupSm),

                // ── Author info + optional follow button ─────────────────
                // Expanded absorbs all remaining space so the action group
                // is always right-anchored regardless of name length or
                // whether the follow button is visible.
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Name column — Flexible lets it shrink when the follow
                      // button occupies space.  AnimatedDefaultTextStyle
                      // smoothly scales both lines down when the follow CTA
                      // appears (only for non-following state).
                      //
                      // When the follow button is visible, long names are
                      // hidden by a right-side gradient fade (ShaderMask +
                      // TextOverflow.clip) instead of an ellipsis "..." so
                      // the text blends smoothly into the button.
                      Flexible(
                        child: showFollowButton
                            ? ShaderMask(
                                // Fixed 18 px fade at the right edge so the
                                // gradient stays proportional regardless of
                                // how narrow the name column gets.
                                shaderCallback: (bounds) {
                                  const fadeWidth = 18.0;
                                  final start =
                                      ((bounds.width - fadeWidth) /
                                              bounds.width)
                                          .clamp(0.0, 1.0);
                                  return LinearGradient(
                                    begin: Alignment.centerLeft,
                                    end: Alignment.centerRight,
                                    stops: [start, 1.0],
                                    colors: const [
                                      Colors.white,
                                      Colors.transparent,
                                    ],
                                  ).createShader(bounds);
                                },
                                blendMode: BlendMode.dstIn,
                                child: _nameColumn(
                                  compressText: compressText,
                                  clip: true,
                                ),
                              )
                            : _nameColumn(
                                compressText: compressText,
                                clip: false,
                              ),
                      ),

                      // Follow button — slides in from the RIGHT (near the
                      // action group) via AnimatedSize(alignment: centerRight).
                      // alignment: Alignment.centerRight anchors the right
                      // edge so the widget expands leftward, giving the
                      // visual impression the button emerges from near the
                      // action icons, not from behind the name text.
                      AnimatedSize(
                        duration: const Duration(milliseconds: 260),
                        curve: Curves.easeOutCubic,
                        alignment: Alignment.centerRight,
                        child: showFollowButton
                            ? Padding(
                                padding: const EdgeInsets.only(
                                  left: AppSpacing.intraGroupSm,
                                ),
                                child: GestureDetector(
                                  onTap: onFollowTap,
                                  behavior: HitTestBehavior.opaque,
                                  child: Container(
                                    width: _kFollowBtnWidth,
                                    height: AppSpacing.buttonHeightXs,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: isFollowing
                                          ? AppColors.followingButtonOnDark
                                          : AppColors.worksAccent,
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.circularBorderRadius,
                                      ),
                                    ),
                                    child: Text(
                                      isFollowing
                                          ? UITextConstants.following
                                          : '+${UITextConstants.follow}',
                                      style: TextStyle(
                                        color: isFollowing
                                            ? AppColors.worksBodyText
                                                  .withValues(alpha: 0.72)
                                            : AppColors.white,
                                        fontSize: AppTypography.xs,
                                        fontWeight: AppTypography.semiBold,
                                      ),
                                    ),
                                  ),
                                ),
                              )
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ),
                ),

                // ── Responsive cross-group divider ───────────────────────
                SizedBox(width: divider),

                // ── Action group — responsive cell width + gap ───────────
                // The group width is calculated from context once per build
                // and is identical for every post on a given device →
                // actions never shift between posts.
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _action(
                      icon: Icon(
                        isLiked
                            ? CupertinoIcons.heart_fill
                            : CupertinoIcons.heart,
                        color: isLiked
                            ? AppColors.worksLike
                            : AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCount(post.likeCount + (isLiked ? 1 : 0)),
                      onTap: onLikeTap,
                      cellWidth: cellWidth,
                    ),
                    SizedBox(width: actionGap),
                    _action(
                      icon: Icon(
                        CupertinoIcons.arrowshape_turn_up_right,
                        color: AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCount(post.shareCount),
                      onTap: onShareTap,
                      cellWidth: cellWidth,
                    ),
                    SizedBox(width: actionGap),
                    _action(
                      icon: Icon(
                        isSaved
                            ? CupertinoIcons.star_fill
                            : CupertinoIcons.star,
                        color: isSaved
                            ? AppColors.worksSave
                            : AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCount(
                        post.favoriteCount + (isSaved ? 1 : 0),
                      ),
                      onTap: onFavoriteTap,
                      cellWidth: cellWidth,
                    ),
                    SizedBox(width: actionGap),
                    _action(
                      icon: Icon(
                        CupertinoIcons.chat_bubble,
                        color: AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCount(post.commentCount),
                      onTap: onCommentTap,
                      cellWidth: cellWidth,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Name + circle-name column with responsive font sizes.
  /// [clip] = true when the ShaderMask parent handles overflow visually;
  ///          TextOverflow.clip avoids the "..." appearing under the fade.
  Widget _nameColumn({required bool compressText, required bool clip}) {
    final overflow = clip ? TextOverflow.clip : TextOverflow.ellipsis;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedDefaultTextStyle(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          style: TextStyle(
            color: AppColors.worksTitle,
            fontSize: compressText ? AppTypography.sm : AppTypography.base,
            fontWeight: AppTypography.bold,
          ),
          child: Text(post.displayName, maxLines: 1, overflow: overflow),
        ),
        SizedBox(height: AppSpacing.intraGroupXs / 2),
        AnimatedDefaultTextStyle(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          style: TextStyle(
            color: AppColors.worksBodyText.withValues(alpha: 0.72),
            fontSize: compressText ? AppTypography.xxs : AppTypography.xs,
            fontWeight: AppTypography.medium,
          ),
          child: GestureDetector(
            onTap: onCircleTap,
            behavior: HitTestBehavior.opaque,
            child: Text(circleName, maxLines: 1, overflow: overflow),
          ),
        ),
      ],
    );
  }

  Widget _action({
    required Widget icon,
    required String label,
    required double cellWidth,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: cellWidth,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            icon,
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              label,
              style: TextStyle(
                color: AppColors.worksBodyText,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
