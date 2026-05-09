// ignore_for_file: unnecessary_non_null_assertion, unused_element, unused_element_parameter
import 'dart:async';
import 'dart:math' show max;
import 'dart:ui' show ImageFilter;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/article_reader_observability.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/post_read_projection_facade.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

class WorksImmersiveViewer extends ConsumerStatefulWidget {
  const WorksImmersiveViewer({
    super.key,
    required this.showWorksToolbar,
    required this.onUserTap,
    required this.onAssistantTap,
    this.onTapBack,
    this.onSwitchToFollowing,
    this.onSwitchToCircles,
    this.onSwitchToMoment, // Deprecated/Fallback
    this.onRevealSystemNav,
    this.onHideSystemNav,
    this.showTopNavigation = true,
    this.externalPosts,
    this.externalPostViews,
    this.initialPostIndex = 0,
    this.initialImageIndex = 0,
    this.source = 'featured',
    this.rawPostsById = const <String, MediaViewerPostWireRow>{},
    this.defaultCircleId,
    this.initialInteractionSnapshot = const MediaViewerInteractionSnapshot(),
    this.onDismissed,
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
  final VoidCallback? onTapBack;
  final VoidCallback? onSwitchToFollowing;
  final VoidCallback? onSwitchToCircles;
  final VoidCallback? onSwitchToMoment;
  final VoidCallback? onRevealSystemNav;
  final VoidCallback? onHideSystemNav;
  final bool showTopNavigation;
  final List<PostBaseDto>? externalPosts;
  final List<PostSummaryView>? externalPostViews;
  final int initialPostIndex;
  final int initialImageIndex;
  final String source;
  final Map<String, MediaViewerPostWireRow> rawPostsById;
  final String? defaultCircleId;
  final MediaViewerInteractionSnapshot initialInteractionSnapshot;
  final ValueChanged<MediaViewerResult>? onDismissed;

  @override
  ConsumerState<WorksImmersiveViewer> createState() =>
      _WorksImmersiveViewerState();
}

class _WorksImmersiveViewerState extends ConsumerState<WorksImmersiveViewer>
    with TickerProviderStateMixin {
  static bool _didAutoExpandInSession = false;
  static const double _toolbarReservedHeight =
      ImmersiveEngagementBar.preferredReservedHeight;

  String? _filterType;
  bool _isFilterExpanded = false;
  int _currentPage = 0;
  final Map<String, int> _photoInnerIndex = <String, int>{};
  final Map<String, int> _articleInnerIndex = <String, int>{};
  final Map<String, int> _videoInnerIndex = <String, int>{};
  final Set<String> _expandedCaptionPostIds = <String>{};

  // Dwell tracking：记录当前帖子进入时间
  DateTime? _pageEnterTime;
  final DateTime _viewerOpenedAt = DateTime.now();
  final Map<String, Map<String, Object?>> _hydratedRawPostsById =
      <String, Map<String, Object?>>{};
  final Set<String> _hydratingArticleIds = <String>{};

  Timer? _autoCollapseTimer;
  // Follow-button delayed reveal: 3 s for photos, 5 s for video/article.
  Timer? _followButtonTimer;
  bool _showFollowButton = false;

  late final PageController _pageController;

  @override
  void initState() {
    super.initState();
    final initialPage = _safeInitialPage;
    _currentPage = initialPage;
    _pageController = PageController(initialPage: initialPage);
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (mounted) {
        primeMediaViewerInteractionSnapshot(
          ref,
          widget.initialInteractionSnapshot,
        );
      }
      if (!_usesExternalFeed) {
        for (final tabId in <String>['photo', 'video', 'article']) {
          final feedMap = ref.read(discoveryFeedMapProvider);
          if (!feedMap.containsKey(tabId)) {
            ref.read(discoveryFeedMapProvider.notifier).load(tabId);
          }
        }
      }
      if (widget.showTopNavigation) {
        _runOneTimeAutoExpand();
      }
      // Kick off the follow-button timer for the first visible post.
      final posts = _buildFeed();
      if (posts.isNotEmpty) {
        final initialIndex = _currentPage.clamp(0, posts.length - 1);
        _startFollowButtonTimer(posts[initialIndex]);
        // Track impression for the first post
        _trackImpressionForPost(posts[initialIndex]);
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

  bool get _usesExternalFeed =>
      widget.externalPosts != null && widget.externalPosts!.isNotEmpty;

  int get _safeInitialPage {
    if (_usesExternalFeed) {
      return widget.initialPostIndex.clamp(0, widget.externalPosts!.length - 1);
    }
    return 0;
  }

  MediaViewerResult _buildResult() {
    final posts = _buildFeed();
    final postsById = <String, PostBaseDto>{
      for (final post in posts) post.id: post,
    };
    final scopePostIds =
        widget.initialInteractionSnapshot.effectiveScopePostIds;
    final scopeProfileIds =
        widget.initialInteractionSnapshot.effectiveScopeProfileIds;
    final postInteractionState = ref.read(postInteractionStateProvider);
    final relationshipState = ref.read(userRelationshipStateProvider);
    return MediaViewerResult(
      scopePostIds: Set<String>.from(scopePostIds),
      scopeProfileIds: Set<String>.from(scopeProfileIds),
      followingUsers: {
        for (final profileId in scopeProfileIds)
          if (relationshipState.isFollowing(profileId)) profileId,
      },
      savedPosts: {
        for (final postId in scopePostIds)
          if (postInteractionState.isSaved(postId)) postId,
      },
      likedPosts: {
        for (final postId in scopePostIds)
          if (postInteractionState.isLiked(postId)) postId,
      },
      postLikesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.likeCountFor(
            postId,
            fallback: postsById[postId]?.likeCount ?? 0,
          ),
      },
      postBookmarksCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.bookmarkCountFor(
            postId,
            fallback: postsById[postId]?.favoriteCount ?? 0,
          ),
      },
      postSharesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.shareCountFor(
            postId,
            fallback: postsById[postId]?.shareCount ?? 0,
          ),
      },
      postCommentCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.commentCountFor(
            postId,
            fallback: postsById[postId]?.commentCount ?? 0,
          ),
      },
    );
  }

  void _dismissViewer() {
    final result = _buildResult();
    if (widget.onDismissed != null) {
      widget.onDismissed!(result);
      return;
    }
    widget.onTapBack?.call();
  }

