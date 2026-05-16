import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/media/video/viewer/immersive_video_viewer.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

class VideoDetailPage extends ConsumerStatefulWidget {
  const VideoDetailPage({
    super.key,
    required this.initialIndex,
    this.initialExtra,
  });

  final int initialIndex;
  final MediaViewerExtra? initialExtra;

  @override
  ConsumerState<VideoDetailPage> createState() => _VideoDetailPageState();
}

class _VideoDetailPageState extends ConsumerState<VideoDetailPage> {
  bool _isOpen = true;
  List<PostSummaryView> _posts = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    if (widget.initialExtra != null) {
      _posts = widget.initialExtra!.posts;
      _isLoading = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        primeMediaViewerInteractionSnapshot(
          ref,
          widget.initialExtra!.interactionSnapshot,
        );
      });
    } else {
      _loadData();
    }
  }

  int get _safeInitialIndex =>
      (widget.initialExtra?.initialIndex ?? widget.initialIndex).clamp(
        0,
        _posts.isNotEmpty ? _posts.length - 1 : 0,
      );

  Future<void> _loadData() async {
    try {
      final dtos = await ref
          .read(contentRepositoryProvider)
          .listDiscoveryFeed(category: 'video', limit: 50);
      applyConfirmedInteractionPosts(ref, dtos);
      _posts = dtos
          .map(
            (dto) => PostSummaryView.fromDto(
              dto,
              surfaceId: PostReadSurfaceId.detailVideo,
            ),
          )
          .toList(growable: false);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    final isDark = ref.watch(isDarkProvider);
    if (_isLoading) {
      return AppScaffold(
        backgroundColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }
    if (!_isOpen || _posts.isEmpty) {
      return AppScaffold(
        backgroundColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        child: Center(
          child: CupertinoButton(
            onPressed: () => context.pop(),
            child: Text(AppStrings.back),
          ),
        ),
      );
    }

    final feedCategory = widget.initialExtra?.category;
    final isMoment =
        widget.initialExtra?.category == 'moment' ||
        widget.initialExtra?.category == 'profile_moment';
    if (feedCategory != null && feedCategory.isNotEmpty) {
      ref.listen<AsyncValue<DiscoveryFeedState>>(
        discoveryFeedProvider(feedCategory),
        (prev, next) {
          final value = next.value;
          if (value != null && value.items.length > _posts.length && mounted) {
            setState(() {
              _posts = value.items
                  .map(
                    (dto) => PostSummaryView.fromDto(
                      dto,
                      surfaceId: PostReadSurfaceId.detailVideo,
                    ),
                  )
                  .toList(growable: false);
            });
          }
        },
      );
    }

    final mediaItems = _posts
        .map<MediaItem>((post) {
          final videoUrl = post.videoUrl ?? '';
          return MediaItem(
            type: 'video',
            url: videoUrl.isNotEmpty
                ? videoUrl
                : 'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4',
            aspectRatio: post.videoType == 'vertical' ? 9 / 16 : 16 / 9,
          );
        })
        .toList(growable: false);

    return ImmersiveVideoViewer(
      isOpen: _isOpen,
      onClose: () {
        setState(() => _isOpen = false);
        context.pop();
      },
      mediaItems: mediaItems,
      initialIndex: _safeInitialIndex,
      posts: _posts,
      initialPostIndex: _safeInitialIndex,
      toolbarMode: isMoment ? 'backOnly' : 'full',
      onUserClick: (username, {avatarUrl, displayName, backgroundUrl}) {
        context.push(
          '/user/$username',
          extra: UserProfileRouteExtra(
            avatar: avatarUrl,
            displayName: displayName,
            backgroundImage: backgroundUrl,
          ),
        );
      },
      followingUsers: ref
          .watch(userRelationshipStateProvider)
          .followingSubAccountIds,
      onFollowClick: (subAccountId, _) => syncProfileFollowIntent(
        ref,
        subAccountId: subAccountId,
        isFollowing: !effectiveProfileFollowing(ref, subAccountId),
      ),
      likedPosts: ref.watch(postInteractionStateProvider).likedPostIds,
      savedPosts: ref.watch(postInteractionStateProvider).savedPostIds,
      getPostLikesCount: (post) {
        return effectivePostLikeCount(ref, post.id, fallback: post.likesCount);
      },
      getPostBookmarksCount: (post) {
        return effectivePostBookmarkCount(
          ref,
          post.id,
          fallback: post.savesCount,
        );
      },
      getPostCommentsCount: (post) {
        return effectivePostCommentCount(
          ref,
          post.id,
          fallback: post.commentsCount,
        );
      },
      getPostSharesCount: (post) {
        return effectivePostShareCount(
          ref,
          post.id,
          fallback: post.sharesCount,
        );
      },
      onLikeClick: (post) {
        final wasLiked = effectivePostLiked(ref, post.id);
        final currentLikeCount = effectivePostLikeCount(
          ref,
          post.id,
          fallback: post.likesCount,
        );
        syncPostLikeIntent(
          ref,
          postId: post.id,
          isLiked: !wasLiked,
          likeCount: wasLiked
              ? (currentLikeCount - 1).clamp(0, 1 << 31).toInt()
              : currentLikeCount + 1,
        );
      },
      onSaveClick: (post) {
        final wasSaved = effectivePostSaved(ref, post.id);
        final currentBookmarkCount = effectivePostBookmarkCount(
          ref,
          post.id,
          fallback: post.savesCount,
        );
        syncPostSaveIntent(
          ref,
          postId: post.id,
          isSaved: !wasSaved,
          bookmarkCount: wasSaved
              ? (currentBookmarkCount - 1).clamp(0, 1 << 31).toInt()
              : currentBookmarkCount + 1,
        );
      },
      onAssistantClick: () {
        final target = VisitTarget.page('discovery_video');
        final service = ref.read(visitRecorderServiceProvider);
        AssistantHalfSheet.show(
          context,
          AssistantOpenContext(
            source: AssistantSource.discovery,
            tab: 'video',
            visitTarget: target,
            experienceLevel: service.getExperience(target),
          ),
        );
      },
      onNearEnd: feedCategory != null && feedCategory.isNotEmpty
          ? () => ref
                .read(discoveryFeedMapProvider.notifier)
                .appendNextPage(feedCategory)
          : null,
    );
  }
}
