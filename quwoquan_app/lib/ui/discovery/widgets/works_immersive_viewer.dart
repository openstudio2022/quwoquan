import 'dart:async';
import 'dart:math' show exp, max;
import 'dart:ui' show FontFeature, ImageFilter;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart'
    as runtime_error_display;
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_media_item_dto.g.dart';
import 'package:video_player/video_player.dart'
    show VideoPlayerController, VideoPlayerValue;
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/components/comment_system/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorAction, ReferralSource;
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart'
    show authSessionControllerProvider;
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/article_reader_observability.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart'
    show ContentType;
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show ActivePersonaContextViewData;
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/immersive_browser_reader_adapter.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart'
    show ArticleReadOnlyBookDeckPresentationStyle;
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_time_label.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

part 'works_immersive_viewer_controls.dart';

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
    this.initialCommentContext = const MediaViewerCommentContext(),
    this.onDismissed,
    this.onPostIndexChanged,
    this.topChromeSafeInset = 0,
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
  final List<ContentSurfaceView>? externalPostViews;
  final int initialPostIndex;
  final int initialImageIndex;
  final String source;
  final Map<String, MediaViewerPostWireRow> rawPostsById;
  final String? defaultCircleId;
  final MediaViewerInteractionSnapshot initialInteractionSnapshot;
  final MediaViewerCommentContext initialCommentContext;
  final ValueChanged<MediaViewerResult>? onDismissed;
  final ValueChanged<int>? onPostIndexChanged;
  final double topChromeSafeInset;

  @override
  ConsumerState<WorksImmersiveViewer> createState() =>
      _WorksImmersiveViewerState();
}