  /// Resets follow-button visibility and starts the appropriate reveal strategy:
  /// - Already following: show immediately (state is established, no discovery needed).
  /// - Not following: delayed reveal — 3 s for photos, 5 s for video / article.
  void _startFollowButtonTimer(PostBaseDto post) {
    _followButtonTimer?.cancel();
    if (effectiveProfileFollowing(ref, post.subAccountId)) {
      // Already following → show right away, no animation delay.
      if (!_showFollowButton) setState(() => _showFollowButton = true);
      return;
    }
    if (_showFollowButton) setState(() => _showFollowButton = false);
    final delay = post.displayFormat == 'image'
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
    if (_usesExternalFeed) {
      final external = widget.externalPosts!;
      if (_filterType == 'image') {
        return external.where(_isImageLikePost).toList(growable: false);
      }
      if (_filterType == 'video') {
        return external.where(_isVideoLikePost).toList(growable: false);
      }
      if (_filterType == 'article') {
        return external
            .where(
              (post) => _isArticleLikePost(post) || _isTextOnlyMomentPost(post),
            )
            .toList(growable: false);
      }
      return external;
    }
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

  bool _hasStructuredArticlePayload(Map<String, Object?>? raw) {
    if (raw == null) {
      return false;
    }
    if ((raw[ArticleDetailWireKeys.articleMarkdown]?.toString().trim() ?? '')
        .isNotEmpty) {
      return true;
    }
    if (raw[ArticleDetailWireKeys.articleBlocks] is List &&
        (raw[ArticleDetailWireKeys.articleBlocks] as List).isNotEmpty) {
      return true;
    }
    if (raw[ArticleDetailWireKeys.cards] is List &&
        (raw[ArticleDetailWireKeys.cards] as List).isNotEmpty) {
      return true;
    }
    return false;
  }

  Map<String, Object?>? _effectiveRawPostById(String postId) {
    return _hydratedRawPostsById[postId] ?? _rawPostById(postId);
  }

  Map<String, Object?> _rawArticleDataFor(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final hasStructuredPayload = _hasStructuredArticlePayload(raw);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    final rawBody = raw?['body']?.toString().trim() ?? '';
    return <String, Object?>{
      ...?raw,
      'postId': post.id,
      'type': (raw?['type'] ?? raw?['contentType'] ?? 'article').toString(),
      'contentType': (raw?['contentType'] ?? raw?['type'] ?? 'article')
          .toString(),
      'authorId': (raw?['authorId'] ?? post.authorId).toString(),
      'displayName':
          (raw?['displayName'] ?? raw?['authorNickname'] ?? post.displayName)
              .toString(),
      'authorAvatarUrl': (raw?['authorAvatarUrl'] ?? post.avatarUrl).toString(),
      'title': rawTitle.isNotEmpty
          ? rawTitle
          : (hasStructuredPayload ? '' : post.title),
      'body': rawBody.isNotEmpty
          ? rawBody
          : (hasStructuredPayload ? '' : post.body),
      'coverUrl': (raw?[ArticleDetailWireKeys.coverUrl] ?? post.coverUrl)
          .toString(),
      'thumbnailUrl': (raw?['thumbnailUrl'] ?? post.thumbnailUrl).toString(),
      'mediaUrls': raw?['mediaUrls'] ?? post.imageUrls,
      'likeCount': raw?['likeCount'] ?? post.likeCount,
      'commentCount': raw?['commentCount'] ?? post.commentCount,
      'favoriteCount': raw?['favoriteCount'] ?? post.favoriteCount,
      'shareCount': raw?['shareCount'] ?? post.shareCount,
      'createdAt': raw?['createdAt'] ?? post.createdAt,
    };
  }

  ArticleDetailView _articleViewFor(PostBaseDto post) {
    return projectArticleDetailView(
      Map<String, dynamic>.from(_rawArticleDataFor(post)),
      fallbackArticleId: post.id,
    );
  }

  int _articlePageCount(PostBaseDto post) {
    return _articleViewFor(post).pages.length.clamp(1, 99);
  }

  ({int current, int total}) _innerProgress(List<PostBaseDto> posts) {
    if (posts.isEmpty) return (current: 1, total: 1);
    final idx = _currentPage.clamp(0, posts.length - 1);
    final current = posts[idx];
    if (_isImageLikePost(current)) {
      final imageUrls = _imageUrlsForPost(current);
      final total = imageUrls.isEmpty ? 1 : imageUrls.length;
      final currentIndex =
          (_photoInnerIndex[current.id] ?? _defaultImageIndexFor(current))
              .clamp(0, total - 1) +
          1;
      return (current: currentIndex, total: total);
    }
    if (_isArticleLikePost(current)) {
      final total = _articlePageCount(current);
      final currentCard =
          (_articleInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentCard, total: total);
    }
    if (_isTextOnlyMomentPost(current)) {
      return (current: 1, total: 1);
    }
    if (_isVideoLikePost(current)) {
      final episodes = _videoEpisodesForCurrent(current, posts);
      final total = episodes.length.clamp(1, 99);
      final currentEpisode =
          (_videoInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentEpisode, total: total);
    }
    return (current: 1, total: 1);
  }

  bool _isVideoLikePost(PostBaseDto post) {
    return post.isVideoLike;
  }

  bool _isArticleLikePost(PostBaseDto post) {
    return post.isArticleLike;
  }

  bool _isTextOnlyMomentPost(PostBaseDto post) {
    return post.identity == 'moment' && post.isTextOnly;
  }

  bool _isImageLikePost(PostBaseDto post) {
    if (_isVideoLikePost(post) ||
        _isArticleLikePost(post) ||
        _isTextOnlyMomentPost(post)) {
      return false;
    }
    return _imageUrlsForPost(post).isNotEmpty;
  }

  bool get _canSwipePrimaryTabs =>
      widget.showTopNavigation &&
      (widget.onSwitchToFollowing != null ||
          widget.onSwitchToCircles != null ||
          widget.onSwitchToMoment != null);

  void _switchToPreviousPrimaryTab() {
    if (widget.onSwitchToFollowing != null) {
      widget.onSwitchToFollowing!();
      return;
    }
    widget.onSwitchToMoment?.call();
  }

  void _switchToNextPrimaryTab() {
    widget.onSwitchToCircles?.call();
  }

  void _handlePrimaryTabSwipe(TabSwipeDirection direction) {
    if (!_canSwipePrimaryTabs) {
      return;
    }
    if (direction == TabSwipeDirection.previous) {
      _switchToPreviousPrimaryTab();
      return;
    }
    _switchToNextPrimaryTab();
  }

  void _handlePrimaryTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handlePrimaryTabSwipe(direction);
  }

