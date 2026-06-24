import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

String? buildProfileCommentDetailRoute({
  required String workId,
  required String source,
  required String entrySource,
  String? filter,
  required String commentId,
  String? parentCommentId,
  String? replyToCommentId,
}) {
  final cleanWorkId = workId.trim();
  final cleanCommentId = commentId.trim();
  if (cleanWorkId.isEmpty || cleanCommentId.isEmpty) {
    return null;
  }
  final cleanParentCommentId = parentCommentId?.trim() ?? '';
  final isReply = cleanParentCommentId.isNotEmpty;
  final route = Uri.parse(
    AppRoutePaths.workBrowser(
      workId: cleanWorkId,
      filter: filter?.trim().isNotEmpty == true ? filter!.trim() : null,
      source: source,
    ),
  );
  return route
      .replace(
        queryParameters: <String, String>{
          ...route.queryParameters,
          ...MediaViewerCommentContext.buildDeepLinkQuery(
            entrySource: entrySource,
            targetParentCommentId: isReply ? cleanParentCommentId : null,
            targetReplyId: isReply ? cleanCommentId : null,
            targetCommentId: isReply ? null : cleanCommentId,
            replyToCommentId: replyToCommentId,
          ),
        },
      )
      .toString();
}
