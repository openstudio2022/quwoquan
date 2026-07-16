import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

/// Immersive media viewer with engagement tracking.
class UnifiedMediaViewerPage extends ConsumerStatefulWidget {
  const UnifiedMediaViewerPage({super.key, required this.extra});

  final MediaViewerExtra extra;

  @override
  ConsumerState<UnifiedMediaViewerPage> createState() =>
      _UnifiedMediaViewerPageState();
}

class _UnifiedMediaViewerPageState
    extends ConsumerState<UnifiedMediaViewerPage> {
  String? _trackedContentId;
  late final ContentEngagementTracker _tracker;

  @override
  void initState() {
    super.initState();
    _tracker = ref.read(contentEngagementTrackerProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _startTrackingInitialPost();
    });
  }

  @override
  void dispose() {
    if (_trackedContentId != null) {
      _tracker.trackContentExit(_trackedContentId!);
    }
    super.dispose();
  }

  ContentType _resolveContentType(ContentSurfaceView post) {
    if (post.contentIdentity == 'moment') return ContentType.micro;
    switch (post.contentType) {
      case 'video':
        return ContentType.video;
      case 'article':
        return ContentType.article;
      case 'micro':
        return ContentType.micro;
      default:
        return ContentType.image;
    }
  }

  ContentType _resolveContentTypeFromDto(PostBaseDto dto) {
    if (dto.identity == 'moment') return ContentType.micro;
    switch (dto.type) {
      case 'video':
        return ContentType.video;
      case 'article':
        return ContentType.article;
      case 'micro':
        return ContentType.micro;
      default:
        return ContentType.image;
    }
  }

  void _startTrackingInitialPost() {
    final idx = widget.extra.initialIndex.clamp(0, _postCount - 1);
    _trackPostAtIndex(idx);
  }

  int get _postCount {
    if (widget.extra.dtoPosts.isNotEmpty) return widget.extra.dtoPosts.length;
    return widget.extra.posts.length;
  }

  void _trackPostAtIndex(int index) {
    if (index < 0) return;

    if (_trackedContentId != null) {
      _tracker.trackContentExit(_trackedContentId!);
    }

    String postId;
    ContentType contentType;
    String? authorId;
    List<String>? tags;
    int? totalImages;

    if (widget.extra.dtoPosts.isNotEmpty &&
        index < widget.extra.dtoPosts.length) {
      final dto = widget.extra.dtoPosts[index];
      postId = dto.id;
      contentType = _resolveContentTypeFromDto(dto);
      authorId = dto.authorId;
      totalImages = (dto is PhotoPostDto) ? dto.imageUrls.length : null;
    } else if (widget.extra.posts.isNotEmpty &&
        index < widget.extra.posts.length) {
      final post = widget.extra.posts[index];
      postId = post.postId;
      contentType = _resolveContentType(post);
      authorId = post.author.id;
      tags = post.tags;
      totalImages = post.images.length;
    } else {
      return;
    }

    _trackedContentId = postId;
    _tracker.trackContentEnter(
      postId,
      contentType: contentType,
      referralSource: widget.extra.referralSource,
      feedRequestId: widget.extra.feedRequestId,
      authorId: authorId,
      tags: tags,
      totalImages: totalImages,
      position: index,
    );
  }

  @override
  Widget build(BuildContext context) {
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final topChromeSafeInset = AppSpacing.appChromeTopSafeInset(
      safeTop,
      context,
    );
    return CupertinoPageScaffold(
      backgroundColor: AppColors.black,
      child: WorksImmersiveViewer(
        showWorksToolbar: true,
        showTopNavigation: widget.extra.showWorksNavigation,
        topChromeSafeInset: topChromeSafeInset,
        externalPosts: widget.extra.dtoPosts,
        externalPostViews: widget.extra.posts,
        initialPostIndex: widget.extra.initialIndex,
        initialImageIndex: widget.extra.initialImageIndex,
        source: widget.extra.source,
        rawPostsById: widget.extra.rawPostsById,
        initialInteractionSnapshot: widget.extra.interactionSnapshot,
        initialCommentContext: widget.extra.commentContext,
        onPostIndexChanged: (newIndex) {
          _trackPostAtIndex(newIndex);
        },
        onDismissed: (result) {
          if (context.canPop()) {
            context.pop(result);
          }
        },
        onUserTap:
            (
              userId, {
              String? avatarUrl,
              String? displayName,
              String? backgroundUrl,
            }) {
              context.push(
                '/user/$userId',
                extra: UserProfileRouteExtra(
                  subAccountId: userId,
                  avatar: avatarUrl,
                  displayName: displayName,
                  backgroundImage: backgroundUrl,
                ),
              );
            },
        onAssistantTap: () {},
      ),
    );
  }
}