class _WorksImmersiveViewerState extends ConsumerState<WorksImmersiveViewer>
    with TickerProviderStateMixin {
  static const int _tailPrefetchThreshold = 2;
  static const double _edgeDismissHotzoneWidth = AppSpacing.lg;
  static const double _edgeDismissMinDistance = 56;
  static const double _edgeDismissMinVelocity = 520;

  Set<String> _selectedWorkFilterIds = <String>{'all'};
  int _currentPage = 0;
  final Map<String, int> _photoInnerIndex = <String, int>{};
  final Map<String, int> _articleInnerIndex = <String, int>{};
  final Map<String, int> _resolvedArticlePageCount = <String, int>{};
  final Map<String, String> _articlePaperThemeOverrides = <String, String>{};
  final Map<String, int> _videoInnerIndex = <String, int>{};
  final Set<String> _expandedCaptionPostIds = <String>{};
  String? _commentSplitPostId;

  // Dwell tracking：记录当前帖子进入时间
  DateTime? _pageEnterTime;
  final DateTime _viewerOpenedAt = DateTime.now();
  final Map<String, Map<String, Object?>> _hydratedRawPostsById =
      <String, Map<String, Object?>>{};
  final Set<String> _hydratingArticleIds = <String>{};
  final Set<String> _failedArticleHydrationIds = <String>{};
  final Map<String, Object> _failedArticleHydrationErrorsById =
      <String, Object>{};
  final Map<String, WorkBrowserItemDto> _workItemCache =
      <String, WorkBrowserItemDto>{};

  // 当前可见视频作品的播放控制器（由 _WorksVideoCanvas 上报，供极简控制条消费）。
  VideoPlayerController? _activeVideoController;
  String? _activeVideoStageKey;

  late final PageController _pageController;
  bool _prefetchScheduled = false;
  bool _awaitingPrefetchedReveal = false;
  TabSwipeDirection? _activeEdgeDismissDirection;
  double _activeEdgeDismissDistance = 0;

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
      final posts = _buildFeed();
      if (posts.isNotEmpty) {
        final initialIndex = _currentPage.clamp(0, posts.length - 1);
        if (widget.initialCommentContext.shouldOpen &&
            _commentSplitPostId == null) {
          setState(() => _commentSplitPostId = posts[initialIndex].id);
        }
        // Track impression for the first post
        _trackImpressionForPost(posts[initialIndex]);
        _pageEnterTime = DateTime.now();
      }
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  bool get _usesExternalFeed =>
      widget.externalPosts != null && widget.externalPosts!.isNotEmpty;

  bool get _enableArticlePageCurl {
    final runtimeConfig = ref.read(contentRuntimeConfigProvider);
    return runtimeConfig.featureFlags.containsKey('enable_article_page_curl')
        ? runtimeConfig.isEnabled('enable_article_page_curl')
        : true;
  }

  List<String> get _trackedFeedTabIds {
    if (_usesExternalFeed) {
      return const <String>[];
    }
    final contentTypes = _effectiveFilterContentTypes;
    if (contentTypes.isEmpty) {
      return const <String>['photo', 'video', 'article'];
    }
    final tracked = <String>[];
    if (contentTypes.contains('image')) tracked.add('photo');
    if (contentTypes.contains('video')) tracked.add('video');
    if (contentTypes.contains('article')) tracked.add('article');
    return tracked;
  }

  DiscoveryFeedState? _readFeedState(String tabId) {
    return ref.read(discoveryFeedProvider(tabId)).value;
  }

  bool _trackedFeedsHaveMore() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.hasMore ?? false,
    );
  }

  bool _trackedFeedsLoading() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.isLoading ?? false,
    );
  }

  Object? _trackedFeedsError() {
    for (final tabId in _trackedFeedTabIds) {
      final error = _readFeedState(tabId)?.appendError;
      if (error != null) {
        return error;
      }
    }
    return null;
  }

  void _requestPrefetchNow({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed) {
      return;
    }
    final thresholdIndex = max(0, postsLength - 1 - _tailPrefetchThreshold);
    if (!force && visibleIndex < thresholdIndex) {
      return;
    }
    for (final tabId in _trackedFeedTabIds) {
      final feedState = _readFeedState(tabId);
      if (feedState == null || !feedState.hasMore || feedState.isLoading) {
        continue;
      }
      unawaited(
        ref.read(discoveryFeedMapProvider.notifier).appendNextPage(tabId),
      );
    }
  }

  void _schedulePrefetch({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed || _prefetchScheduled) {
      return;
    }
    _prefetchScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prefetchScheduled = false;
      if (!mounted) {
        return;
      }
      _requestPrefetchNow(
        visibleIndex: visibleIndex,
        postsLength: postsLength,
        force: force,
      );
    });
  }

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

  bool _canDeletePost(
    PostBaseDto post,
    ActivePersonaContextViewData? activePersonaContext,
  ) {
    final postSubAccountId = post.subAccountId.trim();
    if (postSubAccountId.isEmpty) {
      return false;
    }
    final personaSubAccountId = activePersonaContext?.subAccountId.trim() ?? '';
    if (personaSubAccountId.isNotEmpty) {
      return personaSubAccountId == postSubAccountId;
    }
    final sessionSubAccountId = ref
        .read(authSessionControllerProvider)
        .activeSubAccountId
        .trim();
    if (sessionSubAccountId.isNotEmpty) {
      return sessionSubAccountId == postSubAccountId;
    }
    final currentUserId = ref.read(currentUserIdProvider).trim();
    return currentUserId.isNotEmpty && currentUserId == postSubAccountId;
  }

  Future<void> _deleteCurrentPost(
    BuildContext context,
    PostBaseDto post,
  ) async {
    runWhenLoggedIn(ref, context, AuthGateReason.deletePost, () async {
      final displayName = post.displayName.trim().isNotEmpty
          ? post.displayName.trim()
          : post.title.trim().isNotEmpty
          ? post.title.trim()
          : UITextConstants.contentUnavailable;
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: UITextConstants.messageActionDelete,
        message: UITextConstants.profileSubAccountDeleteConfirmTemplate
            .replaceFirst('%s', displayName),
        sections: const [
          AppActionSheetSection<bool>(
            items: [
              AppActionSheetItem<bool>(
                value: true,
                label: UITextConstants.messageActionDelete,
                icon: CupertinoIcons.delete,
                isDestructive: true,
              ),
            ],
          ),
        ],
      );
      if (confirmed != true || !context.mounted) {
        return;
      }
      try {
        await ref.read(contentRepositoryProvider).deletePost(postId: post.id);
        ref.read(discoveryFeedMapProvider.notifier).removePostLocally(post.id);
        if (context.mounted) {
          AppToast.show(context, UITextConstants.contentDeleteSuccess);
        }
        if (!mounted) {
          return;
        }
        setState(() {
          _commentSplitPostId = null;
          _hydratedRawPostsById.remove(post.id);
          _workItemCache.remove(post.id);
          _failedArticleHydrationIds.remove(post.id);
          _failedArticleHydrationErrorsById.remove(post.id);
          _hydratingArticleIds.remove(post.id);
        });
        _dismissViewer();
      } catch (error) {
        if (!context.mounted) {
          return;
        }
        final semantic = runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: semantic);
      }
    });
  }

  Set<String> get _effectiveFilterIds {
    if (_selectedWorkFilterIds.isEmpty ||
        _selectedWorkFilterIds.contains('all')) {
      return <String>{'all'};
    }
    return _selectedWorkFilterIds;
  }

  Set<String> get _effectiveFilterContentTypes {
    final types = <String>{};
    for (final filter in ContentUIConfig.workFormatFilters) {
      if (_effectiveFilterIds.contains(filter.id) &&
          filter.contentType != null) {
        types.add(filter.contentType!);
      }
    }
    return types;
  }

  /// Opens the post-level more-options sheet for the currently visible post.
  ///
  /// Work Browser V1.0：媒体筛选入口在「更多」菜单内（全部作品/图片/视频/文章）。
  void _showWorksMoreSheet(BuildContext context) {
    final posts = _buildFeed();
    final post = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)] as PostBaseDto?;
    if (post == null) return;
    final enableIdentityTemplate = ref.read(
      contentFeatureFlagProvider('enable_identity_share_template'),
    );
    final activePersonaContext = ref
        .read(activePersonaContextProvider)
        .asData
        ?.value;
    final canDelete = _canDeletePost(post, activePersonaContext);
    final filterOptions = <MoreActionFilterOption>[
      for (final filter in ContentUIConfig.workFormatFilters)
        MoreActionFilterOption(
          id: filter.id,
          label: UITextConstants.contentLabelForKey(filter.labelKey),
        ),
    ];
    final isArticle = _isArticleLikePost(post);
    final readingOptions = isArticle
        ? <MoreActionReadingOption>[
            for (final option in ContentUIConfig.articlePaperThemeOptions)
              MoreActionReadingOption(
                id: option.id,
                label: UITextConstants.contentLabelForKey(option.labelKey),
              ),
          ]
        : const <MoreActionReadingOption>[];
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
        filterOptions: filterOptions,
        selectedFilterIds: _effectiveFilterIds.toList(growable: false),
        onFilterSelectionChanged: _applyFilterSelection,
        readingOptions: readingOptions,
        selectedReadingOptionId: isArticle
            ? (_articlePaperThemeOverrides[post.id] ?? 'system')
            : null,
        onReadingOptionChanged: isArticle
            ? (id) => setState(() {
                if (id == 'system') {
                  _articlePaperThemeOverrides.remove(post.id);
                } else {
                  _articlePaperThemeOverrides[post.id] = id;
                }
              })
            : null,
        forceDarkAppearance: true,
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
        showDeleteAction: canDelete,
        onDelete: canDelete ? () => _deleteCurrentPost(context, post) : null,
      ),
    );
  }

  List<PostBaseDto> _buildFeed() {
    if (_usesExternalFeed) {
      final external = widget.externalPosts!;
      final filterTypes = _effectiveFilterContentTypes;
      if (filterTypes.contains('image') && filterTypes.length == 1) {
        return external.where(_isImageLikePost).toList(growable: false);
      }
      if (filterTypes.contains('video') && filterTypes.length == 1) {
        return external.where(_isVideoLikePost).toList(growable: false);
      }
      if (filterTypes.contains('article') && filterTypes.length == 1) {
        return external
            .where(
              (post) => _isArticleLikePost(post) || _isTextOnlyMomentPost(post),
            )
            .toList(growable: false);
      }
      if (filterTypes.isNotEmpty) {
        return external
            .where((post) {
              if (filterTypes.contains('image') && _isImageLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('video') && _isVideoLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('article') &&
                  (_isArticleLikePost(post) || _isTextOnlyMomentPost(post))) {
                return true;
              }
              return false;
            })
            .toList(growable: false);
      }
      return external;
    }
    final photos = ref.watch(discoveryFeedProvider('photo')).value?.items ?? [];
    final videos = ref.watch(discoveryFeedProvider('video')).value?.items ?? [];
    final articles =
        ref.watch(discoveryFeedProvider('article')).value?.items ?? [];

    final filterTypes = _effectiveFilterContentTypes;
    if (filterTypes.contains('image') && filterTypes.length == 1) return photos;
    if (filterTypes.contains('video') && filterTypes.length == 1) return videos;
    if (filterTypes.contains('article') && filterTypes.length == 1) {
      return articles;
    }
    if (filterTypes.isNotEmpty) {
      final result = <PostBaseDto>[];
      final maxLen = max(photos.length, max(videos.length, articles.length));
      for (var i = 0; i < maxLen; i++) {
        if (filterTypes.contains('image') && i < photos.length) {
          result.add(photos[i]);
        }
        if (filterTypes.contains('video') && i < videos.length) {
          result.add(videos[i]);
        }
        if (filterTypes.contains('article') && i < articles.length) {
          result.add(articles[i]);
        }
      }
      return result;
    }

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
      'shareCount': raw?['shareCount'] ?? post.shareCount,
      'createdAt': raw?['createdAt'] ?? post.createdAt,
    };
  }

  ContentArticleRender _articleViewFor(PostBaseDto post) {
    return projectArticleDetailView(
      Map<String, dynamic>.from(_rawArticleDataFor(post)),
      fallbackArticleId: post.id,
    );
  }

  int _articlePageCount(PostBaseDto post) {
    return (_resolvedArticlePageCount[post.id] ??
            _articleViewFor(post).pages.length)
        .clamp(1, 99);
  }

  void _handleResolvedArticlePageCount(String postId, int pageCount) {
    final safePageCount = pageCount.clamp(1, 99);
    if (_resolvedArticlePageCount[postId] == safePageCount) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _resolvedArticlePageCount[postId] == safePageCount) {
        return;
      }
      setState(() {
        _resolvedArticlePageCount[postId] = safePageCount;
      });
    });
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
      final items = _videoItemsFor(current);
      final total = items.isEmpty ? 1 : items.length.clamp(1, 99);
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

  bool get _canDismissViewerWithEdgeGesture =>
      widget.onDismissed != null || widget.onTapBack != null;

  bool _supportsEdgeDismissDirection(TabSwipeDirection direction) {
    if (!_canDismissViewerWithEdgeGesture) {
      return false;
    }
    return switch (Theme.of(context).platform) {
      TargetPlatform.android || TargetPlatform.fuchsia => true,
      TargetPlatform.iOS ||
      TargetPlatform.macOS ||
      TargetPlatform.linux ||
      TargetPlatform.windows => direction == TabSwipeDirection.previous,
    };
  }

  void _resetEdgeDismissTracking() {
    _activeEdgeDismissDirection = null;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragStart(TabSwipeDirection direction) {
    _activeEdgeDismissDirection = direction;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragUpdate(
    DragUpdateDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedDelta = direction == TabSwipeDirection.previous
        ? details.delta.dx
        : -details.delta.dx;
    _activeEdgeDismissDistance = max(
      0,
      _activeEdgeDismissDistance + signedDelta,
    );
  }

  void _handleEdgeDismissDragEnd(
    DragEndDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedVelocity = direction == TabSwipeDirection.previous
        ? (details.primaryVelocity ?? 0)
        : -(details.primaryVelocity ?? 0);
    final shouldDismiss =
        _activeEdgeDismissDistance >= _edgeDismissMinDistance ||
        signedVelocity >= _edgeDismissMinVelocity;
    _resetEdgeDismissTracking();
    if (shouldDismiss) {
      _dismissViewer();
    }
  }

  Widget _buildEdgeDismissHotzone(TabSwipeDirection direction) {
    if (!_supportsEdgeDismissDirection(direction)) {
      return const SizedBox.shrink();
    }
    return Positioned(
      top: 0,
      bottom: 0,
      left: direction == TabSwipeDirection.previous ? 0 : null,
      right: direction == TabSwipeDirection.next ? 0 : null,
      child: SizedBox(
        key: ValueKey<String>('works-edge-dismiss-${direction.name}'),
        width: _edgeDismissHotzoneWidth,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragStart: (_) => _handleEdgeDismissDragStart(direction),
          onHorizontalDragUpdate: (details) =>
              _handleEdgeDismissDragUpdate(details, direction),
          onHorizontalDragEnd: (details) =>
              _handleEdgeDismissDragEnd(details, direction),
          onHorizontalDragCancel: _resetEdgeDismissTracking,
          child: const SizedBox.expand(),
        ),
      ),
    );
  }

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

  /// 作品级统一投影：raw wire + PostBaseDto 收敛为 [WorkBrowserItemDto]。
  /// 视频集（mediaItems）、图片序列、交集摘要只允许从该投影读取。
  WorkBrowserItemDto _workItemFor(PostBaseDto post) {
    final cached = _workItemCache[post.id];
    if (cached != null) return cached;
    final raw = _effectiveRawPostById(post.id);
    final source = raw == null
        ? post.toMap()
        : Map<String, dynamic>.from(
            raw.map((k, v) => MapEntry(k.toString(), v)),
          );
    final item = WorkBrowserItemDto.fromMap(source);
    _workItemCache[post.id] = item;
    return item;
  }

  /// 视频集序列：契约 mediaItems[kind=video]，为空时回落单视频。
  List<WorkBrowserMediaItemDto> _videoItemsFor(PostBaseDto post) {
    final items = _workItemFor(post).videoItems;
    if (items.isNotEmpty) return items;
    if (post.mediaVideoUrl.isEmpty) return const <WorkBrowserMediaItemDto>[];
    return <WorkBrowserMediaItemDto>[
      WorkBrowserMediaItemDto(
        kind: 'video',
        url: post.mediaVideoUrl,
        coverUrl: post.mediaThumbnailUrl.isEmpty
            ? null
            : post.mediaThumbnailUrl,
      ),
    ];
  }

  void _applyFilterSelection(Set<String> selectedIds) {
    final nextIds = selectedIds.isEmpty || selectedIds.contains('all')
        ? <String>{'all'}
        : selectedIds;
    setState(() {
      _selectedWorkFilterIds = nextIds;
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
    return Map<String, Object?>.from(wire.toWireMap());
  }

  ContentSurfaceView? _summaryForPost(String postId) {
    final external = widget.externalPostViews;
    if (external == null || external.isEmpty) return null;
    for (final item in external) {
      if (item.postId == postId) return item;
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
    final summaryTitle = summary?.title?.trim() ?? '';
    if (summaryTitle.isNotEmpty) return summaryTitle;
    final pres = PostReadPresentation.fromPostBase(
      post,
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
    final summaryBody = summary?.body?.trim() ?? '';
    if (summaryBody.isNotEmpty) return summaryBody;
    final pres = PostReadPresentation.fromPostBase(
      post,
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

  _WorksTopChromeTheme _topChromeThemeForPost(
    BuildContext context,
    PostBaseDto? post,
  ) {
    if (post == null || !_isArticleLikePost(post)) {
      return _WorksTopChromeTheme(
        overlayStyle: const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
          systemNavigationBarColor: AppColors.transparent,
          systemNavigationBarIconBrightness: Brightness.light,
        ),
        foregroundColor: AppColors.white,
        mutedForegroundColor: AppColors.white.withValues(alpha: 0.72),
      );
    }
    final palette = resolveArticlePaperPalette(
      context,
      _resolveArticlePaperTexture(post),
    );
    final surfaceColor = Color.alphaBlend(
      palette.paperColor.withValues(alpha: 0.22),
      palette.stageBackground,
    );
    final primaryColor = palette.textColor.withValues(alpha: 0.96);
    final secondaryColor = palette.secondaryTextColor.withValues(alpha: 0.84);
    return _WorksTopChromeTheme(
      overlayStyle: const SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: AppColors.transparent,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      foregroundColor: primaryColor,
      mutedForegroundColor: secondaryColor,
      surfaceColor: surfaceColor,
      surfaceBorderColor: palette.paperBorderColor.withValues(alpha: 0.44),
    );
  }

  ArticlePaperTexture _resolveArticlePaperTexture(PostBaseDto post) {
    final override = _articlePaperThemeOverrides[post.id];
    if (override != null && override != 'system') {
      return articlePaperTextureFromString(override);
    }
    final item = _workItemFor(post);
    final profile = item.articleRenderProfile ?? const <String, dynamic>{};
    final profileTexture = _stringFromProfile(profile, 'paperTexture');
    if (profileTexture != null && profileTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(profileTexture);
    }
    final topLevelTexture = item.paperTexture;
    if (topLevelTexture != null && topLevelTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(topLevelTexture);
    }
    final vertical =
        item.contentVertical ??
        _stringFromProfile(profile, 'contentVertical') ??
        ContentUIConfig.articleDarkPaperDefaultTheme;
    final mapped = ContentUIConfig.articlePaperVerticalDefaults[vertical];
    return articlePaperTextureFromString(
      mapped ?? ContentUIConfig.articleDarkPaperDefaultTheme,
    );
  }

  String? _stringFromProfile(Map<String, dynamic> profile, String key) {
    final value = profile[key];
    if (value == null) return null;
    return value.toString();
  }

  void _handleArticleEntityTap(ArticleInlineSpan span) {
    final targetType = span.targetType?.trim();
    final targetId = span.targetId?.trim() ?? '';
    if (targetId.isEmpty) return;
    if (targetType != 'homepage' && targetType != 'entity') return;
    context.push(
      AppRoutePaths.homepageDetail(id: _homepageIdForArticleEntity(targetId)),
    );
  }

  String _homepageIdForArticleEntity(String targetId) {
    final normalized = targetId.trim();
    if (!normalized.startsWith('entity:')) {
      return normalized;
    }
    final seed = ContractFixtureRuntimeLoader.entitySeedSet();
    final homepages = seed?['homepages'];
    if (homepages is List) {
      for (final raw in homepages) {
        if (raw is! Map) continue;
        final item = raw.cast<String, dynamic>();
        if (item['canonicalEntityId']?.toString() == normalized) {
          final homepageId = item['homepageId']?.toString() ?? '';
          if (homepageId.isNotEmpty) {
            return homepageId;
          }
        }
      }
    }
    return normalized;
  }

  bool _showsCaptionOverlay(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return false;
    }
    // 视频作品恒显示 caption 区（极简控制条挂载在 caption header）。
    if (_isVideoLikePost(post)) {
      return true;
    }
    // 图片多图作品恒显示（点指示器挂载在 caption header）。
    if (_isImageLikePost(post) && _imageUrlsForPost(post).length > 1) {
      return true;
    }
    return _overlayTitleForPost(post).isNotEmpty ||
        _overlayBodyForPost(post).isNotEmpty;
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

  ImmersiveViewerStageLayoutSpec _engagementLayoutSpecForPost(
    PostBaseDto post,
  ) {
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  double _statusBarContentInsetFor(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return AppSpacing.zero;
    }
    if (widget.topChromeSafeInset <= AppSpacing.zero) {
      return AppSpacing.zero;
    }
    return _shouldMediaInvadeStatusBar(post)
        ? AppSpacing.zero
        : widget.topChromeSafeInset;
  }

  bool _shouldMediaInvadeStatusBar(PostBaseDto post) {
    if (_isVideoLikePost(post)) {
      return true;
    }
    if (!_isImageLikePost(post)) {
      return false;
    }
    final aspectRatio = post.aspectRatio;
    if (aspectRatio == null || aspectRatio <= AppSpacing.zero) {
      return false;
    }
    return aspectRatio <= AppSpacing.immersiveStatusBarMaxAspectRatio;
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

  // ── 交集（推荐解释层）────────────────────────────────────────

  /// 作者区交集摘要：`N 个交集`；无交集证据返回空串（不渲染入口）。
  String _intersectionSummaryFor(PostBaseDto post) {
    final count = post.intersectionReasons?.length ?? 0;
    if (count <= 0) return '';
    return UITextConstants.intersectionEntrySummary(count);
  }

  /// 点击交集入口弹出推荐解释层（V1.0：解释层弹出，禁止卡片/标签遮挡内容）。
  void _showIntersectionDetail(BuildContext context, PostBaseDto post) {
    final reasons = post.intersectionReasons ?? const <IntersectionReason>[];
    if (reasons.isEmpty) return;
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (sheetContext) => _WorksIntersectionDetailSheet(
        reasons: reasons,
        onAskAssistant: () {
          Navigator.pop(sheetContext);
          _openAssistantForIntersectionReason(context, post, reasons);
        },
      ),
    );
  }

  void _openAssistantForIntersectionReason(
    BuildContext context,
    PostBaseDto post,
    List<IntersectionReason> reasons,
  ) {
    if (reasons.isEmpty) return;
    final primary = reasons.first;
    final target = VisitTarget.page('work_intersection_${post.id}');
    final openContext = AssistantOpenContext(
      source: AssistantSource.article,
      tab: 'work_intersection',
      dimension: primary.dimension,
      entityId: post.id,
      objectType: 'post',
      intersectionRefs: _intersectionRefsForReasons(reasons),
      visitTarget: target,
      experienceLevel: ref
          .read(visitRecorderServiceProvider)
          .getExperience(target),
      hints: <String, dynamic>{
        'postId': post.id,
        'contentType': post.type,
        'primaryText': primary.primaryText,
        'reasonCount': reasons.length,
      },
    );
    context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  List<String> _intersectionRefsForReasons(List<IntersectionReason> reasons) {
    final refs = <String>{};
    for (final reason in reasons) {
      final id = reason.intersectionId.trim();
      if (id.isNotEmpty) {
        refs.add('intersection:$id');
      }
      for (final tag in reason.tagRefs) {
        final normalized = tag.trim();
        if (normalized.isNotEmpty) {
          refs.add(normalized);
        }
      }
    }
    return refs.toList(growable: false);
  }

  /// 视频画布上报当前激活的播放控制器（stageKey = postId-episodeIndex）。
  void _handleActiveVideoController(
    String stageKey,
    VideoPlayerController? controller,
  ) {
    if (!mounted) return;
    if (_activeVideoStageKey == stageKey &&
        identical(_activeVideoController, controller)) {
      return;
    }
    setState(() {
      _activeVideoStageKey = stageKey;
      _activeVideoController = controller;
    });
  }

  // ── 行为追踪辅助 ──────────────────────────────────────────────

  void _trackImpressionForPost(PostBaseDto post) {
    final tracker = ref.read(contentBehaviorTrackerProvider);
    tracker.trackImpression(post.id);

    final engTracker = ref.read(contentEngagementTrackerProvider);
    engTracker.trackContentEnter(
      post.id,
      contentType: _mapPostContentType(post),
      referralSource: ReferralSource.organicFeed,
      totalImages: post.imageUrls.length,
      authorId: post.authorId,
    );

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
      ArticleDetailDocumentSource.empty => 'empty',
    };
  }

  void _trackDocumentStructureFallback({
    required PostBaseDto post,
    required ContentArticleRender article,
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

  Future<void> _maybeHydrateArticleDetail(
    PostBaseDto post, {
    bool force = false,
  }) async {
    final raw = _effectiveRawPostById(post.id);
    if (_hasStructuredArticlePayload(raw) ||
        _hydratingArticleIds.contains(post.id) ||
        (!force && _failedArticleHydrationIds.contains(post.id))) {
      return;
    }
    if (force) {
      _failedArticleHydrationIds.remove(post.id);
      _failedArticleHydrationErrorsById.remove(post.id);
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
        _failedArticleHydrationIds.remove(post.id);
        _failedArticleHydrationErrorsById.remove(post.id);
        _workItemCache.remove(post.id);
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
    } catch (error) {
      if (mounted) {
        setState(() {
          _failedArticleHydrationIds.add(post.id);
          _failedArticleHydrationErrorsById[post.id] = error;
        });
      } else {
        _failedArticleHydrationIds.add(post.id);
        _failedArticleHydrationErrorsById[post.id] = error;
      }
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

  bool _shouldShowArticleHydrationError(
    PostBaseDto post,
    ContentArticleRender article,
  ) {
    return article.documentSource == ArticleDetailDocumentSource.empty &&
        _failedArticleHydrationIds.contains(post.id);
  }

  UiErrorSemantic _articleHydrationErrorSemantic(PostBaseDto post) {
    return runtime_error_display.runtimeErrorSemantic(
      context,
      error:
          _failedArticleHydrationErrorsById[post.id] ??
          Exception('article hydration failed'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
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

    ref.read(contentEngagementTrackerProvider).trackContentExit(post.id);
  }

  ContentType _mapPostContentType(PostBaseDto post) {
    final fmt = post.displayFormat;
    if (fmt == 'video') return ContentType.video;
    if (fmt == 'article') return ContentType.article;
    if (post.type == 'micro') return ContentType.micro;
    return ContentType.image;
  }

  // ── 互动操作（乐观 UI + 云侧 API 同步）────────────────────────

  void _onLike(PostBaseDto post) {
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
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
    });
  }

  void _onFollow(PostBaseDto post) {
    runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
      final subjectId = post.subAccountId;
      final nextFollowing = !effectiveProfileFollowing(ref, subjectId);
      syncProfileFollowIntent(
        ref,
        subAccountId: subjectId,
        isFollowing: nextFollowing,
      );
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
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    ref.watch(contentRuntimeConfigProvider);
    ref.watch(activePersonaContextProvider);
    final enableArticlePageCurl = _enableArticlePageCurl;
    final posts = _buildFeed();
    final showLoadMoreSentinel =
        !_usesExternalFeed &&
        posts.isNotEmpty &&
        (_trackedFeedsHaveMore() ||
            _trackedFeedsLoading() ||
            _trackedFeedsError() != null);
    final isOnLoadMoreSentinel =
        showLoadMoreSentinel && _currentPage >= posts.length;
    final currentPost = posts.isEmpty || isOnLoadMoreSentinel
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)];
    final loadMoreError = !_usesExternalFeed ? _trackedFeedsError() : null;
    final isLoadingMore = !_usesExternalFeed && _trackedFeedsLoading();
    if (posts.isNotEmpty) {
      _schedulePrefetch(
        visibleIndex: _currentPage.clamp(0, posts.length),
        postsLength: posts.length,
        force: isOnLoadMoreSentinel,
      );
    }
    if (_awaitingPrefetchedReveal && currentPost != null) {
      final revealedPost = currentPost;
      final revealedIndex = _currentPage;
      _awaitingPrefetchedReveal = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        widget.onPostIndexChanged?.call(revealedIndex);
        _trackImpressionForPost(revealedPost);
        _pageEnterTime = DateTime.now();
      });
    }
    final commentSplitPost = _commentSplitPostId == null
        ? null
        : _postById(posts, _commentSplitPostId!);
    if (commentSplitPost != null) {
      final interaction = ref.watch(postInteractionStateProvider);
      final splitPostId = commentSplitPost.id;
      // 评论分屏复用沉浸式状态栏样式（透明 + 浅色图标），避免回落为白底。
      return AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
        ),
        child: DefaultTextStyle.merge(
          style: const TextStyle(
            decoration: TextDecoration.none,
            decorationThickness: 0,
          ),
          child: ImmersiveCommentSplitSheet(
            postId: splitPostId,
            content: _buildCommentSplitContent(commentSplitPost),
            commentContext: widget.initialCommentContext,
            likeCount: interaction.likeCountFor(splitPostId),
            isLiked: interaction.isLiked(splitPostId),
            onLikeTap: () => _onLike(commentSplitPost),
            onClose: () => setState(() => _commentSplitPostId = null),
          ),
        ),
      );
    }
    final currentLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _layoutSpecForPost(currentPost);
    final currentEngagementLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _engagementLayoutSpecForPost(currentPost);
    final progress = _innerProgress(posts);
    final overlayTitle = currentPost == null
        ? ''
        : _overlayTitleForPost(currentPost);
    final overlayBody = currentPost == null
        ? ''
        : _overlayBodyForPost(currentPost);
    final topChromeTheme = _topChromeThemeForPost(context, currentPost);
    // caption header（内容下方、标题上方）：
    // - 图片多图：点指示器（● ● ○ ● ●，最多 6 点）
    // - 视频：极简播放控制条 + 视频集进度
    Widget? counterIndicator;
    if (currentPost != null) {
      if (_isImageLikePost(currentPost) && progress.total > 1) {
        counterIndicator = _WorksPageIndicator(
          total: progress.total,
          current: progress.current,
        );
      } else if (_isVideoLikePost(currentPost)) {
        counterIndicator = _WorksVideoControlRow(
          key: ValueKey<String>('works-video-controls-${currentPost.id}'),
          controller:
              _activeVideoStageKey ==
                  '${currentPost.id}-${(_videoInnerIndex[currentPost.id] ?? 0)}'
              ? _activeVideoController
              : null,
          episodeCurrent: progress.current,
          episodeTotal: progress.total,
        );
      }
    }
    // 与 welcome_screen 一致：阻断 MaterialApp 默认 TextStyle 合并带来的误装饰（黄下划线等）。
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: topChromeTheme.overlayStyle,
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
                  itemCount: posts.isEmpty
                      ? 1
                      : posts.length + (showLoadMoreSentinel ? 1 : 0),
                  onPageChanged: (index) {
                    if (_currentPage != index) {
                      // Flush dwell time for the previous post
                      if (posts.isNotEmpty && _currentPage < posts.length) {
                        final prevPost =
                            posts[_currentPage.clamp(0, posts.length - 1)];
                        _flushDwell(prevPost);
                        // Track skip: user swiped away from prevPost
                        final enterTime = _pageEnterTime;
                        final skipDwell = enterTime != null
                            ? DateTime.now()
                                      .difference(enterTime)
                                      .inMilliseconds /
                                  1000.0
                            : null;
                        ref
                            .read(contentBehaviorTrackerProvider)
                            .trackSkip(prevPost.id, dwellSeconds: skipDwell);
                      }

                      final nextIsSentinel =
                          showLoadMoreSentinel && index >= posts.length;
                      setState(() {
                        _currentPage = index;
                        _awaitingPrefetchedReveal = nextIsSentinel;
                      });
                      if (nextIsSentinel) {
                        _pageEnterTime = null;
                        _schedulePrefetch(
                          visibleIndex: index,
                          postsLength: posts.length,
                          force: true,
                        );
                        return;
                      }
                      widget.onPostIndexChanged?.call(index);
                      final newPost = posts[index.clamp(0, posts.length - 1)];
                      _trackImpressionForPost(newPost);
                      _pageEnterTime = DateTime.now();
                    }
                  },
                  itemBuilder: (context, index) {
                    if (posts.isEmpty) {
                      return Center(child: CupertinoActivityIndicator());
                    }
                    if (showLoadMoreSentinel && index >= posts.length) {
                      return _buildLoadMoreSentinel(
                        isLoading: isLoadingMore,
                        error: loadMoreError,
                        onRetry: () => _schedulePrefetch(
                          visibleIndex: index,
                          postsLength: posts.length,
                          force: true,
                        ),
                      );
                    }
                    final post = posts[index];
                    return Padding(
                      padding: EdgeInsets.only(
                        top: _statusBarContentInsetFor(post),
                      ),
                      child: KeyedSubtree(
                        key: ValueKey<String>(
                          'works-status-content-canvas-${post.id}',
                        ),
                        child: _buildPostCanvas(
                          post,
                          enableArticlePageCurl: enableArticlePageCurl,
                        ),
                      ),
                    );
                  },
                ),
              ),

              _buildEdgeDismissHotzone(TabSwipeDirection.previous),
              _buildEdgeDismissHotzone(TabSwipeDirection.next),

              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: DecoratedBox(
                  decoration: topChromeTheme.hasSurfaceDecoration
                      ? BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: <Color>[
                              topChromeTheme.surfaceColor!,
                              topChromeTheme.surfaceColor!.withValues(
                                alpha: 0.94,
                              ),
                              topChromeTheme.surfaceColor!.withValues(alpha: 0),
                            ],
                            stops: const <double>[0, 0.68, 1],
                          ),
                          border: Border(
                            bottom: BorderSide(
                              color: topChromeTheme.surfaceBorderColor!,
                              width: AppSpacing.hairline,
                            ),
                          ),
                        )
                      : const BoxDecoration(),
                  child: Padding(
                    padding: EdgeInsets.only(top: widget.topChromeSafeInset),
                    child: _WorksPrimaryTopBar(
                      layoutSpec: currentLayoutSpec,
                      foregroundColor: topChromeTheme.foregroundColor,
                      onTapClose: _dismissViewer,
                      onTapMore: () => _showWorksMoreSheet(context),
                      onHorizontalDragEnd: _handlePrimaryTabSwipeDragEnd,
                    ),
                  ),
                ),
              ),

              if (currentPost != null && _showsCaptionOverlay(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: ImmersiveEngagementBar.overlayClearance(
                    context,
                    gap: AppSpacing.containerSm,
                  ),
                  child: MediaCaptionBlock(
                    layoutSpec: currentLayoutSpec,
                    railKey: const ValueKey<String>('works-caption-rail'),
                    header: counterIndicator,
                    title: overlayTitle,
                    caption: overlayBody,
                    isExpanded: _isCaptionExpanded(currentPost.id),
                    onToggle: () => _toggleCaptionExpanded(currentPost.id),
                  ),
                ),

              // 文章页码：正文下方、作者工具栏上方（V1.0：`‹ 1 / 6 ›`，chevron 可点切页）。
              if (currentPost != null && _isArticleLikePost(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: ImmersiveEngagementBar.overlayClearance(
                    context,
                    gap: AppSpacing.intraGroupSm,
                  ),
                  child: Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-prev',
                          ),
                          icon: CupertinoIcons.chevron_back,
                          enabled: progress.current > 1,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, -1),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.workArticlePageProgress(
                            progress.current,
                            progress.total,
                          ),
                          key: const ValueKey<String>(
                            'works-article-page-progress',
                          ),
                          style: TextStyle(
                            color: topChromeTheme.mutedForegroundColor,
                            fontSize: AppTypography.xs,
                            fontWeight: AppTypography.medium,
                            fontFeatures: const [FontFeature.tabularFigures()],
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-next',
                          ),
                          icon: CupertinoIcons.chevron_forward,
                          enabled: progress.current < progress.total,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, 1),
                        ),
                      ],
                    ),
                  ),
                ),

              if (currentPost != null && widget.showWorksToolbar)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: ImmersiveEngagementBar(
                    layoutSpec: currentEngagementLayoutSpec,
                    avatarUrl: currentPost.avatarUrl,
                    displayName: currentPost.displayName,
                    authorBadge: _workItemFor(currentPost).authorBadge ?? '',
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
                    intersectionSummary: _intersectionSummaryFor(currentPost),
                    onIntersectionTap: () =>
                        _showIntersectionDetail(context, currentPost),
                    onUserTap: () {
                      // §7.3 旅程无断点：携该作品的最强证据组 kind 跳作者主页高亮。
                      ref
                          .read(intersectionHighlightIntentProvider.notifier)
                          .primeFromReasons(
                            currentPost.subAccountId,
                            currentPost.intersectionReasons,
                          );
                      widget.onUserTap(
                        currentPost.subAccountId,
                        avatarUrl: currentPost.avatarUrl,
                        displayName: currentPost.displayName,
                        backgroundUrl: currentPost.authorBackgroundUrl,
                      );
                    },
                    onFollowTap: () => _onFollow(currentPost),
                    onLikeTap: () => _onLike(currentPost),
                    onCommentTap: () => _openCommentFor(currentPost.id),
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

  Widget _buildPostCanvas(
    PostBaseDto post, {
    required bool enableArticlePageCurl,
  }) {
    return _buildTypedCanvas(
      post,
      enableArticlePageCurl: enableArticlePageCurl,
    );
  }

  Widget _buildLoadMoreSentinel({
    required bool isLoading,
    required Object? error,
    required VoidCallback onRetry,
  }) {
    final hasError = error != null;
    return ColoredBox(
      key: const ValueKey<String>('works-load-more-sentinel'),
      color: AppColors.black,
      child: Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasError)
                AppListAppendErrorFooter(
                  key: const ValueKey<String>('works-load-more-retry'),
                  semantic: runtime_error_display.runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.listAppend,
                    scope: UiErrorScope.section,
                    presentation: UiErrorPresentation.appendFooter,
                  ),
                  onAction: isLoading
                      ? null
                      : (action) async {
                          if (action.type == UiErrorActionType.retry ||
                              action.type == UiErrorActionType.resubmit) {
                            onRetry();
                          }
                        },
                )
              else ...[
                const CupertinoActivityIndicator(radius: 16),
                SizedBox(height: AppSpacing.containerSm),
                Text(
                  '正在加载更多精品内容',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.body,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  '继续停留即可自动预取新一批内容',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.iosSubheadline,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTypedCanvas(
    PostBaseDto post, {
    required bool enableArticlePageCurl,
  }) {
    if (_isImageLikePost(post)) {
      return _WorksPhotoCanvas(
        post: post,
        initialIndex: _photoInnerIndex[post.id] ?? _defaultImageIndexFor(post),
        onImageChanged: (index) =>
            setState(() => _photoInnerIndex[post.id] = index),
        onOverflowPrevious: null,
        onOverflowNext: null,
      );
    }
    if (_isVideoLikePost(post)) {
      return _WorksVideoCanvas(
        post: post,
        items: _videoItemsFor(post),
        onEpisodeChanged: (idx) =>
            setState(() => _videoInnerIndex[post.id] = idx),
        onActiveControllerChanged: (episodeIndex, controller) =>
            _handleActiveVideoController(
              '${post.id}-$episodeIndex',
              controller,
            ),
      );
    }
    if (_isArticleLikePost(post)) {
      final article = _articleViewFor(post);
      if (_shouldShowArticleHydrationError(post, article)) {
        return AppPageErrorState(
          key: ValueKey<String>('article-hydration-error-${post.id}'),
          semantic: _articleHydrationErrorSemantic(post),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _maybeHydrateArticleDetail(post, force: true);
            }
          },
        );
      }
      final safeInitialPage = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, article.pages.length - 1)
          .toInt();
      return _WorksArticleCanvas(
        post: post,
        article: article,
        timeLine: ContentTimeLabel.readerLine(
          createdAt: post.createdAt,
          updatedAt: post.updatedAt,
        ),
        paperTexture: _resolveArticlePaperTexture(post),
        enablePageCurl: enableArticlePageCurl,
        initialPage: safeInitialPage,
        topChromeSafeInset: widget.topChromeSafeInset,
        onPageChanged: (index) => _handleArticleInnerPageChanged(post, index),
        onResolvedPageCountChanged: (pageCount) =>
            _handleResolvedArticlePageCount(post.id, pageCount),
        onFallbackResolved: (reason) =>
            _trackArticleReaderFallback(post, reason, bookReaderEnabled: true),
        onPageFlipCommitted: (event) =>
            _trackArticlePageFlipCommit(post, event),
        onPageCurlAborted: (event) => _trackArticlePageCurlAbort(post, event),
        onEntityTap: _handleArticleEntityTap,
        onOverflowPrevious: null,
        onOverflowNext: null,
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

  /// 页码 chevron 切页（V1.0 `‹ n / m ›`）：更新 inner index 后由
  /// `_WorksArticleCanvas.initialPage` 驱动 deck `didUpdateWidget` 跳页，
  /// 不引入第二套翻页控制通路。
  void _stepArticlePage(PostBaseDto post, int delta) {
    final total = _articlePageCount(post);
    final current = (_articleInnerIndex[post.id] ?? 0).clamp(0, total - 1);
    final next = (current + delta).clamp(0, total - 1).toInt();
    if (next == current) return;
    setState(() => _articleInnerIndex[post.id] = next);
  }

  void _handleArticleInnerPageChanged(PostBaseDto post, int index) {
    final previousIndex = _articleInnerIndex[post.id] ?? 0;
    if (previousIndex != index) {
      _trackArticlePageFlipCommit(
        post,
        ArticleReaderPageFlipCommit(
          fromPage: previousIndex,
          toPage: index,
          durationMs: 0,
          mechanism: 'page_curl',
        ),
      );
    }
    setState(() => _articleInnerIndex[post.id] = index);
  }

  void _openCommentFor(String postId) {
    setState(() => _commentSplitPostId = postId);
  }

  Widget _buildCommentSplitContent(PostBaseDto post) {
    return ColoredBox(
      color: AppColors.worksBackground,
      child: _buildPostCanvas(
        post,
        enableArticlePageCurl: _enableArticlePageCurl,
      ),
    );
  }

  PostBaseDto? _postById(List<PostBaseDto> posts, String postId) {
    for (final post in posts) {
      if (post.id == postId) {
        return post;
      }
    }
    return null;
  }

  void _sharePost(
    BuildContext ctx,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.shareRecord, () {
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
    });
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
      ContentShareAction(id: 'copy_link', label: UITextConstants.copyLink),
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
    final surfaceView = ContentSurfaceViewMapper.fromDto(post, wire: raw);
    return ContentShareTemplateBuilder.build(
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
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

@immutable
class _WorksTopChromeTheme {
  const _WorksTopChromeTheme({
    required this.overlayStyle,
    required this.foregroundColor,
    required this.mutedForegroundColor,
    this.surfaceColor,
    this.surfaceBorderColor,
  });

  final SystemUiOverlayStyle overlayStyle;
  final Color foregroundColor;
  final Color mutedForegroundColor;
  final Color? surfaceColor;
  final Color? surfaceBorderColor;

  bool get hasSurfaceDecoration =>
      surfaceColor != null && surfaceBorderColor != null;
}

/// Work Browser 顶部栏（V1.0）：极简，仅「返回」与「更多」。
/// 禁止媒体类型指示、页码、形态 tab；媒体筛选入口收敛到「更多」菜单。
/// 顶栏空白区保留横滑手势用于宿主一级 tab 切换（首页嵌入态）。
class _WorksPrimaryTopBar extends StatelessWidget {
  const _WorksPrimaryTopBar({
    required this.layoutSpec,
    required this.onHorizontalDragEnd,
    required this.foregroundColor,
    this.onTapClose,
    this.onTapMore,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final GestureDragEndCallback onHorizontalDragEnd;
  final Color foregroundColor;
  final VoidCallback? onTapClose;
  final VoidCallback? onTapMore;

  @override
  Widget build(BuildContext context) {
    return ImmersiveViewerLayout.alignToRail(
      context: context,
      layoutSpec: layoutSpec,
      child: SizedBox(
        key: const ValueKey<String>('works-top-rail'),
        width: double.infinity,
        height: AppSpacing.appChromeTopBarHeight(context),
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onHorizontalDragEnd: onHorizontalDragEnd,
                child: const SizedBox.expand(),
              ),
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
                      foregroundColor: foregroundColor,
                    ),
                  ),
                ),
              ),
            ),

            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: KeyedSubtree(
                  key: const ValueKey<String>('works-top-more'),
                  child: ImmersiveToolbarIconButton(
                    icon: CupertinoIcons.ellipsis,
                    onPressed: onTapMore,
                    foregroundColor: foregroundColor,
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
  static const double _overflowEdgeStartInset =
      AppSpacing.minInteractiveSize / 2;
  static const double _photoBoundaryRubberBandMaxOffset =
      AppSpacing.buttonHeight;
  static const Duration _photoBoundaryResetDuration = Duration(
    milliseconds: 220,
  );

  late final PageController _imgController;
  double _edgeOverflowDistance = 0;
  double _boundaryRubberBandRawOffset = 0;
  double _boundaryRubberBandOffset = 0;
  TabSwipeDirection? _pendingOverflowDirection;
  bool _overflowTriggered = false;
  bool _shouldAnimateBoundaryReset = false;
  Offset? _dragStartLocalPosition;

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

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _precacheNeighborImages(_safeInitialIndex);
  }

  @override
  void didUpdateWidget(covariant _WorksPhotoCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.post != oldWidget.post ||
        widget.initialIndex != oldWidget.initialIndex) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _precacheNeighborImages(_safeInitialIndex);
      });
    }
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

  double _pageWidthForConstraints(BoxConstraints constraints) {
    if (constraints.maxWidth.isFinite && constraints.maxWidth > 0) {
      return constraints.maxWidth;
    }
    return MediaQuery.of(context).size.width;
  }

  void _precacheNeighborImages(int centerIndex) {
    final images = _images;
    for (final index in <int>[centerIndex - 1, centerIndex, centerIndex + 1]) {
      if (index < 0 || index >= images.length) {
        continue;
      }
      final url = images[index];
      if (url.isEmpty) {
        continue;
      }
      final candidates = resolveContentMediaUrlCandidates(url);
      if (_shouldSkipLocalPrecache(candidates)) {
        continue;
      }
      unawaited(_precacheImageCandidates(candidates));
    }
  }

  bool _shouldSkipLocalPrecache(List<String> candidates) {
    return candidates.isNotEmpty &&
        candidates.every(isPrivateDevContentMediaUrl);
  }

  Future<void> _precacheImageCandidates(List<String> candidates) async {
    for (final candidate in candidates) {
      try {
        final url = candidate;
        await precacheImage(CachedNetworkImageProvider(url), context);
        return;
      } catch (_) {
        continue;
      }
    }
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

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) {
      return 0;
    }
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  void _setBoundaryRubberBandOffset(
    double visualOffset, {
    required bool animate,
    double? rawOffset,
  }) {
    final safeVisualOffset = visualOffset.abs() < 0.1 ? 0.0 : visualOffset;
    final safeRawOffset =
        rawOffset ??
        (safeVisualOffset == 0.0 ? 0.0 : _boundaryRubberBandRawOffset);
    if ((_boundaryRubberBandOffset - safeVisualOffset).abs() < 0.1 &&
        (_boundaryRubberBandRawOffset - safeRawOffset).abs() < 0.1 &&
        _shouldAnimateBoundaryReset == animate) {
      return;
    }
    setState(() {
      _boundaryRubberBandOffset = safeVisualOffset;
      _boundaryRubberBandRawOffset = safeRawOffset;
      _shouldAnimateBoundaryReset = animate;
    });
  }

  void _applyBoundaryRubberBand(
    DragUpdateDetails details,
    TabSwipeDirection direction,
  ) {
    final nextRaw = direction == TabSwipeDirection.previous
        ? (_boundaryRubberBandRawOffset + details.delta.dx).clamp(
            0.0,
            double.infinity,
          )
        : (_boundaryRubberBandRawOffset + details.delta.dx).clamp(
            double.negativeInfinity,
            0.0,
          );
    final magnitude = _springDampedOffset(
      nextRaw.abs(),
      _photoBoundaryRubberBandMaxOffset,
    );
    final visualOffset = direction == TabSwipeDirection.previous
        ? magnitude
        : -magnitude;
    _setBoundaryRubberBandOffset(
      visualOffset,
      animate: false,
      rawOffset: nextRaw.toDouble(),
    );
  }

  void _resetBoundaryRubberBand({required bool animate}) {
    _setBoundaryRubberBandOffset(0, animate: animate, rawOffset: 0);
  }

  void _trackEdgeOverflow(
    DragUpdateDetails details,
    List<String> images,
    double pageWidth,
  ) {
    if (!_imgController.hasClients) {
      return;
    }
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
      _resetBoundaryRubberBand(animate: false);
      _edgeOverflowDistance = 0;
      _pendingOverflowDirection = null;
      return;
    }
    _applyBoundaryRubberBand(details, direction);
    if (!_isEdgeOverflowStart(direction, pageWidth)) {
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

  bool _isEdgeOverflowStart(TabSwipeDirection direction, double width) {
    final startPosition = _dragStartLocalPosition;
    if (startPosition == null) {
      return false;
    }
    return switch (direction) {
      TabSwipeDirection.previous =>
        widget.onOverflowPrevious != null &&
            startPosition.dx <= _overflowEdgeStartInset,
      TabSwipeDirection.next =>
        widget.onOverflowNext != null &&
            startPosition.dx >= width - _overflowEdgeStartInset,
    };
  }

  void _onHorizontalDragDown(DragDownDetails details) {
    _dragStartLocalPosition = details.localPosition;
    if (_imgController.hasClients) {
      _imgController.jumpTo(_imgController.offset);
    }
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: false);
  }

  void _onHorizontalDragUpdate(DragUpdateDetails details, double pageWidth) {
    final images = _images;
    if (images.length > 1 && _imgController.hasClients) {
      final maxOffset = (images.length - 1) * pageWidth;
      _imgController.jumpTo(
        (_imgController.offset - details.delta.dx).clamp(0.0, maxOffset),
      );
    }
    _trackEdgeOverflow(details, images, pageWidth);
  }

  Duration _settleDuration({
    required int targetPage,
    required double pageWidth,
    required double velocity,
  }) {
    if (!_imgController.hasClients || pageWidth <= 0) {
      return const Duration(milliseconds: 180);
    }
    final targetOffset = targetPage * pageWidth;
    final distance = (targetOffset - _imgController.offset).abs();
    final distanceRatio = (distance / pageWidth).clamp(0.0, 1.0).toDouble();
    final fastFling = velocity.abs() >= 700;
    final milliseconds = fastFling
        ? 140 + distanceRatio * 80
        : 160 + distanceRatio * 100;
    return Duration(milliseconds: milliseconds.clamp(140, 260).round().toInt());
  }

  void _onHorizontalDragEnd(DragEndDetails details, double pageWidth) {
    final images = _images;
    final maxOffset = images.length <= 1
        ? 0.0
        : (images.length - 1) * pageWidth;
    final currentOffset = _imgController.hasClients ? _imgController.offset : 0;
    final atLeadingEdge = currentOffset <= AppSpacing.hairline;
    final atTrailingEdge = currentOffset >= maxOffset - AppSpacing.hairline;
    final velocity = details.primaryVelocity ?? 0;

    if (!_overflowTriggered && velocity.abs() >= _overflowSwitchVelocity) {
      if (velocity > 0 &&
          atLeadingEdge &&
          _isEdgeOverflowStart(TabSwipeDirection.previous, pageWidth)) {
        _triggerOverflow(TabSwipeDirection.previous);
      } else if (velocity < 0 &&
          atTrailingEdge &&
          _isEdgeOverflowStart(TabSwipeDirection.next, pageWidth)) {
        _triggerOverflow(TabSwipeDirection.next);
      }
    }

    if (!_overflowTriggered && images.length > 1 && _imgController.hasClients) {
      final currentPage = pageWidth <= 0 ? 0.0 : currentOffset / pageWidth;
      final int targetPage;
      if (velocity < -500) {
        targetPage = (currentPage.round() + 1).clamp(0, images.length - 1);
      } else if (velocity > 500) {
        targetPage = (currentPage.round() - 1).clamp(0, images.length - 1);
      } else {
        targetPage = currentPage.round().clamp(0, images.length - 1);
      }
      _precacheNeighborImages(targetPage);
      _imgController.animateToPage(
        targetPage,
        duration: _settleDuration(
          targetPage: targetPage,
          pageWidth: pageWidth,
          velocity: velocity,
        ),
        curve: Curves.easeOutCubic,
      );
    }

    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: true);
    _dragStartLocalPosition = null;
  }

  void _onHorizontalDragCancel() {
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: true);
    _dragStartLocalPosition = null;
  }

  @override
  Widget build(BuildContext context) {
    final images = _images;
    final handlesHorizontalOverflow =
        images.length > 1 ||
        widget.onOverflowPrevious != null ||
        widget.onOverflowNext != null;
    return LayoutBuilder(
      builder: (context, constraints) {
        final pageWidth = _pageWidthForConstraints(constraints);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onHorizontalDragDown: handlesHorizontalOverflow
              ? _onHorizontalDragDown
              : null,
          onHorizontalDragUpdate: handlesHorizontalOverflow
              ? (details) => _onHorizontalDragUpdate(details, pageWidth)
              : null,
          onHorizontalDragEnd: handlesHorizontalOverflow
              ? (details) => _onHorizontalDragEnd(details, pageWidth)
              : null,
          onHorizontalDragCancel: handlesHorizontalOverflow
              ? _onHorizontalDragCancel
              : null,
          child: AnimatedContainer(
            key: const ValueKey<String>('works-photo-stage'),
            duration: _shouldAnimateBoundaryReset
                ? _photoBoundaryResetDuration
                : Duration.zero,
            curve: Curves.easeOutCubic,
            transform: Matrix4.translationValues(
              _boundaryRubberBandOffset,
              0,
              0,
            ),
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
                    _precacheNeighborImages(i);
                    widget.onImageChanged(i);
                  },
                  itemBuilder: (context, i) {
                    if (images.isEmpty) {
                      return Container(color: AppColors.worksBackground);
                    }
                    return AppCachedNetworkImage(
                      imageUrl: images[i],
                      imageUrlCandidates: resolveContentMediaUrlCandidates(
                        images[i],
                      ),
                      fit: BoxFit.cover,
                      placeholder: Container(color: AppColors.worksBackground),
                      errorWidget: Container(color: AppColors.worksBackground),
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
          ),
        );
      },
    );
  }
}

