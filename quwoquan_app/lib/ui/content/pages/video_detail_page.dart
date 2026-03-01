import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/media/video/viewer/immersive_video_viewer.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

class VideoDetailPage extends ConsumerStatefulWidget {
  const VideoDetailPage({
    super.key,
    required this.initialIndex,
    required this.dataService,
    this.initialExtra,
  });

  final int initialIndex;
  final dynamic dataService;
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
    } else {
      _loadData();
    }
  }

  int get _safeInitialIndex =>
      (widget.initialExtra?.initialIndex ?? widget.initialIndex)
          .clamp(0, _posts.isNotEmpty ? _posts.length - 1 : 0);

  Future<void> _loadData() async {
    try {
      final posts = await widget.dataService.getDataList(
        endpoint: '/posts',
        params: {'category': 'video'},
        limit: 50,
      );
      _posts = (posts as List)
          .whereType<Map<String, dynamic>>()
          .map(projectPostMap)
          .toList(growable: false);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    if (_isLoading) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (!_isOpen || _posts.isEmpty) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: Center(
          child: ElevatedButton(onPressed: () => context.pop(), child: Text(AppStrings.back)),
        ),
      );
    }

    final discoveryState = ref.watch(discoveryStateProvider);
    final feedCategory = widget.initialExtra?.category;
    final isMoment = feedCategory == 'moment';
    if (feedCategory != null && feedCategory.isNotEmpty) {
      ref.listen<AsyncValue<DiscoveryFeedState>>(discoveryFeedProvider(feedCategory), (prev, next) {
        final value = next.value;
        if (value != null && value.items.length > _posts.length && mounted) {
          setState(() {
            _posts = value.items.map(PostSummaryView.fromDto).toList(growable: false);
          });
        }
      });
    }

    final mediaItems = _posts.map<MediaItem>((post) {
      final videoUrl = post.videoUrl ?? '';
      return MediaItem(
        type: 'video',
        url: videoUrl.isNotEmpty
            ? videoUrl
            : 'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4',
        aspectRatio: post.videoType == 'vertical' ? 9 / 16 : 16 / 9,
      );
    }).toList(growable: false);

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
      followingUsers: discoveryState.followingUsers,
      onFollowClick: (username, _) => ref.read(discoveryStateProvider).toggleFollow(username),
      likedPosts: discoveryState.likedPosts,
      savedPosts: discoveryState.savedPosts,
      getPostLikesCount: (post) {
        final n = discoveryState.getPostLikesCount(post.id);
        return n > 0 ? n : post.likesCount;
      },
      getPostBookmarksCount: (post) {
        final n = discoveryState.getPostBookmarksCount(post.id);
        return n > 0 ? n : post.savesCount;
      },
      onLikeClick: (post) {
        ref.read(discoveryStateProvider).toggleLike(post.id, baseLikesCount: post.likesCount);
      },
      onSaveClick: (post) {
        ref.read(discoveryStateProvider).toggleSave(post.id, baseBookmarksCount: post.savesCount);
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
          ? () => ref.read(discoveryFeedMapProvider.notifier).appendNextPage(feedCategory)
          : null,
    );
  }
}
