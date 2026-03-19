import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

class UnifiedMediaViewerPage extends StatelessWidget {
  const UnifiedMediaViewerPage({super.key, required this.extra});

  final MediaViewerExtra extra;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: Colors.black,
      child: Material(
        type: MaterialType.transparency,
        child: WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: extra.showWorksNavigation,
          externalPosts: extra.dtoPosts,
          externalPostViews: extra.posts,
          initialPostIndex: extra.initialIndex,
          initialImageIndex: extra.initialImageIndex,
          source: extra.source,
          rawPostsById: extra.rawPostsById,
          defaultCircleId: extra.circleId,
          initialInteractionSnapshot: extra.interactionSnapshot,
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
                    profileSubjectId: userId,
                    avatar: avatarUrl,
                    displayName: displayName,
                    backgroundImage: backgroundUrl,
                  ),
                );
              },
          onAssistantTap: () {},
        ),
      ),
    );
  }
}
