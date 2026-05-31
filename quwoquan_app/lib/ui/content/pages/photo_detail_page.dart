import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/media/image/viewer/immersive_image_viewer.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

class PhotoDetailPage extends ConsumerStatefulWidget {
  const PhotoDetailPage({
    super.key,
    required this.category,
    required this.initialIndex,
    this.initialExtra,
  });

  final String category;
  final int initialIndex;
  final MediaViewerExtra? initialExtra;

  @override
  ConsumerState<PhotoDetailPage> createState() => _PhotoDetailPageState();
}

class _PhotoDetailPageState extends ConsumerState<PhotoDetailPage> {
  bool _isOpen = true;
  List<ContentSurfaceView> _posts = [];
  bool _isLoading = true;
  String? _trackedContentId;

  @override
  void initState() {
    super.initState();
    if (widget.initialExtra != null) {
      _posts = widget.initialExtra!.posts;
      _isLoading = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        primeMediaViewerInteractionSnapshot(
          ref,
          widget.initialExtra!.interactionSnapshot,
        );
        _startEngagementTracking();
      });
    } else {
      _loadData();
    }
  }

  ContentType get _resolvedContentType {
    final cat = widget.initialExtra?.category;
    if (cat == 'moment' || cat == 'profile_moment') return ContentType.micro;
    if (_posts.isNotEmpty) {
      final idx = _safeInitialIndex;
      final post = _posts[idx];
      final postType = post.contentType;
      if (postType == 'micro') return ContentType.micro;
    }
    return ContentType.image;
  }

  void _startEngagementTracking() {
    if (_posts.isEmpty) return;
    final idx = _safeInitialIndex;
    final post = _posts[idx];
    _trackedContentId = post.postId;
    ref.read(contentEngagementTrackerProvider).trackContentEnter(
      post.postId,
      contentType: _resolvedContentType,
      referralSource: widget.initialExtra?.referralSource ?? ReferralSource.organicFeed,
      totalImages: post.images.isEmpty ? 1 : post.images.length,
      authorId: post.author.id,
      tags: post.tags,
      position: idx,
      feedRequestId: widget.initialExtra?.feedRequestId,
    );
  }

  @override
  void dispose() {
    if (_trackedContentId != null) {
      ref.read(contentEngagementTrackerProvider).trackContentExit(_trackedContentId!);
    }
    super.dispose();
  }

  int get _safeInitialIndex =>
      (widget.initialExtra?.initialIndex ?? widget.initialIndex).clamp(
        0,
        _posts.isNotEmpty ? _posts.length - 1 : 0,
      );

  Future<void> _loadData() async {
    try {
      final category = widget.category == 'images' ? 'images' : widget.category;
      final dtos = await ref
          .read(contentRepositoryProvider)
          .listDiscoveryFeed(category: category, limit: 100);
      applyConfirmedInteractionPosts(ref, dtos);
      _posts = dtos
          .map((dto) => ContentSurfaceViewMapper.fromDto(dto, wire: dto.toMap()))
          .toList(growable: false);
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
        _startEngagementTracking();
      }
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
    if (feedCategory != null && feedCategory.isNotEmpty) {
      ref.listen<AsyncValue<DiscoveryFeedState>>(
        discoveryFeedProvider(feedCategory),
        (prev, next) {
          final value = next.value;
          if (value != null && value.items.length > _posts.length && mounted) {
            setState(() {
              _posts = value.items
                  .map(
                    (dto) =>
                        ContentSurfaceViewMapper.fromDto(dto, wire: dto.toMap()),
                  )
                  .toList(growable: false);
            });
          }
        },
      );
    }

    final isMoment =
        widget.initialExtra?.category == 'moment' ||
        widget.initialExtra?.category == 'profile_moment';
    return ImmersiveImageViewer(
      isOpen: _isOpen,
      onClose: () {
        setState(() => _isOpen = false);
        context.pop();
      },
      mediaItems: const <MediaItem>[],
      initialIndex: _safeInitialIndex,
      posts: _posts,
      initialPostIndex: _safeInitialIndex,
      layoutMode: isMoment ? 'nested' : 'flat',
      initialImageIndex: widget.initialExtra?.initialImageIndex ?? 0,
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
      onFollowClick: (subAccountId, _) =>
          runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
            syncProfileFollowIntent(
              ref,
              subAccountId: subAccountId,
              isFollowing: !effectiveProfileFollowing(ref, subAccountId),
            );
          }),
      likedPosts: ref.watch(postInteractionStateProvider).likedPostIds,
      savedPosts: ref.watch(postInteractionStateProvider).savedPostIds,
      getPostLikesCount: (post) {
        return effectivePostLikeCount(
          ref,
          post.postId,
          fallback: post.stats.like,
        );
      },
      getPostBookmarksCount: (post) {
        return effectivePostBookmarkCount(
          ref,
          post.postId,
          fallback: post.stats.favorite,
        );
      },
      getPostCommentsCount: (post) {
        return effectivePostCommentCount(
          ref,
          post.postId,
          fallback: post.stats.comment,
        );
      },
      getPostSharesCount: (post) {
        return effectivePostShareCount(
          ref,
          post.postId,
          fallback: post.stats.share,
        );
      },
      onLikeClick: (post) {
        runWhenLoggedIn(ref, context, AuthGateReason.like, () {
          final wasLiked = effectivePostLiked(ref, post.postId);
          final currentLikeCount = effectivePostLikeCount(
            ref,
            post.postId,
            fallback: post.stats.like,
          );
          syncPostLikeIntent(
            ref,
            postId: post.postId,
            isLiked: !wasLiked,
            likeCount: wasLiked
                ? (currentLikeCount - 1).clamp(0, 1 << 31).toInt()
                : currentLikeCount + 1,
          );
        });
      },
      onSaveClick: (post) {
        runWhenLoggedIn(ref, context, AuthGateReason.favorite, () {
          final wasSaved = effectivePostSaved(ref, post.postId);
          final currentBookmarkCount = effectivePostBookmarkCount(
            ref,
            post.postId,
            fallback: post.stats.favorite,
          );
          syncPostSaveIntent(
            ref,
            postId: post.postId,
            isSaved: !wasSaved,
            bookmarkCount: wasSaved
                ? (currentBookmarkCount - 1).clamp(0, 1 << 31).toInt()
                : currentBookmarkCount + 1,
          );
        });
      },
      onAssistantClick: () {
        final target = VisitTarget.page('discovery_photo');
        final service = ref.read(visitRecorderServiceProvider);
        AssistantHalfSheet.show(
          context,
          AssistantOpenContext(
            source: AssistantSource.discovery,
            tab: 'photo',
            visitTarget: target,
            experienceLevel: service.getExperience(target),
            objectType: 'post',
          ),
        );
      },
      onNearEnd: feedCategory != null && feedCategory.isNotEmpty
          ? () => ref
                .read(discoveryFeedMapProvider.notifier)
                .appendNextPage(feedCategory)
          : null,
      onPostIndexChanged: (newIndex) {
        if (_trackedContentId != null) {
          ref.read(contentEngagementTrackerProvider).trackContentExit(_trackedContentId!);
        }
        if (newIndex >= 0 && newIndex < _posts.length) {
          final post = _posts[newIndex];
          _trackedContentId = post.postId;
          ref.read(contentEngagementTrackerProvider).trackContentEnter(
            post.postId,
            contentType: _resolvedContentType,
            referralSource: widget.initialExtra?.referralSource ?? ReferralSource.organicFeed,
            totalImages: post.images.isEmpty ? 1 : post.images.length,
            authorId: post.author.id,
            tags: post.tags,
            position: newIndex,
            feedRequestId: widget.initialExtra?.feedRequestId,
          );
        }
      },
      onImageIndexChanged: (imageIndex) {
        if (_trackedContentId != null) {
          ref.read(contentEngagementTrackerProvider).trackContentProgress(
            _trackedContentId!,
            currentImageIndex: imageIndex,
          );
        }
      },
    );
  }
}
