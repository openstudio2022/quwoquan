import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _startTrackingInitialPost();
    });
  }

  @override
  void dispose() {
    if (_trackedContentId != null) {
      ref
          .read(contentEngagementTrackerProvider)
          .trackContentExit(_trackedContentId!);
    }
    super.dispose();
  }

  ContentType _resolveContentType(PostSummaryView post) {
    final cat = widget.extra.category;
    if (cat == 'moment' || cat == 'profile_moment') return ContentType.moment;
    final typeStr = post.contentType;
    if (typeStr == 'video') return ContentType.video;
    if (typeStr == 'article') return ContentType.article;
    if (typeStr == 'moment') return ContentType.moment;
    return ContentType.photo;
  }

  ContentType _resolveContentTypeFromDto(PostBaseDto dto) {
    final cat = widget.extra.category;
    if (cat == 'moment' || cat == 'profile_moment') return ContentType.moment;
    if (dto is VideoPostDto) return ContentType.video;
    if (dto is ArticlePostDto) return ContentType.article;
    if (dto is MomentPostDto) return ContentType.moment;
    return ContentType.photo;
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

    final tracker = ref.read(contentEngagementTrackerProvider);
    if (_trackedContentId != null) {
      tracker.trackContentExit(_trackedContentId!);
    }

    String postId;
    ContentType contentType;
    String? authorId;
    List<String>? tags;
    int? totalImages;

    if (widget.extra.dtoPosts.isNotEmpty && index < widget.extra.dtoPosts.length) {
      final dto = widget.extra.dtoPosts[index];
      postId = dto.id;
      contentType = _resolveContentTypeFromDto(dto);
      authorId = dto.authorId;
      totalImages = (dto is PhotoPostDto) ? dto.imageUrls.length : null;
    } else if (widget.extra.posts.isNotEmpty && index < widget.extra.posts.length) {
      final post = widget.extra.posts[index];
      postId = post.id;
      contentType = _resolveContentType(post);
      authorId = post.authorId;
      tags = post.tags;
      totalImages = post.images?.length;
    } else {
      return;
    }

    _trackedContentId = postId;
    tracker.trackContentEnter(
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
    return CupertinoPageScaffold(
      backgroundColor: AppColors.black,
      child: WorksImmersiveViewer(
        showWorksToolbar: true,
        showTopNavigation: widget.extra.showWorksNavigation,
        externalPosts: widget.extra.dtoPosts,
        externalPostViews: widget.extra.posts,
        initialPostIndex: widget.extra.initialIndex,
        initialImageIndex: widget.extra.initialImageIndex,
        source: widget.extra.source,
        rawPostsById: widget.extra.rawPostsById,
        defaultCircleId: widget.extra.circleId,
        initialInteractionSnapshot: widget.extra.interactionSnapshot,
        onPostIndexChanged: (newIndex) {
          _trackPostAtIndex(newIndex);
        },
        onDismissed: (result) {
          if (context.canPop()) {
            context.pop(result);
          }
        },
        onUserTap: (
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