/// 视频作品画布（V1.0）：全屏沉浸视频；作品内分集横滑切换（mediaItems 契约序列）；
/// 默认控件被禁用，播放控制由 caption header 的极简控制条承载；
/// 点击视频区域切换播放/暂停。
class _WorksVideoCanvas extends StatefulWidget {
  const _WorksVideoCanvas({
    required this.post,
    required this.items,
    required this.onEpisodeChanged,
    required this.onActiveControllerChanged,
  });

  final PostBaseDto post;
  final List<WorkBrowserMediaItemDto> items;
  final ValueChanged<int> onEpisodeChanged;
  final void Function(int episodeIndex, VideoPlayerController? controller)
  onActiveControllerChanged;

  @override
  State<_WorksVideoCanvas> createState() => _WorksVideoCanvasState();
}

class _WorksVideoCanvasState extends State<_WorksVideoCanvas> {
  late final PageController _episodeController;
  int _currentEpisodeIndex = 0;
  final Map<int, VideoPlayerController> _controllersByIndex =
      <int, VideoPlayerController>{};

  @override
  void initState() {
    super.initState();
    _episodeController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onEpisodeChanged(0);
    });
  }

  @override
  void dispose() {
    _episodeController.dispose();
    super.dispose();
  }

  void _registerController(int index, VideoPlayerController controller) {
    _controllersByIndex[index] = controller;
    if (index == _currentEpisodeIndex) {
      widget.onActiveControllerChanged(index, controller);
    }
  }

  void _togglePlayback(int index) {
    final controller = _controllersByIndex[index];
    if (controller == null || !controller.value.isInitialized) return;
    if (controller.value.isPlaying) {
      controller.pause();
    } else {
      controller.play();
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = widget.items;
    if (items.isEmpty) {
      return Container(color: AppColors.worksBackground);
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _episodeController,
          scrollDirection: Axis.horizontal,
          allowImplicitScrolling: true,
          itemCount: items.length,
          onPageChanged: (index) {
            setState(() => _currentEpisodeIndex = index);
            widget.onEpisodeChanged(index);
            widget.onActiveControllerChanged(index, _controllersByIndex[index]);
          },
          itemBuilder: (context, index) {
            final item = items[index];
            if (item.url.isEmpty) {
              return Container(color: AppColors.worksBackground);
            }
            return _KeepAliveStage(
              key: ValueKey<String>(
                'works-video-stage-${widget.post.id}-$index',
              ),
              child: VideoPlayerWidget(
                key: ValueKey<String>('works-video-${widget.post.id}-$index'),
                videoUrl: item.url,
                thumbnailUrl: item.coverUrl,
                autoPlay: index == _currentEpisodeIndex,
                showControls: false,
                onTap: () => _togglePlayback(index),
                onControllerCreated: (controller) =>
                    _registerController(index, controller),
              ),
            );
          },
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
}

class _KeepAliveStage extends StatefulWidget {
  const _KeepAliveStage({super.key, required this.child});

  final Widget child;

  @override
  State<_KeepAliveStage> createState() => _KeepAliveStageState();
}

class _KeepAliveStageState extends State<_KeepAliveStage>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return widget.child;
  }
}