  List<String> _imageUrlsForPost(PostBaseDto post) {
    if (post.hasImages) return post.mediaImageUrls;
    if (post.primaryImageUrl.isNotEmpty) return <String>[post.primaryImageUrl];
    return const <String>[];
  }

  int _defaultImageIndexFor(PostBaseDto post) {
    if (!_usesExternalFeed) return 0;
    final initialPost = widget.externalPosts![_safeInitialPage];
    if (post.id != initialPost.id) return 0;
    final total = _imageUrlsForPost(post).length;
    if (total <= 1) return 0;
    return widget.initialImageIndex.clamp(0, total - 1);
  }

  List<PostBaseDto> _videoEpisodesForCurrent(
    PostBaseDto current,
    List<PostBaseDto> posts,
  ) {
    final episodes = posts
        .where(_isVideoLikePost)
        .where((v) => v.authorId == current.authorId)
        .toList(growable: false);
    if (episodes.isEmpty) return <PostBaseDto>[current];
    return episodes;
  }

  void _applyFilter(String? type) {
    setState(() {
      _filterType = type;
      _currentPage = 0;
      _pageController.jumpToPage(0);
    });
  }

  Map<String, Object?>? _rawPostById(String postId) {
    final external = widget.rawPostsById[postId];
    if (external != null) return external.toObjectMap();
    final wire = ref
        .read(contentRepositoryProvider)
        .discoveryPresentationWireForPost(postId);
    if (wire == null) return null;
    return Map<String, Object?>.from(wire);
  }

  PostSummaryView? _summaryForPost(String postId) {
    final external = widget.externalPostViews;
    if (external == null || external.isEmpty) return null;
    for (final item in external) {
      if (item.id == postId) return item;
    }
    return null;
  }

  Map<String, dynamic> _wireMapForPresentation(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    if (raw == null) {
      return post.toMap();
    }
    return Map<String, dynamic>.from(
      raw.map((k, v) => MapEntry(k.toString(), v)),
    );
  }

