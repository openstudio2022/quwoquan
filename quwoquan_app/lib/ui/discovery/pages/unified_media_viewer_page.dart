import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
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
        referralSource: widget.extra.referralSource,
        feedRequestId: widget.extra.feedRequestId,
        initialFeedPosition: widget.extra.position,
        rawPostsById: widget.extra.rawPostsById,
        initialInteractionSnapshot: widget.extra.interactionSnapshot,
        initialCommentContext: widget.extra.commentContext,
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
                AppRoutePaths.userProfile(username: userId),
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
