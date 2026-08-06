import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Runtime composition from a Notification target into an App route.
class AppMessageNavigationTarget {
  const AppMessageNavigationTarget._(this.location);

  final String location;

  /// 评论系通知源（source 语义）：sourceId 为 commentId，target 为宿主 post。
  static const Set<String> _commentNotificationSources = <String>{
    'comment',
    'comment_mention',
    'comment_pin',
  };

  static AppMessageNavigationTarget? fromMessage(AppMessage message) {
    final target = message.target;
    final routeId = target.routeId?.trim() ?? '';
    final routePath = target.routePath?.trim() ?? '';
    final targetType = target.targetType.trim();
    final targetId = target.targetId.trim();
    if (targetType == 'report') {
      return const AppMessageNavigationTarget._(AppRoutePaths.myReports);
    }
    if (targetType == 'homepage' && targetId.isNotEmpty) {
      return AppMessageNavigationTarget._(
        AppRoutePaths.homepageDetail(id: targetId),
      );
    }
    if (routeId == 'myIntersections' ||
        routePath == AppRoutePaths.myIntersectionsPathTemplate ||
        targetId == 'myIntersections') {
      final dimension = target.query.dimension?.trim() ?? '';
      return AppMessageNavigationTarget._(
        AppRoutePaths.myIntersections(
          dimension: dimension.isEmpty ? null : dimension,
        ),
      );
    }
    // 评论/回复/@提及/置顶通知：进入宿主作品浏览器并深链定位到目标评论
    //（复用 MediaViewerCommentContext 唯一深链方言，与「我的评论」同源）。
    if (targetType == 'post' &&
        targetId.isNotEmpty &&
        _commentNotificationSources.contains(message.source.trim())) {
      final commentId = message.sourceId.trim();
      if (commentId.isNotEmpty) {
        return AppMessageNavigationTarget._(
          AppRoutePaths.workBrowser(
            workId: targetId,
            source: 'notification',
            openComments: 'true',
            commentEntrySource:
                MediaViewerCommentContext.entrySourceNotification,
            targetCommentId: commentId,
          ),
        );
      }
    }
    if (routePath.startsWith('/')) {
      return AppMessageNavigationTarget._(routePath);
    }
    return null;
  }
}
