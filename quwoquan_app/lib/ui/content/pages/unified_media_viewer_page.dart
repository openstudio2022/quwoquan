import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

/// 侵入式媒体浏览；本页为薄壳，只读表面为 [PostReadSurfaceId.immersive]。
///
/// 标题/正文等统一经 [WorksImmersiveViewer] 与 [MediaViewerExtra.posts] 上的
/// [PostSummaryView.readPresentation]（及必要时 raw wire）解析，与
/// [PostReadProjectionFacade] 同管线；父页备注与 inventory 见
/// `post-projection-pipeline-inventory.md` §2（`unified_media_viewer_page` / `discovery_page`）。
class UnifiedMediaViewerPage extends StatelessWidget {
  const UnifiedMediaViewerPage({super.key, required this.extra});

  final MediaViewerExtra extra;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: AppColors.black,
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
