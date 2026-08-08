import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

String? buildProfileInteractionCommentRoute({
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
  final cleanReplyToCommentId = replyToCommentId?.trim() ?? '';
  return AppRoutePaths.workBrowser(
    workId: cleanWorkId,
    filter: filter?.trim().isNotEmpty == true ? filter!.trim() : null,
    source: source,
    openComments: 'true',
    commentEntrySource: entrySource.trim(),
    targetParentCommentId: isReply ? cleanParentCommentId : null,
    targetReplyId: isReply ? cleanCommentId : null,
    targetCommentId: isReply ? null : cleanCommentId,
    replyToCommentId: cleanReplyToCommentId.isEmpty
        ? null
        : cleanReplyToCommentId,
  );
}