class _WorksArticleCanvas extends StatelessWidget {
  const _WorksArticleCanvas({
    required this.post,
    required this.article,
    required this.timeLine,
    required this.paperTexture,
    required this.enablePageCurl,
    required this.onPageChanged,
    required this.onResolvedPageCountChanged,
    required this.topChromeSafeInset,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onEntityTap,
    this.initialPage = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final ContentArticleRender article;
  final String timeLine;
  final ArticlePaperTexture paperTexture;
  final bool enablePageCurl;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onResolvedPageCountChanged;
  final double topChromeSafeInset;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    final topPaperReservedHeight =
        topChromeSafeInset +
        AppSpacing.appChromeTopBarHeight(context) +
        AppSpacing.intraGroupSm;
    final stagePadding = EdgeInsets.only(top: topPaperReservedHeight);
    final palette = resolveArticlePaperPalette(context, paperTexture);
    // Work Browser V1.0 Dark Paper：文章默认延续深色沉浸背景，
    // 翻页正面、背面、底页都消费同一 paperTexture。
    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(brightness: Brightness.dark),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ColoredBox(color: palette.stageBackground),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: ImmersiveEngagementBar.overlayClearance(
              context,
              gap: AppSpacing.containerMd,
            ),
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
                  paperTexture: paperTexture,
                );
                onResolvedPageCountChanged(pages.length.clamp(1, 99).toInt());
                final maxIndex = pages.isEmpty ? 0 : pages.length - 1;
                final safeInitialPage = pages.isEmpty
                    ? 0
                    : initialPage.clamp(0, maxIndex).toInt();
                final metrics = resolveArticleCanvasMetrics(
                  context,
                  constraints,
                  variant: ArticleCanvasVariant.immersive,
                );
                return ArticleReaderFlipHost(
                  adapter: ImmersiveBrowserReaderAdapter(
                    ArticleReaderHostConfig(
                      pages: pages,
                      template: article.template,
                      fontPreset: article.fontPreset,
                      metrics: metrics,
                      coverUrl: post.primaryImageUrl,
                      initialPage: safeInitialPage,
                      enablePageCurl: enablePageCurl,
                      pagePadding: stagePadding,
                      headerLabel: timeLine,
                      showFooterPageLabel: false,
                      paperTexture: paperTexture,
                      presentationStyle:
                          ArticleReadOnlyBookDeckPresentationStyle.immersive,
                      onPageChanged: onPageChanged,
                      onOverflowPrevious: onOverflowPrevious,
                      onOverflowNext: onOverflowNext,
                      onFallbackResolved: onFallbackResolved,
                      onPageFlipCommitted: onPageFlipCommitted,
                      onPageCurlAborted: onPageCurlAborted,
                      onEntityTap: onEntityTap,
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
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
              child: AppCachedNetworkImage(
                imageUrl: imageUrl!,
                imageUrlCandidates: resolveContentMediaUrlCandidates(imageUrl!),
                fit: BoxFit.cover,
                placeholder: Container(color: AppColors.worksBackground),
                errorWidget: Container(color: AppColors.worksBackground),
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
              bottom: ImmersiveEngagementBar.overlayClearance(
                context,
                gap: AppSpacing.containerMd,
              ),
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