  String _titleForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    if (rawTitle.isNotEmpty) return rawTitle;
    final summary = _summaryForPost(post.id);
    final summaryTitle = summary?.readPresentation.title.trim() ?? '';
    if (summaryTitle.isNotEmpty) return summaryTitle;
    final pres = PostReadProjectionFacade.presentationFor(
      post,
      PostReadSurfaceId.immersive,
      wire: _wireMapForPresentation(post),
    );
    return pres.title.isNotEmpty ? pres.title : post.normalizedTitle;
  }

  String _bodyForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawBody =
        raw?['body']?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.description]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.content]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.caption]?.toString().trim() ??
        '';
    if (rawBody.isNotEmpty) return rawBody;
    final summary = _summaryForPost(post.id);
    final summaryBody = summary?.readPresentation.body.trim() ?? '';
    if (summaryBody.isNotEmpty) return summaryBody;
    final pres = PostReadProjectionFacade.presentationFor(
      post,
      PostReadSurfaceId.immersive,
      wire: _wireMapForPresentation(post),
    );
    return pres.body.isNotEmpty ? pres.body : post.normalizedBody;
  }

  String _overlayTitleForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _titleForPost(post);
  }

  String _overlayBodyForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _bodyForPost(post);
  }

  List<_PostCircleTarget> _circlesForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    if (raw == null) {
      if (widget.defaultCircleId != null &&
          widget.defaultCircleId!.isNotEmpty) {
        return <_PostCircleTarget>[
          _PostCircleTarget(id: widget.defaultCircleId!, name: '圈子'),
        ];
      }
      return const <_PostCircleTarget>[];
    }

    final summaries = raw[ContentPostImmersiveWireKeys.circleSummaries];
    if (summaries is List) {
      final resolved = summaries
          .whereType<Map>()
          .map(
            (item) => _PostCircleTarget(
              id: item['id']?.toString() ?? '',
              name: item['name']?.toString() ?? '',
            ),
          )
          .where((item) => item.id.isNotEmpty && item.name.isNotEmpty)
          .toList(growable: false);
      if (resolved.isNotEmpty) return resolved;
    }

    final circleIds =
        (raw[ContentPostImmersiveWireKeys.circleIds] as List?)
            ?.map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final circleNames =
        (raw[ContentPostImmersiveWireKeys.circleNames] as List?)
            ?.map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (circleIds.isNotEmpty) {
      return List<_PostCircleTarget>.generate(circleIds.length, (index) {
        final name = index < circleNames.length
            ? circleNames[index]
            : circleIds[index];
        return _PostCircleTarget(id: circleIds[index], name: name);
      });
    }

    final circleId =
        raw[ContentPostImmersiveWireKeys.circleId]?.toString() ??
        widget.defaultCircleId ??
        '';
    final circleName =
        raw[ContentPostImmersiveWireKeys.circleName]?.toString() ?? '';
    if (circleId.isNotEmpty) {
      return <_PostCircleTarget>[
        _PostCircleTarget(
          id: circleId,
          name: circleName.isNotEmpty ? circleName : '圈子$circleId',
        ),
      ];
    }
    return const <_PostCircleTarget>[];
  }

  Widget? _circleFooterForPost(BuildContext context, PostBaseDto post) {
    final circles = _circlesForPost(post);
    if (circles.isEmpty) return null;
    return Wrap(
      spacing: AppSpacing.intraGroupXs,
      runSpacing: AppSpacing.intraGroupXs,
      children: circles
          .map(
            (circle) => GestureDetector(
              onTap: () =>
                  context.push(AppRoutePaths.circleDetail(id: circle.id)),
              behavior: HitTestBehavior.opaque,
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.intraGroupSm,
                  vertical: AppSpacing.intraGroupXs / 2,
                ),
                decoration: BoxDecoration(
                  color: AppColors.black.withValues(alpha: 0.24),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
                  border: Border.all(
                    color: AppColors.white.withValues(alpha: 0.16),
                  ),
                ),
                child: Text(
                  circle.name,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.xs,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ),
            ),
          )
          .toList(growable: false),
    );
  }

  String? _topProgressLabelForPost(
    PostBaseDto post,
    ({int current, int total}) progress,
  ) {
    if (_isArticleLikePost(post)) {
      return '${progress.current}/${progress.total}';
    }
    if (!(_isImageLikePost(post) || _isVideoLikePost(post))) {
      return null;
    }
    if (progress.total <= 1) return null;
    return '${progress.current}/${progress.total}';
  }

  Widget? _overlayFooterForPost(BuildContext context, PostBaseDto post) {
    final circleFooter = _circleFooterForPost(context, post);
    return circleFooter;
  }

  bool _showsCaptionOverlay(PostBaseDto post) {
    return _overlayTitleForPost(post).isNotEmpty ||
        _overlayBodyForPost(post).isNotEmpty ||
        _circlesForPost(post).isNotEmpty;
  }

  ImmersiveViewerStageLayoutSpec _layoutSpecForPost(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  bool _isCaptionExpanded(String postId) {
    return _expandedCaptionPostIds.contains(postId);
  }

  void _toggleCaptionExpanded(String postId) {
    setState(() {
      if (_expandedCaptionPostIds.contains(postId)) {
        _expandedCaptionPostIds.remove(postId);
      } else {
        _expandedCaptionPostIds.add(postId);
      }
    });
  }

  String? _primaryCircleIdForPost(PostBaseDto post) {
    final circles = _circlesForPost(post);
    if (circles.isEmpty) return null;
    return circles.first.id;
  }

  // ── 行为追踪辅助 ──────────────────────────────────────────────

  void _trackImpressionForPost(PostBaseDto post) {
    final tracker = ref.read(contentBehaviorTrackerProvider);
    tracker.trackImpression(post.id);
    if (!_isArticleLikePost(post)) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    final article = _articleViewFor(post);
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderOpen(
          postId: post.id,
          durationMs: DateTime.now().difference(_viewerOpenedAt).inMilliseconds,
          source: widget.source,
          template: article.template.name,
          fontPreset: article.fontPreset.name,
          pageCount: article.pages.length.clamp(1, 99),
          bookReaderEnabled: bookReaderEnabled,
        );
    if (!bookReaderEnabled) {
      ref
          .read(articleReaderObservabilityProvider)
          .trackReaderFallback(
            postId: post.id,
            reason: 'feature_flag_disabled',
            bookReaderEnabled: false,
          );
    }
    _trackDocumentStructureFallback(
      post: post,
      article: article,
      hydrated: _hydratedRawPostsById.containsKey(post.id),
    );
    unawaited(_maybeHydrateArticleDetail(post));
  }

  String _documentSourceName(ArticleDetailDocumentSource source) {
    return switch (source) {
      ArticleDetailDocumentSource.markdown => 'markdown',
      ArticleDetailDocumentSource.articleBlocks => 'article_blocks',
      ArticleDetailDocumentSource.cards => 'cards',
      ArticleDetailDocumentSource.body => 'body',
      ArticleDetailDocumentSource.empty => 'empty',
    };
  }

  void _trackDocumentStructureFallback({
    required PostBaseDto post,
    required ArticleDetailView article,
    required bool hydrated,
  }) {
    if (article.documentSource == ArticleDetailDocumentSource.markdown) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason:
              'document_structure:${_documentSourceName(article.documentSource)}:hydrated=$hydrated',
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  Future<void> _maybeHydrateArticleDetail(PostBaseDto post) async {
    final raw = _effectiveRawPostById(post.id);
    if (_hasStructuredArticlePayload(raw) ||
        _hydratingArticleIds.contains(post.id)) {
      return;
    }
    _hydratingArticleIds.add(post.id);
    final startedAt = DateTime.now();
    try {
      final detail = await ref
          .read(contentRepositoryProvider)
          .getPost(postId: post.id);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      setState(() {
        _hydratedRawPostsById[post.id] = <String, Object?>{
          ...?raw,
          ...Map<String, Object?>.from(detail.mergedArticleWireMap),
        };
      });
      final hydratedArticle = _articleViewFor(post);
      _trackDocumentStructureFallback(
        post: post,
        article: hydratedArticle,
        hydrated: true,
      );
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'success',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } catch (_) {
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'error',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } finally {
      _hydratingArticleIds.remove(post.id);
    }
  }

  String _fallbackReasonName(ArticleReaderFallbackReason reason) {
    return switch (reason) {
      ArticleReaderFallbackReason.forcedDegradedPager =>
        'forced_degraded_pager',
      ArticleReaderFallbackReason.pageCurlDisabled => 'page_curl_disabled',
      ArticleReaderFallbackReason.accessibilityDisableAnimations =>
        'accessibility_disable_animations',
      ArticleReaderFallbackReason.longDocument => 'long_document',
    };
  }

  void _trackArticleReaderFallback(
    PostBaseDto post,
    ArticleReaderFallbackReason reason, {
    required bool bookReaderEnabled,
  }) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason: _fallbackReasonName(reason),
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  void _trackArticlePageFlipCommit(
    PostBaseDto post,
    ArticleReaderPageFlipCommit event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageFlipCommit(
          postId: post.id,
          durationMs: event.durationMs,
          mechanism: event.mechanism,
          direction: event.direction,
          fromPage: event.fromPage,
          toPage: event.toPage,
        );
  }

  void _trackArticlePageCurlAbort(
    PostBaseDto post,
    ArticleReaderPageCurlAbort event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageCurlAbort(
          postId: post.id,
          corner: event.corner,
          progress: event.progress,
          direction: event.direction,
        );
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
    final isLiked = effectivePostLiked(ref, post.id);
    final currentCount = effectivePostLikeCount(
      ref,
      post.id,
      fallback: post.likeCount,
    );
    final nextLiked = !isLiked;
    final nextLikeCount = nextLiked
        ? currentCount + 1
        : (currentCount - 1).clamp(0, 1 << 31).toInt();
    syncPostLikeIntent(
      ref,
      postId: post.id,
      isLiked: nextLiked,
      likeCount: nextLikeCount,
    );
  }

  void _onFavorite(PostBaseDto post) {
    final isSaved = effectivePostSaved(ref, post.id);
    final currentCount = effectivePostBookmarkCount(
      ref,
      post.id,
      fallback: post.favoriteCount,
    );
    final nextSaved = !isSaved;
    final nextBookmarkCount = nextSaved
        ? currentCount + 1
        : (currentCount - 1).clamp(0, 1 << 31).toInt();
    syncPostSaveIntent(
      ref,
      postId: post.id,
      isSaved: nextSaved,
      bookmarkCount: nextBookmarkCount,
    );
  }

  void _onFollow(PostBaseDto post) {
    final subjectId = post.subAccountId;
    final nextFollowing = !effectiveProfileFollowing(ref, subjectId);
    syncProfileFollowIntent(
      ref,
      subAccountId: subjectId,
      isFollowing: nextFollowing,
    );
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
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    final posts = _buildFeed();
    final currentPost = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)];
    final currentLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _layoutSpecForPost(currentPost);
    final progress = _innerProgress(posts);
    final overlayTitle = currentPost == null
        ? ''
        : _overlayTitleForPost(currentPost);
    final overlayBody = currentPost == null
        ? ''
        : _overlayBodyForPost(currentPost);
    final topProgressLabel = currentPost == null
        ? null
        : _topProgressLabelForPost(currentPost, progress);
    final Widget? counterIndicator = null;
    final overlayFooter = currentPost == null
        ? null
        : _overlayFooterForPost(context, currentPost);
    // 与 welcome_screen 一致：阻断 MaterialApp 默认 TextStyle 合并带来的误装饰（黄下划线等）。
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
          systemNavigationBarColor: AppColors.transparent,
          systemNavigationBarIconBrightness: Brightness.light,
        ),
        child: GestureDetector(
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
                      return Center(child: CupertinoActivityIndicator());
                    }
                    return _buildPostCanvas(posts[index]);
                  },
                ),
              ),

              if (_isFilterExpanded && widget.showTopNavigation)
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
                        layoutSpec: currentLayoutSpec,
                        isFilterExpanded: _isFilterExpanded,
                        progressLabel: topProgressLabel,
                        onTapClose: _dismissViewer,
                        onTapMore: () => _showWorksMoreSheet(context),
                        onTapWorksArrow: _toggleFilterPanel,
                        onTapFollowing:
                            widget.onSwitchToFollowing ??
                            widget.onSwitchToMoment,
                        onTapCircles: widget.onSwitchToCircles,
                        onHorizontalDragEnd: _handlePrimaryTabSwipeDragEnd,
                        showNavigationTabs: widget.showTopNavigation,
                      ),
                      if (widget.showTopNavigation)
                        AnimatedSwitcher(
                          duration: const Duration(milliseconds: 420),
                          switchInCurve: Curves.elasticOut,
                          switchOutCurve: Curves.easeInCubic,
                          transitionBuilder: (child, animation) =>
                              SizeTransition(
                                sizeFactor: animation,
                                axisAlignment: -1,
                                child: FadeTransition(
                                  opacity: animation,
                                  child: child,
                                ),
                              ),
                          child: _isFilterExpanded
                              ? _WorksSecondaryFilterBar(
                                  key: const ValueKey<String>(
                                    'works-filter-open',
                                  ),
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

              if (currentPost != null && _showsCaptionOverlay(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: _toolbarReservedHeight + AppSpacing.containerSm,
                  child: MediaCaptionBlock(
                    layoutSpec: currentLayoutSpec,
                    railKey: const ValueKey<String>('works-caption-rail'),
                    header: counterIndicator,
                    title: overlayTitle,
                    caption: overlayBody,
                    isExpanded: _isCaptionExpanded(currentPost.id),
                    onToggle: () => _toggleCaptionExpanded(currentPost.id),
                    footer: overlayFooter,
                  ),
                ),

              if (currentPost != null && widget.showWorksToolbar)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: ImmersiveEngagementBar(
                    layoutSpec: currentLayoutSpec,
                    avatarUrl: currentPost.avatarUrl,
                    displayName: currentPost.displayName,
                    circleName: '',
                    likeCount: effectivePostLikeCount(
                      ref,
                      currentPost.id,
                      fallback: currentPost.likeCount,
                    ),
                    shareCount: effectivePostShareCount(
                      ref,
                      currentPost.id,
                      fallback: currentPost.shareCount,
                    ),
                    commentCount: effectivePostCommentCount(
                      ref,
                      currentPost.id,
                      fallback: currentPost.commentCount,
                    ),
                    isLiked: effectivePostLiked(ref, currentPost.id),
                    isFollowing: effectiveProfileFollowing(
                      ref,
                      currentPost.subAccountId,
                    ),
                    showFollowButton: _showFollowButton,
                    onUserTap: () => widget.onUserTap(
                      currentPost.subAccountId,
                      avatarUrl: currentPost.avatarUrl,
                      displayName: currentPost.displayName,
                      backgroundUrl: currentPost.authorBackgroundUrl,
                    ),
                    onCircleTap: () {
                      final circleId = _primaryCircleIdForPost(currentPost);
                      if (circleId == null || circleId.isEmpty) return;
                      context.push(AppRoutePaths.circleDetail(id: circleId));
                    },
                    onFollowTap: () => _onFollow(currentPost),
                    onLikeTap: () => _onLike(currentPost),
                    onCommentTap: () =>
                        _openCommentFor(context, currentPost.id),
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
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPostCanvas(PostBaseDto post) {
    return _buildTypedCanvas(post);
  }

  Widget _buildTypedCanvas(PostBaseDto post) {
    final onOverflowPrevious = _canSwipePrimaryTabs
        ? _switchToPreviousPrimaryTab
        : null;
    final onOverflowNext = _canSwipePrimaryTabs
        ? _switchToNextPrimaryTab
        : null;
    final enableArticlePageCurl = ref.watch(
      contentFeatureFlagProvider('enable_article_page_curl'),
    );
    if (_isImageLikePost(post)) {
      return _WorksPhotoCanvas(
        post: post,
        initialIndex: _photoInnerIndex[post.id] ?? _defaultImageIndexFor(post),
        onImageChanged: (index) =>
            setState(() => _photoInnerIndex[post.id] = index),
        onOverflowPrevious: onOverflowPrevious,
        onOverflowNext: onOverflowNext,
      );
    }
    if (_isVideoLikePost(post)) {
      final episodes = _videoEpisodesForCurrent(post, _buildFeed());
      return _WorksVideoCanvas(
        post: post,
        episodes: episodes,
        onEpisodeChanged: (idx) =>
            setState(() => _videoInnerIndex[post.id] = idx),
        onOverflowPrevious: onOverflowPrevious,
        onOverflowNext: onOverflowNext,
      );
    }
    if (_isArticleLikePost(post)) {
      final article = _articleViewFor(post);
      final safeInitialPage = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, article.pages.length - 1)
          .toInt();
      return _WorksArticleCanvas(
        post: post,
        article: article,
        enablePageCurl: enableArticlePageCurl,
        initialPage: safeInitialPage,
        onPageChanged: (index) =>
            setState(() => _articleInnerIndex[post.id] = index),
        onFallbackResolved: (reason) =>
            _trackArticleReaderFallback(post, reason, bookReaderEnabled: true),
        onPageFlipCommitted: (event) =>
            _trackArticlePageFlipCommit(post, event),
        onPageCurlAborted: (event) => _trackArticlePageCurlAbort(post, event),
        onOverflowPrevious: onOverflowPrevious,
        onOverflowNext: onOverflowNext,
      );
    }
    if (_isTextOnlyMomentPost(post)) {
      return TabSwipeSwitchRegion(
        enabled: _canSwipePrimaryTabs,
        onSwipe: _handlePrimaryTabSwipe,
        child: _WorksTextCanvas(
          layoutSpec: _layoutSpecForPost(post),
          title: _titleForPost(post),
          body: _bodyForPost(post),
          imageUrl: _rawPostById(
            post.id,
          )?[ArticleDetailWireKeys.coverUrl]?.toString(),
        ),
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
        await _recordShare(post.id, result.actionId);
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
      await _recordShare(post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final raw = _rawPostById(post.id);
    final visibility =
        raw?[ContentPostImmersiveWireKeys.visibility]?.toString() ?? 'public';
    final tags =
        (raw?[ContentPostImmersiveWireKeys.tags] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    return ContentShareTemplateBuilder.build(
      post: post,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
      tags: tags,
      circleNames: _circlesForPost(
        post,
      ).map((circle) => circle.name).toList(growable: false),
    );
  }

  Future<void> _recordShare(String postId, String actionId) async {
    final rawShareCount =
        (_rawPostById(postId)?[ContentPostImmersiveWireKeys.shareCount] as num?)
            ?.toInt() ??
        0;
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
}

class _PostCircleTarget {
  const _PostCircleTarget({required this.id, required this.name});

  final String id;
  final String name;
}

class _WorksPrimaryTopBar extends StatelessWidget {
  const _WorksPrimaryTopBar({
    required this.layoutSpec,
    required this.isFilterExpanded,
    required this.progressLabel,
    required this.onTapWorksArrow,
    required this.onHorizontalDragEnd,
    this.showNavigationTabs = true,
    this.onTapClose,
    this.onTapMore,
    this.onTapFollowing,
    this.onTapCircles,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final bool isFilterExpanded;
  final String? progressLabel;
  final VoidCallback onTapWorksArrow;
  final GestureDragEndCallback onHorizontalDragEnd;
  final bool showNavigationTabs;
  final VoidCallback? onTapClose;
  final VoidCallback? onTapMore;
  final VoidCallback? onTapFollowing;
  final VoidCallback? onTapCircles;

  @override
  Widget build(BuildContext context) {
    return ImmersiveViewerLayout.alignToRail(
      context: context,
      layoutSpec: layoutSpec,
      child: SizedBox(
        key: const ValueKey<String>('works-top-rail'),
        width: double.infinity,
        height: AppSpacing.tabNavigationHeight,
        child: Stack(
          children: [
            Positioned.fill(
              child: showNavigationTabs
                  ? Center(
                      child: HomePrimaryTabStrip(
                        activeTab: HomePrimaryTabStrip.featuredTabId,
                        onTabChange: (tabId) {
                          switch (tabId) {
                            case HomePrimaryTabStrip.followingTabId:
                              onTapFollowing?.call();
                              break;
                            case HomePrimaryTabStrip.circlesTabId:
                              onTapCircles?.call();
                              break;
                            case HomePrimaryTabStrip.featuredTabId:
                              onTapWorksArrow();
                              break;
                          }
                        },
                        onHorizontalDragEnd: onHorizontalDragEnd,
                        isDark: true,
                        style: HomePrimaryTabStripStyle.immersive,
                        featuredIndicatorVisible: true,
                        featuredExpanded: isFilterExpanded,
                      ),
                    )
                  : const SizedBox.shrink(),
            ),

            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: Opacity(
                  opacity: onTapClose == null ? 0 : 1,
                  child: KeyedSubtree(
                    key: const ValueKey<String>('works-top-back'),
                    child: ImmersiveToolbarIconButton(
                      icon: CupertinoIcons.back,
                      onPressed: onTapClose,
                      foregroundColor: AppColors.white,
                    ),
                  ),
                ),
              ),
            ),

            if (progressLabel?.isNotEmpty == true)
              Positioned(
                left: AppSpacing.iconButtonMinSizeSm + AppSpacing.intraGroupSm,
                top: 0,
                bottom: 0,
                child: Center(
                  child: _WorksTopProgressLabel(label: progressLabel!),
                ),
              ),

            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: ImmersiveToolbarIconButton(
                  icon: CupertinoIcons.ellipsis,
                  onPressed: onTapMore,
                  foregroundColor: AppColors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WorksTopProgressLabel extends StatelessWidget {
  const _WorksTopProgressLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: DecoratedBox(
          key: const ValueKey<String>('works-top-progress-label'),
          decoration: BoxDecoration(
            color: AppColors.black.withValues(alpha: 0.18),
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            border: Border.all(
              color: AppColors.white.withValues(alpha: 0.12),
              width: AppSpacing.hairline,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            child: Text(
              label,
              style: TextStyle(
                color: AppColors.worksBodyText,
                fontSize: AppTypography.xsPlus,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
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
              : AppColors.transparent,
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
  const _WorksPhotoCanvas({
    required this.post,
    required this.onImageChanged,
    this.initialIndex = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final void Function(int index) onImageChanged;
  final int initialIndex;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  State<_WorksPhotoCanvas> createState() => _WorksPhotoCanvasState();
}

class _WorksPhotoCanvasState extends State<_WorksPhotoCanvas> {
  static const double _overflowSwitchVelocity = 320;
  static const double _overflowSwitchDistance = AppSpacing.buttonHeight;

  late final PageController _imgController;
  double _edgeOverflowDistance = 0;
  TabSwipeDirection? _pendingOverflowDirection;
  bool _overflowTriggered = false;

  @override
  void initState() {
    super.initState();
    _imgController = PageController(initialPage: _safeInitialIndex);
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      widget.onImageChanged(_safeInitialIndex);
    });
  }

  @override
  void dispose() {
    _imgController.dispose();
    super.dispose();
  }

  int get _safeInitialIndex {
    final length = _images.length;
    if (length <= 1) return 0;
    return widget.initialIndex.clamp(0, length - 1);
  }

  List<String> get _images {
    return widget.post.hasImages
        ? widget.post.mediaImageUrls
        : (widget.post.primaryImageUrl.isNotEmpty
              ? <String>[widget.post.primaryImageUrl]
              : const <String>[]);
  }

  void _triggerOverflow(TabSwipeDirection direction) {
    final callback = direction == TabSwipeDirection.previous
        ? widget.onOverflowPrevious
        : widget.onOverflowNext;
    if (callback == null || _overflowTriggered) {
      return;
    }
    _overflowTriggered = true;
    callback();
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  void _trackEdgeOverflow(DragUpdateDetails details, List<String> images) {
    final pageWidth = MediaQuery.of(context).size.width;
    final maxOffset = images.length <= 1
        ? 0.0
        : (images.length - 1) * pageWidth;
    final atLeadingEdge = _imgController.offset <= AppSpacing.hairline;
    final atTrailingEdge =
        _imgController.offset >= maxOffset - AppSpacing.hairline;
    final swipingToPrevious = details.delta.dx > 0;
    final swipingToNext = details.delta.dx < 0;
    final direction = atLeadingEdge && swipingToPrevious
        ? TabSwipeDirection.previous
        : atTrailingEdge && swipingToNext
        ? TabSwipeDirection.next
        : null;
    if (direction == null) {
      _edgeOverflowDistance = 0;
      _pendingOverflowDirection = null;
      return;
    }
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += details.delta.dx.abs();
    if (_edgeOverflowDistance >= _overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
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
    if (images.length > 1) {
      final pageWidth = MediaQuery.of(context).size.width;
      final maxOffset = (images.length - 1) * pageWidth;
      _imgController.jumpTo(
        (_imgController.offset - details.delta.dx).clamp(0.0, maxOffset),
      );
    }
    _trackEdgeOverflow(details, images);
  }

  void _onHorizontalDragEnd(DragEndDetails details) {
    final images = _images;
    final pageWidth = MediaQuery.of(context).size.width;
    final maxOffset = images.length <= 1
        ? 0.0
        : (images.length - 1) * pageWidth;
    final atLeadingEdge = _imgController.offset <= AppSpacing.hairline;
    final atTrailingEdge =
        _imgController.offset >= maxOffset - AppSpacing.hairline;
    final velocity = details.primaryVelocity ?? 0;

    if (!_overflowTriggered && velocity.abs() >= _overflowSwitchVelocity) {
      if (velocity > 0 && atLeadingEdge) {
        _triggerOverflow(TabSwipeDirection.previous);
      } else if (velocity < 0 && atTrailingEdge) {
        _triggerOverflow(TabSwipeDirection.next);
      }
    }

    if (!_overflowTriggered && images.length > 1) {
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

    _resetOverflowTracking();
  }

  @override
  Widget build(BuildContext context) {
    final images = _images;
    final handlesHorizontalOverflow =
        images.length > 1 ||
        widget.onOverflowPrevious != null ||
        widget.onOverflowNext != null;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onHorizontalDragUpdate: handlesHorizontalOverflow
          ? _onHorizontalDragUpdate
          : null,
      onHorizontalDragEnd: handlesHorizontalOverflow
          ? _onHorizontalDragEnd
          : null,
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
              if (images.isEmpty) {
                return Container(color: AppColors.worksBackground);
              }
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
                      AppColors.black.withValues(alpha: 0.06),
                      AppColors.black.withValues(alpha: 0.58),
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
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final List<PostBaseDto> episodes;
  final ValueChanged<int> onEpisodeChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  State<_WorksVideoCanvas> createState() => _WorksVideoCanvasState();
}

class _WorksVideoCanvasState extends State<_WorksVideoCanvas> {
  late final PageController _episodeController;
  late int _currentEpisodeIndex;
  bool _overflowLocked = false;

  int get _initialIndex {
    final idx = widget.episodes.indexWhere((e) => e.id == widget.post.id);
    return idx < 0 ? 0 : idx;
  }

  @override
  void initState() {
    super.initState();
    _currentEpisodeIndex = _initialIndex;
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
        ? <PostBaseDto>[widget.post]
        : widget.episodes;
    return Stack(
      fit: StackFit.expand,
      children: [
        NotificationListener<ScrollNotification>(
          onNotification: (notification) {
            if (notification is OverscrollNotification && !_overflowLocked) {
              if (notification.overscroll < 0) {
                _overflowLocked = true;
                widget.onOverflowPrevious?.call();
              } else if (notification.overscroll > 0) {
                _overflowLocked = true;
                widget.onOverflowNext?.call();
              }
            } else if (notification is ScrollEndNotification) {
              _overflowLocked = false;
            }
            return false;
          },
          child: PageView.builder(
            controller: _episodeController,
            scrollDirection: Axis.horizontal,
            itemCount: episodes.length,
            onPageChanged: (index) {
              setState(() => _currentEpisodeIndex = index);
              widget.onEpisodeChanged(index);
            },
            itemBuilder: (context, index) {
              final episode = episodes[index];
              final videoUrl = _videoUrlFor(episode);
              if (videoUrl.isNotEmpty) {
                return VideoPlayerWidget(
                  key: ValueKey<String>('works-video-${episode.id}-$index'),
                  videoUrl: videoUrl,
                  thumbnailUrl: _thumbnailFor(episode),
                  autoPlay: index == _currentEpisodeIndex,
                  showControls: true,
                );
              }
              return Container(color: AppColors.worksBackground);
            },
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.black.withValues(alpha: 0.08),
                    AppColors.black.withValues(alpha: 0.62),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  String _videoUrlFor(PostBaseDto post) {
    return post.mediaVideoUrl;
  }

  String? _thumbnailFor(PostBaseDto post) {
    return post.mediaThumbnailUrl.isEmpty ? null : post.mediaThumbnailUrl;
  }
}

class _WorksArticleCanvas extends StatelessWidget {
  const _WorksArticleCanvas({
    super.key,
    required this.post,
    required this.article,
    required this.enablePageCurl,
    required this.onPageChanged,
    this.forceDegradedPager = false,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.initialPage = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final ArticleDetailView article;
  final bool enablePageCurl;
  final bool forceDegradedPager;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    final topPaperReservedHeight =
        MediaQuery.paddingOf(context).top +
        AppSpacing.tabNavigationHeight +
        AppSpacing.intraGroupSm;
    final stagePadding = articleReaderStagePagePadding().copyWith(
      top: topPaperReservedHeight,
    );
    return Stack(
      fit: StackFit.expand,
      children: [
        Container(color: AppColors.worksBackground),
        if (post.primaryImageUrl.isNotEmpty)
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
              child: CachedNetworkImage(
                imageUrl: post.primaryImageUrl,
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
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.worksBackground.withValues(alpha: 0.92),
                ],
              ),
            ),
          ),
        ),
        Positioned(
          left: AppSpacing.intraGroupSm,
          right: AppSpacing.intraGroupSm,
          top: 0,
          bottom:
              _WorksImmersiveViewerState._toolbarReservedHeight +
              AppSpacing.containerMd,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final pages = resolvePaginatedArticlePages(
                context: context,
                constraints: constraints,
                document: article.document,
                template: article.template,
                fontPreset: article.fontPreset,
                fallbackPages: article.pages,
                variant: ArticleCanvasVariant.immersive,
              );
              final maxIndex = pages.isEmpty ? 0 : pages.length - 1;
              final safeInitialPage = pages.isEmpty
                  ? 0
                  : initialPage.clamp(0, maxIndex).toInt();
              final metrics = resolveArticleCanvasMetrics(
                context,
                constraints,
                variant: ArticleCanvasVariant.immersive,
              );
              return ArticleReadOnlyBookDeck(
                pages: pages,
                template: article.template,
                fontPreset: article.fontPreset,
                metrics: metrics,
                coverUrl: post.primaryImageUrl,
                initialPage: safeInitialPage,
                enablePageCurl: enablePageCurl,
                forceDegradedPager: forceDegradedPager,
                pagePadding: stagePadding,
                onPageChanged: onPageChanged,
                onOverflowPrevious: onOverflowPrevious,
                onOverflowNext: onOverflowNext,
                onFallbackResolved: onFallbackResolved,
                onPageFlipCommitted: onPageFlipCommitted,
                onPageCurlAborted: onPageCurlAborted,
              );
            },
          ),
        ),
      ],
    );
  }
}

class _WorksTextCanvas extends StatelessWidget {
  const _WorksTextCanvas({
    required this.layoutSpec,
    required this.title,
    required this.body,
    this.imageUrl,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final String title;
  final String body;
  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Container(color: AppColors.worksBackground),
        if ((imageUrl ?? '').isNotEmpty)
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
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
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.worksBackground.withValues(alpha: 0.92),
                ],
              ),
            ),
          ),
        ),
        SafeArea(
          child: Padding(
            padding: EdgeInsets.only(
              top: AppSpacing.containerLg,
              bottom:
                  _WorksImmersiveViewerState._toolbarReservedHeight +
                  AppSpacing.containerMd,
            ),
            child: ImmersiveViewerLayout.alignToRail(
              context: context,
              layoutSpec: layoutSpec,
              child: Container(
                key: const ValueKey<String>('works-text-stage-rail'),
                width: double.infinity,
                padding: EdgeInsets.all(AppSpacing.containerLg),
                decoration: BoxDecoration(
                  color: AppColors.worksDrawerBg.withValues(alpha: 0.74),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.borderRadius + 4,
                  ),
                  border: Border.all(
                    color: AppColors.worksBodyText.withValues(alpha: 0.16),
                  ),
                ),
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (title.isNotEmpty) ...[
                        Text(
                          title,
                          style: TextStyle(
                            fontSize: AppTypography.xl + 2,
                            fontWeight: AppTypography.bold,
                            color: AppColors.worksTitle,
                            height: AppTypography.bodyLineHeight,
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupSm),
                      ],
                      Text(
                        body,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          color: AppColors.worksBodyText,
                          height: AppTypography.lineHeightRelaxed,
                          letterSpacing: 0.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _WorksPageIndicator extends StatelessWidget {
  const _WorksPageIndicator({required this.total, required this.current});

  final int total;
  final int current;
  static const int _maxVisibleDots = 6;

  @override
  Widget build(BuildContext context) {
    final currentIndex = (current - 1).clamp(0, total - 1).toInt();
    final visibleCount = total.clamp(1, _maxVisibleDots).toInt();
    final windowStart = total <= _maxVisibleDots
        ? 0
        : (currentIndex - 2).clamp(0, total - visibleCount).toInt();
    final indicator = Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(visibleCount, (visibleIndex) {
        final absoluteIndex = windowStart + visibleIndex;
        final selected = absoluteIndex == currentIndex;
        final hasLeadingOverflow = windowStart > 0 && visibleIndex == 0;
        final hasTrailingOverflow =
            windowStart + visibleCount < total &&
            visibleIndex == visibleCount - 1;
        final alpha = selected
            ? 0.94
            : (absoluteIndex < currentIndex && hasLeadingOverflow) ||
                  (absoluteIndex > currentIndex && hasTrailingOverflow)
            ? 0.18
            : 0.38;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: 1.5),
          width: AppSpacing.xs + AppSpacing.hairline,
          height: AppSpacing.xs + AppSpacing.hairline,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.white.withValues(alpha: alpha),
          ),
        );
      }),
    );
    return IgnorePointer(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: DecoratedBox(
            key: const ValueKey<String>('works-page-indicator'),
            decoration: BoxDecoration(
              color: AppColors.black.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
              border: Border.all(
                color: AppColors.white.withValues(alpha: 0.06),
                width: AppSpacing.hairline,
              ),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: indicator,
            ),
          ),
        ),
      ),
    );
  }
}

class _ArticleGuideCard extends StatelessWidget {
  const _ArticleGuideCard({required this.post});

  final PostBaseDto post;

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
                  post.normalizedTitle,
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
                  post.normalizedBody,
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
            child: _GuideThumb(imageUrl: post.coverUrl ?? ''),
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
                                      AppColors.white,
                                      AppColors.transparent,
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
